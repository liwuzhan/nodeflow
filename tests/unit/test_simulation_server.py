"""无端口的整帧仿真配置、重置、命令超时和地块边界回归。"""
import random
import threading

import pytest
from shapely.geometry import Polygon

from simulation.field_generator import FieldGenerator
from simulation.server import SimulatorServer


def base_config():
    return {
        "server": {"random_seed": 7, "initial_pose_mode": "origin", "realtime": False,
                   "command_timeout_s": 0.5, "zmq_port": 6789},
        "kinematics": {"dt": 0.1, "max_accel": 1.0, "slip": {"enabled": False},
                       "terrain": {"enabled": False}},
        "physics": {"bounds": {"x": [-400, 400], "y": [-300, 300]}},
        "field": {"type": "rectangular", "width": 10, "length": 20},
        "sensors": {"rtk": {"status": "FIXED", "frequency": 10,
                              "position_noise_std": 0.0}},
    }


def velocity(server, linear=1.0, angular=0.0):
    return server._set_actuator({"actuator": "velocity", "data": {
        "linear_velocity": linear, "angular_velocity": angular}})


def test_config_values_and_explicit_false_zero_are_honored():
    server = SimulatorServer(config=base_config(), initial_sim_time=0)
    assert server.context is None and server.socket is None
    assert server.sim_dt == server.kinematics.dt == 0.1
    assert server.zmq_port == 6789
    assert server.realtime is False
    assert server.physics.bounds_x == (-400, 400)
    assert server.physics.bounds_y == (-300, 300)
    server.state.x = 150
    assert server.step_once(command_elapsed_s=0).x == 150
    override = SimulatorServer(config=base_config(), sim_dt=0.02, realtime=False,
                               command_timeout_s=0, initial_sim_time=0)
    assert override.sim_dt == override.kinematics.dt == 0.02
    assert override.command_timeout_s == 0


def test_reset_clears_motion_implement_history_sensor_and_replays():
    config = base_config()
    config["sensors"]["rtk"].update(latency_s=0.2, position_noise_std=0.1)
    server = SimulatorServer(config=config, initial_sim_time=0)
    velocity(server)
    server._set_actuator({"actuator": "implement", "data": {"hitch_height": 1, "pto_on": True}})
    for _ in range(5):
        server.step_once(command_elapsed_s=0)
    assert server.state.pto_on
    assert server.sensors.get_rtk_gps_data() is not None
    server._reset()
    assert server.state.x == server.state.y == server.state.sim_time == 0
    assert server.state.hitch_height == server.state.pto_rpm == 0
    assert len(server.state_history.history) == 1
    assert server.sensors.get_rtk_gps_data() is None
    fresh = SimulatorServer(config=config, initial_sim_time=0)
    for _ in range(4):
        assert server.step_once(command_elapsed_s=0) == fresh.step_once(command_elapsed_s=0)
        assert server.sensors.get_rtk_gps_data() == fresh.sensors.get_rtk_gps_data()


def test_offline_timeout_is_controlled_and_zero_disables_it():
    server = SimulatorServer(config=base_config(), initial_sim_time=0)
    velocity(server)
    for _ in range(10):
        server.step_once(command_elapsed_s=0)
    assert server.state.vx == pytest.approx(1)
    server.step_once(command_elapsed_s=0.5)
    assert server.state.vx < 1
    for _ in range(15):
        server.step_once(command_elapsed_s=1)
    assert server.state.vx == pytest.approx(0)
    server.command_timeout_s = 0
    velocity(server)
    for _ in range(15):
        server.step_once(command_elapsed_s=1000)
    assert server.state.vx == pytest.approx(1)


def test_motion_timeout_uses_monotonic_and_implement_does_not_refresh_it(monkeypatch):
    clock = [10.0]
    monkeypatch.setattr("simulation.server.time.monotonic", lambda: clock[0])
    server = SimulatorServer(config=base_config(), initial_sim_time=0)
    velocity(server)
    for _ in range(10):
        server.step_once()
    clock[0] += 1
    server._set_actuator({"actuator": "implement", "data": {"hitch_height": 1, "pto_on": True}})
    assert server.step_once().vx < 1


def test_instance_and_poll_rate_do_not_affect_other_run():
    before = random.getstate()
    a = SimulatorServer(config=base_config(), initial_sim_time=0)
    b = SimulatorServer(config=base_config(), initial_sim_time=0)
    velocity(a)
    velocity(b)
    for _ in range(30):
        for _ in range(4):
            a._get_sensor({"sensor": "rtk_gps"})
        assert a.step_once(command_elapsed_s=0) == b.step_once(command_elapsed_s=0)
        assert a._get_sensor({"sensor": "rtk_gps"}) == b._get_sensor({"sensor": "rtk_gps"})
    assert random.getstate() == before


def test_refresh_clears_old_motion_and_history():
    server = SimulatorServer(config=base_config(), initial_sim_time=0)
    velocity(server)
    server.step_once(command_elapsed_s=0)
    response = server._refresh_field({})
    assert response["version"] == 2
    assert server.state.step_count == 0
    assert server.step_once(command_elapsed_s=0).vx == 0


def test_concurrent_step_get_reset_do_not_leave_mixed_history():
    server = SimulatorServer(config=base_config(), initial_sim_time=0)
    errors = []
    def drive():
        try:
            for _ in range(100):
                velocity(server)
                server.step_once(command_elapsed_s=0)
        except Exception as exc:
            errors.append(exc)
    thread = threading.Thread(target=drive)
    thread.start()
    for _ in range(30):
        server._reset()
        state = server._get_state()["state"]
        assert state["sim_time"] == pytest.approx(state["step_count"] * server.sim_dt)
    thread.join()
    assert not errors


def test_fixed_concave_field_rejects_hole_inside_bbox_but_outside_polygon():
    gen = FieldGenerator(seed=19)
    boundary = [(0, 0), (10, 0), (10, 3), (3, 3), (3, 10), (0, 10)]
    with pytest.raises(ValueError, match="actual boundary"):
        gen.generate_fixed_field(boundary, [[(5, 5), (6, 5), (6, 6), (5, 6)]])
    fixed = gen.generate_fixed_field(boundary)
    result = gen.generate_random_holes(fixed, 2, 0.01)
    outer = Polygon(boundary)
    assert all(outer.contains(Polygon(hole)) for hole in result["holes"])
    assert not Polygon(result["holes"][0]).intersects(Polygon(result["holes"][1]))
    assert result["area"] < outer.area
