"""
环境变量构建器模块（ZeroMQ版本）
为节点进程构建完整的环境变量字典
"""

import os
from typing import Dict, List

from runtime.config.models import NodeInstance, NodeManifest, Edge
from runtime.utils.logger import get_logger

logger = get_logger(__name__)


class EnvBuilder:
    """环境变量构建器（ZeroMQ版本）"""

    @staticmethod
    def build_env(
        node: NodeInstance,
        manifest: NodeManifest,
        node_hub_path: str,
        edges: List[Edge]
    ) -> Dict[str, str]:
        """
        为节点构建环境变量字典（ZeroMQ版本）

        构建的环境变量包括：
        - NODE_ID: 节点实例ID
        - NODE_HUB_PATH: 节点库根目录
        - NODE_IN_<PORT_NAME>: 输入端口ZMQ地址（对应每个输入端口）
        - NODE_OUT_<PORT_NAME>: 输出端口ZMQ地址（对应每个输出端口）

        与Shared Buffer版本的区别：
        - 环境变量传递ZMQ地址而非缓冲区名称
        - ZMQ地址格式：ipc:///tmp/nodeflow/source_node.source_port

        参数：
        - node: NodeInstance对象
        - manifest: NodeManifest对象
        - node_hub_path: 节点库根目录
        - edges: 边列表

        返回：
        - 环境变量字典
        """
        # 复制当前环境
        env = os.environ.copy()

        # 添加通用环境变量
        env['NODE_ID'] = node.id
        env['NODE_HUB_PATH'] = node_hub_path

        logger.debug(f"Building environment for node '{node.id}':")
        logger.debug(f"  NODE_ID={node.id}")
        logger.debug(f"  NODE_HUB_PATH={node_hub_path}")

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
                # 生成ZMQ地址：ipc:///tmp/nodeflow/source_node.source_port
                zmq_address = f"ipc:///tmp/nodeflow/{source_edge.from_node}.{source_edge.from_port}"
                env_var_name = f'NODE_IN_{port_name}'
                env[env_var_name] = zmq_address
                logger.debug(f"  {env_var_name}={zmq_address}")
            else:
                # 输入端口没有连接，跳过
                logger.warning(
                    f"Input port '{port_name}' of node '{node.id}' has no connection, skipping"
                )
                continue

        # 为每个输出端口添加环境变量
        for output_port in manifest.outputs:
            port_name = output_port.name

            # 生成ZMQ地址：ipc:///tmp/nodeflow/node_id.port_name
            zmq_address = f"ipc:///tmp/nodeflow/{node.id}.{port_name}"
            env_var_name = f'NODE_OUT_{port_name}'
            env[env_var_name] = zmq_address

            # 添加buffer配置
            buffer_size = getattr(output_port, 'buffer_size', 1024 * 1024)
            conflate = getattr(output_port, 'conflate', True)

            env[f'NODE_OUT_{port_name}_BUFFER_SIZE'] = str(buffer_size)
            env[f'NODE_OUT_{port_name}_CONFLATE'] = str(conflate).lower()

            logger.debug(f"  {env_var_name}={zmq_address} (buffer={buffer_size//1024}KB, conflate={conflate})")

        return env
