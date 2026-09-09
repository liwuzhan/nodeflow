"""Offline comparison of heading P and pure-pursuit geometry.

Run from NodeFlow:
python -m simulation.tracking_law_comparison --output /tmp/tracking_comparison

Both methods use the actual runtime controller, selected through its parameter;
the geometric method is not a complete Nav2 Regulated Pure Pursuit port.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import statistics
from dataclasses import asdict, replace
from pathlib import Path

import simulation.rtk_experiment as experiment_runner

def rms(values):
    return math.sqrt(sum(x*x for x in values)/len(values)) if values else None


def summarize(rows):
    # Same spatial steady-state window for both runs: initial 5 m excluded.
    cruise = [r for r in rows if 5.0 <= r['true_x_m'] <= 55.0]
    ys = [r['true_y_m'] for r in cruise]
    omegas = [r['command_w_radps'] for r in cruise]
    changes = [b - a for a, b in zip(omegas, omegas[1:])]
    return {
        'window_x_m': [5.0, 55.0], 'samples': len(cruise),
        'first_window_time_s': cruise[0]['time_s'] if cruise else None,
        'last_window_time_s': cruise[-1]['time_s'] if cruise else None,
        'true_cte_rms_m': rms(ys),
        'true_cte_max_abs_m': max(map(abs, ys)) if ys else None,
        'centerline_crossings_2cm_deadband': experiment_runner._crossings(ys, 0.02),
        'command_omega_rms_radps': rms(omegas),
        'command_omega_std_radps': statistics.pstdev(omegas) if omegas else None,
        'command_omega_delta_rms_radps_per_20ms': rms(changes),
        'command_omega_max_abs_radps': max(map(abs, omegas)) if omegas else None,
        'true_speed_mean_mps': statistics.mean(r['true_v_mps'] for r in cruise) if cruise else None,
        'true_distance_x_m': rows[-1]['true_x_m'],
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=Path('/tmp/tracking_comparison'))
    output = parser.parse_args().output
    output.mkdir(parents=True, exist_ok=True)
    summary = {
        'comparison_source_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        'scope': 'Eight fixed-step straight-line runs: four scenarios times two algorithms. No ROS, no IPC, no soil/load or roll model. Same ideal actuator velocity interface, original waypoint selector and speed logic. Geometry variant is not the complete Nav2 RPP controller.',
        'window': 'true x between 5 and 55 m; simulation ends at 60 s, before terminal braking. Max CTE and omega metrics use only that window.',
        'seed': 42, 'control_period_s': 0.02,
        'runs': [],
    }
    for speed in (0.3, 0.5):
        for condition in ('ideal', 'light_noise_lag'):
            disturbances = {} if condition == 'ideal' else dict(
                position_noise_std_m=0.02, heading_noise_std_deg=0.2,
                rtk_latency_s=0.1, velocity_response_time_s=0.2,
                angular_response_time_s=0.2)
            scenario = experiment_runner.Experiment(
                name=f'{speed:.1f}mps_{condition}', duration_s=60.0,
                path_length_m=60.0, initial_y_m=0.25,
                max_speed_mps=speed, segment_speed_limit_mps=speed,
                graph_path='configs/graphs/planning_with_real_rtk.yaml',
                **disturbances)
            for algorithm in ('existing_heading_p', 'pure_pursuit_geometry'):
                selected = replace(scenario, tracking_method=(
                    'heading_p' if algorithm == 'existing_heading_p' else 'pure_pursuit'))
                metadata, rows = experiment_runner.run_experiment(selected)
                name = f'{scenario.name}_{algorithm}'
                metrics = summarize(rows)
                record = {'name': name, 'algorithm': algorithm, 'scenario': asdict(selected), 'metrics': metrics}
                metadata.update(comparison_algorithm=algorithm, comparison_metrics=metrics,
                                comparison_source_sha256=summary['comparison_source_sha256'])
                (output / (name + '.json')).write_text(json.dumps(metadata, indent=2, ensure_ascii=False)+'\n')
                with (output / (name + '.csv')).open('w', newline='') as stream:
                    writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
                    writer.writeheader()
                    writer.writerows(rows)
                summary['runs'].append(record)
                print(json.dumps(record, ensure_ascii=False), flush=True)
    (output / 'summary.json').write_text(json.dumps(summary, indent=2, ensure_ascii=False)+'\n')


if __name__ == '__main__':
    main()
