"""物理层与延迟状态读取的回归：共同用于 RTK 控制闭环。"""

import math
import random

import pytest

from simulation.physics import KinematicsEngine, SimplePhysics
from simulation.state import RobotState, StateHistory


def engine(**kwargs):
    options = dict(dt=0.1, enable_slip=False, enable_terrain_noise=False)
    options.update(kwargs)
    return KinematicsEngine(**options)


def test_zero_velocity_command_does_not_reactivate_old_throttle():
    model = engine()
    model.set_control(1.0, 1.0)
    state = model.step(RobotState(sim_time=0.0))
    model.set_velocity_control(0.0, 0.0)
    for _ in range(30):
        state = model.step(state)
    assert state.vx == 0.0
    assert state.omega_yaw == 0.0
    assert model.control_mode == "velocity"
    model.set_control(-1.0, 0.0)
    assert model.step(state).vx < 0.0


@pytest.mark.parametrize("mode", ["velocity", "throttle"])
def test_both_modes_limit_speed_acceleration_and_turn_rate(mode):
    model = engine(max_speed=0.8, max_accel=0.3, max_angular_vel=0.5,
                   max_angular_accel=0.2, enable_slip=True,
                   enable_terrain_noise=True, terrain_roughness=0.1, seed=10)
    state = RobotState(sim_time=0.0)
    for demand in (20.0, -20.0, 0.0):
        if mode == "velocity":
            model.set_velocity_control(demand, demand)
        else:
            model.set_control(demand, demand)
        for _ in range(100):
            previous = state
            state = model.step(state)
            assert abs(state.vx) <= model.max_speed + 1e-12
            assert abs(state.omega_yaw) <= model.max_angular_vel + 1e-12
            assert abs(state.vx - previous.vx) <= model.max_accel * model.dt + 1e-12
            assert abs(state.omega_yaw - previous.omega_yaw) <= model.max_angular_accel * model.dt + 1e-12
            assert abs(state.ax) <= model.max_accel + 1e-12


def test_response_time_applies_to_forward_and_angular_speed():
    model = engine(dt=0.05, max_accel=100.0, max_angular_accel=100.0,
                   velocity_response_time_s=0.8, angular_response_time_s=1.6)
    model.set_velocity_control(1.0, 0.5)
    state = RobotState(sim_time=0.0)
    for _ in range(16):
        state = model.step(state)
    assert state.vx == pytest.approx(1.0 - math.exp(-1.0))
    assert state.omega_yaw == pytest.approx(0.5 * (1.0 - math.exp(-0.5)))
    assert state.sim_time == pytest.approx(0.8)
    assert state.step_count == 16


def test_seeded_equivalent_modes_share_vehicle_response():
    options = dict(seed=42, enable_slip=True, enable_terrain_noise=True,
                   velocity_response_time_s=0.4, angular_response_time_s=0.8)
    throttle = engine(**options)
    velocity = engine(**options)
    throttle.set_control(0.5, 0.2)
    velocity.set_velocity_control(1.0, 0.2)
    first = second = RobotState(sim_time=0.0)
    for _ in range(100):
        first = throttle.step(first)
        random.gauss(0.0, 1.0)
        second = velocity.step(second)
        assert first == second


def test_crossing_pi_does_not_reverse_translation():
    model = engine()
    model.set_velocity_control(1.0, 0.4)
    initial = RobotState(yaw=math.pi - 0.01, vx=1.0, omega_yaw=0.4, sim_time=4.0)
    state = model.step(initial)
    assert state.yaw == pytest.approx(-math.pi + 0.03)
    assert state.x < -0.099
    assert abs(state.y) < 0.002
    assert initial.x == 0.0  # step 不修改历史真值


def test_seed_and_reset_replay_trajectory_without_global_rng():
    model = engine(seed=321, enable_slip=True, enable_terrain_noise=True)

    def run():
        model.set_velocity_control(0.8, 0.2)
        model.set_implement_control(1.0, True)
        state = RobotState(sim_time=0.0)
        result = []
        for _ in range(60):
            random.random()  # 其他模块消耗全局随机数不改变车辆轨迹
            state = model.step(state)
            result.append(state.to_dict())
        return result

    expected = run()
    model.reset_control()
    assert model.control_mode == "throttle"
    assert model.target_hitch_height == 0.0
    assert model.target_pto_on is False
    assert model.implement_drag_factor == 0.0
    assert run() == expected
    model.reset_control()
    model.reset_rng(322)
    assert run() != expected


def test_stationary_vehicle_does_not_rotate_from_terrain_noise():
    model = engine(seed=1, enable_terrain_noise=True)
    model.set_velocity_control(0.0, 0.0)
    state = RobotState(sim_time=0.0)
    for _ in range(30):
        state = model.step(state)
    assert state.x == state.y == state.yaw == 0.0


