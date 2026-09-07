"""Run a coverage plan through the existing RTK, tracking and implement logic.

The initial vehicle pose is aligned with the first planned segment. Entry from
an arbitrary gate is a separate manoeuvre and is not fabricated by this runner.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
from dataclasses import asdict, fields
from pathlib import Path

import yaml

from edge.nodes.control.track_controller.atom import ControlSafetyGuard, compute_velocity_cmd
from edge.nodes.implement.tillage_controller.atom import TillageConfig, TillageController
from edge.nodes.localization.coord_transform.atom import transform_pose
from edge.nodes.planning.global_coverage.utils.models import ParcelData, VehicleConfig
from edge.nodes.planning.global_coverage.utils.operation_plan import build_operation_plan
from edge.nodes.planning.global_coverage.utils.planner import GlobalCoveragePlanner
from edge.nodes.planning.path_progress.atom import _path_stations, compute_progress
from edge.nodes.planning.waypoint_selector.atom import ViewConfig, WaypointSelector
from edge.nodes.sensing.rtk_filter.atom import EMAFilter
from simulation.evaluation import CoverageAccumulator
from simulation.rtk_experiment import ROOT, Experiment, _node_parameters, _simulator_config
from simulation.server import SimulatorServer


def run_coverage_experiment(plan, parcel, vehicle, *, duration_s=1800.0, seed=42,
                            position_noise_std_m=0.0, heading_noise_std_deg=0.0):
    if plan.get("status") != "success" or len(plan.get("path", [])) < 2:
        raise ValueError("A successful executable operation_plan is required")
    if plan.get("summary", {}).get("planner", {}).get("execution_ready") is False:
        raise ValueError("Raw geometric candidates cannot drive the simulator")
    if parcel.points:
        raise ValueError("Coverage experiments require point obstacles expressed as polygon holes")
    if not math.isfinite(duration_s) or duration_s <= 0:
        raise ValueError("duration_s must be finite and positive")
    e = Experiment(seed=seed, position_noise_std_m=position_noise_std_m,
                   heading_noise_std_deg=heading_noise_std_deg)
    e.validate()
    drive_params, selector_params, progress_params, filter_params, guard_params = _node_parameters(e)
    drive_params["require_implement_ready"] = True
    selector = WaypointSelector(ViewConfig(**selector_params))
    selector.set_path(plan)
    path = plan["path"]
    x, y = path[0]
    heading = next(math.atan2(p[1]-y, p[0]-x) for p in path[1:] if math.hypot(p[0]-x, p[1]-y) > 1e-8)
    config = _simulator_config(e)
    config["server"]["initial_pose"] = {"x": x, "y": y, "yaw": heading}
    config["field"] = {"boundary": parcel.outer, "fixed_holes": parcel.holes}
    config["physics"]["bounds"] = {
        "x": [min(p[0] for p in parcel.outer)-20, max(p[0] for p in parcel.outer)+20],
        "y": [min(p[1] for p in parcel.outer)-20, max(p[1] for p in parcel.outer)+20],
    }
    sim = SimulatorServer(config=config, initial_sim_time=0.0)
    filtering = EMAFilter(filter_params.get("alpha_pos", .2), filter_params.get("alpha_heading", .3), False)
    graph = yaml.safe_load((ROOT/e.graph_path).read_text())
    tillage_params = next(n["params"] for n in graph["nodes"] if n["id"] == "tillage_controller")
    keys = {f.name for f in fields(TillageConfig)}
    tillage_config = TillageConfig(**{k: v for k, v in tillage_params.items() if k in keys})
    tillage_config.require_implement_feedback = True
    tillage = TillageController(tillage_config, clock=lambda: sim.state.sim_time)
    guard = ControlSafetyGuard(**guard_params)
    stations = _path_stations(path)
    # Offline evaluation needs only the final union. Larger batches avoid
    # repeatedly unioning an entire multi-kilometre sweep at every few metres.
    evaluator = CoverageAccumulator(parcel.outer, vehicle.implement_width_m,
                                     field_holes=parcel.holes, batch_size=4096)
    pose = target = progress = None
    last_seq = None
    path_index = truth_index = 0
    rows, status_counts = [], {}
    command = {"linear_velocity": 0.0, "angular_velocity": 0.0}
    arrived_since = stalled_since = None
    stop_reason = "duration_limit"
    last_coverage_working = None
    for step in range(math.ceil(duration_s/e.dt_s)+1):
        now = sim.state.sim_time
        if step % 5 == 0:
            sample = sim.sensors.get_rtk_gps_data()
            if sample and sample["seq"] != last_seq:
                last_seq = sample["seq"]
                filtered = filtering.update(sample, None, now)
                new_pose = transform_pose(filtered, 121.5, 31.2)
                if new_pose:
                    pose = new_pose
                    guard.note_pose(now)
        if step % 2 == 0:
            progress = compute_progress(plan, pose, path_index, path_stations=stations, **progress_params)
            if progress:
                path_index = progress["path_index"]
                target = selector.select(pose, progress)
                guard.note_target(target, now)
            implement_command = tillage.update(pose=pose, next_point=target, path_progress=progress)
            sim._set_actuator({"actuator": "implement", "data": implement_command})
            feedback = sim.state.to_dict()["implement"]
            tillage_status = tillage.get_status(feedback, feedback_age_s=0.0)
            command = compute_velocity_cmd(pose, target, now=now, path_progress=progress,
                                           tillage_status=tillage_status, **drive_params)
            command = guard.apply(command, now, now)
            sim._set_actuator({"actuator": "velocity", "data": command})
            status = command.get("status", "tracking")
            status_counts[status] = status_counts.get(status, 0)+1
            if status == "arrived":
                arrived_since = now if arrived_since is None else arrived_since
            else:
                arrived_since = None
            if status == "needs_reposition":
                stalled_since = now if stalled_since is None else stalled_since
            else:
                stalled_since = None
        if step % 10 == 0:
            state = sim.state
            truth = {"x": state.x, "y": state.y, "theta": state.yaw}
            truth_progress = compute_progress(plan, truth, truth_index, path_stations=stations, **progress_params)
            truth_index = truth_progress["path_index"]
            working = state.hitch_height >= .95 and state.pto_on
            if step % 50 == 0 or working != last_coverage_working:
                evaluator.add({**truth, "hitch_height": state.hitch_height, "pto_on": state.pto_on,
                               "position_source": "simulation_truth", "implement_source": "simulation_feedback"})
                last_coverage_working = working
            rows.append({"time_s": round(now, 8), "true_x_m": state.x, "true_y_m": state.y,
                         "true_theta_rad": state.yaw, "true_v_mps": state.vx,
                         "true_w_radps": state.omega_yaw,
                         "rtk_x_m": pose["x"] if pose else None, "rtk_y_m": pose["y"] if pose else None,
                         "true_cte_m": truth_progress["cross_track_error_m"],
                         "path_station_m": truth_progress["station_m"],
                         "hitch_height": state.hitch_height, "pto_on": state.pto_on,
                         "pto_rpm": state.pto_rpm, "implement_ready": tillage_status["ready"],
                         "command_v_mps": command["linear_velocity"],
                         "command_w_radps": command["angular_velocity"],
                         "status": command.get("status", "tracking")})
        if arrived_since is not None and now-arrived_since >= 2.0:
            stop_reason = "reported_arrived"
            break
        if stalled_since is not None and now-stalled_since >= 5.0:
            stop_reason = "needs_reposition"
            break
        if step < math.ceil(duration_s/e.dt_s):
            sim.step_once(command_elapsed_s=(step % 2)*e.dt_s)
    moving = [r for r in rows if abs(r["true_v_mps"]) > .1]
    error = math.hypot(sim.state.x-path[-1][0], sim.state.y-path[-1][1])
    metrics = {
        **evaluator.metrics(), "stop_reason": stop_reason, "duration_s": round(sim.state.sim_time, 3),
        "true_endpoint_error_m": error,
        "completed": stop_reason == "reported_arrived" and error <= drive_params["final_stop_dist"],
        "true_cte_rms_m": math.sqrt(sum(r["true_cte_m"]**2 for r in moving)/len(moving)) if moving else None,
        "true_cte_max_abs_m": max(abs(r["true_cte_m"]) for r in rows),
        "path_length_m": stations[-1], "final_path_station_m": rows[-1]["path_station_m"],
        "mid_work_pto_disengagements": sum(a["pto_on"] and not b["pto_on"] and b["status"] != "arrived"
                                             for a, b in zip(rows, rows[1:])),
        "status_frames": status_counts,
        "initialization": "aligned_with_first_segment; entry manoeuvre excluded",
        "evaluation_source": "simulated_true_pose_and_implement_feedback",
        "coverage_observation_period_s": .5,
    }
    return {"metrics": metrics, "seed": seed, "drive_params": drive_params,
            "position_noise_std_m": position_noise_std_m, "heading_noise_std_deg": heading_noise_std_deg}, rows


def write_runtime_fixture(plan, parcel, vehicle, output_dir):
    """Create matching server/graph configs for an aligned-start runtime demo."""
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    e = Experiment()
    server = _simulator_config(e)
    path = plan["path"]
    start = path[0]
    yaw = next(math.atan2(p[1]-start[1], p[0]-start[0]) for p in path[1:] if math.dist(p, start) > 1e-8)
    server["server"].update(realtime=True, initial_pose={"x": start[0], "y": start[1], "yaw": yaw})
    server["field"] = {"boundary": parcel.outer, "fixed_holes": parcel.holes}
    server["vehicle"] = asdict(vehicle)
    graph = yaml.safe_load((ROOT/e.graph_path).read_text())
    graph["description"] = "大半径连续旋耕演示；仿真初始位置与首段对齐"
    for node in graph["nodes"]:
        if node["id"] == "global_coverage":
            node["params"].update(planning_strategy=plan["summary"]["planner"]["strategy"],
                                  path_point_spacing=.25, work_speed_limit_mps=.8)
        elif node["id"] == "sim_output":
            node["params"].update({k: v for k, v in asdict(vehicle).items() if v is not None})
    for name, config in (("server.yaml", server), ("graph.yaml", graph)):
        (output_dir/name).write_text(yaml.safe_dump(config, allow_unicode=True, sort_keys=False), encoding="utf-8")


def plot_tracking(plan, parcel, result, rows, output):
    import bisect
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    path = plan["path"]
    stations = _path_stations(path)
    initial = math.atan2(path[1][1]-path[0][1], path[1][0]-path[0][0])
    bend = next((i for i in range(1, len(path)-1)
                 if abs(math.atan2(math.sin(math.atan2(path[i+1][1]-path[i][1], path[i+1][0]-path[i][0])-initial),
                                   math.cos(math.atan2(path[i+1][1]-path[i][1], path[i+1][0]-path[i][0])-initial))) > .04), 1)
    turn_end = next((i for i in range(bend, len(path)-1)
                     if abs(math.atan2(math.sin(math.atan2(path[i+1][1]-path[i][1], path[i+1][0]-path[i][0])-initial),
                                       math.cos(math.atan2(path[i+1][1]-path[i][1], path[i+1][0]-path[i][0])-initial))) > math.pi-.04), bend)
    left = max(0, bisect.bisect_left(stations, stations[bend]-3))
    right = min(len(path)-1, bisect.bisect_right(stations, stations[turn_end]+3))
    section = path[left:right+1]
    local_rows = [r for r in rows if stations[left] <= r["path_station_m"] <= stations[right]]
    fig = plt.figure(figsize=(12, 8), constrained_layout=True)
    grid = fig.add_gridspec(2, 2, width_ratios=(1, 1.2))
    full = fig.add_subplot(grid[:, 0])
    turn = fig.add_subplot(grid[0, 1])
    error = fig.add_subplot(grid[1, 1])
    outer = parcel.outer+[parcel.outer[0]]
    full.plot(*zip(*outer), color="#637064", linewidth=1)
    for ax, planned, measured in ((full, path, rows), (turn, section, local_rows)):
        ax.plot(*zip(*planned), color="#e59938", linewidth=1.2, label="Planned")
        if measured:
            ax.plot([r["true_x_m"] for r in measured], [r["true_y_m"] for r in measured],
                    color="#176b91", linewidth=.8, label="True vehicle")
        ax.set_aspect("equal")
        ax.set_xlabel("East (m)")
        ax.set_ylabel("North (m)")
        ax.grid(alpha=.2)
        ax.legend(fontsize=8)
    full.set_title("Complete route")
    turn.set_title("First wide turn")
    error.plot([r["time_s"]/60 for r in rows], [r["true_cte_m"] for r in rows], color="#176b91", linewidth=.7)
    error.set(xlabel="Simulation time (min)", ylabel="True lateral error (m)", title="Tracking error along the full route")
    error.grid(alpha=.2)
    metrics = result["metrics"]
    fig.suptitle(f"Wide-turn coverage | completed: {metrics['completed']} | "
                 f"intermediate PTO releases: {metrics['mid_work_pto_disengagements']}\n"
                 f"Whole-field coverage {metrics['coverage_rate_percent']:.1f}% | "
                 f"outside {metrics['outside_area_m2']:.2f} m2 | aligned start, ideal RTK", fontsize=12)
    fig.savefig(output, dpi=170)
    plt.close(fig)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--strategy", choices=["wide_turn", "contour_spiral"], default="wide_turn")
    parser.add_argument("--width", type=float, default=40)
    parser.add_argument("--length", type=float, default=70)
    parser.add_argument("--radius", type=float, default=4)
    parser.add_argument("--duration", type=float, default=1800)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--prepare-runtime", action="store_true", help="Write matching server.yaml / graph.yaml without offline tracking")
    args = parser.parse_args(argv)
    parcel = ParcelData(outer=[(0, 0), (args.width, 0), (args.width, args.length), (0, args.length)])
    vehicle = VehicleConfig(implement_width_m=1.2, overlap_ratio=.1, path_inset_m=.3,
                            pivot_turn=False, work_min_turn_radius_m=args.radius,
                            work_max_curvature_rate_1pm2=.08)
    planner = GlobalCoveragePlanner()
    path = planner.plan(parcel, vehicle, path_point_spacing=.25, planning_strategy=args.strategy)
    plan = build_operation_plan("coverage_experiment", path, vehicle, timestamp=0,
                                work_speed_mps=.8, turn_speed_mps=.5,
                                path_zones=planner.last_path_zones, planner_metadata=planner.last_plan_metadata)
    if args.prepare_runtime:
        write_runtime_fixture(plan, parcel, vehicle, args.output)
        print(f"Runtime configurations written to {args.output}")
        return
    result, rows = run_coverage_experiment(plan, parcel, vehicle, duration_s=args.duration)
    args.output.mkdir(parents=True, exist_ok=True)
    (args.output/"plan.json").write_text(json.dumps({"plan": plan, "parcel": parcel.to_dict(), "vehicle": asdict(vehicle)}, indent=2)+"\n")
    (args.output/"result.json").write_text(json.dumps(result, indent=2)+"\n")
    with (args.output/"trajectory.csv").open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=rows[0].keys())
        writer.writeheader()
        writer.writerows(rows)
    plot_tracking(plan, parcel, result, rows, args.output/"tracking.png")
    print(json.dumps(result["metrics"], indent=2))


if __name__ == "__main__":
    main()
