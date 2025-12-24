"""
端口抽象模块（混合方案：Shared Buffer + ZeroMQ）

提供InputPort和OutputPort类，结合共享内存和ZeroMQ实现高效可靠的进程间通信。
- OutputPort: 写入Shared Buffer + 发送ZMQ通知
- InputPort: 监听ZMQ通知 + 从Shared Buffer读取
- 解决Slow Joiner问题：late subscribers可以从buffer读取历史数据
"""

import time
import zmq
from typing import Optional, Dict, Any
from pathlib import Path

# 导入共享模块
import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from sdk.shared_buffer_lite import SharedBufferLite
from runtime.utils.logger import get_logger

logger = get_logger(__name__)

# 全局ZMQ context
_zmq_context = None

def get_zmq_context():
    """获取全局ZMQ context (线程安全)"""
    global _zmq_context
    if _zmq_context is None:
        _zmq_context = zmq.Context()
    return _zmq_context


class OutputPort:
    """
    输出端口（混合方案）

    职责：
    - 维护一个Shared Buffer存储最新值
    - 创建ZMQ PUB socket发送更新通知
    - send()时：先写buffer，再发ZMQ通知

    优势：
    - 数据持久在buffer，late joiners可以读取
    - ZMQ提供实时通知，减少轮询
    """

    def __init__(self, name: str, zmq_address: str):
        """
        初始化输出端口

        参数：
        - name: 端口名 (如 'rtk_fix')
        - zmq_address: ZMQ地址 (如 'ipc:///tmp/nodeflow/sim_output.rtk_fix')
                      通常由Runtime通过环境变量传入
        """
        import os

        self.name = name
        self.zmq_address = zmq_address
        self.socket: Optional[zmq.Socket] = None
        self.buffer: Optional[SharedBufferLite] = None

        # 从ZMQ地址提取buffer名称
        # ipc:///tmp/nodeflow/sim_output.rtk_fix -> sim_output.rtk_fix
        self.buffer_name = zmq_address.split('/')[-1]

        # 从环境变量读取buffer配置
        buffer_size_env = os.getenv(f'NODE_OUT_{name}_BUFFER_SIZE')
        self.buffer_size = int(buffer_size_env) if buffer_size_env else 1024 * 1024  # 默认1MB

        conflate_env = os.getenv(f'NODE_OUT_{name}_CONFLATE', 'true')
        self.conflate = conflate_env.lower() == 'true'

        self._setup()

    def _setup(self):
        """
        设置Buffer和ZMQ socket
        """
        try:
            # 1. 创建Shared Buffer（如果已存在则重用，避免invalidate现有的mmap）
            buffer_path = Path(f"/tmp/nodeflow/buffers/{self.buffer_name}.buf")
            buffer_exists = buffer_path.exists()

            if buffer_exists:
                # 重用现有buffer（重启场景）
                self.buffer = SharedBufferLite(self.buffer_name, size=self.buffer_size, create=False)
                logger.debug(
                    f"OutputPort '{self.name}' reusing existing buffer: {self.buffer_name} "
                    f"(size={self.buffer.size//1024}KB)"
                )
            else:
                # 创建新buffer
                self.buffer = SharedBufferLite(self.buffer_name, size=self.buffer_size, create=True)
                logger.debug(
                    f"OutputPort '{self.name}' created buffer: {self.buffer_name} "
                    f"(size={self.buffer_size//1024}KB, conflate={self.conflate})"
                )

            # 2. 创建ZMQ PUB socket
            context = get_zmq_context()
            self.socket = context.socket(zmq.PUB)

            # 设置高水位标记：通知消息很小，可以多缓存一些
            self.socket.setsockopt(zmq.SNDHWM, 100)

            # Bind到指定地址
            self.socket.bind(self.zmq_address)

            logger.info(
                f"OutputPort '{self.name}' ready: buffer={self.buffer_name} "
                f"({self.buffer_size//1024}KB), zmq={self.zmq_address}"
            )

            # 给订阅者一点时间建立连接
            time.sleep(0.05)

        except Exception as e:
            logger.error(f"OutputPort '{self.name}' setup failed: {e}")
            raise

    def send(self, data: Dict[str, Any]):
        """
        发送数据（混合方案）

        步骤：
        1. 写入Shared Buffer（持久化）
        2. 发送ZMQ通知（实时通知）

        参数：
        - data: 要发送的数据字典
        """
        if not self.buffer or not self.socket:
            logger.error(f"OutputPort '{self.name}' not ready")
            return

        try:
            # 1. 写入Shared Buffer
            sequence = self.buffer.write(data)

            # 2. 发送ZMQ通知（只发送序列号，节省带宽）
            notification = f"{sequence}".encode('utf-8')
            self.socket.send(notification, zmq.NOBLOCK)

            logger.debug(
                f"OutputPort '{self.name}' sent data (seq={sequence})"
            )

        except zmq.Again:
            # ZMQ缓冲区满，但数据已写入buffer，不影响正确性
            logger.debug(f"OutputPort '{self.name}' ZMQ buffer full, but data persisted in buffer")

        except Exception as e:
            logger.error(f"OutputPort '{self.name}' send error: {e}")
            raise

    def close(self):
        """
        关闭端口

        释放ZMQ socket和Shared Buffer资源。
        """
        if self.socket:
            try:
                self.socket.close()
            except Exception as e:
                logger.warning(f"Error closing OutputPort socket '{self.name}': {e}")

        if self.buffer:
            try:
                self.buffer.close()
            except Exception as e:
                logger.warning(f"Error closing OutputPort buffer '{self.name}': {e}")

        logger.debug(f"OutputPort '{self.name}' closed")

    def __del__(self):
        """析构函数：尝试清理资源"""
        try:
            self.close()
        except:
            pass


