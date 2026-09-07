"""Shared, deterministic implement-sweep evaluation in metres and radians.

The rectangle follows the supplied vehicle heading, with a signed longitudinal
offset (positive ahead of the pose origin). This is a geometric sweep, not a
soil/traction model. Coverage is clipped to the field minus its holes. Repeated
area means ground entered again after leaving the implement footprint; ordinary
overlap between adjacent time samples is not a second cultivation pass.
"""

from __future__ import annotations

import math
from typing import Any, Iterable, Mapping

from shapely.geometry import GeometryCollection, Polygon
from shapely.ops import unary_union


def is_working(sample: Mapping[str, Any], hitch_threshold: float = 0.95) -> bool:
    """Require both lowered implement and active PTO; intent is not feedback."""
    if sample.get("working") is not None:
        return sample["working"] is True
    height = sample.get("hitch_height")
    return sample.get("pto_on") is True and height is not None and float(height) >= hitch_threshold


def _pose(sample, fallback_theta=0.0):
    x, y = float(sample["x"]), float(sample["y"])
    theta = sample.get("theta")
    theta = fallback_theta if theta is None else float(theta)
    if not all(math.isfinite(v) for v in (x, y, theta)):
        raise ValueError("Sweep poses must be finite")
    return x, y, theta


def _footprint(pose, width, length, offset):
    x, y, theta = pose
    c, s = math.cos(theta), math.sin(theta)
    return Polygon([
        (x + a*c - b*s, y + a*s + b*c)
        for a, b in ((offset-length/2, -width/2), (offset+length/2, -width/2),
                     (offset+length/2, width/2), (offset-length/2, width/2))
    ])


def _merge_summary(left, right):
    a, ar = left
    b, br = right
    return unary_union([a, b]), unary_union([ar, br, a.intersection(b)])


def _batch_summary(pieces):
    """Balanced merges also detect repeats occurring wholly inside a batch."""
    level = [(p, GeometryCollection()) for p in pieces if not p.is_empty]
    if not level:
        return GeometryCollection(), GeometryCollection()
    while len(level) > 1:
        level = [_merge_summary(level[i], level[i+1]) if i+1 < len(level) else level[i]
                 for i in range(0, len(level), 2)]
    return level[0]


