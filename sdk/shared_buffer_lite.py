"""
轻量级共享缓冲区（用于混合ZMQ方案）

这是一个简化版的SharedBuffer，只用于持久化最新值。
与完整版SharedBuffer的区别：
- 只存储一个值（最新值）
- 配合ZMQ使用，不单独作为IPC机制
- 文件锁保护跨线程、跨进程快照完整性

序列化格式: MsgPack (支持 dict, list, bytes, numpy.ndarray)
"""

import mmap
import msgpack
import struct
import threading
from contextlib import contextmanager
from pathlib import Path
from typing import Optional, Dict, Any, Tuple

try:
    import fcntl
except ImportError:  # pragma: no cover - edge deployments use Linux
    fcntl = None

try:
    import numpy as np
    HAS_NUMPY = True
except ImportError:
    HAS_NUMPY = False

# 缓冲区布局:
# [0-3]   序列号 (uint32)
# [4-7]   数据长度 (uint32)
# [8-N]   数据内容 (MsgPack)

_PROCESS_LOCKS: dict[str, threading.RLock] = {}
_PROCESS_LOCKS_GUARD = threading.Lock()


def _get_process_lock(buffer_path: Path) -> threading.RLock:
    key = str(buffer_path.resolve())
    with _PROCESS_LOCKS_GUARD:
        return _PROCESS_LOCKS.setdefault(key, threading.RLock())


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

        # 缓冲区文件路径
        from runtime.utils.constants import BUFFERS_DIR
        buffer_dir = Path(BUFFERS_DIR)
        buffer_dir.mkdir(parents=True, exist_ok=True)
        self.buffer_path = buffer_dir / f"{buffer_name}.buf"

        if create:
            # 创建新文件
            with open(self.buffer_path, 'wb') as f:
                f.write(b'\x00' * size)
            self.size = size
        else:
            # 打开现有文件，自动检测其实际大小
            self.size = self.buffer_path.stat().st_size

        # 打开mmap
        self.file = open(self.buffer_path, 'r+b')
        self.mmap = mmap.mmap(self.file.fileno(), self.size)
        self._process_lock = _get_process_lock(self.buffer_path)

    @contextmanager
    def _locked(self, exclusive: bool):
        """Serialize access across threads and processes without changing the file format."""
        with self._process_lock:
            if fcntl is not None:
                mode = fcntl.LOCK_EX if exclusive else fcntl.LOCK_SH
                fcntl.flock(self.file.fileno(), mode)
            try:
                yield
            finally:
                if fcntl is not None:
                    fcntl.flock(self.file.fileno(), fcntl.LOCK_UN)

    @staticmethod
    def _encode_numpy(obj):
        """MsgPack编码器：支持numpy数据类型"""
        if HAS_NUMPY:
            if isinstance(obj, np.ndarray):
                return {
                    '__ndarray__': True,
                    'dtype': str(obj.dtype),
                    'shape': tuple(obj.shape),
                    'data': obj.tobytes()
                }
            elif isinstance(obj, (np.integer, np.floating)):
                return obj.item()  # 转换为Python原生类型
        raise TypeError(f"Object of type {type(obj).__name__} is not JSON serializable")

    @staticmethod
    def _decode_numpy(obj):
        """MsgPack解码器：还原numpy数据类型"""
        if isinstance(obj, dict) and obj.get('__ndarray__'):
            if not HAS_NUMPY:
                raise ImportError("NumPy is required to decode numpy arrays")
            dtype = np.dtype(obj['dtype'])
            shape = obj['shape']
            data = obj['data']
            return np.frombuffer(data, dtype=dtype).reshape(shape)
        return obj

    def write(self, data: Dict[str, Any]) -> int:
        """
        写入数据（覆盖式）

        Args:
            data: 要写入的数据字典（支持dict, list, bytes, numpy.ndarray）

        Returns:
            新的序列号
        """
        # 序列化数据为MsgPack
        try:
            serialized = msgpack.packb(data, default=self._encode_numpy, use_bin_type=True)
        except Exception as e:
            raise ValueError(f"Failed to serialize data: {e}")

        data_length = len(serialized)

        if data_length > (self.size - self.HEADER_SIZE):
            raise ValueError(f"Data too large: {data_length} bytes (max {self.size - self.HEADER_SIZE})")

        with self._locked(exclusive=True):
            current_seq = struct.unpack('<I', self.mmap[0:4])[0]
            new_seq = (current_seq + 1) & 0xFFFFFFFF

            # 长度为 0 表示当前没有可提交快照，写进程异常退出时读者不会解析半写数据。
            self.mmap[4:8] = struct.pack('<I', 0)
            self.mmap.flush()
            self.mmap[8:8+data_length] = serialized
            self.mmap[0:4] = struct.pack('<I', new_seq)
            self.mmap[4:8] = struct.pack('<I', data_length)
            self.mmap.flush()

        return new_seq

    def read_with_sequence(self, max_retries: int = 3) -> Tuple[int, Optional[Dict[str, Any]]]:
        """
        原子读取序列号和对应数据。

        max_retries 为兼容旧 API 保留；文件锁已经保证快照完整性。
        """
        del max_retries
        with self._locked(exclusive=False):
            sequence = struct.unpack('<I', self.mmap[0:4])[0]
            length = struct.unpack('<I', self.mmap[4:8])[0]
            if length == 0 or length > (self.size - self.HEADER_SIZE):
                return sequence, None
            serialized = bytes(self.mmap[8:8+length])

        try:
            data = msgpack.unpackb(serialized, object_hook=self._decode_numpy, raw=False)
            return sequence, data
        except Exception:
            return sequence, None

    def read(self, max_retries: int = 3) -> Optional[Dict[str, Any]]:
        """读取一个完整的最新值快照。"""
        _, data = self.read_with_sequence(max_retries=max_retries)
        return data

    def get_sequence(self) -> int:
        """获取当前序列号"""
        with self._locked(exclusive=False):
            return struct.unpack('<I', self.mmap[0:4])[0]

    def close(self):
        """关闭缓冲区"""
        if self.mmap:
            try:
                self.mmap.close()
            except Exception:
                pass  # Already closed
        if self.file:
            try:
                self.file.close()
            except Exception:
                pass  # Already closed

    def __del__(self):
        """析构函数"""
        try:
            self.close()
        except:
            pass

    @staticmethod
    def cleanup_all():
        """清理所有缓冲区文件"""
        from runtime.utils.constants import BUFFERS_DIR
        buffer_dir = Path(BUFFERS_DIR)
        if buffer_dir.exists():
            for buf_file in buffer_dir.glob("*.buf"):
                try:
                    buf_file.unlink()
                except:
                    pass
