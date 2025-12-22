#!/usr/bin/env python3
"""
InputPort 自动重连测试

测试场景：
1. 验证正常连接和断开
2. 验证自动重连逻辑
3. 验证指数退避
"""

import tempfile
import threading
import time
from pathlib import Path

from runtime.ipc.channel import ServerChannel, ClientChannel
from runtime.ipc.protocol import MessageProtocol
from sdk.port import InputPort, OutputPort


def test_inputport_reconnect_basic():
    """测试InputPort基本重连功能"""
    print("\n" + "="*60)
    print("测试1: InputPort基本重连功能")
    print("="*60)

    with tempfile.TemporaryDirectory() as tmpdir:
        socket_path = str(Path(tmpdir) / "test.sock")

        # 第一阶段：创建OutputPort（服务端）
        output_port = OutputPort("output", socket_path)
        print("✓ 创建OutputPort")

        # 第二阶段：创建InputPort（客户端），应该连接成功
        input_port = InputPort("input", socket_path)
        assert input_port.is_connected(), "InputPort应该已连接"
        print(f"✓ 创建InputPort，状态: {input_port.get_connection_state()}")

        # 第三阶段：发送和接收数据
        msg = {"test": "data", "value": 42}
        output_port.send(msg)
        print("✓ OutputPort发送消息")

        # 第四阶段：关闭OutputPort，模拟对端断开
        output_port.close()
        print("✓ 关闭OutputPort")

        # 第五阶段：InputPort会在下次recv时检测到断开
        time.sleep(0.5)
        # 可能需要多次读取才能检测到连接断开
        for _ in range(5):
            result = input_port.recv_latest()
            if input_port.get_connection_state() == "disconnected":
                break
            time.sleep(0.1)

        print(f"✓ InputPort检测到断开，recv返回: {result}")
        assert input_port.get_connection_state() == "disconnected", "InputPort应该处于disconnected状态"
        print(f"✓ InputPort状态: {input_port.get_connection_state()}")

        # 第六阶段：重新创建OutputPort，InputPort应该自动重连
        output_port = OutputPort("output", socket_path)
        print("✓ 重新创建OutputPort")

        # 让InputPort检测到新的OutputPort并重连
        # 需要等待一秒使得重连间隔满足
        time.sleep(1.5)
        result = input_port.recv_latest()
        print(f"✓ InputPort尝试重连后recv返回: {result}")

        # 再发送一条消息验证重连成功
        msg2 = {"test": "reconnected", "value": 100}
        output_port.send(msg2)
        print("✓ OutputPort发送第二条消息")

        # InputPort应该能收到新消息（重连成功的证据）
        time.sleep(0.1)
        result = input_port.recv_latest()
        print(f"✓ 重连成功！InputPort接收到消息: {result}")
        assert input_port.is_connected(), "InputPort应该已重新连接"
        print(f"✓ InputPort状态: {input_port.get_connection_state()}")

        # 清理
        input_port.close()
        output_port.close()
        print("✓ 测试1通过！\n")


def test_exponential_backoff():
    """测试指数退避重试间隔"""
    print("="*60)
    print("测试2: 指数退避重试间隔")
    print("="*60)

    with tempfile.TemporaryDirectory() as tmpdir:
        socket_path = str(Path(tmpdir) / "test_backoff.sock")

        # 创建InputPort，但对端不存在，会失败并进入disconnected状态
        try:
            input_port = InputPort("input", socket_path)
        except ConnectionError as e:
            print(f"✓ 初始连接失败（预期行为）: {e}")
            # 手动创建一个断开的InputPort用于测试
            input_port = InputPort.__new__(InputPort)
            input_port.name = "input"
            input_port.socket_path = socket_path
            input_port.sock = None
            input_port.reader = None
            input_port._last_reconnect_time = 0.0
            input_port._reconnect_interval = 1.0
            input_port._max_reconnect_interval = 30.0
            input_port._connection_state = "disconnected"

        # 验证初始重试间隔
        assert input_port._reconnect_interval == 1.0, "初始重试间隔应该是1.0秒"
        print(f"✓ 初始重试间隔: {input_port._reconnect_interval}秒")

        # 尝试重连（失败），重试间隔应该增加
        time.sleep(1.1)
        result = input_port._try_reconnect()
        assert result == False, "重连应该失败"
        assert input_port._reconnect_interval == 1.5, f"重试间隔应该是1.5秒，实际是{input_port._reconnect_interval}"
        print(f"✓ 第1次失败，重试间隔增加到: {input_port._reconnect_interval}秒")

        # 再次尝试重连（失败），重试间隔继续增加
        time.sleep(1.6)
        result = input_port._try_reconnect()
        assert result == False, "重连应该失败"
        assert input_port._reconnect_interval == 2.25, f"重试间隔应该是2.25秒，实际是{input_port._reconnect_interval}"
        print(f"✓ 第2次失败，重试间隔增加到: {input_port._reconnect_interval}秒")

        # 再次尝试重连（失败），重试间隔继续增加
        time.sleep(2.3)
        result = input_port._try_reconnect()
        assert result == False, "重连应该失败"
        assert input_port._reconnect_interval == 3.375, f"重试间隔应该是3.375秒，实际是{input_port._reconnect_interval}"
        print(f"✓ 第3次失败，重试间隔增加到: {input_port._reconnect_interval}秒")

        print("✓ 测试2通过！\n")


