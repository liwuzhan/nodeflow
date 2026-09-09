"""Deterministic straight-line RTK experiment using the actual node algorithms.

Run from the repository root: python -m simulation.rtk_experiment --output /tmp/rtk
No sockets, real-time sleeps or alternative controller are involved. This isolates
sensor/vehicle response; it does not reproduce process scheduling or soil forces.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import inspect
import json
import math
from dataclasses import asdict, dataclass, fields, replace
from pathlib import Path

import yaml

from edge.nodes.control.track_controller.atom import ControlSafetyGuard, compute_velocity_cmd
from edge.nodes.localization.coord_transform.atom import transform_pose
from edge.nodes.planning.path_progress.atom import compute_progress
from edge.nodes.planning.waypoint_selector.atom import ViewConfig, WaypointSelector
from edge.nodes.sensing.rtk_filter.atom import EMAFilter
from simulation.server import SimulatorServer

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG = Path(__file__).parent / "experiments" / "rtk_straight.yaml"


@dataclass(frozen=True)
class Experiment:
    name: str = "ideal"
    seed: int = 42
    duration_s: float = 90.0
    path_length_m: float = 60.0
    initial_y_m: float = 0.25
    initial_yaw_deg: float = 0.0
    dt_s: float = 0.01
    control_hz: float = 50.0
    bridge_hz: float = 20.0
    rtk_hz: float = 20.0
    position_noise_std_m: float = 0.0
    heading_noise_std_deg: float = 0.0
    rtk_latency_s: float = 0.0
    heading_mode: str = "dual_antenna"
    velocity_response_time_s: float = 0.0
    angular_response_time_s: float = 0.0
    max_speed_mps: float = 2.0
    segment_speed_limit_mps: float = 1.2
    graph_path: str = "configs/graphs/planning_simulation.yaml"
    tracking_method: str | None = None  # None沿用图；对照实验可显式覆盖

    def validate(self):
        if self.tracking_method not in (None, "heading_p", "pure_pursuit"):
            raise ValueError("tracking_method must be heading_p or pure_pursuit")
        if self.heading_mode != "dual_antenna":
            raise ValueError("This closed-loop experiment requires dual_antenna heading; "
                             "position_delta needs external motion/heading initialization")
        for item in fields(self):
            value = getattr(self, item.name)
            if isinstance(value, (float, int)) and not math.isfinite(value):
                raise ValueError(f"{item.name} must be finite")
        for name in ("duration_s", "path_length_m", "dt_s", "control_hz", "bridge_hz",
                     "rtk_hz", "max_speed_mps", "segment_speed_limit_mps"):
            if getattr(self, name) <= 0:
                raise ValueError(f"{name} must be positive")
        for name in ("position_noise_std_m", "heading_noise_std_deg", "rtk_latency_s",
                     "velocity_response_time_s", "angular_response_time_s"):
            if getattr(self, name) < 0:
                raise ValueError(f"{name} must be nonnegative")
        # Integral schedules keep this small runner unambiguous. Sensor sampling
        # itself supports arbitrary frequencies in SensorSimulator.
        for hz in (self.control_hz, self.bridge_hz):
            steps = 1.0 / (hz * self.dt_s)
            if steps < 1 or not math.isclose(steps, round(steps), abs_tol=1e-8):
                raise ValueError("control/bridge periods must be integer multiples of dt_s")


def _node_parameters(experiment: Experiment):
    path = ROOT / experiment.graph_path
    graph = yaml.safe_load(path.read_text(encoding="utf-8"))
    nodes = {node["id"]: node.get("params", {}) for node in graph["nodes"]}
    mapping = {"heading_p_gain": "kp", "max_angular_velocity": "max_w",
               "pivot_threshold_deg": "pivot_th", "decel_start_distance": "decel_start_dist",
               "final_stop_distance": "final_stop_dist"}
    allowed = inspect.signature(compute_velocity_cmd).parameters
    controller = {mapping.get(k, k): v for k, v in nodes["track_controller"].items()
                  if mapping.get(k, k) in allowed}
    controller.update(max_speed=experiment.max_speed_mps, require_implement_ready=False)
    if experiment.tracking_method is not None:
        controller["tracking_method"] = experiment.tracking_method
    selector_keys = {item.name for item in fields(ViewConfig)}
    selector = {k: v for k, v in nodes["waypoint_selector"].items() if k in selector_keys}
    selector["goal_tolerance"] = controller["final_stop_dist"]
    progress_keys = {"search_window", "relocalize_error_m", "heading_match_weight_m"}
    progress = {k: v for k, v in nodes["path_progress"].items() if k in progress_keys}
    filtering = nodes["rtk_filter"]
    guard = {k: v for k, v in nodes["track_controller"].items()
             if k in ("pose_timeout_s", "target_timeout_s", "pivot_timeout_s")}
    return controller, selector, progress, filtering, guard


def _simulator_config(e: Experiment):
    return {
        "server": {"random_seed": e.seed, "realtime": False,
                   "initial_pose": {"x": 0.0, "y": e.initial_y_m,
                                    "yaw": math.radians(e.initial_yaw_deg)}},
        "field": {"type": "rectangular", "width": 200.0, "length": 200.0,
                  "num_obstacles": 0, "holes": {"enabled": False}},
        "kinematics": {"dt": e.dt_s, "max_speed": e.max_speed_mps,
                       "max_accel": 1.0, "max_angular_vel": 1.0,
                       "max_angular_accel": 2.0,
                       "velocity_response_time_s": e.velocity_response_time_s,
                       "angular_response_time_s": e.angular_response_time_s,
                       "slip": {"enabled": False}, "terrain": {"enabled": False}},
        "physics": {"bounds": {"x": [-200.0, 200.0], "y": [-200.0, 200.0]}},
        "sensors": {"rtk": {"frequency": e.rtk_hz, "status": "FIXED",
                            "heading_mode": e.heading_mode,
                            "position_noise_std": e.position_noise_std_m,
                            "heading_noise_std_deg": e.heading_noise_std_deg,
                            "latency_s": e.rtk_latency_s}},
        "gps_ref": {"lat": 31.2, "lon": 121.5},
    }


def _straight_plan(e: Experiment):
    count = max(1, math.ceil(e.path_length_m / 0.5))
    path = [(e.path_length_m * i / count, 0.0) for i in range(count + 1)]
    return {"task_id": "rtk_straight", "path": path, "path_zones": ["work"] * len(path),
            "segments": [{"id": "straight", "type": "work", "zone": "work",
                          "start_index": 0, "end_index": count,
                          "motion": {"speed_limit_mps": e.segment_speed_limit_mps},
                          "implement": {"hitch": "down", "pto": "on"}}]}


def _rms(values):
    return math.sqrt(sum(x * x for x in values) / len(values)) if values else None


def _crossings(values, deadband):
    previous, count = 0, 0
    for value in values:
        sign = 1 if value > deadband else -1 if value < -deadband else 0
        if sign:
            count += int(previous != 0 and previous != sign)
            previous = sign
    return count


def run_experiment(experiment: Experiment) -> tuple[dict, list[dict]]:
    """Run one fixed-step scenario. Metadata and CSV rows are repeatable."""
    e = experiment
    e.validate()
    params, selector_params, progress_params, filter_params, guard_params = _node_parameters(e)
    sim = SimulatorServer(config=_simulator_config(e), initial_sim_time=0.0)
    filter_ = EMAFilter(alpha_pos=filter_params.get("alpha_pos", 0.2),
                        alpha_heading=filter_params.get("alpha_heading", 0.3),
                        use_imu_yaw_rate=False)
    selector = WaypointSelector(ViewConfig(**selector_params))
    plan = _straight_plan(e)
    selector.set_path(plan)
    guard = ControlSafetyGuard(**guard_params)
    control_every = round(1 / (e.control_hz * e.dt_s))
    bridge_every = round(1 / (e.bridge_hz * e.dt_s))
    rows, last_index, last_seq, observations = [], 0, None, 0
    pose = raw_pose = target = progress = raw = None
    command = {"linear_velocity": 0.0, "angular_velocity": 0.0, "status": "waiting_for_pose"}
    last_control_step = 0
    # Do not stop when a noisy pose first reports arrival: keep a short settling
    # window and report true endpoint error independently from reported arrival.
    arrived_since = None
    for step in range(math.ceil(e.duration_s / e.dt_s) + 1):
        now = sim.state.sim_time
        if step % bridge_every == 0:
            sample = sim.sensors.get_rtk_gps_data()
            if sample is not None and sample["seq"] != last_seq:
                last_seq, raw = sample["seq"], sample
                observations += 1
                filtered = filter_.update(sample, None, now)
                raw_pose = transform_pose(sample, 121.5, 31.2)
                pose = transform_pose(filtered, 121.5, 31.2)
                guard.note_pose(now)
        if step % control_every == 0:
            last_control_step = step
            progress = compute_progress(plan, pose, last_index, **progress_params)
            if progress:
                last_index = progress["path_index"]
                target = selector.select(pose, progress)
                guard.note_target(target, now)
            command = compute_velocity_cmd(pose, target, now=now, path_progress=progress, **params)
            command = guard.apply(command, now, now)
            response = sim._set_actuator({"actuator": "velocity", "data": command})
            if response.get("status") != "ok":
                raise RuntimeError(response)
            state = sim.state
            rows.append({
                "time_s": round(now, 8), "true_x_m": state.x, "true_y_m": state.y,
                "true_yaw_deg": math.degrees(state.yaw), "true_v_mps": state.vx,
                "true_w_radps": state.omega_yaw,
                "rtk_x_m": raw_pose["x"] if raw_pose else None,
                "rtk_y_m": raw_pose["y"] if raw_pose else None,
                "rtk_yaw_deg": math.degrees(raw_pose["theta"]) if raw_pose else None,
                "filtered_x_m": pose["x"] if pose else None,
                "filtered_y_m": pose["y"] if pose else None,
                "filtered_yaw_deg": math.degrees(pose["theta"]) if pose else None,
                "sample_seq": last_seq,
                "sample_time_s": raw["timestamp"] if raw else None,
                "sample_age_s": now - raw["timestamp"] if raw else None,
                "target_x_m": target["x"] if target else None,
                "target_y_m": target["y"] if target else None,
                "command_v_mps": command["linear_velocity"],
                "command_w_radps": command["angular_velocity"],
                "status": command.get("status", "tracking"),
            })
            if command.get("status") == "arrived":
                arrived_since = now if arrived_since is None else arrived_since
                if now - arrived_since >= 2.0:
                    break
            else:
                arrived_since = None
        if step < math.ceil(e.duration_s / e.dt_s):
            sim.step_once(command_elapsed_s=(step - last_control_step) * e.dt_s)

    # Fixed spatial window excludes initial convergence and endpoint braking.
    margin = min(5.0, e.path_length_m / 4)
    cruise = [r for r in rows if margin <= r["true_x_m"] <= e.path_length_m - margin]
    truth_error = [r["true_y_m"] for r in cruise]
    sample_ages = [r["sample_age_s"] for r in rows if r["sample_age_s"] is not None]
    statuses = {status: sum(r["status"] == status for r in rows)
                for status in sorted({r["status"] for r in rows})}
    metrics = {
        "duration_s": rows[-1]["time_s"], "observations": observations,
        "cruise_window_x_m": [margin, e.path_length_m - margin],
        "cruise_samples": len(cruise), "true_lateral_rms_m": _rms(truth_error),
        "true_lateral_peak_to_peak_m": max(truth_error) - min(truth_error) if cruise else None,
        "true_lateral_max_abs_m": max(abs(r["true_y_m"]) for r in rows),
        "true_centerline_crossings": _crossings(truth_error, 0.02),
        "steering_reversals": _crossings([r["command_w_radps"] for r in cruise], 0.02),
        "command_w_rms_radps": _rms([r["command_w_radps"] for r in cruise]),
        "mean_sample_age_s": sum(sample_ages) / len(sample_ages) if sample_ages else None,
        "reported_arrived": rows[-1]["status"] == "arrived",
        "true_endpoint_error_m": math.hypot(sim.state.x - e.path_length_m, sim.state.y),
        "true_final_x_m": sim.state.x, "status_frames": statuses,
    }
    sources = ["simulation/physics.py", "simulation/sensors.py", "simulation/server.py",
               "simulation/rtk_experiment.py", e.graph_path,
               "edge/nodes/control/track_controller/atom.py",
               "edge/nodes/planning/path_progress/atom.py",
               "edge/nodes/planning/waypoint_selector/atom.py",
               "edge/nodes/localization/coord_transform/atom.py",
               "edge/nodes/localization/coord_transform/utils/geo.py",
               "edge/nodes/sensing/rtk_filter/atom.py"]
    return {"experiment": asdict(e), "metrics": metrics,
            "controller_params": params, "selector_params": selector_params,
            "progress_params": progress_params,
            "filter_params": {"alpha_pos": filter_.alpha_pos,
                              "alpha_heading": filter_.alpha_heading, "use_imu_yaw_rate": False},
            "scope": "Fixed-step RTK steering experiment; implement raised, no soil/load calibration; no IPC scheduling.",
            "source_sha256": {p: hashlib.sha256((ROOT / p).read_bytes()).hexdigest() for p in sources}}, rows


def plot_comparison(runs, output: Path):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    figure, axes = plt.subplots(3, 1, figsize=(11, 8), constrained_layout=True)
    for result, rows in runs:
        name = result["experiment"]["name"]
        axes[0].plot([r["true_x_m"] for r in rows], [r["true_y_m"] for r in rows], label=name, linewidth=1.1)
        axes[1].plot([r["time_s"] for r in rows], [r["command_w_radps"] for r in rows], label=name, linewidth=.7, alpha=.8)
        axes[2].plot([r["time_s"] for r in rows], [r["sample_age_s"] for r in rows], label=name, linewidth=.8)
    axes[0].axhline(0, color="black", linewidth=.7, linestyle="--")
    axes[0].set(xlabel="True forward position (m)", ylabel="True lateral error (m)")
    axes[1].set(xlabel="Simulation time (s)", ylabel="Steering command (rad/s)")
    axes[2].set(xlabel="Simulation time (s)", ylabel="RTK sample age (s)")
    for ax in axes:
        ax.grid(alpha=.2)
    axes[0].legend(ncol=3, fontsize=8, loc="upper right")
    figure.suptitle("Pure RTK straight-line tracking | synthetic, fixed-step experiments\nLateral axis enlarged; not a field-scale map", fontsize=12)
    figure.savefig(output, dpi=160)
    plt.close(figure)


def plot_observations(result, rows, output: Path):
    """Keep measured pose separate from true motion and vehicle response."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    figure, axes = plt.subplots(3, 1, figsize=(11, 8), constrained_layout=True, sharex=True)
    times = [r["time_s"] for r in rows]
    for column, label, color in (("rtk_y_m", "RTK delivered", "#a5b4c6"),
                                 ("filtered_y_m", "Filtered RTK", "#e08627"),
                                 ("true_y_m", "True vehicle", "#18649b")):
        axes[0].plot(times, [r[column] for r in rows], label=label, color=color, linewidth=1)
    for column, label, color in (("rtk_yaw_deg", "RTK delivered", "#a5b4c6"),
                                 ("filtered_yaw_deg", "Filtered RTK", "#e08627"),
                                 ("true_yaw_deg", "True vehicle", "#18649b")):
        axes[1].plot(times, [r[column] for r in rows], label=label, color=color, linewidth=1)
    axes[2].plot(times, [r["command_w_radps"] for r in rows], label="Command", color="#e08627", linewidth=1)
    axes[2].plot(times, [r["true_w_radps"] for r in rows], label="Actual response", color="#18649b", linewidth=1)
    for ax, ylabel in zip(axes, ("Lateral position (m)", "Heading (degrees)", "Yaw rate (rad/s)")):
        ax.set_ylabel(ylabel)
        ax.grid(alpha=.2)
        ax.legend(loc="upper right", ncol=3, fontsize=8)
    axes[-1].set_xlabel("Simulation delivery time (s); measurements retain their acquisition timestamp in CSV")
    figure.suptitle(f"{result['experiment']['name']} | observation versus actual movement", fontsize=13)
    figure.savefig(output, dpi=160)
    plt.close(figure)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--scenario", action="append", help="May be repeated; default runs all scenarios")
    parser.add_argument("--seed", type=int, help="Override the configured seed for every scenario")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--no-plot", action="store_true")
    args = parser.parse_args(argv)
    config = yaml.safe_load(args.config.read_text(encoding="utf-8"))
    scenarios = config["scenarios"]
    selected = args.scenario or list(scenarios)
    unknown = set(selected) - scenarios.keys()
    if unknown:
        parser.error(f"unknown scenarios: {sorted(unknown)}")
    args.output.mkdir(parents=True, exist_ok=True)
    runs = []
    for name in selected:
        if not name or any(c not in "abcdefghijklmnopqrstuvwxyz0123456789_-" for c in name):
            parser.error("scenario names may contain only lowercase letters, digits, underscores and hyphens")
        experiment = Experiment(**{**config.get("base", {}), **(scenarios[name] or {}), "name": name})
        if args.seed is not None:
            experiment = replace(experiment, seed=args.seed)
        result, rows = run_experiment(experiment)
        (args.output / f"{name}.json").write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        with (args.output / f"{name}.csv").open("w", encoding="utf-8", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
            writer.writeheader()
            writer.writerows(rows)
        runs.append((result, rows))
        print(json.dumps({"scenario": name, **result["metrics"]}, ensure_ascii=False))
    (args.output / "summary.json").write_text(json.dumps([r for r, _ in runs], ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if not args.no_plot:
        plot_comparison(runs, args.output / "comparison.png")
        detailed = next((run for run in runs if run[0]["experiment"]["name"] == "combined"), runs[-1])
        plot_observations(*detailed, args.output / "observations.png")


if __name__ == "__main__":
    main()
