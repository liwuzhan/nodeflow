"""
协议 v2 测试（W2-1~W2-5）

覆盖:
- Buffer header v2: 16 字节布局 / write_ts 年龄 / 版本握手（W2-1）
- run_id + incarnation + run 作用域目录 + PID JSON（W2-2）
- InputPort 自愈与重同步（W2-3）
- 死亡记录 schema / 存储 / 监控接入（W2-4）
- readiness 驱动启动（W2-5）
"""

import json
import os
import struct
import subprocess
import sys
import time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from edge.sdk.shared_buffer_lite import SharedBufferLite, IPC_VERSION
from edge.sdk.port import OutputPort, InputPort
from edge.runtime.utils import constants


@pytest.fixture(autouse=True)
def _reset_run_scope():
    """每个用例后清除 run 作用域与环境变量，避免跨用例污染"""
    yield
    constants.set_current_run(None)
    os.environ.pop("NODEFLOW_BUFFERS_DIR", None)
    SharedBufferLite.cleanup_all()


# ========== W2-1: Buffer header v2 ==========

class TestHeaderV2:
    def test_header_size_16_and_layout(self):
        w = SharedBufferLite("v2_layout", size=1024 * 1024, create=True)
        assert SharedBufferLite.HEADER_SIZE == 16
        assert IPC_VERSION == 2

        w.write({"x": 1})
        seq, length, ts = w.get_header()
        assert seq == 1
        assert length > 0
        assert ts > 0, "write_ts_ns 必须落盘（CLOCK_MONOTONIC 纳秒）"
        w.close()

    def test_write_age_ms_accuracy(self):
        """验收 #10：写入年龄可查且误差 <5ms（放宽到 50ms 容忍调度抖动）"""
        w = SharedBufferLite("v2_age", size=1024 * 1024, create=True)
        w.write({"x": 1})
        age0 = w.get_write_age_ms()
        assert age0 is not None and age0 < 50

        time.sleep(0.15)
        age1 = w.get_write_age_ms()
        assert 100 <= age1 - age0 <= 1000
        w.close()

    def test_input_port_last_write_age(self):
        out = OutputPort(name="p", buffer_name="v2_out_age")
        out.send({"v": 1})
        inp = InputPort(name="in", buffer_name="v2_out_age")
        assert inp.last_write_age_ms() is not None
        assert inp.last_write_age_ms() < 50
        out.close()
        inp.close()

    def test_version_handshake_rejects_mismatch(self):
        """SDK 遇到不符的 IPC 版本必须大声退出（退出码 86）而非静默混读"""
        env = dict(os.environ)
        env.update({"NODE_ID": "v2_ver_node", "NODEFLOW_IPC_VERSION": "1"})
        result = subprocess.run(
            [sys.executable, "-c",
             "from edge.sdk.nodeflow_sdk import NodeFlowSDK; "
             "NodeFlowSDK(enable_parent_watchdog=False)"],
            capture_output=True, text=True, env=env,
            cwd=str(Path(__file__).parent.parent.parent),
            timeout=30,
        )
        assert result.returncode == 86, (
            f"mismatched version should exit 86, got {result.returncode}; "
            f"stderr={result.stderr[-500:]}"
        )
        assert "ipc_version_mismatch" in result.stderr

    def test_version_handshake_accepts_match(self):
        env = dict(os.environ)
        env.update({"NODE_ID": "v2_ver_ok", "NODEFLOW_IPC_VERSION": "2"})
        result = subprocess.run(
            [sys.executable, "-c",
             "from edge.sdk.nodeflow_sdk import NodeFlowSDK; "
             "sdk = NodeFlowSDK(enable_parent_watchdog=False); sdk.shutdown(); print('OK')"],
            capture_output=True, text=True, env=env,
            cwd=str(Path(__file__).parent.parent.parent),
            timeout=30,
        )
        assert result.returncode == 0, result.stderr[-500:]
        assert "OK" in result.stdout


# ========== W2-2: run_id + incarnation + run 目录 ==========

