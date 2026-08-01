from __future__ import annotations

import heapq
import math
import warnings
from dataclasses import dataclass
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

from shapely.geometry import LineString, MultiPolygon, Point, Polygon
from shapely.ops import substring, triangulate, unary_union

try:
    from pyclothoids import SolveG2
except ImportError:  # pragma: no cover - exercised by deployment dependency checks
    SolveG2 = None


Point2D = Tuple[float, float]


@dataclass
class ContourSpiralResult:
    path: List[Point2D]
    path_zones: List[str]
    contour_count: int
    layer_count: int
    chain_count: int
    component_count: int
    work_connector_count: int
    transit_connector_count: int
    coverage_ratio: float
    unsafe_work_area_m2: float
    overlap_area_m2: float = 0.0
    overlap_ratio: float = 0.0
    max_curvature_1pm: float = 0.0
    achieved_min_turn_radius_m: float = float("inf")
    connector_max_curvature_rate_1pm2: float = 0.0
    curvature_constrained: bool = False
    terminal_pass_count: int = 0
    contour_spacing_m: float = 0.0
    effective_overlap_ratio: float = 0.0


@dataclass
class _ContourRing:
    line: LineString
    role: str


@dataclass(frozen=True)
class _GateState:
    station: float
    point: Point2D
    heading: float
    curvature: float


@dataclass
class _G2Connection:
    points: List[Point2D]
    length: float
    max_curvature: float
    max_curvature_rate: float
    score: float


@dataclass
class _ChainPlan:
    rings: List[LineString]
    arrivals: List[_GateState]
    departures: List[Optional[_GateState]]
    connections: List[Optional[_G2Connection]]


def _polygon_components(geometry) -> List[Polygon]:
    if geometry is None or geometry.is_empty:
        return []
    if isinstance(geometry, Polygon):
        return [geometry]
    if isinstance(geometry, MultiPolygon):
        return [polygon for polygon in geometry.geoms if not polygon.is_empty]
    if hasattr(geometry, "geoms"):
        polygons: List[Polygon] = []
        for part in geometry.geoms:
            polygons.extend(_polygon_components(part))
        return polygons
    return []


def _ring_lines(geometry) -> List[_ContourRing]:
    rings: List[_ContourRing] = []
    for polygon in _polygon_components(geometry):
        exterior = LineString(polygon.exterior.coords)
        if exterior.length > 1e-6:
            rings.append(_ContourRing(exterior, "exterior"))
        for interior in polygon.interiors:
            ring = LineString(interior.coords)
            if ring.length > 1e-6:
                rings.append(_ContourRing(ring, "interior"))
    return rings


def _is_convex_polygon(polygon: Polygon, tolerance: float = 1e-7) -> bool:
    return (
        not polygon.interiors
        and polygon.convex_hull.area - polygon.area <= max(tolerance, polygon.area * 1e-8)
    )


def _convex_cells(geometry) -> List[Polygon]:
    """Triangulate free space, then greedily merge adjacent convex pieces."""
    cells: List[Polygon] = []
    for component in _polygon_components(geometry):
        if _is_convex_polygon(component):
            cells.append(component)
            continue
        for triangle in triangulate(component):
            clipped = triangle.intersection(component)
            for polygon in _polygon_components(clipped):
                if polygon.area > 1e-6:
                    cells.append(polygon)

    while True:
        best = None
        for first_index, first in enumerate(cells):
            for second_index in range(first_index + 1, len(cells)):
                second = cells[second_index]
                shared_length = first.boundary.intersection(second.boundary).length
                if shared_length <= 1e-6:
                    continue
                merged = first.union(second)
                if not isinstance(merged, Polygon) or not _is_convex_polygon(merged):
                    continue
                if best is None or shared_length > best[0]:
                    best = (shared_length, first_index, second_index, merged)
        if best is None:
            break
        _, first_index, second_index, merged = best
        cells = [
            cell
            for index, cell in enumerate(cells)
            if index not in {first_index, second_index}
        ]
        cells.append(merged)
    return cells


def _match_contour_chains(
    layers: Sequence[Sequence[_ContourRing]],
    spacing_m: float,
) -> List[List[_ContourRing]]:
    chains: List[List[_ContourRing]] = []
    active: List[int] = []
    match_limit = spacing_m * 1.6 + 1e-6

    for layer in layers:
        if not layer:
            active = []
            continue

        pairs = []
        for chain_index in active:
            previous = chains[chain_index][-1]
            for ring_index, ring in enumerate(layer):
                if previous.role != ring.role:
                    continue
                distance = previous.line.distance(ring.line)
                if distance <= match_limit:
                    pairs.append((distance, chain_index, ring_index))
        pairs.sort(key=lambda item: item[0])

        matched_chains = set()
        matched_rings = set()
        next_active: List[int] = []
        for _, chain_index, ring_index in pairs:
            if chain_index in matched_chains or ring_index in matched_rings:
                continue
            chains[chain_index].append(layer[ring_index])
            matched_chains.add(chain_index)
            matched_rings.add(ring_index)
            next_active.append(chain_index)

        for ring_index, ring in enumerate(layer):
            if ring_index in matched_rings:
                continue
            chains.append([ring])
            next_active.append(len(chains) - 1)
        active = next_active

    return chains


def _signed_ring_area(coords: Sequence[Point2D]) -> float:
    area = 0.0
    for current, following in zip(coords, coords[1:]):
        area += current[0] * following[1] - following[0] * current[1]
    return area * 0.5


def _clockwise_ring(ring: LineString) -> LineString:
    coords = [(float(x), float(y)) for x, y in ring.coords]
    if _signed_ring_area(coords) > 0.0:
        coords.reverse()
    return LineString(coords)


