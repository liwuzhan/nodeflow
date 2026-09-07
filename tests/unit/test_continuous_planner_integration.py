from collections import deque

import pytest

from edge.nodes.planning.global_coverage import run as planner_node
from edge.nodes.planning.global_coverage.utils.models import ParcelData, VehicleConfig
from edge.nodes.planning.global_coverage.utils.operation_plan import build_operation_plan
from edge.nodes.planning.global_coverage.utils.planner import GlobalCoveragePlanner
from edge.nodes.planning.path_progress.atom import _path_stations, compute_progress
from simulation.coverage_experiment import run_coverage_experiment


def vehicle():
    return VehicleConfig(implement_width_m=1.2, overlap_ratio=.1, path_inset_m=.3,
                         work_min_turn_radius_m=4.0, work_max_curvature_rate_1pm2=.08, pivot_turn=False)


def test_public_planner_preserves_continuous_work_and_requested_radius():
    cfg = vehicle()
    planner = GlobalCoveragePlanner()
    path = planner.plan(ParcelData([(0, 0), (40, 0), (40, 70), (0, 70)]), cfg,
                        planning_strategy="wide_turn")
    plan = build_operation_plan("wide", path, cfg, 0, path_zones=planner.last_path_zones,
                                planner_metadata=planner.last_plan_metadata)
    assert plan["status"] == "success"
    assert all(s["implement"]["pto"] == "on" and s["implement"]["hitch"] == "down" for s in plan["segments"])
    assert planner.last_plan_metadata["achieved_min_turn_radius_m"] >= 4
    assert planner.last_plan_metadata["entry_manoeuvre_included"] is False
    assert planner.last_plan_metadata["all_rows_visited"]
    assert planner.last_plan_metadata["missed_work_area_m2"] > 0


def test_raw_nepath_candidate_is_not_an_online_strategy():
    with pytest.raises(ValueError, match="Unsupported"):
        GlobalCoveragePlanner().plan(ParcelData([(0, 0), (40, 0), (40, 70), (0, 70)]),
                                     vehicle(), planning_strategy="nepath_cfs_candidate")
    with pytest.raises(ValueError, match="Raw geometric"):
        run_coverage_experiment({"status": "success", "path": [(0, 0), (1, 0)],
                                 "summary": {"planner": {"execution_ready": False}}}, None, None)


def test_precomputed_stations_preserve_projection_and_segment_distance():
    path = [(0, 0), (2, 0), (4, 2), (4, 6)]
    plan = build_operation_plan("test", path, vehicle(), 0)
    for pose in ({"x": 1, "y": .2, "theta": 0}, {"x": 4, "y": 3, "theta": 1.5}):
        expected = compute_progress(plan, pose)
        assert compute_progress(plan, pose, path_stations=_path_stations(path)) == expected
    with pytest.raises(ValueError, match="path_stations"):
        compute_progress(plan, {"x": 1, "y": 0}, path_stations=[0])


def test_changed_task_consumed_during_broadcast_is_actually_planned(monkeypatch):
    """InputPort latest-value reads consume updates; the broadcast loop must retain one."""
    task = {"id": "field", "plan_revision": 0,
            "parcel": {"outer": [(0, 0), (40, 0), (40, 70), (0, 70)]},
            "vehicle": {"implement_width_m": 1.2, "work_min_turn_radius_m": 4,
                        "path_inset_m": .3, "pivot_turn": False}}
    events = deque([task, {**task, "plan_revision": 1}])
    outputs = {}

    class Input:
        def recv_latest(self):
            if events:
                return events.popleft()
            raise KeyboardInterrupt

    class Output:
        def __init__(self, name):
            self.name = name

        def send(self, data):
            outputs.setdefault(self.name, []).append(dict(data))

    class SDK:
        params = {"planning_strategy": "wide_turn"}
        # Match the SDK StructuredLogger single-message signature. Standard
        # logging also accepts positional formatting and can hide this mismatch.
        class Logger:
            def info(self, message):
                pass
            debug = warning = error = info
        logger = Logger()

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def create_input_port(self, name):
            return Input()

        def create_output_port(self, name, **kwargs):
            return Output(name)

    monkeypatch.setattr(planner_node, "NodeFlowSDK", lambda **kwargs: SDK())
    planner_node.main()
    assert [p["plan_revision"] for p in outputs["operation_plan"]] == [0, 1]
    assert all(p["status"] == "success" for p in outputs["operation_plan"])


def test_closed_loop_waits_for_real_implement_before_motion():
    cfg = vehicle()
    parcel = ParcelData([(0, 0), (20, 0), (20, 10), (0, 10)])
    path = [(2+i*.25, 5.) for i in range(49)]
    plan = build_operation_plan("straight", path, cfg, 0, path_zones=["work"]*len(path))
    result, rows = run_coverage_experiment(plan, parcel, cfg, duration_s=3)
    early = [r for r in rows if not r["implement_ready"]]
    assert early and all(r["command_v_mps"] == 0 for r in early)
    assert all(abs(r["true_x_m"]-2) < 1e-8 for r in early)
    assert any(r["implement_ready"] and r["true_v_mps"] > 0 for r in rows)
    assert result["metrics"]["completed"] is False
