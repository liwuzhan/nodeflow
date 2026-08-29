"""
轻量级共享缓冲区 — NodeFlow 节点间 IPC 的唯一通道

通过 mmap 实现跨进程共享内存，支持 latest-value 语义。
每个端口对应一个缓冲区文件，单写者多读者模型。
读者通过轮询序列号获知新数据，无需额外的通知通道。

序列化格式: MsgPack (支持 dict, list, bytes, numpy.ndarray)

缓冲区布局 (header v2, W2-1):
  [0-3]   序列号 (uint32, little-endian) — 每次写入递增
  [4-7]   数据长度 (uint32, little-endian) — 0 表示无可用快照
  [8-15]  写入时刻 write_ts_ns (uint64, little-endian) — CLOCK_MONOTONIC
          框架观测的写入时刻，不依赖节点自觉；同机跨进程可比
  [16-N]  数据内容 (MsgPack)

写序（tombstone 协议）: length=0 → payload → ts → seq → length
版本防护: NODEFLOW_IPC_VERSION 环境握手（launcher 注入，SDK 断言），
header 布局变更不经首字节协商（首字节与 seq 语义冲突）。
"""

import mmap
import msgpack
import struct
import threading
import time
from pathlib import Path
from typing import Optional, Dict, Any, Tuple

try:
    import numpy as np
    HAS_NUMPY = True
except ImportError:
    HAS_NUMPY = False

# 本模块实现的 header 布局版本（W2-1 = 2；[seq:4][length:4][write_ts_ns:8]）
IPC_VERSION = 2

# ── per-buffer 线程锁（同一进程内多线程写保护）─────────────────────────
_PROCESS_LOCKS: dict[str, threading.RLock] = {}
_LOCKS_GUARD = threading.Lock()


def _get_buffer_lock(buffer_path: Path) -> threading.RLock:
    key = str(buffer_path.resolve())
    with _LOCKS_GUARD:
        return _PROCESS_LOCKS.setdefault(key, threading.RLock())


def monotonic_ns() -> int:
    """CLOCK_MONOTONIC 纳秒（boot 基准，同机跨进程可比）"""
    return time.monotonic_ns()


class SharedBufferLite:
    """单写者多读者共享缓冲区 — 纯 mmap，无 fcntl，无 ZMQ"""

    HEADER_SIZE = 16
    DEFAULT_SIZE = 1024 * 1024

    def __init__(self, buffer_name: str, size: int = DEFAULT_SIZE, create: bool = True):
        self.buffer_name = buffer_name

        from edge.runtime.utils.constants import get_buffers_dir
        buffer_dir = Path(get_buffers_dir(buffer_name))
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

            self.mmap[self.HEADER_SIZE:self.HEADER_SIZE + data_length] = serialized
            # 写序: payload → ts → seq → length（length 最后落定即提交）
            self.mmap[8:16] = struct.pack('<Q', monotonic_ns())
            self.mmap[0:4] = struct.pack('<I', new_seq)
            self.mmap[4:8] = struct.pack('<I', data_length)
            self.mmap.flush()

        return new_seq

    # ── 读路径 ───────────────────────────────────────────────────────

    def read_with_sequence(self, _max_retries: int = 5) -> Tuple[int, Optional[Dict[str, Any]]]:
        """原子读取序列号和对应数据快照。

        header（seq + length + ts 共 16 字节）通过 fd 直接读取以保证跨进程一致性。
        读取前后比较完整 16 字节 header——仅比较 seq 不够：
        写端顺序为 length=0 → data → ts → seq → length，data 已更新但 seq 未变时
        seq 检查会漏过，必须连 length/ts 一起校验。
        """
        for _ in range(_max_retries):
            with self._lock:
                self.file.seek(0)
                header_before = self.file.read(self.HEADER_SIZE)
                seq_before = struct.unpack('<I', header_before[0:4])[0]
                length = struct.unpack('<I', header_before[4:8])[0]

                if length == 0 or length > (self.size - self.HEADER_SIZE):
                    return seq_before, None

                self.file.seek(self.HEADER_SIZE)
                serialized = self.file.read(length)

                self.file.seek(0)
                header_after = self.file.read(self.HEADER_SIZE)

            if header_before != header_after:
                continue  # header 发生变化（写入穿插），重试

            try:
                data = msgpack.unpackb(serialized, object_hook=self._decode_numpy, raw=False)
                return seq_before, data
            except Exception:
                return seq_before, None

        return 0, None  # 重试耗尽

    def read(self, _max_retries: int = 3) -> Optional[Dict[str, Any]]:
        _, data = self.read_with_sequence(_max_retries=_max_retries)
        return data

    def get_sequence(self) -> int:
        self.file.seek(0)
        return struct.unpack('<I', self.file.read(4))[0]

    def get_header(self) -> Tuple[int, int, int]:
        """读取完整 header: (seq, length, write_ts_ns)"""
        with self._lock:
            self.file.seek(0)
            header = self.file.read(self.HEADER_SIZE)
        seq = struct.unpack('<I', header[0:4])[0]
        length = struct.unpack('<I', header[4:8])[0]
        ts = struct.unpack('<Q', header[8:16])[0]
        return seq, length, ts

    def get_write_age_ms(self) -> Optional[float]:
        """距最后一次写入的毫秒数；从未写入（ts=0）返回 None"""
        _, _, ts = self.get_header()
        if ts == 0:
            return None
        return (monotonic_ns() - ts) / 1e6

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
        from edge.runtime.utils.constants import get_buffers_dir
        buffer_dir = Path(get_buffers_dir())
        if buffer_dir.exists():
            for buf_file in buffer_dir.glob("*.buf"):
                try:
                    buf_file.unlink()
                except Exception:
                    pass