def _append_coords(target: List[Point2D], coords: Sequence[Point2D]) -> None:
    for x, y in coords:
        point = (float(x), float(y))
        if not target or math.dist(target[-1], point) > 1e-9:
            target.append(point)


def _fillet_ring(
    ring: LineString,
    allowed_area,
    min_turn_radius_m: float,
) -> Optional[LineString]:
    """Replace significant polygon vertices with tangent circular fillets."""
    oriented = _oriented_ring(ring)
    vertices = [(float(x), float(y)) for x, y in list(oriented.coords)[:-1]]
    if len(vertices) < 3:
        return None

    radius = float(min_turn_radius_m)
    corner_paths: List[List[Point2D]] = []
    minimum_turn = math.radians(8.0)
    for index, current in enumerate(vertices):
        previous = vertices[index - 1]
        following = vertices[(index + 1) % len(vertices)]
        incoming_length = math.dist(previous, current)
        outgoing_length = math.dist(current, following)
        if incoming_length <= 1e-7 or outgoing_length <= 1e-7:
            corner_paths.append([current])
            continue

        incoming = (
            (current[0] - previous[0]) / incoming_length,
            (current[1] - previous[1]) / incoming_length,
        )
        outgoing = (
            (following[0] - current[0]) / outgoing_length,
            (following[1] - current[1]) / outgoing_length,
        )
        turn = math.atan2(
            incoming[0] * outgoing[1] - incoming[1] * outgoing[0],
            incoming[0] * outgoing[0] + incoming[1] * outgoing[1],
        )
        turn_magnitude = abs(turn)
        if turn_magnitude < minimum_turn or turn_magnitude > math.pi - 1e-3:
            corner_paths.append([current])
            continue

        tangent_cut = radius * math.tan(turn_magnitude * 0.5)
        if tangent_cut > min(incoming_length, outgoing_length) * 0.48:
            return None

        start = (
            current[0] - incoming[0] * tangent_cut,
            current[1] - incoming[1] * tangent_cut,
        )
        end = (
            current[0] + outgoing[0] * tangent_cut,
            current[1] + outgoing[1] * tangent_cut,
        )
        side = 1.0 if turn > 0.0 else -1.0
        center = (
            start[0] + side * -incoming[1] * radius,
            start[1] + side * incoming[0] * radius,
        )
        start_angle = math.atan2(start[1] - center[1], start[0] - center[0])
        steps = max(3, int(math.ceil(turn_magnitude / math.radians(5.0))))
        arc = []
        for step in range(steps + 1):
            angle = start_angle + turn * step / steps
            arc.append((
                center[0] + radius * math.cos(angle),
                center[1] + radius * math.sin(angle),
            ))
        arc[0] = start
        arc[-1] = end
        corner_paths.append(arc)

    coords: List[Point2D] = []
    for corner_path in corner_paths:
        _append_coords(coords, corner_path)
    if len(coords) < 3:
        return None
    _append_coords(coords, [coords[0]])
    filleted = LineString(coords)
    if not allowed_area.buffer(1e-6).covers(filleted):
        return None
    return filleted


def _oriented_ring(ring: LineString) -> LineString:
    return _clockwise_ring(ring)


def _gate_candidates(
    ring: LineString,
    min_turn_radius_m: float,
    max_count: int = 20,
) -> List[_GateState]:
    """Choose gate states on locally straight portions of a closed contour."""
    line = _oriented_ring(ring)
    coords = list(line.coords)
    length = line.length
    if length <= 1e-6:
        return []

    minimum_segment = max(0.35, min(1.5, min_turn_radius_m * 0.3))
    proposals: List[Tuple[float, float, _GateState]] = []
    station = 0.0
    for start, end in zip(coords, coords[1:]):
        segment_length = math.dist(start, end)
        if segment_length >= minimum_segment:
            samples = 1
            if segment_length >= max(8.0, min_turn_radius_m * 2.5):
                samples = 3
            for sample_index in range(samples):
                fraction = (sample_index + 1) / (samples + 1)
                point = (
                    float(start[0] + (end[0] - start[0]) * fraction),
                    float(start[1] + (end[1] - start[1]) * fraction),
                )
                heading = math.atan2(end[1] - start[1], end[0] - start[0])
                gate = _GateState(
                    station=station + segment_length * fraction,
                    point=point,
                    heading=heading,
                    curvature=0.0,
                )
                proposals.append((-segment_length, gate.station, gate))
        station += segment_length

    if not proposals:
        vertices = [(float(x), float(y)) for x, y in coords[:-1]]
        samples = min(max_count, len(vertices))
        indices = sorted({int(index * len(vertices) / samples) for index in range(samples)})
        segment_stations = [0.0]
        for start, end in zip(vertices, [*vertices[1:], vertices[0]]):
            segment_stations.append(segment_stations[-1] + math.dist(start, end))
        for index in indices:
            first = vertices[index - 1]
            middle = vertices[index]
            last = vertices[(index + 1) % len(vertices)]
            station = segment_stations[index]
            heading = math.atan2(last[1] - first[1], last[0] - first[0])
            denominator = (
                math.dist(first, middle)
                * math.dist(middle, last)
                * math.dist(last, first)
            )
            cross = (
                (middle[0] - first[0]) * (last[1] - first[1])
                - (middle[1] - first[1]) * (last[0] - first[0])
            )
            curvature = 2.0 * cross / denominator if denominator > 1e-10 else 0.0
            proposals.append((
                0.0,
                station,
                _GateState(station, middle, heading, curvature),
            ))

    proposals.sort(key=lambda item: (item[0], item[1]))
    selected = sorted(proposals[:max_count], key=lambda item: item[1])
    return [item[2] for item in selected]


