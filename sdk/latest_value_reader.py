"""
最新值读取器模块
实现latest-value语义：循环读取socket缓冲区，只保留最后一条消息
"""

import socket
from typing import Optional, Dict, Any

# 导入协议模块（与runtime共享）
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from runtime.ipc.protocol import MessageProtocol
from runtime.utils.logger import get_logger

logger = get_logger(__name__)


class LatestValueReader:
    """
    最新值读取器

    核心职责：实现latest-value语义
    - 循环非阻塞读取socket缓冲区
    - 丢弃所有旧消息
    - 只保留最后一条
    """

    def __init__(self, sock: socket.socket):
        """
        初始化最新值读取器

        参数：
        - sock: Socket对象（应该设置为非阻塞模式）
        """
        self.sock = sock

    def read_latest(self) -> Optional[Dict[str, Any]]:
        """
        读取最新值

        算法：
        1. 循环非阻塞读取socket
        2. 每次读到消息就覆盖上一条
        3. 直到socket无数据（BlockingIOError）
        4. 返回最后一条消息

        返回：
        - 最新的消息字典，如果无数据返回None
        """
        latest_msg = None

        while True:
            try:
                msg = MessageProtocol.decode(self.sock)
                if msg is None:
                    # 连接关闭
                    break

                # 覆盖上一条消息
                latest_msg = msg

            except BlockingIOError:
                # 无更多数据
                break
            except Exception as e:
                logger.warning(f"Error reading message: {e}")
                break

        return latest_msg

    def read_latest_blocking(self, timeout: Optional[float] = None) -> Optional[Dict[str, Any]]:
        """
        阻塞读取最新值

        等待直到有数据可读，然后应用最新值语义

        参数：
        - timeout: 超时时间（秒），None表示无限等待

        返回：
        - 最新的消息字典，如果超时返回None
        """
        import select

        # 等待socket可读
        readable, _, _ = select.select([self.sock], [], [], timeout)

        if not readable:
            # 超时
            return None

        # 读取最新值
        return self.read_latest()
