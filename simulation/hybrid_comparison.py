"""Compare wide-turn work with the same route followed by boundary cleanup.

Run ``python -m simulation.hybrid_comparison --output /tmp/hybrid_results``.
Coverage comes from the shared oriented-rectangle sweep evaluator. These are
planned footprints; vehicle tracking and implement response require a separate
closed-loop experiment.
"""
from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
import json
import math
from pathlib import Path
import time

from shapely.geometry import Polygon, mapping

from edge.nodes.planning.global_coverage.utils.models import ParcelData, VehicleConfig
from edge.nodes.planning.global_coverage.utils.planner import GlobalCoveragePlanner
from edge.nodes.planning.global_coverage.utils.safe_area import build_safe_area
from simulation.planner_comparison import (
    ComparisonSettings, _fill_geometry, _json_value, evaluate_paths,
)


@dataclass(frozen=True)
class HybridSettings(ComparisonSettings):
    path_inset_m: float = 0.3
    max_curvature_rate_1pm2: float = 0.08
    boundary_target_coverage_ratio: float = 0.98
    boundary_max_layers: int = 16

    def validate(self):
        super().validate()
        if self.max_curvature_rate_1pm2 <= 0:
            raise ValueError("Curvature rate must be positive")
        if not 0 < self.boundary_target_coverage_ratio <= 1:
            raise ValueError("Target coverage ratio must be in (0, 1]")
        if not isinstance(self.boundary_max_layers, int) or self.boundary_max_layers < 0:
            raise ValueError("Boundary layer limit must be a nonnegative integer")


def rectangle_parcel(width_m=40.0, length_m=70.0):
    if not all(math.isfinite(v) and v > 0 for v in (width_m, length_m)):
        raise ValueError("Parcel dimensions must be finite and positive")
    return ParcelData(outer=[(0, 0), (width_m, 0), (width_m, length_m), (0, length_m)])


def path_distance(points):
    return sum(math.dist(a, b) for a, b in zip(points, points[1:]))


def boundary_start_index(base_path, combined_path):
    """Locate appended cleanup without inventing a connector or a work zone.

    A planner is allowed to change the final base point's zone to transit. The
    coordinates themselves must retain the entire original main-work prefix.
    Returning its last point includes the real first transfer in the plot.
    """
    if len(combined_path) < len(base_path) or any(
            math.dist(first, second) > 1e-7
            for first, second in zip(base_path, combined_path)):
        raise ValueError("Combined plan did not retain the main wide-turn route as a prefix")
    return max(0, len(base_path)-1)


def _summary(base, combined):
    first, last = base["metrics"], combined["metrics"]
    start = boundary_start_index(base["path"], combined["path"])
    zones = combined["zones"][start:]
    return {
        "evaluation_scope": "planned_rectangular_sweep_not_closed_loop",
        "coverage_gain_percentage_points": last["coverage_rate_percent"]-first["coverage_rate_percent"],
        "parcel_coverage_gain_percentage_points": (
            last["parcel_coverage_rate_percent"]-first["parcel_coverage_rate_percent"]),
        "newly_covered_work_area_m2": last["unique_covered_area_m2"]-first["unique_covered_area_m2"],
        "remaining_work_area_m2": last["missed_area_m2"],
        "remaining_parcel_area_m2": last["parcel_missed_area_m2"],
        "main_path_length_m": path_distance(base["path"]),
        "combined_path_length_m": path_distance(combined["path"]),
        "added_boundary_and_transfer_length_m": path_distance(combined["path"][start:]),
        "boundary_start_index": start,
        "planned_implement_lifts": last["planned_implement_lifts_within_paths"],
        "boundary_transit_runs": (sum(stage["zone"] == "transit"
                                      for stage in combined["metadata"]["execution_stages"])
                                  if combined["metadata"].get("execution_stages") else
                                  sum(zone == "transit" and (index == 0 or zones[index-1] != "transit")
                                      for index, zone in enumerate(zones))),
        "boundary_layers": combined["metadata"].get("boundary_layer_count",
                                                       combined["metadata"].get("boundary_layers")),
        "boundary_pass_count": combined["metadata"].get("cleanup_pass_count"),
        "outside_parcel_area_m2": last["outside_parcel_area_m2"],
    }


