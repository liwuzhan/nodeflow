import sys
from pathlib import Path

import pytest
from shapely.geometry import LineString, Point, Polygon
from shapely.ops import unary_union


node_dir = Path(__file__).parent.parent
sys.path.insert(0, str(node_dir))

from utils.contour_spiral import build_contour_spiral
from utils.models import ParcelData, VehicleConfig
from utils.planner import GlobalCoveragePlanner
from utils.safe_area import build_safe_area


def _work_sweep(result, implement_width_m):
    segments = []
    for index in range(len(result.path) - 1):
        if result.path_zones[index] != "work" or result.path_zones[index + 1] != "work":
            continue
        segments.append(LineString([result.path[index], result.path[index + 1]]))
    return unary_union([
        segment.buffer(implement_width_m * 0.5, cap_style=2, join_style=1)
        for segment in segments
    ])


def test_contour_spiral_covers_rectangular_field_without_pivot_rows():
    area = Polygon([(0, 0), (30, 0), (30, 20), (0, 20)])

    result = build_contour_spiral(
        area,
        implement_width_m=2.0,
        overlap_ratio=0.1,
        path_point_spacing_m=0.5,
    )

    assert result.path
    assert result.contour_count >= 4
    assert result.layer_count >= 4
    assert result.chain_count == 1
    assert result.work_connector_count > 0
    assert result.coverage_ratio >= 0.95
    assert result.unsafe_work_area_m2 <= 0.02
    assert result.curvature_constrained
    assert result.max_curvature_1pm <= (1.0 / 1.5) * 1.08
    assert result.effective_overlap_ratio >= 0.5
    assert "transit" in result.path_zones
    assert "work" in result.path_zones
    assert area.boundary.distance(Point(result.path[0])) <= 1.1


def test_large_work_radius_prefers_overlap_and_bounded_g2_turns():
    area = Polygon([(0, 0), (60, 0), (60, 36), (0, 36)])

    result = build_contour_spiral(
        area,
        implement_width_m=3.0,
        overlap_ratio=0.1,
        path_point_spacing_m=0.5,
        min_turn_radius_m=4.0,
        max_curvature_rate_1pm2=0.08,
    )

    assert result.coverage_ratio >= 0.97
    assert result.curvature_constrained
    assert result.achieved_min_turn_radius_m >= 4.0 / 1.08
    assert result.connector_max_curvature_rate_1pm2 <= 0.0801
    assert result.effective_overlap_ratio >= 0.5
    assert result.work_connector_count > result.transit_connector_count


def test_contour_spiral_preserves_hole_exclusion_and_routes_connectors_safely():
    hole = Polygon([(10, 7), (20, 7), (20, 13), (10, 13)])
    area = Polygon(
        [(0, 0), (30, 0), (30, 20), (0, 20)],
        [list(hole.exterior.coords)[:-1]],
    )

    result = build_contour_spiral(
        area,
        implement_width_m=2.0,
        overlap_ratio=0.1,
        path_point_spacing_m=0.5,
    )

    assert result.path
    assert result.chain_count >= 2
    assert result.transit_connector_count >= 1
    assert result.coverage_ratio >= 0.95
    assert result.unsafe_work_area_m2 <= 0.02

    for start, end in zip(result.path, result.path[1:]):
        assert area.buffer(1e-6).covers(LineString([start, end]))

    swept = _work_sweep(result, implement_width_m=2.0)
    assert swept.intersection(hole).area <= 0.02


def test_contour_spiral_handles_concave_safe_area():
    area = Polygon([
        (0, 0),
        (30, 0),
        (30, 8),
        (18, 8),
        (18, 20),
        (0, 20),
    ])

    result = build_contour_spiral(
        area,
        implement_width_m=2.0,
        overlap_ratio=0.1,
        path_point_spacing_m=0.5,
    )

    assert result.path
    assert result.coverage_ratio >= 0.95
    assert result.unsafe_work_area_m2 <= 0.02
    for start, end in zip(result.path, result.path[1:]):
        assert area.buffer(1e-6).covers(LineString([start, end]))


def test_double_spiral_routes_multiple_hole_chains_without_crossing_exclusions():
    first_hole = Point(16, 16).buffer(3.0, quad_segs=16)
    second_hole = Point(42, 28).buffer(4.0, quad_segs=16)
    area = Polygon(
        [(0, 0), (60, 0), (60, 42), (0, 42)],
        [
            list(first_hole.exterior.coords)[:-1],
            list(second_hole.exterior.coords)[:-1],
            [(27, 7), (35, 7), (35, 13), (27, 13)],
        ],
    )

    result = build_contour_spiral(
        area,
        implement_width_m=2.5,
        overlap_ratio=0.1,
        path_point_spacing_m=0.5,
    )

    assert result.coverage_ratio >= 0.95
    assert result.chain_count >= 3
    assert result.work_connector_count > 0
    assert result.transit_connector_count > 0
    for start, end in zip(result.path, result.path[1:]):
        assert area.buffer(1e-6).covers(LineString([start, end]))

    swept = _work_sweep(result, implement_width_m=2.5)
    exclusions = unary_union([first_hole, second_hole, Polygon([
        (27, 7), (35, 7), (35, 13), (27, 13),
    ])])
    assert swept.intersection(exclusions).area <= 0.02


def test_global_planner_selects_contour_strategy_and_exposes_metadata():
    parcel = ParcelData(
        outer=[(0, 0), (30, 0), (30, 20), (0, 20)],
        holes=[[(10, 7), (20, 7), (20, 13), (10, 13)]],
    )
    vehicle = VehicleConfig(
        implement_width_m=2.0,
        overlap_ratio=0.1,
        path_inset_m=0.5,
    )
    planner = GlobalCoveragePlanner()

    path = planner.plan(
        parcel,
        vehicle,
        path_point_spacing=0.5,
        planning_strategy="contour_spiral",
    )
    safe_area, _ = build_safe_area(parcel.to_dict(), vehicle)

    assert path
    assert len(planner.last_path_zones) == len(path)
    assert planner.last_plan_metadata["strategy"] == "contour_spiral"
    assert planner.last_plan_metadata["coverage_ratio"] >= 0.95
    for start, end in zip(path, path[1:]):
        assert safe_area.buffer(1e-6).covers(LineString([start, end]))


def test_global_planner_rejects_unknown_strategy():
    planner = GlobalCoveragePlanner()
    parcel = ParcelData(outer=[(0, 0), (10, 0), (10, 10), (0, 10)])

    with pytest.raises(ValueError, match="Unsupported planning strategy"):
        planner.plan(parcel, VehicleConfig(), planning_strategy="unknown")
