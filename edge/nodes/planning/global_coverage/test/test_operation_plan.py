import sys
from pathlib import Path

node_dir = Path(__file__).parent.parent
sys.path.insert(0, str(node_dir))

from utils.models import VehicleConfig
from utils.operation_plan import build_operation_plan, classify_path_zones
from utils.planner import smooth_polyline_corners


def test_classify_path_zones_marks_sharp_turn_as_transit():
    path = [(0.0, 0.0), (5.0, 0.0), (10.0, 0.0), (10.0, 5.0), (10.0, 10.0)]

    zones = classify_path_zones(
        path,
        turn_angle_threshold_deg=45.0,
        turn_zone_radius_m=1.0,
    )

    assert zones[0] == "transit"
    assert zones[-1] == "transit"
    assert zones[2] == "transit"
    assert "work" in zones


def test_build_operation_plan_contains_segments_and_intent():
    path = [(0.0, 0.0), (5.0, 0.0), (10.0, 0.0), (10.0, 5.0), (10.0, 10.0)]
    vehicle = VehicleConfig(implement_width_m=3.0, overlap_ratio=0.1)

    plan = build_operation_plan(
        task_id="task_001",
        path=path,
        vehicle=vehicle,
        timestamp=123.0,
        turn_angle_threshold_deg=45.0,
        turn_zone_radius_m=1.0,
    )

    assert plan["task_id"] == "task_001"
    assert plan["frame"] == "ENU"
    assert plan["path"] == path
    assert len(plan["path_zones"]) == len(path)
    assert plan["segments"]
    assert any(segment["type"] == "work" for segment in plan["segments"])
    assert any(segment["type"] == "headland_turn" for segment in plan["segments"])
    assert plan["summary"]["path_points"] == len(path)

    work_segment = next(segment for segment in plan["segments"] if segment["type"] == "work")
    turn_segment = next(segment for segment in plan["segments"] if segment["type"] == "headland_turn")

    assert work_segment["implement"]["pto"] == "on"
    assert work_segment["implement"]["hitch"] == "down"
    assert turn_segment["implement"]["pto"] == "off"
    assert turn_segment["implement"]["hitch"] == "up"


def test_classify_path_zones_marks_smoothed_turn_as_transit():
    path = smooth_polyline_corners(
        [(0.0, 0.0), (10.0, 0.0), (10.0, 10.0)],
        corner_radius_m=2.0,
        spacing_m=0.5,
        min_turn_angle_deg=35.0,
    )

    zones = classify_path_zones(
        path,
        turn_angle_threshold_deg=45.0,
        turn_zone_radius_m=2.0,
    )

    assert len(zones) == len(path)
    assert "transit" in zones[3:-3]


def test_build_operation_plan_preserves_explicit_transit_segments():
    path = [(0.0, 0.0), (5.0, 0.0), (6.0, 1.0), (6.0, 6.0)]
    zones = ["work", "transit", "transit", "work"]
    vehicle = VehicleConfig(implement_width_m=2.0)

    plan = build_operation_plan(
        task_id="spiral_001",
        path=path,
        path_zones=zones,
        vehicle=vehicle,
        timestamp=123.0,
        planner_metadata={"strategy": "contour_spiral"},
    )

    transit = next(segment for segment in plan["segments"] if segment["type"] == "transit")
    assert transit["implement"]["pto"] == "off"
    assert transit["implement"]["hitch"] == "up"
    assert plan["summary"]["transit_segment_count"] == 1
    assert plan["summary"]["planner"]["strategy"] == "contour_spiral"
