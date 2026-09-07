"""A hybrid route must actually lift and align between finishing strips."""
import math

import pytest

from edge.nodes.control.track_controller.atom import compute_velocity_cmd
from edge.nodes.implement.tillage_controller.atom import TillageConfig, TillageController
from edge.nodes.planning.global_coverage.utils.models import ParcelData, VehicleConfig
from edge.nodes.planning.global_coverage.utils.operation_plan import build_operation_plan
from edge.nodes.planning.waypoint_selector.atom import WaypointSelector
from simulation.coverage_experiment import run_coverage_experiment
from simulation.rtk_experiment import Experiment, _node_parameters


def _u_plan():
    vehicle = VehicleConfig(implement_width_m=1.2)
    path = ([(i*.25, 0.0) for i in range(41)]
            + [(10.0, j*.25) for j in range(1, 21)]
            + [(10.0-i*.25, 5.0) for i in range(1, 41)])
    metadata = {"staged_execution": True, "execution_stages": [
        {"start_index": 0, "end_index": 40, "zone": "work", "speed_limit_mps": .8},
        {"start_index": 40, "end_index": 60, "zone": "transit", "speed_limit_mps": .5},
        {"start_index": 60, "end_index": 100, "zone": "work", "speed_limit_mps": .8},
    ]}
    plan = build_operation_plan("stage-regression", path, vehicle, 0.0,
                                path_zones=["work"]*40+["transit"]*20+["work"]*41,
                                planner_metadata=metadata)
    return plan, vehicle


def test_staged_lookahead_stays_on_current_edge_despite_future_projection():
    plan, _ = _u_plan()
    selector = WaypointSelector()
    selector.set_path(plan)
    target = selector.select({"x": 9.0, "y": 0.0, "theta": 0.0, "timestamp": 0.0},
                             {"path_index": 90, "zone": "work"})
    assert (target["x"], target["y"]) == (10.0, 0.0)
    assert target["execution_progress"]["execution_stage_index"] == 0
    assert target["execution_progress"]["zone"] == "work"
    assert not target["final"]


def test_stage_endpoint_stops_before_aligning_next_stage():
    plan, _ = _u_plan()
    selector = WaypointSelector()
    selector.set_path(plan)
    pose = {"x": 9.98, "y": 0.0, "theta": 0.0, "timestamp": 0.0}
    target = selector.select(pose)
    assert target["execution_phase"] == "hold"
    assert target["execution_progress"]["implement"] == {"pto": "off", "hitch": "up"}
    assert selector.select({**pose, "timestamp": .2})["execution_phase"] == "hold"
    target = selector.select({**pose, "timestamp": .31})
    assert target["execution_phase"] == "align"
    assert target["execution_heading_rad"] == pytest.approx(math.pi/2)
    assert target["execution_stage_index"] == 1


def test_transit_waits_for_actual_raise_even_when_logical_state_is_transport():
    controller = TillageController(TillageConfig(require_implement_feedback=True), clock=lambda: 0)
    stale_physical_state = {"hitch_height": 1.0, "pto_on": True, "pto_rpm": 540.0}
    status = controller.get_status(stale_physical_state, feedback_age_s=0.0)
    assert status["state"] == "transport"
    assert status["transport_ready"] is False
    progress = {"zone": "transit", "implement": {"pto": "off", "hitch": "up"}}
    target = {"x": 0.0, "y": 2.0, "execution_phase": "align",
              "execution_heading_rad": math.pi/2, "execution_progress": progress}
    params, *_ = _node_parameters(Experiment())
    pose = {"x": 0.0, "y": 0.0, "theta": 0.0}
    command = compute_velocity_cmd(pose, target, now=0.0, tillage_status=status, **params)
    assert command["status"] == "waiting_for_implement_raise"
    assert command["linear_velocity"] == command["angular_velocity"] == 0.0
    lifted = {"hitch_height": 0.0, "pto_on": False, "pto_rpm": 0.0}
    for missing in lifted:
        partial = {key: value for key, value in lifted.items() if key != missing}
        assert not controller.get_status(partial, feedback_age_s=0.0)["transport_ready"]
    for key in ("hitch_height", "pto_rpm"):
        assert not controller.get_status({**lifted, key: -1.0}, feedback_age_s=0.0)["transport_ready"]
    assert not controller.get_status(lifted, feedback_age_s=10.0)["transport_ready"]
    status = controller.get_status(lifted, feedback_age_s=0.0)
    command = compute_velocity_cmd(pose, target, now=0.0, tillage_status=status, **params)
    assert command["status"] == "turn_align"
    assert command["linear_velocity"] == 0.0
    assert command["angular_velocity"] > 0.0


def test_execution_intent_overrides_geometric_work_projection():
    controller = TillageController(clock=lambda: 0.0)
    target = {"x": 0.0, "y": 1.0, "execution_phase": "align",
              "execution_progress": {"zone": "transit", "implement": {"pto": "off", "hitch": "up"}}}
    command = controller.update(pose={"x": 0, "y": 0, "theta": 0}, next_point=target,
                                path_progress={"zone": "work", "implement": {"pto": "on", "hitch": "down"}})
    assert command["state"] == "transport"
    assert command["pto_on"] is False


def test_u_route_finishes_and_never_commands_pivot_with_implement_down():
    plan, vehicle = _u_plan()
    parcel = ParcelData(outer=[(-2, -2), (12, -2), (12, 7), (-2, 7)])
    result, rows = run_coverage_experiment(plan, parcel, vehicle, duration_s=110)
    assert result["metrics"]["completed"]
    assert result["metrics"]["true_endpoint_error_m"] < .12
    assert result["metrics"]["true_cte_max_abs_m"] < .15
    assert result["metrics"]["mid_work_pto_disengagements"] == 1
    assert "stage_stop" in result["metrics"]["status_frames"]
    assert "waiting_for_implement_raise" in result["metrics"]["status_frames"]
    assert "needs_reposition" not in result["metrics"]["status_frames"]
    pivot_rows = [r for r in rows if r["status"] == "turn_align"]
    assert pivot_rows
    assert all(r["hitch_height"] <= .05 and not r["pto_on"] for r in pivot_rows)
    assert all(not (abs(r["command_v_mps"]) < .01 and abs(r["command_w_radps"]) > .01)
               for r in rows if r["hitch_height"] > .05 or r["pto_on"])


def test_stages_reject_gaps_and_reset_on_plan_revision():
    plan, _ = _u_plan()
    selector = WaypointSelector()
    selector.set_path(plan)
    pose = {"x": 9.98, "y": 0.0, "theta": 0.0, "timestamp": 0.0}
    selector.select(pose)
    assert selector.select({**pose, "timestamp": .31})["execution_stage_index"] == 1
    selector.set_path({**plan, "plan_revision": 1})
    assert selector.select({"x": 0, "y": 0, "theta": 0})["execution_stage_index"] == 0
    plan["summary"]["planner"]["execution_stages"][1]["start_index"] = 41
    with pytest.raises(ValueError, match="contiguous"):
        WaypointSelector().set_path(plan)
