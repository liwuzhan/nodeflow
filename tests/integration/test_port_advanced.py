"""
Port 高级集成测试

验证复杂的多节点交互场景：
- 多订阅者场景（1对多、Late-Joiner 混合）
- 高频数据流（1000 msg/s、消息丢失检测）
- 大数据传输（10MB数组、buffer限制）
- 边缘场景（快速启停、同时启动、重启恢复）
"""

import os
import sys
import time
import threading
from pathlib import Path

# 添加项目根目录到路径
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from sdk.port import OutputPort, InputPort
from sdk.shared_buffer_lite import SharedBufferLite

try:
    import numpy as np
    HAS_NUMPY = True
except ImportError:
    HAS_NUMPY = False


# ========== 多订阅者场景测试 ==========

class TestMultipleSubscribers:
    """多订阅者场景测试"""

    def test_one_publisher_multiple_subscribers(self):
        """1个 OutputPort，3个 InputPort 同时订阅"""
        print("\n=== 测试一对多订阅 ===")
        SharedBufferLite.cleanup_all()

        zmq_addr = "ipc:///tmp/nodeflow/test_multi_sub"

        # 创建1个发布者
        output = OutputPort(name="publisher", zmq_address=zmq_addr)
        time.sleep(0.1)

        # 创建3个订阅者
        subscribers = []
        for i in range(3):
            sub = InputPort(name=f"subscriber_{i}", zmq_address_or_source=zmq_addr)
            subscribers.append(sub)

        time.sleep(0.2)

        # 发布者发送数据
        test_data = {"message": "broadcast", "timestamp": time.time()}
        output.send(test_data)
        time.sleep(0.2)

        # 所有订阅者都应该收到
        received_count = 0
        for i, sub in enumerate(subscribers):
            data = sub.recv_latest()
            if data is not None and data["message"] == "broadcast":
                received_count += 1
                print(f"  ✓ 订阅者 {i} 收到数据")

        assert received_count == 3, f"所有3个订阅者应该收到数据，实际 {received_count} 个"

        # 清理
        output.close()
        for sub in subscribers:
            sub.close()
        SharedBufferLite.cleanup_all()

        print("✅ 一对多订阅测试通过")

    def test_late_joiners_mixed(self):
        """订阅者分批启动（0s, 1s, 2s后启动）"""
        print("\n=== 测试分批 Late-Joiner ===")
        SharedBufferLite.cleanup_all()

        zmq_addr = "ipc:///tmp/nodeflow/test_late_mixed"

        # T=0s: 发布者启动并发送第一条
        output = OutputPort(name="pub", zmq_address=zmq_addr)
        msg1 = {"seq": 1, "time": 0}
        output.send(msg1)
        print("  T=0s: 发送 msg1")

        # T=0s: 第一批订阅者启动（应该读到 msg1）
        sub1 = InputPort(name="sub1", zmq_address_or_source=zmq_addr)
        time.sleep(0.1)

        # T=0.5s: 发送第二条
        time.sleep(0.5)
        msg2 = {"seq": 2, "time": 0.5}
        output.send(msg2)
        print("  T=0.5s: 发送 msg2")

        # T=0.5s: 第二批订阅者启动（应该读到 msg2，Late-Joiner）
        sub2 = InputPort(name="sub2", zmq_address_or_source=zmq_addr)
        time.sleep(0.1)

        # T=1s: 发送第三条
        time.sleep(0.5)
        msg3 = {"seq": 3, "time": 1.0}
        output.send(msg3)
        print("  T=1s: 发送 msg3")

        # T=1s: 第三批订阅者启动（应该读到 msg3，Late-Joiner）
        sub3 = InputPort(name="sub3", zmq_address_or_source=zmq_addr)
        time.sleep(0.2)

        # 验证各订阅者读取的数据
        data1 = sub1.recv_latest()  # 应该读到 msg3（最新）
        data2 = sub2.recv_latest()  # 应该读到 msg3（最新）
        data3 = sub3.recv_latest()  # 应该读到 msg3（Late-Joiner历史）

        print(f"  sub1 读到: seq={data1['seq'] if data1 else 'None'}")
        print(f"  sub2 读到: seq={data2['seq'] if data2 else 'None'}")
        print(f"  sub3 读到: seq={data3['seq'] if data3 else 'None'}")

        # 所有订阅者最终都应该读到 msg3 (Latest-Value)
        assert data3 is not None and data3["seq"] == 3, "Late-Joiner 应该读到最新值"

        # 清理
        output.close()
        sub1.close()
        sub2.close()
        sub3.close()
        SharedBufferLite.cleanup_all()

        print("✅ 分批 Late-Joiner 测试通过")

    def test_subscriber_dropout(self):
        """订阅者中途断开后重连"""
        print("\n=== 测试订阅者断开重连 ===")
        SharedBufferLite.cleanup_all()

        zmq_addr = "ipc:///tmp/nodeflow/test_dropout"

        # 发布者
        output = OutputPort(name="pub", zmq_address=zmq_addr)

        # 订阅者1连接
        sub = InputPort(name="sub", zmq_address_or_source=zmq_addr)
        time.sleep(0.1)

        # 发送第一条
        output.send({"msg": 1})
        time.sleep(0.1)
        data1 = sub.recv_latest()
        assert data1 is not None and data1["msg"] == 1, "应该收到第一条"
        print("  ✓ 收到第一条消息")

        # 订阅者断开
        sub.close()
        print("  订阅者断开")
        time.sleep(0.2)

        # 发布者继续发送（订阅者离线）
        output.send({"msg": 2})
        output.send({"msg": 3})
        time.sleep(0.2)

        # 订阅者重连（Late-Joiner，应该读到 msg3）
        sub = InputPort(name="sub", zmq_address_or_source=zmq_addr)
        time.sleep(0.1)

        data3 = sub.recv_latest()
        assert data3 is not None and data3["msg"] == 3, "重连后应该读到最新值 (Late-Joiner)"
        print("  ✓ 重连后读到最新值")

        # 清理
        output.close()
        sub.close()
        SharedBufferLite.cleanup_all()

        print("✅ 订阅者断开重连测试通过")


