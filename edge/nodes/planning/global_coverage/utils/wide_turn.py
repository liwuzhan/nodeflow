"""Forward-only skip-row coverage with curvature-continuous headland turns.

The first version deliberately accepts only a convex, hole-free work polygon.
Every generated row is visited exactly once.  Headlands are reserved from the
measured extent of the connecting clothoids; no straight-line fallback, radius
reduction or unreported omission of rows is permitted.
"""
from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Dict, List, Optional, Tuple

from shapely import affinity
from shapely.geometry import LineString, Polygon

from .contour_spiral import (
    SolveG2,
    _append_segment,
    _coverage_metrics,
    _sample_g2_connection,
)

Point2D = Tuple[float, float]


@dataclass
class WideTurnResult:
    path: List[Point2D]
    path_zones: List[str]
    row_segments: List[Tuple[Point2D, Point2D]]
    row_order: List[int]
    metadata: Dict


@dataclass
class _Turn:
    points: List[Point2D]
    length: float
    max_curvature: float
    max_curvature_rate: float
    forward_extent: float


def _row_order(row_count: int, min_jump: int, max_jump: int) -> Optional[List[int]]:
    """Find a complete skip-row order with a bounded deterministic search.

    A failed search is only a rejected candidate, never a partial route.  The
    caller expands the permitted jump before declaring the layout infeasible.
    Integer bitsets keep the small ordering search separate from geometry.
    """
    # Interleave the two halves as a guaranteed complete candidate when the
    # field can fit that wider turn. This also bounds the heuristic's failures.
    split = (row_count + 1) // 2
    interleaved = []
    for index in range(split):
        interleaved.append(index)
        if index + split < row_count:
            interleaved.append(index + split)
    if all(min_jump <= abs(a - b) <= max_jump for a, b in zip(interleaved, interleaved[1:])):
        return interleaved
    neighbors = [
        sum(1 << j for j in range(row_count) if min_jump <= abs(i - j) <= max_jump)
        for i in range(row_count)
    ]
    if any(not mask for mask in neighbors):
        return None
    full = (1 << row_count) - 1

    for start in dict.fromkeys((0, row_count - 1, row_count // 2)):
        budget = 1200

        def visit(route: List[int], remaining: int) -> Optional[List[int]]:
            nonlocal budget
            budget -= 1
            if not remaining:
                return route
            if budget <= 0:
                return None
            mask = neighbors[route[-1]] & remaining
            candidates = []
            while mask:
                bit = mask & -mask
                mask -= bit
                candidates.append(bit.bit_length() - 1)
            candidates.sort(key=lambda j: (
                (neighbors[j] & remaining).bit_count(), abs(j - route[-1]), j,
            ))
            for next_row in candidates:
                if budget <= 0:
                    return None
                rest = remaining ^ (1 << next_row)
                if rest and not (neighbors[next_row] & rest):
                    continue
                result = visit(route + [next_row], rest)
                if result is not None:
                    return result
            return None

        result = visit([start], full ^ (1 << start))
        if result is not None:
            return result
    return None


def _long_axis_heading(polygon: Polygon) -> float:
    vertices = list(polygon.minimum_rotated_rectangle.exterior.coords)
    edges = [(math.dist(a, b), a, b) for a, b in zip(vertices, vertices[1:])]
    _, start, end = max(edges, key=lambda item: item[0])
    return math.atan2(end[1] - start[1], end[0] - start[0]) % math.pi


def _positive_finite(name: str, value: float) -> float:
    number = float(value)
    if not math.isfinite(number) or number <= 0.0:
        raise ValueError(f"{name} must be finite and positive")
    return number


def build_wide_turn_coverage(
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
) -> WideTurnResult:
    """Return all-work straight rows joined by forward G2 turns.

    ``work_area`` already includes the caller's boundary setback.  The width
    here adds the centered implement half-width, not another boundary setback.
    ``headland_depth_m`` is measured from that implement-center boundary to the
    row ends.  If omitted it is derived from actual turn geometry.  Coverage is
    reported against the entire supplied work area, including unworked corners
    and parts of the headlands; complete row visitation does not imply 100%
    parcel coverage.  Entry chooses route direction only, and does not invent
    an unchecked drive from outside the field.
    """
    width = _positive_finite("implement_width_m", implement_width_m)
    radius = _positive_finite("min_turn_radius_m", min_turn_radius_m)
    point_spacing = _positive_finite("path_point_spacing_m", path_point_spacing_m)
    if not math.isfinite(float(overlap_ratio)) or not 0.0 <= overlap_ratio < 1.0:
        raise ValueError("overlap_ratio must be in [0, 1)")
    rate_limit = _positive_finite(
        "max_curvature_rate_1pm2",
        0.25 / radius if max_curvature_rate_1pm2 is None else max_curvature_rate_1pm2,
    )
    if (not isinstance(work_area, Polygon) or work_area.is_empty
            or not work_area.is_valid or work_area.interiors):
        raise ValueError("wide_turn requires one valid convex polygon without holes")
    if work_area.convex_hull.difference(work_area).area > max(1e-8, work_area.area * 1e-9):
        raise ValueError("wide_turn currently supports convex work areas only; decompose concave areas first")
    if SolveG2 is None:
        raise RuntimeError("wide_turn requires pyclothoids; install global_coverage/requirements.txt")
    if heading_deg is not None and not math.isfinite(float(heading_deg)):
        raise ValueError("heading_deg must be finite")
    if headland_depth_m is not None:
        headland_depth_m = _positive_finite("headland_depth_m", headland_depth_m)

    heading = _long_axis_heading(work_area) if heading_deg is None else math.radians(heading_deg)
    # Reserve a small discretization margin as sampled clothoids are chords.
    sample_spacing = min(0.1, point_spacing)
    sampling_margin = sample_spacing * sample_spacing / (8.0 * radius) + 1e-5
    center_area = work_area.buffer(-width * 0.5 - sampling_margin, join_style=2)
    if center_area.is_empty:
        raise ValueError("wide_turn work area is narrower than the implement")
    local_center = affinity.rotate(center_area, -math.degrees(heading), origin=(0, 0))
    min_x, min_y, max_x, max_y = local_center.bounds
    span = max_y - min_y
    nominal_spacing = width * (1.0 - overlap_ratio)
    row_count = int(math.ceil(span / nominal_spacing)) + 1
    if row_count < 2 or row_count > 512:
        raise ValueError("wide_turn requires between 2 and 512 rows in one planning block")
    spacing = span / (row_count - 1)
    if spacing <= 1e-8:
        raise ValueError("wide_turn work area cannot accommodate distinct rows")
    # Tiny endpoint inset avoids floating-point line/polygon tangencies after rotation.
    y_values = [min_y + 1e-8 + (span - 2e-8) * i / (row_count - 1) for i in range(row_count)]
    intervals = []
    for y in y_values:
        section = local_center.intersection(LineString([(min_x - 1, y), (max_x + 1, y)]))
        if not isinstance(section, LineString) or section.length <= 1e-7:
            raise ValueError("wide_turn convex shape has insufficient row length near its boundary")
        intervals.append((section.bounds[0], section.bounds[2]))
    # A shared headland gate makes all turns scaled copies, including in a
    # convex trapezoid with sufficiently long rows. Wedge tips may be infeasible.
    common_left = max(pair[0] for pair in intervals)
    common_right = min(pair[1] for pair in intervals)

    turns: Dict[int, _Turn] = {}

    def get_turn(jump: int) -> _Turn:
        if jump not in turns:
            separation = (y_values[-1] - y_values[0]) * jump / (row_count - 1)
            curves = SolveG2(0.0, 0.0, 0.0, 0.0, 0.0, separation, math.pi, 0.0)
            points, length, curvature, curvature_rate = _sample_g2_connection(curves, sample_spacing)
            if not points or not all(math.isfinite(v) for p in points for v in p):
                raise ValueError("wide_turn clothoid solver returned invalid geometry")
            turns[jump] = _Turn(points, length, curvature, curvature_rate, max(p[0] for p in points))
        return turns[jump]

    min_jump = None
    for jump in range(1, row_count):
        turn = get_turn(jump)
        if turn.max_curvature <= 1.0 / radius and turn.max_curvature_rate <= rate_limit:
            min_jump = jump
            break
    if min_jump is None:
        raise ValueError("wide_turn field is too narrow for the requested turn radius and curvature rate")

    chosen_order = None
    reserved_headland = 0.0
    # Larger jumps may rescue the ordering, but their measured turns must still
    # fit two headlands and a positive straight pass. Search never drops a row.
    for max_jump in range(min_jump, row_count):
        candidate_turn = get_turn(max_jump)
        required_headland = candidate_turn.forward_extent + sampling_margin
        depth = required_headland if headland_depth_m is None else headland_depth_m
        if depth + 1e-8 < required_headland:
            break
        if common_right - common_left - 2.0 * depth < max(width, point_spacing * 2):
            break
        order = _row_order(row_count, min_jump, max_jump)
        if order is not None:
            chosen_order = order
            # The route may not use every permitted jump; reserve its real maximum.
            actual_jump = max(abs(a - b) for a, b in zip(order, order[1:]))
            reserved_headland = (get_turn(actual_jump).forward_extent + sampling_margin
                                 if headland_depth_m is None else headland_depth_m)
            break
    if chosen_order is None:
        raise ValueError(
            "wide_turn cannot fit a complete skip-row route with the requested radius, "
            "curvature rate and headland space; use a wider/longer block or another strategy"
        )

    left = common_left + reserved_headland
    right = common_right - reserved_headland
    rows = [((left, y), (right, y)) for y in y_values]
    local_path: List[Point2D] = []
    edge_zones: List[str] = []
    pieces = []
    maximum_curvature = 0.0
    maximum_rate = 0.0
    total_turn_length = 0.0
    for position, row_index in enumerate(chosen_order):
        row = rows[row_index]
        forward = position % 2 == 0
        start, end = row if forward else tuple(reversed(row))
        steps = max(1, int(math.ceil(math.dist(start, end) / point_spacing)))
        points = [(start[0] + (end[0] - start[0]) * i / steps, start[1]) for i in range(steps + 1)]
        _append_segment(local_path, edge_zones, points, "work")
        pieces.append(LineString(points))
        if position == len(chosen_order) - 1:
            continue
        next_row = chosen_order[position + 1]
        jump = next_row - row_index
        turn = get_turn(abs(jump))
        x_sign = 1 if forward else -1
        y_sign = 1 if jump > 0 else -1
        connected = [(end[0] + x_sign * p[0], end[1] + y_sign * p[1]) for p in turn.points]
        # Exact coordinates avoid harmless floating-point mismatch at joins.
        connected[0] = end
        connected[-1] = (end[0], y_values[next_row])
        _append_segment(local_path, edge_zones, connected, "work")
        pieces.append(LineString(connected))
        maximum_curvature = max(maximum_curvature, turn.max_curvature)
        maximum_rate = max(maximum_rate, turn.max_curvature_rate)
        total_turn_length += turn.length

    local_work = affinity.rotate(work_area, -math.degrees(heading), origin=(0, 0))
    full_line = LineString(local_path)
    if not local_center.buffer(1e-7).covers(full_line):
        raise ValueError("wide_turn headland sweep does not fit this convex polygon")
    piece_coverage, _, overlap_area, _ = _coverage_metrics(local_work, pieces, width)
    # The joined path includes tiny join wedges omitted by individually flat-
    # capped pieces. Use that full swept band for the unique coverage result.
    full_sweep = full_line.buffer(width * 0.5, cap_style=2, join_style=1)
    covered_area = full_sweep.intersection(local_work).area
    coverage = covered_area / local_work.area
    unsafe = full_sweep.difference(local_work).area
    overlap_area = max(0.0, overlap_area + piece_coverage * local_work.area - covered_area)
    measured_overlap = overlap_area / local_work.area
    if unsafe > 1e-6:
        raise ValueError(f"wide_turn implement sweep leaves the allowed work area ({unsafe:.6f} m2)")

    cos_a, sin_a = math.cos(heading), math.sin(heading)

    def world(point: Point2D) -> Point2D:
        return (point[0] * cos_a - point[1] * sin_a, point[0] * sin_a + point[1] * cos_a)

    path = [world(point) for point in local_path]
    world_rows = [(world(a), world(b)) for a, b in rows]
    if entry_point is not None:
        if len(entry_point) != 2 or not all(math.isfinite(float(v)) for v in entry_point):
            raise ValueError("entry_point must contain two finite coordinates")
        if math.dist(entry_point, path[-1]) < math.dist(entry_point, path[0]):
            path.reverse()
            chosen_order = list(reversed(chosen_order))

    metadata = {
        "strategy": "wide_turn",
        "wide_turn_mode": "skip_rows_g2_headland",
        "row_count": row_count,
        "row_order": chosen_order,
        "visited_row_count": len(set(chosen_order)),
        "all_rows_visited": len(chosen_order) == row_count and len(set(chosen_order)) == row_count,
        "turn_count": row_count - 1,
        "work_connector_count": row_count - 1,
        "transit_connector_count": 0,
        "row_spacing_m": spacing,
        "effective_overlap_ratio": 1.0 - spacing / width,
        "heading_deg": math.degrees(heading) % 180,
        "headland_depth_m": reserved_headland,
        "straight_row_length_m": right - left,
        "min_skipped_row_jump": min(abs(a - b) for a, b in zip(chosen_order, chosen_order[1:])),
        "max_skipped_row_jump": max(abs(a - b) for a, b in zip(chosen_order, chosen_order[1:])),
        "turn_length_m": total_turn_length,
        "coverage_ratio": coverage,
        "missed_work_area_m2": local_work.area * (1.0 - coverage),
        "unsafe_work_area_m2": unsafe,
        "overlap_area_m2": overlap_area,
        "overlap_ratio": measured_overlap,
        "work_min_turn_radius_m": radius,
        "max_curvature_1pm": maximum_curvature,
        "achieved_min_turn_radius_m": 1.0 / maximum_curvature,
        "connector_max_curvature_rate_1pm2": maximum_rate,
        "work_max_curvature_rate_1pm2": rate_limit,
        "curvature_constrained": maximum_curvature <= 1.0 / radius,
        "coverage_complete": coverage >= 1.0 - 1e-6,
        "coverage_note": "All rows are visited; unworked headland and corner areas remain in the coverage denominator.",
        "sweep_model": "centered_implement_band",
    }
    return WideTurnResult(path, ["work"] * len(path), world_rows, chosen_order, metadata)
