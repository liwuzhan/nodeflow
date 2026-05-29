import sys
from pathlib import Path
import importlib.util

MODULE_PATH = Path(__file__).parent.parent / "atom.py"
spec = importlib.util.spec_from_file_location("track_controller_atom", MODULE_PATH)
atom = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(atom)

compute_velocity_cmd = atom.compute_velocity_cmd


def test_turn_preview_slows_linear_speed():
    pose = {"x": 0.0, "y": 0.0, "theta": 0.0}
    npkt = {
        "x": 3.0,
        "y": 0.0,
        "final": False,
        "mode": "tracking",
        "in_view_count": 3,
        "upcoming_turn_angle_deg": 180.0,
    }

    cmd = compute_velocity_cmd(
        pose, npkt,
        max_speed=2.0,
        min_speed=0.0,
        kp=2.0,
        max_w=1.0,
        pivot_th=20.0,
        decel_start_dist=3.0,
        final_stop_dist=0.5,
        now=1.0,
    )

    assert cmd["linear_velocity"] == 0.7
    assert cmd["turn_factor"] == 0.35
    assert cmd["status"] == "slowdown"


def test_low_view_slows_without_turn_preview():
    pose = {"x": 0.0, "y": 0.0, "theta": 0.0}
    npkt = {
        "x": 4.0,
        "y": 0.0,
        "final": False,
        "mode": "tracking",
        "in_view_count": 1,
        "upcoming_turn_angle_deg": 0.0,
    }

    cmd = compute_velocity_cmd(
        pose, npkt,
        max_speed=2.0,
        min_speed=0.0,
        kp=2.0,
        max_w=1.0,
        pivot_th=20.0,
        decel_start_dist=3.0,
        final_stop_dist=0.5,
        now=1.0,
    )

    assert cmd["linear_velocity"] == 0.9
    assert cmd["view_factor"] == 0.45
    assert cmd["status"] == "slowdown"


def test_path_progress_speed_limit_caps_segment_speed():
    pose = {"x": 0.0, "y": 0.0, "theta": 0.0}
    npkt = {
        "x": 5.0,
        "y": 0.0,
        "final": False,
        "mode": "tracking",
        "in_view_count": 4,
    }
    progress = {
        "motion": {"speed_limit_mps": 0.5},
        "cross_track_error_m": 0.0,
    }

    cmd = compute_velocity_cmd(
        pose, npkt,
        max_speed=2.0,
        min_speed=0.0,
        kp=2.0,
        max_w=1.0,
        pivot_th=20.0,
        decel_start_dist=3.0,
        final_stop_dist=0.5,
        now=1.0,
        path_progress=progress,
    )

    assert cmd["linear_velocity"] == 0.5
    assert cmd["segment_speed_limit_mps"] == 0.5
    assert cmd["speed_limit_factor"] == 0.25


def test_cross_track_error_keeps_low_recovery_speed():
    pose = {"x": 0.0, "y": 0.0, "theta": 0.0}
    npkt = {
        "x": 5.0,
        "y": 0.0,
        "final": False,
        "mode": "tracking",
        "in_view_count": 4,
    }
    progress = {
        "motion": {"speed_limit_mps": 2.0},
        "cross_track_error_m": 2.0,
    }

    cmd = compute_velocity_cmd(
        pose, npkt,
        max_speed=2.0,
        min_speed=0.0,
        kp=2.0,
        max_w=1.0,
        pivot_th=20.0,
        decel_start_dist=3.0,
        final_stop_dist=0.5,
        now=1.0,
        path_progress=progress,
    )

    assert cmd["linear_velocity"] == 0.3
    assert cmd["cte_factor"] == 0.15
    assert cmd["cross_track_recovery_factor"] == 0.15


def test_headland_turn_uses_path_heading_for_alignment():
    pose = {"x": 0.0, "y": 0.0, "theta": 0.0}
    npkt = {
        "x": 5.0,
        "y": 0.0,
        "final": False,
        "mode": "tracking",
        "in_view_count": 4,
    }
    progress = {
        "segment_type": "headland_turn",
        "path_heading_rad": 1.57079632679,
        "heading_error_deg": 90.0,
        "motion": {"speed_limit_mps": 0.5},
        "cross_track_error_m": 0.0,
    }

    cmd = compute_velocity_cmd(
        pose, npkt,
        max_speed=2.0,
        min_speed=0.0,
        kp=0.1,
        max_w=1.0,
        pivot_th=20.0,
        decel_start_dist=3.0,
        final_stop_dist=0.5,
        now=1.0,
        path_progress=progress,
        headland_turn_heading_gain=2.0,
        headland_turn_align_threshold_deg=35.0,
        headland_turn_min_speed_factor=0.25,
    )

    assert cmd["linear_velocity"] == 0.0
    assert cmd["angular_velocity"] == 1.0
    assert cmd["status"] == "turn_align"
    assert cmd["target_mode"] == "path_heading"
    assert cmd["headland_turn"] is True
    assert cmd["heading_error_deg"] == 90.0


def test_headland_turn_creeps_after_heading_aligned():
    pose = {"x": 0.0, "y": 0.0, "theta": 0.0}
    npkt = {
        "x": 5.0,
        "y": 0.0,
        "final": False,
        "mode": "tracking",
        "in_view_count": 4,
    }
    progress = {
        "segment_type": "headland_turn",
        "path_heading_rad": 0.1,
        "motion": {"speed_limit_mps": 0.5},
        "cross_track_error_m": 0.0,
    }

    cmd = compute_velocity_cmd(
        pose, npkt,
        max_speed=2.0,
        min_speed=0.0,
        kp=0.1,
        max_w=1.0,
        pivot_th=20.0,
        decel_start_dist=3.0,
        final_stop_dist=0.5,
        now=1.0,
        path_progress=progress,
        headland_turn_heading_gain=2.0,
        headland_turn_align_threshold_deg=35.0,
        headland_turn_min_speed_factor=0.25,
    )

    assert round(cmd["linear_velocity"], 3) == 0.498
    assert round(cmd["angular_velocity"], 3) == 0.2
    assert cmd["status"] == "headland_turn"
    assert cmd["speed_factor"] == 0.25
