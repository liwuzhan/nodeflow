from edge.nodes.implement.tillage_controller.run import TillageStatus
from edge.nodes.planning.global_coverage.utils.models import ParcelData, VehicleConfig
from edge.nodes.planning.global_coverage.utils.operation_plan import build_operation_plan
from edge.nodes.planning.global_coverage.utils.planner import GlobalCoveragePlanner
from edge.nodes.planning.waypoint_selector.atom import WaypointSelector
from edge.nodes.planning.waypoint_selector.run import NextPoint


def test_public_hybrid_plan_retains_stage_speeds_and_wire_execution_fields():
    vehicle = VehicleConfig(implement_width_m=1.2, path_inset_m=.3,
                            work_min_turn_radius_m=4, work_max_curvature_rate_1pm2=.08)
    planner = GlobalCoveragePlanner()
    path = planner.plan(ParcelData([(0, 0), (40, 0), (40, 70), (0, 70)]), vehicle,
                        planning_strategy="wide_turn_boundary", path_point_spacing=.25)
    plan = build_operation_plan("hybrid", path, vehicle, 0, work_speed_mps=.8, turn_speed_mps=.5,
                                path_zones=planner.last_path_zones, planner_metadata=planner.last_plan_metadata)
    metadata = plan["summary"]["planner"]
    assert metadata["target_coverage_reached"]
    assert metadata["cleanup_pass_count"] > 0
    assert {stage["motion"]["speed_limit_mps"] for stage in metadata["execution_stages"]} == {.5, .8}
    selector = WaypointSelector()
    # Separate IPC outputs can arrive in either order. A bare global_path of
    # the same revision must not suppress the subsequent execution plan.
    selector.set_path({"task_id": "hybrid", "path": path})
    assert selector.set_path(plan) is not None
    start = planner.last_plan_metadata["start_pose"]
    target = selector.select({**start, "timestamp": 0})
    sent = NextPoint(**target).model_dump()
    assert sent["execution_progress"] == target["execution_progress"]
    assert sent["execution_phase"] == target["execution_phase"]
    assert sent["execution_stage_index"] == 0
    assert selector.set_path({"task_id": "hybrid", "path": path}) is None
    assert selector.set_path(plan) is None


def test_transport_feedback_confirmation_survives_status_output_schema():
    packet = {"state": "transport", "hitch_height": 0., "pto_on": False,
              "ready": False, "transport_ready": True, "pto_rpm": 0.,
              "state_elapsed_s": 2., "emergency_stop": False,
              "last_zone": "transit", "timestamp": 1.}
    assert TillageStatus(**packet).model_dump()["transport_ready"] is True