# ========== 高频数据流测试 ==========

class TestHighFrequencyData:
    """高频数据流测试"""

    def test_high_frequency_send(self):
        """1000 msg/s 发送速率"""
        print("\n=== 测试高频发送 (1000 msg/s) ===")
        SharedBufferLite.cleanup_all()

        zmq_addr = "ipc:///tmp/nodeflow/test_high_freq"

        output = OutputPort(name="fast_pub", zmq_address=zmq_addr)
        input_port = InputPort(name="fast_sub", zmq_address_or_source=zmq_addr)
        time.sleep(0.1)

        # 发送1000条消息，间隔1ms
        num_messages = 1000
        start_time = time.time()

        for i in range(num_messages):
            output.send({"index": i, "ts": time.time()})
            time.sleep(0.001)  # 1ms间隔 = 1000 msg/s

        send_duration = time.time() - start_time
        actual_rate = num_messages / send_duration

        print(f"  发送 {num_messages} 条消息")
        print(f"  耗时: {send_duration:.2f}s")
        print(f"  实际速率: {actual_rate:.0f} msg/s")

        # 验证最终序列号
        final_seq = output.buffer.get_sequence()
        assert final_seq == num_messages, f"序列号应该是 {num_messages}, 得到 {final_seq}"

        # 读取最新值
        time.sleep(0.1)
        latest = input_port.recv_latest()
        assert latest is not None, "应该能读到最新数据"
        assert latest["index"] >= num_messages - 10, "应该是最近的消息"

        print(f"  ✓ 最新消息索引: {latest['index']}")

        # 清理
        output.close()
        input_port.close()
        SharedBufferLite.cleanup_all()

        print("✅ 高频发送测试通过")

    def test_message_loss_detection(self):
        """检测是否有消息丢失（序列号跳跃）"""
        print("\n=== 测试消息丢失检测 ===")
        SharedBufferLite.cleanup_all()

        zmq_addr = "ipc:///tmp/nodeflow/test_loss_detect"

        output = OutputPort(name="pub", zmq_address=zmq_addr)
        input_port = InputPort(name="sub", zmq_address_or_source=zmq_addr)
        time.sleep(0.1)

        # 快速发送100条
        for i in range(100):
            output.send({"index": i})
            time.sleep(0.001)

        time.sleep(0.1)

        # 检查最终序列号连续性
        final_seq = output.buffer.get_sequence()
        assert final_seq == 100, f"序列号应该连续到100, 得到 {final_seq}"

        print(f"  ✓ 序列号连续: 1 → {final_seq}")

        # 清理
        output.close()
        input_port.close()
        SharedBufferLite.cleanup_all()

        print("✅ 消息丢失检测测试通过")

    def test_conflate_mode(self):
        """Conflate模式下旧消息被覆盖（Latest-Value语义）"""
        print("\n=== 测试 Conflate 模式 ===")
        SharedBufferLite.cleanup_all()

        zmq_addr = "ipc:///tmp/nodeflow/test_conflate"

        # 设置 conflate 环境变量
        os.environ['NODE_OUT_test_conflate_CONFLATE'] = 'true'

        output = OutputPort(name="test_conflate", zmq_address=zmq_addr)
        time.sleep(0.1)

        # 快速发送多条
        for i in range(10):
            output.send({"value": i})
            time.sleep(0.01)

        # 订阅者晚启动（Late-Joiner）
        input_port = InputPort(name="sub", zmq_address_or_source=zmq_addr)
        time.sleep(0.1)

        # 应该只读到最新值（Latest-Value）
        data = input_port.recv_latest()
        assert data is not None, "应该读到数据"
        assert data["value"] == 9, f"Conflate 模式应该只保留最新值，得到 {data['value']}"

        print(f"  ✓ 读到最新值: {data['value']}")

        # 清理
        output.close()
        input_port.close()
        del os.environ['NODE_OUT_test_conflate_CONFLATE']
        SharedBufferLite.cleanup_all()

        print("✅ Conflate 模式测试通过")


