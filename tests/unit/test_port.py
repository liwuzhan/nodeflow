"""
InputPort / OutputPort 单元测试（纯 SharedBuffer IPC）

验证核心通信机制：
- OutputPort: SharedBuffer 写入（tombstone 协议保证原子性）
- InputPort:  序列号轮询 + 原子读取
- Late-Joiner: 晚启动节点读取历史数据
- 环境变量配置
"""

import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from sdk.port import OutputPort, InputPort
from sdk.shared_buffer_lite import SharedBufferLite


# ========== OutputPort 单元测试 ==========

class TestOutputPortInitialization:

    def test_output_port_creation(self):
        print("\n=== 测试 OutputPort 创建 ===")
        SharedBufferLite.cleanup_all()
        output = OutputPort(name="test_output", buffer_name="test_out_create")
        assert output.buffer is not None, "Buffer 应该被创建"
        assert output.buffer_name == "test_out_create", "Buffer 名称应该匹配"
        output.close()
        SharedBufferLite.cleanup_all()
        print("✅ OutputPort 创建测试通过")

    def test_buffer_name_direct(self):
        print("\n=== 测试 buffer 名称直接指定 ===")
        SharedBufferLite.cleanup_all()
        output = OutputPort(name="port1", buffer_name="my_node.my_port")
        assert output.buffer_name == "my_node.my_port"
        output.close()
        SharedBufferLite.cleanup_all()
        print("✅ Buffer 名称测试通过")

    def test_buffer_size_from_env(self):
        print("\n=== 测试从环境变量读取 Buffer 大小 ===")
        SharedBufferLite.cleanup_all()
        os.environ['NODE_OUT_port1_BUFFER_SIZE'] = str(2048 * 1024)
        output = OutputPort(name="port1", buffer_name="test_size_env")
        assert output.buffer_size == 2048 * 1024, f"Buffer 大小应该是 2048KB"
        output.close()
        del os.environ['NODE_OUT_port1_BUFFER_SIZE']
        SharedBufferLite.cleanup_all()
        print("✅ Buffer 大小环境变量测试通过")

    def test_default_buffer_size(self):
        print("\n=== 测试默认 Buffer 大小 ===")
        SharedBufferLite.cleanup_all()
        os.environ.pop('NODE_OUT_test_default_BUFFER_SIZE', None)
        output = OutputPort(name="test_default", buffer_name="test_default")
        assert output.buffer_size == 1024 * 1024, f"默认 Buffer 大小应该是 1MB"
        output.close()
        SharedBufferLite.cleanup_all()
        print("✅ 默认 Buffer 大小测试通过")


