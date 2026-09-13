"""Contracts for area-driven cleanup without changing the continuous main route."""
import math

import pytest
from shapely import affinity
from shapely.geometry import LineString, Polygon, box
from shapely.ops import unary_union

from edge.nodes.planning.global_coverage.utils.hybrid_coverage import (
    _edge_candidates,
    build_hybrid_coverage,
)
from edge.nodes.planning.global_coverage.utils.wide_turn import build_wide_turn_coverage


def make(field=None, **kwargs):
    return build_hybrid_coverage(
        box(0, 0, 56, 44) if field is None else field,
        1.2, 0.1, min_turn_radius_m=4, path_point_spacing_m=0.25, **kwargs,
    )


def test_cleanup_preserves_the_complete_continuous_main_route():
    field = box(0, 0, 56, 44)
    baseline = build_wide_turn_coverage(field, 1.2, 0.1, min_turn_radius_m=4,
                                       path_point_spacing_m=0.25)
    result = make(field)
    count = result.metadata["base_path_point_count"]
    assert result.path[:count] == baseline.path
    assert result.path_zones[:count] == ["work"] * count
    assert result.metadata["main_planner"] == baseline.metadata
    assert result.metadata["achieved_min_turn_radius_m"] >= 4
    assert result.metadata["coverage_ratio"] > baseline.metadata["coverage_ratio"]
    assert result.metadata["target_coverage_reached"]
    assert result.metadata["cleanup_pass_count"] >= 1
    assert result.metadata["boundary_layer_count"] > 1
    assert not result.metadata["coverage_complete"]


@pytest.mark.parametrize("angle", [0, 31, -72])
def test_every_stage_is_contiguous_and_work_rectangles_stay_inside(angle):
    field = affinity.translate(affinity.rotate(box(0, 0, 56, 44), angle), 130, -40)
    result = make(field)
    stages = result.metadata["execution_stages"]
    assert result.metadata["staged_execution"]
    assert len(result.path) == len(result.path_zones)
    assert all(0 < math.dist(a, b) <= 0.250001 for a, b in zip(result.path, result.path[1:]))
    assert stages[0]["start_index"] == 0
    assert stages[-1]["end_index"] == len(result.path)-1
    assert [stage["zone"] for stage in stages] == ["work"] + ["transit", "work"] * result.metadata["cleanup_pass_count"]
    for before, after in zip(stages, stages[1:]):
        assert before["end_index"] == after["start_index"]
    sweeps = [LineString(result.path[:result.metadata["base_path_point_count"]]).buffer(0.6, cap_style=2)]
    for stage in stages[1:]:
        start, end = stage["start_index"], stage["end_index"]
        points = result.path[start:end+1]
        line = LineString([points[0], points[-1]])
        assert line.buffer(1e-7).covers(LineString(points))
        assert field.buffer(1e-7).covers(line)
        if stage["zone"] == "transit":
            assert stage["requires_lift_before"]
            continue
        assert stage["requires_alignment_before"]
        theta = stage["work_heading_rad"]
        # Independent rectangle construction; flat caps extended by half of
        # the physical implement length, never rounded corner caps.
        extension = (0.1*math.cos(theta), 0.1*math.sin(theta))
        extended = LineString([(points[0][0]-extension[0], points[0][1]-extension[1]),
                               (points[-1][0]+extension[0], points[-1][1]+extension[1])])
        sweep = extended.buffer(0.6, cap_style=2)
        assert sweep.difference(field).area < 1e-6
        sweeps.append(sweep)
    covered = unary_union(sweeps).intersection(field).area
    assert result.metadata["coverage_ratio"] == pytest.approx(covered/field.area, abs=1e-8)
    assert result.metadata["missed_work_area_m2"] == pytest.approx(field.area-covered, abs=1e-6)


