"""
通道抽象模块
提供对Socket连接的高层封装
"""

import socket
import os
from typing import Optional, Dict, Any, List

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
    支持1-to-many连接（一个输出端口连接多个输入端口）
    """

    def __init__(self, socket_path: str):
        """
        初始化服务端通道

        参数：
        - socket_path: Socket文件路径
        """
        super().__init__(socket_path)
        self.server_sock: Optional[socket.socket] = None
        self.client_socks: List[socket.socket] = []  # 支持多个客户端

    def listen(self, backlog: int = 10):
        """
        开始监听

        创建Unix Domain Socket服务端，并监听连接

        参数：
        - backlog: 监听队列长度（默认10，支持多个客户端）
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
            raise SocketError(
                f"Failed to create server socket at {self.socket_path}: {e}"
            )

    def accept(self) -> bool:
        """
        尝试接受单个客户端连接（非阻塞）

        返回：
        - True表示接受了新连接，False表示无新连接
        """
        if not self.server_sock:
            return False

        try:
            client_sock, _ = self.server_sock.accept()
            client_sock.setblocking(False)  # 非阻塞模式
            self.client_socks.append(client_sock)
            logger.debug(
                f"Accepted client connection: {self.socket_path} (total: {len(self.client_socks)})"
            )
            return True
        except BlockingIOError:
            # 无新连接
            return False
        except Exception as e:
            logger.warning(f"Error accepting connection on {self.socket_path}: {e}")
            return False

    def _accept_new_clients(self):
        """
        持续接受所有待连接的客户端（非阻塞）

        尽可能多地接受待连接的客户端，直到没有新连接为止
        """
        while self.accept():
            pass  # accept()已经处理了添加客户端

    def send(self, data: Dict[str, Any]):
        """
        向所有已连接客户端发送数据

        策略：
        - 首先尝试接受所有待连接的客户端（非阻塞）
        - 向每个已连接的客户端发送数据
        - BlockingIOError时丢弃消息但保留连接（最新值语义）
        - 真正断开的客户端会被移除

        参数：
        - data: 要发送的数据字典
        """
        # 尝试接受新连接
        self._accept_new_clients()

        # 如果没有任何客户端连接，忽略数据
        if not self.client_socks:
            return

        # 编码消息
        message = MessageProtocol.encode(data)

        # 记录发送失败的客户端索引
        failed_indices = []

        # 向所有客户端发送数据
        for i, client_sock in enumerate(self.client_socks):
            try:
                client_sock.sendall(message)
            except BlockingIOError:
                # 缓冲区满 - 采用"尽力而为"策略
                # 丢弃当前消息，但保留客户端连接（符合最新值语义）
                logger.debug(
                    f"ServerChannel client {i} send buffer full (socket: {self.socket_path}), dropping message"
                )
            except (BrokenPipeError, ConnectionResetError):
                # 客户端真正断开连接 - 移除该客户端
                logger.debug(f"Client {i} disconnected: {self.socket_path}")
                failed_indices.append(i)
                try:
                    client_sock.close()
                except:
                    pass
            except Exception as e:
                # 其他异常 - 移除客户端
                logger.warning(
                    f"Error sending data to client {i} on {self.socket_path}: {e}"
                )
                failed_indices.append(i)
                try:
                    client_sock.close()
                except:
                    pass

        # 移除真正断开的客户端（从后往前删除避免索引错乱）
        for i in reversed(failed_indices):
            self.client_socks.pop(i)

        if failed_indices:
            logger.debug(
                f"Removed {len(failed_indices)} failed client(s) from {self.socket_path}, remaining: {len(self.client_socks)}"
            )

    def close(self):
        """关闭服务端通道"""
        # 关闭所有客户端连接
        for client_sock in self.client_socks:
            try:
                client_sock.close()
            except:
                pass
        self.client_socks.clear()

        # 关闭服务端Socket
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

        raise SocketError(
            f"Connection timeout: {self.socket_path} (tried for {timeout}s)"
        )

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
