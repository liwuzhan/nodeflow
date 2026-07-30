"""
SharedBufferLite 单元测试

验证共享缓冲区的核心功能：
- 序列号管理（单调递增、回绕）
- 数据持久化（读写、大小限制）
- 并发安全性（多进程/线程）
- 文件系统交互（创建、清理、权限）
- MsgPack 序列化（基础类型、numpy）
"""

import os
import sys
import time
import struct
import tempfile
import threading
import multiprocessing
from pathlib import Path
from unittest import mock

import pytest

# 添加项目根目录到路径
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from sdk.shared_buffer_lite import SharedBufferLite

try:
    import numpy as np
    HAS_NUMPY = True
except ImportError:
    HAS_NUMPY = False


class _PausingMmap:
    def __init__(self, backing, write_started, finish_write):
        self._backing = backing
        self._write_started = write_started
        self._finish_write = finish_write
        self._paused = False

    def __getitem__(self, key):
        return self._backing[key]

    def __setitem__(self, key, value):
        if (
            not self._paused
            and isinstance(key, slice)
            and key.start == SharedBufferLite.HEADER_SIZE
            and len(value) > 1
        ):
            self._paused = True
            midpoint = len(value) // 2
            self._backing[key.start:key.start + midpoint] = value[:midpoint]
            self._write_started.set()
            self._finish_write.wait(timeout=5)
            self._backing[key.start + midpoint:key.stop] = value[midpoint:]
            return
        self._backing[key] = value

    def flush(self):
        return self._backing.flush()


class _FailingMmap:
    def __init__(self, backing):
        self._backing = backing

    def __getitem__(self, key):
        return self._backing[key]

    def __setitem__(self, key, value):
        if isinstance(key, slice) and key.start == SharedBufferLite.HEADER_SIZE:
            midpoint = len(value) // 2
            self._backing[key.start:key.start + midpoint] = value[:midpoint]
            raise OSError("simulated writer failure")
        self._backing[key] = value

    def flush(self):
        return self._backing.flush()


def _write_with_pause(buffer_name, size, payload, write_started, finish_write):
    buffer = SharedBufferLite(buffer_name, size=size, create=False)
    backing = buffer.mmap
    try:
        buffer.mmap = _PausingMmap(backing, write_started, finish_write)
        buffer.write(payload)
    finally:
        buffer.mmap = backing
        buffer.close()


# ========== 测试类 ==========

