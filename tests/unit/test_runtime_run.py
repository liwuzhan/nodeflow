from runtime import main as runtime_main
from runtime.main import NodeFlowRuntime


def test_traditional_run_marks_running_before_start_dataflow(monkeypatch):
    runtime = NodeFlowRuntime("dummy.yaml", duration=1)
    observed = {}

    monkeypatch.setattr(runtime, "_initialize_framework", lambda: 0)

    def fake_start_dataflow():
        observed["running_at_start"] = runtime.running
        runtime.dataflow_running = True
        runtime.start_time = 0.0
        return True

    def fake_stop_dataflow():
        runtime.dataflow_running = False

    monkeypatch.setattr(runtime, "start_dataflow", fake_start_dataflow)
    monkeypatch.setattr(runtime, "stop_dataflow", fake_stop_dataflow)
    monkeypatch.setattr(runtime_main.time, "sleep", lambda _seconds: None)

    times = iter([0.0, 2.0])
    monkeypatch.setattr(runtime_main.time, "time", lambda: next(times, 2.0))

    assert runtime.run() == 0
    assert observed["running_at_start"] is True
