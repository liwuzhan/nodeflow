"""
启动协调器模块
按拓扑顺序协调节点启动（纯 SharedBuffer IPC）

启动等待为 readiness 驱动（W2-5）：
- heartbeat（默认）：{node_id}.health 存在且新鲜即就绪
- first_output：全部输出 buffer seq>0 即就绪（静态输出节点 opt-in，
  在 node.yaml 中声明 readiness: first_output）
- startup_timeout 是 readiness 上限，超时告警放行（与历史宽容度一致）
"""

import time
import subprocess
from typing import Callable, Dict, List, Optional

from edge.runtime.config.models import NodeInstance
from edge.runtime.orchestrator.node_launcher import NodeLauncher
from edge.runtime.node_hub.node_registry import NodeRegistry
from edge.runtime.utils.errors import NodeStartupError
from edge.runtime.utils.logger import get_logger

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
        按拓扑层次启动节点

        启动策略：
        1. 按层次顺序处理
        2. 同一层内的节点并行启动
        3. 等待该层所有节点启动完成（超时检测）
        4. 再启动下一层

        SharedBuffer 语义说明：
        - 无需预分配缓冲区，首个打开者按配置尺寸创建
        - latest-value 语义天然支持后启动的读者读取历史快照
        - 分层启动确保上游生产者先于下游消费者就绪

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
        logger.info("Using SharedBuffer (mmap) for inter-node communication")

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
                    layer_processes, nodes, startup_timeout, should_cancel=should_cancel
                )

                # 层之间短延迟（下游读者同步上游已有快照；SharedBuffer 无连接建立开销）
                if layer_idx < len(layers) - 1:
                    logger.debug(f"Waiting {startup_delay}s before starting next layer")
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
        nodes: Dict[str, NodeInstance],
        timeout: float,
        should_cancel: Optional[Callable[[], bool]] = None,
    ):
        """
        等待该层节点就绪（readiness 驱动，W2-5）

        策略：
        - 每 0.1s 轮询：进程立即退出 → 抛错回滚；readiness 达成 → 进入下一层
        - readiness 信号由节点 manifest 声明（heartbeat | first_output）
        - 超时告警放行（不阻塞整图启动）

        参数：
        - processes: 节点ID -> subprocess.Popen对象的映射
        - nodes: 节点实例字典（用于查 manifest 的 readiness 声明）
        - timeout: readiness 上限（秒）

        异常：
        - NodeStartupError: 节点启动失败（进程立即退出）
        """
        start_time = time.time()
        check_interval = 0.1
        pending = set(processes.keys())

        while pending:
            if should_cancel and should_cancel():
                logger.info("Startup cancelled while waiting for layer")
                return

            # 进程退出检查（保留：启动初期崩溃快速失败）
            for node_id in list(pending):
                ret_code = processes[node_id].poll()
                if ret_code is not None:
                    logger.error(f"Node '{node_id}' exited immediately with code {ret_code}")
                    try:
                        _, stderr = processes[node_id].communicate(timeout=0.1)
                        if stderr:
                            logger.error(f"Node '{node_id}' stderr: {stderr[:500]}")
                    except Exception:
                        pass
                    raise NodeStartupError(
                        node_id, f"Process exited with code {ret_code}"
                    )

            # readiness 检查
            for node_id in list(pending):
                if self._node_is_ready(node_id, nodes.get(node_id)):
                    logger.info(f"  ✓ Node '{node_id}' ready")
                    pending.discard(node_id)

            if not pending:
                break

            if time.time() - start_time >= timeout:
                logger.warning(
                    f"Layer readiness timeout ({timeout}s), continuing anyway. "
                    f"Nodes not ready yet: {sorted(pending)}"
                )
                return

            time.sleep(check_interval)

    def _node_is_ready(self, node_id: str, node: Optional[NodeInstance]) -> bool:
        """节点 readiness 判定（manifest 缺失时不阻塞启动）"""
        if node is None:
            return True
        try:
            manifest = self.registry.get_manifest(node.package)
        except Exception:
            return True
        if not manifest:
            return True

        mode = manifest.readiness or "heartbeat"
        if mode == "first_output":
            output_names = [f"{node_id}.{p.name}" for p in manifest.outputs]
            if not output_names:
                return True
            return all(self._buffer_has_data(n) for n in output_names)

        # 默认 heartbeat
        return self._health_is_fresh(node_id)

    def _health_is_fresh(self, node_id: str) -> bool:
        try:
            from edge.sdk.health_reader import health_is_fresh, read_node_health

            return health_is_fresh(read_node_health(node_id))
        except Exception:
            return False

    def _buffer_has_data(self, buffer_name: str) -> bool:
        try:
            from edge.sdk.shared_buffer_lite import SharedBufferLite

            buf = SharedBufferLite(buffer_name, create=False)
            seq = buf.get_sequence()
            buf.close()
            return seq > 0
        except Exception:
            return False

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