def _sample_g2_connection(curves, spacing_m: float) -> Tuple[List[Point2D], float, float, float]:
    points: List[Point2D] = []
    total_length = 0.0
    max_curvature = 0.0
    max_curvature_rate = 0.0
    for curve in curves:
        curve_length = float(curve.length)
        if curve_length <= 1e-9:
            continue
        sample_count = max(2, int(math.ceil(curve_length / spacing_m)) + 1)
        sampled_x, sampled_y = curve.SampleXY(sample_count)
        sampled = [(float(x), float(y)) for x, y in zip(sampled_x, sampled_y)]
        if points and math.dist(points[-1], sampled[0]) <= 1e-7:
            sampled = sampled[1:]
        points.extend(sampled)
        total_length += curve_length
        max_curvature = max(
            max_curvature,
            abs(float(curve.KappaStart)),
            abs(float(curve.KappaEnd)),
        )
        max_curvature_rate = max(max_curvature_rate, abs(float(curve.dk)))
    return points, total_length, max_curvature, max_curvature_rate


def _solve_work_connection(
    start: _GateState,
    end: _GateState,
    center_area,
    work_area,
    implement_width_m: float,
    min_turn_radius_m: float,
    max_curvature_rate_1pm2: float,
    spacing_m: float,
) -> Optional[_G2Connection]:
    if SolveG2 is None:
        raise RuntimeError(
            "contour_spiral requires pyclothoids; install global_coverage/requirements.txt"
        )

    try:
        curves = SolveG2(
            start.point[0],
            start.point[1],
            start.heading,
            start.curvature,
            end.point[0],
            end.point[1],
            end.heading,
            end.curvature,
        )
    except (RuntimeError, ValueError):
        return None

    sample_spacing = min(0.2, max(0.05, spacing_m * 0.2))
    points, length, max_curvature, max_curvature_rate = _sample_g2_connection(
        curves,
        sample_spacing,
    )
    if len(points) < 2 or not math.isfinite(length):
        return None

    curvature_limit = 1.0 / min_turn_radius_m
    if max_curvature > curvature_limit * 1.001:
        return None
    if max_curvature_rate > max_curvature_rate_1pm2 * 1.001:
        return None

    max_length = max(18.0, min_turn_radius_m * 10.0 + spacing_m * 4.0)
    if length > max_length:
        return None

    connector = LineString(points)
    if not center_area.buffer(1e-6).covers(connector):
        return None
    sweep = connector.buffer(
        implement_width_m * 0.5,
        cap_style=2,
        join_style=1,
    )
    if sweep.difference(work_area.buffer(1e-6)).area > 0.01:
        return None

    curvature_ratio = max_curvature / curvature_limit
    rate_ratio = max_curvature_rate / max_curvature_rate_1pm2
    score = (
        length
        + min_turn_radius_m * 8.0 * curvature_ratio * curvature_ratio
        + min_turn_radius_m * 2.0 * rate_ratio * rate_ratio
    )
    return _G2Connection(
        points=points,
        length=length,
        max_curvature=max_curvature,
        max_curvature_rate=max_curvature_rate,
        score=score,
    )


def _transition_options(
    source_ring: LineString,
    target_ring: LineString,
    source_candidates: Sequence[_GateState],
    target_candidates: Sequence[_GateState],
    center_area,
    work_area,
    implement_width_m: float,
    min_turn_radius_m: float,
    max_curvature_rate_1pm2: float,
    spacing_m: float,
) -> Dict[Tuple[int, int], _G2Connection]:
    options: Dict[Tuple[int, int], _G2Connection] = {}
    for source_index, source in enumerate(source_candidates):
        for target_index, target in enumerate(target_candidates):
            connection = _solve_work_connection(
                source,
                target,
                center_area,
                work_area,
                implement_width_m,
                min_turn_radius_m,
                max_curvature_rate_1pm2,
                spacing_m,
            )
            if connection is not None:
                options[(source_index, target_index)] = connection
    return options


def _optimize_chain_group(
    rings: Sequence[LineString],
    candidates: Sequence[Sequence[_GateState]],
    transition_options: Sequence[Dict[Tuple[int, int], _G2Connection]],
    entry_point: Optional[Point2D],
) -> _ChainPlan:
    first_costs = {}
    for index, gate in enumerate(candidates[0]):
        first_costs[index] = (
            math.dist(entry_point, gate.point) * 0.25 if entry_point is not None else 0.0
        )

    costs = first_costs
    parents: List[Dict[int, Tuple[int, int, _G2Connection]]] = [dict()]
    overlap_weight = 0.15
    for layer_index, options in enumerate(transition_options):
        next_costs: Dict[int, float] = {}
        next_parents: Dict[int, Tuple[int, int, _G2Connection]] = {}
        ring_length = rings[layer_index].length
        for (source_index, target_index), connection in options.items():
            source_gate = candidates[layer_index][source_index]
            for arrival_index, arrival_cost in costs.items():
                arrival_gate = candidates[layer_index][arrival_index]
                repeated_distance = (source_gate.station - arrival_gate.station) % ring_length
                candidate_cost = arrival_cost + connection.score + overlap_weight * repeated_distance
                if candidate_cost < next_costs.get(target_index, float("inf")):
                    next_costs[target_index] = candidate_cost
                    next_parents[target_index] = (
                        arrival_index,
                        source_index,
                        connection,
                    )
        if not next_costs:
            raise ValueError("no curvature-constrained transition between contour layers")
        costs = next_costs
        parents.append(next_parents)

    final_index = min(costs, key=costs.get)
    arrivals: List[Optional[_GateState]] = [None] * len(rings)
    departures: List[Optional[_GateState]] = [None] * len(rings)
    connections: List[Optional[_G2Connection]] = [None] * max(0, len(rings) - 1)
    current_index = final_index
    arrivals[-1] = candidates[-1][current_index]
    for layer_index in range(len(rings) - 1, 0, -1):
        previous_index, source_index, connection = parents[layer_index][current_index]
        arrivals[layer_index - 1] = candidates[layer_index - 1][previous_index]
        departures[layer_index - 1] = candidates[layer_index - 1][source_index]
        connections[layer_index - 1] = connection
        current_index = previous_index

    return _ChainPlan(
        rings=list(rings),
        arrivals=[gate for gate in arrivals if gate is not None],
        departures=departures,
        connections=connections,
    )


