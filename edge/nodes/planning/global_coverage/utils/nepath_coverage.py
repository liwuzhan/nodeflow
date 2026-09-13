"""Optional NEPath CP/CFS geometry adapter; candidates are not driving plans.

NEPath connects CNC/printing contours, but does not constrain a vehicle's turning
radius. Keep separate native paths separate and report their geometry honestly.
No optimizer (IPOPT/Gurobi) is needed by this adapter.
"""
from __future__ import annotations

import importlib
import math
from dataclasses import dataclass
from typing import Any

import numpy as np
from shapely.geometry import LineString, MultiPolygon, Polygon
from shapely.geometry.polygon import orient
from shapely.ops import unary_union

NEPATH_TESTED_REVISION = "f688ec3c327b13180e72fe43e12b78fd191f05e2"
NEPATH_SOURCE = "https://github.com/WangY18/NEPath"
Point2D = tuple[float, float]


class NEPathUnavailableError(RuntimeError):
    """The optional native extension could not be loaded."""


@dataclass
class NEPathCandidate:
    paths: list[list[Point2D]]
    path_component_indices: list[int]
    metadata: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "paths": self.paths,
            "path_component_indices": self.path_component_indices,
            "metadata": self.metadata,
        }


def _load_nepath():
    try:
        return importlib.import_module("NEPath")
    except (ImportError, OSError) as exc:
        raise NEPathUnavailableError(
            "NEPath is optional and is not available. Install it with "
            "python tools/optional/install_nepath.py; see docs/NEPATH_OPTIONAL.md."
        ) from exc


def _components(area) -> list[Polygon]:
    if area.is_empty:
        return []
    if isinstance(area, Polygon):
        return [area]
    if isinstance(area, MultiPolygon):
        return list(area.geoms)
    raise ValueError("work_area must be a Polygon or MultiPolygon")


def _xy(ring):
    # Omit the duplicate closing vertex; NEPath treats contour inputs as closed.
    points = np.asarray(ring.coords[:-1], dtype=np.float64)
    return np.ascontiguousarray(points[:, 0]), np.ascontiguousarray(points[:, 1])


def sampled_turn_diagnostics(paths: list[list[Point2D]]) -> dict[str, Any]:
    """Three-point circumcircle estimates, never a continuous-curvature proof.

    Collinear reversals have zero circumcircle curvature, so count those
    separately and report a zero sampled radius when they occur.
    """
    maximum = 0.0
    max_heading_step = 0.0
    reversals = 0
    maximum_step = 0.0
    for path in paths:
        pts = np.asarray(path, dtype=float)
        if len(pts) < 2:
            continue
        edges = np.diff(pts, axis=0)
        lengths = np.linalg.norm(edges, axis=1)
        maximum_step = max(maximum_step, float(lengths.max()))
        if len(pts) < 3:
            continue
        # Evaluate closure as well if the native output is explicitly closed.
        if np.linalg.norm(pts[0] - pts[-1]) < 1e-8:
            pts = np.vstack([pts[-2], pts, pts[1]])
            edges = np.diff(pts, axis=0)
            lengths = np.linalg.norm(edges, axis=1)
        for i in range(len(edges) - 1):
            a, b = edges[i], edges[i + 1]
            la, lb = float(lengths[i]), float(lengths[i + 1])
            if min(la, lb) < 1e-9:
                continue
            cross = float(a[0] * b[1] - a[1] * b[0])
            dot = float(np.dot(a, b))
            angle = abs(math.atan2(cross, dot))
            max_heading_step = max(max_heading_step, angle)
            chord = float(np.linalg.norm(a + b))
            if angle > math.pi - 1e-6:
                reversals += 1
            if chord > 1e-9:
                maximum = max(maximum, 2.0 * abs(cross) / (la * lb * chord))
    return {
        "sampled_max_curvature_1pm": maximum,
        "sampled_min_radius_m": (0.0 if reversals else 1.0 / maximum) if maximum > 1e-12 or reversals else None,
        "max_heading_step_deg": math.degrees(max_heading_step),
        "collinear_reversal_count": reversals,
        "max_sample_step_m": maximum_step,
        "curvature_measurement": "three_point_circumcircle_on_native_samples",
    }


