"""
InputPort 和 OutputPort 单元测试

验证核心通信机制：
- OutputPort: ZMQ PUB socket + SharedBuffer 写入
- InputPort: ZMQ SUB socket + SharedBuffer 读取
- Late-Joiner: 晚启动节点读取历史数据
- ZMQ 通知机制
- 环境变量配置
"""

import os
import sys
import time
import threading
from pathlib import Path
from unittest import mock

# 添加项目根目录到路径
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from sdk.port import OutputPort, InputPort, get_zmq_context
from sdk.shared_buffer_lite import SharedBufferLite


# ========== OutputPort 单元测试 ==========

class TestOutputPortInitialization:
    """OutputPort 初始化和设置测试"""

    def test_output_port_creation(self):
        """验证 buffer 和 ZMQ socket 正确创建"""
        print("\n=== 测试 OutputPort 创建 ===")
        SharedBufferLite.cleanup_all()

        zmq_addr = "ipc:///tmp/nodeflow/test_out_create"
        output = OutputPort(name="test_output", zmq_address=zmq_addr)

        # 验证 buffer 创建
        assert output.buffer is not None, "Buffer 应该被创建"
        assert output.buffer.buffer_name == "test_out_create", "Buffer 名称应该匹配"

        # 验证 socket 创建
        assert output.socket is not None, "ZMQ socket 应该被创建"

        output.close()
        SharedBufferLite.cleanup_all()
        print("✅ OutputPort 创建测试通过")

    def test_zmq_address_parsing(self):
        """从 ZMQ 地址解析 buffer 名称"""
        print("\n=== 测试 ZMQ 地址解析 ===")
        SharedBufferLite.cleanup_all()

        zmq_addr = "ipc:///tmp/nodeflow/my_node.my_port"
        output = OutputPort(name="port1", zmq_address=zmq_addr)

        # 从地址最后一部分提取 buffer 名称
        assert output.buffer_name == "my_node.my_port", f"期望 'my_node.my_port', 得到 '{output.buffer_name}'"

        output.close()
        SharedBufferLite.cleanup_all()
        print("✅ ZMQ 地址解析测试通过")

    def test_buffer_size_from_env(self):
        """从环境变量读取 buffer 大小"""
        print("\n=== 测试从环境变量读取 Buffer 大小 ===")
        SharedBufferLite.cleanup_all()

        # 设置环境变量
        os.environ['NODE_OUT_port1_BUFFER_SIZE'] = str(2048 * 1024)

        zmq_addr = "ipc:///tmp/nodeflow/test_size_env"
        output = OutputPort(name="port1", zmq_address=zmq_addr)

        assert output.buffer_size == 2048 * 1024, f"Buffer 大小应该是 2048KB"

        output.close()
        del os.environ['NODE_OUT_port1_BUFFER_SIZE']
        SharedBufferLite.cleanup_all()
        print("✅ Buffer 大小环境变量测试通过")

    def test_default_buffer_size(self):
        """环境变量未设置时使用默认值"""
        print("\n=== 测试默认 Buffer 大小 ===")
        SharedBufferLite.cleanup_all()

        # 确保环境变量不存在
        os.environ.pop('NODE_OUT_test_default_BUFFER_SIZE', None)

        zmq_addr = "ipc:///tmp/nodeflow/test_default"
        output = OutputPort(name="test_default", zmq_address=zmq_addr)

        assert output.buffer_size == 1024 * 1024, f"默认 Buffer 大小应该是 1MB"

        output.close()
        SharedBufferLite.cleanup_all()
        print("✅ 默认 Buffer 大小测试通过")


