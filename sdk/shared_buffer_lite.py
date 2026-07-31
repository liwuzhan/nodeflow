"""
轻量级共享缓冲区 — NodeFlow 节点间 IPC 的唯一通道

通过 mmap 实现跨进程共享内存，支持 latest-value 语义。
每个端口对应一个缓冲区文件，单写者多读者模型。
读者通过轮询序列号获知新数据，无需额外的通知通道。

序列化格式: MsgPack (支持 dict, list, bytes, numpy.ndarray)

缓冲区布局:
  [0-3]   序列号 (uint32, little-endian) — 每次写入递增
  [4-7]   数据长度 (uint32, little-endian) — 0 表示无可用快照
  [8-N]   数据内容 (MsgPack)
"""

import mmap
import msgpack
import struct
import threading
from pathlib import Path
from typing import Optional, Dict, Any, Tuple

try:
    import numpy as np
    HAS_NUMPY = True
except ImportError:
    HAS_NUMPY = False

# ── per-buffer 线程锁（同一进程内多线程写保护）─────────────────────────
_PROCESS_LOCKS: dict[str, threading.RLock] = {}
_LOCKS_GUARD = threading.Lock()


def _get_buffer_lock(buffer_path: Path) -> threading.RLock:
    key = str(buffer_path.resolve())
    with _LOCKS_GUARD:
        return _PROCESS_LOCKS.setdefault(key, threading.RLock())


class SharedBufferLite:
    """单写者多读者共享缓冲区 — 纯 mmap，无 fcntl，无 ZMQ"""

    HEADER_SIZE = 8
    DEFAULT_SIZE = 1024 * 1024

    def __init__(self, buffer_name: str, size: int = DEFAULT_SIZE, create: bool = True):
        self.buffer_name = buffer_name

        from runtime.utils.constants import BUFFERS_DIR
        buffer_dir = Path(BUFFERS_DIR)
        buffer_dir.mkdir(parents=True, exist_ok=True)
        self.buffer_path = buffer_dir / f"{buffer_name}.buf"

        if create:
            with open(self.buffer_path, 'wb') as f:
                f.write(b'\x00' * size)
            self.size = size
        else:
            self.size = self.buffer_path.stat().st_size

        self.file = open(self.buffer_path, 'r+b', buffering=0)
        self.mmap = mmap.mmap(self.file.fileno(), self.size)
        self._lock = _get_buffer_lock(self.buffer_path)

    # ── numpy 序列化辅助 ──────────────────────────────────────────────

    @staticmethod
    def _encode_numpy(obj):
        if HAS_NUMPY:
            if isinstance(obj, np.ndarray):
                return {
                    '__ndarray__': True,
                    'dtype': str(obj.dtype),
                    'shape': tuple(obj.shape),
                    'data': obj.tobytes(),
                }
            elif isinstance(obj, (np.integer, np.floating)):
                return obj.item()
        raise TypeError(f"Object of type {type(obj).__name__} is not serializable")

    @staticmethod
    def _decode_numpy(obj):
        if isinstance(obj, dict) and obj.get('__ndarray__'):
            if not HAS_NUMPY:
                raise ImportError("NumPy is required to decode numpy arrays")
            dtype = np.dtype(obj['dtype'])
            shape = obj['shape']
            data = obj['data']
            return np.frombuffer(data, dtype=dtype).reshape(shape)
        return obj

    # ── 写路径 ───────────────────────────────────────────────────────

    def write(self, data: Dict[str, Any]) -> int:
        serialized = msgpack.packb(data, default=self._encode_numpy, use_bin_type=True)
        data_length = len(serialized)

        if data_length > (self.size - self.HEADER_SIZE):
            raise ValueError(
                f"Data too large: {data_length} bytes (max {self.size - self.HEADER_SIZE})"
            )

        with self._lock:
            current_seq = struct.unpack('<I', self.mmap[0:4])[0]
            new_seq = (current_seq + 1) & 0xFFFFFFFF

            self.mmap[4:8] = struct.pack('<I', 0)
            self.mmap.flush()

            self.mmap[8:8 + data_length] = serialized
            self.mmap[0:4] = struct.pack('<I', new_seq)
            self.mmap[4:8] = struct.pack('<I', data_length)
            self.mmap.flush()

        return new_seq

    # ── 读路径 ───────────────────────────────────────────────────────

    def read_with_sequence(self, _max_retries: int = 5) -> Tuple[int, Optional[Dict[str, Any]]]:
        """原子读取序列号和对应数据快照。

        header（seq + length）通过 fd 直接读取以保证跨进程一致性；
        macOS 上两份 mmap 映射同一文件未必立即可见。
        使用 seqlock 协议：读取前后各取一次序列号，不一致则重试。
        """
        for _ in range(_max_retries):
            with self._lock:
                self.file.seek(0)
                header = self.file.read(8)
                seq_before = struct.unpack('<I', header[0:4])[0]
                length = struct.unpack('<I', header[4:8])[0]

                if length == 0 or length > (self.size - self.HEADER_SIZE):
                    return seq_before, None

                self.file.seek(8)
                serialized = self.file.read(length)

                self.file.seek(0)
                seq_after = struct.unpack('<I', self.file.read(4))[0]

            if seq_before != seq_after:
                continue  # 写入穿插，重试

            try:
                data = msgpack.unpackb(serialized, object_hook=self._decode_numpy, raw=False)
                return seq_before, data
            except Exception:
                return seq_before, None

        return seq_before, None  # 重试耗尽

    def read(self, _max_retries: int = 3) -> Optional[Dict[str, Any]]:
        _, data = self.read_with_sequence(_max_retries=_max_retries)
        return data

    def get_sequence(self) -> int:
        self.file.seek(0)
        return struct.unpack('<I', self.file.read(4))[0]

    # ── 生命周期 ─────────────────────────────────────────────────────

    def close(self):
        if self.mmap:
            try:
                self.mmap.close()
            except Exception:
                pass
        if self.file:
            try:
                self.file.close()
            except Exception:
                pass

    def __del__(self):
        try:
            self.close()
        except Exception:
            pass

    @staticmethod
    def cleanup_all():
        from runtime.utils.constants import BUFFERS_DIR
        buffer_dir = Path(BUFFERS_DIR)
        if buffer_dir.exists():
            for buf_file in buffer_dir.glob("*.buf"):
                try:
                    buf_file.unlink()
                except Exception:
                    pass
