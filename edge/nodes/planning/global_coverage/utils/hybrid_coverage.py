"""Continuous main passes followed by selected, lift-separated edge passes.

The main wide-turn route is retained verbatim. Cleanup candidates run parallel
to polygon sides, at successively deeper offsets, and are selected by *new*
covered area. Their straight work sweeps are actual oriented rectangles; transit
and pivot motion contributes no coverage. First version: one convex polygon,
with no holes, and a centered implement.
"""
from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Dict, List, Optional, Tuple

from shapely import affinity
from shapely.geometry import LineString, Polygon
from shapely.geometry.polygon import orient

from .wide_turn import build_wide_turn_coverage

Point2D = Tuple[float, float]


@dataclass
class HybridCoverageResult:
    path: List[Point2D]
    path_zones: List[str]
    stages: List[Dict]
    metadata: Dict


@dataclass
class _EdgePass:
    start: Point2D
    end: Point2D
    sweep: Polygon
    edge_index: int
    layer: int
    offset_m: float


def _positive(name, value):
    result = float(value)
    if not math.isfinite(result) or result <= 0:
        raise ValueError(f"{name} must be finite and positive")
    return result


def _straight_sweep(start, end, width, length):
    """Exact union of a fixed-heading rectangle translated along a line."""
    distance = math.dist(start, end)
    ux, uy = (end[0] - start[0]) / distance, (end[1] - start[1]) / distance
    nx, ny = -uy, ux
    return Polygon([
        (p[0] + along * ux + across * nx, p[1] + along * uy + across * ny)
        for p, along, across in (
            (start, -length / 2, -width / 2),
            (end, length / 2, -width / 2),
            (end, length / 2, width / 2),
            (start, -length / 2, width / 2),
        )
    ])


def _edge_candidates(area, width, length, overlap, max_layers):
    """Erode by the *oriented rectangle*, rather than a circular clearance."""
    vertices = list(orient(area, sign=1.0).exterior.coords)
    extent = math.hypot(area.bounds[2] - area.bounds[0], area.bounds[3] - area.bounds[1]) * 2
    spacing = width * (1 - overlap)
    candidates = []
    for edge_index, (a, b) in enumerate(zip(vertices, vertices[1:])):
        distance = math.dist(a, b)
        if distance <= 1e-8:
            continue
        ux, uy = (b[0] - a[0]) / distance, (b[1] - a[1]) / distance
        nx, ny = -uy, ux
        center_area = area
        for along, across in ((-length/2, -width/2), (length/2, -width/2),
                              (length/2, width/2), (-length/2, width/2)):
            corner_x, corner_y = along*ux + across*nx, along*uy + across*ny
            center_area = center_area.intersection(affinity.translate(area, -corner_x, -corner_y))
        if center_area.is_empty:
            continue
        for layer in range(max_layers):
            # Stay infinitesimally inside the exact tangent to avoid empty GEOS
            # intersections for translated/rotated coordinates.
            offset = width / 2 + layer * spacing + 1e-8
            origin = (a[0] + offset*nx, a[1] + offset*ny)
            line = LineString([(origin[0]-extent*ux, origin[1]-extent*uy),
                               (origin[0]+extent*ux, origin[1]+extent*uy)])
            section = center_area.intersection(line)
            if section.is_empty:
                break
            if not isinstance(section, LineString) or section.length <= length:
                continue
            start, end = tuple(section.coords[0]), tuple(section.coords[-1])
            sweep = _straight_sweep(start, end, width, length)
            if sweep.difference(area).area > 1e-6:
                raise ValueError("hybrid boundary rectangle leaves the allowed work area")
            candidates.append(_EdgePass(start, end, sweep, edge_index, layer, offset))
    return candidates


def _densify(start, end, spacing):
    steps = max(1, int(math.ceil(math.dist(start, end) / spacing)))
    return [(start[0] + (end[0]-start[0])*i/steps,
             start[1] + (end[1]-start[1])*i/steps) for i in range(steps + 1)]


