"""
IPC消息协议模块
实现Socket通信的消息格式和编解码（MsgPack + 版本控制）
"""

import struct
import msgpack
import socket
from typing import Dict, Optional, Any

from runtime.utils.errors import ProtocolError
from runtime.utils.logger import get_logger

logger = get_logger(__name__)


class MessageProtocol:
    """
    消息协议实现（MsgPack 格式 + 版本控制）

    格式: [1字节版本] + [4字节小端序长度] + [MsgPack数据]

    示例（IMU 消息）:
    {
        "accel": {"x": 0.1, "y": 0.2, "z": 9.8},
        "timestamp": 1234567890
    }

    编码后:
    [0x01] + [0x28, 0x00, 0x00, 0x00] + [MsgPack 二进制 40 字节]

    版本历史:
    - v0x01: MsgPack 格式（当前版本）
    - v0x02: 预留给分片传输协议（未来）
    """

    PROTOCOL_VERSION = 0x01  # 当前协议版本

    @staticmethod
    def encode(data: Dict[str, Any]) -> bytes:
        """
        编码消息为 MsgPack 格式

        参数：
        - data: 要发送的数据字典

        返回：
        - 编码后的字节流（版本 + 长度前缀 + MsgPack数据）

        异常：
        - ProtocolError: 编码失败
        """
        try:
            # MsgPack 序列化
            msgpack_bytes = msgpack.packb(data, use_bin_type=True)

            # 验证大小限制
            length = len(msgpack_bytes)
            if length > 1024 * 1024:  # 1MB
                raise ProtocolError(f"Message too large: {length} bytes")

            # 构造消息: [版本] + [长度] + [数据]
            version_byte = struct.pack("B", MessageProtocol.PROTOCOL_VERSION)
            length_prefix = struct.pack("<I", length)
            message = version_byte + length_prefix + msgpack_bytes

            logger.debug(
                f"Encoded message: v={MessageProtocol.PROTOCOL_VERSION}, len={length}"
            )
            return message

        except (TypeError, ValueError) as e:
            raise ProtocolError(f"Failed to encode with MsgPack: {e}")
        except Exception as e:
            raise ProtocolError(f"Unexpected error encoding message: {e}")

    @staticmethod
    def decode(sock: socket.socket) -> Optional[Dict[str, Any]]:
        """
        从socket解码一条消息（MsgPack 格式）

        步骤：
        1. 读取1字节版本号
        2. 读取4字节长度前缀
        3. 根据长度读取MsgPack消息体
        4. 根据版本号反序列化

        参数：
        - sock: Socket对象（应该处于可读状态）

        返回：
        - 解码后的数据字典，如果连接关闭返回None

        异常：
        - ProtocolError: 解码失败
        """
        try:
            # 读取版本字节
            version_data = MessageProtocol._recv_exact(sock, 1)
            if not version_data:
                logger.debug("Connection closed or no data (version byte)")
                return None

            version = struct.unpack("B", version_data)[0]

            # 读取长度前缀（4 字节）
            length_data = MessageProtocol._recv_exact(sock, 4)
            if not length_data:
                logger.debug("Connection closed or no data (length prefix)")
                return None

            length = struct.unpack("<I", length_data)[0]

            # 验证长度
            if length == 0:
                raise ProtocolError("Invalid message length: 0")

            if length > 1024 * 1024:  # 最大 1MB
                raise ProtocolError(f"Message too large: {length} bytes")

            # 读取 MsgPack 数据
            msgpack_data = MessageProtocol._recv_exact(sock, length)
            if not msgpack_data:
                logger.debug("Connection closed while reading message body")
                return None

            # 根据版本号解码
            if version == 0x01:
                data = msgpack.unpackb(msgpack_data, raw=False)
                logger.debug(f"Decoded message: v={version}, len={length}")
                return data
            else:
                raise ProtocolError(f"Unsupported protocol version: {version}")

        except BlockingIOError:
            # 保持透传（latest-value 语义依赖此行为）
            raise
        except msgpack.UnpackException as e:
            raise ProtocolError(f"Failed to decode MsgPack: {e}")
        except struct.error as e:
            raise ProtocolError(f"Failed to parse message header: {e}")
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
        data = b""

        while len(data) < n:
            try:
                chunk = sock.recv(n - len(data))
                if not chunk:
                    # recv()返回空表示连接关闭
                    if len(data) == 0:
                        return None
                    else:
                        # 部分数据已读取，但连接突然关闭
                        raise ProtocolError(
                            f"Connection closed unexpectedly (got {len(data)}/{n} bytes)"
                        )

                data += chunk

            except socket.timeout:
                # 超时
                raise ProtocolError(f"Socket timeout (got {len(data)}/{n} bytes)")
            except BlockingIOError:
                # 非阻塞Socket无数据 - 直接抛出不包装，让上层处理
                raise
            except Exception as e:
                raise ProtocolError(f"Socket error: {e}")

        return data

    @staticmethod
    def validate_json(data: Dict[str, Any]) -> bool:
        """
        验证数据是否可被序列化（现使用 MsgPack）

        参数：
        - data: 要验证的数据字典

        返回：
        - True表示可以序列化，False表示不行
        """
        try:
            msgpack.packb(data, use_bin_type=True)
            return True
        except (TypeError, ValueError):
            return False