def test_first_layer_reaches_real_rectangular_corners_without_disk_caps():
    field = box(0, 0, 100, 28)
    candidates = _edge_candidates(field, 1.2, 0.2, 0.1, 1)
    assert len(candidates) == 4
    perimeter_sweep = unary_union([candidate.sweep for candidate in candidates])
    expected_ring = field.difference(field.buffer(-1.2, join_style=2))
    assert perimeter_sweep.symmetric_difference(expected_ring).area < 1e-5
    for corner in [box(0, 0, 0.2, 0.2), box(99.8, 0, 100, 0.2),
                   box(99.8, 27.8, 100, 28), box(0, 27.8, 0.2, 28)]:
        assert perimeter_sweep.intersection(corner).area == pytest.approx(corner.area, abs=1e-7)


def test_target_is_honest_when_layer_budget_or_minimum_gain_stops_cleanup():
    limited = make(target_coverage_ratio=1, max_boundary_layers=1)
    assert not limited.metadata["target_coverage_reached"]
    assert limited.metadata["cleanup_stop_reason"] == "candidate_layers_exhausted"
    assert limited.metadata["missed_work_area_m2"] > 0
    exhaustive = make(target_coverage_ratio=1)
    assert not exhaustive.metadata["target_coverage_reached"]
    assert exhaustive.metadata["cleanup_stop_reason"] == "no_positive_gain"
    assert exhaustive.metadata["coverage_ratio"] > limited.metadata["coverage_ratio"]
    assert exhaustive.metadata["missed_work_area_m2"] > 0


def test_already_satisfied_target_avoids_unnecessary_boundary_work():
    result = make(target_coverage_ratio=0.9)
    assert result.metadata["target_coverage_reached"]
    assert result.metadata["cleanup_pass_count"] == 0
    assert len(result.stages) == 1
    assert result.metadata["cleanup_work_length_m"] == 0
    assert result.metadata["cleanup_transit_length_m"] == 0


def test_coincident_boundary_endpoints_do_not_emit_zero_length_transit():
    # A square footprint lets adjacent perimeter passes share a corner center.
    # The controller raises/aligns on the work-stage transition itself.
    result = make(box(0, 0, 28, 100), implement_length_m=1.2,
                  target_coverage_ratio=1, max_boundary_layers=1)
    stages = result.metadata["execution_stages"]
    assert result.metadata["cleanup_pass_count"] == 4
    assert result.metadata["transit_connector_count"] < 4
    assert result.metadata["boundary_transit_count"] == sum(stage["zone"] == "transit" for stage in stages)
    assert all(stage["end_index"] > stage["start_index"] for stage in stages)
    assert all(math.dist(a, b) > 1e-6 for a, b in zip(result.path, result.path[1:]))
    adjacent_work = [(before, after) for before, after in zip(stages, stages[1:])
                     if before["zone"] == after["zone"] == "work"]
    assert adjacent_work
    for before, after in adjacent_work:
        assert before["end_index"] == after["start_index"]
        assert after["requires_lift_before"] and after["requires_alignment_before"]


def test_convex_sloping_sides_gain_coverage_without_rounding_into_excluded_area():
    result = make(Polygon([(0, 0), (100, 0), (95, 28), (5, 28)]))
    assert result.metadata["coverage_ratio"] >= 0.98
    assert result.metadata["cleanup_new_area_m2"] > 50
    assert result.metadata["unsafe_work_area_m2"] < 1e-6


@pytest.mark.parametrize("field", [
    Polygon([(0, 0), (100, 0), (100, 10), (10, 10), (10, 28), (0, 28)]),
    Polygon([(0, 0), (100, 0), (100, 28), (0, 28)], holes=[[(40, 10), (50, 10), (50, 20), (40, 20)]]),
])
def test_cleanup_does_not_relax_the_main_planners_geometry_boundary(field):
    with pytest.raises(ValueError, match="convex|without holes"):
        make(field)


@pytest.mark.parametrize("kwargs", [
    {"target_coverage_ratio": 0}, {"target_coverage_ratio": 1.01},
    {"target_coverage_ratio": float("nan")}, {"max_boundary_layers": -1},
    {"max_boundary_layers": 1.5}, {"implement_length_m": 0},
])
def test_invalid_cleanup_parameters_are_rejected(kwargs):
    with pytest.raises(ValueError):
        make(**kwargs)
