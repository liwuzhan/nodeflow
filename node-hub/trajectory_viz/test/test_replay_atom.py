"""
Tests for trajectory replay samples and event detection.
"""

import sys
from pathlib import Path
import importlib.util

node_dir = Path(__file__).parent.parent
sys.path.insert(0, str(node_dir))

spec = importlib.util.spec_from_file_location("trajectory_viz_atom", node_dir / "atom.py")
trajectory_viz_atom = importlib.util.module_from_spec(spec)
spec.loader.exec_module(trajectory_viz_atom)

make_replay_sample = trajectory_viz_atom.make_replay_sample
detect_replay_events = trajectory_viz_atom.detect_replay_events
build_coverage_overlay = trajectory_viz_atom.build_coverage_overlay
summarize_coverage_samples = trajectory_viz_atom.summarize_coverage_samples


def test_make_replay_sample_collects_control_and_implement_state():
    sample = make_replay_sample(
        pose={"x": 1.0, "y": 2.0, "theta": 0.5},
        velocity_cmd={
            "linear_velocity": 0.8,
            "angular_velocity": 0.1,
            "status": "slowdown",
            "target_mode": "path_heading",
            "headland_turn": True,
            "speed_factor": 0.35,
            "turn_factor": 0.35,
        },
        next_point={
            "x": 5.0,
            "y": 2.5,
            "index": 12,
            "mode": "tracking",
            "in_view_count": 2,
            "upcoming_turn_angle_deg": 135.0,
            "zone": "transit",
        },
        tillage_status={
            "state": "raising",
            "pto_on": False,
            "hitch_height": 0.4,
            "pto_rpm": 0.0,
        },
        path_progress={
            "segment_id": "turn_001",
            "segment_type": "headland_turn",
            "zone": "transit",
            "cross_track_error_m": 0.2,
            "heading_error_deg": 8.0,
        },
        now=100.0,
    )

    assert sample["timestamp"] == 100.0
    assert sample["linear_velocity"] == 0.8
    assert sample["track_status"] == "slowdown"
    assert sample["target_mode"] == "path_heading"
    assert sample["headland_turn"] is True
    assert sample["upcoming_turn_angle_deg"] == 135.0
    assert sample["segment_id"] == "turn_001"
    assert sample["zone"] == "transit"
    assert sample["tillage_state"] == "raising"
    assert sample["pto_on"] is False
    assert sample["hitch_height"] == 0.4


def test_make_replay_sample_uses_operation_plan_intent_without_tillage_node():
    sample = make_replay_sample(
        pose={"x": 1.0, "y": 2.0, "theta": 0.5},
        path_progress={
            "segment_id": "row_001",
            "segment_type": "work",
            "zone": "work",
            "implement": {"pto": "on", "hitch": "down"},
        },
        now=100.0,
    )

    assert sample["tillage_state"] == "intent_working"
    assert sample["pto_on"] is True
    assert sample["hitch_height"] == 1.0


def test_detect_replay_events_on_state_changes():
    previous = {
        "timestamp": 10.0,
        "x": 1.0,
        "y": 1.0,
        "track_status": "",
        "next_mode": "tracking",
        "segment_id": "row_001",
        "tillage_state": "working",
        "pto_on": True,
        "upcoming_turn_angle_deg": 10.0,
    }
    current = {
        "timestamp": 11.0,
        "x": 2.0,
        "y": 1.5,
        "track_status": "slowdown",
        "next_mode": "approach",
        "segment_id": "turn_001",
        "tillage_state": "raising",
        "pto_on": False,
        "upcoming_turn_angle_deg": 90.0,
    }

    events = detect_replay_events(previous, current)
    kinds = {event["kind"] for event in events}

    assert "track_status" in kinds
    assert "waypoint_mode" in kinds
    assert "segment" in kinds
    assert "tillage_state" in kinds
    assert "pto" in kinds
    assert "turn_preview" in kinds
    assert all(event["x"] == 2.0 and event["y"] == 1.5 for event in events)


def test_build_coverage_overlay_counts_only_active_implement_segments():
    samples = [
        {
            "timestamp": 1.0,
            "x": 0.0,
            "y": 0.0,
            "pto_on": False,
            "hitch_height": 0.0,
            "tillage_state": "transport",
        },
        {
            "timestamp": 2.0,
            "x": 10.0,
            "y": 0.0,
            "pto_on": True,
            "hitch_height": 1.0,
            "tillage_state": "working",
        },
        {
            "timestamp": 3.0,
            "x": 20.0,
            "y": 0.0,
            "pto_on": True,
            "hitch_height": 1.0,
            "tillage_state": "working",
        },
    ]

    overlay = build_coverage_overlay(
        samples,
        implement_width_m=2.0,
        field_boundary=[(0.0, -5.0), (20.0, -5.0), (20.0, 5.0), (0.0, 5.0)],
    )

    assert overlay["implement_width_m"] == 2.0
    assert overlay["active_segments"] == 1
    assert overlay["sample_count"] == 3
    assert overlay["working_sample_count"] == 2
    assert overlay["working_sample_percent"] == 66.7
    assert overlay["latest_active"] is True
    assert overlay["latest_tillage_state"] == "working"
    assert len(overlay["polygons"]) == 1
    assert overlay["covered_area_m2"] == 20.0
    assert overlay["coverage_rate_percent"] == 10.0


def test_build_coverage_overlay_ignores_transport_only_samples():
    samples = [
        {"timestamp": 1.0, "x": 0.0, "y": 0.0, "pto_on": False, "hitch_height": 0.0},
        {"timestamp": 2.0, "x": 10.0, "y": 0.0, "pto_on": False, "hitch_height": 0.0},
    ]

    overlay = build_coverage_overlay(
        samples,
        implement_width_m=2.0,
        field_boundary=[(0.0, -5.0), (10.0, -5.0), (10.0, 5.0), (0.0, 5.0)],
    )

    assert overlay["active_segments"] == 0
    assert overlay["sample_count"] == 2
    assert overlay["working_sample_count"] == 0
    assert overlay["latest_active"] is False
    assert overlay["polygons"] == []
    assert overlay["covered_area_m2"] == 0.0


def test_summarize_coverage_samples_explains_zero_coverage():
    samples = [
        {"timestamp": 1.0, "x": 0.0, "y": 0.0, "tillage_state": "transport", "pto_on": False, "hitch_height": 0.0},
        {"timestamp": 2.0, "x": 1.0, "y": 0.0, "tillage_state": "lowering", "pto_on": False, "hitch_height": 0.3},
    ]

    summary = summarize_coverage_samples(samples)

    assert summary["sample_count"] == 2
    assert summary["working_sample_count"] == 1
    assert summary["working_sample_percent"] == 50.0
    assert summary["latest_active"] is True
    assert summary["latest_tillage_state"] == "lowering"
    assert summary["latest_pto_on"] is False
    assert summary["latest_hitch_height"] == 0.3