class TestSequenceNumberManagement:
    """序列号管理测试"""

    def test_sequence_increment(self):
        """验证序列号单调递增"""
        print("\n=== 测试序列号递增 ===")
        SharedBufferLite.cleanup_all()
        buffer = SharedBufferLite("test_seq_inc", size=1024*1024, create=True)

        # 写入5次数据，验证序列号递增
        sequences = []
        for i in range(5):
            data = {"index": i, "value": i * 10}
            seq = buffer.write(data)
            sequences.append(seq)
            print(f"  写入 {i}: seq={seq}")

        # 验证序列号严格递增
        for i in range(1, len(sequences)):
            assert sequences[i] > sequences[i-1], f"序列号应该递增: {sequences[i-1]} < {sequences[i]}"

        # 验证与 get_sequence() 结果一致
        final_seq = buffer.get_sequence()
        assert final_seq == sequences[-1], f"最终序列号应该是 {sequences[-1]}, 得到 {final_seq}"

        buffer.close()
        SharedBufferLite.cleanup_all()
        print("✅ 序列号递增测试通过")

    def test_sequence_wraparound(self):
        """验证 uint32 溢出回绕 (0xFFFFFFFF → 0)"""
        print("\n=== 测试序列号回绕 ===")
        SharedBufferLite.cleanup_all()
        buffer = SharedBufferLite("test_seq_wrap", size=1024*1024, create=True)

        # 模拟序列号接近溢出：设置初始值为 0xFFFFFFFD
        with open(buffer.buffer_path, 'r+b') as f:
            with open(f.fileno(), 'r+b', closefd=False) as mmap_file:
                # 写入 0xFFFFFFFD 到前4字节
                mmap_file.seek(0)
                mmap_file.write(struct.pack('<I', 0xFFFFFFFD))

        buffer = SharedBufferLite("test_seq_wrap", size=1024*1024, create=False)

        # 进行多次写入，触发溢出
        data1 = {"test": 1}
        seq1 = buffer.write(data1)  # 应该是 0xFFFFFFFE

        data2 = {"test": 2}
        seq2 = buffer.write(data2)  # 应该是 0xFFFFFFFF

        data3 = {"test": 3}
        seq3 = buffer.write(data3)  # 应该是 0 (回绕)

        print(f"  seq1 (0xFFFFFFFD+1): {seq1:#x}")
        print(f"  seq2 (0xFFFFFFFE+1): {seq2:#x}")
        print(f"  seq3 (0xFFFFFFFF+1): {seq3:#x}")

        assert seq1 == 0xFFFFFFFE, f"预期 0xFFFFFFFE, 得到 {seq1:#x}"
        assert seq2 == 0xFFFFFFFF, f"预期 0xFFFFFFFF, 得到 {seq2:#x}"
        assert seq3 == 0, f"预期 0 (回绕), 得到 {seq3:#x}"
        assert buffer.read() == data3, "回绕到序列号 0 后最新数据仍应可读"

        buffer.close()
        SharedBufferLite.cleanup_all()
        print("✅ 序列号回绕测试通过")

    def test_concurrent_sequence(self):
        """多线程并发写入时序列号正确性（使用threading测试原子性）"""
        print("\n=== 测试并发序列号 ===")
        SharedBufferLite.cleanup_all()

        # 创建 buffer
        buffer = SharedBufferLite("test_concurrent_seq", size=10*1024*1024, create=True)

        # 用于收集结果的线程安全列表
        all_seqs = []
        lock = threading.Lock()

        def thread_writer(thread_id, num_writes):
            """线程：写入多条数据并记录序列号"""
            for i in range(num_writes):
                data = {"thread": thread_id, "index": i}
                seq = buffer.write(data)
                with lock:
                    all_seqs.append(seq)

        # 启动5个线程，每个写入20条数据
        threads = []
        num_threads = 5
        writes_per_thread = 20

        for i in range(num_threads):
            t = threading.Thread(target=thread_writer, args=(i, writes_per_thread))
            t.start()
            threads.append(t)

        for t in threads:
            t.join(timeout=30)

        print(f"  总写入: {len(all_seqs)} 条数据")
        print(f"  序列号范围: {min(all_seqs)} - {max(all_seqs)}")

        # 验证所有序列号不重复
        assert len(all_seqs) == num_threads * writes_per_thread, f"序列号计数错误"
        assert len(set(all_seqs)) == len(all_seqs), f"存在重复的序列号"

        # 验证序列号为连续的
        sorted_seqs = sorted(all_seqs)
        assert sorted_seqs == list(range(1, len(all_seqs) + 1)), f"序列号应该连续"

        buffer.close()
        SharedBufferLite.cleanup_all()
        print("✅ 并发序列号测试通过")


