"""
W3 打磨项测试

覆盖:
- W3-1 设备时间透传（rtk_filter 不以墙钟覆盖上游时间）
- W3-2 现场保留（run 目录滚动保留 + 死亡 run 快照）
- W3-3 输入看门狗（默认 die / 自定义回调）
- W3-4 stdout 日志降级（64MB×3）
- W3-5 sdk.die 统一大声死
- W3-6 health v2 显示与旧字段降级
"""

import json
import os
import subprocess
import sys
import time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from edge.sdk.shared_buffer_lite import SharedBufferLite
from edge.sdk.port import OutputPort, InputPort
from edge.runtime.utils import constants


@pytest.fixture(autouse=True)
def _reset_env():
    yield
    constants.set_current_run(None)
    os.environ.pop("NODEFLOW_BUFFERS_DIR", None)
    os.environ.pop("NODEFLOW_INPUT_WATCHDOG", None)
    os.environ.pop("NODEFLOW_RUNTIME_ROOT", None)
    SharedBufferLite.cleanup_all()


# ========== W3-1: 设备时间透传 ==========

class TestDeviceTimestampPassthrough:
    def test_upstream_timestamp_preserved(self):
        from edge.nodes.sensing.rtk_filter.atom import EMAFilter
        import importlib.util

        # atom 无包结构，按路径加载
        spec = importlib.util.spec_from_file_location(
            "rtk_filter_atom",
            Path(__file__).parent.parent.parent
            / "edge/nodes/sensing/rtk_filter/atom.py",
        )
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)

        filt = mod.EMAFilter(alpha_pos=0.5, alpha_heading=0.5, use_imu_yaw_rate=False)

        device_ts = 1700000000.123
        out = filt.update(
            {"lat": 30.0, "lon": 120.0, "heading": 10.0, "timestamp": device_ts},
            None, now=9999999.0,
        )
        assert out["timestamp"] == device_ts, "上游设备时间不得被墙钟覆盖"
        assert out["timestamp_source"] == "device"

        out2 = filt.update(
            {"lat": 30.0, "lon": 120.0, "heading": 10.0},  # 无 timestamp
            None, now=8888888.0,
        )
        assert out2["timestamp"] == 8888888.0
        assert out2["timestamp_source"] == "local"


# ========== W3-2: 现场保留 ==========

class TestRunRetention:
    def test_prune_keeps_five_runs_and_snapshots_incident_runs(self, tmp_path, monkeypatch):
        monkeypatch.setenv("NODEFLOW_RUNTIME_ROOT", str(tmp_path))
        monkeypatch.setenv("NODEFLOW_INCIDENT_DIR", str(tmp_path / "incidents"))
        from edge.runtime.monitoring import incident_store

        # 造 7 个 run 目录（名字按时间递增），run2 有死亡记录
        for i in range(7):
            run_dir = tmp_path / "runs" / f"run{i:04d}"
            buf_dir = run_dir / "buffers"
            buf_dir.mkdir(parents=True)
        incident_store.append_incident({"ts_unix": time.time(), "run_id": "run0001", "node_id": "n"})

        # run0001 放一个小端口数据（会被快照）：先在默认目录写入再移动过去
        small = SharedBufferLite("node.out", create=True)
        small.write({"evidence": True})
        small.close()
        os.replace(
            Path(constants.get_buffers_dir()) / "node.out.buf",
            tmp_path / "runs/run0001/buffers/node.out.buf",
        )

        pruned = incident_store.prune_run_dirs(keep=5)
        assert pruned == 2, "7 个 run 保留 5 个应剪除 2 个"

        remaining = sorted(d.name for d in (tmp_path / "runs").iterdir())
        assert remaining == [f"run{i:04d}" for i in range(2, 7)]

        snap = tmp_path / "incidents/snapshots/run0001/node.out.snapshot.msgpack"
        assert snap.exists(), "含死亡记录的 run 剪除前应快照小端口 payload"
        import msgpack
        payload = msgpack.unpackb(snap.read_bytes(), raw=False)
        assert payload["payload"] == {"evidence": True}
        assert payload["buffer"] == "node.out"

    def test_clean_buffers_retired_noop(self, tmp_path):
        """_clean_buffers 不再就地清零任何文件（run 目录天然全新）"""
        from edge.runtime.main import NodeFlowRuntime

        runtime = NodeFlowRuntime.__new__(NodeFlowRuntime)
        victim = Path(constants.get_buffers_dir()) / "retired_check.buf"
        victim.parent.mkdir(parents=True, exist_ok=True)
        victim.write_bytes(b"\x01" * 64)
        try:
            runtime._clean_buffers()  # no-op：不抛错也不清文件
            assert victim.read_bytes() == b"\x01" * 64
        finally:
            victim.unlink(missing_ok=True)


