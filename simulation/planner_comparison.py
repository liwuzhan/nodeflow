"""Compare actual coverage planners on the same inset field geometry.

Run ``python -m simulation.planner_comparison --output /tmp/planner_results``.
This evaluates planned implement sweeps, not closed-loop vehicle tracking. NEPath
paths remain disconnected, raw candidates even if their coverage looks good.
"""
from __future__ import annotations

import argparse
import bisect
import json
import math
import time
from dataclasses import asdict, dataclass
from pathlib import Path

from shapely.geometry import Polygon, mapping
from shapely.ops import unary_union

from edge.nodes.planning.global_coverage.utils.models import ParcelData, VehicleConfig
from edge.nodes.planning.global_coverage.utils.planner import GlobalCoveragePlanner
from edge.nodes.planning.global_coverage.utils.safe_area import build_safe_area
from simulation.evaluation import CoverageAccumulator


MEASUREMENT_NOTES = {
    "coverage": "Shared oriented-rectangle sweep of planned paths; no closed-loop tracking error is included.",
    "curvature": "Fixed-window curvature is a polyline estimate, not an analytic minimum-radius acceptance test. "
                 "The window can be shorter than the planner's original arc chords even after collinear "
                 "point insertion. Read analytic planner constraints separately; unsmoothed vertex data is retained.",
    "nepath": "Raw independent paths are evaluated without adding transfers and remain non-executable candidates.",
}


@dataclass(frozen=True)
class ComparisonSettings:
    implement_width_m: float = 1.2
    implement_length_m: float = 0.2
    implement_offset_m: float = 0.0
    overlap_ratio: float = 0.1
    path_inset_m: float = 1.0
    min_turn_radius_m: float = 4.0
    path_point_spacing_m: float = 0.25

    def validate(self):
        if not all(math.isfinite(value) for value in asdict(self).values()):
            raise ValueError("Comparison settings must be finite")
        if min(self.implement_width_m, self.implement_length_m,
               self.min_turn_radius_m, self.path_point_spacing_m) <= 0:
            raise ValueError("Dimensions, turn radius and point spacing must be positive")
        if self.path_inset_m < 0 or not 0 <= self.overlap_ratio < 1:
            raise ValueError("Inset must be nonnegative and overlap must be in [0, 1)")


def comparison_cases():
    """Dimensions below are parcel dimensions, before the requested setback."""
    return {
        "long_rectangle": ParcelData(outer=[(0, 0), (102, 0), (102, 30), (0, 30)]),
        "wide_rectangle": ParcelData(outer=[(0, 0), (58, 0), (58, 46), (0, 46)]),
        "large_rectangle": ParcelData(outer=[(0, 0), (102, 0), (102, 62), (0, 62)]),
        "field_with_hole": ParcelData(
            outer=[(0, 0), (82, 0), (82, 50), (0, 50)],
            holes=[[(35, 20), (45, 20), (45, 30), (35, 30)]]),
    }


def _validate_paths(paths):
    for path in paths:
        points, zones = path["points"], path["zones"]
        if len(points) != len(zones):
            raise ValueError("Every path point needs an explicit work/transit zone")
        for point in points:
            if len(point) != 2 or not all(math.isfinite(float(v)) for v in point):
                raise ValueError("Path coordinates must be finite x/y pairs")
        if any(zone not in {"work", "transit"} for zone in zones):
            raise ValueError("Unknown path zone")


