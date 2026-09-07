"""Closed-loop tests distinguish truth, measurements, arrival and repeatability."""
from dataclasses import replace

import pytest

from simulation.rtk_experiment import Experiment, run_experiment


def test_seed_replays_entire_closed_loop_and_noise_changes_measurements():
    e = Experiment(duration_s=4, path_length_m=15, position_noise_std_m=.03,
                   heading_noise_std_deg=2, angular_response_time_s=.7)
    result, rows = run_experiment(e)
    assert (result, rows) == run_experiment(e)
    other_result, other_rows = run_experiment(replace(e, seed=43))
    assert rows != other_rows
    assert result["filter_params"]["use_imu_yaw_rate"] is False
    assert any(abs(r["rtk_y_m"] - r["true_y_m"]) > .01 for r in rows)
    # 50 Hz controller must not smooth/filter the same 20 Hz RTK sample twice.
    assert result["metrics"]["observations"] == 81
    same_sample = next((a, b) for a, b in zip(rows, rows[1:]) if a["sample_seq"] == b["sample_seq"])
    assert same_sample[0]["filtered_y_m"] == same_sample[1]["filtered_y_m"]


def test_latency_preserves_acquisition_time_and_initial_wait():
    result, rows = run_experiment(Experiment(duration_s=2, path_length_m=15, rtk_latency_s=.3))
    assert all(r["status"] == "waiting_for_pose" for r in rows if r["time_s"] < .3)
    observed = [r for r in rows if r["sample_seq"] is not None]
    assert observed[0]["sample_time_s"] == 0
    assert min(r["sample_age_s"] for r in observed) == pytest.approx(.3)
    assert max(r["sample_age_s"] for r in observed) <= .35


def test_ideal_control_converges_and_truth_checks_endpoint():
    result, rows = run_experiment(Experiment(path_length_m=12, duration_s=30))
    assert result["metrics"]["reported_arrived"]
    assert result["metrics"]["true_endpoint_error_m"] < .5
    assert abs(rows[-1]["true_y_m"]) < .01
    assert rows[-1]["command_v_mps"] == 0


def test_delay_and_response_produce_real_oscillation_in_controlled_comparison():
    # Test an observable behaviour, not exact trace values or a real-machine claim.
    e = Experiment(duration_s=25, path_length_m=30, position_noise_std_m=.03,
                   heading_noise_std_deg=2, rtk_latency_s=.3, angular_response_time_s=.7)
    combined, rows = run_experiment(e)
    ideal, _ = run_experiment(replace(e, position_noise_std_m=0, heading_noise_std_deg=0,
                                      rtk_latency_s=0, angular_response_time_s=0))
    assert combined["metrics"]["true_lateral_rms_m"] > ideal["metrics"]["true_lateral_rms_m"] * 5
    assert min(r["true_y_m"] for r in rows) < -.02
    assert max(r["true_y_m"] for r in rows if r["true_x_m"] > 6) > .02
    assert all(r["status"] != "pivot" for r in rows)


@pytest.mark.parametrize("overrides", [{"duration_s": 0}, {"control_hz": 60},
                                      {"rtk_latency_s": -1}, {"initial_y_m": float("nan")},
                                      {"heading_mode": "position_delta"}])
def test_invalid_experiment_is_rejected(overrides):
    with pytest.raises(ValueError):
        run_experiment(Experiment(**overrides))