class TestBoundaryConditions:
    """边界条件测试"""

    def test_buffer_size_limit(self):
        """数据超过 buffer 容量时抛出 ValueError"""
        print("\n=== 测试 Buffer 大小限制 ===")
        SharedBufferLite.cleanup_all()

        # 创建小 buffer (仅 1KB)
        small_size = 1024
        buffer = SharedBufferLite("test_size_limit", size=small_size, create=True)

        # 尝试写入超大数据
        large_data = {"payload": "x" * (small_size + 1000)}

        try:
            buffer.write(large_data)
            assert False, "应该抛出 ValueError"
        except ValueError as e:
            print(f"  ✓ 正确抛出异常: {e}")
            assert "too large" in str(e).lower() or "data too large" in str(e).lower()

        buffer.close()
        SharedBufferLite.cleanup_all()
        print("✅ Buffer 大小限制测试通过")

    def test_empty_buffer_read(self):
        """未写入过数据时 read() 返回 None"""
        print("\n=== 测试空 Buffer 读取 ===")
        SharedBufferLite.cleanup_all()
        buffer = SharedBufferLite("test_empty", size=1024*1024, create=True)

        # 立即读取，不写入任何数据
        data = buffer.read()
        assert data is None, f"空 buffer 应该返回 None, 得到 {data}"

        # 验证序列号为 0
        seq = buffer.get_sequence()
        assert seq == 0, f"空 buffer 序列号应该是 0, 得到 {seq}"

        buffer.close()
        SharedBufferLite.cleanup_all()
        print("✅ 空 Buffer 读取测试通过")

    def test_header_only_buffer(self):
        """buffer 仅包含 header 时的处理"""
        print("\n=== 测试仅 Header Buffer ===")
        SharedBufferLite.cleanup_all()
        buffer = SharedBufferLite("test_header", size=1024*1024, create=True)

        # 手动写入有效的 header（序列号为1，数据长度为0）
        with open(buffer.buffer_path, 'r+b') as f:
            import mmap
            with mmap.mmap(f.fileno(), buffer.size) as m:
                m[0:4] = struct.pack('<I', 1)      # 序列号 = 1
                m[4:8] = struct.pack('<I', 0)      # 数据长度 = 0
                m.flush()

        buffer = SharedBufferLite("test_header", size=1024*1024, create=False)
        data = buffer.read()
        # 数据长度为0时应该返回None
        assert data is None, f"长度为0的数据应该返回 None"

        buffer.close()
        SharedBufferLite.cleanup_all()
        print("✅ 仅 Header Buffer 测试通过")

    def test_corrupted_length(self):
        """length 字段损坏时的错误处理"""
        print("\n=== 测试损坏的 Length 字段 ===")
        SharedBufferLite.cleanup_all()
        buffer = SharedBufferLite("test_corrupt", size=1024*1024, create=True)

        # 先正常写入数据
        buffer.write({"test": "data"})

        # 损坏 length 字段（设置为超大值）
        with open(buffer.buffer_path, 'r+b') as f:
            import mmap
            with mmap.mmap(f.fileno(), buffer.size) as m:
                m[4:8] = struct.pack('<I', buffer.size + 1000)  # 超过 buffer 大小
                m.flush()

        buffer = SharedBufferLite("test_corrupt", size=1024*1024, create=False)
        data = buffer.read()
        # 应该返回 None（无效数据）
        assert data is None, f"损坏的长度字段应该返回 None, 得到 {data}"

        buffer.close()
        SharedBufferLite.cleanup_all()
        print("✅ 损坏 Length 字段测试通过")


