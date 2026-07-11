"""
启动协调器模块
按拓扑顺序协调节点启动（Shared Buffer版本）
"""

import time
import subprocess
from typing import Callable, Dict, List, Optional

from runtime.config.models import NodeInstance
from runtime.orchestrator.node_launcher import NodeLauncher
from runtime.node_hub.node_registry import NodeRegistry
from runtime.utils.errors import NodeStartupError
from runtime.utils.logger import get_logger

logger = get_logger(__name__)


class StartupCoordinator:
    """启动协调器"""

    def __init__(self, launcher: NodeLauncher, registry: NodeRegistry):
        """
        初始化启动协调器

        参数：
        - launcher: NodeLauncher对象
        - registry: NodeRegistry对象
        """
        self.launcher = launcher
        self.registry = registry

    def startup_nodes(
        self,
        layers: List[List[str]],
        nodes: Dict[str, NodeInstance],
        startup_timeout: float = 30.0,
        startup_delay: float = 2.0,
        should_cancel: Optional[Callable[[], bool]] = None,
    ) -> Dict[str, subprocess.Popen]:
        """
        按拓扑层次启动节点（ZeroMQ版本）

        启动策略：
        1. 按层次顺序处理
        2. 同一层内的节点并行启动
        3. 等待该层所有节点启动完成（超时检测）
        4. 再启动下一层

        与Shared Buffer版本的区别：
        - 无需预分配缓冲区，ZMQ自动管理
        - PUB socket bind，SUB socket connect
        - 分层启动确保PUB先于SUB启动

        参数：
        - layers: 拓扑排序的分层结果 [[layer0], [layer1], ...]
        - nodes: 节点实例字典 {node_id: NodeInstance}
        - startup_timeout: 每层启动超时（秒）
        - startup_delay: 层之间的延迟（秒）

        返回：
        - 节点ID -> subprocess.Popen对象的映射

        异常：
        - NodeStartupError: 节点启动失败
        """
        processes = {}

        logger.info(f"Starting {len(nodes)} nodes in {len(layers)} layers")
        logger.info("Using ZeroMQ IPC for inter-node communication")

        try:
            # ========== 按层启动节点 ==========
            for layer_idx, layer_nodes in enumerate(layers):
                if should_cancel and should_cancel():
                    logger.info("Startup cancelled before next layer")
                    break

                logger.info(f"=== Starting Layer {layer_idx} ({len(layer_nodes)} nodes) ===")
                logger.info(f"Nodes: {layer_nodes}")

                layer_processes = self._start_layer(
                    layer_nodes, nodes, should_cancel=should_cancel
                )
                processes.update(layer_processes)

                self._wait_for_layer(
                    layer_processes, startup_timeout, should_cancel=should_cancel
                )

                # 层之间延迟（给ZMQ SUB时间连接到PUB）
                if layer_idx < len(layers) - 1:
                    logger.debug(f"Waiting {startup_delay}s before starting next layer (ZMQ connection setup)")
                    delay_deadline = time.time() + startup_delay
                    while time.time() < delay_deadline:
                        if should_cancel and should_cancel():
                            logger.info("Startup cancelled during layer delay")
                            return processes
                        time.sleep(min(0.1, delay_deadline - time.time()))
        except Exception:
            if processes:
                logger.info("Startup failed; rolling back started nodes")
                self.shutdown_nodes(processes)
            raise

        logger.info(f"All {len(processes)} nodes started successfully")
        return processes

    def _start_layer(
        self,
        layer_nodes: List[str],
        nodes: Dict[str, NodeInstance],
        should_cancel: Optional[Callable[[], bool]] = None,
    ) -> Dict[str, subprocess.Popen]:
        """
        启动一层中的所有节点

        参数：
        - layer_nodes: 节点ID列表
        - nodes: 节点实例字典

        返回：
        - 节点ID -> subprocess.Popen对象的映射

        异常：
        - NodeStartupError: 节点启动失败
        """
        layer_processes = {}
        node_id = "<unknown>"

        try:
            for node_id in layer_nodes:
                if should_cancel and should_cancel():
                    logger.info("Startup cancelled while starting layer")
                    break

                node = nodes[node_id]
                manifest = self.registry.get_manifest(node.package)

                if not manifest:
                    raise NodeStartupError(
                        node_id,
                        f"Node package '{node.package}' not found in registry"
                    )

                # 启动节点
                process = self.launcher.launch(node, manifest)
                layer_processes[node_id] = process

                logger.info(f"  ✓ Node '{node_id}' started (PID {process.pid})")
        except Exception as e:
            logger.error(f"  ✗ Node '{node_id}' failed to start: {e}")
            if layer_processes:
                self.shutdown_nodes(layer_processes)
            if isinstance(e, NodeStartupError):
                raise
            raise NodeStartupError(node_id, str(e)) from e

        return layer_processes

    def _wait_for_layer(
        self,
        processes: Dict[str, subprocess.Popen],
        timeout: float,
        should_cancel: Optional[Callable[[], bool]] = None,
    ):
        """
        等待该层节点启动完成

        策略：
        - 轮询检查进程是否立即退出（启动失败）
        - 等待指定时间后认为启动成功

        参数：
        - processes: 节点ID -> subprocess.Popen对象的映射
        - timeout: 超时时间（秒）

        异常：
        - NodeStartupError: 节点启动失败（进程立即退出）
        """
        start_time = time.time()
        check_interval = 0.5  # 每0.5秒检查一次

        while time.time() - start_time < timeout:
            if should_cancel and should_cancel():
                logger.info("Startup cancelled while waiting for layer")
                return

            all_alive = True

            # 检查所有进程
            for node_id, process in processes.items():
                ret_code = process.poll()

                if ret_code is not None:
                    # 进程已退出（启动失败）
                    logger.error(f"Node '{node_id}' exited immediately with code {ret_code}")

                    # 尝试获取错误输出
                    try:
                        stdout, stderr = process.communicate(timeout=0.1)
                        if stderr:
                            logger.error(f"Node '{node_id}' stderr: {stderr[:500]}")
                    except:
                        pass

                    raise NodeStartupError(
                        node_id,
                        f"Process exited with code {ret_code}"
                    )

            # 短暂休眠
            time.sleep(check_interval)

        logger.debug(f"Layer startup wait completed ({timeout}s)")

    def shutdown_nodes(
        self,
        processes: Dict[str, subprocess.Popen],
        shutdown_timeout: float = 5.0
    ):
        """
        关闭所有节点

        按启动的反向顺序关闭

        参数：
        - processes: 节点ID -> subprocess.Popen对象的映射
        - shutdown_timeout: 每个节点的关闭超时（秒）
        """
        logger.info(f"Shutting down {len(processes)} nodes")

        # 反向关闭（后启动的先关闭）
        for node_id in reversed(list(processes.keys())):
            process = processes[node_id]
            try:
                self.launcher.terminate_process(process, node_id, shutdown_timeout)
            except Exception as e:
                logger.error(f"Error shutting down node '{node_id}': {e}")

        logger.info("All nodes shut down")
