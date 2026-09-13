"""Read-only farm monitor contracts, including stale observations and holes."""

import copy
import json
from types import SimpleNamespace

import pytest
from shapely.geometry import Polygon
from shapely.ops import unary_union

from edge.nodes.observability.trajectory_viz import atom, monitor, web_server
from simulation.evaluation import CoverageAccumulator


FIELD = [(0, 0), (10, 0), (10, 10), (0, 10)]
HOLE = [(4, 4), (6, 4), (6, 6), (4, 6)]
POSE = {"x": 2.0, "y": 3.0, "theta": 0.7, "timestamp": 1_000_000.0}


def frame(**kwargs):
    defaults = {"now_monotonic": 20.0, "timestamp": 1_000.0,
                "estimate": POSE, "estimate_received": 19.75}
    defaults.update(kwargs)
    return monitor.build_monitor_frame(**defaults)


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(web_server.socketio, "emit", lambda *args, **kwargs: None)
    web_server.reset_monitor_data()
    with web_server.app.test_client() as value:
        yield value
    web_server.reset_monitor_data()


def test_real_telemetry_does_not_create_truth_from_estimate_or_an_unconnected_packet():
    value = frame(truth=POSE, truth_received=19.9)
    assert value["mode"] == "telemetry"
    assert value["primary_source"] == "estimate"
    assert value["truth"] is None
    assert value["estimate"]["theta"] == 0.7
    assert value["status"] == "live"


def test_simulation_waits_for_truth_and_does_not_substitute_rtk():
    waiting = frame(truth_connected=True)
    assert waiting["status"] == "waiting"
    assert waiting["truth"] is None
    assert waiting["estimate"] is not None
    truth = {"position": {"x": 1, "y": 2, "z": 0.4},
             "orientation": {"yaw": 1.2, "pitch": 0.03, "roll": -0.02}}
    value = frame(truth_connected=True, truth=truth, truth_received=19.8)
    assert value["primary_source"] == "truth"
    assert (value["truth"]["x"], value["truth"]["theta"]) == (1, 1.2)
    assert value["truth"]["roll"] == -0.02


@pytest.mark.parametrize("pose", [
    {"x": 1, "y": 2},
    {"x": 1, "y": 2, "theta": None},
    {"x": 1, "y": 2, "theta": float("nan")},
    {**POSE, "heading_valid": False},
])
def test_missing_or_invalid_heading_never_becomes_zero(pose):
    assert not monitor.valid_pose(pose)
    value = frame(estimate=pose)
    assert value["estimate"] is None
    assert value["status"] == "waiting"
    json.dumps(value, allow_nan=False)


def test_age_uses_local_monotonic_receipt_not_source_time_or_wall_clock():
    first = frame()
    wall_jump = frame(timestamp=-1234)
    assert first["estimate"]["age_s"] == wall_jump["estimate"]["age_s"] == 0.25
    stale = frame(now_monotonic=21.5, timestamp=1)
    assert stale["status"] == "stale"
    assert stale["estimate"]["age_s"] == 1.75
    assert stale["estimate"]["x"] == first["estimate"]["x"]
    assert stale["estimate"]["theta"] == first["estimate"]["theta"]


def test_actual_implement_feedback_is_independent_of_commands():
    command = {"linear_velocity": 0.3, "angular_velocity": 0.1,
               "pto_on": True, "hitch_height": 1.0}
    value = frame(command=command, command_received=19.9)
    assert value["implement"] is None
    value = frame(command=command, command_received=19.9,
                  implement_feedback={"pto_on": False, "hitch_height": 0.2},
                  implement_received=19.8)
    assert value["implement"]["source"] == "feedback"
    assert value["implement"]["pto_on"] is False
    assert value["implement"]["hitch_height"] == 0.2
    assert value["command"]["linear_velocity"] == 0.3
    simulated = frame(truth_connected=True,
                      truth={**POSE, "implement": {"pto_on": False, "hitch_height": 0.0}},
                      truth_received=19.9,
                      implement_feedback={"pto_on": True, "hitch_height": 1.0},
                      implement_received=19.9)
    assert simulated["implement"]["source"] == "simulation_truth"
    assert simulated["implement"]["pto_on"] is False


