import signal
import subprocess
from pathlib import Path

from tools.cli.commands import runtime_cmd


def test_stop_runtime_sends_daemon_shutdown_command(monkeypatch, tmp_path):
    pid_file = tmp_path / "nodeflow_runtime.pid"
    pid_file.write_text("12345\n1000.0")
    monkeypatch.setattr(runtime_cmd, "PID_FILE", pid_file)
    monkeypatch.setattr(runtime_cmd, "_process_alive", lambda pid: True)
    monkeypatch.setattr(runtime_cmd, "_wait_for_exit", lambda pid, timeout: True)

    writes = []

    class FakeBuffer:
        def __init__(self, name, create=False):
            self.name = name
            self.create = create

        def write(self, payload):
            writes.append((self.name, payload))

    monkeypatch.setattr("sdk.shared_buffer_lite.SharedBufferLite", FakeBuffer)

    result = runtime_cmd.stop_runtime()

    assert result["status"] == "success"
    assert any(
        name == "runtime.control" and payload.get("command") == "shutdown"
        for name, payload in writes
    )
    assert not pid_file.exists()


def test_stop_runtime_falls_back_to_sigterm_without_sudo(monkeypatch, tmp_path):
    pid_file = tmp_path / "nodeflow_runtime.pid"
    pid_file.write_text("12345\n1000.0")
    monkeypatch.setattr(runtime_cmd, "PID_FILE", pid_file)

    sent = []
    waits = {"count": 0}

    monkeypatch.setattr(runtime_cmd, "_process_alive", lambda pid: True)
    monkeypatch.setattr(runtime_cmd, "_request_runtime_shutdown", lambda: False)

    def fake_wait_for_exit(pid, timeout):
        waits["count"] += 1
        return waits["count"] == 2

    monkeypatch.setattr(runtime_cmd, "_wait_for_exit", fake_wait_for_exit)

    def fake_send_signal(pid, sig):
        sent.append(sig)
        return True

    monkeypatch.setattr(runtime_cmd, "_send_signal", fake_send_signal)

    result = runtime_cmd.stop_runtime()

    assert result["status"] == "success"
    assert signal.SIGTERM in sent
    assert not pid_file.exists()


def test_status_cleans_stale_pid_file(monkeypatch, tmp_path):
    pid_file = tmp_path / "nodeflow_runtime.pid"
    pid_file.write_text("12345\n1000.0")
    monkeypatch.setattr(runtime_cmd, "PID_FILE", pid_file)
    monkeypatch.setattr(runtime_cmd, "_process_alive", lambda pid: False)

    result = runtime_cmd.get_runtime_status()

    assert result == {"status": "not_running", "pid": None}
    assert not pid_file.exists()


def test_zombie_pid_is_not_runtime_running(monkeypatch):
    monkeypatch.setattr(runtime_cmd.os, "kill", lambda pid, sig: None)

    class Result:
        returncode = 0
        stdout = "Z\n"

    monkeypatch.setattr(subprocess, "run", lambda *args, **kwargs: Result())

    assert runtime_cmd._process_alive(12345) is False
