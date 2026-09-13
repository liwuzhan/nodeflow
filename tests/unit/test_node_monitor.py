"""
NodeMonitor 可靠性测试（W1-1 / W1-2）

覆盖:
1. 监控循环单轮异常不打死监控线程（F-1）
2. 重启回调失败进入重试调度，与节点崩溃共享 max_retries 预算（F-2）
"""

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from edge.runtime.config.models import RestartPolicy as RestartPolicyConfig
from edge.runtime.monitoring.node_monitor import NodeMonitor


class FakeProcess:
    """最小 Popen 替身：poll() 可控"""

    def __init__(self, pid=4242, exit_code=None):
        self.pid = pid
        self._exit_code = exit_code

    def poll(self):
        return self._exit_code

    def communicate(self, timeout=None):
        return ("", "fake stderr")


def _make_monitor(max_retries=3, callback=None):
    monitor = NodeMonitor(RestartPolicyConfig(max_retries=max_retries, backoff_ms=0))
    monitor.restart_callback = callback
    return monitor


class TestMonitorLoopExceptionGuard:
    """W1-1: 连续注入异常下崩溃检测不中断"""

    def test_loop_survives_repeated_tick_exceptions(self, monkeypatch):
        monkeypatch.setattr(time, "sleep", lambda *_: None)
        monitor = _make_monitor()
        monitor.running = True

        ticks = []

        def bad_tick():
            ticks.append(1)
            if len(ticks) >= 3:
                monitor.running = False
            raise RuntimeError("injected boom")

        monkeypatch.setattr(monitor, "_monitor_tick", bad_tick)
        monitor._monitor_loop()  # 必须正常返回而不是抛异常

        assert len(ticks) == 3, "监控循环应吞掉异常继续运行"

    def test_crash_detection_continues_after_exception(self, monkeypatch):
        """第一轮 _handle_node_crash 抛异常被循环吞掉，第二轮仍能检测到崩溃并入队重启"""
        monitor = _make_monitor(callback=lambda node_id: FakeProcess(pid=99))
        monitor.running = True
        monitor._original_handler = monitor._handle_node_crash

        state = {"failed_once": False, "ticks": 0}

        def crashing_handler(node_id, ret_code):
            if not state["failed_once"]:
                state["failed_once"] = True
                raise RuntimeError("injected crash-handler failure")
            monitor._original_handler(node_id, ret_code)

        monkeypatch.setattr(monitor, "_handle_node_crash", crashing_handler)

        def stop_after_two_ticks(_secs):
            state["ticks"] += 1
            if state["ticks"] >= 2:
                monitor.running = False

        monkeypatch.setattr(time, "sleep", stop_after_two_ticks)

        process = FakeProcess(exit_code=1)
        monitor.processes = {"n1": process}

        monitor._monitor_loop()  # 第一轮异常被吞，第二轮正常处理

        assert monitor.retry_tracker.get_retry_count("n1") == 1
        assert "n1" in monitor._pending_restarts
        assert "n1" not in monitor.processes


class TestRestartFailureRetryScheduling:
    """W1-2: 重启回调失败按退避重新入队，预算耗尽后 give up"""

    def test_callback_returning_none_is_rescheduled(self):
        monitor = _make_monitor(max_retries=3, callback=lambda node_id: None)

        monitor._execute_restart("n1")
        assert monitor.retry_tracker.get_retry_count("n1") == 1
        assert "n1" in monitor._pending_restarts

        monitor._pending_restarts.clear()
        monitor._execute_restart("n1")
        assert monitor.retry_tracker.get_retry_count("n1") == 2
        assert "n1" in monitor._pending_restarts

    def test_callback_exception_is_rescheduled(self):
        def exploding(node_id):
            raise RuntimeError("launch failed")

        monitor = _make_monitor(max_retries=3, callback=exploding)

        monitor._execute_restart("n1")
        assert monitor.retry_tracker.get_retry_count("n1") == 1
        assert "n1" in monitor._pending_restarts

    def test_give_up_after_budget_exhausted(self):
        """max_retries=1：一次崩溃 + 一次重启失败后 give up，不再入队"""
        monitor = _make_monitor(max_retries=1, callback=lambda node_id: None)

        # 模拟节点崩溃已消耗一次预算
        monitor.retry_tracker.record_failure("n1")
        assert not monitor.retry_tracker.can_retry("n1")

        monitor._execute_restart("n1")
        assert "n1" not in monitor._pending_restarts

    def test_retry_budget_shared_between_crash_and_restart(self, monkeypatch):
        """整轮流程：崩溃→重启失败→退避→再失败→预算耗尽 give up"""
        monkeypatch.setattr(time, "sleep", lambda *_: None)
        monitor = _make_monitor(max_retries=3, callback=lambda node_id: None)
        monitor.running = True

        process = FakeProcess(exit_code=1)
        monitor.processes = {"n1": process}

        # 第 1 轮：检测崩溃 → record_failure(1) → 入队
        monitor._monitor_tick()
        assert monitor.retry_tracker.get_retry_count("n1") == 1

        # 第 2 轮：执行重启（失败）→ record_failure(2) → 再入队
        monitor._pending_restarts["n1"] = 0  # 立即到期
        monitor._monitor_tick()
        assert monitor.retry_tracker.get_retry_count("n1") == 2

        # 第 3 轮：再失败 → record_failure(3) → 预算耗尽 give up
        monitor._pending_restarts["n1"] = 0
        monitor._monitor_tick()
        assert monitor.retry_tracker.get_retry_count("n1") == 3
        assert "n1" not in monitor._pending_restarts

        monitor.running = False


class TestSuccessfulRestart:
    def test_successful_restart_resets_start_time(self):
        new_process = FakeProcess(pid=777)

        monitor = _make_monitor(callback=lambda node_id: new_process)
        monitor._execute_restart("n1")

        assert monitor.processes["n1"] is new_process
        assert monitor.start_times["n1"] > 0
        assert "n1" not in monitor._pending_restarts


if __name__ == "__main__":
    raise SystemExit("Run via: python3 -m pytest tests/unit/test_node_monitor.py -q")
