"""
环境变量构建器模块
为节点进程构建完整的环境变量字典
"""

import os
from typing import Dict

from runtime.config.models import NodeInstance, NodeManifest, Edge
from runtime.ipc.socket_manager import SocketManager
from runtime.utils.logger import get_logger
from typing import List

logger = get_logger(__name__)


class EnvBuilder:
    """环境变量构建器"""

    @staticmethod
    def build_env(
        node: NodeInstance,
        manifest: NodeManifest,
        socket_manager: SocketManager,
        node_hub_path: str,
        edges: List[Edge]
    ) -> Dict[str, str]:
        """
        为节点构建环境变量字典

        构建的环境变量包括：
        - NODE_ID: 节点实例ID
        - NODE_HUB_PATH: 节点库根目录
        - NODE_SOCKET_DIR: socket临时目录
        - NODE_IN_<PORT_NAME>: 输入端口socket路径（对应每个输入端口）
        - NODE_OUT_<PORT_NAME>: 输出端口socket路径（对应每个输出端口）

        参数：
        - node: NodeInstance对象
        - manifest: NodeManifest对象
        - socket_manager: SocketManager对象
        - node_hub_path: 节点库根目录

        返回：
        - 环境变量字典
        """
        # 复制当前环境
        env = os.environ.copy()

        # 添加通用环境变量
        env['NODE_ID'] = node.id
        env['NODE_HUB_PATH'] = node_hub_path
        env['NODE_SOCKET_DIR'] = str(socket_manager.socket_dir)

        logger.debug(f"Building environment for node '{node.id}':")
        logger.debug(f"  NODE_ID={node.id}")
        logger.debug(f"  NODE_HUB_PATH={node_hub_path}")
        logger.debug(f"  NODE_SOCKET_DIR={socket_manager.socket_dir}")

        # 为每个输入端口添加环境变量
        for input_port in manifest.inputs:
            port_name = input_port.name

            # 查找连接到此输入端口的边
            source_edge = None
            for edge in edges:
                if edge.to_node == node.id and edge.to_port == port_name:
                    source_edge = edge
                    break

            if source_edge:
                # 使用上游节点的输出socket路径
                socket_path = socket_manager.get_channel_path(
                    source_edge.from_node, source_edge.from_port, 'out'
                )
                if socket_path is None:
                    logger.warning(
                        f"Output socket for edge {source_edge.from_node}.{source_edge.from_port} "
                        f"not found. This socket should be created by the source node."
                    )
                    continue
            else:
                # 输入端口没有连接，跳过
                logger.warning(
                    f"Input port '{port_name}' of node '{node.id}' has no connection, skipping"
                )
                continue

            env_var_name = f'NODE_IN_{port_name}'
            env[env_var_name] = socket_path
            logger.debug(f"  {env_var_name}={socket_path}")

        # 为每个输出端口添加环境变量
        for output_port in manifest.outputs:
            port_name = output_port.name
            socket_path = socket_manager.create_channel_path(
                node.id, port_name, 'out'
            )
            env_var_name = f'NODE_OUT_{port_name}'
            env[env_var_name] = socket_path

            logger.debug(f"  {env_var_name}={socket_path}")

        return env