def _forward_ring_path(
    ring: LineString,
    start_station: float,
    end_station: float,
    full_loop: bool,
) -> List[Point2D]:
    line = _oriented_ring(ring)
    length = line.length
    start = start_station % length
    travel = (end_station - start_station) % length
    if full_loop and travel <= 1e-8:
        vertices = [(float(x), float(y)) for x, y in list(line.coords)[:-1]]
        target = line.interpolate(start)
        nearest = min(
            range(len(vertices)),
            key=lambda index: math.dist(vertices[index], (target.x, target.y)),
        )
        if math.dist(vertices[nearest], (target.x, target.y)) <= 1e-5:
            rotated = vertices[nearest:] + vertices[:nearest]
            rotated.append(rotated[0])
            return rotated
    if full_loop:
        travel += length
    if travel <= 1e-8:
        point = line.interpolate(start)
        return [(float(point.x), float(point.y))]

    coords: List[Point2D] = []
    cursor = start
    remaining = travel
    while remaining > 1e-8:
        part_length = min(remaining, length - cursor)
        if part_length > 1e-8:
            part = substring(line, cursor, cursor + part_length)
            _append_coords(coords, list(part.coords))
        remaining -= part_length
        cursor = 0.0
    return coords


def _discrete_max_curvature(coords: Sequence[Point2D]) -> float:
    maximum = 0.0
    for first, middle, last in zip(coords, coords[1:], coords[2:]):
        a = math.dist(first, middle)
        b = math.dist(middle, last)
        c = math.dist(last, first)
        denominator = a * b * c
        if denominator <= 1e-10:
            continue
        cross = (
            (middle[0] - first[0]) * (last[1] - first[1])
            - (middle[1] - first[1]) * (last[0] - first[0])
        )
        maximum = max(maximum, abs(2.0 * cross / denominator))
    return maximum


def _max_heading_change(coords: Sequence[Point2D]) -> float:
    vertices = list(coords)
    if len(vertices) >= 2 and math.dist(vertices[0], vertices[-1]) <= 1e-8:
        vertices = vertices[:-1]
    maximum = 0.0
    for index, current in enumerate(vertices):
        previous = vertices[index - 1]
        following = vertices[(index + 1) % len(vertices)]
        incoming = math.atan2(current[1] - previous[1], current[0] - previous[0])
        outgoing = math.atan2(following[1] - current[1], following[0] - current[0])
        change = abs(math.atan2(
            math.sin(outgoing - incoming),
            math.cos(outgoing - incoming),
        ))
        maximum = max(maximum, change)
    return maximum


def _terminal_pass_candidates(
    cells: Sequence[Polygon],
    center_area,
    work_area,
    implement_width_m: float,
    spacing_m: float,
    headland_margin_m: float,
) -> List[LineString]:
    candidates: List[LineString] = []
    for cell in cells:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", RuntimeWarning)
            rectangle = cell.minimum_rotated_rectangle
        rectangle_coords = list(rectangle.exterior.coords)
        edges = [
            (
                math.dist(start, end),
                (end[0] - start[0], end[1] - start[1]),
            )
            for start, end in zip(rectangle_coords, rectangle_coords[1:])
        ]
        _, direction_vector = max(edges, key=lambda item: item[0])
        direction_length = math.hypot(*direction_vector)
        if direction_length <= 1e-8:
            continue
        direction = (
            direction_vector[0] / direction_length,
            direction_vector[1] / direction_length,
        )
        normal = (-direction[1], direction[0])
        cell_coords = list(cell.exterior.coords)
        projections = [x * normal[0] + y * normal[1] for x, y in cell_coords]
        minimum = min(projections)
        maximum = max(projections)
        cross_span = maximum - minimum
        if cross_span <= 1e-6:
            continue

        count = max(1, int(math.ceil(cross_span / spacing_m)))
        actual_spacing = cross_span / count
        along = [x * direction[0] + y * direction[1] for x, y in cell_coords]
        along_min = min(along) - implement_width_m
        along_max = max(along) + implement_width_m
        for index in range(count + 1):
            offset = minimum + index * actual_spacing
            start = (
                direction[0] * along_min + normal[0] * offset,
                direction[1] * along_min + normal[1] * offset,
            )
            end = (
                direction[0] * along_max + normal[0] * offset,
                direction[1] * along_max + normal[1] * offset,
            )
            clipped = LineString([start, end]).intersection(work_area.buffer(-1e-6))
            geometries = list(clipped.geoms) if hasattr(clipped, "geoms") else [clipped]
            for geometry in geometries:
                if isinstance(geometry, LineString) and geometry.length >= implement_width_m:
                    for line in _lateral_safe_segments(
                        geometry,
                        work_area,
                        implement_width_m * 0.5,
                    ):
                        candidates.append(line)
                        margin = min(
                            headland_margin_m,
                            max(0.0, (line.length - implement_width_m) * 0.25),
                        )
                        if margin > 1e-6 and line.length > margin * 2.0 + implement_width_m:
                            trimmed = substring(line, margin, line.length - margin)
                            if isinstance(trimmed, LineString):
                                candidates.append(trimmed)
    return candidates


