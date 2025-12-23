"""
Late-Joiner 功能测试

验证晚启动的下游节点能够读取上游节点已发送的历史数据

测试场景：
1. 上游节点启动并发送数据
2. 下游节点晚启动
3. 下游节点首次调用 recv_latest() 应该读取到历史数据
"""

import os
import sys
import time
import subprocess
import tempfile
from pathlib import Path

# 添加项目根目录到路径
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from sdk.port import OutputPort, InputPort
from sdk.shared_buffer_lite import SharedBufferLite


def test_late_joiner_basic():
    """测试基础的 Late-Joiner 场景"""
    print("\n=== 测试 Late-Joiner 基础场景 ===")

    # 清理旧缓冲区
    SharedBufferLite.cleanup_all()

    # 1. 上游节点启动并发送数据
    zmq_address = "ipc:///tmp/nodeflow/upstream.output"
    output = OutputPort(name="output", zmq_address=zmq_address)

    test_data = {"message": "Hello from upstream", "seq": 1, "timestamp": time.time()}
    output.send(test_data)

    print(f"✓ 上游发送数据: {test_data}")

    # 给ZMQ时间传播
    time.sleep(0.2)

    # 2. 下游节点晚启动
    input_port = InputPort(name="input", zmq_address_or_source=zmq_address)

    print("✓ 下游节点晚启动")

    # 3. 下游首次读取应该获取历史数据
    received_data = input_port.recv_latest()

    assert received_data is not None, "Late-Joiner 应该读取到历史数据"
    assert received_data["message"] == test_data["message"], "数据内容应该匹配"
    assert received_data["seq"] == test_data["seq"], "数据序列号应该匹配"

    print(f"✓ 下游成功读取历史数据: {received_data}")

    # 清理
    output.close()
    input_port.close()
    SharedBufferLite.cleanup_all()

    print("✅ Late-Joiner 基础测试通过\n")


def test_late_joiner_multiple_updates():
    """测试上游多次更新后，Late-Joiner 只读取最新值"""
    print("\n=== 测试 Late-Joiner 读取最新值 ===")

    # 清理旧缓冲区
    SharedBufferLite.cleanup_all()

    # 1. 上游节点启动并发送多次数据
    zmq_address = "ipc:///tmp/nodeflow/upstream2.output"
    output = OutputPort(name="output", zmq_address=zmq_address)

    # 发送3次数据
    for i in range(1, 4):
        data = {"message": f"Update {i}", "value": i * 100}
        output.send(data)
        print(f"  上游发送: {data}")
        time.sleep(0.05)

    time.sleep(0.2)

    # 2. 下游节点晚启动
    input_port = InputPort(name="input", zmq_address_or_source=zmq_address)

    # 3. 下游首次读取应该获取最新值（第3次数据）
    received_data = input_port.recv_latest()

    assert received_data is not None, "Late-Joiner 应该读取到数据"
    assert received_data["message"] == "Update 3", "应该读取到最新值"
    assert received_data["value"] == 300, "应该是最新的值"

    print(f"✓ 下游读取到最新值: {received_data}")

    # 4. 第二次调用应该返回 None（没有新数据）
    received_data_2 = input_port.recv_latest()
    assert received_data_2 is None, "缓存数据只应该返回一次"

    print("✓ 缓存数据只返回一次")

    # 清理
    output.close()
    input_port.close()
    SharedBufferLite.cleanup_all()

    print("✅ Late-Joiner 最新值测试通过\n")


def test_late_joiner_then_realtime():
    """测试 Late-Joiner 读取历史后，继续接收实时数据"""
    print("\n=== 测试 Late-Joiner 历史 + 实时数据 ===")

    # 清理旧缓冲区
    SharedBufferLite.cleanup_all()

    # 1. 上游启动并发送初始数据
    zmq_address = "ipc:///tmp/nodeflow/upstream3.output"
    output = OutputPort(name="output", zmq_address=zmq_address)

    initial_data = {"message": "Initial data", "value": 100}
    output.send(initial_data)
    time.sleep(0.2)

    # 2. 下游晚启动并读取历史
    input_port = InputPort(name="input", zmq_address_or_source=zmq_address)

    history_data = input_port.recv_latest()
    assert history_data is not None, "应该读取到历史数据"
    assert history_data["message"] == "Initial data"

    print(f"✓ 下游读取历史: {history_data}")

    # 3. 上游发送新数据
    new_data = {"message": "New realtime data", "value": 200}
    output.send(new_data)
    time.sleep(0.2)

    # 4. 下游应该能接收新数据
    realtime_data = input_port.recv_latest()
    assert realtime_data is not None, "应该接收到新数据"
    assert realtime_data["message"] == "New realtime data"
    assert realtime_data["value"] == 200

    print(f"✓ 下游接收实时数据: {realtime_data}")

    # 清理
    output.close()
    input_port.close()
    SharedBufferLite.cleanup_all()

    print("✅ Late-Joiner 历史+实时数据测试通过\n")