def stage_paths(path, zones, metadata):
    """Keep stage-boundary headings separate while preserving every transfer.

    Shared endpoints belong to both stages. Averaging headings across a stopped,
    lifted alignment would otherwise rotate an active implement at that point.
    """
    stages = metadata.get("execution_stages")
    if not stages:
        return [{"points": path, "zones": zones}]
    result = []
    previous_end = 0
    for stage in stages:
        start, end = stage["start_index"], stage["end_index"]
        if start != previous_end or not 0 <= start <= end < len(path):
            raise ValueError("Execution stages must cover the connected path with shared endpoints")
        if stage["zone"] not in {"work", "transit"}:
            raise ValueError("Execution stages need explicit work/transit intent")
        result.append({"points": path[start:end+1], "zones": [stage["zone"]]*(end-start+1)})
        previous_end = end
    if previous_end != len(path)-1:
        raise ValueError("Execution stages do not cover the complete path")
    return result


def compare_hybrid(parcel, settings=None, checkpoint=None):
    settings = settings or HybridSettings()
    settings.validate()
    vehicle = VehicleConfig(
        implement_width_m=settings.implement_width_m,
        overlap_ratio=settings.overlap_ratio, path_inset_m=settings.path_inset_m,
        pivot_turn=True, work_min_turn_radius_m=settings.min_turn_radius_m,
        work_max_curvature_rate_1pm2=settings.max_curvature_rate_1pm2,
    )
    work_area, _ = build_safe_area(parcel.to_dict(), vehicle)
    parcel_area = Polygon(parcel.outer, parcel.holes)
    if work_area.is_empty:
        raise ValueError("Requested setback removes the entire field")
    report = {
        "complete": False, "settings": asdict(settings),
        "parcel_input": parcel.to_dict(), "parcel_geometry": mapping(parcel_area),
        "work_geometry": mapping(work_area), "results": [],
        "measurement_notes": {
            "coverage": "Both paths use the same oriented rectangular implement sweep, with batch size 4096.",
            "denominators": "Work coverage excludes the requested setback; whole-parcel coverage includes it.",
            "intent": "Transit points do not contribute to worked area. No missing connections are synthesized.",
            "execution": "This is planned coverage, not measured vehicle or implement motion.",
        },
    }
    geometries = {}
    for strategy in ("wide_turn", "wide_turn_boundary"):
        planner = GlobalCoveragePlanner()
        options = {"planning_strategy": strategy, "path_point_spacing": settings.path_point_spacing_m}
        if strategy == "wide_turn_boundary":
            options.update(boundary_target_coverage_ratio=settings.boundary_target_coverage_ratio,
                           boundary_max_layers=settings.boundary_max_layers)
        begin = time.perf_counter()
        path = planner.plan(parcel, vehicle, **options)
        planning_elapsed = time.perf_counter()-begin
        zones = planner.last_path_zones
        if not path:
            raise ValueError(f"{strategy} did not generate a path")
        if zones is None:
            raise ValueError(f"{strategy} did not expose work/transit intent")
        begin = time.perf_counter()
        evaluated_paths = stage_paths(path, zones, planner.last_plan_metadata)
        metrics, geometry = evaluate_paths(evaluated_paths, work_area, parcel_area, settings)
        stages = planner.last_plan_metadata.get("execution_stages")
        if stages:
            # These are contiguous execution stages, not disconnected plans.
            metrics.update(independent_path_count=1, unplanned_connections=0,
                           planned_implement_lifts_within_paths=sum(
                               stage["zone"] == "transit" for stage in stages),
                           single_continuous_work_path=all(stage["zone"] == "work" for stage in stages),
                           point_count=len(path), evaluated_stage_count=len(stages))
        result = {
            "strategy": strategy, "path": path, "zones": zones,
            "metadata": planner.last_plan_metadata, "metrics": metrics,
            "planning_elapsed_s": planning_elapsed,
            "evaluation_elapsed_s": time.perf_counter()-begin,
        }
        report["results"].append(result)
        geometries[strategy] = geometry
        print(f"{strategy}: work coverage {metrics['coverage_rate_percent']:.2f}%, "
              f"whole parcel {metrics['parcel_coverage_rate_percent']:.2f}%, "
              f"length {path_distance(path):.1f} m", flush=True)
        if checkpoint:
            checkpoint(report)
    report["summary"] = _summary(*report["results"])
    report["complete"] = True
    return report, geometries


