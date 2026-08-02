#!/usr/bin/env python3
"""Run the software-only NodeFlow preflight before connecting real hardware."""

from __future__ import annotations

import argparse
import json
import math
import os
import signal
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Callable

import zmq

from edge.sdk.shared_buffer_lite import SharedBufferLite
from tools.cli.commands.runtime_cmd import (
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

    simulator: subprocess.Popen[Any] | None = None
    runtime_started = False
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
        return {
            "status": "ok",
            "config": str(config_path.relative_to(PROJECT_ROOT)),
            "graph_id": runtime_status.get("graph_id"),
            "required_buffers": len(buffer_payloads),
            "motion_distance_m": round(distance_m, 3),
            "last_linear_velocity_mps": velocity.get("linear_velocity"),
            "elapsed_seconds": round(time.monotonic() - started_at, 2),
        }
    finally:
        if runtime_started or is_runtime_running():
            stop_runtime()
        _stop_process_group(simulator)


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