def sample_curvature(paths, min_turn_radius_m, probe_distance_m=0.5):
    """Compare curvature over a fixed spatial window, retaining raw corner data.

    This is a sample-level diagnostic, not proof of curvature continuity between
    samples. Inserting collinear midpoints doubles the immediate vertex turn
    density at the old vertices. A fixed +/- 0.5 m window makes that tessellation
    effect comparable; the unsmoothed local trace is retained separately. Both
    methods retain U-turn reversals that a circumcircle alone would miss.
    """
    traces, local_traces, total_station, values, raw_values, reversals = [], [], 0.0, [], [], 0
    maximum_heading_jump = 0.0
    limit = 1.0 / min_turn_radius_m
    for path in paths:
        points, zones = path["points"], path["zones"]
        local = [0.0]
        for a, b in zip(points, points[1:]):
            local.append(local[-1] + math.dist(a, b))
        trace = {"station_m": [], "curvature_1pm": []}
        raw_trace = {"station_m": [], "curvature_1pm": []}

        def at_station(station):
            edge = min(len(points)-2, max(0, bisect.bisect_right(local, station)-1))
            length = local[edge+1]-local[edge]
            fraction = (station-local[edge])/length if length > 1e-9 else 0.0
            return (tuple(points[edge][axis]+fraction*(points[edge+1][axis]-points[edge][axis])
                          for axis in (0, 1)), edge)

        for index in range(1, len(points)-1):
            trace["station_m"].append(total_station + local[index])
            trace["curvature_1pm"].append(None)
            raw_trace["station_m"].append(total_station + local[index])
            raw_trace["curvature_1pm"].append(None)
            if any(z != "work" for z in zones[index-1:index+2]):
                continue
            a, b, c = points[index-1:index+2]
            ab, bc = math.dist(a, b), math.dist(b, c)
            if min(ab, bc) <= 1e-9:
                continue
            incoming = math.atan2(b[1]-a[1], b[0]-a[0])
            outgoing = math.atan2(c[1]-b[1], c[0]-b[0])
            delta = math.atan2(math.sin(outgoing-incoming), math.cos(outgoing-incoming))
            raw_curvature = delta / ((ab+bc)/2)
            raw_values.append(abs(raw_curvature))
            raw_trace["curvature_1pm"][-1] = raw_curvature
            maximum_heading_jump = max(maximum_heading_jump, abs(math.degrees(delta)))
            reversals += int(abs(delta) > math.radians(170))
            first, left = at_station(max(0.0, local[index]-probe_distance_m))
            last, right = at_station(min(local[-1], local[index]+probe_distance_m))
            if any(zone != "work" for zone in zones[left:right+2]):
                continue
            first_length, last_length = math.dist(first, b), math.dist(b, last)
            if min(first_length, last_length) <= 1e-9:
                continue
            incoming = math.atan2(b[1]-first[1], b[0]-first[0])
            outgoing = math.atan2(last[1]-b[1], last[0]-b[0])
            delta = math.atan2(math.sin(outgoing-incoming), math.cos(outgoing-incoming))
            curvature = delta / ((first_length+last_length)/2)
            values.append(abs(curvature))
            trace["curvature_1pm"][-1] = curvature
        traces.append(trace)
        local_traces.append(raw_trace)
        total_station += local[-1]
    maximum = max(values, default=0.0)
    return {
        "method": "heading_change_over_fixed_station_window_chords",
        "probe_distance_each_side_m": probe_distance_m,
        "limit_1pm": limit,
        "limit_relative_tolerance": 0.005,
        "max_abs_curvature_1pm": maximum,
        "sampled_min_radius_m": 1/maximum if maximum > 1e-12 else None,
        "over_limit_sample_count": sum(value > limit*1.005 for value in values),
        "work_curvature_sample_count": len(values),
        "near_reversal_count": reversals,
        "maximum_local_heading_jump_deg": maximum_heading_jump,
        "local_turn_density_max_1pm": max(raw_values, default=0.0),
        "local_turn_density_note": "unsmoothed; depends on collinear midpoint insertion",
        "local_turn_density_traces": local_traces,
        "traces": traces,
    }