def _lateral_safe_segments(
    line: LineString,
    work_area,
    half_width_m: float,
) -> List[LineString]:
    """Keep straight-line stations whose lateral implement bar stays in bounds."""
    if line.length <= 1e-8:
        return []
    start = line.coords[0]
    end = line.coords[-1]
    direction = (
        (end[0] - start[0]) / line.length,
        (end[1] - start[1]) / line.length,
    )
    normal = (-direction[1], direction[0])
    step = min(0.2, max(0.05, half_width_m * 0.15))
    sample_count = max(2, int(math.ceil(line.length / step)) + 1)
    stations = [line.length * index / (sample_count - 1) for index in range(sample_count)]
    safe = []
    expanded = work_area.buffer(1e-7)
    for station in stations:
        point = line.interpolate(station)
        cross_section = LineString([
            (
                point.x - normal[0] * half_width_m,
                point.y - normal[1] * half_width_m,
            ),
            (
                point.x + normal[0] * half_width_m,
                point.y + normal[1] * half_width_m,
            ),
        ])
        safe.append(expanded.covers(cross_section))

    result = []
    run_start = None
    for index, is_safe in enumerate([*safe, False]):
        if is_safe and run_start is None:
            run_start = index
        elif not is_safe and run_start is not None:
            run_end = index - 1
            if run_end > run_start:
                segment = substring(line, stations[run_start], stations[run_end])
                if isinstance(segment, LineString) and segment.length > half_width_m * 2.0:
                    result.append(segment)
            run_start = None
    return result


def _append_terminal_passes(
    raw_path: List[Point2D],
    edge_zones: List[str],
    work_lines: List[LineString],
    cells: Sequence[Polygon],
    center_area,
    work_area,
    implement_width_m: float,
    spacing_m: float,
    min_turn_radius_m: float,
    max_curvature_rate_1pm2: float,
    target_coverage_ratio: float = 0.97,
) -> Tuple[int, int, int, float, float]:
    if not raw_path:
        return 0, 0, 0, 0.0, 0.0

    candidates = _terminal_pass_candidates(
        cells,
        center_area,
        work_area,
        implement_width_m,
        max(implement_width_m * 0.5, spacing_m),
        min_turn_radius_m * 2.0,
    )
    half_width = implement_width_m * 0.5
    swept = unary_union([
        line.buffer(half_width, cap_style=2, join_style=1)
        for line in work_lines
    ])
    uncovered = work_area.difference(swept)
    terminal_count = 0
    work_connection_count = 0
    transit_count = 0
    max_connection_curvature = 0.0
    max_connection_rate = 0.0

    while (
        candidates
        and uncovered.area / work_area.area > 1.0 - target_coverage_ratio
        and terminal_count < 120
    ):
        current_heading = math.atan2(
            raw_path[-1][1] - raw_path[-2][1],
            raw_path[-1][0] - raw_path[-2][0],
        )
        current = _GateState(0.0, raw_path[-1], current_heading, 0.0)
        choices = []
        for candidate_index, candidate in enumerate(candidates):
            gain = candidate.buffer(
                half_width,
                cap_style=2,
                join_style=1,
            ).intersection(uncovered).area
            coords = [(float(x), float(y)) for x, y in candidate.coords]
            for reverse in (False, True):
                oriented = list(reversed(coords)) if reverse else coords
                heading = math.atan2(
                    oriented[1][1] - oriented[0][1],
                    oriented[1][0] - oriented[0][0],
                )
                target = _GateState(0.0, oriented[0], heading, 0.0)
                connection = _solve_work_connection(
                    current,
                    target,
                    center_area,
                    work_area,
                    implement_width_m,
                    min_turn_radius_m,
                    max_curvature_rate_1pm2,
                    spacing_m,
                )
                pto_penalty = 0.0 if connection is not None else work_area.area * 2.0
                distance = connection.length if connection is not None else math.dist(
                    current.point,
                    target.point,
                )
                choices.append((
                    pto_penalty + distance - gain * 5.0,
                    candidate_index,
                    oriented,
                    connection,
                ))
        if not choices:
            break

        _, candidate_index, oriented, connection = min(choices, key=lambda item: item[0])
        candidates.pop(candidate_index)
        if connection is not None:
            _append_segment(raw_path, edge_zones, connection.points, "work")
            work_lines.append(LineString(connection.points))
            work_connection_count += 1
            max_connection_curvature = max(
                max_connection_curvature,
                connection.max_curvature,
            )
            max_connection_rate = max(
                max_connection_rate,
                connection.max_curvature_rate,
            )
        else:
            transit = _shortest_connector(
                work_area,
                raw_path[-1],
                oriented[0],
                max(1e-7, implement_width_m * 1e-7),
            )
            if transit is None:
                continue
            _append_segment(raw_path, edge_zones, transit, "transit")
            transit_count += 1

        _append_segment(raw_path, edge_zones, oriented, "work")
        work_line = LineString(oriented)
        work_lines.append(work_line)
        swept = unary_union([
            swept,
        work_line.buffer(half_width, cap_style=2, join_style=1),
        ])
        if connection is not None:
            swept = unary_union([
                swept,
                LineString(connection.points).buffer(
                    half_width,
                    cap_style=2,
                    join_style=1,
                ),
            ])
        uncovered = work_area.difference(swept)
        terminal_count += 1

    return (
        terminal_count,
        work_connection_count,
        transit_count,
        max_connection_curvature,
        max_connection_rate,
    )


