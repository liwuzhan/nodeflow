"""
端口抽象模块 — 纯 SharedBuffer IPC

InputPort / OutputPort 基于 SharedBufferLite（mmap）实现进程间通信。
- OutputPort: 写入 mmap 缓冲区（带 tombstone 协议保证原子性）
- InputPort:  轮询序列号 + 原子读取最新快照
- 无 ZMQ / 无 fcntl 文件锁 / 无网络层

缓冲区命名约定: {node_id}.{port_name}
"""

import os
import time
from pathlib import Path
from typing import Optional, Dict, Any, Type, Union

try:
    from pydantic import BaseModel
    HAS_PYDANTIC = True
except ImportError:
    HAS_PYDANTIC = False
    BaseModel = None  # type: ignore

from sdk.shared_buffer_lite import SharedBufferLite
from runtime.utils.logger import get_logger
from runtime.utils.constants import BUFFERS_DIR

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

    def _setup(self):
        buffer_path = Path(f"{BUFFERS_DIR}/{self.buffer_name}.buf")
        create = not buffer_path.exists()

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
        logger.debug(f"OutputPort '{self.name}' closed")

    def __del__(self):
        try:
            self.close()
        except Exception:
            pass


class InputPort:
    """输入端口 — 轮询序列号 + 原子读取"""

    def __init__(self, name: str, buffer_name: str, source_port: Optional[str] = None):
        """
        Args:
            name: 本地端口名
            buffer_name: 缓冲区名称 (如 'sim_output.rtk_fix')
            source_port: 源端口名（可选，用于日志）
        """
        self.name = name
        self.buffer_name = buffer_name

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

        self._connect()

    def _connect(self):
        for attempt in range(10):
            buffer_path = Path(f"{BUFFERS_DIR}/{self.buffer_name}.buf")
            if buffer_path.exists():
                self.buffer = SharedBufferLite(self.buffer_name, create=False)
                logger.debug(f"InputPort '{self.name}' opened buffer: {self.buffer_name}")
                break
            if attempt < 9:
                logger.debug(f"InputPort '{self.name}' waiting for buffer ({attempt + 1}/10)...")
                time.sleep(0.2)

        if not self.buffer:
            logger.warning(
                f"InputPort '{self.name}': buffer '{self.buffer_name}' not found after 10 attempts. "
                f"Upstream node may not have started yet. Data on this port will be dropped."
            )
            return

        # 首次连接：读取历史序列号和数据（Late-Joiner）
        current_seq, history_data = self.buffer.read_with_sequence()
        self.last_sequence = current_seq
        if history_data is not None:
            self._cached_history = history_data
            logger.info(
                f"InputPort '{self.name}' read history (seq={current_seq})"
            )
        else:
            logger.debug(f"InputPort '{self.name}' synced to seq={current_seq} (no data)")

        logger.info(
            f"InputPort '{self.name}' connected to {self.source_node}.{self.source_port}"
        )

    def recv_latest(self) -> Optional[Dict[str, Any]]:
        """非阻塞：无新数据时返回 None"""
        if not self.buffer:
            return None

        try:
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
                return data

            return None
        except Exception as e:
            logger.error(f"InputPort '{self.name}' read error: {e}")
            return None

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
        return "connected" if self.buffer is not None else "disconnected"

    def close(self):
        if self.buffer:
            try:
                self.buffer.close()
            except Exception as e:
                logger.warning(f"Error closing InputPort buffer '{self.name}': {e}")
        logger.debug(f"InputPort '{self.name}' closed")

    def __del__(self):
        try:
            self.close()
        except Exception:
            pass
