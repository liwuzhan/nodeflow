"""规划目标、行走与机具在同一条作业路线上的衔接回归。"""

import importlib.util
import math
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]


def _load(name, relative_path):
    spec = importlib.util.spec_from_file_location(name, ROOT / relative_path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


waypoint = _load("operation_waypoint", "edge/nodes/planning/waypoint_selector/atom.py")
tillage = _load("operation_tillage", "edge/nodes/implement/tillage_controller/atom.py")
track = _load("operation_track", "edge/nodes/control/track_controller/atom.py")


def drive(pose, target, **options):
    return track.compute_velocity_cmd(
        pose, target, max_speed=1.0, min_speed=0.0, kp=2.0,
        max_w=1.0, pivot_th=20.0, decel_start_dist=3.0,
        final_stop_dist=0.5, now=10.0, **options,
    )


def make_working_controller(monkeypatch):
    clock = [0.0]
    monkeypatch.setattr(tillage.time, "time", lambda: clock[0])
    controller = tillage.TillageController(tillage.TillageConfig(auto_zone_detect=False))
    target = {"x": 10.0, "y": 0.0, "zone": "work", "final": False}
    controller.update(next_point=target)
    clock[0] = 3.0
    controller.update(next_point=target)
    assert controller.get_status()["ready"] is True
    return controller


def test_terminal_lookahead_keeps_working_until_actual_arrival(monkeypatch):
    """复现：距终点2.4米就选中 final，不能提前抬刀；到0.5米内才停。"""
    selector = waypoint.WaypointSelector(waypoint.ViewConfig(goal_tolerance=0.5))
    path = [(i * 0.5, 0.0) for i in range(21)]
    selector.set_path({"task_id": "straight", "path": path, "path_zones": ["work"] * len(path)})
    pose = {"x": 7.6, "y": 0.0, "theta": 0.0}
    progress = {
        "task_id": "straight", "path_index": 15, "segment_fraction": 0.2,
        "zone": "work", "segment_type": "work", "cross_track_error_m": 0.0,
        "implement": {"pto": "on", "hitch": "down"},
    }
    target = selector.select(pose, progress)
    assert target["final"] is True
    assert target["arrived"] is False
    assert target["goal_distance_m"] == pytest.approx(2.4)
    assert target["mode"] == "tracking"

    controller = make_working_controller(monkeypatch)
    implement_cmd = controller.update(pose=pose, next_point=target, path_progress=progress)
    assert implement_cmd["state"] == "working"
    assert implement_cmd["pto_on"] is True
    velocity = drive(
        pose, target, path_progress=progress, tillage_status=controller.get_status(),
        require_implement_ready=True,
    )
    assert velocity["linear_velocity"] > 0

    pose["x"] = 9.6
    progress.update(path_index=19, segment_fraction=0.2)
    target = selector.select(pose, progress)
    assert target["arrived"] is True
    assert target["mode"] == "finished"
    implement_cmd = controller.update(pose=pose, next_point=target, path_progress=progress)
    assert implement_cmd["state"] == "raising"
    assert implement_cmd["pto_on"] is False
    velocity = drive(pose, target, require_implement_ready=True)
    assert velocity["status"] == "arrived"
    assert velocity["linear_velocity"] == 0
    assert velocity["angular_velocity"] == 0


def test_closed_path_start_is_not_mistaken_for_completion():
    selector = waypoint.WaypointSelector(waypoint.ViewConfig(goal_tolerance=0.5))
    selector.set_path({"path": [(0, 0), (10, 0), (10, 10), (0, 0)]})
    target = selector.select(
        {"x": 0.0, "y": 0.0, "theta": 0.0},
        {"path_index": 0, "segment_fraction": 0.0, "cross_track_error_m": 0.0},
    )
    assert target["goal_distance_m"] == 0
    assert target["arrived"] is False


def test_legacy_final_without_arrived_uses_actual_distance(monkeypatch):
    controller = make_working_controller(monkeypatch)
    target = {"x": 10.0, "y": 0.0, "zone": "work", "final": True}
    cmd = controller.update(pose={"x": 7.6, "y": 0.0}, next_point=target)
    assert cmd["pto_on"] is True
    cmd = controller.update(pose={"x": 9.5, "y": 0.0}, next_point=target)
    assert cmd["pto_on"] is False
    assert cmd["state"] == "raising"


def test_broad_selector_arrival_does_not_raise_before_drive_stops(monkeypatch):
    controller = make_working_controller(monkeypatch)
    target = {"x": 10.0, "y": 0.0, "zone": "work", "final": True, "arrived": True}
    pose = {"x": 8.7, "y": 0.0, "theta": 0.0}
    # 旧图选择器的1.5米容差会提前报告 arrived，但机具应继续配合行走。
    assert drive(pose, target)["linear_velocity"] > 0
    cmd = controller.update(pose=pose, next_point=target)
    assert cmd["pto_on"] is True


def test_work_entry_waits_for_lowering_and_pto(monkeypatch):
    clock = [0.0]
    monkeypatch.setattr(tillage.time, "time", lambda: clock[0])
    controller = tillage.TillageController(tillage.TillageConfig(auto_zone_detect=False))
    pose = {"x": 0.0, "y": 0.0, "theta": 0.0}
    target = {"x": 3.0, "y": 0.0, "zone": "work", "final": False}
    for t in (0.0, 0.7, 1.5, 1.9):
        clock[0] = t
        controller.update(pose=pose, next_point=target)
        status = controller.get_status()
        assert status["ready"] is False
        command = drive(pose, target, tillage_status=status, require_implement_ready=True)
        assert command["status"] == "waiting_for_implement"
        assert command["linear_velocity"] == 0
    clock[0] = 2.01
    controller.update(pose=pose, next_point=target)
    command = drive(pose, target, tillage_status=controller.get_status(), require_implement_ready=True)
    assert command["linear_velocity"] > 0


@pytest.mark.parametrize("status", [None, {"state": "lowering", "pto_on": False},
    {"state": "working", "pto_on": True, "ready": False},
    {"state": "working", "pto_on": True, "ready": True, "emergency_stop": True}])
def test_missing_or_not_ready_implement_holds_work(status):
    command = drive(
        {"x": 0, "y": 0, "theta": 0}, {"x": 3, "y": 0, "zone": "work"},
        tillage_status=status, require_implement_ready=True,
    )
    assert command["status"] == "waiting_for_implement"
    assert command["linear_velocity"] == command["angular_velocity"] == 0


def test_unconnected_implement_is_optional_by_default():
    command = drive({"x": 0, "y": 0, "theta": 0}, {"x": 3, "y": 0, "zone": "work"})
    assert command["linear_velocity"] > 0


def test_in_soil_turn_stops_instead_of_pivot_but_transit_still_pivots():
    pose = {"x": 0, "y": 0, "theta": 0}
    target = {"x": 0, "y": 3, "zone": "work"}
    command = drive(pose, target)
    assert command["status"] == "needs_reposition"
    assert command["linear_velocity"] == command["angular_velocity"] == 0

    target["zone"] = "transit"
    command = drive(pose, target)
    assert command["status"] == "pivot"
    assert command["angular_velocity"] > 0

    # 仍在提升中的刀具，即使路线已进入 transit，也不能原地拧转。
    command = drive(pose, target, tillage_status={"state": "raising", "hitch_height": 0.5})
    assert command["status"] == "needs_reposition"


def test_work_intent_overrides_headland_transit_label():
    command = drive(
        {"x": 0, "y": 0, "theta": math.pi / 2}, {"x": 3, "y": 0, "zone": "transit"},
        path_progress={"segment_type": "headland_turn", "zone": "transit",
                       "implement": {"pto": "on", "hitch": "down"}},
    )
    assert command["status"] == "needs_reposition"


def test_old_work_pivot_can_be_explicitly_reproduced():
    command = drive(
        {"x": 0, "y": 0, "theta": 0}, {"x": 0, "y": 3, "zone": "work"},
        allow_work_pivot=True,
    )
    assert command["status"] == "pivot"


def test_simulation_graph_keeps_truth_out_of_control():
    import yaml

    graph = yaml.safe_load((ROOT / "configs/graphs/planning_simulation.yaml").read_text())
    nodes = {node["id"]: node for node in graph["nodes"]}
    assert nodes["sim_output"]["params"]["enable_state"] is True
    assert nodes["track_controller"]["params"]["require_implement_ready"] is True
    assert nodes["tillage_controller"]["params"]["require_implement_feedback"] is True
    assert nodes["waypoint_selector"]["params"]["goal_tolerance"] == nodes["track_controller"]["params"]["final_stop_distance"]
    truth_destinations = [edge["to"] for edge in graph["edges"] if edge["from"] == "sim_output.state_info"]
    assert truth_destinations == ["trajectory_viz.state_info"]
    assert any(edge["from"] == "sim_output.implement_state"
               and edge["to"] == "tillage_controller.implement_state" for edge in graph["edges"])


@pytest.mark.parametrize("feedback,age,expected_ready", [
    (None, 0.0, False),
    ({"hitch_height": 0.6, "pto_on": True, "pto_rpm": 540.0}, 0.1, False),
    ({"hitch_height": 1.0, "pto_on": True, "pto_rpm": 200.0}, 0.1, False),
    ({"hitch_height": 1.0, "pto_on": False, "pto_rpm": 540.0}, 0.1, False),
    ({"hitch_height": 1.0, "pto_on": True, "pto_rpm": 540.0}, 0.51, False),
    ({"hitch_height": 1.0, "pto_on": True, "pto_rpm": 540.0}, float("inf"), False),
    ({"hitch_height": float("nan"), "pto_on": True, "pto_rpm": 540.0}, 0.0, False),
    ({"hitch_height": 0.95, "pto_on": True, "pto_rpm": 480.0}, 0.1, True),
])
def test_logic_ready_requires_fresh_actual_hitch_and_pto(monkeypatch, feedback, age, expected_ready):
    controller = make_working_controller(monkeypatch)
    controller.config.require_implement_feedback = True
    status = controller.get_status(feedback, age)
    assert status["logical_ready"] is True
    assert status["ready_source"] == "feedback"
    assert status["ready"] is expected_ready
    command = drive(
        {"x": 0, "y": 0, "theta": 0}, {"x": 3, "y": 0, "zone": "work"},
        tillage_status=status, require_implement_ready=True,
    )
    if expected_ready:
        assert command["linear_velocity"] > 0
    else:
        assert command["status"] == "waiting_for_implement"
        assert command["linear_velocity"] == command["angular_velocity"] == 0


def test_drive_waits_for_simulated_implement_instead_of_controller_timer(monkeypatch):
    from simulation.physics import KinematicsEngine
    from simulation.state import RobotState

    # 逻辑控制器已经完成2秒计时，但实际机具仍在零位。
    controller = make_working_controller(monkeypatch)
    controller.config.require_implement_feedback = True
    physics = KinematicsEngine(dt=0.01, enable_slip=False, enable_terrain_noise=False, seed=0)
    state = RobotState(sim_time=0.0)
    target = {"x": 10, "y": 0, "zone": "work", "final": False}
    issued = controller.update(next_point=target)
    physics.set_implement_control(issued["hitch_height"], issued["pto_on"], issued["pto_rpm"])
    saw_wait = False
    saw_motion = False
    for _ in range(200):
        feedback = state.to_dict()["implement"]
        status = controller.get_status(feedback, feedback_age_s=0.01)
        assert status["logical_ready"] is True
        command = drive(
            {"x": state.x, "y": state.y, "theta": state.yaw}, target,
            tillage_status=status, require_implement_ready=True,
        )
        if not status["ready"]:
            saw_wait = True
            assert command["linear_velocity"] == 0
            assert state.x == 0.0
        else:
            assert state.hitch_height >= 0.95
            assert state.pto_rpm >= controller.config.pto_ready_rpm
            saw_motion = saw_motion or command["linear_velocity"] > 0
        physics.set_velocity_control(command["linear_velocity"], command["angular_velocity"])
        state = physics.step(state)
    assert saw_wait and saw_motion
    assert state.x > 0.0
