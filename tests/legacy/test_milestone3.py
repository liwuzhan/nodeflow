#!/usr/bin/env python3
"""
里程碑3测试脚本 - 验证IPC通信实现
"""

import sys
import socket
import tempfile
from pathlib import Path

# 添加项目根目录到路径
sys.path.insert(0, str(Path(__file__).parent))

from runtime.ipc.protocol import MessageProtocol
from runtime.ipc.socket_manager import SocketManager
from runtime.ipc.channel import ServerChannel, ClientChannel
from runtime.utils.errors import ProtocolError


def test_message_protocol_encode_decode():
    """测试消息编解码"""
    print("=" * 60)
    print("测试消息编解码")
    print("=" * 60)

    # 测试数据
    data = {
        "timestamp": 1234567890,
        "latitude": 39.9042,
        "longitude": 116.4074,
        "fix_type": "RTK",
        "message": "This is a test message",
    }

    # 编码
    encoded = MessageProtocol.encode(data)
    print(f"✓ 编码成功: {len(encoded)} 字节")

    # 验证格式
    # 验证消息格式（MsgPack + 版本号）
    assert len(encoded) > 5, "消息至少包含1字节版本 + 4字节长度"

    # 解析版本号
    version = encoded[0]
    print(f"✓ 编码格式: MsgPack v{version:#x}")

    # 解析长度前缀（从第 1 字节开始）
    length = int.from_bytes(encoded[1:5], byteorder="little")
    print(f"✓ 消息体长度: {length} 字节")

    # 验证版本号和总长度
    assert version == 0x01, f"协议版本应为 0x01，实际为 {version:#x}"
    assert len(encoded) == 5 + length, f"消息总长度应为 {5 + length}，实际为 {len(encoded)}"
    print(f"✓ 消息格式正确: v={version:#x}, total_len={len(encoded)}, msgpack_len={length}")

    print("✓ 消息编解码测试通过\n")


def test_message_protocol_socket():
    """测试通过Socket发送和接收消息"""
    print("=" * 60)
    print("测试Socket消息收发")
    print("=" * 60)

    import threading
    import time

    # 创建临时socket
    with tempfile.TemporaryDirectory() as tmpdir:
        socket_path = str(Path(tmpdir) / "test.sock")

        # 服务端线程
        def server_thread():
            try:
                # 创建服务端Socket
                server_sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
                server_sock.bind(socket_path)
                server_sock.listen(1)

                print("  [Server] 等待客户端连接...")
                client_sock, _ = server_sock.accept()
                print("  [Server] 客户端已连接")

                # 接收消息
                msg = MessageProtocol.decode(client_sock)
                print(f"  [Server] 接收到消息: {msg}")

                assert msg is not None, "应该接收到消息"
                assert msg["temperature"] == 36.5, "消息内容不匹配"

                # 发送响应
                response = {"status": "ok"}
                encoded = MessageProtocol.encode(response)
                client_sock.sendall(encoded)
                print("  [Server] 发送响应完成")

                client_sock.close()
                server_sock.close()

            except Exception as e:
                print(f"  [Server] 错误: {e}")
                raise

        # 启动服务端线程
        server = threading.Thread(target=server_thread, daemon=True)
        server.start()

        # 给服务端时间准备
        time.sleep(0.5)

        # 客户端：连接并发送消息
        try:
            client_sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            client_sock.connect(socket_path)
            print("  [Client] 已连接到服务端")

            # 发送消息
            data = {"temperature": 36.5, "humidity": 65}
            encoded = MessageProtocol.encode(data)
            client_sock.sendall(encoded)
            print("  [Client] 发送消息完成")

            # 接收响应
            response = MessageProtocol.decode(client_sock)
            print(f"  [Client] 接收到响应: {response}")

            assert response is not None, "应该接收到响应"
            assert response["status"] == "ok", "响应内容不匹配"

            client_sock.close()

        except Exception as e:
            print(f"  [Client] 错误: {e}")
            raise

        # 等待服务端线程完成
        server.join(timeout=5)

    print("✓ Socket消息收发测试通过\n")


def test_socket_manager():
    """测试Socket管理器"""
    print("=" * 60)
    print("测试Socket管理器")
    print("=" * 60)

    with tempfile.TemporaryDirectory() as tmpdir:
        manager = SocketManager(tmpdir)
        manager.initialize()

        print("✓ Socket管理器初始化成功")

        # 创建通道路径
        path1 = manager.create_channel_path("node_a", "output", "out")
        path2 = manager.create_channel_path("node_b", "input", "in")

        print(f"✓ 创建了2个通道路径")
        print(f"  - {path1}")
        print(f"  - {path2}")

        # 验证路径格式
        assert "nodeflow_node_a.output.out" in path1
        assert "nodeflow_node_b.input.in" in path2

        # 获取所有路径
        all_paths = manager.get_all_socket_paths()
        assert len(all_paths) == 2

        print(f"✓ 获取到{len(all_paths)}个通道路径")

        # 清理
        manager.cleanup()
        print("✓ Socket管理器清理完成\n")


def test_server_client_channels():
    """测试服务端和客户端通道"""
    print("=" * 60)
    print("测试服务端/客户端通道")
    print("=" * 60)

    import threading
    import time

    with tempfile.TemporaryDirectory() as tmpdir:
        socket_path = str(Path(tmpdir) / "test.sock")

        # 创建服务端通道
        server_channel = ServerChannel(socket_path)
        server_channel.listen()
        print("✓ 服务端通道创建并监听")

        # 客户端线程
        def client_thread():
            time.sleep(0.5)  # 给服务端时间

            try:
                client_channel = ClientChannel(socket_path)
                client_channel.connect(timeout=5, retry_interval=0.1)
                print("✓ 客户端通道已连接")

                # 通过原始Socket发送消息
                msg_data = {"test": "data", "value": 42}
                encoded = MessageProtocol.encode(msg_data)
                client_channel.sock.setblocking(True)  # 设置为阻塞模式便于测试
                client_channel.sock.sendall(encoded)
                print("✓ 客户端发送消息完成")

                client_channel.close()

            except Exception as e:
                print(f"✗ 客户端错误: {e}")
                raise

        # 启动客户端线程
        client = threading.Thread(target=client_thread, daemon=True)
        client.start()

        # 服务端接受连接并接收消息
        time.sleep(1)
        server_channel.accept()
        print("✓ 服务端接受了客户端连接")

        # 接收消息
        if server_channel.client_socks:
            msg = MessageProtocol.decode(server_channel.client_socks[0])
            if msg:
                print(f"✓ 服务端接收到消息: {msg}")
                assert msg["test"] == "data"
                assert msg["value"] == 42

        # 清理
        server_channel.close()
        client.join(timeout=5)

    print("✓ 服务端/客户端通道测试通过\n")


if __name__ == "__main__":
    try:
        test_message_protocol_encode_decode()
        test_message_protocol_socket()
        test_socket_manager()
        test_server_client_channels()

        print("=" * 60)
        print("里程碑3所有测试通过！")
        print("=" * 60)
    except Exception as e:
        print(f"测试失败: {e}")
        import traceback

        traceback.print_exc()
        sys.exit(1)
