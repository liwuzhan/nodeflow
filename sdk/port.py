"""
端口抽象模块
提供InputPort和OutputPort类，封装Socket连接和数据收发
"""

import os
import socket
import time
from typing import Optional, Dict, Any

# 导入共享模块
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from runtime.ipc.protocol import MessageProtocol
from sdk.latest_value_reader import LatestValueReader
from runtime.utils.logger import get_logger

logger = get_logger(__name__)


class OutputPort:
    """
    输出端口（作为Socket服务端）

    职责：
    - 创建Unix Domain Socket服务端
    - 监听客户端连接
    - 发送数据
    """

    def __init__(self, name: str, socket_path: str):
        """
        初始化输出端口

        参数：
        - name: 端口名
        - socket_path: Socket文件路径
        """
        self.name = name
        self.socket_path = socket_path
        self.server_sock: Optional[socket.socket] = None
        self.client_sock: Optional[socket.socket] = None
        self._setup_server()

    def _setup_server(self):
        """创建Socket服务端"""
        try:
            # 清理旧socket文件
            if os.path.exists(self.socket_path):
                os.unlink(self.socket_path)

            # 创建Unix Domain Socket服务端
            self.server_sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            self.server_sock.bind(self.socket_path)
            self.server_sock.listen(1)
            self.server_sock.setblocking(False)  # 非阻塞模式

            logger.debug(f"OutputPort '{self.name}' listening on {self.socket_path}")

        except Exception as e:
            logger.error(f"Failed to setup OutputPort '{self.name}': {e}")
            raise

    def send(self, data: Dict[str, Any]):
        """
        发送数据

        策略：
        - 如果没有客户端连接，尝试接受连接（非阻塞）
        - 如果有客户端连接，发送数据
        - 发送失败时断开连接（等待重连）

        参数：
        - data: 要发送的数据字典
        """
        # 尝试接受新连接
        if self.client_sock is None:
            try:
                self.client_sock, _ = self.server_sock.accept()
                self.client_sock.setblocking(False)
                logger.debug(f"OutputPort '{self.name}' accepted client connection")
            except BlockingIOError:
                # 无客户端连接，忽略数据
                return

        # 发送数据
        try:
            msg = MessageProtocol.encode(data)
            self.client_sock.sendall(msg)
            logger.debug(f"OutputPort '{self.name}' sent message")
        except (BrokenPipeError, ConnectionResetError):
            # 客户端断开连接
            logger.debug(f"OutputPort '{self.name}' client disconnected")
            if self.client_sock:
                self.client_sock.close()
                self.client_sock = None
        except Exception as e:
            logger.warning(f"OutputPort '{self.name}' send error: {e}")
            if self.client_sock:
                self.client_sock.close()
                self.client_sock = None

    def close(self):
        """关闭端口"""
        if self.client_sock:
            self.client_sock.close()
            self.client_sock = None

        if self.server_sock:
            self.server_sock.close()
            self.server_sock = None

        # 清理Socket文件
        if os.path.exists(self.socket_path):
            try:
                os.unlink(self.socket_path)
            except:
                pass

        logger.debug(f"OutputPort '{self.name}' closed")


class InputPort:
    """
    输入端口（作为Socket客户端）

    职责：
    - 连接到输出端口的Socket服务端
    - 接收并应用最新值语义
    """

    def __init__(self, name: str, socket_path: str):
        """
        初始化输入端口

        参数：
        - name: 端口名
        - socket_path: Socket文件路径
        """
        self.name = name
        self.socket_path = socket_path
        self.sock: Optional[socket.socket] = None
        self.reader: Optional[LatestValueReader] = None
        self._connect()

    def _connect(self, max_retries: int = 30, retry_interval: float = 1.0):
        """
        连接到输出端口的Socket服务端

        参数：
        - max_retries: 最大重试次数
        - retry_interval: 重试间隔（秒）
        """
        for i in range(max_retries):
            try:
                self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
                self.sock.connect(self.socket_path)
                self.sock.setblocking(False)  # 非阻塞模式

                # 创建最新值读取器
                self.reader = LatestValueReader(self.sock)

                logger.debug(f"InputPort '{self.name}' connected to {self.socket_path}")
                return

            except (FileNotFoundError, ConnectionRefusedError):
                if self.sock:
                    self.sock.close()
                    self.sock = None

                if i < max_retries - 1:
                    logger.debug(f"InputPort '{self.name}' connection attempt {i+1} failed, retrying...")
                    time.sleep(retry_interval)
                else:
                    raise ConnectionError(
                        f"Failed to connect InputPort '{self.name}' to {self.socket_path} "
                        f"after {max_retries} attempts"
                    )

            except Exception as e:
                if self.sock:
                    self.sock.close()
                    self.sock = None
                raise ConnectionError(f"Failed to connect InputPort '{self.name}': {e}")

    def recv_latest(self) -> Optional[Dict[str, Any]]:
        """
        接收最新值（非阻塞）

        实现最新值语义：
        - 循环读取socket缓冲区
        - 丢弃所有旧消息
        - 只返回最后一条消息

        返回：
        - 最新的消息字典，如果无数据返回None
        """
        if not self.reader:
            return None

        return self.reader.read_latest()

    def recv_latest_blocking(self, timeout: Optional[float] = None) -> Optional[Dict[str, Any]]:
        """
        阻塞接收最新值

        等待直到有数据可读，然后应用最新值语义

        参数：
        - timeout: 超时时间（秒），None表示无限等待

        返回：
        - 最新的消息字典，如果超时返回None
        """
        if not self.reader:
            return None

        return self.reader.read_latest_blocking(timeout)

    def close(self):
        """关闭端口"""
        if self.sock:
            self.sock.close()
            self.sock = None

        self.reader = None
        logger.debug(f"InputPort '{self.name}' closed")
