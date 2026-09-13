"""Coverage regression cases with independently known geometry."""

import importlib.util
import math
from pathlib import Path

import pytest
from shapely.geometry import Polygon

from simulation.evaluation import CoverageAccumulator, evaluate_coverage, is_working


FIELD = [(0, 0), (10, 0), (10, 10), (0, 10)]


def sample(x, y=5.0, theta=0.0, working=True):
    return {"x": x, "y": y, "theta": theta, "working": working}


def test_same_strip_repeated_ten_times_stays_twenty_percent():
    trace = [sample(0)]
    for _ in range(10):
        trace.extend([sample(10), sample(0)])
    result = evaluate_coverage(trace, FIELD, 2.0)
    assert result["covered_area_m2"] == pytest.approx(20)
    assert result["coverage_rate_percent"] == pytest.approx(20)
    assert result["missed_area_m2"] == pytest.approx(80)
    assert result["repeated_area_m2"] == pytest.approx(20)
    assert result["repeat_pass_area_m2"] > 300


def test_adjacent_footprint_overlap_and_stationary_dwell_are_not_repeated_passes():
    trace = [sample(x/100) for x in range(1001)]
    trace.extend([sample(10)] * 100)
    result = evaluate_coverage(trace, FIELD, 2.0, implement_length_m=1)
    assert result["covered_area_m2"] == pytest.approx(20)
    assert result["repeated_area_m2"] < 1e-7
    assert result["repeat_pass_area_m2"] < 1e-7


def test_field_holes_and_outside_do_not_count_as_coverage():
    hole = [(4, 4), (6, 4), (6, 6), (4, 6)]
    result = evaluate_coverage([sample(-2), sample(12)], FIELD, 2, field_holes=[hole])
    assert result["field_area_m2"] == pytest.approx(96)
    assert result["covered_area_m2"] == pytest.approx(16)
    assert result["outside_area_m2"] == pytest.approx(12.4)
    assert result["missed_area_m2"] == pytest.approx(80)
    result = evaluate_coverage([sample(20), sample(30)], FIELD, 2)
    assert result["covered_area_m2"] == 0


def test_work_requires_both_pto_and_completed_lowering():
    assert not is_working({"pto_on": True, "hitch_height": 0.4, "tillage_state": "lowering"})
    assert not is_working({"pto_on": False, "hitch_height": 1.0, "tillage_state": "working"})
    assert not is_working({"tillage_state": "working"})
    assert is_working({"pto_on": True, "hitch_height": 1.0})


def test_implement_heading_and_longitudinal_offset_are_applied():
    accumulator = CoverageAccumulator(FIELD, 2, implement_length_m=1, implement_offset_m=2)
    accumulator.add(sample(5, 5, math.pi/2))
    assert accumulator.geometries()["covered"].bounds == pytest.approx((4, 6.5, 6, 7.5))


def test_cumulative_batch_results_do_not_depend_on_display_window_or_batch_size():
    trace = [sample(0), sample(10), sample(0), sample(10)]
    small = CoverageAccumulator(FIELD, 2, batch_size=2).extend(trace)
    large = CoverageAccumulator(FIELD, 2, batch_size=1000)
    for point in trace:
        large.add(point)
        large.metrics()  # Frequent UI snapshots cannot change counting semantics.
    for key in ("covered_area_m2", "repeated_area_m2", "repeat_pass_area_m2"):
        assert large.metrics()[key] == pytest.approx(small.metrics()[key])
    assert large.metrics()["sample_count"] == 4


def test_missing_observation_breaks_connection_instead_of_covering_unknown_gap():
    accumulator = CoverageAccumulator(FIELD, 2)
    accumulator.add(sample(1))
    accumulator.break_segment()
    accumulator.add(sample(9))
    assert accumulator.metrics()["covered_area_m2"] == pytest.approx(0.8)


def test_turn_sweep_converges_with_spatial_and_angular_subdivision():
    trace = [sample(5, 5, 0), sample(5, 5, math.pi/2)]
    coarse = evaluate_coverage(trace, FIELD, 2, implement_length_m=1, implement_offset_m=2)
    fine = evaluate_coverage(trace, FIELD, 2, implement_length_m=1, implement_offset_m=2,
                             sample_angle_rad=math.radians(1))
    assert coarse["covered_area_m2"] == pytest.approx(fine["covered_area_m2"], rel=0.01)


@pytest.fixture
def viz_atom():
    path = Path(__file__).parents[2] / "edge/nodes/observability/trajectory_viz/atom.py"
    spec = importlib.util.spec_from_file_location("sweep_viz_atom", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_plan_intent_does_not_fabricate_actual_implement_feedback(viz_atom):
    value = viz_atom.make_replay_sample(
        pose={"x": 1, "y": 2},
        path_progress={"zone": "work", "implement": {"hitch": "down", "pto": "on"}},
    )
    assert value["planned_working"] is True
    assert value["pto_on"] is None
    assert value["implement_source"] == "unknown"
    assert not viz_atom.is_sample_working(value)


def test_truth_packets_override_observed_pose_and_command_state(viz_atom):
    value = viz_atom.make_replay_sample(
        pose={"x": 20, "y": 30}, tillage_cmd={"pto_on": True, "hitch_height": 1.0},
        truth_state={"position": {"x": 2, "y": 3}, "orientation": {"yaw": 0.5},
                     "implement": {"pto_on": False, "hitch_height": 0.0}},
    )
    assert (value["x"], value["y"], value["theta"]) == (2, 3, 0.5)
    assert value["position_source"] == value["implement_source"] == "simulation_truth"
    assert not viz_atom.is_sample_working(value)


def test_overlay_retains_cumulative_metrics_and_excludes_holes(viz_atom):
    hole = [(4, 4), (6, 4), (6, 6), (4, 6)]
    accumulator = CoverageAccumulator(FIELD, 2, field_holes=[hole]).extend([sample(0), sample(10)])
    result = viz_atom.build_coverage_overlay([sample(10)], 2, FIELD, field_holes=[hole],
                                              accumulator=accumulator)
    assert result["sample_count"] == 2
    assert result["display_sample_count"] == 1
    assert result["covered_area_m2"] == pytest.approx(16)
    for points in result["polygons"]:
        assert Polygon(points).intersection(Polygon(hole)).area < 1e-7