class TestRunScope:
    def test_buffers_dir_resolution(self):
        # 无 run → 默认目录
        assert constants.get_buffers_dir() == f"{constants.get_runtime_root()}/buffers"

        # runtime 设置当前 run → run 作用域目录
        constants.set_current_run("abc123")
        expected = f"{constants.get_runs_root()}/abc123/buffers"
        assert constants.get_buffers_dir() == expected

        # 控制面缓冲区固定根目录（CLI 查活体依赖，不随 run 漂移）
        assert constants.get_buffers_dir("runtime.control") == f"{constants.get_runtime_root()}/buffers"
        assert constants.get_buffers_dir("runtime.status") == f"{constants.get_runtime_root()}/buffers"

        # 节点侧 env 注入优先（W2-2 env_builder 路径）
        os.environ["NODEFLOW_BUFFERS_DIR"] = "/somewhere/else"
        assert constants.get_buffers_dir() == "/somewhere/else"
        # 控制面不受 env 影响
        assert constants.get_buffers_dir("runtime.control") == f"{constants.get_runtime_root()}/buffers"

    def test_env_builder_injects_protocol_env(self):
        from edge.runtime.config.models import NodeInstance, NodeManifest, PortDef, EntryPoint
        from edge.runtime.orchestrator.env_builder import EnvBuilder

        constants.set_current_run("run42")
        node = NodeInstance(id="n1", package="pkg")
        manifest = NodeManifest(
            name="pkg",
            entrypoints={"linux": EntryPoint(kind="python", cmd=["python3", "run.py"])},
            outputs=[PortDef(name="out")],
        )
        env = EnvBuilder.build_env(node, manifest, "/tmp/hub", [], incarnation=3)
        assert env["NODEFLOW_IPC_VERSION"] == "2"
        assert env["NODEFLOW_RUN_ID"] == "run42"
        assert env["NODEFLOW_BUFFERS_DIR"] == f"{constants.get_runs_root()}/run42/buffers"
        assert env["NODEFLOW_INCARNATION"] == "3"

    def test_incarnation_increments_across_restarts(self, monkeypatch, tmp_path):
        """首拉=1，重启 +1（launcher 维护，随 launcher 实例重置）"""
        import io
        from edge.runtime.config.models import NodeInstance, NodeManifest, EntryPoint
        from edge.runtime.orchestrator.node_launcher import NodeLauncher

        pkg_dir = tmp_path / "pkg"
        pkg_dir.mkdir()
        launcher = NodeLauncher(str(tmp_path), [])

        stdout_f = open(tmp_path / "o", "w+")
        stderr_f = open(tmp_path / "e", "w+")

        class FakePopen:
            pid = 4242
            stdout = stdout_f
            stderr = stderr_f

            def poll(self):
                return 0  # 已退出：让 launcher 的日志转发线程结束

        monkeypatch.setattr(
            "edge.runtime.orchestrator.node_launcher.subprocess.Popen",
            lambda *a, **kw: FakePopen(),
        )

        node = NodeInstance(id="n1", package="pkg")
        manifest = NodeManifest(
            name="pkg",
            entrypoints={"linux": EntryPoint(kind="python", cmd=["true"])},
        )

        launcher.launch(node, manifest)
        launcher.launch(node, manifest)
        launcher.launch(node, manifest)

        assert launcher.incarnations["n1"] == 3
        assert launcher.get_incarnation("n1") == 3
        stdout_f.close()
        stderr_f.close()

    def test_health_payload_v2_fields(self):
        """W3-6：health 含 incarnation + inputs v2（connected/last_seq_seen/source_write_age_ms）"""
        os.environ["NODE_ID"] = "v2_health_node"
        os.environ["NODE_OUT_p"] = "v2_health_node.p"
        os.environ["NODEFLOW_INCARNATION"] = "4"
        from edge.sdk.nodeflow_sdk import NodeFlowSDK

        sdk = NodeFlowSDK(enable_parent_watchdog=False)
        sdk.create_output_port("p")
        time.sleep(0.3)

        health = SharedBufferLite("v2_health_node.health", create=False).read()
        assert health["incarnation"] == 4
        assert isinstance(health.get("inputs", {}), dict)
        assert "run_id" in health
        sdk.shutdown()

        os.environ.pop("NODEFLOW_INCARNATION", None)


# ========== W2-3: InputPort 自愈与重同步 ==========

