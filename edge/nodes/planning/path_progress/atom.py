import math
from typing import Any, Dict, List, Optional, Tuple


def normalize_angle(angle_rad: float) -> float:
    while angle_rad > math.pi:
        angle_rad -= 2.0 * math.pi
    while angle_rad <= -math.pi:
        angle_rad += 2.0 * math.pi
    return angle_rad


def _path_stations(path: List[Tuple[float, float]]) -> List[float]:
    stations = [0.0]
    for i in range(1, len(path)):
        x0, y0 = path[i - 1]
        x1, y1 = path[i]
        stations.append(stations[-1] + math.hypot(x1 - x0, y1 - y0))
    return stations


def project_pose_to_path(
    pose: Dict[str, Any],
    path: List[Tuple[float, float]],
    search_start_idx: int = 0,
    search_window: int = 80,
    heading_match_weight_m: float = 2.0,
    path_stations: Optional[List[float]] = None,
) -> Optional[Dict[str, Any]]:
    if not pose or len(path) < 2:
        return None

    px = pose.get("x")
    py = pose.get("y")
    if px is None or py is None:
        return None

    start = max(0, min(search_start_idx, len(path) - 2))
    end = min(len(path) - 1, start + max(1, search_window))
    if start >= len(path) - 1:
        start = max(0, len(path) - 2)
        end = len(path) - 1

    stations = path_stations if path_stations is not None else _path_stations(path)
    if len(stations) != len(path):
        raise ValueError("path_stations must match path length")
    best = None
    best_score = float("inf")
    pose_theta = pose.get("theta")
    try:
        pose_theta = float(pose_theta) if pose_theta is not None else None
    except (TypeError, ValueError):
        pose_theta = None
    heading_weight = max(0.0, float(heading_match_weight_m))

    for i in range(start, end):
        x0, y0 = path[i]
        x1, y1 = path[i + 1]
        dx = x1 - x0
        dy = y1 - y0
        seg_len_sq = dx * dx + dy * dy
        if seg_len_sq <= 1e-12:
            continue

        t = ((px - x0) * dx + (py - y0) * dy) / seg_len_sq
        t = max(0.0, min(1.0, t))
        cx = x0 + t * dx
        cy = y0 + t * dy
        ex = px - cx
        ey = py - cy
        dist_sq = ex * ex + ey * ey
        heading = math.atan2(dy, dx)
        heading_error = (
            abs(normalize_angle(heading - pose_theta))
            if pose_theta is not None
            else 0.0
        )
        score = math.sqrt(dist_sq) + heading_weight * (heading_error / math.pi)

        if score < best_score:
            seg_len = math.sqrt(seg_len_sq)
            station = stations[i] + t * seg_len
            signed_error = (dx * (py - y0) - dy * (px - x0)) / seg_len
            best_score = score
            best = {
                "path_index": i,
                "segment_fraction": t,
                "closest_x": cx,
                "closest_y": cy,
                "station_m": station,
                "cross_track_error_m": signed_error,
                "path_heading_rad": heading,
            }

    return best


def find_segment_for_index(segments: List[Dict[str, Any]], path_index: int) -> Optional[Dict[str, Any]]:
    for segment in segments:
        start = int(segment.get("start_index", 0))
        end = int(segment.get("end_index", start))
        if start <= path_index <= end:
            return segment
    return None


def distance_to_segment_end(
    path: List[Tuple[float, float]],
    station_m: float,
    segment: Optional[Dict[str, Any]],
    path_stations: Optional[List[float]] = None,
) -> float:
    if not path:
        return 0.0

    stations = path_stations if path_stations is not None else _path_stations(path)
    if segment:
        end_idx = max(0, min(int(segment.get("end_index", len(path) - 1)), len(path) - 1))
    else:
        end_idx = len(path) - 1
    return max(0.0, stations[end_idx] - station_m)


def next_segment_after(segments: List[Dict[str, Any]], current: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    if not segments or not current:
        return None
    try:
        idx = segments.index(current)
    except ValueError:
        return None
    if idx + 1 < len(segments):
        return segments[idx + 1]
    return None


def compute_progress(
    operation_plan: Dict[str, Any],
    pose: Dict[str, Any],
    last_path_index: int = 0,
    search_window: int = 100,
    relocalize_error_m: float = 8.0,
    heading_match_weight_m: float = 2.0,
    path_stations: Optional[List[float]] = None,
) -> Optional[Dict[str, Any]]:
    if not operation_plan or not pose:
        return None

    path = operation_plan.get("path", [])
    if isinstance(path, dict):
        path = path.get("points", [])
    if len(path) < 2:
        return None

    projection = project_pose_to_path(
        pose,
        path,
        last_path_index,
        search_window,
        heading_match_weight_m=heading_match_weight_m,
        path_stations=path_stations,
    )
    if not projection:
        return None

    relocalized = False
    if abs(projection["cross_track_error_m"]) > relocalize_error_m:
        full_projection = project_pose_to_path(
            pose,
            path,
            0,
            len(path) - 1,
            heading_match_weight_m=heading_match_weight_m,
            path_stations=path_stations,
        )
        if full_projection and abs(full_projection["cross_track_error_m"]) < abs(projection["cross_track_error_m"]):
            projection = full_projection
            relocalized = True

    segments = operation_plan.get("segments", []) or []
    segment = find_segment_for_index(segments, projection["path_index"])
    upcoming_segment = next_segment_after(segments, segment)

    pose_theta = float(pose.get("theta", 0.0) or 0.0)
    heading_error = normalize_angle(projection["path_heading_rad"] - pose_theta)

    dist_to_end = distance_to_segment_end(path, projection["station_m"], segment, path_stations)

    result = {
        "task_id": operation_plan.get("task_id"),
        "segment_id": segment.get("id", "") if segment else "",
        "segment_type": segment.get("type", "") if segment else "",
        "zone": segment.get("zone", "") if segment else "",
        "path_index": projection["path_index"],
        "segment_fraction": round(projection["segment_fraction"], 4),
        "closest_x": projection["closest_x"],
        "closest_y": projection["closest_y"],
        "station_m": round(projection["station_m"], 3),
        "distance_to_segment_end_m": round(dist_to_end, 3),
        "cross_track_error_m": round(projection["cross_track_error_m"], 3),
        "heading_error_deg": round(math.degrees(heading_error), 2),
        "path_heading_rad": projection["path_heading_rad"],
        "relocalized": relocalized,
        "motion": segment.get("motion", {}) if segment else {},
        "implement": segment.get("implement", {}) if segment else {},
        "upcoming": {
            "next_segment_id": upcoming_segment.get("id", "") if upcoming_segment else "",
            "next_segment_type": upcoming_segment.get("type", "") if upcoming_segment else "",
            "distance_m": round(dist_to_end, 3) if upcoming_segment else None,
        },
    }
    return result
