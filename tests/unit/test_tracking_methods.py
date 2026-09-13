"""Selectable tracking laws share the existing controller and execution rules."""
import importlib.util
import math
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
import yaml

from edge.nodes.control.track_controller import atom


ROOT = Path(__file__).resolve().parents[2]
POSE = {"x": 0.0, "y": 0.0, "theta": 0.0}
TARGET = {"x": 4.0, "y": 2.0, "final": False}


def command(pose=None, target=None, **overrides):
    params = dict(max_speed=.8, min_speed=0.0, kp=2.5, max_w=10.0,
                  pivot_th=90.0, decel_start_dist=1.0,
                  final_stop_dist=.1, now=123.0)
    params.update(overrides)
    return atom.compute_velocity_cmd(
        POSE if pose is None else pose, TARGET if target is None else target, **params
    )


@pytest.mark.parametrize("speed", [.02, .3, .8])
@pytest.mark.parametrize("target_updates,params", [
    ({}, {}),
    ({"mode": "fallback"}, {}),
    ({"in_view_count": 1}, {}),
    ({"upcoming_turn_angle_deg": 150.0}, {}),
    ({}, {"path_progress": {"motion": {"speed_limit_mps": .01}}}),
    ({}, {"path_progress": {"cross_track_error_m": 1.0}}),
    ({}, {"path_progress": {"segment_type": "headland_turn"}}),
])
def test_pure_pursuit_preserves_curvature_after_all_speed_factors(speed, target_updates, params):
    result = command(target={**TARGET, **target_updates}, max_speed=speed,
                     tracking_method="pure_pursuit", **params)
    assert result["linear_velocity"] > 0.0
    # The target lies on the circle through (0, 0), tangent to the vehicle's +x axis.
    expected_curvature = .2  # 2 * 2 / (4**2 + 2**2)
    assert result["angular_velocity"] / result["linear_velocity"] == pytest.approx(expected_curvature)


@pytest.mark.parametrize("rotation", [0.0, math.pi / 2, -math.pi / 3, math.pi])
@pytest.mark.parametrize("side", [-1.0, 1.0])
def test_turn_sign_and_geometry_are_invariant_under_rigid_coordinate_changes(rotation, side):
    origin_x, origin_y = 50.0, -20.0
    dx, dy = 4.0, 2.0 * side
    target = {"x": origin_x + math.cos(rotation)*dx - math.sin(rotation)*dy,
              "y": origin_y + math.sin(rotation)*dx + math.cos(rotation)*dy}
    pose = {"x": origin_x, "y": origin_y, "theta": rotation}
    result = command(pose, target, tracking_method="pure_pursuit")
    reference = command(target={"x": dx, "y": dy}, tracking_method="pure_pursuit")
    assert result["linear_velocity"] == pytest.approx(reference["linear_velocity"])
    assert result["angular_velocity"] == pytest.approx(reference["angular_velocity"])
    assert math.copysign(1, result["angular_velocity"]) == side


def test_angular_limit_reduces_forward_speed_to_keep_the_commanded_circle():
    target = {"x": .2, "y": .2}
    unrestricted = command(target=target, tracking_method="pure_pursuit")
    limited = command(target=target, tracking_method="pure_pursuit", max_w=.12, min_speed=.3)
    assert unrestricted["angular_velocity"] > .12
    assert limited["angular_velocity"] == pytest.approx(.12)
    assert limited["linear_velocity"] == pytest.approx(.024)
    assert limited["linear_velocity"] < .3  # Curvature/turn limits outrank the speed floor.
    assert limited["angular_velocity"] / limited["linear_velocity"] == pytest.approx(5.0)


def test_staged_endpoint_speed_cap_also_preserves_curvature():
    result = command(target={**TARGET, "execution_phase": "follow", "execution_progress": {
        "zone": "transit", "distance_to_segment_end_m": .15,
        "motion": {"speed_limit_mps": .3},
    }}, tracking_method="pure_pursuit", tillage_status={"transport_ready": True})
    assert result["linear_velocity"] == pytest.approx(.09)
    assert result["angular_velocity"] / result["linear_velocity"] == pytest.approx(.2)