def test_rtk_source_and_antenna_metadata_survive_with_elapsed_heading_age():
    raw = {"timestamp": 5_000.0, "heading_source": "THS", "heading_valid": False,
           "heading_mode": "dual_antenna", "heading_age_s": 0.4,
           "antenna_heading_deg": 181.0, "heading_offset_deg": 180.0,
           "rtk_quality": 4, "num_satellites": 28}
    value = frame(raw_rtk=raw, rtk_received=19.5)
    assert value["rtk"]["source"] == "raw_rtk"
    assert value["rtk"]["source_timestamp"] == 5_000.0
    assert value["rtk"]["heading_source"] == "THS"
    assert value["rtk"]["heading_valid"] is False
    assert value["rtk"]["heading_age_s"] == pytest.approx(0.9)
    assert value["rtk"]["antenna_heading_deg"] == 181.0
    assert value["rtk"]["heading_offset_deg"] == 180.0
    fallback = frame(estimate={**POSE, "heading_source": "THS"})
    assert fallback["rtk"]["source"] == "pose_enu"


def test_controller_status_stays_an_estimate_and_cannot_overwrite_hardware_feedback():
    status = {"pto_on": True, "hitch_height": 1.0, "ready_source": "feedback",
              "feedback_fresh": True}
    estimated = frame(implement_status=status, implement_status_received=19.9)
    assert estimated["implement"]["source"] == "controller_status"
    assert estimated["implement"]["estimated"] is True
    measured = frame(implement_status=status, implement_status_received=19.9,
                     implement_feedback={"pto_on": False, "hitch_height": 0.15},
                     implement_received=19.8)
    assert measured["implement"]["source"] == "feedback"
    assert measured["implement"]["estimated"] is False
    assert measured["implement"]["pto_on"] is False
    assert measured["implement"]["hitch_height"] == 0.15


def test_frame_api_starts_empty_and_never_caches(client):
    response = client.get("/api/monitor/frame")
    assert response.status_code == 200
    assert response.get_json() is None
    assert response.headers["Cache-Control"] == "no-store"


def test_http_ages_stopped_producer_without_mutating_saved_frame_or_replay(monkeypatch, client):
    clock = SimpleNamespace(now=100.0)
    monkeypatch.setattr(web_server, "time", SimpleNamespace(monotonic=lambda: clock.now))
    packet = frame(
        truth_connected=True, truth=POSE, truth_received=19.6,
        implement_feedback={"pto_on": False, "hitch_height": 0.2}, implement_received=19.8,
        target={"x": 5, "y": 6}, target_received=19.7,
        command={"linear_velocity": 0.3, "angular_velocity": 0.1}, command_received=19.9,
        raw_rtk={"heading_valid": True, "heading_age_s": 0.1, "heading_source": "THS"},
        rtk_received=19.8,
    )
    original = copy.deepcopy(packet)
    web_server.update_monitor_frame(packet, record=True)
    assert client.get("/api/monitor/frame").get_json() == original

    # No more producer updates: a responsive HTTP server must not mean live telemetry.
    for elapsed in (2.0, 3.0):
        clock.now = 100.0 + elapsed
        response = client.get("/api/monitor/frame")
        assert response.status_code == 200
        aged = response.get_json()
        assert aged["status"] == "stale"
        for key in ("truth", "estimate", "implement", "target", "command", "rtk"):
            assert aged[key]["age_s"] == pytest.approx(original[key]["age_s"] + elapsed)
            assert aged[key]["stale"] is True
        assert aged["rtk"]["heading_age_s"] == pytest.approx(original["rtk"]["heading_age_s"] + elapsed)
        assert aged["truth"]["x"] == original["truth"]["x"]

    assert web_server._monitor_frame == original
    assert packet == original
    assert client.get("/api/monitor/replay").get_json()["frames"] == [original]