def test_concurrent_reconnect():
    """测试并发场景下的重连"""
    print("="*60)
    print("测试3: 并发重连场景")
    print("="*60)

    with tempfile.TemporaryDirectory() as tmpdir:
        socket_path = str(Path(tmpdir) / "test_concurrent.sock")

        # 启动OutputPort
        output_port = OutputPort("output", socket_path)
        print("✓ 创建OutputPort")

        # 创建多个InputPort
        input_ports = []
        for i in range(3):
            port = InputPort(f"input_{i}", socket_path)
            input_ports.append(port)
            assert port.is_connected(), f"InputPort {i}应该已连接"
        print(f"✓ 创建了{len(input_ports)}个InputPort，都已连接")

        # 关闭OutputPort模拟断开
        output_port.close()
        print("✓ 关闭OutputPort")

        # 所有InputPort都应该检测到断开
        time.sleep(0.5)
        for i, port in enumerate(input_ports):
            # 可能需要多次读取才能检测到连接断开
            for _ in range(5):
                port.recv_latest()
                if port.get_connection_state() == "disconnected":
                    break
                time.sleep(0.1)
            assert port.get_connection_state() == "disconnected", f"InputPort {i}应该断开"
        print(f"✓ 所有{len(input_ports)}个InputPort都检测到断开")

        # 重新创建OutputPort
        output_port = OutputPort("output", socket_path)
        print("✓ 重新创建OutputPort")

        # 所有InputPort都应该自动重连
        time.sleep(1.5)
        for i, port in enumerate(input_ports):
            port.recv_latest()
            assert port.get_connection_state() == "connected", f"InputPort {i}应该已重连"
        print(f"✓ 所有{len(input_ports)}个InputPort都自动重连成功")

        # 验证数据流畅
        msg = {"broadcast": "test", "index": 1}
        output_port.send(msg)
        time.sleep(0.1)

        received_count = 0
        for i, port in enumerate(input_ports):
            result = port.recv_latest()
            if result is not None:
                received_count += 1
                print(f"  InputPort {i}接收到: {result}")

        assert received_count > 0, "至少有一个InputPort应该接收到数据"
        print(f"✓ 共{received_count}个InputPort接收到广播消息")

        # 清理
        for port in input_ports:
            port.close()
        output_port.close()
        print("✓ 测试3通过！\n")


def test_connection_state_api():
    """测试连接状态API"""
    print("="*60)
    print("测试4: 连接状态API")
    print("="*60)

    with tempfile.TemporaryDirectory() as tmpdir:
        socket_path = str(Path(tmpdir) / "test_api.sock")

        # 创建OutputPort
        output_port = OutputPort("output", socket_path)
        print("✓ 创建OutputPort")

        # 创建InputPort，应该处于connected状态
        input_port = InputPort("input", socket_path)

        # 测试is_connected()
        assert input_port.is_connected() == True, "is_connected()应该返回True"
        print(f"✓ is_connected(): {input_port.is_connected()}")

        # 测试get_connection_state()
        state = input_port.get_connection_state()
        assert state == "connected", f"get_connection_state()应该返回'connected'，实际是'{state}'"
        print(f"✓ get_connection_state(): '{state}'")

        # 关闭OutputPort，模拟断开
        output_port.close()
        print("✓ 关闭OutputPort")

        # InputPort应该检测到断开
        time.sleep(0.5)
        # 可能需要多次读取才能检测到连接断开
        for _ in range(5):
            input_port.recv_latest()
            if not input_port.is_connected():
                break
            time.sleep(0.1)

        assert input_port.is_connected() == False, "is_connected()应该返回False"
        print(f"✓ 断开后is_connected(): {input_port.is_connected()}")

        state = input_port.get_connection_state()
        assert state == "disconnected", f"get_connection_state()应该返回'disconnected'，实际是'{state}'"
        print(f"✓ 断开后get_connection_state(): '{state}'")

        # 清理
        input_port.close()
        print("✓ 测试4通过！\n")


if __name__ == "__main__":
    print("\n" + "="*60)
    print("InputPort 自动重连功能完整测试")
    print("="*60)

    try:
        test_inputport_reconnect_basic()
        test_exponential_backoff()
        test_concurrent_reconnect()
        test_connection_state_api()

        print("="*60)
        print("所有测试通过！✓")
        print("="*60)
    except AssertionError as e:
        print(f"\n✗ 测试失败: {e}")
        exit(1)
    except Exception as e:
        print(f"\n✗ 测试异常: {e}")
        import traceback
        traceback.print_exc()
        exit(1)
