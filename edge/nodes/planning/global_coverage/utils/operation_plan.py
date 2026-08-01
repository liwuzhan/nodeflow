import math
from typing import Any, Dict, List, Optional, Tuple

from .models import VehicleConfig


def normalize_angle(angle_rad: float) -> float:
    while angle_rad > math.pi:
        angle_rad -= 2.0 * math.pi
    while angle_rad <= -math.pi:
        angle_rad += 2.0 * math.pi
    return angle_rad


def path_length(path: List[Tuple[float, float]]) -> float:
    total = 0.0
    for i in range(1, len(path)):
        x0, y0 = path[i - 1]
        x1, y1 = path[i]
        total += math.hypot(x1 - x0, y1 - y0)
    return total


def _path_station(path: List[Tuple[float, float]]) -> List[float]:
    stations = [0.0]
    for i in range(1, len(path)):
        x0, y0 = path[i - 1]
        x1, y1 = path[i]
        stations.append(stations[-1] + math.hypot(x1 - x0, y1 - y0))
    return stations


def _turn_indices(
    path: List[Tuple[float, float]],
    turn_angle_threshold_deg: float,
    turn_window_m: float = 4.0,
) -> List[int]:
    if len(path) < 3:
        return []

    threshold = math.radians(turn_angle_threshold_deg)
    result: List[int] = []
    stations = _path_station(path)
    headings: List[Tuple[int, float, float]] = []

    for i in range(1, len(path)):
        x0, y0 = path[i - 1]
        x1, y1 = path[i]
        seg_len = math.hypot(x1 - x0, y1 - y0)
        if seg_len <= 1e-6:
            continue

        heading = math.atan2(y1 - y0, x1 - x0)
        headings.append((i - 1, stations[i - 1] + seg_len * 0.5, heading))

    if len(headings) < 2:
        return []

    window = max(0.1, turn_window_m)
    for current_pos, (idx, station, heading) in enumerate(headings):
        for future_idx, future_station, future_heading in headings[current_pos + 1:]:
            if future_station - station > window:
                break
            turn = abs(normalize_angle(future_heading - heading))
            if turn >= threshold:
                result.append(max(idx, min(future_idx, len(path) - 1)))
                break

    return result


def classify_path_zones(
    path: List[Tuple[float, float]],
    turn_angle_threshold_deg: float = 45.0,
    turn_zone_radius_m: float = 4.0,
) -> List[str]:
    """
    Classify dense path points into work/transit zones from geometry.

    Large heading changes mark a short headland/turn zone around the corner.
    This is a transitional heuristic until a dedicated headland planner emits
    semantic segments directly.
    """
    if not path:
        return []

    zones = ["work"] * len(path)
    stations = _path_station(path)
    turns = _turn_indices(path, turn_angle_threshold_deg, max(turn_zone_radius_m * 2.0, 8.0))

    for idx in turns:
        center = stations[idx]
        for j, station in enumerate(stations):
            if abs(station - center) <= turn_zone_radius_m:
                zones[j] = "transit"

    if zones:
        zones[0] = "transit"
        zones[-1] = "transit"
    return zones


def build_segments_from_zones(
    path: List[Tuple[float, float]],
    zones: List[str],
    vehicle: VehicleConfig,
    work_speed_mps: float = 1.2,
    turn_speed_mps: float = 0.5,
    transit_segment_type: str = "headland_turn",
) -> List[Dict[str, Any]]:
    if not path:
        return []

    segments: List[Dict[str, Any]] = []
    stations = _path_station(path)
    start = 0
    seg_counts = {"work": 0, "headland_turn": 0, "transit": 0}

    def segment_type_for_zone(zone: str) -> str:
        return "work" if zone == "work" else transit_segment_type

    for i in range(1, len(path) + 1):
        at_end = i == len(path)
        zone_changed = not at_end and zones[i] != zones[start]
        if not at_end and not zone_changed:
            continue

        zone = zones[start] if start < len(zones) else "work"
        seg_type = segment_type_for_zone(zone)
        seg_counts[seg_type] = seg_counts.get(seg_type, 0) + 1
        prefix = {
            "work": "row",
            "headland_turn": "turn",
            "transit": "transit",
        }.get(seg_type, "segment")
        seg_id = f"{prefix}_{seg_counts[seg_type]:03d}"
        end = i - 1
        length = max(0.0, stations[end] - stations[start])

        speed_limit = work_speed_mps if seg_type == "work" else turn_speed_mps
        implement = {
            "mode": "tillage",
            "pto": "on" if seg_type == "work" else "off",
            "hitch": "down" if seg_type == "work" else "up",
            "engage_offset_m": max(0.5, vehicle.implement_width_m * 0.3),
            "disengage_offset_m": max(0.5, vehicle.implement_width_m * 0.5),
        }

        segments.append({
            "id": seg_id,
            "type": seg_type,
            "zone": zone,
            "start_index": start,
            "end_index": end,
            "length_m": round(length, 3),
            "motion": {
                "speed_limit_mps": speed_limit,
                "preferred_tracker": (
                    "line" if seg_type == "work"
                    else "turn" if seg_type == "headland_turn"
                    else "path"
                ),
            },
            "implement": implement,
        })

        start = i

    return segments


def build_operation_plan(
    task_id: str,
    path: List[Tuple[float, float]],
    vehicle: VehicleConfig,
    timestamp: float,
    turn_angle_threshold_deg: float = 45.0,
    turn_zone_radius_m: float = 4.0,
    work_speed_mps: float = 1.2,
    turn_speed_mps: float = 0.5,
    path_zones: Optional[List[str]] = None,
    planner_metadata: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    if path_zones is not None:
        if len(path_zones) != len(path):
            raise ValueError("path_zones must have the same length as path")
        zones = list(path_zones)
        transit_segment_type = "transit"
    else:
        zones = classify_path_zones(path, turn_angle_threshold_deg, turn_zone_radius_m)
        transit_segment_type = "headland_turn"
    segments = build_segments_from_zones(
        path,
        zones,
        vehicle,
        work_speed_mps,
        turn_speed_mps,
        transit_segment_type=transit_segment_type,
    )

    return {
        "task_id": task_id,
        "timestamp": timestamp,
        "frame": "ENU",
        "status": "success" if path else "failed",
        "path": path,
        "path_zones": zones,
        "segments": segments,
        "vehicle": {
            "implement_width_m": vehicle.implement_width_m,
            "overlap_ratio": vehicle.overlap_ratio,
            "path_inset_m": vehicle.path_inset_m,
            "min_turn_radius_m": vehicle.min_turn_radius_m,
            "work_min_turn_radius_m": vehicle.effective_work_min_turn_radius_m,
            "work_max_curvature_rate_1pm2": vehicle.work_max_curvature_rate_1pm2,
            "pivot_turn": vehicle.pivot_turn,
        },
        "summary": {
            "path_points": len(path),
            "path_length_m": round(path_length(path), 3),
            "segment_count": len(segments),
            "work_segment_count": sum(1 for s in segments if s.get("type") == "work"),
            "turn_segment_count": sum(1 for s in segments if s.get("type") == "headland_turn"),
            "transit_segment_count": sum(1 for s in segments if s.get("type") == "transit"),
            "planner": dict(planner_metadata or {}),
        },
    }
