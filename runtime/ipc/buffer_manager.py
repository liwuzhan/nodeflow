"""
共享缓冲区管理器

负责在运行时启动前预分配所有端口的共享缓冲区。
这是与Socket-based IPC的根本区别：缓冲区必须在节点启动前就创建好。
"""

import logging
from pathlib import Path
from typing import Dict, Optional
from .shared_buffer import SharedPortBuffer

logger = logging.getLogger(__name__)


class BufferManager:
    """
    缓冲区管理器

    职责：
    1. 根据数据流配置预分配所有端口的共享缓冲区
    2. 提供缓冲区查询接口（给节点使用）
    3. 管理缓冲区生命周期（创建、清理）
    """

    def __init__(self, buffer_size: int = 1024 * 1024):
        """
        初始化缓冲区管理器

        Args:
            buffer_size: 每个缓冲区的大小（默认1MB）
        """
        self.buffer_size = buffer_size
        self.buffers: Dict[str, SharedPortBuffer] = {}
        logger.info(f"BufferManager initialized (buffer_size={buffer_size})")

    def initialize(self, nodes_config: dict, manifest_loader):
        """
        根据数据流配置初始化所有缓冲区

        这个方法必须在启动任何节点之前调用！

        Args:
            nodes_config: 节点配置字典 {node_id: node_info}
            manifest_loader: Manifest加载函数 (node_type -> manifest)
        """
        logger.info("Initializing shared buffers for all ports...")

        buffer_count = 0

        for node_id, node_info in nodes_config.items():
            # 加载节点的manifest
            node_type = node_info.get('node_type') or node_info.get('package')
            if not node_type:
                logger.warning(f"Node {node_id} has no node_type, skipping")
                continue

            try:
                manifest = manifest_loader(node_type)
            except Exception as e:
                logger.error(f"Failed to load manifest for {node_type}: {e}")
                continue

            # 为所有输出端口创建缓冲区
            outputs = manifest.outputs if manifest.outputs else []
            for output in outputs:
                port_name = output.name
                if not port_name:
                    logger.warning(f"Output port in {node_id} has no name")
                    continue

                # 生成缓冲区名称: node_id.port_name.out
                buffer_name = f"{node_id}.{port_name}.out"

                # 创建缓冲区
                try:
                    buffer = SharedPortBuffer(
                        buffer_name=buffer_name,
                        size=self.buffer_size,
                        create=True
                    )
                    self.buffers[buffer_name] = buffer
                    buffer_count += 1
                    logger.info(f"  ✓ Created buffer: {buffer_name}")
                except Exception as e:
                    logger.error(f"  ✗ Failed to create buffer {buffer_name}: {e}")

        logger.info(f"Shared buffer initialization complete: {buffer_count} buffers created")

    def get_buffer(self, node_id: str, port_name: str) -> Optional[SharedPortBuffer]:
        """
        获取指定端口的缓冲区

        Args:
            node_id: 节点ID
            port_name: 端口名称

        Returns:
            SharedPortBuffer实例，如果不存在返回None
        """
        buffer_name = f"{node_id}.{port_name}.out"
        buffer = self.buffers.get(buffer_name)

        if not buffer:
            logger.warning(f"Buffer not found: {buffer_name}")

        return buffer

    def get_buffer_by_name(self, buffer_name: str) -> Optional[SharedPortBuffer]:
        """
        根据完整名称获取缓冲区

        Args:
            buffer_name: 完整的缓冲区名称 (如 "sim_output.rtk_fix.out")

        Returns:
            SharedPortBuffer实例，如果不存在返回None
        """
        buffer = self.buffers.get(buffer_name)

        if not buffer:
            logger.warning(f"Buffer not found: {buffer_name}")

        return buffer

    def get_buffer_path(self, node_id: str, port_name: str) -> str:
        """
        获取缓冲区名称（用于环境变量传递）

        Args:
            node_id: 节点ID
            port_name: 端口名称

        Returns:
            缓冲区名称字符串
        """
        return f"{node_id}.{port_name}.out"

    def cleanup(self):
        """
        清理所有缓冲区

        在框架关闭时调用。
        - 关闭所有mmap
        - 删除所有缓冲区文件
        """
        logger.info("Cleaning up shared buffers...")

        # 关闭所有缓冲区
        for buffer_name, buffer in self.buffers.items():
            try:
                buffer.close()
                logger.debug(f"Closed buffer: {buffer_name}")
            except Exception as e:
                logger.warning(f"Error closing buffer {buffer_name}: {e}")

        self.buffers.clear()

        # 清理缓冲区目录
        try:
            SharedPortBuffer.cleanup_all()
        except Exception as e:
            logger.error(f"Error cleaning up buffer directory: {e}")

        logger.info("Buffer cleanup complete")

    def list_buffers(self) -> Dict[str, dict]:
        """
        列出所有缓冲区的状态（用于调试）

        Returns:
            缓冲区名称 -> 状态信息的字典
        """
        status = {}

        for buffer_name, buffer in self.buffers.items():
            try:
                counter = buffer.get_current_sequence()
                status[buffer_name] = {
                    'counter': counter,
                    'has_data': counter > 0,
                    'size': buffer.buffer_size
                }
            except Exception as e:
                status[buffer_name] = {
                    'error': str(e)
                }

        return status

    def __del__(self):
        """析构函数：确保清理资源"""
        try:
            self.cleanup()
        except:
            pass
