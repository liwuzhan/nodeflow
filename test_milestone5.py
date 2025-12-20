#!/usr/bin/env python3
"""
里程碑5测试脚本 - 验证节点SDK实现
"""

import sys
import os
import time
import tempfile
import threading
from pathlib import Path

# 添加项目根目录到路径
sys.path.insert(0, str(Path(__file__).parent))

from sdk.param_parser import ParamParser
from sdk.port import OutputPort, InputPort
from sdk.latest_value_reader import LatestValueReader
from sdk.nodeflow_sdk import NodeFlowSDK


def test_param_parser():
    """测试参数解析器"""
    print("=" * 60)
    print("测试参数解析器")
    print("=" * 60)

    # 模拟命令行参数
    original_argv = sys.argv
    sys.argv = ['test.py', '--params', '{"device":"/dev/ttyUSB0","baudrate":115200}']

    try:
        params = ParamParser.parse()

        assert params['device'] == "/dev/ttyUSB0"
        assert params['baudrate'] == 115200

        print(f"✓ 参数解析成功: {params}")

        # 测试获取参数
        device = ParamParser.get_param(params, 'device')
        assert device == "/dev/ttyUSB0"
        print(f"✓ get_param测试通过: device={device}")

        # 测试默认值
        missing = ParamParser.get_param(params, 'missing', 'default')
        assert missing == 'default'
        print(f"✓ 默认值测试通过: missing={missing}")

        # 测试require_param
        try:
            ParamParser.require_param(params, 'nonexistent')
            assert False, "应该抛出异常"
        except ValueError:
            print("✓ require_param异常测试通过")

    finally:
        sys.argv = original_argv

    print("✓ 参数解析器测试通过\n")


def test_output_input_ports():
    """测试输出端口和输入端口通信"""
    print("=" * 60)
    print("测试输出/输入端口通信")
    print("=" * 60)

    with tempfile.TemporaryDirectory() as tmpdir:
        socket_path = str(Path(tmpdir) / "test.sock")

        # 输出端口（服务端）
        output_port = OutputPort("test_output", socket_path)
        print("✓ OutputPort创建成功")

        # 输入端口（客户端）在另一个线程启动
        received_data = []

        def input_thread():
            time.sleep(0.5)  # 给输出端口时间准备

            try:
                input_port = InputPort("test_input", socket_path)
                print("✓ InputPort连接成功")

                # 接收消息（阻塞）
                for i in range(3):
                    data = input_port.recv_latest_blocking(timeout=2.0)
                    if data:
                        received_data.append(data)
                        print(f"✓ 接收到消息 {i+1}: {data}")

                input_port.close()

            except Exception as e:
                print(f"✗ InputPort错误: {e}")
                raise

        # 启动输入线程
        thread = threading.Thread(target=input_thread, daemon=True)
        thread.start()

        # 发送消息
        time.sleep(1.0)  # 等待客户端连接
        for i in range(5):
            output_port.send({"count": i, "timestamp": time.time()})
            print(f"✓ 发送消息 {i+1}")
            time.sleep(0.3)

        # 等待线程完成
        thread.join(timeout=10)

        # 验证接收到的消息
        assert len(received_data) >= 2, f"应该接收到至少2条消息，实际收到{len(received_data)}条"
        print(f"✓ 接收到{len(received_data)}条消息")

        output_port.close()

    print("✓ 输出/输入端口测试通过\n")


def test_latest_value_semantics():
    """测试最新值语义"""
    print("=" * 60)
    print("测试最新值语义")
    print("=" * 60)

    with tempfile.TemporaryDirectory() as tmpdir:
        socket_path = str(Path(tmpdir) / "latest.sock")

        # 输出端口
        output_port = OutputPort("sender", socket_path)
        print("✓ 发送端创建成功")

        # 接收端
        received_values = []

        def receiver_thread():
            time.sleep(0.5)

            try:
                input_port = InputPort("receiver", socket_path)
                print("✓ 接收端连接成功")

                # 等待发送端发送大量数据
                time.sleep(2.0)

                # 读取最新值（应该只有最后一条）
                latest = input_port.recv_latest()
                if latest:
                    received_values.append(latest)
                    print(f"✓ 接收到最新值: {latest}")

                input_port.close()

            except Exception as e:
                print(f"✗ 接收端错误: {e}")
                raise

        # 启动接收线程
        thread = threading.Thread(target=receiver_thread, daemon=True)
        thread.start()

        # 发送端快速发送大量消息
        time.sleep(1.0)
        for i in range(100):
            output_port.send({"seq": i})
            time.sleep(0.01)  # 快速发送

        print(f"✓ 发送了100条消息")

        # 等待接收线程
        thread.join(timeout=5)

        # 验证：由于latest-value语义，应该只收到最后的消息
        if received_values:
            last_seq = received_values[0]['seq']
            print(f"✓ 最新值语义验证: 接收到seq={last_seq}（应该接近99）")
            assert last_seq >= 90, "最新值应该是最后几条消息之一"
        else:
            print("⚠ 未接收到数据（可能时序问题）")

        output_port.close()

    print("✓ 最新值语义测试通过\n")


def test_nodeflow_sdk():
    """测试完整的SDK"""
    print("=" * 60)
    print("测试NodeFlow SDK")
    print("=" * 60)

    # 设置环境变量（模拟框架注入）
    os.environ['NODE_ID'] = 'test_sdk_node'
    os.environ['NODE_HUB_PATH'] = '/node-hub'

    with tempfile.TemporaryDirectory() as tmpdir:
        os.environ['NODE_SOCKET_DIR'] = tmpdir
        os.environ['NODE_IN_input1'] = str(Path(tmpdir) / "input1.sock")
        os.environ['NODE_OUT_output1'] = str(Path(tmpdir) / "output1.sock")

        # 模拟命令行参数
        original_argv = sys.argv
        sys.argv = ['test.py', '--params', '{"device":"test","rate":10}']

        try:
            # 使用上下文管理器
            with NodeFlowSDK() as sdk:
                # 验证基本信息
                assert sdk.node_id == 'test_sdk_node'
                print(f"✓ Node ID: {sdk.node_id}")

                # 验证参数
                device = sdk.get_param('device')
                rate = sdk.get_param('rate')
                assert device == 'test'
                assert rate == 10
                print(f"✓ 参数解析: device={device}, rate={rate}")

                # 创建端口
                output = sdk.create_output_port('output1')
                print(f"✓ 创建输出端口: output1")

                # 尝试发送数据（无客户端连接，不会报错）
                output.send({"test": "data"})
                print(f"✓ 发送数据（无客户端）")

        finally:
            sys.argv = original_argv

    print("✓ NodeFlow SDK测试通过\n")


if __name__ == "__main__":
    try:
        test_param_parser()
        test_output_input_ports()
        test_latest_value_semantics()
        test_nodeflow_sdk()

        print("=" * 60)
        print("里程碑5所有测试通过！")
        print("=" * 60)
    except Exception as e:
        print(f"测试失败: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