class CoverageAccumulator:
    """Cumulative sweep geometry, independent of a bounded display history.

    Expensive accumulated unions run once per batch or requested metrics snapshot,
    never at every high-frequency pose. Input samples themselves are not retained.
    Working state applies at a sample: an on->off interval is conservatively
    uncounted because the exact disengagement point is unknown.
    """

    def __init__(self, field_boundary, implement_width_m: float, *, field_holes=None,
                 implement_length_m: float = 0.2, implement_offset_m: float = 0.0,
                 sample_distance_m: float = 0.25,
                 sample_angle_rad: float = math.radians(2), batch_size: int = 128):
        self.width = float(implement_width_m)
        self.length = float(implement_length_m)
        self.offset = float(implement_offset_m)
        self.distance_step = float(sample_distance_m)
        self.angle_step = float(sample_angle_rad)
        if not all(math.isfinite(v) for v in (self.width, self.length, self.offset,
                                               self.distance_step, self.angle_step)):
            raise ValueError("Sweep parameters must be finite")
        if min(self.width, self.length, self.distance_step, self.angle_step) <= 0:
            raise ValueError("Implement dimensions and sampling steps must be positive")
        self.field = (field_boundary if hasattr(field_boundary, "geom_type")
                      else Polygon(field_boundary, holes=field_holes or []))
        if not self.field.is_valid:
            raise ValueError("Field must be a valid polygon with valid holes")
        self.batch_size = max(2, int(batch_size))
        self._covered = GeometryCollection()
        self._repeated = GeometryCollection()
        self._pending = []
        self._previous = None
        self.sample_count = 0
        self.working_sample_count = 0
        self.active_segments = 0
        self.total_distance_m = 0.0
        self.working_distance_m = 0.0
        self.gross_in_field_area_m2 = 0.0
        self.gross_outside_area_m2 = 0.0
        self.position_sources = set()
        self.implement_sources = set()

    def _queue(self, geometry):
        if geometry.is_empty or geometry.area <= 1e-12:
            return
        inside_area = geometry.intersection(self.field).area
        self.gross_in_field_area_m2 += inside_area
        self.gross_outside_area_m2 += max(0.0, geometry.area - inside_area)
        self._pending.append(geometry)
        if len(self._pending) >= self.batch_size:
            self.flush()

    def flush(self):
        if self._pending:
            self._covered, self._repeated = _merge_summary(
                (self._covered, self._repeated), _batch_summary(self._pending))
            self._pending.clear()

    def add(self, sample: Mapping[str, Any]):
        """Add one chronological pose; missing x/y breaks the sweep connection."""
        self.sample_count += 1
        working = is_working(sample)
        self.working_sample_count += int(working)
        if sample.get("x") is None or sample.get("y") is None:
            self._previous = None
            return
        current = dict(sample)
        self.position_sources.add(current.get("position_source", "unspecified"))
        self.implement_sources.add(current.get("implement_source", "unspecified"))
        prev = self._previous
        fallback = (math.atan2(float(current["y"])-float(prev["y"]),
                               float(current["x"])-float(prev["x"])) if prev else 0.0)
        b = _pose(current, fallback)
        footprint = _footprint(b, self.width, self.length, self.offset)
        if prev is None or not is_working(prev):
            if working:
                self._queue(footprint)
        if prev is not None:
            a = _pose(prev, fallback)
            distance = math.hypot(b[0]-a[0], b[1]-a[1])
            self.total_distance_m += distance
            if working and is_working(prev):
                self.working_distance_m += distance
                da = math.atan2(math.sin(b[2]-a[2]), math.cos(b[2]-a[2]))
                count = max(1, math.ceil(distance/self.distance_step),
                            math.ceil(abs(da)/self.angle_step))
                old = _footprint(a, self.width, self.length, self.offset)
                for index in range(1, count+1):
                    t = index/count
                    p = (a[0]+(b[0]-a[0])*t, a[1]+(b[1]-a[1])*t, a[2]+da*t)
                    new = _footprint(p, self.width, self.length, self.offset)
                    # Excluding the old footprint avoids treating sample overlap
                    # or a stationary implement as a second pass.
                    self._queue(unary_union([old, new]).convex_hull.difference(old))
                    old = new
                if distance > 1e-9 or abs(da) > 1e-9:
                    self.active_segments += 1
        self._previous = current

    def extend(self, samples: Iterable[Mapping[str, Any]]):
        for sample in samples:
            self.add(sample)
        return self

    def break_segment(self):
        """Mark missing observations; never sweep a line across an unknown gap."""
        self._previous = None

    def geometries(self):
        self.flush()
        return {
            "covered": self._covered.intersection(self.field),
            "missed": self.field.difference(self._covered),
            "repeated": self._repeated.intersection(self.field),
            "outside": self._covered.difference(self.field),
        }

    def metrics(self):
        geometries = self.geometries()
        area = self.field.area
        covered = geometries["covered"].area
        return {
            "field_area_m2": area,
            "covered_area_m2": covered,
            "unique_covered_area_m2": covered,
            "missed_area_m2": geometries["missed"].area,
            "repeated_area_m2": geometries["repeated"].area,
            "outside_area_m2": geometries["outside"].area,
            "gross_in_field_area_m2": self.gross_in_field_area_m2,
            "repeat_pass_area_m2": max(0.0, self.gross_in_field_area_m2-covered),
            "gross_outside_area_m2": self.gross_outside_area_m2,
            "coverage_rate_percent": covered/area*100 if area else 0.0,
            "repeat_rate_percent": geometries["repeated"].area/area*100 if area else 0.0,
            "implement_width_m": self.width,
            "implement_length_m": self.length,
            "implement_offset_m": self.offset,
            "total_distance_m": self.total_distance_m,
            "working_distance_m": self.working_distance_m,
            "active_segments": self.active_segments,
            "sample_count": self.sample_count,
            "working_sample_count": self.working_sample_count,
            "area_estimation": "sampled_oriented_rectangle_union",
            "sample_distance_m": self.distance_step,
            "sample_angle_rad": self.angle_step,
            "coverage_scope": "cumulative",
            "position_sources": sorted(self.position_sources),
            "implement_sources": sorted(self.implement_sources),
        }


def evaluate_coverage(samples, field_boundary, implement_width_m, **kwargs):
    """Pure offline API: return only JSON-serializable cumulative metrics."""
    return CoverageAccumulator(field_boundary, implement_width_m, **kwargs).extend(samples).metrics()
