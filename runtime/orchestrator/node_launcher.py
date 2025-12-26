"""
节点启动管理器模块
负责启动单个节点进程
"""

import subprocess
import json
import os
from pathlib import Path
from typing import Dict, Optional, TextIO, Tuple

from runtime.config.models import NodeInstance, NodeManifest, EntryPoint
from runtime.orchestrator.env_builder import EnvBuilder
from runtime.utils.errors import NodeLaunchError
from runtime.utils.logger import get_logger
from runtime.utils.constants import LOGS_DIR

logger = get_logger(__name__)


class NodeLauncher:
    """节点启动管理器"""

    def __init__(self, node_hub_path: str, edges: list):
        """
        初始化节点启动管理器

        参数：
        - node_hub_path: 节点库根目录
        - socket_manager: SocketManager对象
        - edges: 图的边列表
        """
        self.node_hub_path = node_hub_path
        self.edges = edges
        self.env_builder = EnvBuilder()

        # 节点日志文件管理
        self.log_dir = Path(LOGS_DIR)
        self.log_dir.mkdir(exist_ok=True, parents=True)
        self.log_files: Dict[str, Tuple[TextIO, TextIO]] = {}

    def launch(
        self, node: NodeInstance, manifest: NodeManifest, platform: str = "linux"
    ) -> subprocess.Popen:
        """
        启动单个节点

        步骤：
        1. 获取entrypoint（使用节点实例的覆盖或manifest中的默认）
        2. 构建环境变量
        3. 构建命令行（追加--params参数）
        4. 设置工作目录（节点包目录）
        5. 启动subprocess

        参数：
        - node: NodeInstance对象
        - manifest: NodeManifest对象
        - platform: 平台名（默认linux）

        返回：
        - subprocess.Popen对象

        异常：
        - NodeLaunchError: 启动失败
        """
        logger.info(f"Launching node '{node.id}' (package: {node.package})")

        # 1. 获取启动入口
        entrypoint = self._get_entrypoint(node, manifest, platform)
        if not entrypoint:
            raise NodeLaunchError(
                node.id, f"No entrypoint found for platform '{platform}'"
            )

        # 2. 构建环境变量（Shared Buffer版本：不再需要socket_manager）
        env = self.env_builder.build_env(
            node, manifest, self.node_hub_path, self.edges
        )

        # 3. 构建命令
        cmd = self._build_command(node, entrypoint)
        logger.debug(f"Command: {' '.join(cmd)}")

        # 4. 设置工作目录（节点包目录）
        cwd = os.path.join(self.node_hub_path, node.package)
        if not os.path.isdir(cwd):
            raise NodeLaunchError(node.id, f"Node package directory not found: {cwd}")

        # 5-6. 创建日志文件并启动进程（重定向到文件避免管道阻塞）
        try:
            stdout_file = open(self.log_dir / f"{node.id}.stdout.log", "w", buffering=1)
            stderr_file = open(self.log_dir / f"{node.id}.stderr.log", "w", buffering=1)
            self.log_files[node.id] = (stdout_file, stderr_file)

            process = subprocess.Popen(
                cmd, env=env, cwd=cwd, stdout=stdout_file, stderr=stderr_file, text=True
            )

            logger.info(f"Node '{node.id}' started with PID {process.pid}")
            logger.debug(
                f"Node '{node.id}' logs: {self.log_dir / node.id}.{{stdout,stderr}}.log"
            )
            return process

        except FileNotFoundError:
            self.close_node_logs(node.id)
            raise NodeLaunchError(
                node.id,
                f"Command not found: {cmd[0]}. Ensure the entrypoint is correct.",
            )
        except PermissionError:
            self.close_node_logs(node.id)
            raise NodeLaunchError(node.id, f"Permission denied executing: {cmd[0]}")
        except Exception as e:
            self.close_node_logs(node.id)
            raise NodeLaunchError(node.id, f"Failed to start process: {e}")

    def _get_entrypoint(
        self, node: NodeInstance, manifest: NodeManifest, platform: str
    ) -> Optional[EntryPoint]:
        """
        获取节点的启动入口

        优先使用节点实例的覆盖入口，否则使用manifest中的默认入口

        参数：
        - node: NodeInstance对象
        - manifest: NodeManifest对象
        - platform: 平台名

        返回：
        - EntryPoint对象，如果不存在返回None
        """
        # 优先使用节点实例的覆盖入口
        if node.entrypoint:
            logger.debug(f"Using overridden entrypoint for node '{node.id}'")
            return node.entrypoint

        # 否则使用manifest中的默认入口
        entrypoint = manifest.entrypoints.get(platform)
        if not entrypoint:
            logger.warning(
                f"No entrypoint for platform '{platform}' in node '{node.id}'"
            )
            return None

        return entrypoint

    def _build_command(self, node: NodeInstance, entrypoint: EntryPoint) -> list:
        """
        构建启动命令

        格式：[cmd...] + ["--params", json_params]

        例如：
        ["python3", "run.py", "--params", '{"device":"/dev/ttyUSB0"}']

        参数：
        - node: NodeInstance对象
        - entrypoint: EntryPoint对象

        返回：
        - 命令数组
        """
        cmd = entrypoint.cmd.copy()

        # 追加--params参数
        if node.params:
            params_json = json.dumps(node.params)
            cmd.extend(["--params", params_json])

        return cmd

    def check_process_health(self, process: subprocess.Popen, node_id: str) -> bool:
        """
        检查进程健康状态

        参数：
        - process: subprocess.Popen对象
        - node_id: 节点ID

        返回：
        - True表示进程运行中，False表示进程已退出
        """
        ret_code = process.poll()

        if ret_code is not None:
            # 进程已退出
            logger.warning(
                f"Node '{node_id}' (PID {process.pid}) exited with code {ret_code}"
            )

            # 读取日志文件最后几行（如果存在）
            try:
                stdout_log = self.log_dir / f"{node_id}.stdout.log"
                stderr_log = self.log_dir / f"{node_id}.stderr.log"

                if stdout_log.exists():
                    with open(stdout_log, "r") as f:
                        lines = f.readlines()
                        if lines:
                            last_lines = "".join(lines[-5:])  # 最后5行
                            logger.debug(
                                f"Node '{node_id}' stdout (last 5 lines):\n{last_lines}"
                            )

                if stderr_log.exists():
                    with open(stderr_log, "r") as f:
                        lines = f.readlines()
                        if lines:
                            last_lines = "".join(lines[-5:])  # 最后5行
                            logger.error(
                                f"Node '{node_id}' stderr (last 5 lines):\n{last_lines}"
                            )
            except Exception as e:
                logger.warning(f"Failed to read log files for node '{node_id}': {e}")

            return False

        return True

    def terminate_process(
        self, process: subprocess.Popen, node_id: str, timeout: float = 5.0
    ):
        """
        优雅地终止进程

        策略: SIGTERM → wait(timeout) → SIGKILL if needed

        参数：
        - process: subprocess.Popen对象
        - node_id: 节点ID
        - timeout: SIGTERM 后等待的秒数，超时则 SIGKILL
        """
        # 检查进程是否已退出
        if process.poll() is not None:
            logger.debug(f"Node '{node_id}' already exited")
            self.close_node_logs(node_id)
            return

        logger.info(f"Terminating node '{node_id}' (PID {process.pid})")

        try:
            # 发送 SIGTERM 进行优雅关闭
            try:
                process.terminate()
            except ProcessLookupError:
                # 进程在 poll() 和 terminate() 之间退出
                logger.debug(f"Node '{node_id}' exited before terminate signal")
                self.close_node_logs(node_id)
                return

            # 等待优雅退出
            try:
                process.wait(timeout=timeout)
                logger.info(f"Node '{node_id}' terminated gracefully")
            except subprocess.TimeoutExpired:
                # 优雅关闭超时，强制 kill
                logger.warning(f"Node '{node_id}' did not terminate in {timeout}s, sending SIGKILL")
                try:
                    process.kill()
                    process.wait(timeout=2.0)  # SIGKILL 后短暂等待
                    logger.info(f"Node '{node_id}' killed")
                except ProcessLookupError:
                    # 进程在超时后但 kill 前退出
                    logger.debug(f"Node '{node_id}' exited before kill signal")
                except subprocess.TimeoutExpired:
                    # 极端罕见: 进程无响应 SIGKILL (内核问题)
                    logger.error(f"Node '{node_id}' did not respond to SIGKILL")

        except ProcessLookupError:
            # 进程在终止过程中退出
            logger.debug(f"Node '{node_id}' exited during termination")
        except OSError as e:
            # 处理其他 OS 级别错误（权限等）
            logger.error(f"OS error terminating node '{node_id}': {e}")
        except Exception as e:
            logger.error(f"Unexpected error terminating node '{node_id}': {e}")
        finally:
            # 总是关闭日志文件
            self.close_node_logs(node_id)

    def close_node_logs(self, node_id: str):
        """
        关闭特定节点的日志文件

        参数：
        - node_id: 节点ID
        """
        if node_id in self.log_files:
            stdout_file, stderr_file = self.log_files[node_id]
            try:
                stdout_file.close()
                stderr_file.close()
            except Exception as e:
                logger.warning(f"Error closing log files for node '{node_id}': {e}")
            finally:
                del self.log_files[node_id]

    def cleanup(self):
        """
        清理所有资源

        关闭所有打开的日志文件
        """
        logger.debug("Cleaning up NodeLauncher resources")
        for node_id in list(self.log_files.keys()):
            self.close_node_logs(node_id)
