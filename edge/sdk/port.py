"""
端口抽象模块 — 纯 SharedBuffer IPC

InputPort / OutputPort 基于 SharedBufferLite（mmap）实现进程间通信。
- OutputPort: 写入 mmap 缓冲区（带 tombstone 协议保证原子性）；
  打开旧 buffer 发现损坏（header 非法/尺寸不符）时改名留证并重建（D2）
- InputPort:  轮询序列号 + 原子读取最新快照；
  DISCONNECTED→CONNECTED 自愈 + 重同步安全网（seq 回跳/ts 倒退/inode 变化）
- 无 ZMQ / 无 fcntl 文件锁 / 无网络层

缓冲区命名约定: {node_id}.{port_name}
"""

import os
import struct
import time
from pathlib import Path
from typing import Optional, Dict, Any, Type, Union

try:
    from pydantic import BaseModel
    HAS_PYDANTIC = True
except ImportError:
    HAS_PYDANTIC = False
    BaseModel = None  # type: ignore

from edge.sdk.shared_buffer_lite import SharedBufferLite
from edge.runtime.utils.logger import get_logger
from edge.runtime.utils.constants import get_buffers_dir

logger = get_logger(__name__)


class OutputPort:
    """输出端口 — 写入共享缓冲区"""

    def __init__(self, name: str, buffer_name: str, schema: Optional[Type['BaseModel']] = None):
        """
        Args:
            name: 端口名 (如 'rtk_fix')
            buffer_name: 缓冲区名称 (如 'sim_output.rtk_fix')
            schema: Pydantic 模型类（可选），用于数据校验
        """
        self.name = name
        self.buffer_name = buffer_name
        self.schema = schema
        self.buffer: Optional[SharedBufferLite] = None

        self.validation_mode = os.getenv("NODE_SCHEMA_VALIDATION", "off").lower()

        buffer_size_env = os.getenv(f'NODE_OUT_{name}_BUFFER_SIZE')
        self.buffer_size = int(buffer_size_env) if buffer_size_env else 1024 * 1024

        self._setup()

    def _buffer_path(self) -> Path:
        return Path(get_buffers_dir(self.buffer_name)) / f"{self.buffer_name}.buf"

    def _inspect_existing(self, path: Path) -> Optional[str]:
        """检查已存在的 buffer 文件是否可用；返回 None 表示可复用，否则返回损坏原因"""
        try:
            st = path.stat()
        except OSError as e:
            return f"stat_failed: {e}"

        if st.st_size != self.buffer_size:
            return f"size_mismatch: file={st.st_size} configured={self.buffer_size}"

        try:
            with open(path, 'rb', buffering=0) as f:
                header = f.read(SharedBufferLite.HEADER_SIZE)
            if len(header) >= 8:
                length = struct.unpack('<I', header[4:8])[0]
                if length > (st.st_size - SharedBufferLite.HEADER_SIZE):
                    return f"illegal_header: length={length}"
        except OSError as e:
            return f"read_failed: {e}"

        return None

    def _quarantine(self, path: Path, reason: str):
        """损坏 buffer 改名留证（不删除），后续新建同名池（D2）"""
        incarnation = os.getenv('NODEFLOW_INCARNATION', '1')
        dead_path = path.with_name(f"{path.stem}.dead.{incarnation}.buf")
        suffix = 0
        while dead_path.exists():
            suffix += 1
            dead_path = path.with_name(f"{path.stem}.dead.{incarnation}.{suffix}.buf")
        try:
            path.rename(dead_path)
            logger.warning(
                f"OutputPort '{self.name}' quarantined corrupt buffer "
                f"'{path.name}' -> '{dead_path.name}' (reason: {reason})"
            )
        except OSError as e:
            logger.error(f"Failed to quarantine buffer '{path.name}': {e}")

    def _setup(self):
        path = self._buffer_path()
        create = not path.exists()

        if not create:
            problem = self._inspect_existing(path)
            if problem:
                self._quarantine(path, problem)
                create = True

        self.buffer = SharedBufferLite(self.buffer_name, size=self.buffer_size, create=create)
        logger.info(
            f"OutputPort '{self.name}' ready: buffer={self.buffer_name} "
            f"({'created' if create else 'reused'}, size={self.buffer.size // 1024}KB)"
        )

    def get_schema_json(self) -> Optional[Dict[str, Any]]:
        if not self.schema or not HAS_PYDANTIC:
            return None
        try:
            if hasattr(self.schema, 'model_json_schema'):
                return self.schema.model_json_schema()
            elif hasattr(self.schema, 'schema'):
                return self.schema.schema()
        except Exception as e:
            logger.warning(f"Failed to generate schema for port '{self.name}': {e}")
        return None

    def send(self, data: Union[Dict[str, Any], 'BaseModel']):
        if not self.buffer:
            logger.error(f"OutputPort '{self.name}' not ready")
            return

        # ── Schema 校验 ──────────────────────────────────────────
        if self.schema and self.validation_mode != "off" and HAS_PYDANTIC:
            try:
                if isinstance(data, self.schema):
                    data = data.model_dump() if hasattr(data, 'model_dump') else data.dict()
                elif isinstance(data, dict):
                    validated = (
                        self.schema.model_validate(data)
                        if hasattr(self.schema, 'model_validate')
                        else self.schema.parse_obj(data)
                    )
                    data = validated.model_dump() if hasattr(validated, 'model_dump') else validated.dict()
                else:
                    raise TypeError(f"Data must be dict or {self.schema.__name__}, got {type(data)}")
            except Exception as e:
                if self.validation_mode == "strict":
                    raise ValueError(f"Schema validation failed for '{self.name}': {e}") from e
                logger.warning(f"Schema validation failed for '{self.name}': {e}")
                if isinstance(data, dict):
                    pass  # loose mode: send anyway
                elif hasattr(data, 'model_dump'):
                    data = data.model_dump()
                elif hasattr(data, 'dict'):
                    data = data.dict()
                else:
                    return
        elif HAS_PYDANTIC and hasattr(data, 'model_dump'):
            data = data.model_dump()
        elif HAS_PYDANTIC and hasattr(data, 'dict'):
            data = data.dict()

        # ── 写入缓冲区 ───────────────────────────────────────────
        try:
            sequence = self.buffer.write(data)
            logger.debug(f"OutputPort '{self.name}' sent data (seq={sequence})")
        except Exception as e:
            logger.error(f"OutputPort '{self.name}' write error: {e}")
            raise

    def close(self):
        if self.buffer:
            try:
                self.buffer.close()
            except Exception as e:
                logger.warning(f"Error closing OutputPort buffer '{self.name}': {e}")
            self.buffer = None
        logger.debug(f"OutputPort '{self.name}' closed")

    def __del__(self):
        try:
            self.close()
        except Exception:
            pass


