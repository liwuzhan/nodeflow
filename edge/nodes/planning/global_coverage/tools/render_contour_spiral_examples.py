#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import math
import runpy
import sys
from pathlib import Path
from typing import Dict, Tuple

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import numpy as np
from matplotlib.collections import LineCollection
from matplotlib.lines import Line2D
from matplotlib.patches import Polygon as PolygonPatch
from matplotlib.patches import PathPatch
from matplotlib.path import Path as PlotPath
from shapely.geometry import LineString, MultiPolygon, Point, Polygon
from shapely.geometry.polygon import orient


NODE_DIR = Path(__file__).resolve().parents[1]
REPO_ROOT = NODE_DIR.parents[3]
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(NODE_DIR))

from simulation.evaluation import CoverageAccumulator

from utils.contour_spiral import ContourSpiralResult, build_contour_spiral
from utils.models import ParcelData, VehicleConfig
from utils.safe_area import build_safe_area


COLORS = {
    "field": "#f3f5f1",
    "boundary": "#26332d",
    "hole": "#d7dad5",
    "work": "#17854b",
    "transit": "#c6453d",
    "start": "#087ea4",
    "end": "#9d3ba3",
}


def _polygons(geometry):
    if isinstance(geometry, Polygon):
        return [geometry]
    if isinstance(geometry, MultiPolygon):
        return list(geometry.geoms)
    return []


def _draw_area(ax, geometry) -> None:
    for polygon in _polygons(geometry):
        ax.add_patch(PolygonPatch(
            list(polygon.exterior.coords),
            closed=True,
            facecolor=COLORS["field"],
            edgecolor=COLORS["boundary"],
            linewidth=1.4,
            zorder=0,
        ))
        for interior in polygon.interiors:
            ax.add_patch(PolygonPatch(
                list(interior.coords),
                closed=True,
                facecolor=COLORS["hole"],
                edgecolor=COLORS["boundary"],
                linewidth=1.2,
                hatch="///",
                zorder=1,
            ))


def _draw_result(ax, area, result: ContourSpiralResult, title: str) -> None:
    _draw_area(ax, area)
    work_segments = []
    transit_segments = []
    for index, (start, end) in enumerate(zip(result.path, result.path[1:])):
        zones = {result.path_zones[index], result.path_zones[index + 1]}
        target = transit_segments if "transit" in zones else work_segments
        target.append([start, end])

    if work_segments:
        ax.add_collection(LineCollection(
            work_segments,
            colors=COLORS["work"],
            linewidths=1.35,
            zorder=3,
        ))
    if transit_segments:
        ax.add_collection(LineCollection(
            transit_segments,
            colors=COLORS["transit"],
            linewidths=1.4,
            linestyles="dashed",
            zorder=4,
        ))
    if result.path:
        ax.scatter(*result.path[0], s=42, color=COLORS["start"], zorder=5)
        ax.scatter(*result.path[-1], s=42, color=COLORS["end"], zorder=5)

    ax.autoscale()
    ax.set_aspect("equal", adjustable="box")
    ax.margins(0.06)
    ax.grid(True, color="#dfe4df", linewidth=0.6, alpha=0.8)
    ax.set_xlabel("East (m)")
    ax.set_ylabel("North (m)")
    ax.set_title(
        f"{title}\n"
        f"planner estimate {result.coverage_ratio * 100:.2f}% | "
        f"R achieved {result.achieved_min_turn_radius_m:.2f} m | "
        f"work links {result.work_connector_count}, PTO lifts {result.transit_connector_count}",
        fontsize=10,
    )


def _work_runs(result: ContourSpiralResult):
    runs = []
    current = []
    for index, (start, end) in enumerate(zip(result.path, result.path[1:])):
        is_work = (
            result.path_zones[index] == "work"
            and result.path_zones[index + 1] == "work"
        )
        if is_work:
            if not current:
                current = [start]
            current.append(end)
        elif len(current) >= 2:
            runs.append(current)
            current = []
    if len(current) >= 2:
        runs.append(current)
    return runs


def _fill_geometry(ax, geometry, color, alpha, zorder):
    for polygon in _polygons(geometry):
        polygon = orient(polygon)
        paths = []
        for ring in [polygon.exterior, *polygon.interiors]:
            coords = list(ring.coords)
            paths.append(PlotPath(coords, [PlotPath.MOVETO]
                                  + [PlotPath.LINETO]*(len(coords)-2) + [PlotPath.CLOSEPOLY]))
        ax.add_patch(PathPatch(PlotPath.make_compound_path(*paths),
                              facecolor=color, edgecolor="none", alpha=alpha, zorder=zorder))