class TestInputPortSelfHealing:
    def test_reconnect_after_late_producer(self, monkeypatch):
        """上游后启动：InputPort 不再永久放弃，按退避重连"""
        monkeypatch.setattr("edge.sdk.port.time.sleep", lambda *_: None)
        inp = InputPort(name="in", buffer_name="v3_late_src")
        assert inp.state == "DISCONNECTED"

        out = OutputPort(name="src", buffer_name="v3_late_src")
        out.send({"v": 1})

        data = None
        for _ in range(5):
            data = inp.recv_latest()
            if data is not None:
                break
        assert data == {"v": 1}
        assert inp.state == "CONNECTED"
        out.close()
        inp.close()

    def test_resync_on_producer_rebuild(self):
        """生产者中途重建 buffer（改名留证/损坏重建路径）→ 下游经 inode/seq 安全网恢复"""
        out = OutputPort(name="src", buffer_name="v3_rebuild_src")
        out.send({"v": 1})
        out.send({"v": 2})
        inp = InputPort(name="in", buffer_name="v3_rebuild_src")
        assert inp.recv_latest() is not None
        assert inp.generation == 0

        # 生产者死亡 + 损坏重建：旧文件删除，新池从 seq=0 开始
        old_path = Path(out.buffer.buffer_path)
        out.close()
        os.unlink(old_path)
        out2 = OutputPort(name="src", buffer_name="v3_rebuild_src")
        out2.send({"v": "new-pool"})

        data = inp.recv_latest()  # 触发重同步并读取新池快照
        assert data == {"v": "new-pool"}
        assert inp.generation == 1

        out2.send({"v": "next"})
        assert inp.recv_latest() == {"v": "next"}
        out2.close()
        inp.close()

    def test_no_resync_on_reuse_restart(self):
        """生产者复用型重启（N-1：seq 连续、inode 不变）→ 不触发重同步，数据面无感"""
        out = OutputPort(name="src", buffer_name="v3_reuse_src")
        for i in range(5):
            out.send({"i": i})
        inp = InputPort(name="in", buffer_name="v3_reuse_src")
        assert inp.recv_latest() == {"i": 4}
        assert inp.generation == 0

        # 复用重启：同一文件重开，seq 继续
        out.close()
        resumed = SharedBufferLite("v3_reuse_src", create=False)
        resumed.write({"i": 5})

        assert inp.recv_latest() == {"i": 5}
        assert inp.generation == 0, "复用型重启不应触发重同步（世代归因走 incarnation）"
        resumed.close()
        inp.close()

    def test_get_stats_fields(self):
        out = OutputPort(name="src", buffer_name="v3_stats_src")
        out.send({"v": 1})
        inp = InputPort(name="in", buffer_name="v3_stats_src")
        stats = inp.get_stats()
        assert stats["state"] == "connected"
        assert stats["generation"] == 0
        assert stats["source_write_age_ms"] is not None and stats["source_write_age_ms"] < 100
        out.close()
        inp.close()


# ========== W2-4: 死亡记录 ==========

class TestIncidentStore:
    def test_append_and_list_roundtrip(self, tmp_path, monkeypatch):
        monkeypatch.setenv("NODEFLOW_INCIDENT_DIR", str(tmp_path))
        from edge.runtime.monitoring import incident_store

        for i in range(3):
            incident_store.append_incident({"ts_unix": time.time() - i, "node_id": f"n{i}"})

        records = incident_store.list_recent_incidents(limit=2)
        assert len(records) == 2
        assert records[-1]["node_id"] == "n2"

    def test_prune_keeps_recent_records(self, tmp_path, monkeypatch):
        monkeypatch.setenv("NODEFLOW_INCIDENT_DIR", str(tmp_path))
        from edge.runtime.monitoring import incident_store

        old_ts = time.time() - 40 * 86400  # 40 天前，超保留期
        for i in range(10):
            incident_store.append_incident({"ts_unix": old_ts, "node_id": f"old{i}"})
        incident_store.append_incident({"ts_unix": time.time(), "node_id": "fresh"})

        records = incident_store.list_recent_incidents(limit=100)
        assert all(r["node_id"] != "old0" for r in records)
        assert any(r["node_id"] == "fresh" for r in records)

    def test_death_record_schema(self):
        from edge.runtime.monitoring.incident_store import build_death_record

        frozen = {
            "timestamp": time.time() - 1.2,
            "inputs": {"serial_raw": {"connected": True, "last_seq_seen": 1204,
                                      "source_write_age_ms": 41000.0}},
        }
        rec = build_death_record(
            run_id="run42", node_id="rtk_sensor", package="sensing/rtk_driver",
            incarnation=3, retry_count=2, exit_code=-9, stderr_tail="x" * 800,
            frozen_health=frozen,
            output_ages_ms={"rtk_fix": 41200.0},
            input_ages_ms={"serial_raw": 42000.0},
            quarantined_buffers=["rtk_sensor.rtk_fix.dead.3.buf"],
        )
        # 信号终止：exit_code=-9 → signal=9
        assert rec["signal"] == 9
        # stderr 尾部截断 ≤500 字
        assert len(rec["stderr_tail"]) <= 500
        # will = 冻结证词（主证据）
        assert rec["will"]["health_age_ms_at_crash_detect"] <= 1300
        assert rec["will"]["inputs"]["serial_raw"]["last_seq_seen"] == 1204
        # witness = 旁证 + 如实标注
        assert rec["witness"]["output_ages_ms"]["rtk_fix"] == 41200.0
        assert "检测时刻" in rec["witness"]["input_ages_ms_note"]
        assert rec["quarantined_buffers"] == ["rtk_sensor.rtk_fix.dead.3.buf"]

    def test_monitor_invokes_incident_recorder_on_crash(self, monkeypatch):
        from edge.runtime.config.models import RestartPolicy as RestartPolicyConfig
        from edge.runtime.monitoring.node_monitor import NodeMonitor

        calls = []
        monitor = NodeMonitor(
            RestartPolicyConfig(max_retries=3, backoff_ms=0),
            incident_recorder=lambda nid, code, tail, retry: calls.append((nid, code, tail, retry)),
        )
        monitor.processes = {"n1": FakeCrashProcess()}
        monitor._handle_node_crash("n1", 1)

        assert len(calls) == 1
        nid, code, tail, retry = calls[0]
        assert nid == "n1" and code == 1 and retry == 1
        assert "boom" in tail