def test_scene_revision_avoids_resending_identical_geometry(client):
    web_server.update_trajectory_data(task_id="one", field_boundary=FIELD, field_holes=[HOLE])
    first = client.get("/api/monitor/scene").get_json()
    assert first["data"]["task_id"] == "one"
    response = client.get(f"/api/monitor/scene?since={first['revision']}")
    assert response.get_json() == {"revision": first["revision"], "unchanged": True}
    assert response.headers["Cache-Control"] == "no-store"
    web_server.update_trajectory_data(actual_trajectory=[(1, 2), (2, 3)])
    changed = client.get(f"/api/monitor/scene?since={first['revision']}").get_json()
    assert changed["revision"] > first["revision"]
    assert len(changed["data"]["actual_trajectory"]) == 2


def test_replay_is_bounded_and_copies_packets_before_the_producer_reuses_them(client):
    web_server.reset_monitor_data(max_history=2)
    packet = frame()
    for x in (1, 2, 3):
        packet["estimate"]["x"] = x
        web_server.update_monitor_frame(packet, record=True)
    packet["estimate"]["x"] = 999
    assert client.get("/api/monitor/frame").get_json()["estimate"]["x"] == 3
    assert [p["estimate"]["x"] for p in client.get("/api/monitor/replay").get_json()["frames"]] == [2, 3]
    web_server.update_monitor_frame(frame(now_monotonic=22), record=False)
    assert len(client.get("/api/monitor/replay").get_json()["frames"]) == 2


def test_reset_drops_previous_task_map_holes_path_and_replay(client):
    web_server.update_trajectory_data(task_id="old", field_boundary=FIELD, field_holes=[HOLE],
                                      planned_path=[(0, 0), (8, 8)],
                                      actual_trajectory=[(1, 1), (2, 2)])
    web_server.update_monitor_frame(frame(task_id="old"), record=True)
    old_revision = client.get("/api/monitor/scene").get_json()["revision"]
    web_server.reset_monitor_data()
    web_server.update_trajectory_data(task_id="new")
    scene = client.get("/api/monitor/scene").get_json()
    assert scene["revision"] > old_revision
    assert scene["data"]["task_id"] == "new"
    assert scene["data"]["field_boundary"] is None
    assert scene["data"]["field_holes"] == []
    assert scene["data"]["planned_path"] is None
    assert scene["data"]["actual_trajectory"] == []
    assert client.get("/api/monitor/frame").get_json() is None
    assert client.get("/api/monitor/replay").get_json()["frames"] == []


@pytest.mark.parametrize("endpoint", ["frame", "scene", "replay"])
def test_monitor_endpoints_reject_commands(client, endpoint):
    response = client.post(f"/api/monitor/{endpoint}", json={"linear_velocity": 1})
    assert response.status_code == 405


def test_3d_page_model_and_renderer_are_available_locally(client):
    page = client.get("/3d")
    assert page.status_code == 200
    assert b"/static/vendor/three/" in page.data
    model = client.get("/assets/tracked_tiller.glb")
    assert model.status_code == 200
    assert model.data[:4] == b"glTF"
    assert model.mimetype == "model/gltf-binary"
    for name in ("three.module.min.js", "three.core.min.js", "GLTFLoader.js", "OrbitControls.js"):
        asset = client.get(f"/static/vendor/three/{name}")
        assert asset.status_code == 200, name
        assert len(asset.data) > 100, name