def _evaluate_result(area, result, implement_width_m):
    evaluation = CoverageAccumulator(area, implement_width_m)
    for coords in _work_runs(result):
        evaluation.break_segment()
        for index, point in enumerate(coords):
            before = coords[max(0, index-1)]
            after = coords[min(len(coords)-1, index+1)]
            theta = math.atan2(after[1]-before[1], after[0]-before[0])
            evaluation.add({"x": point[0], "y": point[1], "theta": theta, "working": True})
    return evaluation


def _draw_coverage(ax, area, result: ContourSpiralResult, implement_width_m: float,
                   evaluation=None) -> None:
    _draw_area(ax, area)
    evaluation = evaluation or _evaluate_result(area, result, implement_width_m)
    shapes = evaluation.geometries()
    measured = evaluation.metrics()
    for key, color, alpha, order in [("covered", "#8fd0aa", .75, 2),
                                     ("missed", "#df6b62", .9, 3),
                                     ("repeated", "#e9b949", .7, 4)]:
        _fill_geometry(ax, shapes[key], color, alpha, order)
    ax.autoscale()
    ax.set_aspect("equal", adjustable="box")
    ax.margins(0.04)
    ax.set_title(
        f"Planned sweep: {measured['coverage_rate_percent']:.2f}% of shown work area\n"
        f"repeat {measured['repeat_rate_percent']:.1f}% | outside {measured['outside_area_m2']:.1f} m2",
        fontsize=10,
    )
    ax.set_xlabel("East (m)")
    ax.set_ylabel("North (m)")


def _draw_curvature(ax, result: ContourSpiralResult, requested_radius_m: float) -> None:
    if len(result.path) < 3:
        return
    station = [0.0]
    for start, end in zip(result.path, result.path[1:]):
        station.append(station[-1] + np.hypot(end[0] - start[0], end[1] - start[1]))
    values = np.full(len(result.path), np.nan)
    for index in range(1, len(result.path) - 1):
        left = max(0, int(np.searchsorted(station, station[index] - 0.4, side="right")) - 1)
        right = min(
            len(result.path) - 1,
            int(np.searchsorted(station, station[index] + 0.4)),
        )
        if left >= index or right <= index:
            continue
        if "transit" in result.path_zones[left:right + 1]:
            continue
        first = result.path[left]
        middle = result.path[index]
        last = result.path[right]
        a = np.hypot(middle[0] - first[0], middle[1] - first[1])
        b = np.hypot(last[0] - middle[0], last[1] - middle[1])
        c = np.hypot(last[0] - first[0], last[1] - first[1])
        if a * b * c <= 1e-9:
            continue
        cross = (
            (middle[0] - first[0]) * (last[1] - first[1])
            - (middle[1] - first[1]) * (last[0] - first[0])
        )
        values[index] = 2.0 * cross / (a * b * c)
    limit = 1.0 / requested_radius_m
    ax.plot(station, values, color="#305f91", linewidth=0.8)
    ax.axhline(limit, color="#c6453d", linestyle="--", linewidth=1.0)
    ax.axhline(-limit, color="#c6453d", linestyle="--", linewidth=1.0)
    observed = np.nanmax(np.abs(values)) if np.any(np.isfinite(values)) else 0.0
    extent = max(limit, observed) * 1.12
    ax.set_ylim(-extent, extent)
    ax.grid(True, color="#dfe4df", linewidth=0.6)
    ax.set_title(
        f"Work-path curvature | limit +/-{limit:.3f} 1/m",
        fontsize=10,
    )
    ax.set_xlabel("Path station (m)")
    ax.set_ylabel("Curvature (1/m)")