def test_implement_animates_at_rest_and_zero_rpm_can_stop():
    model = engine()
    model.set_velocity_control(0.0, 0.0)
    model.set_implement_control(1.0, True)
    state = RobotState(sim_time=0.0)
    for _ in range(16):
        state = model.step(state)
    assert state.hitch_height == 1.0
    assert state.pto_on
    model.set_implement_control(0.0, False, 0.0)
    for _ in range(16):
        state = model.step(state)
    assert state.hitch_height == 0.0
    assert state.pto_rpm == 0.0
    assert not state.pto_on


@pytest.mark.parametrize("name,value", [
    ("dt", 0.0), ("max_accel", -1.0), ("max_angular_accel", math.inf),
    ("angular_response_time_s", -1.0), ("velocity_response_time_s", math.nan),
    ("slip_ratio", 1.1), ("terrain_roughness", math.nan),
])
def test_invalid_runtime_parameter_rejected_before_moving(name, value):
    model = engine()
    setattr(model, name, value)
    state = RobotState(sim_time=0.0)
    with pytest.raises(ValueError, match=name):
        model.step(state)
    assert state.sim_time == 0.0


def test_nonfinite_command_and_state_are_rejected():
    model = engine()
    with pytest.raises(ValueError):
        model.set_control(math.nan, 0.0)
    with pytest.raises(ValueError):
        model.set_velocity_control(0.5, math.inf)
    with pytest.raises(ValueError):
        model.set_implement_control(0.0, True, math.nan)
    with pytest.raises(ValueError, match="state.yaw"):
        model.step(RobotState(yaw=math.nan))


def test_history_short_arc_preserves_full_state_and_discrete_timing():
    history = StateHistory()
    s0 = RobotState(x=0.0, y=2.0, z=3.0, roll=3.1, pitch=-3.1, yaw=3.1,
                    vx=0.2, vy=0.3, vz=0.4, omega_roll=0.5, omega_pitch=0.6,
                    omega_yaw=0.7, ax=0.8, ay=0.9, az=9.81,
                    hitch_height=0.4, pto_on=False, pto_rpm=5.0,
                    step_count=4, sim_time=10.0)
    s1 = s0.copy()
    s1.x = 2.0
    s1.roll, s1.pitch, s1.yaw = -3.1, 3.1, -3.1
    s1.hitch_height = 0.8
    s1.pto_on = True
    s1.pto_rpm = 105.0
    s1.step_count = 5
    s1.sim_time = 12.0
    history.add(s0)
    history.add(s1)
    middle = history.get_at_time(11.0)
    assert middle.x == 1.0
    assert abs(middle.yaw) == pytest.approx(math.pi)
    assert abs(middle.roll) == pytest.approx(math.pi)
    assert abs(middle.pitch) == pytest.approx(math.pi)
    assert middle.vz == 0.4
    assert middle.omega_roll == 0.5
    assert middle.omega_pitch == 0.6
    assert middle.omega_yaw == 0.7
    assert middle.ax == 0.8
    assert middle.ay == 0.9
    assert middle.az == 9.81
    assert middle.hitch_height == pytest.approx(0.6)
    assert middle.pto_rpm == 55.0
    assert not middle.pto_on
    assert middle.step_count == 4
    assert history.get_at_time(12.0).pto_on


def test_history_clamps_both_ends_and_returns_copies():
    history = StateHistory(max_size=2)
    for timestamp in (1.0, 2.0, 3.0):
        history.add(RobotState(x=timestamp, sim_time=timestamp))
    before = history.get_at_time(-10.0)
    after = history.get_at_time(100.0)
    assert before.sim_time == 2.0
    assert after.sim_time == 3.0
    before.x = 999.0
    after.x = 999.0
    assert history.get_at_time(2.0).x == 2.0
    assert history.get_latest().x == 3.0
    history.add(RobotState(x=4.0, sim_time=3.0))
    assert history.get_latest().x == 4.0
    with pytest.raises(ValueError, match="timestamps"):
        history.add(RobotState(sim_time=1.0))


def test_boundary_uses_configured_extent_and_stops_body_velocity():
    model = SimplePhysics(bounds_x=(-400.0, 400.0), bounds_y=(-400.0, 400.0))
    inside = RobotState(x=200.0, y=300.0, vx=0.5, yaw=math.pi / 2)
    assert model.apply_boundary(inside) == inside
    outside = RobotState(x=200.0, y=401.0, vx=0.5, yaw=math.pi / 2)
    stopped = model.apply_boundary(outside)
    assert stopped.y == 400.0
    assert stopped.vx == stopped.vy == 0.0
    assert outside.y == 401.0