def _covers_segment(polygon: Polygon, start: Point2D, end: Point2D, tolerance: float) -> bool:
    segment = LineString([start, end])
    return polygon.buffer(tolerance).covers(segment)


def _containing_component(
    free_space,
    start: Point2D,
    end: Point2D,
    tolerance: float,
) -> Optional[Polygon]:
    start_point = Point(start)
    end_point = Point(end)
    for polygon in _polygon_components(free_space):
        expanded = polygon.buffer(tolerance)
        if expanded.covers(start_point) and expanded.covers(end_point):
            return polygon
    return None


def _visibility_vertices(polygon: Polygon, tolerance: float) -> List[Point2D]:
    simplified = polygon.simplify(max(0.01, tolerance * 10.0), preserve_topology=True)
    vertices = list(simplified.exterior.coords)[:-1]
    for interior in simplified.interiors:
        vertices.extend(list(interior.coords)[:-1])

    result: List[Point2D] = []
    seen = set()
    for x, y in vertices:
        key = (round(float(x), 8), round(float(y), 8))
        if key not in seen:
            seen.add(key)
            result.append((float(x), float(y)))
    return result


def _shortest_connector(
    free_space,
    start: Point2D,
    end: Point2D,
    tolerance: float,
) -> Optional[List[Point2D]]:
    if math.dist(start, end) <= tolerance:
        return [start]

    component = _containing_component(free_space, start, end, tolerance)
    if component is None:
        return None
    if _covers_segment(component, start, end, tolerance):
        return [start, end]

    nodes = [start, end, *_visibility_vertices(component, tolerance)]
    graph: List[List[Tuple[int, float]]] = [[] for _ in nodes]
    for source in range(len(nodes)):
        for target in range(source + 1, len(nodes)):
            if not _covers_segment(component, nodes[source], nodes[target], tolerance):
                continue
            distance = math.dist(nodes[source], nodes[target])
            graph[source].append((target, distance))
            graph[target].append((source, distance))

    distances = [float("inf")] * len(nodes)
    previous: List[Optional[int]] = [None] * len(nodes)
    distances[0] = 0.0
    queue = [(0.0, 0)]

    while queue:
        distance, node = heapq.heappop(queue)
        if distance != distances[node]:
            continue
        if node == 1:
            break
        for neighbor, edge_length in graph[node]:
            candidate = distance + edge_length
            if candidate < distances[neighbor]:
                distances[neighbor] = candidate
                previous[neighbor] = node
                heapq.heappush(queue, (candidate, neighbor))

    if not math.isfinite(distances[1]):
        return None

    indices = []
    node: Optional[int] = 1
    while node is not None:
        indices.append(node)
        node = previous[node]
    indices.reverse()
    return [nodes[index] for index in indices]


def _append_segment(
    path: List[Point2D],
    edge_zones: List[str],
    coords: Sequence[Point2D],
    zone: str,
) -> None:
    if not coords:
        return
    start_index = 0
    if not path:
        path.append(coords[0])
        start_index = 1
    elif math.dist(path[-1], coords[0]) <= 1e-7:
        start_index = 1
    else:
        raise ValueError("path segment is not continuous")

    for point in coords[start_index:]:
        point = (float(point[0]), float(point[1]))
        if math.dist(path[-1], point) <= 1e-9:
            continue
        path.append(point)
        edge_zones.append(zone)


def _densify_labeled_path(
    path: Sequence[Point2D],
    edge_zones: Sequence[str],
    spacing_m: float,
) -> Tuple[List[Point2D], List[str]]:
    if not path:
        return [], []
    if len(edge_zones) != len(path) - 1:
        raise ValueError("edge zone count must match path segments")

    spacing = max(0.05, float(spacing_m))
    dense_path = [path[0]]
    dense_edge_zones: List[str] = []
    for index, zone in enumerate(edge_zones):
        start = path[index]
        end = path[index + 1]
        length = math.dist(start, end)
        steps = max(1, int(math.ceil(length / spacing)))
        for step in range(1, steps + 1):
            fraction = step / steps
            dense_path.append((
                start[0] + (end[0] - start[0]) * fraction,
                start[1] + (end[1] - start[1]) * fraction,
            ))
            dense_edge_zones.append(zone)

    point_zones = ["work"] * len(dense_path)
    for index in range(len(dense_path)):
        adjacent = []
        if index > 0:
            adjacent.append(dense_edge_zones[index - 1])
        if index < len(dense_edge_zones):
            adjacent.append(dense_edge_zones[index])
        if "transit" in adjacent:
            point_zones[index] = "transit"
    point_zones[0] = "transit"
    point_zones[-1] = "transit"
    return dense_path, point_zones


def _coverage_metrics(
    work_area,
    work_lines: Iterable[LineString],
    implement_width_m: float,
) -> Tuple[float, float, float, float]:
    half_width = max(0.0, implement_width_m * 0.5)
    sweeps = [
        line.buffer(half_width, cap_style=2, join_style=1)
        for line in work_lines
        if line and not line.is_empty
    ]
    if not sweeps or work_area.is_empty:
        return 0.0, 0.0, 0.0, 0.0

    swept_area = unary_union(sweeps)
    covered_area = swept_area.intersection(work_area).area
    coverage_ratio = covered_area / work_area.area if work_area.area > 0 else 0.0
    unsafe_area = swept_area.difference(work_area.buffer(1e-7)).area
    clipped_area_sum = sum(sweep.intersection(work_area).area for sweep in sweeps)
    overlap_area = max(0.0, clipped_area_sum - covered_area)
    overlap_ratio = overlap_area / work_area.area if work_area.area > 0 else 0.0
    return coverage_ratio, unsafe_area, overlap_area, overlap_ratio