class InputPort:
    """
    输入端口（混合方案）

    职责：
    - 打开源端口的Shared Buffer
    - 连接到源端口的ZMQ PUB socket
    - recv_latest()时：先检查ZMQ通知，再从Buffer读取

    优势：
    - Late joiner可以从buffer读取历史数据
    - 收到ZMQ通知时才读取，减少无效轮询
    """

    def __init__(self, name: str, zmq_address_or_source: str, source_port: Optional[str] = None):
        """
        初始化输入端口

        两种用法：
        1. InputPort(name, zmq_address)
           - zmq_address: 完整ZMQ地址 (如 'ipc:///tmp/nodeflow/sim_output.rtk_fix')

        2. InputPort(name, source_node, source_port)
           - source_node: 源节点ID (如 'sim_output')
           - source_port: 源端口名 (如 'rtk_fix')
           - ZMQ地址自动生成：ipc:///tmp/nodeflow/source_node.source_port

        参数：
        - name: 本地端口名
        - zmq_address_or_source: ZMQ地址 或 源节点ID
        - source_port: 源端口名（仅在第二种用法时需要）
        """
        self.name = name

        # 根据参数判断使用哪种初始化方式
        if source_port is not None:
            # 方式2：传入了source_node和source_port
            source_node = zmq_address_or_source
            self.zmq_address = f"ipc:///tmp/nodeflow/{source_node}.{source_port}"
            self.source_node = source_node
            self.source_port = source_port
        else:
            # 方式1：直接传入zmq_address
            self.zmq_address = zmq_address_or_source
            # 尝试从地址解析source_node和source_port
            # 地址格式: ipc:///tmp/nodeflow/source_node.source_port
            address_part = self.zmq_address.split('/')[-1]  # 得到 "source_node.source_port"
            parts = address_part.rsplit('.', 1)  # 按最后一个.分割
            if len(parts) == 2:
                self.source_node, self.source_port = parts
            else:
                self.source_node = None
                self.source_port = None

        # 从ZMQ地址提取buffer名称
        self.buffer_name = self.zmq_address.split('/')[-1]

        self.socket: Optional[zmq.Socket] = None
        self.buffer: Optional[SharedBufferLite] = None

        # 序列号追踪（用于检测新数据）
        self.last_sequence = 0

        # 缓存的历史数据（首次连接时读取）
        self._cached_history: Optional[Dict[str, Any]] = None

        self._connect()

    def _connect(self):
        """
        连接到源端口

        步骤：
        1. 打开Shared Buffer（等待buffer文件出现）
        2. 连接到ZMQ socket
        """
        try:
            # 1. 等待并打开Shared Buffer
            for attempt in range(10):
                buffer_path = Path(f"/tmp/nodeflow/buffers/{self.buffer_name}.buf")
                if buffer_path.exists():
                    self.buffer = SharedBufferLite(self.buffer_name, create=False)
                    logger.debug(f"InputPort '{self.name}' opened buffer: {self.buffer_name}")
                    break

                if attempt < 9:
                    logger.debug(f"InputPort '{self.name}' waiting for buffer ({attempt+1}/10)...")
                    time.sleep(0.2)

            if not self.buffer:
                logger.warning(
                    f"InputPort '{self.name}' buffer not found after 10 attempts: {self.buffer_name}"
                )
                # 继续尝试连接ZMQ，可能buffer还未创建

            # 2. 连接到ZMQ socket
            context = get_zmq_context()
            self.socket = context.socket(zmq.SUB)

            # 订阅所有消息
            self.socket.setsockopt(zmq.SUBSCRIBE, b'')

            # 设置高水位标记
            self.socket.setsockopt(zmq.RCVHWM, 100)

            # Connect到源地址
            self.socket.connect(self.zmq_address)

            logger.info(
                f"InputPort '{self.name}' connected to "
                f"{self.source_node}.{self.source_port} "
                f"(buffer={self.buffer_name}, zmq={self.zmq_address})"
            )

            # 给socket时间建立连接
            time.sleep(0.1)

            # 首次连接：从buffer读取历史数据（解决Late-Joiner问题）
            if self.buffer:
                current_seq = self.buffer.get_sequence()
                if current_seq > 0:
                    # 有历史数据，读取并缓存
                    history_data = self.buffer.read()
                    if history_data is not None:
                        self._cached_history = history_data
                        self.last_sequence = current_seq
                        logger.info(
                            f"InputPort '{self.name}' read history on first connection: "
                            f"seq={current_seq} (Late-Joiner: data available)"
                        )
                    else:
                        # Buffer中没有有效数据
                        self.last_sequence = current_seq
                        logger.debug(f"InputPort '{self.name}' synced to sequence={current_seq} (no data in buffer)")
                else:
                    # 还没有数据
                    logger.debug(f"InputPort '{self.name}' waiting for first data (seq={current_seq})")

        except Exception as e:
            logger.error(f"InputPort '{self.name}' connection error: {e}")
            raise

    def recv_latest(self) -> Optional[Dict[str, Any]]:
        """
        接收最新数据（非阻塞）

        策略（混合方案）：
        1. 如果有缓存的历史数据，先返回（解决Late-Joiner）
        2. 检查ZMQ是否有新通知（非阻塞）
        3. 如果有通知，从Shared Buffer读取最新数据
        4. 如果无通知但buffer有新数据（序列号增加），也读取

        返回：
        - 最新的数据字典，如果无新数据返回None
        """
        if not self.buffer:
            logger.warning(f"InputPort '{self.name}' buffer not available")
            return None

        if not self.socket:
            logger.warning(f"InputPort '{self.name}' socket not connected")
            return None

        try:
            # 0. 如果有缓存的历史数据，先返回（首次调用时）
            if self._cached_history is not None:
                cached_data = self._cached_history
                self._cached_history = None  # 只返回一次
                logger.debug(
                    f"InputPort '{self.name}' returned cached history data (seq={self.last_sequence})"
                )
                return cached_data

            # 1. 检查ZMQ通知（非阻塞）
            has_notification = False
            try:
                notification = self.socket.recv(zmq.NOBLOCK)
                has_notification = True
            except zmq.Again:
                pass

            # 2. 检查buffer序列号是否增加
            current_seq = self.buffer.get_sequence()
            has_new_data = current_seq > self.last_sequence

            # 3. 如果有新数据，从buffer读取
            if has_notification or has_new_data:
                data = self.buffer.read()
                if data is not None:
                    self.last_sequence = current_seq
                    logger.debug(
                        f"InputPort '{self.name}' received data (seq={current_seq})"
                    )
                    return data

            return None

        except Exception as e:
            logger.error(f"InputPort '{self.name}' read error: {e}")
            return None

    def recv_latest_blocking(self, timeout: Optional[float] = None) -> Optional[Dict[str, Any]]:
        """
        阻塞接收最新数据

        参数：
        - timeout: 超时时间（秒），None表示无限等待

        返回：
        - 最新的数据字典，如果超时返回None
        """
        start_time = time.time()

        while True:
            # 尝试接收数据
            data = self.recv_latest()
            if data is not None:
                return data

            # 检查超时
            if timeout is not None:
                elapsed = time.time() - start_time
                if elapsed >= timeout:
                    logger.debug(
                        f"InputPort '{self.name}' recv_latest_blocking timeout after {timeout}s"
                    )
                    return None

            # 短暂睡眠后重试
            time.sleep(0.01)

    def close(self):
        """
        关闭端口

        释放ZMQ socket和Shared Buffer资源。
        """
        if self.socket:
            try:
                self.socket.close()
            except Exception as e:
                logger.warning(f"Error closing InputPort socket '{self.name}': {e}")

        if self.buffer:
            try:
                self.buffer.close()
            except Exception as e:
                logger.warning(f"Error closing InputPort buffer '{self.name}': {e}")

        logger.debug(f"InputPort '{self.name}' closed")

    def __del__(self):
        """析构函数：尝试清理资源"""
        try:
            self.close()
        except:
            pass
