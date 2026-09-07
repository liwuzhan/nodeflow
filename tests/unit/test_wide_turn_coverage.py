"""Geometric contracts for continuous engaged skip-row coverage."""
import math

import pytest
from shapely import affinity
from shapely.geometry import LineString, MultiPolygon, Polygon, box

from edge.nodes.planning.global_coverage.utils import wide_turn


def make(field=None, **kwargs):
    return wide_turn.build_wide_turn_coverage(
        box(0, 0, 100, 28) if field is None else field,
        implement_width_m=1.2,
        overlap_ratio=0.1,
        min_turn_radius_m=4.0,
        **kwargs,
    )


def discrete_curvature(path):
    maximum = 0.0
    for a, b, c in zip(path, path[1:], path[2:]):
        ab, bc, ac = math.dist(a, b), math.dist(b, c), math.dist(a, c)
        if min(ab, bc, ac) <= 1e-9:
            continue
        cross = abs((b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0]))
        maximum = max(maximum, 2 * cross / (ab * bc * ac))
    return maximum


def test_every_row_is_visited_once_and_all_connectors_keep_working():
    result = make(path_point_spacing_m=0.25)
    assert sorted(result.row_order) == list(range(len(result.row_segments)))
    assert result.metadata["all_rows_visited"]
    assert result.metadata["visited_row_count"] == result.metadata["row_count"]
    assert result.metadata["turn_count"] == len(result.row_order) - 1
    assert result.metadata["min_skipped_row_jump"] > 1
    assert result.path_zones == ["work"] * len(result.path)
    assert result.metadata["transit_connector_count"] == 0
    path = LineString(result.path)
    for start, end in result.row_segments:
        assert LineString((start, end)).difference(path.buffer(1e-7)).length < 1e-6
    assert max(math.dist(a, b) for a, b in zip(result.path, result.path[1:])) <= 0.250001


@pytest.mark.parametrize("radius", [4.0, 6.0])
def test_sampled_curvature_and_exact_clothoid_bounds_agree(radius):
    result = wide_turn.build_wide_turn_coverage(
        box(0, 0, 100, 60), 1.2, 0.1,
        min_turn_radius_m=radius,
        max_curvature_rate_1pm2=0.03,
        path_point_spacing_m=0.25,
    )
    assert result.metadata["achieved_min_turn_radius_m"] >= radius
    assert result.metadata["max_curvature_1pm"] <= 1 / radius
    assert result.metadata["connector_max_curvature_rate_1pm2"] <= 0.03
    assert discrete_curvature(result.path) <= 1 / radius * 1.001


@pytest.mark.parametrize("angle", [0, 31, -72])
def test_implement_sweep_stays_inside_rotated_allowed_area(angle):
    field = affinity.translate(affinity.rotate(box(0, 0, 100, 28), angle), 230, -80)
    result = make(field)
    sweep = LineString(result.path).buffer(0.6, cap_style=2, join_style=1)
    assert sweep.difference(field).area < 1e-6
    actual_coverage = sweep.intersection(field).area / field.area
    assert result.metadata["coverage_ratio"] == pytest.approx(actual_coverage, abs=1e-7)
    assert 0.90 < actual_coverage < 1.0
    assert result.metadata["missed_work_area_m2"] == pytest.approx(field.area * (1 - actual_coverage))
    assert not result.metadata["coverage_complete"]


def test_convex_trapezoid_validates_turns_and_reports_remaining_wedges():
    field = Polygon([(0, 0), (100, 0), (95, 28), (5, 28)])
    result = make(field)
    assert LineString(result.path).buffer(0.6, cap_style=2).difference(field).area < 1e-6
    assert result.metadata["missed_work_area_m2"] > 100


def test_entry_reverses_the_complete_route_without_adding_unchecked_transit():
    forward = make()
    reverse = make(entry_point=forward.path[-1])
    assert reverse.path == list(reversed(forward.path))
    assert reverse.row_order == list(reversed(forward.row_order))
    assert reverse.metadata["coverage_ratio"] == forward.metadata["coverage_ratio"]
    assert reverse.path[0] == forward.path[-1]


@pytest.mark.parametrize("field", [
    Polygon([(0, 0), (100, 0), (100, 28), (0, 28)], holes=[[(40, 10), (50, 10), (50, 20), (40, 20)]]),
    Polygon([(0, 0), (100, 0), (100, 10), (10, 10), (10, 28), (0, 28)]),
    MultiPolygon([box(0, 0, 30, 30), box(40, 0, 70, 30)]),
])
def test_unsupported_geometry_is_rejected_instead_of_crossing_obstacles(field):
    with pytest.raises(ValueError, match="convex|without holes"):
        make(field)


def test_insufficient_width_or_headland_has_no_radius_reduction_fallback():
    with pytest.raises(ValueError, match="too narrow|cannot fit"):
        make(box(0, 0, 100, 8))
    with pytest.raises(ValueError, match="cannot fit"):
        make(headland_depth_m=1.0)
    with pytest.raises(ValueError, match="cannot fit|too narrow"):
        wide_turn.build_wide_turn_coverage(box(0, 0, 12, 12), 1.2, 0.1, min_turn_radius_m=6)


def test_missing_clothoid_dependency_is_reported(monkeypatch):
    monkeypatch.setattr(wide_turn, "SolveG2", None)
    with pytest.raises(RuntimeError, match="requires pyclothoids"):
        make()


def test_ordering_always_returns_every_row_or_no_route():
    for row_count in range(5, 60):
        jump = max(2, row_count // 4)
        order = wide_turn._row_order(row_count, jump, (row_count + 1) // 2)
        assert order is not None
        assert sorted(order) == list(range(row_count))
        assert all(abs(a - b) >= jump for a, b in zip(order, order[1:]))


def test_invalid_nonfinite_configuration_is_rejected():
    for name in ("path_point_spacing_m", "max_curvature_rate_1pm2", "headland_depth_m", "heading_deg"):
        with pytest.raises(ValueError, match="finite"):
            make(**{name: float("nan")})
