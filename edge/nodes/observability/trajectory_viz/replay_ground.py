"""Worked-ground additions for the retained, bounded monitor replay.

Only the observations in the returned replay contribute. In particular, the
latest cumulative coverage must never be painted into an earlier replay frame.
The sweep itself is the same oriented implement rectangle used for evaluation.
"""

import math
from collections.abc import Mapping

from shapely.errors import ShapelyError
from shapely.geometry import Polygon
from shapely.ops import unary_union

from simulation.evaluation import CoverageAccumulator


def _finite(value):
    if isinstance(value, bool):
        return None
    try:
        result = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return result if math.isfinite(result) else None


def _fresh(observation, limit):
    if not isinstance(observation, Mapping) or observation.get("stale") is True:
        return False
    age = _finite(observation.get("age_s"))
    return age is not None and 0 <= age <= limit


def _regions(geometry):
    if isinstance(geometry, Polygon):
        if not geometry.is_empty and geometry.area > 1e-12:
            yield {"exterior": list(geometry.exterior.coords),
                   "holes": [list(ring.coords) for ring in geometry.interiors]}
    elif hasattr(geometry, "geoms"):
        for child in geometry.geoms:
            yield from _regions(child)


class _FrameSweep(CoverageAccumulator):
    """Reuse sweep subdivision without cumulative unions or replay metrics."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.pieces = []

    def _queue(self, geometry):
        if not geometry.is_empty and geometry.area > 1e-12:
            self.pieces.append(geometry)

    def take_polygons(self):
        if not self.pieces:
            return []
        geometry = unary_union(self.pieces).intersection(self.field)
        self.pieces.clear()
        return list(_regions(geometry))


def build_replay_ground(frames, scene):
    """Return incremental polygons keyed by original replay ``frame_index``.

    Missing or old observations break the connection. Controller state is
    accepted as an explicit estimate, just as for live coverage; commands alone
    never constitute a working observation. Frame and source changes also break
    the connection, so neither old task paths nor outages create a painted line.
    """
    result = {"available": False, "scope": "retained_replay", "segments": [],
              "estimated": False, "position_source": "unknown",
              "implement_source": "unknown", "position_sources": [],
              "implement_sources": []}
    if not frames:
        return {**result, "reason": "no_history"}
    if not isinstance(scene, Mapping) or not scene.get("field_boundary"):
        return {**result, "reason": "missing_field"}
    overlay = scene.get("coverage_overlay")
    if not isinstance(overlay, Mapping):
        return {**result, "reason": "missing_implement_dimensions"}
    width = _finite(overlay.get("implement_width_m"))
    length = _finite(overlay.get("implement_length_m", 0.2))
    offset = _finite(overlay.get("implement_offset_m", 0.0))
    if width is None or length is None or offset is None or min(width, length) <= 0:
        return {**result, "reason": "invalid_implement_dimensions"}
    try:
        sweep = _FrameSweep(scene["field_boundary"], width,
                            field_holes=scene.get("field_holes"),
                            implement_length_m=length, implement_offset_m=offset)
    except (TypeError, ValueError, OverflowError, ShapelyError):
        return {**result, "reason": "invalid_field"}
    if sweep.field.is_empty or sweep.field.area <= 0:
        return {**result, "reason": "invalid_field"}

    result.update({"task_id": scene.get("task_id"), "implement_width_m": width,
                   "implement_length_m": length, "implement_offset_m": offset})
    previous = None
    positions, implements = set(), set()
    observed = 0
    for index, frame in enumerate(frames):
        if not isinstance(frame, Mapping):
            sweep.break_segment()
            previous = None
            continue
        limit = _finite(frame.get("stale_after_s"))
        timestamp = _finite(frame.get("timestamp"))
        source = frame.get("primary_source")
        pose = frame.get(source) if source in ("truth", "estimate") else None
        implement = frame.get("implement")
        task_id = frame.get("task_id")
        matching_task = scene.get("task_id") is None or task_id == scene["task_id"]
        valid = (matching_task and timestamp is not None and limit is not None and limit > 0
                 and frame.get("status") == "live"
                 and _fresh(pose, limit) and _fresh(implement, limit))
        if valid:
            coordinates = [_finite(pose.get(key)) for key in ("x", "y", "theta")]
            height = _finite(implement.get("hitch_height"))
            implement_source = implement.get("source")
            valid = (all(value is not None for value in coordinates) and height is not None
                     and isinstance(implement.get("pto_on"), bool)
                     and implement_source in ("simulation_truth", "feedback", "controller_status"))
        if not valid:
            sweep.break_segment()
            previous = None
            continue

        identity = (task_id, source, implement_source)
        if (previous is None or identity != previous[0]
                or not 0 < timestamp - previous[1] <= min(limit, previous[2])):
            sweep.break_segment()
        working = implement["pto_on"] and height >= 0.95
        estimated = source == "estimate" or implement_source == "controller_status"
        sweep.add({"x": coordinates[0], "y": coordinates[1], "theta": coordinates[2],
                   "working": working, "position_source": source,
                   "implement_source": implement_source})
        polygons = sweep.take_polygons()
        if polygons:
            result["segments"].append({"frame_index": index, "polygons": polygons,
                                       "estimated": estimated})
        previous = identity, timestamp, limit
        positions.add(source)
        implements.add(implement_source)
        result["estimated"] = result["estimated"] or estimated
        observed += 1

    result.update({"available": observed > 0, "observed_frame_count": observed,
                   "position_sources": sorted(positions), "implement_sources": sorted(implements),
                   "position_source": next(iter(positions)) if len(positions) == 1 else "mixed" if positions else "unknown",
                   "implement_source": next(iter(implements)) if len(implements) == 1 else "mixed" if implements else "unknown"})
    if not observed:
        result["reason"] = "no_fresh_implement_observations"
    return result
