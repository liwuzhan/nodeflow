"""
通道抽象模块
提供对Socket连接的高层封装
"""

import socket
import os
from typing import Optional, Dict, Any

from runtime.ipc.protocol import MessageProtocol
from runtime.utils.errors import SocketError
from runtime.utils.logger import get_logger

logger = get_logger(__name__)


class Channel:
    """
    通道基类
    封装Unix Domain Socket连接
    """

    def __init__(self, socket_path: str):
        """
        初始化通道

        参数：
        - socket_path: Socket文件路径
        """
        self.socket_path = socket_path
        self.sock: Optional[socket.socket] = None

    def is_connected(self) -> bool:
        """
        检查连接是否建立

        返回：
        - True表示已连接，False表示未连接
        """
        return self.sock is not None

    def close(self):
        """
        关闭通道

        清理Socket资源
        """
        if self.sock:
            try:
                self.sock.close()
                logger.debug(f"Closed socket: {self.socket_path}")
            except Exception as e:
                logger.warning(f"Error closing socket {self.socket_path}: {e}")
            finally:
                self.sock = None


class ServerChannel(Channel):
    """
    服务端通道（用于输出端口）
    创建Socket监听器，等待客户端连接
    """

    def __init__(self, socket_path: str):
        """
        初始化服务端通道

        参数：
        - socket_path: Socket文件路径
        """
        super().__init__(socket_path)
        self.server_sock: Optional[socket.socket] = None
        self.client_sock: Optional[socket.socket] = None

    def listen(self, backlog: int = 1):
        """
        开始监听

        创建Unix Domain Socket服务端，并监听连接

        参数：
        - backlog: 监听队列长度
        """
        try:
            # 清理旧的Socket文件
            if os.path.exists(self.socket_path):
                os.unlink(self.socket_path)

            # 创建Unix Domain Socket
            self.server_sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            self.server_sock.bind(self.socket_path)
            self.server_sock.listen(backlog)
            self.server_sock.setblocking(False)  # 非阻塞模式

            logger.debug(f"Server channel listening on: {self.socket_path}")

        except Exception as e:
            raise SocketError(f"Failed to create server socket at {self.socket_path}: {e}")

    def accept(self) -> bool:
        """
        尝试接受客户端连接（非阻塞）

        返回：
        - True表示接受了新连接，False表示无新连接
        """
        if not self.server_sock:
            return False

        try:
            self.client_sock, _ = self.server_sock.accept()
            self.client_sock.setblocking(False)  # 非阻塞模式
            logger.debug(f"Accepted client connection: {self.socket_path}")
            return True
        except BlockingIOError:
            # 无新连接
            return False
        except Exception as e:
            logger.warning(f"Error accepting connection on {self.socket_path}: {e}")
            return False

    def send(self, data: Dict[str, Any]):
        """
        发送数据

        如果没有客户端连接，尝试接受连接
        如果有客户端连接，编码并发送数据

        参数：
        - data: 要发送的数据字典
        """
        # 尝试接受新连接
        if self.client_sock is None:
            self.accept()
            if self.client_sock is None:
                # 仍然无客户端连接，忽略数据
                return

        # 编码消息
        try:
            message = MessageProtocol.encode(data)
            self.client_sock.sendall(message)
            logger.debug(f"Sent message on {self.socket_path}")
        except (BrokenPipeError, ConnectionResetError):
            # 客户端断开连接
            logger.debug(f"Client disconnected: {self.socket_path}")
            self.client_sock.close()
            self.client_sock = None
        except Exception as e:
            logger.warning(f"Error sending data on {self.socket_path}: {e}")
            if self.client_sock:
                self.client_sock.close()
                self.client_sock = None

    def close(self):
        """关闭服务端通道"""
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
            except Exception as e:
                logger.warning(f"Error cleaning up socket file {self.socket_path}: {e}")

        logger.debug(f"Closed server channel: {self.socket_path}")


class ClientChannel(Channel):
    """
    客户端通道（用于输入端口）
    连接到服务端Socket
    """

    def connect(self, timeout: int = 30, retry_interval: float = 1.0):
        """
        连接到服务端

        参数：
        - timeout: 超时时间（秒）
        - retry_interval: 重试间隔（秒）
        """
        import time

        start_time = time.time()
        retries = 0

        while time.time() - start_time < timeout:
            try:
                self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
                self.sock.connect(self.socket_path)
                self.sock.setblocking(False)  # 非阻塞模式

                logger.debug(f"Client channel connected to: {self.socket_path}")
                return

            except (FileNotFoundError, ConnectionRefusedError):
                # Socket文件不存在或服务端未准备好
                if self.sock:
                    self.sock.close()
                    self.sock = None

                retries += 1
                time.sleep(retry_interval)

            except Exception as e:
                if self.sock:
                    self.sock.close()
                    self.sock = None

                raise SocketError(f"Failed to connect to {self.socket_path}: {e}")

        raise SocketError(f"Connection timeout: {self.socket_path} (tried for {timeout}s)")

    def recv(self) -> Optional[Dict[str, Any]]:
        """
        接收一条消息（非阻塞）

        返回：
        - 解码后的消息字典，如果无消息或连接关闭返回None
        """
        if not self.sock:
            return None

        try:
            return MessageProtocol.decode(self.sock)
        except BlockingIOError:
            # 无数据可读
            return None
        except Exception as e:
            logger.warning(f"Error receiving data from {self.socket_path}: {e}")
            return None
