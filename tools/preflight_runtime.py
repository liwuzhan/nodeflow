#!/usr/bin/env python3
"""Run the software-only NodeFlow preflight before connecting real hardware."""

from __future__ import annotations

import argparse
import json
import math
import os
import signal
import socket
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Callable

import zmq

from edge.sdk.shared_buffer_lite import SharedBufferLite
from tools.cli.commands.runtime_cmd import (
    PID_FILE,
    bootstrap_buffers_dir,
    get_runtime_pid,
    is_runtime_running,
    start_dataflow,
    start_runtime,
    stop_runtime,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG = PROJECT_ROOT / "configs" / "graphs" / "planning_simulation.yaml"
SIMULATOR_LOG = Path("/tmp/nodeflow_preflight_simulator.log")
RUNTIME_LOG = Path("/tmp/nodeflow_runtime.log")

REQUIRED_BUFFERS = (
    "sim_output.rtk_fix",
    "coord_transform.task_enu",
    "coord_transform.pose_enu",
    "global_coverage.global_path",
    "global_coverage.operation_plan",
    "path_progress.progress_state",
    "waypoint_selector.next_point",
    "track_controller.velocity_cmd",
    "tillage_controller.tillage_status",
)


class PreflightError(RuntimeError):
    pass


def _wait_for(
    predicate: Callable[[], Any],
    timeout: float,
    description: str,
    interval: float = 0.2,
) -> Any:
    deadline = time.monotonic() + timeout
    last_error: Exception | None = None
    while time.monotonic() < deadline:
        try:
            value = predicate()
            if value:
                return value
        except Exception as exc:  # Transient startup states are expected.
            last_error = exc
        time.sleep(interval)
    suffix = f"; last error: {last_error}" if last_error else ""
    raise PreflightError(f"Timed out waiting for {description}{suffix}")


def _request_simulator(payload: dict[str, Any], timeout_ms: int = 500) -> dict[str, Any] | None:
    context = zmq.Context()
    socket = context.socket(zmq.REQ)
    socket.setsockopt(zmq.RCVTIMEO, timeout_ms)
    socket.setsockopt(zmq.SNDTIMEO, timeout_ms)
    socket.setsockopt(zmq.LINGER, 0)
    socket.connect("tcp://127.0.0.1:5555")
    try:
        socket.send_json(payload)
        return socket.recv_json()
    except zmq.ZMQError:
        return None
    finally:
        socket.close()
        context.term()


def _read_buffer(name: str) -> dict[str, Any] | None:
    buffer = SharedBufferLite(name, create=False)
    try:
        value = buffer.read()
        return value if isinstance(value, dict) else None
    finally:
        buffer.close()


def _runtime_status() -> dict[str, Any] | None:
    return _read_buffer("runtime.status")


def _tail(path: Path, lines: int = 50) -> str:
    if not path.exists():
        return ""
    content = path.read_text(encoding="utf-8", errors="replace").splitlines()
    return "\n".join(content[-lines:])


def _stop_process_group(process: subprocess.Popen[Any] | None) -> None:
    if process is None or process.poll() is not None:
        return
    try:
        os.killpg(os.getpgid(process.pid), signal.SIGTERM)
        process.wait(timeout=5)
    except (ProcessLookupError, subprocess.TimeoutExpired):
        if process.poll() is None:
            try:
                os.killpg(os.getpgid(process.pid), signal.SIGKILL)
            except ProcessLookupError:
                pass
            process.wait(timeout=2)


def _process_table() -> dict[int, int]:
    """Return the current PID -> PPID mapping from the operating system."""
    result = subprocess.run(
        ["ps", "-Ao", "pid=,ppid="],
        capture_output=True,
        text=True,
        timeout=3,
    )
    if result.returncode != 0:
        raise PreflightError(f"Could not inspect process table: {result.stderr.strip()}")

    processes: dict[int, int] = {}
    for line in result.stdout.splitlines():
        fields = line.split()
        if len(fields) < 2:
            continue
        try:
            processes[int(fields[0])] = int(fields[1])
        except ValueError:
            continue
    return processes


def _descendant_pids(root_pid: int) -> set[int]:
    """Find every current descendant of a managed runtime process."""
    processes = _process_table()
    descendants: set[int] = set()
    pending = [root_pid]
    while pending:
        parent = pending.pop()
        children = {pid for pid, ppid in processes.items() if ppid == parent}
        new_children = children - descendants
        descendants.update(new_children)
        pending.extend(new_children)
    return descendants


def _pid_is_alive(pid: int) -> bool:
    """Check a PID without signalling it, treating zombies as exited."""
    result = subprocess.run(
        ["ps", "-p", str(pid), "-o", "stat="],
        capture_output=True,
        text=True,
        timeout=2,
    )
    state = result.stdout.strip()
    return result.returncode == 0 and bool(state) and not state.startswith("Z")


def _port_is_listening(port: int) -> bool:
    """Probe NodeFlow's IPv4 loopback endpoint without external utilities."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.settimeout(0.3)
        return probe.connect_ex(("127.0.0.1", port)) == 0


def _expected_node_count(config_path: Path) -> int:
    """Read the number of nodes the graph promises to launch."""
    import yaml

    config = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    nodes = config.get("nodes")
    if not isinstance(nodes, list) or not nodes:
        raise PreflightError(f"Graph contains no nodes: {config_path}")
    return len(nodes)


def _assert_clean_shutdown(
    *,
    runtime_was_started: bool,
    stop_result: dict[str, Any] | None,
    runtime_pid: int | None,
    node_pids: set[int],
    simulator_pid: int | None,
) -> dict[str, Any]:
    """Enforce the process, PID-file, and port cleanup contract."""
    errors: list[str] = []

    if runtime_was_started:
        if not stop_result or stop_result.get("status") != "success":
            errors.append(f"runtime stop failed: {stop_result}")
        elif stop_result.get("message") != "Runtime stopped gracefully":
            errors.append(f"runtime did not stop gracefully: {stop_result.get('message')}")

    alive_nodes = sorted(pid for pid in node_pids if _pid_is_alive(pid))
    if alive_nodes:
        errors.append(f"node processes still alive: {alive_nodes}")
    if runtime_pid is not None and _pid_is_alive(runtime_pid):
        errors.append(f"runtime process still alive: {runtime_pid}")
    if simulator_pid is not None and _pid_is_alive(simulator_pid):
        errors.append(f"simulator process still alive: {simulator_pid}")
    if is_runtime_running():
        errors.append("runtime status still reports running")
    if PID_FILE.exists():
        errors.append(f"runtime PID file still exists: {PID_FILE}")

    listening_ports = [port for port in (5555, 8080) if _port_is_listening(port)]
    if listening_ports:
        errors.append(f"TCP ports still listening: {listening_ports}")

    if errors:
        raise PreflightError("Unclean shutdown: " + "; ".join(errors))

    return {
        "runtime_stop": "graceful" if runtime_was_started else "not_started",
        "runtime_pid_exited": runtime_pid is None or not _pid_is_alive(runtime_pid),
        "node_processes_checked": len(node_pids),
        "node_processes_exited": True,
        "simulator_pid_exited": simulator_pid is None or not _pid_is_alive(simulator_pid),
        "released_ports": [5555, 8080],
        "pid_file_removed": not PID_FILE.exists(),
        "no_residual_control_process": not is_runtime_running(),
    }


def run_preflight(
    config_path: Path = DEFAULT_CONFIG,
    startup_timeout: float = 60.0,
    motion_timeout: float = 12.0,
) -> dict[str, Any]:
    config_path = config_path.resolve()
    if not config_path.is_file():
        raise PreflightError(f"Config not found: {config_path}")
    if is_runtime_running():
        raise PreflightError("Runtime is already running; stop it before preflight")
    if _request_simulator({"type": "get_state"}, timeout_ms=200):
        raise PreflightError("Port 5555 already has a responding simulator")

    expected_node_count = _expected_node_count(config_path)
    simulator: subprocess.Popen[Any] | None = None
    runtime_started = False
    runtime_pid: int | None = None
    node_pids: set[int] = set()
    stop_result: dict[str, Any] | None = None
    result: dict[str, Any] | None = None
    run_error: Exception | None = None
    cleanup_error: Exception | None = None
    started_at = time.monotonic()
    try:
        with SIMULATOR_LOG.open("w", encoding="utf-8") as simulator_log:
            simulator = subprocess.Popen(
                [sys.executable, "simulation/server.py"],
                cwd=PROJECT_ROOT,
                stdout=simulator_log,
                stderr=subprocess.STDOUT,
                start_new_session=True,
                text=True,
            )

        simulator_state = _wait_for(
            lambda: _request_simulator({"type": "get_state"}),
            timeout=10,
            description="simulator response",
        )
        if simulator_state.get("status") != "ok":
            raise PreflightError(f"Simulator returned an error: {simulator_state}")

        start_result = start_runtime(str(config_path), background=True)
        if start_result.get("status") != "success":
            raise PreflightError(
                f"Runtime failed to initialize: {start_result}\n{_tail(RUNTIME_LOG)}"
            )
        runtime_started = True
        runtime_pid = int(start_result["pid"])

        command_result = start_dataflow()
        if command_result.get("status") != "success":
            raise PreflightError(f"Could not request dataflow start: {command_result}")

        def dataflow_started() -> dict[str, Any] | None:
            status = _runtime_status()
            if status and status.get("command_status") == "failed":
                raise PreflightError(f"Dataflow startup failed: {status.get('error')}")
            if status and status.get("dataflow_running"):
                return status
            return None

        runtime_status = _wait_for(
            dataflow_started,
            timeout=startup_timeout,
            description="all dataflow nodes to start",
        )

        # 数据流已启动：经 PID 文件把本进程定位到当前 run 的 buffer 目录（W2-2）
        bootstrap_buffers_dir()

        def all_node_processes_started() -> set[int] | None:
            descendants = _descendant_pids(runtime_pid)
            return descendants if len(descendants) >= expected_node_count else None

        node_pids = _wait_for(
            all_node_processes_started,
            timeout=5,
            description=f"{expected_node_count} runtime child processes",
        )

        buffer_payloads: dict[str, dict[str, Any]] = {}
        for buffer_name in REQUIRED_BUFFERS:
            buffer_payloads[buffer_name] = _wait_for(
                lambda name=buffer_name: _read_buffer(name),
                timeout=10,
                description=f"valid data in {buffer_name}",
            )

        first_pose = buffer_payloads["coord_transform.pose_enu"]

        def moved_pose() -> dict[str, Any] | None:
            pose = _read_buffer("coord_transform.pose_enu")
            if not pose:
                return None
            distance = math.hypot(
                float(pose.get("x", 0)) - float(first_pose.get("x", 0)),
                float(pose.get("y", 0)) - float(first_pose.get("y", 0)),
            )
            return pose if distance >= 0.05 else None

        final_pose = _wait_for(
            moved_pose,
            timeout=motion_timeout,
            description="simulated vehicle motion",
        )
        distance_m = math.hypot(
            float(final_pose["x"]) - float(first_pose["x"]),
            float(final_pose["y"]) - float(first_pose["y"]),
        )

        velocity = _read_buffer("track_controller.velocity_cmd") or {}
        result = {
            "status": "ok",
            "config": str(config_path.relative_to(PROJECT_ROOT)),
            "graph_id": runtime_status.get("graph_id"),
            "node_processes": len(node_pids),
            "required_buffers": len(buffer_payloads),
            "motion_distance_m": round(distance_m, 3),
            "last_linear_velocity_mps": velocity.get("linear_velocity"),
            "elapsed_seconds": round(time.monotonic() - started_at, 2),
        }
    except Exception as exc:
        run_error = exc
    finally:
        runtime_is_running = is_runtime_running()
        if runtime_pid is None and runtime_is_running:
            runtime_pid = get_runtime_pid()
        if runtime_pid is not None:
            try:
                node_pids.update(_descendant_pids(runtime_pid))
            except Exception as exc:
                cleanup_error = exc
        if runtime_started or runtime_is_running:
            try:
                stop_result = stop_runtime()
            except Exception as exc:
                cleanup_error = cleanup_error or exc
        try:
            _stop_process_group(simulator)
        except Exception as exc:
            cleanup_error = cleanup_error or exc

        try:
            shutdown = _assert_clean_shutdown(
                runtime_was_started=runtime_started,
                stop_result=stop_result,
                runtime_pid=runtime_pid,
                node_pids=node_pids,
                simulator_pid=simulator.pid if simulator is not None else None,
            )
        except Exception as exc:
            cleanup_error = cleanup_error or exc

    if run_error or cleanup_error:
        messages = []
        if run_error:
            messages.append(str(run_error))
        if cleanup_error:
            messages.append(str(cleanup_error))
        raise PreflightError("; cleanup: ".join(messages))

    if result is None:
        raise PreflightError("Preflight completed without a result")
    result["shutdown"] = shutdown
    return result


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Verify that the NodeFlow software stack can boot and move simulated state"
    )
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--startup-timeout", type=float, default=60.0)
    parser.add_argument("--motion-timeout", type=float, default=12.0)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    try:
        result = run_preflight(
            config_path=args.config,
            startup_timeout=args.startup_timeout,
            motion_timeout=args.motion_timeout,
        )
    except Exception as exc:
        result = {"status": "error", "message": str(exc)}
        if args.json:
            print(json.dumps(result, ensure_ascii=False, indent=2))
        else:
            print(f"Preflight failed: {exc}", file=sys.stderr)
        return 1

    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print("NodeFlow preflight passed")
        for key, value in result.items():
            if key != "status":
                print(f"  {key}: {value}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