class FakeCrashProcess:
    pid = 111

    def poll(self):
        return 1

    def communicate(self, timeout=None):
        return ("", "traceback: boom")


# ========== D2: 损坏 buffer 隔离重建 ==========

class TestBufferQuarantine:
    def test_output_port_quarantines_illegal_header(self):
        """验收 #8：垃圾 header → 旧文件改名 .dead.1.buf 留证、新池建立可写"""
        out = OutputPort(name="src", buffer_name="v4_corrupt_src")
        out.send({"v": 1})

        # 写坏 length 字段（越界值）
        with open(out.buffer.buffer_path, "r+b") as f:
            import mmap as _mmap
            with _mmap.mmap(f.fileno(), 0) as m:
                m[4:8] = struct.pack('<I', 10 ** 9)
        old_path = Path(out.buffer.buffer_path)
        out.close()

        out2 = OutputPort(name="src", buffer_name="v4_corrupt_src")
        quarantined = old_path.with_name("v4_corrupt_src.dead.1.buf")
        assert quarantined.exists(), "损坏文件必须改名留证（不删除）"
        assert not old_path.exists() or old_path.stat().st_ino != quarantined.stat().st_ino

        out2.send({"v": "new-pool"})
        seq, data = out2.buffer.read_with_sequence()
        assert data == {"v": "new-pool"} and seq == 1, "新池应从 seq=1 重新计数"
        out2.close()

    def test_output_port_quarantines_size_mismatch(self):
        """尺寸与配置不符（N-2）→ 同样改名重建"""
        out = OutputPort(name="src", buffer_name="v4_size_src")
        old_path = Path(out.buffer.buffer_path)
        out.close()

        # 缩小文件制造尺寸失配
        with open(old_path, "r+b") as f:
            f.truncate(2048)

        out2 = OutputPort(name="src", buffer_name="v4_size_src")
        assert old_path.with_name("v4_size_src.dead.1.buf").exists()
        assert out2.buffer.size == out2.buffer_size
        out2.close()

    def test_incident_side_quarantine_of_dead_node_buffers(self):
        """监控侧框架办后事（P1）：死亡节点的损坏输出 buffer 被改名并进死亡记录"""
        from edge.runtime.monitoring import incident_store

        out = OutputPort(name="src", buffer_name="v4_dead_src")
        out.send({"v": 1})
        path = Path(out.buffer.buffer_path)
        out.close()

        # 写坏 header 模拟撕裂
        with open(path, "r+b") as f:
            import mmap as _mmap
            with _mmap.mmap(f.fileno(), 0) as m:
                m[4:8] = struct.pack('<I', 99999999)

        dead_name = incident_store.inspect_and_quarantine("v4_dead_src", 1024 * 1024, incarnation=2)
        assert dead_name == "v4_dead_src.dead.2.buf"
        assert Path(path.parent, dead_name).exists()
        # 完好 buffer 不动
        good = OutputPort(name="ok", buffer_name="v4_ok_src")
        good.send({"v": 1})
        assert incident_store.inspect_and_quarantine("v4_ok_src", 1024 * 1024, 1) is None
        good.close()


