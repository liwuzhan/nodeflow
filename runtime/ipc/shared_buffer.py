"""
共享端口缓冲区实现

使用mmap实现进程间共享内存缓冲区，支持最新值语义（Latest-Value）的数据交互。

内存布局：
  [0-3]    写入计数器 (uint32) - 用于检测数据更新
  [4-7]    数据长度 (uint32) - 当前数据的字节数
  [8-N]    数据区域 (MsgPack序列化数据)
"""

import mmap
import struct
import msgpack
import os
from pathlib import Path
from threading import Lock
from typing import Optional, Dict, Any
import logging

logger = logging.getLogger(__name__)


class SharedPortBuffer:
    """
    共享端口缓冲区

    提供进程间共享内存的读写接口，实现Latest-Value语义。
    多个进程可以同时访问同一缓冲区：
    - OutputPort: 写入数据（覆盖式）
    - InputPort: 轮询读取（获取最新值）
    """

    BUFFER_SIZE = 1024 * 1024  # 1MB per port
    HEADER_SIZE = 8  # 4字节计数器 + 4字节长度
    DATA_OFFSET = 8

    def __init__(self, buffer_name: str, size: int = BUFFER_SIZE, create: bool = True):
        """
        初始化或打开共享缓冲区

        Args:
            buffer_name: 缓冲区名称 (如 "sim_output.rtk_fix.out")
            size: 缓冲区大小 (默认1MB)
            create: 是否创建新缓冲区 (True) 或打开现有的 (False)
        """
        self.buffer_name = buffer_name
        self.buffer_size = size
        self.buffer_dir = Path('/tmp/nodeflow_buffers')
        self.buffer_dir.mkdir(parents=True, exist_ok=True)

        self.buffer_path = self.buffer_dir / f"{buffer_name}.mem"
        self.fd = None
        self.mmap = None
        self.lock = Lock()

        if create:
            self._create_buffer()
        else:
            self._open_buffer()

        logger.info(f"SharedPortBuffer initialized: {self.buffer_name} (size={self.buffer_size})")

    def _create_buffer(self):
        """创建新的共享缓冲区文件和内存映射"""
        # 清理旧文件
        if self.buffer_path.exists():
            try:
                self.buffer_path.unlink()
                logger.debug(f"Removed old buffer file: {self.buffer_path}")
            except OSError:
                pass

        # 创建新文件并初始化为零
        with open(self.buffer_path, 'wb') as f:
            f.write(b'\x00' * self.buffer_size)

        # 打开并创建内存映射
        self.fd = os.open(str(self.buffer_path), os.O_RDWR)
        self.mmap = mmap.mmap(self.fd, self.buffer_size)
        logger.debug(f"Created shared buffer: {self.buffer_path}")

    def _open_buffer(self):
        """打开现有的共享缓冲区"""
        if not self.buffer_path.exists():
            raise FileNotFoundError(f"Buffer file not found: {self.buffer_path}")

        self.fd = os.open(str(self.buffer_path), os.O_RDWR)
        self.mmap = mmap.mmap(self.fd, self.buffer_size)
        logger.debug(f"Opened shared buffer: {self.buffer_path}")

    def write(self, data: Dict[str, Any]) -> int:
        """
        写入数据（覆盖式）

        OutputPort使用此方法。
        - 序列化数据
        - 递增计数器
        - 直接覆盖缓冲区内容
        - 刷新到磁盘

        Args:
            data: 要写入的数据字典

        Returns:
            新的计数器值

        Raises:
            ValueError: 数据过大（>BUFFER_SIZE - HEADER_SIZE）
        """
        # 序列化数据
        try:
            serialized = msgpack.packb(data, use_bin_type=True)
        except Exception as e:
            logger.error(f"Failed to serialize data: {e}")
            raise

        # 检查数据大小
        max_data_size = self.buffer_size - self.DATA_OFFSET
        if len(serialized) > max_data_size:
            raise ValueError(
                f"Data too large: {len(serialized)} bytes > {max_data_size} bytes"
            )

        with self.lock:
            # 读取并递增计数器
            counter = self._read_counter_unsafe() + 1
            counter = counter & 0xFFFFFFFF  # 32位循环

            # 写入元数据和数据 (顺序很重要：先数据，后长度，最后计数器)
            # 这样可以避免读取端读到不完整的数据
            try:
                self.mmap[self.DATA_OFFSET:self.DATA_OFFSET + len(serialized)] = serialized  # 1. 先写数据
                self.mmap[4:8] = struct.pack('<I', len(serialized))  # 2. 再写长度
                self.mmap.flush()  # 3. 确保数据和长度可见
                self.mmap[0:4] = struct.pack('<I', counter)  # 4. 最后更新计数器
                self.mmap.flush()  # 5. 确保计数器可见

                logger.debug(
                    f"Wrote to buffer: {self.buffer_name}, "
                    f"counter={counter}, size={len(serialized)}"
                )
                return counter
            except Exception as e:
                logger.error(f"Failed to write to buffer: {e}")
                raise

    def read(self, max_retries: int = 3) -> Optional[Dict[str, Any]]:
        """
        读取最新数据（非阻塞，使用 Optimistic Read 模式）

        InputPort使用此方法。
        采用双重计数器验证：读取前后计数器一致才返回数据，
        避免读取到写入过程中的不完整数据。

        Args:
            max_retries: 最大重试次数 (当检测到写入冲突时)

        Returns:
            最新的数据字典，如果无数据返回None
        """
        for _ in range(max_retries):
            # 由于可能存在跨进程读写，我们需要避免长时间持有锁
            # 采用快速读取 + 验证的方式

            # 1. 读取计数器 (读前)
            with self.lock:
                counter_before = self._read_counter_unsafe()
                if counter_before == 0:
                    return None  # 还未有任何写入

                # 2. 读取数据长度
                length = self._read_length_unsafe()
                if length == 0 or length > self.buffer_size - self.DATA_OFFSET:
                    logger.warning(f"Invalid data length: {length}")
                    return None

                # 3. 读取数据
                serialized = bytes(
                    self.mmap[self.DATA_OFFSET:self.DATA_OFFSET + length]
                )

                # 4. 再次读取计数器 (读后)
                counter_after = self._read_counter_unsafe()

            # 5. 验证：两次计数器一致才说明数据完整
            if counter_before == counter_after:
                try:
                    data = msgpack.unpackb(serialized, raw=False)
                    logger.debug(
                        f"Read from buffer: {self.buffer_name}, "
                        f"counter={counter_before}, size={length}"
                    )
                    return data
                except Exception as e:
                    logger.error(f"Failed to deserialize from buffer: {e}")
                    return None
            # 计数器不一致，说明读取期间有写入，重试

        # 重试多次仍然失败
        logger.warning(f"Failed to read consistent data after {max_retries} retries")
        return None

    def has_new_data(self, last_counter: int) -> bool:
        """
        检查是否有新数据可读

        InputPort使用此方法轮询。
        使用模运算差值比较，正确处理32位序列号回绕。

        Args:
            last_counter: 上次读取时的计数器值

        Returns:
            True表示有新数据，False表示无新数据
        """
        with self.lock:
            current_counter = self._read_counter_unsafe()
            # 使用模运算差值处理回绕：
            # 当 current=5, last=3 时，diff=2 (正常情况)
            # 当 current=2, last=0xFFFFFFFE 时，diff=4 (回绕后仍能正确判断)
            diff = (current_counter - last_counter) & 0xFFFFFFFF
            # diff 在 0 到 0x7FFFFFFF 范围内表示有新数据
            # diff 在 0x80000000 到 0xFFFFFFFF 范围内表示 last_counter 反而更新（不应发生）
            return 0 < diff < 0x80000000

    def get_current_sequence(self) -> int:
        """
        获取当前计数器值

        用于InputPort追踪上次读取的序列号。

        Returns:
            当前的32位计数器值
        """
        with self.lock:
            return self._read_counter_unsafe()

    def _read_counter_unsafe(self) -> int:
        """
        读取计数器（非线程安全，须在锁内调用）

        Returns:
            当前的32位无符号整数计数器
        """
        return struct.unpack('<I', bytes(self.mmap[0:4]))[0]

    def _read_length_unsafe(self) -> int:
        """
        读取数据长度（非线程安全，须在锁内调用）

        Returns:
            当前数据的长度（字节数）
        """
        return struct.unpack('<I', bytes(self.mmap[4:8]))[0]

    def reset(self):
        """
        重置缓冲区（清除所有数据和计数器）

        用于测试或恢复初始状态。
        """
        with self.lock:
            self.mmap[:] = b'\x00' * self.buffer_size
            self.mmap.flush()
            logger.info(f"Reset buffer: {self.buffer_name}")

    def close(self):
        """关闭缓冲区并清理资源"""
        if self.mmap:
            try:
                self.mmap.close()
            except Exception as e:
                logger.warning(f"Error closing mmap: {e}")

        if self.fd is not None:
            try:
                os.close(self.fd)
            except Exception as e:
                logger.warning(f"Error closing fd: {e}")

        logger.debug(f"Closed buffer: {self.buffer_name}")

    def __del__(self):
        """析构函数：确保资源被释放"""
        self.close()

    @staticmethod
    def cleanup_all():
        """
        清理所有共享缓冲区文件

        在框架关闭时调用。
        """
        buffer_dir = Path('/tmp/nodeflow_buffers')
        if buffer_dir.exists():
            import shutil
            try:
                shutil.rmtree(buffer_dir)
                logger.info(f"Cleaned up buffer directory: {buffer_dir}")
            except Exception as e:
                logger.error(f"Error cleaning up buffers: {e}")