def _synthetic_cases() -> Dict[str, Tuple[str, Polygon, float, float, float]]:
    circle_a = Point(22, 18).buffer(4.0, quad_segs=20)
    circle_b = Point(50, 34).buffer(3.5, quad_segs=20)
    return {
        "regular_field": (
            "Regular field - bounded-curvature contour spiral",
            Polygon([(0, 0), (60, 0), (60, 36), (0, 36)]),
            3.0,
            0.1,
            4.0,
        ),
        "concave_field": (
            "Concave field - contour chains follow topology",
            Polygon([
                (0, 0), (62, 0), (62, 18), (42, 18),
                (42, 42), (20, 42), (20, 30), (0, 30),
            ]),
            3.0,
            0.1,
            4.0,
        ),
        "multiple_holes": (
            "Multiple holes - safe work loops and PTO-off relocation",
            Polygon(
                [(0, 0), (72, 0), (72, 50), (0, 50)],
                [
                    list(circle_a.exterior.coords)[:-1],
                    list(circle_b.exterior.coords)[:-1],
                    [(32, 8), (43, 8), (43, 15), (32, 15)],
                ],
            ),
            3.0,
            0.1,
            4.0,
        ),
    }


def _real_case() -> Tuple[str, object, ContourSpiralResult, float, float]:
    data = runpy.run_path(str(REPO_ROOT / "tests/test_global_coverage_standalone.py"))[
        "REAL_TASK_ENU"
    ]
    parcel = ParcelData.from_dict(data["parcel"])
    vehicle = VehicleConfig.from_dict(data["vehicle"])
    area, _ = build_safe_area(parcel.to_dict(), vehicle)
    radius = vehicle.effective_work_min_turn_radius_m
    result = build_contour_spiral(
        area,
        implement_width_m=vehicle.implement_width_m,
        overlap_ratio=vehicle.overlap_ratio,
        path_point_spacing_m=0.5,
        min_turn_radius_m=radius,
        max_curvature_rate_1pm2=vehicle.work_max_curvature_rate_1pm2,
    )
    return "Recorded field with central exclusion", area, result, vehicle.implement_width_m, radius


def render(output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    rendered = []

    for name, (title, area, width, overlap, radius) in _synthetic_cases().items():
        result = build_contour_spiral(
            area,
            implement_width_m=width,
            overlap_ratio=overlap,
            path_point_spacing_m=0.5,
            min_turn_radius_m=radius,
            max_curvature_rate_1pm2=0.08,
        )
        rendered.append((name, title, area, result, width, radius))

    real_title, real_area, real_result, real_width, real_radius = _real_case()
    rendered.append(("recorded_field", real_title, real_area, real_result, real_width, real_radius))

    legend = [
        Line2D([0], [0], color=COLORS["work"], lw=2, label="PTO on / work"),
        Line2D([0], [0], color=COLORS["transit"], lw=2, ls="--", label="PTO off / transit"),
        Line2D([0], [0], marker="o", color="none", markerfacecolor=COLORS["start"], label="Start"),
        Line2D([0], [0], marker="o", color="none", markerfacecolor=COLORS["end"], label="End"),
    ]

    for name, title, area, result, width, radius in rendered:
        evaluation = _evaluate_result(area, result, width)
        fig = plt.figure(figsize=(15, 8), constrained_layout=True)
        grid = fig.add_gridspec(2, 2, width_ratios=(1.25, 1.0))
        path_ax = fig.add_subplot(grid[:, 0])
        coverage_ax = fig.add_subplot(grid[0, 1])
        curvature_ax = fig.add_subplot(grid[1, 1])
        _draw_result(path_ax, area, result, title)
        _draw_coverage(coverage_ax, area, result, width, evaluation)
        _draw_curvature(curvature_ax, result, radius)
        path_ax.legend(handles=legend, loc="upper right", fontsize=8, framealpha=0.95)
        fig.savefig(output_dir / f"{name}.png", dpi=180, facecolor="white")
        measured = {**evaluation.metrics(), "evaluation_source": "planned_path",
                    "denominator": "shown_work_area", "requested_turn_radius_m": radius}
        (output_dir / f"{name}.json").write_text(json.dumps(measured, indent=2), encoding="utf-8")
        plt.close(fig)

    fig, axes = plt.subplots(2, 2, figsize=(15, 11), constrained_layout=True)
    for ax, (_, title, area, result, _, _) in zip(axes.flat, rendered):
        _draw_result(ax, area, result, title)
    fig.legend(handles=legend, loc="lower center", ncol=4, framealpha=0.95)
    fig.savefig(output_dir / "overview.png", dpi=180, facecolor="white")
    plt.close(fig)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=REPO_ROOT / "docs/images/contour_spiral",
    )
    args = parser.parse_args()
    render(args.output_dir.resolve())


if __name__ == "__main__":
    main()
