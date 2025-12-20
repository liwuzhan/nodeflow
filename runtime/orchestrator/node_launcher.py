"""
节点启动管理器模块
负责启动单个节点进程
"""

import subprocess
import json
import os
from pathlib import Path
from typing import Optional

from runtime.config.models import NodeInstance, NodeManifest, EntryPoint
from runtime.ipc.socket_manager import SocketManager
from runtime.orchestrator.env_builder import EnvBuilder
from runtime.utils.errors import NodeLaunchError
from runtime.utils.logger import get_logger

logger = get_logger(__name__)


class NodeLauncher:
    """节点启动管理器"""

    def __init__(self, node_hub_path: str, socket_manager: SocketManager, edges: list):
        """
        初始化节点启动管理器

        参数：
        - node_hub_path: 节点库根目录
        - socket_manager: SocketManager对象
        - edges: 图的边列表
        """
        self.node_hub_path = node_hub_path
        self.socket_manager = socket_manager
        self.edges = edges
        self.env_builder = EnvBuilder()

    def launch(
        self,
        node: NodeInstance,
        manifest: NodeManifest,
        platform: str = "linux"
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
                node.id,
                f"No entrypoint found for platform '{platform}'"
            )

        # 2. 构建环境变量
        env = self.env_builder.build_env(
            node, manifest, self.socket_manager, self.node_hub_path, self.edges
        )

        # 3. 构建命令
        cmd = self._build_command(node, entrypoint)
        logger.debug(f"Command: {' '.join(cmd)}")

        # 4. 设置工作目录（节点包目录）
        cwd = os.path.join(self.node_hub_path, node.package)
        if not os.path.isdir(cwd):
            raise NodeLaunchError(
                node.id,
                f"Node package directory not found: {cwd}"
            )

        # 5. 启动进程
        try:
            process = subprocess.Popen(
                cmd,
                env=env,
                cwd=cwd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True
            )

            logger.info(f"Node '{node.id}' started with PID {process.pid}")
            return process

        except FileNotFoundError as e:
            raise NodeLaunchError(
                node.id,
                f"Command not found: {cmd[0]}. Ensure the entrypoint is correct."
            )
        except PermissionError as e:
            raise NodeLaunchError(
                node.id,
                f"Permission denied executing: {cmd[0]}"
            )
        except Exception as e:
            raise NodeLaunchError(
                node.id,
                f"Failed to start process: {e}"
            )

    def _get_entrypoint(
        self,
        node: NodeInstance,
        manifest: NodeManifest,
        platform: str
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
            logger.warning(f"Node '{node_id}' (PID {process.pid}) exited with code {ret_code}")

            # 获取stdout和stderr
            try:
                stdout, stderr = process.communicate(timeout=0.1)
                if stdout:
                    logger.debug(f"Node '{node_id}' stdout: {stdout[:500]}")
                if stderr:
                    logger.error(f"Node '{node_id}' stderr: {stderr[:500]}")
            except subprocess.TimeoutExpired:
                pass

            return False

        return True

    def terminate_process(self, process: subprocess.Popen, node_id: str, timeout: float = 5.0):
        """
        优雅地终止进程

        先尝试SIGTERM，如果超时则使用SIGKILL

        参数：
        - process: subprocess.Popen对象
        - node_id: 节点ID
        - timeout: 等待超时（秒）
        """
        if process.poll() is not None:
            # 进程已退出
            return

        logger.info(f"Terminating node '{node_id}' (PID {process.pid})")

        try:
            # 发送SIGTERM
            process.terminate()

            # 等待进程退出
            try:
                process.wait(timeout=timeout)
                logger.info(f"Node '{node_id}' terminated gracefully")
            except subprocess.TimeoutExpired:
                # 超时，强制kill
                logger.warning(f"Node '{node_id}' did not terminate, killing")
                process.kill()
                process.wait(timeout=1.0)
                logger.info(f"Node '{node_id}' killed")

        except Exception as e:
            logger.error(f"Error terminating node '{node_id}': {e}")