def plot_hybrid(report, geometries, output):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.collections import LineCollection
    from matplotlib.lines import Line2D
    from matplotlib.patches import Patch
    from shapely.geometry import shape

    parcel, work = shape(report["parcel_geometry"]), shape(report["work_geometry"])
    base, combined = report["results"]
    summary = report["summary"]
    fig, axes = plt.subplots(1, 3, figsize=(13.8, 8.0), constrained_layout=False)
    for ax in axes:
        _fill_geometry(ax, parcel, "#e5e7e4", linewidth=.9)
        _fill_geometry(ax, work, "#d5eadb", linewidth=.5)
        ax.set_aspect("equal")
        ax.set_xlabel("East (m)")
        ax.set_ylabel("North (m)")
        ax.autoscale()
        ax.margins(.045)
    for ax, result in ((axes[0], base), (axes[2], combined)):
        _fill_geometry(ax, geometries[result["strategy"]]["missed"], "#d77468")
    axes[0].add_collection(LineCollection(list(zip(base["path"], base["path"][1:])),
                                         colors="#4b7c67", linewidth=.33, alpha=.7))
    start = summary["boundary_start_index"]
    points, zones = combined["path"][start:], combined["zones"][start:]
    stages = combined["metadata"].get("execution_stages")
    drawn_paths = (stage_paths(combined["path"], combined["zones"], combined["metadata"])[1:]
                   if stages else [{"points": points, "zones": zones}])
    for working, color, style in ((True, "#136c64", "solid"), (False, "#b06426", "dashed")):
        runs = []
        for drawn in drawn_paths:
            run = []
            for index, (first, second) in enumerate(zip(drawn["points"], drawn["points"][1:])):
                matches = (drawn["zones"][index] == drawn["zones"][index+1] == "work") == working
                if matches:
                    run.extend([first, second] if not run else [second])
                elif run:
                    runs.append(run)
                    run = []
            if run:
                runs.append(run)
        axes[1].add_collection(LineCollection(runs, colors=color, linewidth=1.05,
                                             linestyles=style, alpha=.9))
    if points:
        axes[1].scatter(*points[0], color="#305c9f", s=22, zorder=5)
    for ax, result, title in ((axes[0], base, "1  Main work: remaining ground"),
                               (axes[2], combined, "3  After boundary cleanup")):
        metrics = result["metrics"]
        ax.set_title(f"{title}\nWork {metrics['coverage_rate_percent']:.2f}% | "
                     f"whole parcel {metrics['parcel_coverage_rate_percent']:.2f}%", fontsize=11, pad=12)
    layer_text = (f"{summary['boundary_layers']} layers | " if summary["boundary_layers"] is not None else "")
    axes[1].set_title("2  Added boundary work and transfers\n"
                      f"{layer_text}{summary['boundary_transit_runs']} raised-implement transfers", fontsize=11, pad=12)
    fig.suptitle("Wide turns + boundary cleanup\n"
                 f"+{summary['coverage_gain_percentage_points']:.2f} coverage points in work area  |  "
                 f"+{summary['added_boundary_and_transfer_length_m']:.0f} m route  |  "
                 f"{summary['remaining_work_area_m2']:.1f} m2 still unworked", fontsize=14, y=.96)
    fig.legend(handles=[Patch(color="#d5eadb", label="Worked"),
                        Patch(color="#d77468", label="Remaining in work area"),
                        Patch(color="#e5e7e4", label="Excluded setback"),
                        Line2D([0], [0], color="#136c64", label="Boundary work"),
                        Line2D([0], [0], color="#b06426", linestyle="--", label="Implement raised")],
               loc="lower center", bbox_to_anchor=(.5, .075), ncol=3, fontsize=10, frameon=False)
    fig.text(.5, .035, "Planned rectangular implement sweep. Tracking error and implement response are not included.",
             ha="center", fontsize=10, color="#53605a")
    fig.tight_layout(rect=(.02, .23, .98, .88))
    fig.savefig(output, dpi=170)
    plt.close(fig)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--width", type=float, default=40.0)
    parser.add_argument("--length", type=float, default=70.0)
    parser.add_argument("--radius", type=float, default=4.0)
    parser.add_argument("--target", type=float, default=.98)
    parser.add_argument("--layers", type=int, default=16)
    parser.add_argument("--no-plots", action="store_true")
    arguments = parser.parse_args(argv)
    settings = HybridSettings(min_turn_radius_m=arguments.radius,
                              boundary_target_coverage_ratio=arguments.target,
                              boundary_max_layers=arguments.layers)
    arguments.output.mkdir(parents=True, exist_ok=True)

    def save_report(report):
        (arguments.output / "comparison.json").write_text(
            json.dumps(_json_value(report), ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8")

    report, geometries = compare_hybrid(rectangle_parcel(arguments.width, arguments.length), settings, save_report)
    save_report(report)
    (arguments.output / "summary.json").write_text(json.dumps(_json_value({
        "settings": report["settings"], "summary": report["summary"],
        "results": [{key: value for key, value in result.items() if key not in {"path", "zones"}}
                    for result in report["results"]],
    }), ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8")
    if not arguments.no_plots:
        plot_hybrid(report, geometries, arguments.output / "comparison.png")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