class TestConcurrencySafety:
    """并发安全性测试"""

    def test_concurrent_write(self):
        """多线程并发写入"""
        print("\n=== 测试并发写入 ===")
        SharedBufferLite.cleanup_all()

        # 创建 buffer
        buffer = SharedBufferLite("test_concurrent_write", size=10*1024*1024, create=True)

        def thread_writer(thread_id):
            """线程：执行多次写入"""
            for i in range(20):
                data = {"thread": thread_id, "iter": i, "value": thread_id * 100 + i}
                buffer.write(data)
                time.sleep(0.0001)

        # 启动5个线程并发写入
        threads = []
        for i in range(5):
            t = threading.Thread(target=thread_writer, args=(i,))
            t.start()
            threads.append(t)

        for t in threads:
            t.join(timeout=30)

        # 验证最终序列号
        final_seq = buffer.get_sequence()
        expected = 5 * 20

        assert final_seq == expected, f"最终序列号应该是 {expected}, 得到 {final_seq}"
        print(f"  最终序列号: {final_seq} (5 threads × 20 writes)")

        buffer.close()
        SharedBufferLite.cleanup_all()
        print(f"✅ 并发写入测试通过")

    def test_read_during_write(self):
        """读写同时进行时的数据完整性"""
        print("\n=== 测试并发读写 ===")
        SharedBufferLite.cleanup_all()

        # 创建 buffer
        buffer = SharedBufferLite("test_read_write", size=10*1024*1024, create=True)

        # 共享结果
        results = {'read_count': 0}
        results_lock = threading.Lock()

        def writer():
            """持续写入数据"""
            for i in range(50):
                data = {"index": i, "payload": "x" * 1000}
                buffer.write(data)
                time.sleep(0.01)

        def reader():
            """持续读取数据"""
            time.sleep(0.05)  # 等待第一个写入
            read_count = 0
            for _ in range(30):
                data = buffer.read()
                if data is not None:
                    read_count += 1
                time.sleep(0.015)
            with results_lock:
                results['read_count'] = read_count

        # 启动读写线程
        t_write = threading.Thread(target=writer)
        t_read = threading.Thread(target=reader)

        t_write.start()
        t_read.start()

        t_write.join(timeout=10)
        t_read.join(timeout=10)

        # 验证读取成功
        read_count = results['read_count']
        print(f"  成功读取 {read_count} 次")
        assert read_count > 0, f"应该能读取数据"

        buffer.close()
        SharedBufferLite.cleanup_all()
        print("✅ 并发读写测试通过")

    def test_cross_process_reader_never_observes_partial_write(self):
        """Tombstone 协议（length=0）防止读者读到半写数据"""
        SharedBufferLite.cleanup_all()
        buffer_name = "test_cross_process_snapshot"
        size = 2 * 1024 * 1024
        initial = {"payload": b"A" * (512 * 1024)}
        updated = {"payload": b"B" * (512 * 1024)}

        writer_buffer = SharedBufferLite(buffer_name, size=size, create=True)
        writer_buffer.write(initial)
        reader_buffer = SharedBufferLite(buffer_name, size=size, create=False)

        ctx = multiprocessing.get_context("spawn")
        write_started = ctx.Event()
        finish_write = ctx.Event()
        process = ctx.Process(
            target=_write_with_pause,
            args=(buffer_name, size, updated, write_started, finish_write),
        )
        process.start()

        read_done = threading.Event()
        result = {}

        def read_snapshot():
            result["data"] = reader_buffer.read()
            read_done.set()

        try:
            assert write_started.wait(timeout=5), "writer did not reach partial-write point"
            reader_thread = threading.Thread(target=read_snapshot)
            reader_thread.start()

            # tombstone 协议：写进程在写数据前已设 length=0，
            # 因此读者应能立即返回 None（而不是读到半写数据）
            assert read_done.wait(timeout=1.0), "reader should return immediately (tombstone protection)"
            assert result["data"] is None, "reader should see None during partial write (tombstone)"
            finish_write.set()

            reader_thread.join(timeout=5)
            process.join(timeout=5)
            assert not reader_thread.is_alive()
            assert process.exitcode == 0

            # 写完成后，读者应能读到完整的最新数据
            final_data = reader_buffer.read()
            assert final_data == updated, f"reader should get full data after write completes"
        finally:
            finish_write.set()
            if process.is_alive():
                process.terminate()
                process.join(timeout=2)
            reader_buffer.close()
            writer_buffer.close()
            SharedBufferLite.cleanup_all()

    def test_failed_write_leaves_no_readable_partial_snapshot(self):
        SharedBufferLite.cleanup_all()
        buffer = SharedBufferLite("test_failed_snapshot", size=1024 * 1024, create=True)
        buffer.write({"payload": b"A" * 1024})
        backing = buffer.mmap

        try:
            buffer.mmap = _FailingMmap(backing)
            with pytest.raises(OSError, match="simulated writer failure"):
                buffer.write({"payload": b"B" * 1024})
        finally:
            buffer.mmap = backing

        try:
            assert buffer.read() is None
        finally:
            buffer.close()
            SharedBufferLite.cleanup_all()

    def test_mmap_flush_consistency(self):
        """flush() 后数据立即可读"""
        print("\n=== 测试 mmap flush 一致性 ===")
        SharedBufferLite.cleanup_all()

        def writer_flush_test():
            """写入并立即 flush"""
            buffer = SharedBufferLite("test_flush", size=1024*1024, create=True)
            data = {"test": "flush_data", "value": 12345}
            seq = buffer.write(data)  # write() 内部调用 flush()
            buffer.close()
            return seq

        def reader_verify_test(seq):
            """验证数据立即可读"""
            time.sleep(0.1)  # 短暂延迟
            buffer = SharedBufferLite("test_flush", size=1024*1024, create=False)
            data = buffer.read()
            buffer.close()
            return data

        seq = writer_flush_test()
        data = reader_verify_test(seq)

        assert data is not None, "flush 后数据应该立即可读"
        assert data["value"] == 12345, f"数据值错误: {data}"

        SharedBufferLite.cleanup_all()
        print("✅ mmap flush 一致性测试通过")