def evaluate_paths(paths, work_area, parcel_area, settings):
    """Use the shared sweep evaluator; no artificial straight links are added."""
    _validate_paths(paths)
    accumulator = CoverageAccumulator(
        work_area, settings.implement_width_m,
        implement_length_m=settings.implement_length_m,
        implement_offset_m=settings.implement_offset_m,
        sample_distance_m=settings.path_point_spacing_m,
        batch_size=4096,
    )
    for path in paths:
        accumulator.break_segment()
        points, zones = path["points"], path["zones"]
        for index, point in enumerate(points):
            before = points[max(0, index-1)]
            after = points[min(len(points)-1, index+1)]
            theta = math.atan2(after[1]-before[1], after[0]-before[0])
            accumulator.add({
                "x": point[0], "y": point[1], "theta": theta,
                "working": zones[index] == "work",
                "position_source": "planned_centerline",
                "implement_source": "planned_work_zone",
            })
    metrics = accumulator.metrics()
    geometries = accumulator.geometries()
    # Covered+outside gives the complete footprint union, including the setback
    # strip. This makes the whole-parcel denominator accurate, too.
    entire_sweep = unary_union([geometries["covered"], geometries["outside"]])
    parcel_covered = entire_sweep.intersection(parcel_area).area
    metrics.update({
        "coverage_denominator": "inset_work_area_minus_expanded_holes",
        "evaluation_scope": "planned_sweep_not_vehicle_tracking",
        "parcel_area_m2": parcel_area.area,
        "work_area_m2": work_area.area,
        "excluded_setback_area_m2": parcel_area.area-work_area.area,
        "parcel_unique_covered_area_m2": parcel_covered,
        "parcel_missed_area_m2": max(0.0, parcel_area.area-parcel_covered),
        "parcel_coverage_rate_percent": parcel_covered/parcel_area.area*100,
        "outside_parcel_area_m2": entire_sweep.difference(parcel_area).area,
        "independent_path_count": len(paths),
        "unplanned_connections": max(0, len(paths)-1),
        "planned_implement_lifts_within_paths": sum(
            first == "work" and second == "transit"
            for path in paths for first, second in zip(path["zones"], path["zones"][1:])),
        "single_continuous_work_path": len(paths) == 1 and all(
            zone == "work" for zone in paths[0]["zones"]),
        "point_count": sum(len(path["points"]) for path in paths),
    })
    return metrics, geometries


def generate_candidate(strategy, parcel, settings, work_area):
    if strategy == "nepath_raw":
        from edge.nodes.planning.global_coverage.utils.nepath_coverage import build_nepath_candidate
        result = build_nepath_candidate(
            work_area, settings.implement_width_m,
            overlap_ratio=settings.overlap_ratio,
            path_point_spacing_m=settings.path_point_spacing_m,
            min_turn_radius_m=settings.min_turn_radius_m,
        )
        return ([{"points": path, "zones": ["work"]*len(path)} for path in result.paths],
                {**result.metadata, "path_component_indices": result.path_component_indices},
                "raw_candidate" if result.paths else "no_path")
    planner = GlobalCoveragePlanner()
    vehicle = VehicleConfig(
        implement_width_m=settings.implement_width_m,
        overlap_ratio=settings.overlap_ratio,
        path_inset_m=settings.path_inset_m,
        pivot_turn=False,
        work_min_turn_radius_m=settings.min_turn_radius_m,
    )
    points = planner.plan(parcel, vehicle, path_point_spacing=settings.path_point_spacing_m,
                          planning_strategy=strategy)
    if not points:
        return [], planner.last_plan_metadata, "no_path"
    if planner.last_path_zones is None:
        raise ValueError("Planner did not expose work/transit intent")
    return ([{"points": points, "zones": planner.last_path_zones}],
            planner.last_plan_metadata, "planned")


def compare_case(case_name, parcel, settings, strategies, checkpoint=None):
    settings.validate()
    vehicle = VehicleConfig(implement_width_m=settings.implement_width_m,
                            path_inset_m=settings.path_inset_m)
    work_area, _ = build_safe_area(parcel.to_dict(), vehicle)
    parcel_area = Polygon(parcel.outer, parcel.holes)
    if work_area.is_empty:
        raise ValueError("Requested setback removes the entire field")
    report = {
        "case": case_name, "settings": asdict(settings),
        "measurement_notes": MEASUREMENT_NOTES,
        "parcel_input": parcel.to_dict(),
        "parcel_geometry": mapping(parcel_area), "work_geometry": mapping(work_area),
        "parcel_area_m2": parcel_area.area, "work_area_m2": work_area.area,
        "results": [], "complete": False,
    }
    plot_geometry = {}
    for strategy in strategies:
        start = time.perf_counter()
        result = {"strategy": strategy, "paths": [], "metadata": {}}
        try:
            paths, metadata, status = generate_candidate(strategy, parcel, settings, work_area)
            result.update(paths=paths, metadata=metadata, status=status)
            result["planning_elapsed_s"] = time.perf_counter()-start
            evaluation_start = time.perf_counter()
            if paths:
                result["metrics"], plot_geometry[strategy] = evaluate_paths(
                    paths, work_area, parcel_area, settings)
                result["curvature"] = sample_curvature(paths, settings.min_turn_radius_m)
            result["evaluation_elapsed_s"] = time.perf_counter()-evaluation_start
            if strategy == "nepath_raw":
                result["execution_ready"] = False
            result["path_contract"] = ("raw_disconnected_geometry" if strategy == "nepath_raw"
                                       else "nodeflow_planned_work_transit_path")
        except Exception as error:
            unavailable = isinstance(error, ImportError) or error.__class__.__name__ == "NEPathUnavailableError"
            status = "unavailable" if unavailable else "rejected" if isinstance(error, ValueError) else "error"
            result.update(status=status, error_type=type(error).__name__, error=str(error))
        result["elapsed_s"] = time.perf_counter()-start
        report["results"].append(result)
        print(f"{case_name}/{strategy}: {result['status']} ({result['elapsed_s']:.2f}s)", flush=True)
        if checkpoint is not None:
            checkpoint(report)
    report["complete"] = True
    return report, plot_geometry


