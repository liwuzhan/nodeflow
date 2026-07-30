"""
Late-Joiner 功能测试（纯 SharedBuffer IPC）

验证晚启动的下游节点能够读取上游节点已发送的历史数据
"""

import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from sdk.port import OutputPort, InputPort
from sdk.shared_buffer_lite import SharedBufferLite


def test_late_joiner_basic():
    print("\n=== 测试 Late-Joiner 基础场景 ===")
    SharedBufferLite.cleanup_all()

    output = OutputPort(name="output", buffer_name="upstream.output")
    test_data = {"message": "Hello from upstream", "seq": 1, "timestamp": time.time()}
    output.send(test_data)
    print(f"✓ 上游发送数据: {test_data}")

    input_port = InputPort(name="input", buffer_name="upstream.output")
    print("✓ 下游节点晚启动")

    received_data = input_port.recv_latest()
    assert received_data is not None, "Late-Joiner 应该读取到历史数据"
    assert received_data["message"] == test_data["message"]
    assert received_data["seq"] == test_data["seq"]
    print(f"✓ 下游成功读取历史数据: {received_data}")

    output.close()
    input_port.close()
    SharedBufferLite.cleanup_all()
    print("✅ Late-Joiner 基础测试通过\n")


def test_late_joiner_multiple_updates():
    print("\n=== 测试 Late-Joiner 读取最新值 ===")
    SharedBufferLite.cleanup_all()

    output = OutputPort(name="output", buffer_name="upstream2.output")
    for i in range(1, 4):
        output.send({"message": f"Update {i}", "value": i * 100})
        print(f"  上游发送: Update {i}")

    input_port = InputPort(name="input", buffer_name="upstream2.output")
    received_data = input_port.recv_latest()
    assert received_data is not None
    assert received_data["message"] == "Update 3"
    assert received_data["value"] == 300
    print(f"✓ 下游读取到最新值: {received_data}")

    received_data_2 = input_port.recv_latest()
    assert received_data_2 is None, "缓存数据只应该返回一次"
    print("✓ 缓存数据只返回一次")

    output.close()
    input_port.close()
    SharedBufferLite.cleanup_all()
    print("✅ Late-Joiner 最新值测试通过\n")


def test_late_joiner_then_realtime():
    print("\n=== 测试 Late-Joiner 历史 + 实时数据 ===")
    SharedBufferLite.cleanup_all()

    output = OutputPort(name="output", buffer_name="upstream3.output")
    output.send({"message": "Initial data", "value": 100})

    input_port = InputPort(name="input", buffer_name="upstream3.output")
    history_data = input_port.recv_latest()
    assert history_data is not None and history_data["message"] == "Initial data"
    print(f"✓ 下游读取历史: {history_data}")

    output.send({"message": "New realtime data", "value": 200})
    realtime_data = input_port.recv_latest()
    assert realtime_data is not None and realtime_data["value"] == 200
    print(f"✓ 下游接收实时数据: {realtime_data}")

    output.close()
    input_port.close()
    SharedBufferLite.cleanup_all()
    print("✅ Late-Joiner 历史+实时数据测试通过\n")


def test_no_history_available():
    print("\n=== 测试无历史数据时启动 ===")
    SharedBufferLite.cleanup_all()

    output = OutputPort(name="output", buffer_name="upstream4.output")
    input_port = InputPort(name="input", buffer_name="upstream4.output")
    received_data = input_port.recv_latest()
    assert received_data is None, "没有历史数据时应该返回 None"
    print("✓ 无历史数据时正确返回 None")

    output.send({"message": "First data", "value": 42})
    received_data = input_port.recv_latest()
    assert received_data is not None and received_data["message"] == "First data"
    print(f"✓ 成功接收后续数据: {received_data}")

    output.close()
    input_port.close()
    SharedBufferLite.cleanup_all()
    print("✅ 无历史数据场景测试通过\n")


def test_late_joiner_with_complex_data():
    print("\n=== 测试复杂数据 Late-Joiner ===")
    SharedBufferLite.cleanup_all()

    output = OutputPort(name="output", buffer_name="upstream5.output")
    complex_data = {
        "header": {"timestamp": time.time(), "node_id": "sensor_node", "seq": 1},
        "path": [
            {"lat": 39.9042, "lon": 116.4074, "alt": 50.0},
            {"lat": 39.9043, "lon": 116.4075, "alt": 51.0},
            {"lat": 39.9044, "lon": 116.4076, "alt": 52.0},
        ],
        "metadata": {"points_count": 3, "total_distance": 300.5},
    }
    output.send(complex_data)

    input_port = InputPort(name="input", buffer_name="upstream5.output")
    received_data = input_port.recv_latest()
    assert received_data is not None
    assert received_data["header"]["node_id"] == "sensor_node"
    assert len(received_data["path"]) == 3
    assert received_data["metadata"]["total_distance"] == 300.5
    print(f"✓ 成功读取复杂数据: {len(received_data['path'])} 个路径点")

    output.close()
    input_port.close()
    SharedBufferLite.cleanup_all()
    print("✅ 复杂数据 Late-Joiner 测试通过\n")


def main():
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