@pytest.mark.parametrize("speed", [0.0, 1e-8, .02])
def test_low_speed_does_not_cause_an_angular_velocity_singularity(speed):
    result = command(tracking_method="pure_pursuit", max_speed=speed)
    assert math.isfinite(result["linear_velocity"])
    assert math.isfinite(result["angular_velocity"])
    assert result["angular_velocity"] == pytest.approx(.2 * result["linear_velocity"], abs=1e-15)
    if speed == 0:
        assert result["linear_velocity"] == result["angular_velocity"] == 0.0


@pytest.mark.parametrize("distance_floor,expected_curvature", [(.1, 2.0), (.2, .5)])
def test_near_target_uses_configured_distance_floor(distance_floor, expected_curvature):
    result = command(target={"x": .01, "y": .01}, tracking_method="pure_pursuit",
                     pure_pursuit_min_distance_m=distance_floor)
    assert result["linear_velocity"] > 0
    assert result["angular_velocity"] / result["linear_velocity"] == pytest.approx(expected_curvature)


@pytest.mark.parametrize("offset", [0.0, 1e-7])
@pytest.mark.parametrize("heading", [1.0, math.pi])
def test_nonfinal_coincident_target_stops_without_choosing_an_arbitrary_heading(offset, heading):
    result = command(pose={"x": 2.0, "y": -3.0, "theta": heading},
                     target={"x": 2.0 + offset, "y": -3.0}, tracking_method="pure_pursuit")
    assert result["status"] == "target_too_close"
    assert result["linear_velocity"] == result["angular_velocity"] == 0.0


@pytest.mark.parametrize("target,params,expected_status", [
    ({"x": 0.0, "y": 0.0, "final": True}, {}, "arrived"),
    ({"x": -2.0, "y": 1.0}, {}, "pivot"),
    ({"x": -2.0, "y": 1.0, "zone": "work"}, {}, "needs_reposition"),
    ({"x": -2.0, "y": 1.0}, {"tillage_status": {"pto_on": True}}, "needs_reposition"),
    ({"x": 4.0, "y": 2.0, "zone": "work"}, {"require_implement_ready": True},
     "waiting_for_implement"),
    ({"x": 4.0, "y": 2.0, "execution_phase": "hold", "execution_progress": {"zone": "work"}},
     {}, "stage_stop"),
    ({"x": 4.0, "y": 2.0, "execution_phase": "complete", "execution_progress": {"zone": "work"}},
     {}, "arrived"),
    ({"x": 4.0, "y": 2.0, "execution_phase": "align", "execution_heading_rad": 1.2,
      "execution_progress": {"zone": "transit"}}, {}, "waiting_for_implement_raise"),
    ({"x": 4.0, "y": 2.0, "execution_phase": "align", "execution_heading_rad": 1.2,
      "execution_progress": {"zone": "transit"}},
     {"tillage_status": {"transport_ready": True}}, "turn_align"),
])
def test_tracking_choice_keeps_stops_lift_waits_and_pivot_control(target, params, expected_status):
    legacy = command(target=target, tracking_method="heading_p", **params)
    pure = command(target=target, tracking_method="pure_pursuit", **params)
    for result in (legacy, pure):
        assert result["status"] == expected_status
        assert result["linear_velocity"] == 0.0
    assert pure["angular_velocity"] == pytest.approx(legacy["angular_velocity"])
    if expected_status in ("pivot", "turn_align"):
        assert pure["angular_velocity"] > 0
    else:
        assert pure["angular_velocity"] == 0.0


@pytest.mark.parametrize("target", [TARGET, {"x": -2.0, "y": 1.0},
                                   {"x": 0.0, "y": 0.0, "final": True}])
def test_omitting_tracking_choice_exactly_retains_legacy_behavior(target):
    assert command(target=target) == command(target=target, tracking_method="heading_p")


@pytest.mark.parametrize("invalid_method", ["", "stanley", "PURE_PURSUIT", None])
def test_unknown_tracking_method_is_rejected(invalid_method):
    with pytest.raises(ValueError):
        command(tracking_method=invalid_method)


