"""
Socket管理器模块
负责创建、管理和清理Unix Domain Socket文件
"""

import os
from pathlib import Path
from typing import Dict, Optional

from runtime.utils.errors import SocketError
from runtime.utils.logger import get_logger

logger = get_logger(__name__)


class SocketManager:
    """Socket管理器"""

    def __init__(self, socket_dir: str = "/tmp/nodeflow_sockets"):
        """
        初始化Socket管理器

        参数：
        - socket_dir: Socket文件的临时目录（默认/tmp/nodeflow_sockets）
        """
        self.socket_dir = Path(socket_dir)
        self._socket_paths: Dict[str, str] = {}  # channel_id -> socket_path

    def initialize(self):
        """
        初始化Socket目录

        创建临时目录（如果不存在）
        """
        try:
            self.socket_dir.mkdir(parents=True, exist_ok=True)
            logger.info(f"Initialized socket directory: {self.socket_dir}")
        except Exception as e:
            raise SocketError(f"Failed to initialize socket directory {self.socket_dir}: {e}")

    def create_channel_path(self, node_id: str, port_name: str, direction: str) -> str:
        """
        生成Socket通道路径

        路径格式：{socket_dir}/nodeflow_{node_id}.{port_name}.{direction}

        例如：/tmp/nodeflow_sockets/nodeflow_rtk_main.gps_fix.out

        参数：
        - node_id: 节点实例ID
        - port_name: 端口名
        - direction: 方向（'in' 或 'out'）

        返回：
        - Socket文件的完整路径
        """
        if direction not in ('in', 'out'):
            raise SocketError(f"Invalid direction: {direction}. Must be 'in' or 'out'")

        channel_id = f"{node_id}.{port_name}.{direction}"
        socket_path = str(self.socket_dir / f"nodeflow_{node_id}.{port_name}.{direction}")

        self._socket_paths[channel_id] = socket_path
        logger.debug(f"Created channel path: {channel_id} -> {socket_path}")

        return socket_path

    def get_channel_path(self, node_id: str, port_name: str, direction: str) -> Optional[str]:
        """
        获取已创建的通道路径

        参数：
        - node_id: 节点实例ID
        - port_name: 端口名
        - direction: 方向（'in' 或 'out'）

        返回：
        - Socket文件路径，如果未创建返回None
        """
        channel_id = f"{node_id}.{port_name}.{direction}"
        return self._socket_paths.get(channel_id)

    def cleanup(self):
        """
        清理所有Socket文件

        删除所有已创建的Socket文件（通常在框架关闭时调用）
        """
        cleaned = 0
        errors = []

        for channel_id, socket_path in self._socket_paths.items():
            try:
                path = Path(socket_path)
                if path.exists():
                    path.unlink()
                    cleaned += 1
                    logger.debug(f"Cleaned up socket: {socket_path}")
            except Exception as e:
                errors.append(f"{channel_id}: {e}")

        if errors:
            logger.warning(f"Failed to clean up {len(errors)} socket files: {errors}")

        logger.info(f"Cleaned up {cleaned} socket files")

    def cleanup_socket_file(self, socket_path: str):
        """
        清理单个Socket文件

        参数：
        - socket_path: Socket文件路径
        """
        try:
            path = Path(socket_path)
            if path.exists():
                path.unlink()
                logger.debug(f"Cleaned up socket file: {socket_path}")
        except Exception as e:
            logger.warning(f"Failed to clean up socket file {socket_path}: {e}")

    def get_all_socket_paths(self) -> Dict[str, str]:
        """
        获取所有Socket路径

        返回：
        - channel_id -> socket_path 的映射
        """
        return dict(self._socket_paths)

    def validate_socket_dir(self) -> bool:
        """
        验证Socket目录是否存在且可写

        返回：
        - True表示有效，False表示无效
        """
        if not self.socket_dir.exists():
            logger.warning(f"Socket directory does not exist: {self.socket_dir}")
            return False

        if not self.socket_dir.is_dir():
            logger.warning(f"Socket path is not a directory: {self.socket_dir}")
            return False

        if not os.access(self.socket_dir, os.W_OK):
            logger.warning(f"Socket directory is not writable: {self.socket_dir}")
            return False

        return True
