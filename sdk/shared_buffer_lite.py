"""
轻量级共享缓冲区（用于混合ZMQ方案）

这是一个简化版的SharedBuffer，只用于持久化最新值。
与完整版SharedBuffer的区别：
- 只存储一个值（最新值）
- 配合ZMQ使用，不单独作为IPC机制
- 更简单的实现，无需复杂的同步
"""

import mmap
import json
import struct
from pathlib import Path
from typing import Optional, Dict, Any

# 缓冲区布局:
# [0-3]   序列号 (uint32)
# [4-7]   数据长度 (uint32)
# [8-N]   数据内容 (JSON)

class SharedBufferLite:
    """轻量级共享缓冲区"""

    HEADER_SIZE = 8  # 4 bytes sequence + 4 bytes length
    DEFAULT_SIZE = 1024 * 1024  # 1MB (默认大小，可通过配置调整)

    def __init__(self, buffer_name: str, size: int = DEFAULT_SIZE, create: bool = True):
        """
        初始化共享缓冲区

        Args:
            buffer_name: 缓冲区名称 (如 "sim_output.rtk_fix")
            size: 缓冲区大小 (默认64KB)
            create: 是否创建新缓冲区
        """
        self.buffer_name = buffer_name
        self.size = size

        # 缓冲区文件路径
        buffer_dir = Path("/tmp/nodeflow/buffers")
        buffer_dir.mkdir(parents=True, exist_ok=True)
        self.buffer_path = buffer_dir / f"{buffer_name}.buf"

        if create:
            # 创建新文件
            with open(self.buffer_path, 'wb') as f:
                f.write(b'\x00' * size)

        # 打开mmap
        self.file = open(self.buffer_path, 'r+b')
        self.mmap = mmap.mmap(self.file.fileno(), size)

    def write(self, data: Dict[str, Any]) -> int:
        """
        写入数据（覆盖式）

        Args:
            data: 要写入的数据字典

        Returns:
            新的序列号
        """
        # 序列化数据
        serialized = json.dumps(data).encode('utf-8')
        data_length = len(serialized)

        if data_length > (self.size - self.HEADER_SIZE):
            raise ValueError(f"Data too large: {data_length} bytes (max {self.size - self.HEADER_SIZE})")

        # 读取当前序列号并递增
        current_seq = struct.unpack('<I', self.mmap[0:4])[0]
        new_seq = (current_seq + 1) & 0xFFFFFFFF

        # 写入新数据
        self.mmap[0:4] = struct.pack('<I', new_seq)
        self.mmap[4:8] = struct.pack('<I', data_length)
        self.mmap[8:8+data_length] = serialized

        # 刷新到磁盘
        self.mmap.flush()

        return new_seq

    def read(self) -> Optional[Dict[str, Any]]:
        """
        读取最新数据

        Returns:
            数据字典，如果无数据返回None
        """
        # 读取序列号
        sequence = struct.unpack('<I', self.mmap[0:4])[0]
        if sequence == 0:
            return None  # 还没有写入过数据

        # 读取数据长度
        length = struct.unpack('<I', self.mmap[4:8])[0]
        if length == 0 or length > (self.size - self.HEADER_SIZE):
            return None  # 数据无效

        # 读取数据
        serialized = bytes(self.mmap[8:8+length])
        try:
            return json.loads(serialized.decode('utf-8'))
        except (json.JSONDecodeError, UnicodeDecodeError):
            return None

    def get_sequence(self) -> int:
        """获取当前序列号"""
        return struct.unpack('<I', self.mmap[0:4])[0]

    def close(self):
        """关闭缓冲区"""
        if self.mmap:
            self.mmap.close()
        if self.file:
            self.file.close()

    def __del__(self):
        """析构函数"""
        try:
            self.close()
        except:
            pass

    @staticmethod
    def cleanup_all():
        """清理所有缓冲区文件"""
        buffer_dir = Path("/tmp/nodeflow/buffers")
        if buffer_dir.exists():
            for buf_file in buffer_dir.glob("*.buf"):
                try:
                    buf_file.unlink()
                except:
                    pass