def build_nepath_candidate(
    work_area: Polygon | MultiPolygon,
    implement_width_m: float,
    overlap_ratio: float = 0.1,
    path_point_spacing_m: float = 0.2,
    min_turn_radius_m: float = 3.0,
) -> NEPathCandidate:
    """Generate raw contour-parallel + connected Fermat spiral candidates.

    ``work_area`` is the permitted swept area in local metres, including holes.
    It is inset by half the implement width before passing contours to NEPath.
    Each surviving component is planned independently. Paths are not joined,
    clipped, fitted, or advertised as continuous-curvature vehicle trajectories.
    """
    width = float(implement_width_m)
    overlap = float(overlap_ratio)
    spacing = float(path_point_spacing_m)
    radius = float(min_turn_radius_m)
    if not all(math.isfinite(v) for v in (width, overlap, spacing, radius)):
        raise ValueError("NEPath candidate parameters must be finite")
    if width <= 0 or spacing <= 0 or radius <= 0 or not 0 <= overlap < 1:
        raise ValueError("width, sample spacing and radius must be positive; overlap must be in [0, 1)")
    _components(work_area)
    if not work_area.is_valid:
        raise ValueError("work_area must be valid; do not silently repair field boundaries")
    nepath = _load_nepath()
    center_area = work_area.buffer(-width * 0.5)
    components = _components(center_area)
    paths: list[list[Point2D]] = []
    component_indices: list[int] = []
    for component_index, component in enumerate(components):
        # Standard exterior/inner orientation, with all coordinates remaining ENU.
        polygon = orient(component, sign=1.0)
        planner = nepath.NEPathPlanner()
        planner.set_contour(*_xy(polygon.exterior), wash=True, washdis=spacing, num_least=12)
        for hole in polygon.interiors:
            planner.addhole(*_xy(hole), wash=True, washdis=spacing, num_least=12)
        options = nepath.ContourParallelOptions()
        options.delta = width * (1.0 - overlap)
        options.wash = True
        options.washdis = spacing
        options.num_least = 12
        options.connector = nepath.ConnectAlgorithm.cfs
        for native_path in planner.CP(options):
            xs, ys = native_path.get_arrays()
            coords: list[Point2D] = []
            for x, y in zip(xs, ys):
                point = (float(x), float(y))
                if not all(math.isfinite(value) for value in point):
                    raise ValueError("NEPath returned a non-finite coordinate")
                if not coords or math.dist(coords[-1], point) > 1e-9:
                    coords.append(point)
            if len(coords) >= 2:
                paths.append(coords)
                component_indices.append(component_index)
    lines = [LineString(path) for path in paths]
    sweeps = [line.buffer(width * 0.5) for line in lines]
    sweep = unary_union(sweeps)
    covered = sweep.intersection(work_area)
    diagnostics = sampled_turn_diagnostics(paths)
    sampled_radius = diagnostics["sampled_min_radius_m"]
    radius_exceeded = sampled_radius is not None and sampled_radius + 1e-6 < radius
    outside = float(sweep.difference(work_area).area)
    reasons = ["raw_polyline_requires_vehicle_smoothing"]
    if not paths:
        reasons.append("no_paths")
    if len(paths) > 1:
        reasons.append("independent_paths_require_transfer_planning")
    if radius_exceeded:
        reasons.append("sampled_turn_radius_below_required_minimum")
    if outside > 0.05:
        reasons.append("tool_sweep_outside_work_area")
    metadata: dict[str, Any] = {
        "strategy": "nepath_cfs_candidate",
        "backend": "NEPath CP + CFS",
        "upstream_url": NEPATH_SOURCE,
        "tested_upstream_revision": NEPATH_TESTED_REVISION,
        "installed_package_version": getattr(nepath, "__version__", None),
        "execution_ready": False,
        "execution_blockers": reasons,
        "curvature_constrained": False,
        "required_min_turn_radius_m": radius,
        "sampled_curvature_limit_exceeded": radius_exceeded,
        "work_area_m2": float(work_area.area),
        "component_count": len(components),
        "path_count": len(paths),
        "point_count": sum(map(len, paths)),
        "path_length_m": sum(line.length for line in lines),
        "coverage_ratio": float(covered.area / work_area.area) if work_area.area else 0.0,
        "swept_outside_area_m2": outside,
        # Clipper's integer conversion can displace a boundary by sub-micrometres.
        # Use an explicit tolerance so a coincident edge is not counted wholesale.
        "centerline_outside_length_m": sum(line.difference(center_area.buffer(1e-6)).length for line in lines),
        "centerline_boundary_tolerance_m": 1e-6,
        "coverage_measurement": "round_buffer_of_raw_centerlines_with_zero_tool_offset",
        "row_spacing_m": width * (1.0 - overlap),
        "sample_spacing_requested_m": spacing,
        **diagnostics,
    }
    return NEPathCandidate(paths, component_indices, metadata)