def test_spatial_coverage_layers_keep_holes_repetition_and_uncovered_area():
    samples = [{"x": x, "y": 5, "theta": 0, "working": True} for x in (-2, 12, -2)]
    accumulator = CoverageAccumulator(FIELD, 6, field_holes=[HOLE]).extend(samples)
    before = copy.deepcopy(accumulator.metrics())
    overlay = atom.build_coverage_overlay(samples[-1:], 6, FIELD, field_holes=[HOLE],
                                          accumulator=accumulator)
    layers = {name: unary_union([Polygon(p["exterior"], p["holes"]) for p in overlay[name]])
              for name in ("covered", "repeated", "missed", "outside")}
    assert any(p["holes"] for p in overlay["covered"])
    assert layers["covered"].intersection(Polygon(HOLE)).area == pytest.approx(0)
    assert layers["covered"].area == pytest.approx(56)
    assert layers["repeated"].area == pytest.approx(56)
    assert layers["missed"].area == pytest.approx(40)
    for name, geometry in layers.items():
        assert geometry.area == pytest.approx(before[f"{name}_area_m2"])
    assert overlay["sample_count"] == 3
    assert overlay["display_sample_count"] == 1
    limited = atom.build_coverage_overlay(samples[-1:], 6, FIELD, field_holes=[HOLE],
                                          accumulator=accumulator, max_polygons=1)
    assert limited["display_geometry_truncated"]
    assert limited["missed_area_m2"] == overlay["missed_area_m2"]
    assert accumulator.metrics() == before


def _run_scripted_node(monkeypatch, schedules, duration=1.4):
    """Drive the real node loop without sockets, subprocesses, or wall-clock waits."""
    from edge.nodes.observability.trajectory_viz import run

    clock = SimpleNamespace(now=10.0)

    def sleep(seconds):
        clock.now += seconds

    monkeypatch.setattr(run, "time", SimpleNamespace(
        monotonic=lambda: clock.now, time=lambda: 1_000 + clock.now, sleep=sleep))
    monkeypatch.setattr(web_server, "start_web_server", lambda **kwargs: None)
    for name in ("state_info", "raw_rtk", "tillage_cmd", "tillage_status", "implement_state"):
        monkeypatch.delenv(f"NODE_IN_{name}", raising=False)

    class Input:
        def __init__(self, name):
            self.packets = list(schedules.get(name, []))

        def recv_latest(self):
            if self.packets and self.packets[0][0] <= clock.now - 10 + 1e-9:
                return copy.deepcopy(self.packets.pop(0)[1])
            return None

    class SDK:
        def __init__(self, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def get_param(self, name, default):
            return {"timeout": duration, "stale_after_s": 0.5,
                    "frame_interval_s": 0.1, "scene_interval_s": 0.1}.get(name, default)

        def create_input_port(self, name):
            return Input(name)

        def create_output_port(self, *args, **kwargs):
            return SimpleNamespace(send=lambda value: None)

    monkeypatch.setattr(run, "NodeFlowSDK", SDK)
    run.main()


def test_node_keeps_last_valid_pose_but_publishes_stale_after_invalid_heading(monkeypatch, client):
    _run_scripted_node(monkeypatch, {
        "pose_enu": [(0, POSE), (0.2, {"x": 99, "y": 99, "theta": None, "heading_valid": False})],
    })
    value = client.get("/api/monitor/frame").get_json()
    assert value["status"] == "stale"
    assert value["estimate"]["x"] == POSE["x"]
    assert value["estimate"]["age_s"] > 1
    assert value["truth"] is None
    replay = client.get("/api/monitor/replay").get_json()["frames"]
    assert len(replay) == 1
    assert replay[0]["estimate"]["x"] == POSE["x"]


def test_node_task_switch_clears_old_map_and_history_without_new_pose(monkeypatch, client):
    _run_scripted_node(monkeypatch, {
        "task_enu": [(0, {"id": "old", "parcel": {"outer": FIELD, "holes": [HOLE]}}),
                     (0.4, {"id": "new"})],
        "global_path": [(0, {"task_id": "old", "path": [(0, 0), (10, 10)]})],
        "pose_enu": [(0, POSE)],
    })
    value = client.get("/api/monitor/frame").get_json()
    assert value["task_id"] == "new"
    assert value["status"] == "waiting"
    assert value["estimate"] is None
    scene = client.get("/api/monitor/scene").get_json()["data"]
    assert scene["field_boundary"] is None
    assert scene["field_holes"] == []
    assert scene["planned_path"] is None
    assert scene["actual_trajectory"] == []
    assert client.get("/api/monitor/replay").get_json()["frames"] == []
