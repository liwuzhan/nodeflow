"""Retained replay ground uses observed work and never future task coverage."""

import copy
import math
import threading

import pytest
from shapely.geometry import Point, Polygon
from shapely.ops import unary_union

from edge.nodes.observability.trajectory_viz import web_server
from edge.nodes.observability.trajectory_viz.replay_ground import build_replay_ground
from simulation.evaluation import CoverageAccumulator


FIELD = [(0, 0), (12, 0), (12, 10), (0, 10)]
HOLE = [(4, 4), (6, 4), (6, 6), (4, 6)]


def scene(**kwargs):
    return {"task_id": "A", "field_boundary": FIELD, "field_holes": [HOLE],
            "coverage_overlay": {"implement_width_m": 2, "implement_length_m": 0.6,
                                 "implement_offset_m": -0.4}, **kwargs}


def frame(x, *, time=1, y=5, theta=0, task="A", source="truth", **implement):
    return {"task_id": task, "timestamp": time, "primary_source": source,
            "status": "live", "stale_after_s": 1,
            source: {"x": x, "y": y, "theta": theta, "age_s": 0.1, "stale": False},
            "implement": {"pto_on": True, "hitch_height": 1,
                          "source": "simulation_truth", "age_s": 0.1,
                          "stale": False, **implement}}


def geometry(ground, through=None):
    return unary_union([Polygon(p["exterior"], p["holes"])
                        for segment in ground["segments"]
                        if through is None or segment["frame_index"] <= through
                        for p in segment["polygons"]])


def test_turning_sweep_matches_evaluator_and_preserves_field_holes():
    frames = [frame(2, time=1), frame(7, time=1.5, theta=math.pi / 3),
              frame(10, time=2, y=8, theta=math.pi / 2)]
    result = build_replay_ground(frames, scene())
    expected = CoverageAccumulator(FIELD, 2, field_holes=[HOLE],
                                    implement_length_m=0.6, implement_offset_m=-0.4)
    expected.extend([{**f["truth"], "working": True} for f in frames])
    actual = geometry(result)
    assert result["available"] and not result["estimated"]
    assert result["scope"] == "retained_replay"
    assert actual.symmetric_difference(expected.geometries()["covered"]).area < 1e-9
    assert actual.intersection(Polygon(HOLE)).area == 0
    assert not actual.difference(Polygon(FIELD)).area
    # The first replay frame has only its footprint, never the final sweep.
    assert geometry(result, through=0).area == pytest.approx(1.2)
    assert geometry(result, through=0).area < actual.area


@pytest.mark.parametrize("change", [
    {"pto_on": False}, {"hitch_height": 0.3}, {"stale": True},
    {"age_s": 2}, {"hitch_height": None}, {"source": "command"},
])
def test_nonworking_or_missing_feedback_does_not_join_work_footprints(change):
    frames = [frame(2, y=2), frame(5, time=1.2, y=2, **change),
              frame(8, time=1.4, y=2)]
    result = build_replay_ground(frames, scene())
    actual = geometry(result)
    assert actual.area == pytest.approx(2.4)
    assert not actual.intersects(Point(5, 2))
    assert [s["frame_index"] for s in result["segments"]] == [0, 2]


@pytest.mark.parametrize("middle", ["missing_pose", "stale_pose", "missing_implement", "other_task"])
def test_invalid_middle_observation_breaks_the_connection(middle):
    frames = [frame(2, y=2), frame(5, time=1.2, y=2), frame(8, time=1.4, y=2)]
    if middle == "missing_pose":
        frames[1]["truth"] = None
    elif middle == "stale_pose":
        frames[1]["truth"]["age_s"] = 1.2
    elif middle == "missing_implement":
        frames[1]["implement"] = None
    else:
        frames[1]["task_id"] = "B"
    assert geometry(build_replay_ground(frames, scene())).area == pytest.approx(2.4)