# ========== W3-3: 输入看门狗 ==========

class TestInputWatchdog:
    def test_manifest_input_watchdog_parsed(self, tmp_path):
        from edge.runtime.config.yaml_parser import YAMLParser

        manifest_yaml = tmp_path / "node.yaml"
        manifest_yaml.write_text(
            "name: w\nentrypoints:\n  linux: {kind: python, cmd: [python3, run.py]}\n"
            "input_watchdog:\n  velocity_cmd: 0.5\n"
        )
        manifest = YAMLParser.parse_node_manifest(str(manifest_yaml))
        assert manifest.input_watchdog == {"velocity_cmd": 0.5}

    def test_watchdog_custom_handler_called(self, monkeypatch):
        """注册 on_input_lost 回调 → 断流超时调用回调而非 die"""
        monkeypatch.setenv("NODE_ID", "wd_node")
        monkeypatch.setenv("NODE_IN_cmd", "wd_src.cmd")
        monkeypatch.setenv("NODEFLOW_INPUT_WATCHDOG", json.dumps({"cmd": 0.1}))
        from edge.sdk.nodeflow_sdk import NodeFlowSDK

        out = OutputPort(name="cmd", buffer_name="wd_src.cmd")
        out.send({"v": 1})  # 上游写过一次

        sdk = NodeFlowSDK(enable_parent_watchdog=False)
        inp = sdk.create_input_port("cmd")
        inp.recv_latest()

        calls = []
        sdk.set_on_input_lost("cmd", lambda port: calls.append(port))

        deadline = time.time() + 3.0
        while not calls and time.time() < deadline:
            time.sleep(0.05)

        assert calls == ["cmd"], "断流超时应调用自定义回调"
        sdk.shutdown()
        out.close()

    def test_watchdog_default_dies_loudly(self):
        """未注册回调 → 默认 sdk.die（进程退出且 stderr 有结构化遗言）"""
        env = dict(os.environ)
        env.update({
            "NODE_ID": "wd_die_node",
            "NODE_IN_cmd": "wd_die_src.cmd",
            "NODEFLOW_INPUT_WATCHDOG": json.dumps({"cmd": 0.1}),
        })
        code = (
            "import time\n"
            "from edge.sdk.nodeflow_sdk import NodeFlowSDK\n"
            "from edge.sdk.port import OutputPort\n"
            "out = OutputPort(name='cmd', buffer_name='wd_die_src.cmd')\n"
            "out.send({'v': 1})\n"
            "sdk = NodeFlowSDK(enable_parent_watchdog=False)\n"
            "sdk.create_input_port('cmd')\n"
            "time.sleep(2.0)\n"  # 断流 2s >> 0.1s 超时 → die
            "print('SHOULD_NOT_REACH')\n"
        )
        result = subprocess.run(
            [sys.executable, "-c", code],
            capture_output=True, text=True, env=env,
            cwd=str(Path(__file__).parent.parent.parent),
            timeout=30,
        )
        assert result.returncode == 1, f"expected loud death, rc={result.returncode}, stderr={result.stderr[-400:]}"
        assert "node_die" in result.stderr
        assert "stale" in result.stderr
        assert "SHOULD_NOT_REACH" not in result.stdout


# ========== W3-4: stdout 日志降级 ==========