def test_no_history_available():
    """测试上游还没发送数据时，下游启动"""
    print("\n=== 测试无历史数据时启动 ===")

    # 清理旧缓冲区
    SharedBufferLite.cleanup_all()

    # 1. 上游启动但不发送数据
    zmq_address = "ipc:///tmp/nodeflow/upstream4.output"
    output = OutputPort(name="output", zmq_address=zmq_address)

    time.sleep(0.2)

    # 2. 下游启动
    input_port = InputPort(name="input", zmq_address_or_source=zmq_address)

    # 3. 第一次读取应该返回 None（没有历史数据）
    received_data = input_port.recv_latest()
    assert received_data is None, "没有历史数据时应该返回 None"

    print("✓ 无历史数据时正确返回 None")

    # 4. 上游发送数据
    data = {"message": "First data", "value": 42}
    output.send(data)
    time.sleep(0.2)

    # 5. 下游应该能接收
    received_data = input_port.recv_latest()
    assert received_data is not None, "应该接收到新数据"
    assert received_data["message"] == "First data"

    print(f"✓ 成功接收后续数据: {received_data}")

    # 清理
    output.close()
    input_port.close()
    SharedBufferLite.cleanup_all()

    print("✅ 无历史数据场景测试通过\n")


def test_late_joiner_with_complex_data():
    """测试复杂数据结构的 Late-Joiner"""
    print("\n=== 测试复杂数据 Late-Joiner ===")

    # 清理旧缓冲区
    SharedBufferLite.cleanup_all()

    # 1. 上游发送复杂数据
    zmq_address = "ipc:///tmp/nodeflow/upstream5.output"
    output = OutputPort(name="output", zmq_address=zmq_address)

    complex_data = {
        "header": {
            "timestamp": time.time(),
            "node_id": "sensor_node",
            "seq": 1
        },
        "path": [
            {"lat": 39.9042, "lon": 116.4074, "alt": 50.0},
            {"lat": 39.9043, "lon": 116.4075, "alt": 51.0},
            {"lat": 39.9044, "lon": 116.4076, "alt": 52.0}
        ],
        "metadata": {
            "points_count": 3,
            "total_distance": 300.5
        }
    }

    output.send(complex_data)
    time.sleep(0.2)

    # 2. 下游晚启动
    input_port = InputPort(name="input", zmq_address_or_source=zmq_address)

    # 3. 读取复杂数据
    received_data = input_port.recv_latest()

    assert received_data is not None, "应该读取到数据"
    assert received_data["header"]["node_id"] == "sensor_node"
    assert len(received_data["path"]) == 3
    assert received_data["path"][0]["lat"] == 39.9042
    assert received_data["metadata"]["total_distance"] == 300.5

    print(f"✓ 成功读取复杂数据: {len(received_data['path'])} 个路径点")

    # 清理
    output.close()
    input_port.close()
    SharedBufferLite.cleanup_all()

    print("✅ 复杂数据 Late-Joiner 测试通过\n")


def main():
    """运行所有 Late-Joiner 测试"""
    print("=" * 70)
    print("Late-Joiner 功能测试")
    print("=" * 70)

    try:
        test_late_joiner_basic()
        test_late_joiner_multiple_updates()
        test_late_joiner_then_realtime()
        test_no_history_available()
        test_late_joiner_with_complex_data()

        print("=" * 70)
        print("✅ 所有 Late-Joiner 测试通过！")
        print("=" * 70)

    except AssertionError as e:
        print(f"\n❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

    except Exception as e:
        print(f"\n❌ 测试出错: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
