import subprocess

import pytest

from edge.runtime.orchestrator.startup_coordinator import StartupCoordinator
from edge.runtime.utils.errors import NodeStartupError


class DummyLauncher:
    def __init__(self):
        self.launched = []

    def launch(self, node, manifest):
        self.launched.append(node.id)
        return subprocess.Popen(["python3", "-c", "import time; time.sleep(30)"])

    def terminate_process(self, process, node_id, timeout=5.0):
        process.terminate()
        try:
            process.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=1.0)


class FailingLauncher(DummyLauncher):
    def __init__(self, fail_node):
        super().__init__()
        self.fail_node = fail_node
        self.processes = {}
        self.terminated = []

    def launch(self, node, manifest):
        if node.id == self.fail_node:
            raise RuntimeError("launch failed")
        process = super().launch(node, manifest)
        self.processes[node.id] = process
        return process

    def terminate_process(self, process, node_id, timeout=5.0):
        self.terminated.append(node_id)
        super().terminate_process(process, node_id, timeout)


class DummyRegistry:
    def get_manifest(self, package):
        return {"name": package}


class DummyNode:
    def __init__(self, node_id, package="dummy"):
        self.id = node_id
        self.package = package


def test_startup_nodes_stops_before_next_layer_when_cancelled():
    launcher = DummyLauncher()
    coordinator = StartupCoordinator(launcher, DummyRegistry())
    cancel_checks = {"count": 0}

    def should_cancel():
        cancel_checks["count"] += 1
        return cancel_checks["count"] > 2

    processes = coordinator.startup_nodes(
        [["a"], ["b"]],
        {"a": DummyNode("a"), "b": DummyNode("b")},
        startup_timeout=0.01,
        startup_delay=0.01,
        should_cancel=should_cancel,
    )

    try:
        assert launcher.launched == ["a"]
        assert list(processes) == ["a"]
    finally:
        coordinator.shutdown_nodes(processes, shutdown_timeout=1.0)


def test_startup_failure_rolls_back_nodes_started_in_same_layer():
    launcher = FailingLauncher(fail_node="b")
    coordinator = StartupCoordinator(launcher, DummyRegistry())

    with pytest.raises(NodeStartupError):
        coordinator.startup_nodes(
            [["a", "b"]],
            {"a": DummyNode("a"), "b": DummyNode("b")},
            startup_timeout=0.01,
            startup_delay=0,
        )

    assert launcher.terminated == ["a"]
    assert launcher.processes["a"].poll() is not None