# ========== W2-5: readiness 驱动启动 ==========

class TestReadinessStartup:
    @staticmethod
    def _make_coordinator(registry):
        from edge.runtime.orchestrator.startup_coordinator import StartupCoordinator

        return StartupCoordinator(launcher=None, registry=registry)

    @staticmethod
    def _write_health(node_id):
        SharedBufferLite(f"{node_id}.health", create=True, size=64 * 1024).write({
            "status": "ok", "timestamp": time.time(), "heartbeat_interval": 2.0,
        })

    def test_readiness_field_parsed_from_manifest(self, tmp_path):
        from edge.runtime.config.yaml_parser import YAMLParser

        manifest_yaml = tmp_path / "node.yaml"
        manifest_yaml.write_text(
            "name: static_node\n"
            "readiness: first_output\n"
            "entrypoints:\n  linux: {kind: python, cmd: [python3, run.py]}\n"
        )
        manifest = YAMLParser.parse_node_manifest(str(manifest_yaml))
        assert manifest.readiness == "first_output"

    def test_heartbeat_ready_returns_fast(self):
        """health 新鲜 → 不等满 timeout 立即放行"""
        from edge.runtime.config.models import NodeInstance, NodeManifest, EntryPoint

        class FakeRegistry:
            def get_manifest(self, package):
                return NodeManifest(
                    name=package,
                    entrypoints={"linux": EntryPoint(kind="python", cmd=[])},
                )

        nodes = {"n1": NodeInstance(id="n1", package="pkg")}
        self._write_health("n1")
        coordinator = self._make_coordinator(FakeRegistry())

        start = time.time()
        coordinator._wait_for_layer({"n1": FakeAliveProcess()}, nodes, timeout=5.0)
        assert time.time() - start < 2.0, "readiness 达成后应立即返回"

    def test_timeout_warns_and_continues(self):
        """readiness 超时 → 告警放行，不抛异常（与现状宽容度一致）"""
        from edge.runtime.config.models import NodeInstance, NodeManifest, EntryPoint

        class FakeRegistry:
            def get_manifest(self, package):
                return NodeManifest(
                    name=package,
                    entrypoints={"linux": EntryPoint(kind="python", cmd=[])},
                )

        nodes = {"n1": NodeInstance(id="n1", package="pkg")}  # 无 health → 永不就绪
        coordinator = self._make_coordinator(FakeRegistry())

        start = time.time()
        coordinator._wait_for_layer({"n1": FakeAliveProcess()}, nodes, timeout=0.3)
        assert 0.25 <= time.time() - start < 2.0, "应等到 timeout 后放行"

    def test_first_output_ready(self):
        from edge.runtime.config.models import NodeInstance, NodeManifest, EntryPoint, PortDef

        class FakeRegistry:
            def get_manifest(self, package):
                return NodeManifest(
                    name=package,
                    entrypoints={"linux": EntryPoint(kind="python", cmd=[])},
                    outputs=[PortDef(name="plan")],
                    readiness="first_output",
                )

        nodes = {"n1": NodeInstance(id="n1", package="pkg")}
        SharedBufferLite("n1.plan", create=True).write({"ready": True})
        coordinator = self._make_coordinator(FakeRegistry())

        start = time.time()
        coordinator._wait_for_layer({"n1": FakeAliveProcess()}, nodes, timeout=5.0)
        assert time.time() - start < 2.0

    def test_process_exit_raises(self):
        from edge.runtime.config.models import NodeInstance, NodeManifest, EntryPoint
        from edge.runtime.orchestrator.startup_coordinator import NodeStartupError

        class FakeRegistry:
            def get_manifest(self, package):
                return NodeManifest(
                    name=package,
                    entrypoints={"linux": EntryPoint(kind="python", cmd=[])},
                )

        nodes = {"n1": NodeInstance(id="n1", package="pkg")}
        coordinator = self._make_coordinator(FakeRegistry())

        with pytest.raises(NodeStartupError):
            coordinator._wait_for_layer({"n1": FakeCrashProcess()}, nodes, timeout=1.0)


class FakeAliveProcess:
    pid = 222

    def poll(self):
        return None


if __name__ == "__main__":
    raise SystemExit("Run via: python3 -m pytest tests/unit/test_protocol_v2.py -q")
