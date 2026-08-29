"""
环境变量构建器模块（纯 SharedBuffer IPC）

为节点进程构建环境变量。每个端口对应一个 SharedBuffer 名称，
不再涉及 ZMQ 地址。
"""

import os
from typing import Dict, List, Optional

from edge.runtime.config.models import NodeInstance, NodeManifest, Edge
from edge.runtime.utils.logger import get_logger
from edge.sdk.shared_buffer_lite import IPC_VERSION

logger = get_logger(__name__)


class EnvBuilder:
    """环境变量构建器"""

    @staticmethod
    def build_env(
        node: NodeInstance,
        manifest: NodeManifest,
        node_hub_path: str,
        edges: List[Edge],
        incarnation: int = 1,
    ) -> Dict[str, str]:
        env = os.environ.copy()

        env['NODE_ID'] = node.id

        # IPC 版本握手（W2-1）：SDK 初始化断言，不符大声退出
        env['NODEFLOW_IPC_VERSION'] = str(IPC_VERSION)

        # run 身份与 run 作用域 buffer 目录（W2-2）
        from edge.runtime.utils import constants

        run_id = constants.get_current_run_id()
        if run_id:
            env['NODEFLOW_RUN_ID'] = run_id
            env['NODEFLOW_BUFFERS_DIR'] = constants.get_buffers_dir()
        env['NODEFLOW_INCARNATION'] = str(incarnation)

        # PYTHONPATH: 项目根目录（node_hub_path 的上两级: edge/nodes/../..)）
        project_root = os.path.abspath(os.path.join(node_hub_path, "../.."))
        existing = env.get('PYTHONPATH', '')
        env['PYTHONPATH'] = f"{project_root}:{existing}" if existing else project_root

        env['PYTHONUNBUFFERED'] = '1'

        # 输入端口：env var = 上游 buffer 名
        for input_port in manifest.inputs:
            port_name = input_port.name
            source_edge = None
            for edge in edges:
                if edge.to_node == node.id and edge.to_port == port_name:
                    source_edge = edge
                    break

            if source_edge:
                buffer_name = f"{source_edge.from_node}.{source_edge.from_port}"
                env[f'NODE_IN_{port_name}'] = buffer_name
                logger.debug(f"  NODE_IN_{port_name}={buffer_name}")
            else:
                logger.warning(
                    f"Input port '{port_name}' of node '{node.id}' has no connection, skipping"
                )

        # 输出端口：env var = 自己的 buffer 名
        for output_port in manifest.outputs:
            port_name = output_port.name
            buffer_name = f"{node.id}.{port_name}"
            env[f'NODE_OUT_{port_name}'] = buffer_name

            buffer_size = getattr(output_port, 'buffer_size', 1024 * 1024)
            conflate = getattr(output_port, 'conflate', True)
            env[f'NODE_OUT_{port_name}_BUFFER_SIZE'] = str(buffer_size)
            env[f'NODE_OUT_{port_name}_CONFLATE'] = str(conflate).lower()

            logger.debug(
                f"  NODE_OUT_{port_name}={buffer_name} "
                f"(buffer={buffer_size // 1024}KB, conflate={conflate})"
            )

        return env