def build_hybrid_coverage(
    work_area,
    implement_width_m: float,
    overlap_ratio: float,
    *,
    min_turn_radius_m: float,
    max_curvature_rate_1pm2: Optional[float] = None,
    path_point_spacing_m: float = 0.5,
    heading_deg: Optional[float] = None,
    entry_point: Optional[Point2D] = None,
    headland_depth_m: Optional[float] = None,
    target_coverage_ratio: float = 0.98,
    max_boundary_layers: int = 16,
    implement_length_m: float = 0.2,
    min_new_area_m2: float = 0.05,
) -> HybridCoverageResult:
    """Return main wide turns plus lift-separated residual edge sweeps.

    ``work_area`` is already inset by the caller's safety setback. Coverage
    never counts that excluded strip. Main-stage coverage uses the existing
    centered crossbar band (conservative in implement length); cleanup uses
    exact length-by-width swept rectangles. This is geometric planned coverage,
    not a guarantee of actual tracking or implement timing.

    Cleanup transitions are explicit straight, PTO-off transits. Their corners
    require stop-and-align control with the implement raised. Stage records
    provide exact point ranges and the heading to establish before lowering.
    A caller must not simply track those corners while the implement is down.
    """
    width = _positive("implement_width_m", implement_width_m)
    length = _positive("implement_length_m", implement_length_m)
    spacing = _positive("path_point_spacing_m", path_point_spacing_m)
    gain_floor = _positive("min_new_area_m2", min_new_area_m2)
    target = float(target_coverage_ratio)
    if not math.isfinite(target) or not 0 < target <= 1:
        raise ValueError("target_coverage_ratio must be in (0, 1]")
    if isinstance(max_boundary_layers, bool) or not isinstance(max_boundary_layers, int) or not 0 <= max_boundary_layers <= 256:
        raise ValueError("max_boundary_layers must be an integer in [0, 256]")
    main = build_wide_turn_coverage(
        work_area, width, overlap_ratio,
        min_turn_radius_m=min_turn_radius_m,
        max_curvature_rate_1pm2=max_curvature_rate_1pm2,
        path_point_spacing_m=spacing, heading_deg=heading_deg,
        entry_point=entry_point, headland_depth_m=headland_depth_m,
    )
    path, zones = list(main.path), list(main.path_zones)
    base_sweep = LineString(main.path).buffer(width/2, cap_style=2, join_style=1)
    covered = base_sweep.intersection(work_area)
    base_area = covered.area
    area = work_area.area
    stages = [{
        "id": "main", "type": "wide_turn", "zone": "work",
        "start_index": 0, "end_index": len(path)-1,
        "requires_lift_before": False,
        "work_min_turn_radius_m": float(min_turn_radius_m),
        "new_covered_area_m2": base_area,
    }]
    candidates = _edge_candidates(work_area, width, length, overlap_ratio, max_boundary_layers)
    candidate_count = len(candidates)
    cleanup_area_sum = 0.0
    selected = []
    transit_distance = 0.0
    cleanup_distance = 0.0
    while covered.area / area + 1e-10 < target and candidates:
        residual = work_area.difference(covered)
        # The residual changes only after choosing a pass; evaluate every edge
        # against the same residual and use a deterministic travel tie-break.
        ranked = [(candidate.sweep.intersection(residual).area,
                   -min(math.dist(path[-1], candidate.start), math.dist(path[-1], candidate.end)),
                   -index, candidate) for index, candidate in enumerate(candidates)]
        gain, _, neg_index, candidate = max(ranked, key=lambda item: item[:3])
        if gain <= gain_floor:
            break
        candidates.pop(-neg_index)
        start, end = candidate.start, candidate.end
        if math.dist(path[-1], end) < math.dist(path[-1], start):
            start, end = end, start
        heading = math.atan2(end[1]-start[1], end[0]-start[0])
        connector = _densify(path[-1], start, spacing)
        transit_start = len(path)-1
        connector_length = math.dist(connector[0], start)
        # The cleanup start itself belongs to work. The preceding transit
        # sample remains off, so no gap is swept by evaluation. End-point
        # control uses the stage boundary to stop, align and lower first.
        work_points = _densify(start, end, spacing)
        if connector_length > 1e-6:
            path.extend(connector[1:-1])
            zones.extend(["transit"] * (len(connector)-2))
            # A sub-spacing connector still needs a transit point before work.
            if len(connector) == 2:
                midpoint = ((connector[0][0]+start[0])/2, (connector[0][1]+start[1])/2)
                path.append(midpoint)
                zones.append("transit")
            work_start = len(path)
            path.extend(work_points)
            zones.extend(["work"] * len(work_points))
        else:
            # Stage switching already stops, raises and aligns before the
            # next work pass. A zero-length transit has no tracking direction,
            # so share one point between the two work stages instead.
            work_start = len(path)-1
            path.extend(work_points[1:])
            zones.extend(["work"] * (len(work_points)-1))
        pass_number = len(selected)+1
        if connector_length > 1e-6:
            stages.append({"id": f"cleanup_transit_{pass_number:03d}", "type": "transit", "zone": "transit",
             "start_index": transit_start, "end_index": work_start,
             "requires_lift_before": True, "requires_stop_at_end": True,
             "arrival_heading_rad": heading, "length_m": connector_length})
        stages.append({"id": f"cleanup_work_{pass_number:03d}", "type": "boundary_pass", "zone": "work",
             "start_index": work_start, "end_index": len(path)-1,
             "requires_lift_before": True, "requires_alignment_before": True,
             "work_heading_rad": heading, "edge_index": candidate.edge_index,
             "layer_index": candidate.layer, "offset_m": candidate.offset_m,
             "length_m": math.dist(start, end), "new_covered_area_m2": gain})
        covered = covered.union(candidate.sweep).intersection(work_area)
        cleanup_area_sum += candidate.sweep.intersection(work_area).area
        transit_distance += connector_length
        cleanup_distance += math.dist(start, end)
        selected.append(candidate)

    ratio = covered.area / area
    reached = ratio + 1e-10 >= target
    cleanup_repeat = max(0.0, cleanup_area_sum-(covered.area-base_area))
    overlap_area = main.metadata["overlap_area_m2"] + cleanup_repeat
    transit_count = sum(stage["zone"] == "transit" for stage in stages)
    metadata = dict(main.metadata)
    metadata.update({
        "strategy": "wide_turn_boundary", "main_strategy": "wide_turn",
        "cleanup_strategy": "residual_gain_boundary_straights",
        "main_path_point_count": len(main.path),
        "base_path_point_count": len(main.path),
        "boundary_start_index": len(main.path)-1,
        "main_coverage_ratio": base_area / area,
        "coverage_ratio": ratio, "target_coverage_ratio": target,
        "target_coverage_reached": reached,
        "coverage_complete": ratio >= 1 - 1e-6,
        "covered_work_area_m2": covered.area,
        "missed_work_area_m2": area-covered.area,
        "cleanup_new_area_m2": covered.area-base_area,
        "cleanup_repeat_pass_area_m2": cleanup_repeat,
        "overlap_area_m2": overlap_area,
        "overlap_ratio": overlap_area/area,
        "cleanup_pass_count": len(selected),
        "boundary_layer_count": len({candidate.layer for candidate in selected}),
        "boundary_layers": sorted({candidate.layer for candidate in selected}),
        "deepest_boundary_layer": max((candidate.layer for candidate in selected), default=-1),
        "max_boundary_layers": max_boundary_layers,
        "boundary_candidate_count": candidate_count,
        "transit_connector_count": transit_count,
        "boundary_transit_count": transit_count,
        "cleanup_work_length_m": cleanup_distance,
        "cleanup_transit_length_m": transit_distance,
        "cleanup_stop_reason": ("target_reached" if reached else
                                "no_positive_gain" if candidates else "candidate_layers_exhausted"),
        "unsafe_work_area_m2": base_sweep.difference(work_area).area,
        "coverage_scope": "work_area_after_setback",
        "sweep_model": "main_centered_crossbar_band_plus_exact_boundary_rectangles",
        "cleanup_implement_length_m": length,
        "cleanup_implement_offset_m": 0.0,
        "main_planner": main.metadata,
        "stages": stages,
        "staged_execution": True,
        "execution_stages": stages,
        "cleanup_requires_stop_and_align": bool(selected),
        "coverage_note": "Planned geometric coverage; residuals include corners the selected edge passes cannot reach. Tracking and implement timing need closed-loop validation.",
    })
    return HybridCoverageResult(path, zones, stages, metadata)
