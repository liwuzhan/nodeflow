"""
节点启动管理器模块
负责启动单个节点进程
"""

import subprocess
import json
import os
import sys
import signal
from pathlib import Path
from typing import Dict, Optional, TextIO, Tuple
import threading
import logging
from logging.handlers import RotatingFileHandler

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
        try:
            entrypoint = self._get_entrypoint(node, manifest, platform)
            if not entrypoint:
                raise NodeLaunchError(
                    node.id, f"No entrypoint found for platform '{platform}'"
                )
        except Exception as e:
            logger.error(f"Failed to get entrypoint for {node.id}: {e}")
            raise

        # 2. 构建环境变量（Shared Buffer版本：不再需要socket_manager）
        try:
            env = self.env_builder.build_env(
                node, manifest, self.node_hub_path, self.edges
            )
        except Exception as e:
            logger.error(f"Failed to build env for {node.id}: {e}")
            raise

        # 3. 构建命令
        try:
            cmd = self._build_command(node, entrypoint)
            logger.debug(f"Command: {' '.join(cmd)}")
        except Exception as e:
            logger.error(f"Failed to build command for {node.id}: {e}")
            raise

        # 4. 设置工作目录（节点包目录）
        cwd = os.path.join(self.node_hub_path, node.package)
        if not os.path.isdir(cwd):
            raise NodeLaunchError(node.id, f"Node package directory not found: {cwd}")

        # 5-6. 创建日志处理器并启动进程（管道→轮转文件）
        try:
            stdout_path = self.log_dir / f"{node.id}.stdout.log"
            stderr_path = self.log_dir / f"{node.id}.stderr.log"

            stdout_handler = RotatingFileHandler(
                stdout_path, maxBytes=1024 * 1024 * 1024, backupCount=30
            )
            stderr_handler = RotatingFileHandler(
                stderr_path, maxBytes=1024 * 1024 * 1024, backupCount=30
            )

            stdout_logger = logging.getLogger(f"node.{node.id}.stdout")
            stderr_logger = logging.getLogger(f"node.{node.id}.stderr")
            stdout_logger.setLevel(logging.INFO)
            stderr_logger.setLevel(logging.ERROR)
            stdout_logger.propagate = False
            stderr_logger.propagate = False
            if not any(isinstance(h, RotatingFileHandler) and h.baseFilename == str(stdout_path) for h in stdout_logger.handlers):
                stdout_logger.addHandler(stdout_handler)
            if not any(isinstance(h, RotatingFileHandler) and h.baseFilename == str(stderr_path) for h in stderr_logger.handlers):
                stderr_logger.addHandler(stderr_handler)
            self.log_files[node.id] = (stdout_handler, stderr_handler)

            # 创建子进程，使用独立的进程组以便后续清理
            # start_new_session=True 确保子进程在新的会话中，便于批量终止
            process = subprocess.Popen(
                cmd,
                env=env,
                cwd=cwd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                start_new_session=True  # Unix/macOS: 创建新会话，便于清理整个进程树
            )

            def _forward(stream, logger, level_func):
                while True:
                    if stream is None:
                        break
                    line = stream.readline()
                    if not line:
                        if process.poll() is not None:
                            break
                        continue
                    level_func(line.rstrip("\n"))

            t_out = threading.Thread(
                target=_forward, args=(process.stdout, stdout_logger, stdout_logger.info), daemon=True
            )
            t_err = threading.Thread(
                target=_forward, args=(process.stderr, stderr_logger, stderr_logger.error), daemon=True
            )
            t_out.start()
            t_err.start()
            if not hasattr(self, "log_threads"):
                self.log_threads = {}
            self.log_threads[node.id] = (t_out, t_err)

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
        优雅地终止进程及其整个进程组

        策略: SIGTERM(进程组) → wait(timeout) → SIGKILL(进程组) if needed

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
            # 发送 SIGTERM 到整个进程组（包括所有子进程）
            # 当使用 start_new_session=True 时，process.pid 就是进程组 ID
            try:
                if sys.platform != "win32":
                    # Unix/macOS: 杀死整个进程组
                    os.killpg(os.getpgid(process.pid), signal.SIGTERM)
                else:
                    # Windows: 无法杀死进程组，只能杀死主进程
                    process.terminate()
            except ProcessLookupError:
                # 进程在 poll() 和 terminate() 之间退出
                logger.debug(f"Node '{node_id}' exited before terminate signal")
                self.close_node_logs(node_id)
                return
            except OSError as e:
                logger.warning(f"Failed to send SIGTERM to process group for '{node_id}': {e}")
                # 降级到单个进程 kill
                try:
                    process.terminate()
                except ProcessLookupError:
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
                    if sys.platform != "win32":
                        # Unix/macOS: 杀死整个进程组
                        os.killpg(os.getpgid(process.pid), signal.SIGKILL)
                    else:
                        # Windows: 无法杀死进程组
                        process.kill()

                    process.wait(timeout=2.0)  # SIGKILL 后短暂等待
                    logger.info(f"Node '{node_id}' killed")
                except ProcessLookupError:
                    # 进程在超时后但 kill 前退出
                    logger.debug(f"Node '{node_id}' exited before kill signal")
                except OSError:
                    # 进程组已不存在，尝试杀死单个进程
                    try:
                        process.kill()
                        process.wait(timeout=1.0)
                    except (ProcessLookupError, subprocess.TimeoutExpired):
                        logger.debug(f"Node '{node_id}' already exited")
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
        if node_id in getattr(self, "log_threads", {}):
            t_out, t_err = self.log_threads[node_id]
            try:
                t_out.join(timeout=2.0)
            except Exception:
                pass
            try:
                t_err.join(timeout=2.0)
            except Exception:
                pass
            del self.log_threads[node_id]
        if node_id in self.log_files:
            stdout_handler, stderr_handler = self.log_files[node_id]
            try:
                stdout_handler.close()
                stderr_handler.close()
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
