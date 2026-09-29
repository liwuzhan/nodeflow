"""SIGTERM 优雅退出：runtime 停节点时，节点的 finally / 清理必须执行。

背景：Python 默认对 SIGTERM 直接终止进程，pwm_driver 的 finally 中
_stop_motors() 不执行，sysfs PWM 保持最后脉宽（停止数据流后车辆继续走）。
SDK 现在把 SIGTERM 转为 SystemExit(143)。
"""

import os
import signal
import subprocess
import sys
import textwrap
import time
from pathlib import Path

import pytest

from edge.runtime.monitoring import incident_store

pytestmark = pytest.mark.skipif(sys.platform == "win32", reason="POSIX signals")

ROOT = Path(__file__).resolve().parents[2]

PROBE = textwrap.dedent(
    """
    import sys, time
    sys.path.insert(0, {root!r})
    from edge.sdk.nodeflow_sdk import NodeFlowSDK
    with NodeFlowSDK(log_level="ERROR") as sdk:
        print("READY", flush=True)
        try:
            while True:
                time.sleep(0.01)
        finally:
            open({marker!r}, "w").write("finally ran")
    """
)


def _env(tmp_path, node_id):
    env = os.environ.copy()
    env.update({
        "NODE_ID": node_id,
        "NODEFLOW_RUNTIME_ROOT": str(tmp_path / "rt"),
        "NODEFLOW_LOG_DIR": str(tmp_path / "logs"),
        "PYTHONPATH": str(ROOT),
    })
    env.pop("NODEFLOW_IPC_VERSION", None)
    return env


def _wait_line(proc, needle, timeout=15.0):
    deadline = time.time() + timeout
    seen = []
    while time.time() < deadline:
        line = proc.stdout.readline()
        if not line:
            if proc.poll() is not None:
                break
            continue
        seen.append(line)
        if needle in line:
            return seen
    raise AssertionError(f"'{needle}' not seen; output={''.join(seen)!r}")


def test_sigterm_runs_finally_and_exits_143(tmp_path):
    marker = tmp_path / "marker"
    script = tmp_path / "probe.py"
    script.write_text(PROBE.format(root=str(ROOT), marker=str(marker)))
    proc = subprocess.Popen(
        [sys.executable, str(script)], env=_env(tmp_path, "sigterm_probe"),
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
    )
    try:
        _wait_line(proc, "READY")
        t0 = time.monotonic()
        proc.send_signal(signal.SIGTERM)
        assert proc.wait(timeout=10) == 143
        # SDK shutdown 不得等满心跳(2s)/父进程看门狗(1s)周期：runtime 逐个停节点，
        # 每个节点多等 1-2s 会让整图停止超过 CLI 超时（preflight 曾因此失败）
        assert time.monotonic() - t0 < 1.0
    finally:
        if proc.poll() is None:
            proc.kill()
    assert marker.read_text() == "finally ran"


def test_sigterm_inside_finalizer_is_redelivered(tmp_path):
    """信号落在 __del__ 中时 SystemExit 会被解释器吞掉；SDK 必须重新投递。

    曾经的现象：pwm_driver 偶发不退出，主循环继续跑，5 秒后才被 SIGKILL。
    """
    marker = tmp_path / "marker"
    script = tmp_path / "probe_del.py"
    script.write_text(textwrap.dedent(
        f"""
        import os, signal, sys, time
        sys.path.insert(0, {str(ROOT)!r})
        from edge.sdk.nodeflow_sdk import NodeFlowSDK

        class Finalized:
            def __del__(self):
                os.kill(os.getpid(), signal.SIGTERM)
                for _ in range(1000):  # 让信号在析构函数内被处理
                    pass

        with NodeFlowSDK(log_level="ERROR") as sdk:
            try:
                Finalized()  # 立即析构
                deadline = time.time() + 5
                while time.time() < deadline:
                    time.sleep(0.01)
            finally:
                open({str(marker)!r}, "w").write("finally ran")
        """
    ))
    t0 = time.monotonic()
    proc = subprocess.run(
        [sys.executable, str(script)], env=_env(tmp_path, "finalizer_probe"),
        capture_output=True, text=True, timeout=15,
    )
    assert proc.returncode == 143, proc.stdout + proc.stderr
    assert marker.read_text() == "finally ran"
    assert time.monotonic() - t0 < 4.0  # 不是等 5 秒循环自然结束


def test_parent_death_runs_finally(tmp_path):
    """父进程（runtime）被 SIGKILL：父进程看门狗经 SIGTERM 路径退出，finally 执行。"""
    marker = tmp_path / "marker"
    script = tmp_path / "probe.py"
    script.write_text(PROBE.format(root=str(ROOT), marker=str(marker)))
    parent_code = textwrap.dedent(
        f"""
        import subprocess, sys, time
        p = subprocess.Popen([sys.executable, {str(script)!r}])
        print(p.pid, flush=True)
        time.sleep(60)
        """
    )
    env = _env(tmp_path, "orphan_probe")
    env["NODE_WATCHDOG_INTERVAL"] = "0.2"
    parent = subprocess.Popen(
        [sys.executable, "-c", parent_code], env=env,
        stdout=subprocess.PIPE, text=True,
    )
    child_pid = int(parent.stdout.readline())
    try:
        time.sleep(2.0)  # 子进程完成 SDK 初始化
        parent.kill()
        parent.wait(timeout=5)
        deadline = time.time() + 10
        while time.time() < deadline and not marker.exists():
            time.sleep(0.1)
        assert marker.exists(), "node finally did not run after parent death"
    finally:
        try:
            os.kill(child_pid, signal.SIGKILL)
        except ProcessLookupError:
            pass


def test_pwm_driver_stops_motors_on_sigterm(tmp_path):
    """真实 pwm_driver 节点：SIGTERM 后执行 _stop_motors（回中位）。"""
    node_dir = ROOT / "edge" / "nodes" / "io" / "pwm_driver"
    env = _env(tmp_path, "pwm_driver")
    env["NODE_IN_velocity_cmd"] = "sigterm_test.velocity_cmd"
    env["NODE_OUT_pwm_status"] = "sigterm_test.pwm_status"
    env["PYTHONFAULTHANDLER"] = "1"  # 卡住时 SIGABRT 打印全部线程栈
    proc = subprocess.Popen(
        [sys.executable, "run.py", "--params", '{"dry_run_mode": true}'],
        cwd=node_dir, env=env,
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
    )
    try:
        _wait_line(proc, "PWM Driver node started")
        proc.send_signal(signal.SIGTERM)
        try:
            out, _ = proc.communicate(timeout=5)
        except subprocess.TimeoutExpired:
            proc.send_signal(signal.SIGABRT)
            out, _ = proc.communicate(timeout=5)
            pytest.fail(f"pwm_driver did not exit after SIGTERM; stacks:\n{out[:4000]}\n...\n{out[-6000:]}")
    finally:
        if proc.poll() is None:
            proc.kill()
    assert proc.returncode == 143
    assert "Motors stopped (center PWM)" in out


def test_incident_maps_exit_143_to_sigterm():
    record = incident_store.build_death_record(
        run_id="r", node_id="n", package="p", incarnation=1, retry_count=0,
        exit_code=143, stderr_tail="", frozen_health=None,
        output_ages_ms={}, input_ages_ms={}, quarantined_buffers=[],
    )
    assert record["signal"] == 15