def _polygons(geometry):
    if geometry.geom_type == "Polygon":
        return [geometry]
    return [polygon for part in getattr(geometry, "geoms", []) for polygon in _polygons(part)]


def _fill_geometry(ax, geometry, color, *, alpha=1.0, linewidth=0.0):
    from matplotlib.path import Path as PlotPath
    from matplotlib.patches import PathPatch
    from shapely.geometry.polygon import orient
    for polygon in _polygons(geometry):
        rings = []
        for ring in [orient(polygon).exterior, *orient(polygon).interiors]:
            coordinates = list(ring.coords)
            rings.append(PlotPath(coordinates, [PlotPath.MOVETO]
                                  + [PlotPath.LINETO]*(len(coordinates)-2) + [PlotPath.CLOSEPOLY]))
        ax.add_patch(PathPatch(PlotPath.make_compound_path(*rings), facecolor=color,
                              edgecolor="#435348" if linewidth else "none",
                              alpha=alpha, linewidth=linewidth))


def plot_comparison(report, geometries, output):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.collections import LineCollection
    from matplotlib.patches import Patch
    from shapely.geometry import shape

    parcel, work = shape(report["parcel_geometry"]), shape(report["work_geometry"])
    rows = len(report["results"])
    fig, axes = plt.subplots(rows, 3, figsize=(15, 4.1*rows), squeeze=False)
    labels = {"contour_spiral": "Existing contour spiral", "wide_turn": "Wide turn / skipped rows",
              "nepath_raw": "NEPath raw candidate (not executable)"}
    settings = report["settings"]
    for row, result in enumerate(report["results"]):
        name = result["strategy"]
        for ax in axes[row, :2]:
            _fill_geometry(ax, parcel, "#e3e4e1", linewidth=.7)
            _fill_geometry(ax, work, "#f7f8f4", linewidth=.6)
            ax.autoscale()
            ax.set_aspect("equal")
            ax.set_xlabel("East (m)")
            ax.set_ylabel("North (m)")
            ax.margins(.04)
        axes[row, 0].set_title(f"{labels.get(name, name)}\n{result['status']}", fontsize=10)
        if not result.get("metrics") or name not in geometries:
            from textwrap import fill
            axes[row, 1].text(.5, .5, fill(result.get("error", "No path returned"), 52),
                              ha="center", va="center", transform=axes[row, 1].transAxes, fontsize=9)
            axes[row, 1].set_title("No coverage claim")
            axes[row, 2].axis("off")
            continue
        for path in result["paths"]:
            segments = list(zip(path["points"], path["points"][1:]))
            colors = ["#bd5044" if "transit" in path["zones"][index:index+2] else "#276743"
                      for index in range(len(segments))]
            axes[row, 0].add_collection(LineCollection(segments, colors=colors, linewidth=.7))
            if path["points"]:
                axes[row, 0].scatter(*path["points"][0], c="#087ea4", s=12, zorder=5)
        for key, color in [("covered", "#a6d4ad"), ("missed", "#df746d"), ("repeated", "#e9ba4d")]:
            _fill_geometry(axes[row, 1], geometries[name][key], color, alpha=.9)
        metrics = result["metrics"]
        axes[row, 1].set_title(
            f"Work coverage {metrics['coverage_rate_percent']:.1f}% | repeat {metrics['repeat_rate_percent']:.1f}%\n"
            f"Whole parcel {metrics['parcel_coverage_rate_percent']:.1f}% | outside work {metrics['outside_area_m2']:.2f} m2",
            fontsize=10)
        curvature = result["curvature"]
        for trace in curvature["local_turn_density_traces"]:
            axes[row, 2].plot(trace["station_m"], trace["curvature_1pm"], color="#b1b7bc", linewidth=.5)
        for trace in curvature["traces"]:
            axes[row, 2].plot(trace["station_m"], trace["curvature_1pm"], color="#336a96", linewidth=.7)
        limit = curvature["limit_1pm"]
        for value in [-limit, limit]:
            axes[row, 2].axhline(value, color="#bd5044", linestyle="--", linewidth=.8)
        extent = max(limit, curvature["max_abs_curvature_1pm"], curvature["local_turn_density_max_1pm"])*1.10
        axes[row, 2].set_ylim(-extent, extent)
        axes[row, 2].set_title(
            f"Work curvature: fixed span blue, local mesh gray\n"
            f"max {curvature['max_abs_curvature_1pm']:.3f} 1/m | over limit {curvature['over_limit_sample_count']} samples",
            fontsize=10)
        axes[row, 2].set_xlabel("Cumulative planned distance (m)")
        axes[row, 2].set_ylabel("Curvature (1/m)")
        axes[row, 2].grid(alpha=.25)
    fig.suptitle(
        f"{report['case']} | implement {settings['implement_width_m']:.2f} m | requested R >= {settings['min_turn_radius_m']:.1f} m\n"
        f"Parcel {report['parcel_area_m2']:.0f} m2; inset work area {report['work_area_m2']:.0f} m2; "
        "planned geometry only, no vehicle tracking", fontsize=12)
    fig.legend(handles=[Patch(color=color, label=label) for color, label in
                        [("#a6d4ad", "Unique coverage"), ("#df746d", "Missed"),
                         ("#e9ba4d", "Repeated ground"), ("#e3e4e1", "Setback strip"),
                         ("#bd5044", "Transit / implement raised")]],
               loc="lower center", ncol=5, fontsize=9)
    fig.tight_layout(rect=(0, .035, 1, .945))
    fig.savefig(output, dpi=150)
    plt.close(fig)


