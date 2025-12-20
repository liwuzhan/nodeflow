"""
IPC消息协议模块
实现Socket通信的消息格式和编解码
"""

import struct
import json
import socket
from typing import Dict, Optional, Any

from runtime.utils.errors import ProtocolError
from runtime.utils.logger import get_logger

logger = get_logger(__name__)


class MessageProtocol:
    """
    消息协议实现
    格式：[4字节小端序长度] + [JSON消息体]

    例如：
    {
        "data": "value",
        "timestamp": 1234567890
    }

    编码后为：
    [0x1D, 0x00, 0x00, 0x00] + {"data":"value","timestamp":1234567890}
    """

    @staticmethod
    def encode(data: Dict[str, Any]) -> bytes:
        """
        编码消息

        参数：
        - data: 要发送的数据字典

        返回：
        - 编码后的字节流（长度前缀 + JSON数据）

        异常：
        - ProtocolError: 编码失败
        """
        try:
            # JSON序列化
            json_str = json.dumps(data)
            json_bytes = json_str.encode('utf-8')

            # 计算长度
            length = len(json_bytes)

            # 创建长度前缀（4字节小端序）
            length_prefix = struct.pack('<I', length)

            # 返回长度前缀 + JSON数据
            message = length_prefix + json_bytes

            logger.debug(f"Encoded message: length={length}, data={json_str[:50]}...")
            return message

        except (TypeError, ValueError) as e:
            raise ProtocolError(f"Failed to encode message: {e}")
        except Exception as e:
            raise ProtocolError(f"Unexpected error encoding message: {e}")

    @staticmethod
    def decode(sock: socket.socket) -> Optional[Dict[str, Any]]:
        """
        从socket解码一条消息

        步骤：
        1. 读取4字节长度前缀
        2. 根据长度读取JSON消息体
        3. JSON反序列化

        参数：
        - sock: Socket对象（应该处于可读状态）

        返回：
        - 解码后的数据字典，如果连接关闭返回None

        异常：
        - ProtocolError: 解码失败
        """
        try:
            # 读取4字节长度前缀
            length_data = MessageProtocol._recv_exact(sock, 4)
            if not length_data:
                # 连接关闭或无数据
                logger.debug("Connection closed or no data (length prefix)")
                return None

            # 解析长度
            length = struct.unpack('<I', length_data)[0]

            if length == 0:
                raise ProtocolError("Invalid message length: 0")

            if length > 1024 * 1024:  # 最大1MB
                raise ProtocolError(f"Message too large: {length} bytes")

            # 读取JSON消息体
            json_data = MessageProtocol._recv_exact(sock, length)
            if not json_data:
                # 连接在读取消息体时关闭
                logger.debug("Connection closed while reading message body")
                return None

            # JSON反序列化
            json_str = json_data.decode('utf-8')
            data = json.loads(json_str)

            logger.debug(f"Decoded message: length={length}, data={json_str[:50]}...")
            return data

        except json.JSONDecodeError as e:
            raise ProtocolError(f"Failed to decode JSON: {e}")
        except struct.error as e:
            raise ProtocolError(f"Failed to parse length prefix: {e}")
        except UnicodeDecodeError as e:
            raise ProtocolError(f"Failed to decode UTF-8: {e}")
        except Exception as e:
            raise ProtocolError(f"Unexpected error decoding message: {e}")

    @staticmethod
    def _recv_exact(sock: socket.socket, n: int) -> Optional[bytes]:
        """
        精确读取n字节

        处理TCP流可能分片的问题，循环读取直到得到n字节

        参数：
        - sock: Socket对象
        - n: 要读取的字节数

        返回：
        - 读取的字节流，如果连接关闭返回None
        """
        data = b''

        while len(data) < n:
            try:
                chunk = sock.recv(n - len(data))
                if not chunk:
                    # recv()返回空表示连接关闭
                    if len(data) == 0:
                        return None
                    else:
                        # 部分数据已读取，但连接突然关闭
                        raise ProtocolError(f"Connection closed unexpectedly (got {len(data)}/{n} bytes)")

                data += chunk

            except socket.timeout:
                # 超时
                raise ProtocolError(f"Socket timeout (got {len(data)}/{n} bytes)")
            except Exception as e:
                raise ProtocolError(f"Socket error: {e}")

        return data

    @staticmethod
    def validate_json(data: Dict[str, Any]) -> bool:
        """
        验证数据是否可被JSON序列化

        参数：
        - data: 要验证的数据字典

        返回：
        - True表示可以序列化，False表示不行
        """
        try:
            json.dumps(data)
            return True
        except (TypeError, ValueError):
            return False