@pytest.mark.parametrize("distance", [0.0, -.1, float("inf"), float("nan"), "bad"])
@pytest.mark.parametrize("method", ["heading_p", "pure_pursuit"])
def test_distance_floor_must_be_finite_and_positive(method, distance):
    with pytest.raises(ValueError):
        command(tracking_method=method, pure_pursuit_min_distance_m=distance)


def test_pure_pursuit_rejects_conflicting_path_heading_compatibility_switch():
    with pytest.raises(ValueError):
        command(tracking_method="pure_pursuit", headland_turn_use_path_heading=True)
    # The old compatibility switch remains available with the original law.
    result = command(tracking_method="heading_p", headland_turn_use_path_heading=True,
                     path_progress={"segment_type": "headland_turn", "path_heading_rad": .1})
    assert result["target_mode"] == "path_heading"


class _Finished(Exception):
    pass


@pytest.mark.parametrize("selected_method", [None, "heading_p", "pure_pursuit"])
def test_existing_node_reads_yaml_selection_and_publishes_real_control_result(monkeypatch, selected_method):
    monkeypatch.setitem(sys.modules, "atom", atom)
    spec = importlib.util.spec_from_file_location(
        "selectable_track_controller_run", ROOT / "edge/nodes/control/track_controller/run.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    params = yaml.safe_load("""
max_speed: 0.3
min_speed: 0.0
heading_p_gain: 2.5
max_angular_velocity: 10.0
pivot_threshold_deg: 90.0
decel_start_distance: 0.1
pure_pursuit_min_distance_m: 1.0
""")
    if selected_method is not None:
        params["tracking_method"] = selected_method
    sent, schemas, inputs = [], [], []
    target = {"x": .2, "y": .1, "final": False}

    class SDK:
        logger = Mock()

        def __init__(self, **kwargs):
            self.params = params

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def create_input_port(self, name):
            inputs.append(name)
            return SimpleNamespace(recv_latest=lambda: {"pose_enu": POSE, "next_point": target}.get(name))

        def create_output_port(self, name, schema):
            assert name == "velocity_cmd"
            schemas.append(schema)
            return SimpleNamespace(send=lambda packet: sent.append(dict(packet)))

    def finish(_delay):
        raise _Finished

    monkeypatch.delenv("NODE_IN_tillage_status", raising=False)
    monkeypatch.setattr(module, "NodeFlowSDK", SDK)
    monkeypatch.setattr(module, "time", SimpleNamespace(time=lambda: 123.0, monotonic=lambda: 10.0,
                                                       sleep=finish))
    with pytest.raises(_Finished):
        module.main()
    assert len(sent) == len(schemas) == 1
    assert inputs == ["pose_enu", "next_point", "path_progress"]
    result = sent[0]
    expected = command(target=target, tracking_method=selected_method or "heading_p",
                       max_speed=.3, decel_start_dist=.1, pure_pursuit_min_distance_m=1.0)
    assert result["linear_velocity"] == pytest.approx(expected["linear_velocity"])
    assert result["angular_velocity"] == pytest.approx(expected["angular_velocity"])
    if selected_method == "pure_pursuit":
        assert result["angular_velocity"] / result["linear_velocity"] == pytest.approx(.2)
    # Exercise the same output validation that can otherwise silently discard diagnostics.
    validated = schemas[0](**result)
    packet = validated.model_dump() if hasattr(validated, "model_dump") else validated.dict()
    for name in ("speed_factor", "target_mode", "tracking_method", "curvature_inv_m"):
        if name in result:
            assert packet[name] == result[name]


def test_existing_controller_manifest_exposes_selection_with_legacy_default():
    manifest = yaml.safe_load((ROOT / "edge/nodes/control/track_controller/node.yaml").read_text())
    assert manifest["name"] == "track_controller"
    assert manifest["params"]["tracking_method"]["default"] == "heading_p"
    assert manifest["params"]["pure_pursuit_min_distance_m"]["default"] == .1
    assert [port["name"] for port in manifest["ports"]["outputs"]] == ["velocity_cmd"]