def _json_value(value):
    if isinstance(value, dict):
        return {key: _json_value(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_json_value(item) for item in value]
    if hasattr(value, "item"):
        value = value.item()
    if isinstance(value, float) and not math.isfinite(value):
        return str(value)
    return value


def main(argv=None):
    cases = comparison_cases()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--cases", nargs="+", choices=list(cases),
                        default=["long_rectangle", "wide_rectangle", "field_with_hole"])
    parser.add_argument("--strategies", nargs="+", choices=["contour_spiral", "wide_turn", "nepath_raw"],
                        default=["contour_spiral", "wide_turn", "nepath_raw"])
    parser.add_argument("--radius", type=float, default=4.0)
    parser.add_argument("--inset", type=float, default=1.0)
    parser.add_argument("--no-plots", action="store_true")
    arguments = parser.parse_args(argv)
    settings = ComparisonSettings(min_turn_radius_m=arguments.radius, path_inset_m=arguments.inset)
    arguments.output.mkdir(parents=True, exist_ok=True)
    summary = {"settings": asdict(settings), "measurement_notes": MEASUREMENT_NOTES, "cases": []}
    for case_name in arguments.cases:
        def save_report(report):
            (arguments.output / f"{case_name}.json").write_text(
                json.dumps(_json_value(report), indent=2, allow_nan=False), encoding="utf-8")
        report, geometry = compare_case(case_name, cases[case_name], settings, arguments.strategies,
                                        checkpoint=save_report)
        save_report(report)
        if not arguments.no_plots:
            plot_comparison(report, geometry, arguments.output / f"{case_name}.png")
        summary["cases"].append({"case": case_name, "parcel_area_m2": report["parcel_area_m2"],
                                 "work_area_m2": report["work_area_m2"],
                                 "results": [{key: value for key, value in result.items()
                                              if key not in {"paths", "curvature"}}
                                             | {"curvature": {key: value for key, value in result.get("curvature", {}).items()
                                                              if key not in {"traces", "local_turn_density_traces"}}}
                                             for result in report["results"]]})
    (arguments.output / "summary.json").write_text(
        json.dumps(_json_value(summary), indent=2, allow_nan=False), encoding="utf-8")
    return 1 if any(result["status"] == "error" for case in summary["cases"] for result in case["results"]) else 0


if __name__ == "__main__":
    raise SystemExit(main())