class TestFileSystemInteraction:
    """文件系统交互测试"""

    def test_buffer_creation(self):
        """验证 /tmp/nodeflow/buffers/ 目录创建"""
        print("\n=== 测试 Buffer 目录创建 ===")
        SharedBufferLite.cleanup_all()

        # 删除目录确保测试从干净状态开始
        buffer_dir = Path("/tmp/nodeflow/buffers")
        if buffer_dir.exists():
            import shutil
            shutil.rmtree(buffer_dir)

        # 创建 buffer 应该自动创建目录
        buffer = SharedBufferLite("test_dir_create", size=1024*1024, create=True)

        # 验证目录存在
        assert buffer_dir.exists(), f"目录 {buffer_dir} 应该存在"
        assert (buffer_dir / "test_dir_create.buf").exists(), f"Buffer 文件应该存在"

        buffer.close()
        SharedBufferLite.cleanup_all()
        print("✅ Buffer 目录创建测试通过")

    def test_buffer_reopening(self):
        """关闭后重新打开 buffer 数据仍在"""
        print("\n=== 测试 Buffer 重新打开 ===")
        SharedBufferLite.cleanup_all()

        # 第一次：创建并写入
        buffer1 = SharedBufferLite("test_reopen", size=1024*1024, create=True)
        test_data = {"message": "persistent data", "number": 42}
        seq1 = buffer1.write(test_data)
        buffer1.close()

        print(f"  第一次写入: seq={seq1}, data={test_data}")

        # 第二次：重新打开并读取
        buffer2 = SharedBufferLite("test_reopen", size=1024*1024, create=False)
        seq2 = buffer2.get_sequence()
        data2 = buffer2.read()

        print(f"  重新打开: seq={seq2}, data={data2}")

        assert seq2 == seq1, f"序列号应该一致: {seq1} vs {seq2}"
        assert data2 == test_data, f"数据应该一致"

        buffer2.close()
        SharedBufferLite.cleanup_all()
        print("✅ Buffer 重新打开测试通过")

    def test_cleanup_all(self):
        """cleanup_all() 清理所有 buffer 文件"""
        print("\n=== 测试 cleanup_all ===")
        SharedBufferLite.cleanup_all()

        # 创建多个 buffer
        buffer_dir = Path("/tmp/nodeflow/buffers")
        buffer_dir.mkdir(parents=True, exist_ok=True)

        for i in range(5):
            buf = SharedBufferLite(f"test_cleanup_{i}", size=1024*1024, create=True)
            buf.write({"test": i})
            buf.close()

        # 验证文件存在
        buf_files = list(buffer_dir.glob("test_cleanup_*.buf"))
        assert len(buf_files) == 5, f"应该有5个 buffer 文件，得到 {len(buf_files)}"

        print(f"  清理前: {len(buf_files)} 个 buffer 文件")

        # 清理
        SharedBufferLite.cleanup_all()

        # 验证文件被删除
        buf_files = list(buffer_dir.glob("test_cleanup_*.buf"))
        assert len(buf_files) == 0, f"cleanup 后不应该有 buffer 文件，得到 {len(buf_files)}"

        print(f"  清理后: {len(buf_files)} 个 buffer 文件")
        print("✅ cleanup_all 测试通过")

    def test_permission_denied(self):
        """无写权限时的错误处理"""
        print("\n=== 测试权限限制 ===")
        SharedBufferLite.cleanup_all()

        buffer = SharedBufferLite("test_perm", size=1024*1024, create=True)
        buffer.write({"test": "data"})
        buffer.close()

        # 移除文件写权限
        buffer_path = Path("/tmp/nodeflow/buffers/test_perm.buf")
        original_mode = os.stat(buffer_path).st_mode
        os.chmod(buffer_path, 0o444)  # 只读权限

        # 尝试打开以写模式访问
        try:
            try:
                buffer = SharedBufferLite("test_perm", size=1024*1024, create=False)
                buffer.close()
                # 如果到这里，权限限制可能被忽略了（在某些系统如 macOS 上）
                print("  ⚠️ 权限限制未生效（可能在 macOS 或某些系统上的系统设置导致）")
            except (PermissionError, OSError) as e:
                # 预期会失败
                print(f"  ✓ 打开被正确拒绝: {type(e).__name__}")
        finally:
            # 恢复权限以便清理
            os.chmod(buffer_path, original_mode)

        SharedBufferLite.cleanup_all()
        print("✅ 权限限制测试通过")