class TestOutputPortSending:

    def test_send_success(self):
        print("\n=== 测试成功发送 ===")
        SharedBufferLite.cleanup_all()
        output = OutputPort(name="test", buffer_name="test_send")
        test_data = {"message": "test", "value": 42}
        output.send(test_data)
        seq = output.buffer.get_sequence()
        assert seq > 0, "序列号应该大于0"
        read_data = output.buffer.read()
        assert read_data == test_data, "发送的数据应该匹配"
        output.close()
        SharedBufferLite.cleanup_all()
        print("✅ 成功发送测试通过")

    def test_send_large_payload(self):
        print("\n=== 测试大数据发送 ===")
        SharedBufferLite.cleanup_all()
        output = OutputPort(name="test", buffer_name="test_large")
        large_payload = "x" * (output.buffer_size // 2)
        test_data = {"payload": large_payload}
        output.send(test_data)
        read_data = output.buffer.read()
        assert read_data["payload"] == large_payload, "大数据应该正确发送"
        output.close()
        SharedBufferLite.cleanup_all()
        print("✅ 大数据发送测试通过")


class TestOutputPortResourceManagement:

    def test_output_port_close(self):
        print("\n=== 测试 OutputPort 关闭 ===")
        SharedBufferLite.cleanup_all()
        output = OutputPort(name="test", buffer_name="test_close")
        output.close()
        SharedBufferLite.cleanup_all()
        print("✅ OutputPort 关闭测试通过")

    def test_output_port_destructor(self):
        print("\n=== 测试 OutputPort 析构 ===")
        SharedBufferLite.cleanup_all()
        output = OutputPort(name="test", buffer_name="test_destruct")
        del output
        print("✅ OutputPort 析构测试通过（无异常）")
        SharedBufferLite.cleanup_all()


# ========== InputPort 单元测试 ==========

class TestInputPortInitialization:

    def test_input_port_connect_to_existing(self):
        print("\n=== 测试 InputPort 连接已有 Buffer ===")
        SharedBufferLite.cleanup_all()
        output = OutputPort(name="output", buffer_name="test_connect")
        input_port = InputPort(name="input", buffer_name="test_connect")
        assert input_port.buffer is not None, "InputPort buffer 应该被打开"
        assert input_port.is_connected(), "应该处于已连接状态"
        output.close()
        input_port.close()
        SharedBufferLite.cleanup_all()
        print("✅ InputPort 连接测试通过")

    def test_input_port_buffer_name(self):
        print("\n=== 测试 buffer 名称解析 ===")
        SharedBufferLite.cleanup_all()
        output = OutputPort(name="output", buffer_name="source_node.output_port")
        input_port = InputPort(name="input", buffer_name="source_node.output_port")
        assert input_port.source_node == "source_node"
        assert input_port.source_port == "output_port"
        output.close()
        input_port.close()
        SharedBufferLite.cleanup_all()
        print("✅ Buffer 名称解析通过")


class TestInputPortLateJoiner:

    def test_history_cache_single_return(self):
        print("\n=== 测试历史缓存单次返回 ===")
        SharedBufferLite.cleanup_all()
        output = OutputPort(name="out", buffer_name="test_history_cache")
        test_data = {"history": "data"}
        output.send(test_data)
        input_port = InputPort(name="in", buffer_name="test_history_cache")
        read1 = input_port.recv_latest()
        assert read1 == test_data, "第一次应该读取历史数据"
        read2 = input_port.recv_latest()
        assert read2 is None, "第二次应该返回 None（缓存已清除）"
        output.close()
        input_port.close()
        SharedBufferLite.cleanup_all()
        print("✅ 历史缓存单次返回测试通过")

    def test_no_history_when_empty(self):
        print("\n=== 测试空 Buffer 无历史 ===")
        SharedBufferLite.cleanup_all()
        output = OutputPort(name="out", buffer_name="test_no_hist")
        input_port = InputPort(name="in", buffer_name="test_no_hist")
        read_data = input_port.recv_latest()
        assert read_data is None, "空 buffer 时应该返回 None"
        output.close()
        input_port.close()
        SharedBufferLite.cleanup_all()
        print("✅ 无历史场景测试通过")

    def test_late_joiner_sequence_sync(self):
        print("\n=== 测试序列号同步 ===")
        SharedBufferLite.cleanup_all()
        output = OutputPort(name="out", buffer_name="test_seq_sync")
        for i in range(3):
            output.send({"index": i})
        input_port = InputPort(name="in", buffer_name="test_seq_sync")
        assert input_port.last_sequence == 3, f"last_sequence 应该是 3, 得到 {input_port.last_sequence}"
        output.close()
        input_port.close()
        SharedBufferLite.cleanup_all()
        print("✅ 序列号同步测试通过")


class TestInputPortReceiving:

    def test_recv_latest_no_data(self):
        print("\n=== 测试无新数据读取 ===")
        SharedBufferLite.cleanup_all()
        output = OutputPort(name="out", buffer_name="test_no_new")
        input_port = InputPort(name="in", buffer_name="test_no_new")
        read_data = input_port.recv_latest()
        assert read_data is None, "无新数据时应该返回 None"
        output.close()
        input_port.close()
        SharedBufferLite.cleanup_all()
        print("✅ 无新数据读取测试通过")

    def test_recv_latest_after_send(self):
        print("\n=== 测试发送后读取 ===")
        SharedBufferLite.cleanup_all()
        output = OutputPort(name="out", buffer_name="test_after_send")
        input_port = InputPort(name="in", buffer_name="test_after_send")
        test_data = {"after": "send"}
        output.send(test_data)
        read_data = input_port.recv_latest()
        assert read_data == test_data, "发送后应该能读取数据"
        output.close()
        input_port.close()
        SharedBufferLite.cleanup_all()
        print("✅ 发送后读取测试通过")

    def test_recv_latest_sequence_check(self):
        print("\n=== 测试序列号检查 ===")
        SharedBufferLite.cleanup_all()
        output = OutputPort(name="out", buffer_name="test_seq_check")
        input_port = InputPort(name="in", buffer_name="test_seq_check")
        output.send({"data": "v1"})
        read1 = input_port.recv_latest()
        assert read1 is not None, "应该读取到数据"
        read2 = input_port.recv_latest()
        assert read2 is None, "序列号未变化时应该返回 None"
        output.close()
        input_port.close()
        SharedBufferLite.cleanup_all()
        print("✅ 序列号检查测试通过")

    def test_rapid_sends_only_latest(self):
        """快速连续发送时只读到最新值"""
        SharedBufferLite.cleanup_all()
        output = OutputPort(name="out", buffer_name="test_notification_backlog")
        input_port = InputPort(name="in", buffer_name="test_notification_backlog")
        try:
            for v in range(10):
                output.send({"value": v})
            assert input_port.recv_latest() == {"value": 9}
            for _ in range(5):
                assert input_port.recv_latest() is None
        finally:
            output.close()
            input_port.close()
            SharedBufferLite.cleanup_all()
        print("✅ 快速连续发送测试通过")


class TestInputPortErrorHandling:

    def test_recv_without_buffer(self):
        print("\n=== 测试无 Buffer 读取 ===")
        SharedBufferLite.cleanup_all()
        input_port = InputPort(name="in", buffer_name="test_nonexistent")
        if input_port.buffer is None:
            read_data = input_port.recv_latest()
            assert read_data is None, "无 buffer 时应该返回 None"
        input_port.close()
        SharedBufferLite.cleanup_all()
        print("✅ 无 Buffer 读取测试通过")


class TestInputPortBlockingReceive:

    def test_recv_latest_blocking_with_timeout(self):
        print("\n=== 测试阻塞接收超时 ===")
        SharedBufferLite.cleanup_all()
        output = OutputPort(name="out", buffer_name="test_block_timeout")
        input_port = InputPort(name="in", buffer_name="test_block_timeout")
        start = time.time()
        read_data = input_port.recv_latest_blocking(timeout=0.3)
        elapsed = time.time() - start
        assert read_data is None, "超时应该返回 None"
        assert elapsed >= 0.25, f"应该等待约 0.3s, 实际 {elapsed:.2f}s"
        output.close()
        input_port.close()
        SharedBufferLite.cleanup_all()
        print("✅ 阻塞接收超时测试通过")

    def test_recv_latest_blocking_immediate(self):
        print("\n=== 测试阻塞接收立即返回 ===")
        SharedBufferLite.cleanup_all()
        output = OutputPort(name="out", buffer_name="test_block_immediate")
        output.send({"immediate": "data"})
        input_port = InputPort(name="in", buffer_name="test_block_immediate")
        start = time.time()
        read_data = input_port.recv_latest_blocking(timeout=2.0)
        elapsed = time.time() - start
        assert read_data is not None, "应该读取到数据"
        assert elapsed < 0.1, f"应该快速返回, 实际 {elapsed:.3f}s"
        output.close()
        input_port.close()
        SharedBufferLite.cleanup_all()
        print("✅ 阻塞接收立即返回测试通过")


def main():
    print("=" * 70)
    print("Port (InputPort/OutputPort) 单元测试")
    print("=" * 70)

    try:
        test_out_init = TestOutputPortInitialization()
        test_out_init.test_output_port_creation()
        test_out_init.test_buffer_name_direct()
        test_out_init.test_buffer_size_from_env()
        test_out_init.test_default_buffer_size()

        test_out_send = TestOutputPortSending()
        test_out_send.test_send_success()
        test_out_send.test_send_large_payload()

        test_out_res = TestOutputPortResourceManagement()
        test_out_res.test_output_port_close()
        test_out_res.test_output_port_destructor()

        test_in_init = TestInputPortInitialization()
        test_in_init.test_input_port_connect_to_existing()
        test_in_init.test_input_port_buffer_name()

        test_in_lj = TestInputPortLateJoiner()
        test_in_lj.test_history_cache_single_return()
        test_in_lj.test_no_history_when_empty()
        test_in_lj.test_late_joiner_sequence_sync()

        test_in_recv = TestInputPortReceiving()
        test_in_recv.test_recv_latest_no_data()
        test_in_recv.test_recv_latest_after_send()
        test_in_recv.test_recv_latest_sequence_check()
        test_in_recv.test_rapid_sends_only_latest()

        test_in_err = TestInputPortErrorHandling()
        test_in_err.test_recv_without_buffer()

        test_in_block = TestInputPortBlockingReceive()
        test_in_block.test_recv_latest_blocking_with_timeout()
        test_in_block.test_recv_latest_blocking_immediate()

        print("\n" + "=" * 70)
        print("✅ 所有 Port 单元测试通过！")
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