@pytest.mark.parametrize("change", ["gap", "time_reversal", "position_source", "implement_source"])
def test_time_gaps_and_source_changes_start_a_new_footprint(change):
    frames = [frame(2, y=2), frame(8, time=1.2, y=2)]
    if change == "gap":
        frames[1]["timestamp"] = 3
    elif change == "time_reversal":
        frames[1]["timestamp"] = 0.5
    elif change == "position_source":
        frames[1]["estimate"] = frames[1].pop("truth")
        frames[1]["primary_source"] = "estimate"
    else:
        frames[1]["implement"]["source"] = "feedback"
    assert geometry(build_replay_ground(frames, scene())).area == pytest.approx(2.4)


def test_retained_history_starts_at_its_first_frame_and_controller_is_labelled():
    frames = [frame(8, y=2, source="estimate"), frame(9, time=1.2, y=2, source="estimate")]
    for packet in frames:
        packet["implement"]["source"] = "controller_status"
    original = copy.deepcopy(frames)
    result = build_replay_ground(frames, scene())
    assert result["estimated"]
    assert result["position_source"] == "estimate"
    assert result["implement_source"] == "controller_status"
    assert result["segments"][0]["frame_index"] == 0
    assert geometry(result).bounds[0] == pytest.approx(7.3)
    assert "coverage_rate_percent" not in result
    assert frames == original


def test_known_nonworking_history_is_available_empty_ground():
    result = build_replay_ground([frame(2, pto_on=False)], scene())
    assert result["available"]
    assert result["segments"] == []


@pytest.mark.parametrize("data,reason", [
    ({"field_boundary": None}, "missing_field"),
    ({"coverage_overlay": None}, "missing_implement_dimensions"),
    ({"coverage_overlay": {"implement_width_m": float("nan")}}, "invalid_implement_dimensions"),
    ({"coverage_overlay": {"implement_width_m": -2}}, "invalid_implement_dimensions"),
    ({"coverage_overlay": {"implement_width_m": 2, "implement_length_m": 0}}, "invalid_implement_dimensions"),
    ({"field_holes": [[(50, 50), (51, 50), (51, 51), (50, 51)]]}, "invalid_field"),
])
def test_missing_or_invalid_geometry_is_an_unavailable_result(data, reason):
    result = build_replay_ground([frame(2)], scene(**data))
    assert not result["available"]
    assert result["reason"] == reason
    assert result["segments"] == []


def test_empty_or_unobserved_history_is_unavailable():
    assert build_replay_ground([], scene())["reason"] == "no_history"
    packet = frame(2)
    packet["implement"] = None
    assert build_replay_ground([packet], scene())["reason"] == "no_fresh_implement_observations"


def test_ground_is_opt_in_and_builds_outside_producer_lock(monkeypatch):
    monkeypatch.setattr(web_server.socketio, "emit", lambda *args, **kwargs: None)
    web_server.reset_monitor_data(max_history=2)
    try:
        web_server.update_trajectory_data(**scene())
        for x, time in ((1, 1), (2, 1.2), (3, 1.4)):
            web_server.update_monitor_frame(frame(x, time=time, y=2), record=True)
        with web_server.app.test_client() as client:
            normal = client.get("/api/monitor/replay").get_json()
            assert "ground" not in normal
            assert [f["truth"]["x"] for f in normal["frames"]] == [2, 3]
            response = client.get("/api/monitor/replay?ground=1")
            assert response.headers["Cache-Control"] == "no-store"
            payload = response.get_json()
            assert payload["frames"] == normal["frames"]
            assert payload["ground"]["segments"][0]["frame_index"] == 0

            def build_while_producer_updates(frames, scene_data):
                updater = threading.Thread(target=lambda: web_server.update_monitor_frame(
                    frame(4, time=1.6, y=2), record=True))
                updater.start()
                updater.join(timeout=1)
                assert not updater.is_alive(), "Replay geometry must not block observation updates"
                return build_replay_ground(frames, scene_data)

            monkeypatch.setattr(web_server, "build_replay_ground", build_while_producer_updates)
            snapshot = client.get("/api/monitor/replay?ground=1").get_json()
            assert snapshot["frames"] == normal["frames"]
            assert snapshot["ground"] == payload["ground"]
    finally:
        web_server.reset_monitor_data()