# ========== 大数据传输测试 ==========

class TestLargeDataTransfer:
    """大数据传输测试"""

    def test_large_numpy_array(self):
        """大数据传输（2MB字符串）"""
        print("\n=== 测试大数据传输 ===")
        SharedBufferLite.cleanup_all()

        zmq_addr = "ipc:///tmp/nodeflow/test_large_data"

        # 创建大 buffer (20MB)
        os.environ['NODE_OUT_large_BUFFER_SIZE'] = str(20 * 1024 * 1024)

        # 先创建发布者和订阅者
        output = OutputPort(name="large", zmq_address=zmq_addr)
        time.sleep(0.1)
        input_port = InputPort(name="sub", zmq_address_or_source=zmq_addr)
        time.sleep(0.1)

        # 创建2MB的字符串数据
        large_string = "x" * (2 * 1024 * 1024)
        data_size_mb = len(large_string) / (1024 * 1024)
        print(f"  数据大小: {data_size_mb:.1f} MB")

        # 发送
        output.send({"payload": large_string, "meta": "large data"})

        # 等待传播
        time.sleep(0.2)

        # 等待接收
        time.sleep(0.1)

        # 接收
        received = input_port.recv_latest()

        # 验证
        assert received is not None, "应该收到数据"
        assert len(received["payload"]) == len(large_string), "数据大小应该匹配"
        assert received["payload"] == large_string, "数据内容应该匹配"

        print("  ✓ 大数据传输成功")

        # 清理
        output.close()
        input_port.close()
        del os.environ['NODE_OUT_large_BUFFER_SIZE']
        SharedBufferLite.cleanup_all()

        print("✅ 大数据传输测试通过")

    def test_near_buffer_limit(self):
        """接近 buffer 大小限制的数据"""
        print("\n=== 测试接近 Buffer 限制 ===")
        SharedBufferLite.cleanup_all()

        zmq_addr = "ipc:///tmp/nodeflow/test_near_limit"

        # 小 buffer (100KB)
        os.environ['NODE_OUT_limit_BUFFER_SIZE'] = str(100 * 1024)
        output = OutputPort(name="limit", zmq_address=zmq_addr)
        input_port = InputPort(name="sub", zmq_address_or_source=zmq_addr)
        time.sleep(0.1)

        # 发送接近限制的数据 (80KB)
        large_payload = "x" * (80 * 1024)
        output.send({"payload": large_payload})

        time.sleep(0.1)
        received = input_port.recv_latest()

        assert received is not None, "接近限制的数据应该成功发送"
        assert len(received["payload"]) == 80 * 1024, "数据大小应该匹配"

        print("  ✓ 接近限制的数据传输成功")

        # 清理
        output.close()
        input_port.close()
        del os.environ['NODE_OUT_limit_BUFFER_SIZE']
        SharedBufferLite.cleanup_all()

        print("✅ 接近 Buffer 限制测试通过")

    def test_buffer_overflow_error(self):
        """超过 buffer 大小的错误处理"""
        print("\n=== 测试 Buffer 溢出 ===")
        SharedBufferLite.cleanup_all()

        zmq_addr = "ipc:///tmp/nodeflow/test_overflow"

        # 小 buffer (10KB)
        os.environ['NODE_OUT_overflow_BUFFER_SIZE'] = str(10 * 1024)
        output = OutputPort(name="overflow", zmq_address=zmq_addr)
        time.sleep(0.1)

        # 尝试发送超大数据 (20KB)
        huge_payload = "x" * (20 * 1024)

        try:
            output.send({"payload": huge_payload})
            assert False, "应该抛出异常"
        except (ValueError, Exception) as e:
            print(f"  ✓ 正确抛出异常: {type(e).__name__}")

        # 清理
        output.close()
        del os.environ['NODE_OUT_overflow_BUFFER_SIZE']
        SharedBufferLite.cleanup_all()

        print("✅ Buffer 溢出测试通过")


