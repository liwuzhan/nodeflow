"""
GPT review findings 修复验证测试

覆盖:
1. 完整 header 检查（seqlock 升级版）
2. 心跳 buffer 复用 + 日志级别
3. Health stale 检测 + interval 契约
"""

import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from edge.sdk.shared_buffer_lite import SharedBufferLite
from edge.sdk.port import OutputPort, InputPort


class TestFullHeaderSeqlock:
    """验证 read_with_sequence 比较完整 8 字节 header"""

    def test_old_data_returns_correctly(self):
        SharedBufferLite.cleanup_all()
        w = SharedBufferLite("test_hdr_old", size=1024 * 1024, create=True)
        r = SharedBufferLite("test_hdr_old", size=1024 * 1024, create=False)

        w.write({"gen": "old"})
        seq, data = r.read_with_sequence(5)
        assert data is not None
        assert data["gen"] == "old"

        r.close()
        w.close()
        SharedBufferLite.cleanup_all()

    def test_mid_write_tombstone_returns_none(self):
        """模拟写入中途：data 已写但 header 未完成 → 返回 None"""
        import struct, msgpack
        SharedBufferLite.cleanup_all()
        w = SharedBufferLite("test_hdr_mid", size=1024 * 1024, create=True)
        r = SharedBufferLite("test_hdr_mid", size=1024 * 1024, create=False)

        # 写一帧正常数据
        w.write({"gen": "old"})
        seq1, d1 = r.read_with_sequence(5)
        assert d1["gen"] == "old"

        # 模拟写入中途：写新 payload 但不更新 seq/length
        new_bytes = msgpack.packb({"gen": "new"}, use_bin_type=True)
        with w._lock:
            w.mmap[4:8] = struct.pack('<I', 0)  # tombstone
            w.mmap.flush()
            w.mmap[8:8 + len(new_bytes)] = new_bytes
            # 故意不写 seq 和 length——模拟 writer 在中途暂停

        seq2, d2 = r.read_with_sequence(5)
        # 应返回 None（tombstone 或 header 不匹配）
        assert d2 is None, f"mid-write should return None, got {d2}"

        # 完成写入
        with w._lock:
            w.mmap[0:4] = struct.pack('<I', 2)
            w.mmap[4:8] = struct.pack('<I', len(new_bytes))
            w.mmap.flush()

        seq3, d3 = r.read_with_sequence(5)
        assert d3["gen"] == "new"

        r.close()
        w.close()
        SharedBufferLite.cleanup_all()

    def test_sequence_strictly_increasing(self):
        SharedBufferLite.cleanup_all()
        w = SharedBufferLite("test_hdr_seq", size=1024 * 1024, create=True)
        r = SharedBufferLite("test_hdr_seq", size=1024 * 1024, create=False)

        last_seq = 0
        for i in range(100):
            w.write({"idx": i})
            seq, data = r.read_with_sequence(5)
            assert data["idx"] == i
            assert seq > last_seq, f"seq regression: {seq} <= {last_seq}"
            last_seq = seq

        r.close()
        w.close()
        SharedBufferLite.cleanup_all()


class TestHealthHeartbeat:
    """验证心跳 buffer 复用和 interval 契约"""

    def test_health_data_contains_interval(self):
        os.environ["NODE_ID"] = "test_hb_node"
        os.environ["NODE_OUT_test"] = "test_hb_node.test"
        from edge.sdk.nodeflow_sdk import NodeFlowSDK

        sdk = NodeFlowSDK(enable_parent_watchdog=False)
        sdk.create_output_port("test")
        time.sleep(0.3)  # 等心跳触发

        buf = SharedBufferLite("test_hb_node.health", create=False)
        data = buf.read()
        buf.close()

        assert data is not None, "health buffer should have data"
        assert "heartbeat_interval" in data, "health data must include heartbeat_interval"
        assert data["heartbeat_interval"] >= 0.5
        assert data["status"] == "ok"
        assert "timestamp" in data
        assert "inputs" in data
        assert "outputs" in data

        sdk.shutdown()
        SharedBufferLite.cleanup_all()

    def test_health_buffer_not_truncated_on_reuse(self):
        """验证心跳写不截断重建文件"""
        os.environ["NODE_ID"] = "test_hb_reuse"
        os.environ["NODE_OUT_test"] = "test_hb_reuse.test"
        from edge.sdk.nodeflow_sdk import NodeFlowSDK

        sdk = NodeFlowSDK(enable_parent_watchdog=False)
        sdk.create_output_port("test")
        time.sleep(0.3)

        # 记录第一次文件大小
        from edge.runtime.utils.constants import BUFFERS_DIR
        buf_path = Path(BUFFERS_DIR) / "test_hb_reuse.health.buf"
        size1 = buf_path.stat().st_size

        time.sleep(2.5)  # 等待至少一次额外心跳

        size2 = buf_path.stat().st_size
        assert size1 == size2, f"buffer should not be truncated: {size1} -> {size2}"

        sdk.shutdown()
        SharedBufferLite.cleanup_all()


class TestHealthStaleDetection:
    """验证 stale 检测"""

    def test_stale_detection(self):
        import subprocess, json

        # 写入一个旧时间戳的 health buffer
        os.environ["NODE_ID"] = "test_stale_node"
        buf = SharedBufferLite("test_stale_node.health", size=64 * 1024, create=True)
        buf.write({
            "status": "ok",
            "node_id": "test_stale_node",
            "timestamp": time.time() - 3600,  # 1 小时前
            "heartbeat_interval": 2.0,
            "inputs": {},
            "outputs": {},
        })
        buf.close()

        # 通过 CLI 读取
        result = subprocess.run(
            [sys.executable, "-m", "tools.cli.core.cli", "health", "status",
             "test_stale_node", "--json"],
            capture_output=True, text=True,
            cwd=str(Path(__file__).parent.parent.parent),
        )
        output = json.loads(result.stdout)
        assert output["stale"] is True, f"1-hour-old health should be stale, got {output}"
        assert output["status"] == "stale"

        SharedBufferLite.cleanup_all()

    def test_fresh_not_stale(self):
        import subprocess, json

        os.environ["NODE_ID"] = "test_fresh_node"
        buf = SharedBufferLite("test_fresh_node.health", size=64 * 1024, create=True)
        buf.write({
            "status": "ok",
            "node_id": "test_fresh_node",
            "timestamp": time.time(),
            "heartbeat_interval": 2.0,
            "inputs": {},
            "outputs": {},
        })
        buf.close()

        result = subprocess.run(
            [sys.executable, "-m", "tools.cli.core.cli", "health", "status",
             "test_fresh_node", "--json"],
            capture_output=True, text=True,
            cwd=str(Path(__file__).parent.parent.parent),
        )
        output = json.loads(result.stdout)
        assert output["stale"] is False, f"fresh health should not be stale, got {output}"
        assert output["status"] == "ok"

        SharedBufferLite.cleanup_all()


if __name__ == "__main__":
    print("=== Full-header seqlock tests ===")
    t = TestFullHeaderSeqlock()
    t.test_old_data_returns_correctly()
    t.test_mid_write_tombstone_returns_none()
    t.test_sequence_strictly_increasing()

    print("\n=== Health heartbeat tests ===")
    th = TestHealthHeartbeat()
    th.test_health_data_contains_interval()
    th.test_health_buffer_not_truncated_on_reuse()

    print("\n=== Health stale detection tests ===")
    ts = TestHealthStaleDetection()
    ts.test_stale_detection()
    ts.test_fresh_not_stale()

    print("\n✅ All review-fix verification tests passed")