class InputPort:
    """输入端口 — 轮询序列号 + 原子读取，含自愈与重同步安全网

    状态机: DISCONNECTED → CONNECTED（buffer 为 None 时 recv_latest 按退避重开）
    重同步触发（安全网而非主路径——默认复用型重启在数据面无痕迹，见 N-1）:
    - seq 大幅回跳（新池从 0 重新计数）
    - write_ts 倒退
    - buffer 文件 inode / 尺寸变化（改名留证重建、外部删除场景）
    """

    REOPEN_BACKOFF_START = 0.2
    REOPEN_BACKOFF_MAX = 2.0
    SEQ_BACKWARD_THRESHOLD = 0x10000

    def __init__(self, name: str, buffer_name: str, source_port: Optional[str] = None,
                 require_new_commit: bool = False):
        """
        Args:
            name: 本地端口名
            buffer_name: 缓冲区名称 (如 'sim_output.rtk_fix')
            source_port: 源端口名（可选，用于日志）
            require_new_commit: anti-replay 语义（2026-09-01 草案 §6.10）——
                打开/重同步时丢弃缓存的历史快照并以其 seq 为基线，
                只返回基线之后的新提交；buffer 换代时同样重建基线
        """
        self.name = name
        self.buffer_name = buffer_name
        self.require_new_commit = require_new_commit

        if source_port is not None:
            self.source_node = buffer_name.rsplit('.', 1)[0] if '.' in buffer_name else buffer_name
            self.source_port = source_port
        else:
            parts = buffer_name.rsplit('.', 1)
            if len(parts) == 2:
                self.source_node, self.source_port = parts
            else:
                self.source_node = buffer_name
                self.source_port = name

        self.buffer: Optional[SharedBufferLite] = None
        self.last_sequence = 0
        self._cached_history: Optional[Dict[str, Any]] = None

        # 自愈/重同步状态
        self.state = "DISCONNECTED"
        self.generation = 0
        self._reopen_backoff = self.REOPEN_BACKOFF_START
        self._reopen_deadline = 0.0
        self._inode: Optional[int] = None
        self._file_size: Optional[int] = None
        self._last_ts: int = 0

        self._connect()

    def _buffer_path(self) -> Path:
        return Path(get_buffers_dir(self.buffer_name)) / f"{self.buffer_name}.buf"

    def _connect(self):
        for attempt in range(10):
            path = self._buffer_path()
            if path.exists():
                if self._open_buffer(sync_history=True):
                    logger.info(
                        f"InputPort '{self.name}' connected to {self.source_node}.{self.source_port}"
                    )
                    return
                # 打开失败（损坏）→ 等退避后重试打开
            if attempt < 9:
                logger.debug(f"InputPort '{self.name}' waiting for buffer ({attempt + 1}/10)...")
                time.sleep(0.2)

        logger.warning(
            f"InputPort '{self.name}': buffer '{self.buffer_name}' not found after 10 attempts. "
            f"Upstream node may not have started yet. Will keep retrying with backoff."
        )

    def _open_buffer(self, sync_history: bool) -> bool:
        """打开（或重开）buffer 并记录 inode/size；成功返回 True"""
        try:
            self.buffer = SharedBufferLite(self.buffer_name, create=False)
        except Exception as e:
            logger.warning(f"InputPort '{self.name}' failed to open buffer: {e}")
            self.buffer = None
            return False

        try:
            st = self._buffer_path().stat()
            self._inode = st.st_ino
            self._file_size = st.st_size
        except OSError:
            self._inode = None
            self._file_size = None

        self.state = "CONNECTED"
        self._reopen_backoff = self.REOPEN_BACKOFF_START

        if sync_history:
            current_seq, history_data = self.buffer.read_with_sequence()
            self.last_sequence = current_seq
            if history_data is not None:
                if self.require_new_commit:
                    # anti-replay：连接/重同步时刻的快照属于"启动前历史"，
                    # 丢弃不回放，以其 seq 为基线等待下一次提交
                    logger.info(
                        f"InputPort '{self.name}' anti-replay: dropped history "
                        f"snapshot (seq={current_seq}), awaiting new commit"
                    )
                else:
                    self._cached_history = history_data
                    logger.info(
                        f"InputPort '{self.name}' read history (seq={current_seq})"
                    )
            else:
                logger.debug(f"InputPort '{self.name}' synced to seq={current_seq} (no data)")
        return True

    def _try_reopen(self):
        """DISCONNECTED 状态下的退避重开（0.2s 起、上限 2s）"""
        now = time.monotonic()
        if now < self._reopen_deadline:
            return
        self._reopen_deadline = now + self._reopen_backoff
        self._reopen_backoff = min(self._reopen_backoff * 2, self.REOPEN_BACKOFF_MAX)

        if self._buffer_path().exists() and self._open_buffer(sync_history=True):
            logger.info(
                f"InputPort '{self.name}' reconnected to {self.source_node}.{self.source_port} "
                f"(generation={self.generation})"
            )

    def _needs_resync(self) -> Optional[str]:
        """检测是否需要重开 mmap；返回触发原因或 None

        注意：inode/size stat 不做节流——重建窗口可能落在任何两次轮询之间，
        安全网必须每次都看（stat 单次 ~1µs，相对既有 get_sequence 的
        seek+read 两次 syscall 成本可忽略，见 N-3）。
        """
        if not self.buffer:
            return None

        try:
            seq, _, ts = self.buffer.get_header()
        except Exception as e:
            return f"header_read_failed: {e}"

        # seq 大幅回跳：新池从 0 重新计数（复用型重启 seq 连续，不触发，N-1）
        backward = (self.last_sequence - seq) & 0xFFFFFFFF
        if 0 < backward < self.SEQ_BACKWARD_THRESHOLD:
            return f"seq_backward: {self.last_sequence} -> {seq}"

        # write_ts 倒退（同 boot 单调时钟下不应出现；出现即换池）
        if ts != 0 and self._last_ts != 0 and ts < self._last_ts:
            return f"ts_backward: {self._last_ts} -> {ts}"

        # inode / 尺寸变化（改名留证重建、外部删除场景）
        try:
            st = self._buffer_path().stat()
            if self._inode is not None and st.st_ino != self._inode:
                return f"inode_changed: {self._inode} -> {st.st_ino}"
            if self._file_size is not None and st.st_size != self._file_size:
                return f"size_changed: {self._file_size} -> {st.st_size}"
        except OSError:
            return "stat_failed"

        return None

    def _resync(self, reason: str):
        """重开 mmap、重置序列号基准、generation 递增"""
        self.generation += 1
        logger.info(
            f"InputPort '{self.name}' resync (generation={self.generation}): {reason}"
        )
        if self.buffer:
            try:
                self.buffer.close()
            except Exception:
                pass
            self.buffer = None

        self._cached_history = None  # 旧世代历史不重放
        self.state = "DISCONNECTED"
        self._last_ts = 0
        self._reopen_deadline = 0.0

        if not self._open_buffer(sync_history=True):
            # 文件已不存在等场景 → 回到 DISCONNECTED 退避重开
            logger.warning(f"InputPort '{self.name}' resync open failed, entering reconnect loop")

    def recv_latest(self) -> Optional[Dict[str, Any]]:
        """非阻塞：无新数据时返回 None"""
        if not self.buffer:
            self._try_reopen()
            if not self.buffer:
                return None

        try:
            reason = self._needs_resync()
            if reason:
                self._resync(reason)
                if not self.buffer:
                    return None

            # 优先返回首次连接的缓存历史
            if self._cached_history is not None:
                data = self._cached_history
                self._cached_history = None
                return data

            # 检查序列号（无锁快读）
            current_seq = self.buffer.get_sequence()
            diff = (current_seq - self.last_sequence) & 0xFFFFFFFF
            if not (0 < diff < 0x80000000):
                return None

            # 序列号已更新 → 原子读取数据
            seq, data = self.buffer.read_with_sequence()
            diff = (seq - self.last_sequence) & 0xFFFFFFFF
            if 0 < diff < 0x80000000 and data is not None:
                self.last_sequence = seq
                _, _, ts = self.buffer.get_header()
                if ts:
                    self._last_ts = ts
                return data

            return None
        except Exception as e:
            logger.error(f"InputPort '{self.name}' read error: {e}")
            # mmap 可能已失效（文件被删/截断）→ 触发重开而非永久静默
            self._resync(f"read_error: {e}")
            return None

    def last_write_age_ms(self) -> Optional[float]:
        """上游最后一次写入距现在的毫秒数；未连接或从未写入返回 None"""
        if not self.buffer:
            return None
        return self.buffer.get_write_age_ms()

    def recv_latest_blocking(self, timeout: Optional[float] = None) -> Optional[Dict[str, Any]]:
        """阻塞等待，直到有新数据或超时"""
        start = time.time()
        while True:
            data = self.recv_latest()
            if data is not None:
                return data
            if timeout is not None and (time.time() - start) >= timeout:
                logger.debug(f"InputPort '{self.name}' blocking recv timeout ({timeout}s)")
                return None
            time.sleep(0.001)

    def is_connected(self) -> bool:
        return self.buffer is not None

    def get_connection_state(self) -> str:
        return self.state.lower()

    def get_stats(self) -> Dict[str, Any]:
        """端口观测状态（health v2 / status 消费）"""
        return {
            "state": self.state.lower(),
            "source_write_age_ms": (
                round(self.buffer.get_write_age_ms(), 1)
                if self.buffer else None
            ),
            "generation": self.generation,
            "anti_replay": self.require_new_commit,
        }

    def close(self):
        if self.buffer:
            try:
                self.buffer.close()
            except Exception as e:
                logger.warning(f"Error closing InputPort buffer '{self.name}': {e}")
            self.buffer = None
        self.state = "DISCONNECTED"
        logger.debug(f"InputPort '{self.name}' closed")

    def __del__(self):
        try:
            self.close()
        except Exception:
            pass