class TestDataSerialization:
    """数据序列化测试（验证 MsgPack 编解码）"""

    def test_basic_types_serialization(self):
        """基础数据类型序列化"""
        print("\n=== 测试基础类型序列化 ===")
        SharedBufferLite.cleanup_all()
        buffer = SharedBufferLite("test_serialize", size=1024*1024, create=True)

        test_data = {
            "string": "hello",
            "integer": 42,
            "float": 3.14,
            "bool": True,
            "null": None,
            "list": [1, 2, 3],
            "nested": {"key": "value"}
        }

        buffer.write(test_data)
        read_data = buffer.read()

        assert read_data == test_data, f"数据序列化失败"

        buffer.close()
        SharedBufferLite.cleanup_all()
        print("✅ 基础类型序列化测试通过")

    def test_bytes_serialization(self):
        """bytes 类型序列化"""
        print("\n=== 测试 Bytes 序列化 ===")
        SharedBufferLite.cleanup_all()
        buffer = SharedBufferLite("test_bytes", size=1024*1024, create=True)

        test_data = {
            "binary": b"binary data",
            "mixed": {
                "text": "string",
                "bytes": b"bytes"
            }
        }

        buffer.write(test_data)
        read_data = buffer.read()

        assert read_data == test_data, f"Bytes 序列化失败"

        buffer.close()
        SharedBufferLite.cleanup_all()
        print("✅ Bytes 序列化测试通过")

    def test_numpy_serialization(self):
        """NumPy 数组序列化"""
        if not HAS_NUMPY:
            print("\n⊘ 跳过 NumPy 序列化测试（NumPy 未安装）")
            return

        print("\n=== 测试 NumPy 序列化 ===")
        SharedBufferLite.cleanup_all()
        buffer = SharedBufferLite("test_numpy", size=10*1024*1024, create=True)

        test_array = np.array([1.0, 2.5, 3.14159], dtype=np.float32)
        test_data = {
            "array": test_array,
            "metadata": {"shape": test_array.shape, "dtype": str(test_array.dtype)}
        }

        buffer.write(test_data)
        read_data = buffer.read()

        assert isinstance(read_data["array"], np.ndarray), "应该是 numpy 数组"
        assert read_data["array"].dtype == np.float32, "dtype 应该保留"
        assert np.allclose(read_data["array"], test_array), "数组值应该匹配"

        buffer.close()
        SharedBufferLite.cleanup_all()
        print("✅ NumPy 序列化测试通过")


def main():
    """运行所有单元测试"""
    print("=" * 70)
    print("SharedBufferLite 单元测试")
    print("=" * 70)

    try:
        # 序列号管理测试
        test_seq = TestSequenceNumberManagement()
        test_seq.test_sequence_increment()
        test_seq.test_sequence_wraparound()
        test_seq.test_concurrent_sequence()

        # 边界条件测试
        test_boundary = TestBoundaryConditions()
        test_boundary.test_buffer_size_limit()
        test_boundary.test_empty_buffer_read()
        test_boundary.test_header_only_buffer()
        test_boundary.test_corrupted_length()

        # 并发安全性测试
        test_concurrent = TestConcurrencySafety()
        test_concurrent.test_concurrent_write()
        test_concurrent.test_read_during_write()
        test_concurrent.test_mmap_flush_consistency()

        # 文件系统交互测试
        test_fs = TestFileSystemInteraction()
        test_fs.test_buffer_creation()
        test_fs.test_buffer_reopening()
        test_fs.test_cleanup_all()
        test_fs.test_permission_denied()

        # 数据序列化测试
        test_serialize = TestDataSerialization()
        test_serialize.test_basic_types_serialization()
        test_serialize.test_bytes_serialization()
        test_serialize.test_numpy_serialization()

        print("\n" + "=" * 70)
        print("✅ 所有 SharedBufferLite 单元测试通过！")
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
