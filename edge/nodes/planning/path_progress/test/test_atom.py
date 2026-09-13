import sys
from pathlib import Path
import importlib.util

node_dir = Path(__file__).parent.parent
sys.path.insert(0, str(node_dir))

spec = importlib.util.spec_from_file_location("path_progress_atom", node_dir / "atom.py")
path_progress_atom = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(path_progress_atom)

compute_progress = path_progress_atom.compute_progress
project_pose_to_path = path_progress_atom.project_pose_to_path


def test_project_pose_to_path_returns_cross_track_error():
    path = [(0.0, 0.0), (10.0, 0.0)]
    pose = {"x": 4.0, "y": 1.5, "theta": 0.0}

    projection = project_pose_to_path(pose, path)

    assert projection["path_index"] == 0
    assert projection["closest_x"] == 4.0
    assert projection["closest_y"] == 0.0
    assert projection["cross_track_error_m"] == 1.5


def test_project_pose_to_path_prefers_heading_consistent_parallel_row():
    path = [(0.0, 0.0), (10.0, 0.0), (10.0, 1.0), (0.0, 1.0)]
    pose = {"x": 5.0, "y": 0.6, "theta": 0.0}

    geometric_only = project_pose_to_path(
        pose, path, heading_match_weight_m=0.0
    )
    heading_aware = project_pose_to_path(
        pose, path, heading_match_weight_m=2.0
    )

    assert geometric_only["path_index"] == 2
    assert heading_aware["path_index"] == 0
    assert heading_aware["path_heading_rad"] == 0.0


def test_compute_progress_maps_pose_to_segment_and_intent():
    plan = {
        "task_id": "task_001",
        "path": [(0.0, 0.0), (10.0, 0.0), (10.0, 10.0)],
        "segments": [
            {
                "id": "row_001",
                "type": "work",
                "zone": "work",
                "start_index": 0,
                "end_index": 1,
                "motion": {"speed_limit_mps": 1.2},
                "implement": {"pto": "on", "hitch": "down"},
            },
            {
                "id": "turn_001",
                "type": "headland_turn",
                "zone": "transit",
                "start_index": 2,
                "end_index": 2,
                "motion": {"speed_limit_mps": 0.5},
                "implement": {"pto": "off", "hitch": "up"},
            },
        ],
    }

    progress = compute_progress(plan, {"x": 5.0, "y": 0.2, "theta": 0.0})

    assert progress["task_id"] == "task_001"
    assert progress["segment_id"] == "row_001"
    assert progress["segment_type"] == "work"
    assert progress["zone"] == "work"
    assert progress["motion"]["speed_limit_mps"] == 1.2
    assert progress["implement"]["pto"] == "on"
    assert progress["upcoming"]["next_segment_id"] == "turn_001"
    assert progress["distance_to_segment_end_m"] == 5.0


def test_compute_progress_handles_nested_path_points():
    plan = {
        "task_id": "task_002",
        "path": {"points": [(0.0, 0.0), (0.0, 10.0)]},
        "segments": [],
    }

    progress = compute_progress(plan, {"x": 0.4, "y": 2.0, "theta": 1.57079632679})

    assert progress["path_index"] == 0
    assert abs(progress["cross_track_error_m"] + 0.4) < 1e-6
    assert abs(progress["heading_error_deg"]) < 0.01


def test_compute_progress_relocalizes_when_local_window_is_wrong():
    plan = {
        "task_id": "task_003",
        "path": [(float(i), 0.0) for i in range(20)] + [(20.0, float(i)) for i in range(1, 21)],
        "segments": [
            {
                "id": "row_001",
                "type": "work",
                "zone": "work",
                "start_index": 0,
                "end_index": 19,
                "motion": {"speed_limit_mps": 1.2},
                "implement": {},
            },
            {
                "id": "turn_001",
                "type": "headland_turn",
                "zone": "transit",
                "start_index": 20,
                "end_index": 39,
                "motion": {"speed_limit_mps": 0.5},
                "implement": {},
            },
        ],
    }

    progress = compute_progress(
        plan,
        {"x": 20.2, "y": 15.0, "theta": 1.57},
        last_path_index=0,
        search_window=5,
        relocalize_error_m=2.0,
    )

    assert progress["relocalized"] is True
    assert progress["path_index"] >= 20
    assert abs(progress["cross_track_error_m"]) < 0.5