class TestStdoutLogDowngrade:
    def test_rotating_handler_64mb_x3(self, monkeypatch, tmp_path):
        from edge.runtime.config.models import NodeInstance, NodeManifest, EntryPoint
        from edge.runtime.orchestrator import node_launcher as nl

        captured = {}
        real_rfhandler = nl.RotatingFileHandler

        class SpyHandler(real_rfhandler):
            def __init__(self, filename, **kwargs):
                captured[str(filename)] = dict(kwargs)
                super().__init__(filename, **kwargs)

        monkeypatch.setattr(nl, "RotatingFileHandler", SpyHandler)

        pkg_dir = tmp_path / "pkg"
        pkg_dir.mkdir()
        stdout_f = open(tmp_path / "o", "w+")
        stderr_f = open(tmp_path / "e", "w+")

        class FakePopen:
            pid = 99
            stdout = stdout_f
            stderr = stderr_f

            def poll(self):
                return 0

        monkeypatch.setattr(nl.subprocess, "Popen", lambda *a, **kw: FakePopen())

        launcher = nl.NodeLauncher(str(tmp_path), [])
        launcher.launch(
            NodeInstance(id="n1", package="pkg"),
            NodeManifest(name="pkg", entrypoints={"linux": EntryPoint(kind="python", cmd=["true"])}),
        )
        stdout_f.close()
        stderr_f.close()

        for kwargs in captured.values():
            assert kwargs["maxBytes"] == 64 * 1024 * 1024
            assert kwargs["backupCount"] == 3


# ========== W3-5: sdk.die ==========

class TestSdkDie:
    def test_die_structured_last_words_and_exit_code(self):
        env = dict(os.environ)
        env["NODE_ID"] = "die_test_node"
        result = subprocess.run(
            [sys.executable, "-c",
             "from edge.sdk.nodeflow_sdk import die; die('boom reason', code=3)"],
            capture_output=True, text=True, env=env,
            cwd=str(Path(__file__).parent.parent.parent),
            timeout=30,
        )
        assert result.returncode == 3
        last_line = result.stderr.strip().splitlines()[-1]
        payload = json.loads(last_line)
        assert payload["event"] == "node_die"
        assert payload["node_id"] == "die_test_node"
        assert payload["reason"] == "boom reason"

    def test_die_captures_traceback(self):
        result = subprocess.run(
            [sys.executable, "-c",
             "from edge.sdk.nodeflow_sdk import die\n"
             "try:\n    1/0\nexcept ZeroDivisionError:\n    die('math failed')\n"],
            capture_output=True, text=True,
            cwd=str(Path(__file__).parent.parent.parent),
            timeout=30,
        )
        assert result.returncode == 1
        assert "ZeroDivisionError" in result.stderr


# ========== W3-6: health v2 显示降级 ==========

class TestHealthDisplayDegrade:
    def test_cli_shows_incarnation_and_degrades_without_it(self):
        # v2 health（含 incarnation）
        SharedBufferLite("v3_disp_new.health", create=True, size=64 * 1024).write({
            "status": "ok", "node_id": "v3_disp_new", "timestamp": time.time(),
            "heartbeat_interval": 2.0, "incarnation": 7,
            "inputs": {"in": {"connected": True, "last_seq_seen": 9, "source_write_age_ms": 12.0}},
            "outputs": {},
        })
        # v1 风格 health（无 incarnation，inputs 为布尔）
        SharedBufferLite("v3_disp_old.health", create=True, size=64 * 1024).write({
            "status": "ok", "node_id": "v3_disp_old", "timestamp": time.time(),
            "heartbeat_interval": 2.0, "inputs": {"in": True}, "outputs": {},
        })

        for node_id, expect_inc in (("v3_disp_new", 7), ("v3_disp_old", None)):
            result = subprocess.run(
                [sys.executable, "-m", "tools.cli.core.cli", "health", "status", node_id, "--json"],
                capture_output=True, text=True,
                cwd=str(Path(__file__).parent.parent.parent),
                timeout=30,
            )
            assert result.returncode == 0, result.stderr[-300:]
            data = json.loads(result.stdout)
            assert data["status"] == "ok"
            assert data.get("incarnation") == expect_inc


if __name__ == "__main__":
    raise SystemExit("Run via: python3 -m pytest tests/unit/test_polish_w3.py -q")