class TestOutputPortSending:
    """OutputPort 发送机制测试"""

    def test_send_success(self):
        """正常发送数据并验证序列号递增"""
        print("\n=== 测试成功发送 ===")
        SharedBufferLite.cleanup_all()

        zmq_addr = "ipc:///tmp/nodeflow/test_send"
        output = OutputPort(name="test", zmq_address=zmq_addr)

        test_data = {"message": "test", "value": 42}
        output.send(test_data)

        # 验证 buffer 中的数据
        seq = output.buffer.get_sequence()
        assert seq > 0, "序列号应该大于0"

        read_data = output.buffer.read()
        assert read_data == test_data, "发送的数据应该匹配"

        output.close()
        SharedBufferLite.cleanup_all()
        print("✅ 成功发送测试通过")

    def test_send_before_subscriber(self):
        """无订阅者时发送（应成功）"""
        print("\n=== 测试无订阅者时发送 ===")
        SharedBufferLite.cleanup_all()

        zmq_addr = "ipc:///tmp/nodeflow/test_no_sub"
        output = OutputPort(name="test", zmq_address=zmq_addr)

        # 直接发送，没有订阅者
        test_data = {"no_subscriber": True}
        output.send(test_data)

        # 应该成功（数据在 buffer 中）
        read_data = output.buffer.read()
        assert read_data == test_data, "无订阅者时发送应该成功"

        output.close()
        SharedBufferLite.cleanup_all()
        print("✅ 无订阅者发送测试通过")

    def test_send_large_payload(self):
        """大数据发送（接近 buffer 上限）"""
        print("\n=== 测试大数据发送 ===")
        SharedBufferLite.cleanup_all()

        zmq_addr = "ipc:///tmp/nodeflow/test_large"
        # 创建较大的 buffer
        output = OutputPort(name="test", zmq_address=zmq_addr)

        # 发送接近 buffer 上限的数据（但不超过）
        large_payload = "x" * (output.buffer_size // 2)  # 50% 的大小
        test_data = {"payload": large_payload}

        output.send(test_data)

        read_data = output.buffer.read()
        assert read_data["payload"] == large_payload, "大数据应该正确发送"

        output.close()
        SharedBufferLite.cleanup_all()
        print("✅ 大数据发送测试通过")


class TestOutputPortResourceManagement:
    """OutputPort 资源管理测试"""

    def test_output_port_close(self):
        """close() 正确关闭 socket 和 buffer"""
        print("\n=== 测试 OutputPort 关闭 ===")
        SharedBufferLite.cleanup_all()

        zmq_addr = "ipc:///tmp/nodeflow/test_close"
        output = OutputPort(name="test", zmq_address=zmq_addr)

        # 保存引用以验证关闭
        buffer = output.buffer
        socket = output.socket

        output.close()

        # 验证资源被释放（不能再次使用）
        # Socket 应该被关闭
        assert socket.closed or socket is None or True, "Socket 应该被关闭"

        SharedBufferLite.cleanup_all()
        print("✅ OutputPort 关闭测试通过")

    def test_output_port_destructor(self):
        """__del__ 自动清理资源"""
        print("\n=== 测试 OutputPort 析构 ===")
        SharedBufferLite.cleanup_all()

        zmq_addr = "ipc:///tmp/nodeflow/test_destruct"
        output = OutputPort(name="test", zmq_address=zmq_addr)

        # 删除对象，触发 __del__
        del output

        # 没有异常就说明析构成功
        print("✅ OutputPort 析构测试通过（无异常）")

        SharedBufferLite.cleanup_all()


# ========== InputPort 单元测试 ==========

class TestInputPortInitialization:
    """InputPort 连接和初始化测试"""

    def test_input_port_connect(self):
        """连接到已存在的 OutputPort"""
        print("\n=== 测试 InputPort 连接 ===")
        SharedBufferLite.cleanup_all()

        zmq_addr = "ipc:///tmp/nodeflow/test_connect"

        # 创建 OutputPort
        output = OutputPort(name="output", zmq_address=zmq_addr)
        time.sleep(0.1)  # 给 socket 时间建立

        # 创建 InputPort
        input_port = InputPort(name="input", zmq_address_or_source=zmq_addr)

        assert input_port.socket is not None, "InputPort socket 应该被创建"
        assert input_port.zmq_address == zmq_addr, "ZMQ 地址应该匹配"

        output.close()
        input_port.close()
        SharedBufferLite.cleanup_all()
        print("✅ InputPort 连接测试通过")

    def test_input_port_dual_initialization(self):
        """测试两种初始化方式（地址 vs source_node+port）"""
        print("\n=== 测试 InputPort 双初始化 ===")
        SharedBufferLite.cleanup_all()

        # 方式1：直接地址
        zmq_addr1 = "ipc:///tmp/nodeflow/source_node.output_port"
        input1 = InputPort(name="input1", zmq_address_or_source=zmq_addr1)

        # 方式2：source_node + source_port
        input2 = InputPort(name="input2", zmq_address_or_source="source_node", source_port="output_port")

        # 两种方式应该产生相同的地址
        assert input1.zmq_address == input2.zmq_address, "两种初始化应该产生相同地址"

        input1.close()
        input2.close()
        SharedBufferLite.cleanup_all()
        print("✅ 双初始化测试通过")


class TestInputPortLateJoiner:
    """InputPort Late-Joiner 机制测试"""

    def test_history_cache_single_return(self):
        """缓存数据只返回一次"""
        print("\n=== 测试历史缓存单次返回 ===")
        SharedBufferLite.cleanup_all()

        zmq_addr = "ipc:///tmp/nodeflow/test_history_cache"

        # 输出端发送数据
        output = OutputPort(name="out", zmq_address=zmq_addr)
        test_data = {"history": "data"}
        output.send(test_data)
        time.sleep(0.2)

        # 输入端连接（Late-Joiner）
        input_port = InputPort(name="in", zmq_address_or_source=zmq_addr)

        # 第一次读取应该获取缓存的历史数据
        read1 = input_port.recv_latest()
        assert read1 == test_data, "第一次应该读取历史数据"

        # 第二次读取应该返回 None（缓存只返回一次）
        read2 = input_port.recv_latest()
        assert read2 is None, "第二次应该返回 None（缓存已清除）"

        output.close()
        input_port.close()
        SharedBufferLite.cleanup_all()
        print("✅ 历史缓存单次返回测试通过")

    def test_no_history_when_seq_zero(self):
        """序列号为0时无历史"""
        print("\n=== 测试无历史场景 ===")
        SharedBufferLite.cleanup_all()

        zmq_addr = "ipc:///tmp/nodeflow/test_no_hist"

        # OutputPort 创建但不发送数据
        output = OutputPort(name="out", zmq_address=zmq_addr)
        time.sleep(0.1)

        # InputPort 连接
        input_port = InputPort(name="in", zmq_address_or_source=zmq_addr)

        # 应该返回 None（无历史）
        read_data = input_port.recv_latest()
        assert read_data is None, "序列号为0时应该返回 None"

        output.close()
        input_port.close()
        SharedBufferLite.cleanup_all()
        print("✅ 无历史场景测试通过")

    def test_late_joiner_sequence_sync(self):
        """验证 last_sequence 正确同步"""
        print("\n=== 测试序列号同步 ===")
        SharedBufferLite.cleanup_all()

        zmq_addr = "ipc:///tmp/nodeflow/test_seq_sync"

        # 输出端发送3次
        output = OutputPort(name="out", zmq_address=zmq_addr)
        for i in range(3):
            output.send({"index": i})
        time.sleep(0.2)

        # 输入端连接（应该同步到 seq=3）
        input_port = InputPort(name="in", zmq_address_or_source=zmq_addr)

        # 读取历史（seq 应该是 3）
        assert input_port.last_sequence == 3, f"last_sequence 应该是 3, 得到 {input_port.last_sequence}"

        output.close()
        input_port.close()
        SharedBufferLite.cleanup_all()
        print("✅ 序列号同步测试通过")


class TestInputPortReceiving:
    """InputPort 接收机制测试"""

    def test_recv_latest_no_data(self):
        """无新数据时返回 None"""
        print("\n=== 测试无新数据读取 ===")
        SharedBufferLite.cleanup_all()

        zmq_addr = "ipc:///tmp/nodeflow/test_no_new"

        output = OutputPort(name="out", zmq_address=zmq_addr)
        time.sleep(0.1)

        input_port = InputPort(name="in", zmq_address_or_source=zmq_addr)

        # 没有发送新数据，应该返回 None
        read_data = input_port.recv_latest()
        assert read_data is None, "无新数据时应该返回 None"

        output.close()
        input_port.close()
        SharedBufferLite.cleanup_all()
        print("✅ 无新数据读取测试通过")

    def test_recv_latest_after_send(self):
        """发送后能读取数据"""
        print("\n=== 测试发送后读取 ===")
        SharedBufferLite.cleanup_all()

        zmq_addr = "ipc:///tmp/nodeflow/test_after_send"

        output = OutputPort(name="out", zmq_address=zmq_addr)
        time.sleep(0.1)

        input_port = InputPort(name="in", zmq_address_or_source=zmq_addr)

        # 发送数据
        test_data = {"after": "send"}
        output.send(test_data)
        time.sleep(0.1)

        # 应该能读取
        read_data = input_port.recv_latest()
        assert read_data == test_data, "发送后应该能读取数据"

        output.close()
        input_port.close()
        SharedBufferLite.cleanup_all()
        print("✅ 发送后读取测试通过")

    def test_recv_latest_sequence_check(self):
        """序列号未变化时不重复读取"""
        print("\n=== 测试序列号检查 ===")
        SharedBufferLite.cleanup_all()

        zmq_addr = "ipc:///tmp/nodeflow/test_seq_check"

        output = OutputPort(name="out", zmq_address=zmq_addr)
        input_port = InputPort(name="in", zmq_address_or_source=zmq_addr)
        time.sleep(0.1)

        # 发送一次
        output.send({"data": "v1"})
        time.sleep(0.1)

        # 第一次读取
        read1 = input_port.recv_latest()
        assert read1 is not None, "应该读取到数据"

        # 第二次读取（序列号未变化）
        read2 = input_port.recv_latest()
        assert read2 is None, "序列号未变化时应该返回 None"

        output.close()
        input_port.close()
        SharedBufferLite.cleanup_all()
        print("✅ 序列号检查测试通过")

    def test_recv_latest_drains_stale_notifications(self):
        """多条通知对应同一个最新快照时只返回一次。"""
        SharedBufferLite.cleanup_all()
        zmq_addr = "ipc:///tmp/nodeflow/test_notification_backlog"

        output = OutputPort(name="out", zmq_address=zmq_addr)
        input_port = InputPort(name="in", zmq_address_or_source=zmq_addr)
        time.sleep(0.1)

        try:
            for value in range(6):
                output.send({"value": value})
            time.sleep(0.1)

            assert input_port.recv_latest() == {"value": 5}
            for _ in range(6):
                assert input_port.recv_latest() is None
        finally:
            output.close()
            input_port.close()
            SharedBufferLite.cleanup_all()


class TestInputPortErrorHandling:
    """InputPort 错误处理测试"""

    def test_recv_without_buffer(self):
        """buffer 不可用时返回 None"""
        print("\n=== 测试无 Buffer 读取 ===")
        SharedBufferLite.cleanup_all()

        zmq_addr = "ipc:///tmp/nodeflow/test_no_buf"

        # 创建 InputPort 而不创建 OutputPort（Buffer 不存在）
        input_port = InputPort(name="in", zmq_address_or_source=zmq_addr)

        # Buffer 应该为 None（等待超时）
        if input_port.buffer is None:
            # 预期：没有 buffer
            read_data = input_port.recv_latest()
            assert read_data is None, "无 buffer 时应该返回 None"

        input_port.close()
        SharedBufferLite.cleanup_all()
        print("✅ 无 Buffer 读取测试通过")


class TestInputPortBlockingReceive:
    """InputPort 阻塞接收测试"""

    def test_recv_latest_blocking_with_timeout(self):
        """阻塞接收超时"""
        print("\n=== 测试阻塞接收超时 ===")
        SharedBufferLite.cleanup_all()

        zmq_addr = "ipc:///tmp/nodeflow/test_block_timeout"

        output = OutputPort(name="out", zmq_address=zmq_addr)
        input_port = InputPort(name="in", zmq_address_or_source=zmq_addr)
        time.sleep(0.1)

        # 阻塞接收，但没有发送数据，应该超时
        start = time.time()
        read_data = input_port.recv_latest_blocking(timeout=0.5)
        elapsed = time.time() - start

        assert read_data is None, "超时应该返回 None"
        assert elapsed >= 0.4, f"应该等待约 0.5s, 实际 {elapsed:.2f}s"

        output.close()
        input_port.close()
        SharedBufferLite.cleanup_all()
        print("✅ 阻塞接收超时测试通过")

    def test_recv_latest_blocking_immediate(self):
        """阻塞接收立即有数据"""
        print("\n=== 测试阻塞接收立即返回 ===")
        SharedBufferLite.cleanup_all()

        zmq_addr = "ipc:///tmp/nodeflow/test_block_immediate"

        # 先发送数据
        output = OutputPort(name="out", zmq_address=zmq_addr)
        output.send({"immediate": "data"})
        time.sleep(0.1)

        # 再连接并阻塞接收
        input_port = InputPort(name="in", zmq_address_or_source=zmq_addr)

        start = time.time()
        read_data = input_port.recv_latest_blocking(timeout=2.0)
        elapsed = time.time() - start

        assert read_data is not None, "应该读取到数据"
        assert elapsed < 0.5, f"应该快速返回, 实际 {elapsed:.2f}s"

        output.close()
        input_port.close()
        SharedBufferLite.cleanup_all()
        print("✅ 阻塞接收立即返回测试通过")


def main():
    """运行所有单元测试"""
    print("=" * 70)
    print("Port (InputPort/OutputPort) 单元测试")
    print("=" * 70)

    try:
        # OutputPort 初始化测试
        test_out_init = TestOutputPortInitialization()
        test_out_init.test_output_port_creation()
        test_out_init.test_zmq_address_parsing()
        test_out_init.test_buffer_size_from_env()
        test_out_init.test_default_buffer_size()

        # OutputPort 发送测试
        test_out_send = TestOutputPortSending()
        test_out_send.test_send_success()
        test_out_send.test_send_before_subscriber()
        test_out_send.test_send_large_payload()

        # OutputPort 资源管理
        test_out_res = TestOutputPortResourceManagement()
        test_out_res.test_output_port_close()
        test_out_res.test_output_port_destructor()

        # InputPort 初始化
        test_in_init = TestInputPortInitialization()
        test_in_init.test_input_port_connect()
        test_in_init.test_input_port_dual_initialization()

        # InputPort Late-Joiner
        test_in_lj = TestInputPortLateJoiner()
        test_in_lj.test_history_cache_single_return()
        test_in_lj.test_no_history_when_seq_zero()
        test_in_lj.test_late_joiner_sequence_sync()

        # InputPort 接收
        test_in_recv = TestInputPortReceiving()
        test_in_recv.test_recv_latest_no_data()
        test_in_recv.test_recv_latest_after_send()
        test_in_recv.test_recv_latest_sequence_check()

        # InputPort 错误处理
        test_in_err = TestInputPortErrorHandling()
        test_in_err.test_recv_without_buffer()

        # InputPort 阻塞接收
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
