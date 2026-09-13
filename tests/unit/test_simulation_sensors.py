"""传感器采样、延迟和独立随机序列的回归。"""
import random

import pytest

from simulation.sensors import SensorSimulator
from simulation.state import RobotState


def sensor(**rtk):
    return SensorSimulator(seed=19, rtk_config={"status": "FIXED", "frequency": 10.0, **rtk})


def test_queries_are_read_only_and_do_not_change_future_noise():
    frequent, sparse = sensor(), sensor()
    for index in range(31):
        state = RobotState(x=index / 10, sim_time=index / 100)
        frequent.update(state)
        sparse.update(state)
        for _ in range(7):
            sample = frequent.get_rtk_gps_data(state)
            sample["latitude"] = -999
            frequent.get_gps_data(state)
            frequent.get_imu_data(state)
        assert frequent.get_rtk_gps_data() == sparse.get_rtk_gps_data()
    assert frequent.get_rtk_gps_data()["seq"] == 4
    assert frequent.get_rtk_gps_data()["timestamp"] == pytest.approx(0.3)


def test_sensor_instance_does_not_change_global_random_state():
    before = random.getstate()
    samples = sensor()
    samples.update(RobotState(sim_time=0))
    assert random.getstate() == before


def test_latency_preserves_sample_time_and_position():
    samples = sensor(latency_s=0.2, position_noise_std=0.0)
    for i in range(4):
        samples.update(RobotState(x=i, sim_time=i / 10))
        if i < 2:
            assert samples.get_rtk_gps_data() is None
    result = samples.get_rtk_gps_data()
    assert result["seq"] == 2
    assert result["timestamp"] == pytest.approx(0.1)
    measured_x = (result["longitude"] - samples.gps_ref_lon) * samples.meters_per_degree_lon
    assert measured_x == pytest.approx(1.0, abs=1e-8)


def test_sampling_interpolates_truth_when_dt_does_not_divide_period():
    samples = sensor(position_noise_std=0.0)
    samples.update(RobotState(x=0, sim_time=0))
    samples.update(RobotState(x=0.12, sim_time=0.12))
    result = samples.get_rtk_gps_data()
    measured_x = (result["longitude"] - samples.gps_ref_lon) * samples.meters_per_degree_lon
    assert result["timestamp"] == pytest.approx(0.1)
    assert measured_x == pytest.approx(0.1, abs=1e-8)


def test_configured_status_ratios_are_used_without_fixed_override():
    samples = sensor(status=None, fixed_ratio=0, float_ratio=0, single_ratio=0, none_ratio=1)
    samples.update(RobotState(sim_time=0))
    data = samples.get_rtk_gps_data()
    assert data["rtk_status"] == "NONE"
    assert data["fix_quality"] == 0
    assert data["heading_valid"] is False


def test_position_delta_heading_is_distinct_from_dual_antenna_heading():
    delta = sensor(heading_mode="position_delta", position_noise_std=0)
    dual = sensor(heading_mode="dual_antenna", position_noise_std=0)
    for samples in (delta, dual):
        samples.update(RobotState(yaw=0, sim_time=0))
    assert delta.get_rtk_gps_data()["heading_valid"] is False
    for samples in (delta, dual):
        samples.update(RobotState(y=1, yaw=0, sim_time=0.1))
    assert delta.get_rtk_gps_data()["heading"] == pytest.approx(0)
    assert dual.get_rtk_gps_data()["heading"] == pytest.approx(90)


def test_reset_replays_noise_and_clears_delayed_samples():
    samples = sensor(latency_s=0.1, heading_noise_std_deg=3)
    initial = RobotState(sim_time=0)
    samples.update(initial)
    samples.update(RobotState(x=20, sim_time=0.1))
    first = samples.get_rtk_gps_data()
    samples.reset()
    samples.update(initial)
    assert samples.get_rtk_gps_data() is None
    samples.update(RobotState(x=20, sim_time=0.1))
    assert samples.get_rtk_gps_data() == first


@pytest.mark.parametrize("config", [{"frequency": 0}, {"latency_s": -1},
                                     {"position_noise_std": float("nan")}, {"heading_mode": "unknown"}])
def test_invalid_rtk_configuration_fails_early(config):
    with pytest.raises(ValueError):
        sensor(**config)
