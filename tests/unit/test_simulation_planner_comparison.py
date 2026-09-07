"""Guard comparison semantics that would otherwise hide bad candidate paths."""
import math

import pytest
from shapely.geometry import Polygon

from simulation.planner_comparison import (
    ComparisonSettings, compare_case, comparison_cases, evaluate_paths, sample_curvature,
)


def path(points):
    return {"points": points, "zones": ["work"]*len(points)}


def test_disconnected_candidates_do_not_cover_or_measure_the_missing_connector():
    field = Polygon([(0, 0), (20, 0), (20, 10), (0, 10)])
    paths = [path([(1, 5), (3, 5)]), path([(17, 5), (19, 5)])]
    metrics, geometry = evaluate_paths(paths, field, field, ComparisonSettings())
    assert metrics["total_distance_m"] == pytest.approx(4)
    assert metrics["unique_covered_area_m2"] == pytest.approx(2*2.2*1.2)
    assert metrics["unplanned_connections"] == 1
    assert not geometry["covered"].intersects(Polygon([(9, 4), (11, 4), (11, 6), (9, 6)]))


def test_work_and_whole_parcel_use_distinct_denominators():
    parcel = Polygon([(0, 0), (10, 0), (10, 10), (0, 10)])
    work = parcel.buffer(-1)
    metrics, _ = evaluate_paths([path([(2, 5), (8, 5)])], work, parcel, ComparisonSettings())
    assert metrics["work_area_m2"] == pytest.approx(64)
    assert metrics["parcel_area_m2"] == pytest.approx(100)
    assert metrics["coverage_rate_percent"] / metrics["parcel_coverage_rate_percent"] == pytest.approx(100/64)


def test_sampled_curvature_retains_sharp_corners_and_reversals():
    sharp = sample_curvature([path([(0, 0), (1, 0), (1, 1)])], 4)
    assert sharp["max_abs_curvature_1pm"] == pytest.approx(math.pi)
    assert sharp["local_turn_density_max_1pm"] == pytest.approx(math.pi/2)
    assert sharp["over_limit_sample_count"] == 1
    reverse = sample_curvature([path([(0, 0), (1, 0), (0, 0)])], 4)
    assert reverse["near_reversal_count"] == 1
    assert reverse["over_limit_sample_count"] == 1
    disjoint = sample_curvature([path([(0, 0), (1, 0)]), path([(1, 1), (0, 1)])], 4)
    assert disjoint["work_curvature_sample_count"] == 0


def test_collinear_midpoints_do_not_double_the_comparable_curvature_estimate():
    original = [(4*math.cos(index*math.pi/36), 4*math.sin(index*math.pi/36)) for index in range(19)]
    denser = []
    for first, second in zip(original, original[1:]):
        denser.extend([first, tuple((a+b)/2 for a, b in zip(first, second))])
    denser.append(original[-1])
    first = sample_curvature([path(original)], 4)
    second = sample_curvature([path(denser)], 4)
    assert second["local_turn_density_max_1pm"] == pytest.approx(2*first["local_turn_density_max_1pm"])
    assert second["max_abs_curvature_1pm"] == pytest.approx(first["max_abs_curvature_1pm"])


def test_rejections_and_missing_optional_dependencies_are_retained(monkeypatch):
    def fail(strategy, *_):
        if strategy == "wide_turn":
            raise ValueError("Hole fields are not supported")
        raise ModuleNotFoundError("Optional NEPath dependency is absent")
    monkeypatch.setattr("simulation.planner_comparison.generate_candidate", fail)
    report, _ = compare_case("hole", comparison_cases()["field_with_hole"], ComparisonSettings(),
                             ["wide_turn", "nepath_raw"])
    assert [result["status"] for result in report["results"]] == ["rejected", "unavailable"]
    assert all("error" in result and "metrics" not in result for result in report["results"])


def test_unknown_intent_is_not_silently_assumed_working():
    field = Polygon([(0, 0), (10, 0), (10, 10), (0, 10)])
    with pytest.raises(ValueError, match="explicit"):
        evaluate_paths([{"points": [(1, 1), (2, 1)], "zones": []}], field, field, ComparisonSettings())