def build_contour_spiral(
    work_area,
    implement_width_m: float,
    overlap_ratio: float,
    path_point_spacing_m: float = 0.5,
    entry_point: Optional[Point2D] = None,
    min_turn_radius_m: Optional[float] = None,
    max_curvature_rate_1pm2: Optional[float] = None,
    max_layers: int = 10000,
) -> ContourSpiralResult:
    """Build bounded-curvature contour spirals over polygonal free space.

    Successive contours are rounded to the engaged-work turn radius. A full
    loop is driven on every contour, then adjacent layers are joined with a G2
    three-clothoid connection. Gate locations are optimized across each chain;
    additional contour travel is a soft overlap cost, while an infeasible work
    connection forces an explicit PTO-off transit between chain groups.
    """
    if work_area is None or work_area.is_empty:
        return ContourSpiralResult([], [], 0, 0, 0, 0, 0, 0, 0.0, 0.0)
    if implement_width_m <= 0:
        raise ValueError("implement_width_m must be positive")
    if not 0.0 <= overlap_ratio < 1.0:
        raise ValueError("overlap_ratio must be in [0, 1)")

    radius = (
        float(min_turn_radius_m)
        if min_turn_radius_m is not None
        else max(1.0, implement_width_m * 0.75)
    )
    if radius <= 0.0:
        raise ValueError("min_turn_radius_m must be positive")
    geometry_radius = radius * 1.25
    curvature_limit = 1.0 / radius
    curvature_rate_limit = (
        float(max_curvature_rate_1pm2)
        if max_curvature_rate_1pm2 is not None
        else 0.25 / radius
    )
    if curvature_rate_limit <= 0.0:
        raise ValueError("max_curvature_rate_1pm2 must be positive")
    if SolveG2 is None:
        raise RuntimeError(
            "contour_spiral requires pyclothoids; install global_coverage/requirements.txt"
        )

    nominal_spacing = implement_width_m * (1.0 - overlap_ratio)
    # Rotary tillage favors continuous engaged turns over nominal row spacing.
    # Extra overlap creates more feasible contour layers and reduces PTO lifts.
    spacing = min(nominal_spacing, implement_width_m * 0.5)
    half_width = implement_width_m * 0.5
    center_area = work_area.buffer(-half_width, join_style=2)
    if center_area.is_empty:
        return ContourSpiralResult([], [], 0, 0, 0, 0, 0, 0, 0.0, 0.0)

    planning_cells = _convex_cells(center_area)
    center_components = _polygon_components(center_area)
    layers: List[List[_ContourRing]] = []
    for layer_index in range(max_layers):
        rings = []
        offset = layer_index * spacing
        for cell_index, cell in enumerate(planning_cells):
            layer_area = cell if layer_index == 0 else cell.buffer(
                -offset,
                join_style=2,
            )
            for polygon in _polygon_components(layer_area):
                simplified = polygon.simplify(
                    min(radius * 0.15, spacing * 0.2),
                    preserve_topology=True,
                )
                raw_ring = LineString(simplified.exterior.coords)
                oriented = _fillet_ring(raw_ring, center_area, geometry_radius)
                if oriented is None:
                    continue
                if _discrete_max_curvature(list(oriented.coords)) <= curvature_limit * 1.001:
                    rings.append(_ContourRing(oriented, f"cell-{cell_index}"))

        for component_index, component in enumerate(center_components):
            for hole_index, interior in enumerate(component.interiors):
                obstacle = Polygon(interior)
                base_ring = LineString(interior.coords)
                base_curvature = _discrete_max_curvature(list(base_ring.coords))
                has_sharp_corner = _max_heading_change(list(base_ring.coords)) > math.radians(8.0)
                corner_growth = (
                    geometry_radius
                    if has_sharp_corner or base_curvature > curvature_limit * 1.08
                    else 0.0
                )
                corner_growth = max(corner_growth, geometry_radius * 0.15)
                expanded_obstacle = obstacle.buffer(
                    corner_growth + offset,
                    quad_segs=16,
                    join_style=1,
                )
                if not isinstance(expanded_obstacle, Polygon):
                    continue
                hole_ring = _oriented_ring(LineString(expanded_obstacle.exterior.coords))
                if not center_area.buffer(1e-6).covers(hole_ring):
                    continue
                if _discrete_max_curvature(list(hole_ring.coords)) <= curvature_limit * 1.001:
                    rings.append(_ContourRing(
                        hole_ring,
                        f"hole-{component_index}-{hole_index}",
                    ))
        if not rings:
            break
        layers.append(rings)

    chains = _match_contour_chains(layers, spacing)

    raw_path: List[Point2D] = []
    edge_zones: List[str] = []
    work_lines: List[LineString] = []
    anchor = entry_point
    contour_count = 0
    work_connector_count = 0
    transit_connector_count = 0
    max_contour_curvature = 0.0
    max_connector_curvature = 0.0
    max_connector_curvature_rate = 0.0
    tolerance = max(1e-7, implement_width_m * 1e-7)

    remaining_chains = [chain for chain in chains if chain]
    while remaining_chains:
        if anchor is None:
            chain = max(
                remaining_chains,
                key=lambda candidate: sum(ring.line.length for ring in candidate),
            )
        else:
            anchor_point = Point(anchor)
            chain = min(
                remaining_chains,
                key=lambda candidate: candidate[0].line.distance(anchor_point),
            )
        remaining_chains.remove(chain)

        ordered_rings = [_oriented_ring(ring.line) for ring in chain]
        candidate_layers = [
            _gate_candidates(ring, radius)
            for ring in ordered_rings
        ]
        usable_count = 0
        for candidates in candidate_layers:
            if not candidates:
                break
            usable_count += 1
        ordered_rings = ordered_rings[:usable_count]
        candidate_layers = candidate_layers[:usable_count]
        if not ordered_rings:
            continue

        transition_layers = []
        for index in range(len(ordered_rings) - 1):
            transition_layers.append(_transition_options(
                ordered_rings[index],
                ordered_rings[index + 1],
                candidate_layers[index],
                candidate_layers[index + 1],
                center_area,
                work_area,
                implement_width_m,
                radius,
                curvature_rate_limit,
                spacing,
            ))

        group_ranges = []
        group_start = 0
        for transition_index, options in enumerate(transition_layers):
            if not options:
                group_ranges.append((group_start, transition_index + 1))
                group_start = transition_index + 1
        group_ranges.append((group_start, len(ordered_rings)))

        for group_start, group_end in group_ranges:
            group_rings = ordered_rings[group_start:group_end]
            group_candidates = candidate_layers[group_start:group_end]
            group_options = transition_layers[group_start:group_end - 1]
            plan = _optimize_chain_group(
                group_rings,
                group_candidates,
                group_options,
                anchor,
            )

            if raw_path:
                connector = _shortest_connector(
                    work_area,
                    raw_path[-1],
                    plan.arrivals[0].point,
                    tolerance,
                )
                if connector is None:
                    raise ValueError(
                        "contour components are disconnected inside the safe work area"
                    )
                _append_segment(raw_path, edge_zones, connector, "transit")
                transit_connector_count += 1

            for ring_index, ring in enumerate(plan.rings):
                arrival = plan.arrivals[ring_index]
                departure = plan.departures[ring_index]
                ring_path = _forward_ring_path(
                    ring,
                    arrival.station,
                    arrival.station,
                    full_loop=True,
                )
                _append_segment(raw_path, edge_zones, ring_path, "work")
                work_lines.append(LineString(ring_path))
                contour_count += 1
                max_contour_curvature = max(
                    max_contour_curvature,
                    _discrete_max_curvature(list(ring.coords)),
                )

                if departure is not None:
                    repeated_path = _forward_ring_path(
                        ring,
                        arrival.station,
                        departure.station,
                        full_loop=False,
                    )
                    if len(repeated_path) >= 2:
                        _append_segment(raw_path, edge_zones, repeated_path, "work")
                        work_lines.append(LineString(repeated_path))

                    work_connection = plan.connections[ring_index]
                    if work_connection is None:
                        raise ValueError("missing optimized contour connection")
                    _append_segment(
                        raw_path,
                        edge_zones,
                        work_connection.points,
                        "work",
                    )
                    work_lines.append(LineString(work_connection.points))
                    work_connector_count += 1
                    max_connector_curvature = max(
                        max_connector_curvature,
                        work_connection.max_curvature,
                    )
                    max_connector_curvature_rate = max(
                        max_connector_curvature_rate,
                        work_connection.max_curvature_rate,
                    )
            anchor = raw_path[-1]

    (
        terminal_pass_count,
        terminal_work_connections,
        terminal_transits,
        terminal_max_curvature,
        terminal_max_curvature_rate,
    ) = _append_terminal_passes(
        raw_path,
        edge_zones,
        work_lines,
        _polygon_components(center_area),
        center_area,
        work_area,
        implement_width_m,
        spacing,
        radius,
        curvature_rate_limit,
    )
    work_connector_count += terminal_work_connections
    transit_connector_count += terminal_transits
    max_connector_curvature = max(max_connector_curvature, terminal_max_curvature)
    max_connector_curvature_rate = max(
        max_connector_curvature_rate,
        terminal_max_curvature_rate,
    )

    path, path_zones = _densify_labeled_path(
        raw_path,
        edge_zones,
        path_point_spacing_m,
    )
    coverage_ratio, unsafe_area, overlap_area, measured_overlap_ratio = _coverage_metrics(
        work_area,
        work_lines,
        implement_width_m,
    )
    max_curvature = max(max_contour_curvature, max_connector_curvature)
    achieved_radius = 1.0 / max_curvature if max_curvature > 1e-9 else float("inf")
    return ContourSpiralResult(
        path=path,
        path_zones=path_zones,
        contour_count=contour_count,
        layer_count=len(layers),
        chain_count=len(chains),
        component_count=len(_polygon_components(work_area)),
        work_connector_count=work_connector_count,
        transit_connector_count=transit_connector_count,
        coverage_ratio=coverage_ratio,
        unsafe_work_area_m2=unsafe_area,
        overlap_area_m2=overlap_area,
        overlap_ratio=measured_overlap_ratio,
        max_curvature_1pm=max_curvature,
        achieved_min_turn_radius_m=achieved_radius,
        connector_max_curvature_rate_1pm2=max_connector_curvature_rate,
        curvature_constrained=max_curvature <= curvature_limit * 1.001,
        terminal_pass_count=terminal_pass_count,
        contour_spacing_m=spacing,
        effective_overlap_ratio=max(0.0, 1.0 - spacing / implement_width_m),
    )
