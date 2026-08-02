import pytest

from tools import preflight_runtime


def test_descendant_pids_walks_the_full_process_tree(monkeypatch):
    monkeypatch.setattr(
        preflight_runtime,
        "_process_table",
        lambda: {10: 1, 11: 10, 12: 11, 13: 10, 99: 1},
    )

    assert preflight_runtime._descendant_pids(10) == {11, 12, 13}


def test_clean_shutdown_accepts_graceful_exit(monkeypatch, tmp_path):
    monkeypatch.setattr(preflight_runtime, "PID_FILE", tmp_path / "missing.pid")
    monkeypatch.setattr(preflight_runtime, "_pid_is_alive", lambda pid: False)
    monkeypatch.setattr(preflight_runtime, "is_runtime_running", lambda: False)
    monkeypatch.setattr(preflight_runtime, "_port_is_listening", lambda port: False)

    result = preflight_runtime._assert_clean_shutdown(
        runtime_was_started=True,
        stop_result={"status": "success", "message": "Runtime stopped gracefully"},
        runtime_pid=100,
        node_pids={101, 102},
        simulator_pid=103,
    )

    assert result == {
        "runtime_stop": "graceful",
        "runtime_pid_exited": True,
        "node_processes_checked": 2,
        "node_processes_exited": True,
        "simulator_pid_exited": True,
        "released_ports": [5555, 8080],
        "pid_file_removed": True,
        "no_residual_control_process": True,
    }


def test_clean_shutdown_rejects_force_kill(monkeypatch, tmp_path):
    monkeypatch.setattr(preflight_runtime, "PID_FILE", tmp_path / "missing.pid")
    monkeypatch.setattr(preflight_runtime, "_pid_is_alive", lambda pid: False)
    monkeypatch.setattr(preflight_runtime, "is_runtime_running", lambda: False)
    monkeypatch.setattr(preflight_runtime, "_port_is_listening", lambda port: False)

    with pytest.raises(preflight_runtime.PreflightError, match="did not stop gracefully"):
        preflight_runtime._assert_clean_shutdown(
            runtime_was_started=True,
            stop_result={"status": "success", "message": "Runtime force-killed"},
            runtime_pid=100,
            node_pids={101},
            simulator_pid=102,
        )


def test_clean_shutdown_reports_residuals(monkeypatch, tmp_path):
    pid_file = tmp_path / "runtime.pid"
    pid_file.write_text("100\n", encoding="utf-8")
    monkeypatch.setattr(preflight_runtime, "PID_FILE", pid_file)
    monkeypatch.setattr(
        preflight_runtime,
        "_pid_is_alive",
        lambda pid: pid in {100, 101},
    )
    monkeypatch.setattr(preflight_runtime, "is_runtime_running", lambda: True)
    monkeypatch.setattr(
        preflight_runtime,
        "_port_is_listening",
        lambda port: port == 8080,
    )

    with pytest.raises(preflight_runtime.PreflightError) as error:
        preflight_runtime._assert_clean_shutdown(
            runtime_was_started=True,
            stop_result={"status": "success", "message": "Runtime stopped gracefully"},
            runtime_pid=100,
            node_pids={101, 102},
            simulator_pid=103,
        )

    message = str(error.value)
    assert "node processes still alive: [101]" in message
    assert "runtime process still alive: 100" in message
    assert "runtime status still reports running" in message
    assert "runtime PID file still exists" in message
    assert "TCP ports still listening: [8080]" in message
