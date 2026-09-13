"""Exercise node loops when path progress stalls or drive calibration is enabled."""
import importlib.util
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from edge.nodes.io.pwm_driver import atom as pwm_atom
from edge.nodes.planning.waypoint_selector import run as selector_run


class _Finished(Exception):
    pass


def _run_selector(monkeypatch, frames, plan, params=None):
    current = [0]
    outputs = []

    class SDK:
        logger = Mock()

        def __init__(self, **kwargs):
            self.params = {"progress_target_lookahead_m": 2.5, **(params or {})}

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def create_input_port(self, name):
            def receive():
                if name == "operation_plan":
                    return plan if current[0] == 0 else None
                return frames[current[0]].get(name)
            return SimpleNamespace(recv_latest=receive)

        def create_output_port(self, name, **kwargs):
            return SimpleNamespace(send=lambda packet: outputs.append(dict(packet)))

    def step(_seconds):
        current[0] += 1
        if current[0] == len(frames):
            raise _Finished

    monkeypatch.setattr(selector_run, "NodeFlowSDK", SDK)
    monkeypatch.setattr(selector_run, "time", SimpleNamespace(
        monotonic=lambda: frames[current[0]]["time"],
        time=lambda: frames[current[0]]["time"], sleep=step,
    ))
    with pytest.raises(_Finished):
        selector_run.main()
    return outputs


def test_expired_progress_stops_publishing_a_point_behind_the_vehicle(monkeypatch):
    plan = {"task_id": "line", "path": [(i * .5, 0) for i in range(101)]}
    frames = [{"time": i * .1, "pose_enu": {"x": i * .1, "y": 0, "theta": 0}}
              for i in range(41)]
    frames[0]["path_progress"] = {
        "task_id": "line", "path_index": 0, "segment_fraction": 0,
        "cross_track_error_m": 0,
    }
    outputs = _run_selector(monkeypatch, frames, plan)
    assert outputs[0]["x"] == outputs[4]["x"] == 2.5
    assert outputs[-1]["x"] > frames[-1]["pose_enu"]["x"]
    assert all(output["y"] == 0 for output in outputs)


def test_progress_can_resume_after_timeout(monkeypatch):
    plan = {"task_id": "line", "path": [(i * .5, 0) for i in range(101)]}
    progress = {"task_id": "line", "path_index": 0, "segment_fraction": 0}
    frames = [
        {"time": 0, "pose_enu": {"x": 0, "y": 0, "theta": 0}, "path_progress": progress},
        {"time": .6, "pose_enu": {"x": .2, "y": 0, "theta": 0}},
        {"time": .7, "pose_enu": {"x": .5, "y": 0, "theta": 0},
         "path_progress": {**progress, "path_index": 1}},
    ]
    outputs = _run_selector(monkeypatch, frames, plan)
    assert outputs[0]["x"] == 2.5
    assert outputs[1]["x"] != 2.5
    assert outputs[2]["x"] == 3.0


def test_progress_expiry_preserves_staged_work_and_transit_boundary(monkeypatch):
    plan = {
        "task_id": "corner", "path": [(0, 0), (5, 0), (10, 0), (10, 5)],
        "summary": {"planner": {"staged_execution": True, "execution_stages": [
            {"start_index": 0, "end_index": 2, "zone": "work", "speed_limit_mps": .5},
            {"start_index": 2, "end_index": 3, "zone": "transit", "speed_limit_mps": .5},
        ]}},
    }
    frames = [
        {"time": 0, "pose_enu": {"x": 8.9, "y": 0, "theta": 0, "timestamp": 0},
         "path_progress": {"task_id": "corner", "path_index": 2, "zone": "transit"}},
        {"time": .6, "pose_enu": {"x": 9.0, "y": 0, "theta": 0, "timestamp": .6}},
    ]
    outputs = _run_selector(monkeypatch, frames, plan)
    assert all(output["execution_stage_index"] == 0 for output in outputs)
    assert all(output["execution_progress"]["zone"] == "work" for output in outputs)
    assert all((output["x"], output["y"]) == (10, 0) for output in outputs)


def _run_pwm_once(monkeypatch, command):
    monkeypatch.setitem(sys.modules, "atom", pwm_atom)
    path = Path(__file__).resolve().parents[2] / "edge/nodes/io/pwm_driver/run.py"
    spec = importlib.util.spec_from_file_location("pwm_input_regression", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    statuses = []
    params = {"dry_run_mode": True, "angular_velocity_bias": .1,
              "pwm_deadzone_ns": 50000, "left_speed_scale": 1.1, "right_speed_scale": .9}
    sdk = SimpleNamespace(
        logger=Mock(), get_param=lambda name, default: params.get(name, default),
        create_input_port=lambda name: SimpleNamespace(recv_latest=lambda: command),
        create_output_port=lambda name: SimpleNamespace(send=statuses.append),
        set_on_input_lost=Mock(),
    )
    node = module.PWMDriverNode(sdk)
    node.latch_guard = SimpleNamespace(is_latched=lambda: False, close=lambda: None)
    writes = []
    node._write_pwm_ns = lambda left, right: writes.append((left, right))
    module.time = SimpleNamespace(time=lambda: 100.0, sleep=lambda _: setattr(node, "running", False))
    node.run()
    assert statuses, "The real PWM loop must have processed the command"
    return statuses[0], writes[0], node._pulse_to_duty_ns(node.pwm_center_ns)


@pytest.mark.parametrize("status", [None, "arrived", "needs_reposition", "stage_stop",
                                    "waiting_for_implement", "waiting_for_implement_raise"])
def test_zero_velocity_is_neutral_even_with_bias_and_deadzone(monkeypatch, status):
    result, pulses, center = _run_pwm_once(monkeypatch, {
        "linear_velocity": 0.0, "angular_velocity": 0.0, "status": status,
    })
    assert pulses == (center, center)
    assert result["angular_velocity"] == 0.0
    assert result["left_wheel_speed"] == result["right_wheel_speed"] == 0.0


@pytest.mark.parametrize("linear,angular", [(.4, 0.0), (0.0, .2)])
def test_bias_is_retained_for_commanded_motion_and_pivot(monkeypatch, linear, angular):
    result, pulses, center = _run_pwm_once(monkeypatch, {
        "linear_velocity": linear, "angular_velocity": angular,
    })
    assert result["angular_velocity"] == pytest.approx(angular + .1)
    assert pulses != (center, center)


def test_explicit_safety_stop_still_overrides_nonzero_velocity(monkeypatch):
    result, pulses, center = _run_pwm_once(monkeypatch, {
        "linear_velocity": .4, "angular_velocity": .2, "safety_stop": True,
    })
    assert pulses == (center, center)
    assert result["safety_stop"] is True