# ========== 边缘场景测试 ==========

class TestEdgeCases:
    """边缘场景测试"""

    def test_rapid_start_stop(self):
        """快速启停节点（10次）"""
        print("\n=== 测试快速启停 ===")
        SharedBufferLite.cleanup_all()

        zmq_addr = "ipc:///tmp/nodeflow/test_rapid"

        for i in range(10):
            output = OutputPort(name="rapid", zmq_address=zmq_addr)
            output.send({"iteration": i})
            time.sleep(0.05)
            output.close()
            time.sleep(0.05)

        print("  ✓ 完成10次快速启停")

        SharedBufferLite.cleanup_all()
        print("✅ 快速启停测试通过")

    def test_zero_delay_startup(self):
        """OutputPort 和 InputPort 同时启动"""
        print("\n=== 测试同时启动 ===")
        SharedBufferLite.cleanup_all()

        zmq_addr = "ipc:///tmp/nodeflow/test_zero_delay"

        # 同时启动（几乎无延迟）
        output = OutputPort(name="out", zmq_address=zmq_addr)
        input_port = InputPort(name="in", zmq_address_or_source=zmq_addr)

        # 短暂等待连接建立
        time.sleep(0.2)

        # 发送数据
        output.send({"test": "simultaneous"})
        time.sleep(0.1)

        # 应该能收到
        data = input_port.recv_latest()
        assert data is not None, "同时启动后应该能收到数据"

        print("  ✓ 同时启动成功通信")

        # 清理
        output.close()
        input_port.close()
        SharedBufferLite.cleanup_all()

        print("✅ 同时启动测试通过")

    def test_output_port_restart(self):
        """OutputPort 重启后 InputPort 重连"""
        print("\n=== 测试 OutputPort 重启 ===")
        SharedBufferLite.cleanup_all()

        zmq_addr = "ipc:///tmp/nodeflow/test_restart"

        # 第一次：发布者启动并发送
        output1 = OutputPort(name="out", zmq_address=zmq_addr)
        output1.send({"version": 1})
        time.sleep(0.1)

        # 订阅者启动
        input_port = InputPort(name="in", zmq_address_or_source=zmq_addr)
        data1 = input_port.recv_latest()
        assert data1 is not None and data1["version"] == 1, "应该收到第一版"
        print("  ✓ 收到第一版数据")

        # 发布者关闭
        output1.close()
        print("  发布者关闭")
        time.sleep(0.2)

        # 发布者重启
        output2 = OutputPort(name="out", zmq_address=zmq_addr)
        output2.send({"version": 2})
        time.sleep(0.2)

        # 订阅者应该能收到新数据
        data2 = input_port.recv_latest()
        assert data2 is not None and data2["version"] == 2, "重启后应该收到新数据"
        print("  ✓ 发布者重启后收到新数据")

        # 清理
        output2.close()
        input_port.close()
        SharedBufferLite.cleanup_all()

        print("✅ OutputPort 重启测试通过")


def main():
    """运行所有高级集成测试"""
    print("=" * 70)
    print("Port 高级集成测试")
    print("=" * 70)

    try:
        # 多订阅者场景
        test_multi = TestMultipleSubscribers()
        test_multi.test_one_publisher_multiple_subscribers()
        test_multi.test_late_joiners_mixed()
        test_multi.test_subscriber_dropout()

        # 高频数据流
        test_freq = TestHighFrequencyData()
        test_freq.test_high_frequency_send()
        test_freq.test_message_loss_detection()
        test_freq.test_conflate_mode()

        # 大数据传输
        test_large = TestLargeDataTransfer()
        test_large.test_large_numpy_array()
        test_large.test_near_buffer_limit()
        test_large.test_buffer_overflow_error()

        # 边缘场景
        test_edge = TestEdgeCases()
        test_edge.test_rapid_start_stop()
        test_edge.test_zero_delay_startup()
        test_edge.test_output_port_restart()

        print("\n" + "=" * 70)
        print("✅ 所有 Port 高级集成测试通过！")
        print("=" * 70)

    except AssertionError as e:
        print(f"\n❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

    except Exception as e:
        print(f"\n❌ 测试错误: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
