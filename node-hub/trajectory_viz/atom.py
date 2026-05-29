#!/usr/bin/env python3
"""
轨迹可视化算法（L4纯函数层）

功能：
- 计算轨迹误差指标

输入输出均为标准Python数据结构，无框架依赖
"""

import math
from typing import List, Tuple, Dict, Any, Optional

import numpy as np


def euclidean_distance(p1: Tuple[float, float], p2: Tuple[float, float]) -> float:
    """
    计算欧几里得距离（米）

    Args:
        p1: 点1 (x, y)
        p2: 点2 (x, y)

    Returns:
        距离（米）
    """
    return math.sqrt((p2[0] - p1[0])**2 + (p2[1] - p1[1])**2)


def calculate_path_length(path: List[Tuple[float, float]]) -> float:
    """
    计算路径总长度（米）

    Args:
        path: 路径点列表 [(x, y), ...]

    Returns:
        总长度（米）
    """
    if len(path) < 2:
        return 0.0

    return sum(euclidean_distance(path[i], path[i+1])
               for i in range(len(path)-1))


def find_trajectory_start_index(trajectory: List[Tuple[float, float]],
                                planned_path: List[Tuple[float, float]],
                                approach_threshold_m: float = 5.0) -> int:
    """
    找到实际轨迹中第一个接近规划路径的点

    Args:
        trajectory: 实际轨迹 [(x, y), ...]
        planned_path: 规划路径 [(x, y), ...]
        approach_threshold_m: 接近阈值（米）

    Returns:
        起始索引
    """
    if not trajectory or not planned_path:
        return 0

    for idx, actual_point in enumerate(trajectory):
        dist = euclidean_distance(actual_point, planned_path[0])
        if dist < approach_threshold_m:
            return idx

    return 0


def calculate_lateral_errors(trajectory: List[Tuple[float, float]],
                             planned_path: List[Tuple[float, float]]) -> List[float]:
    """
    计算轨迹相对于规划路径的横向误差

    Args:
        trajectory: 实际轨迹 [(x, y), ...]
        planned_path: 规划路径 [(x, y), ...]

    Returns:
        横向误差列表（米）
    """
    lateral_errors = []

    for actual_point in trajectory:
        min_dist = float('inf')

        for i in range(len(planned_path) - 1):
            p1 = planned_path[i]
            p2 = planned_path[i + 1]

            dx = p2[0] - p1[0]
            dy = p2[1] - p1[1]

            # 点到线段的距离
            if dx*dx + dy*dy == 0:
                dist = euclidean_distance(actual_point, p1)
            else:
                t = max(0, min(1, ((actual_point[0] - p1[0]) * dx +
                                   (actual_point[1] - p1[1]) * dy) /
                               (dx * dx + dy * dy)))
                closest = (p1[0] + t * dx, p1[1] + t * dy)
                dist = euclidean_distance(actual_point, closest)

            min_dist = min(min_dist, dist)

        if min_dist != float('inf'):
            lateral_errors.append(min_dist)

    return lateral_errors


def calculate_trajectory_metrics(planned_path: List[Tuple[float, float]],
                                 actual_trajectory: List[Tuple[float, float]],
                                 approach_threshold_m: float = 5.0) -> Dict[str, Any]:
    """
    计算轨迹误差指标（纯函数）

    Args:
        planned_path: 规划路径 [(x, y), ...]
        actual_trajectory: 实际轨迹 [(x, y), ...]
        approach_threshold_m: 接近阈值（米）

    Returns:
        指标字典
    """
    if not planned_path or not actual_trajectory:
        return {}

    # 计算规划路径长度
    planned_len = calculate_path_length(planned_path)

    # 找到实际轨迹的有效起点
    start_index = find_trajectory_start_index(
        actual_trajectory, planned_path, approach_threshold_m
    )

    # 分段计算
    approach_trajectory = actual_trajectory[:start_index]
    tracking_trajectory = actual_trajectory[start_index:]

    approach_distance = calculate_path_length(approach_trajectory)
    actual_distance = calculate_path_length(tracking_trajectory)

    # 计算横向误差
    lateral_errors = calculate_lateral_errors(tracking_trajectory, planned_path)

    return {
        "planned_distance_m": round(planned_len, 2),
        "actual_distance_m": round(actual_distance, 2),
        "approach_distance_m": round(approach_distance, 2),
        "distance_error_m": round(abs(actual_distance - planned_len), 2),
        "distance_error_percent": round(
            abs(actual_distance - planned_len) / planned_len * 100
            if planned_len > 0 else 0, 1
        ),
        "avg_lateral_error_m": round(np.mean(lateral_errors), 2) if lateral_errors else 0,
        "max_lateral_error_m": round(np.max(lateral_errors), 2) if lateral_errors else 0,
        "trajectory_points": len(tracking_trajectory),
        "total_points": len(actual_trajectory),
        "start_index": start_index
    }


def calculate_polygon_area(boundary: List[Tuple[float, float]]) -> float:
    """
    Calculate polygon area with the shoelace formula.
    """
    if len(boundary) < 3:
        return 0.0

    area = 0.0
    for i in range(len(boundary)):
        x1, y1 = boundary[i]
        x2, y2 = boundary[(i + 1) % len(boundary)]
        area += x1 * y2 - x2 * y1
    return abs(area) * 0.5


def make_segment_coverage_polygon(
    p1: Tuple[float, float],
    p2: Tuple[float, float],
    width_m: float,
) -> Optional[List[Tuple[float, float]]]:
    """
    Approximate implement footprint for one travelled segment as a rectangle.
    """
    if width_m <= 0:
        return None

    x1, y1 = p1
    x2, y2 = p2
    dx = x2 - x1
    dy = y2 - y1
    length = math.hypot(dx, dy)
    if length <= 1e-6:
        return None

    nx = -dy / length
    ny = dx / length
    half = width_m * 0.5
    return [
        (x1 + nx * half, y1 + ny * half),
        (x2 + nx * half, y2 + ny * half),
        (x2 - nx * half, y2 - ny * half),
        (x1 - nx * half, y1 - ny * half),
    ]


def is_sample_working(sample: Dict[str, Any], hitch_threshold: float = 0.5) -> bool:
    """
    Decide whether a replay sample should count as active implement coverage.
    """
    if not sample:
        return False

    pto_on = sample.get("pto_on")
    hitch_height = sample.get("hitch_height")
    state = (sample.get("tillage_state") or "").lower()

    if pto_on is True:
        return True
    if hitch_height is not None and hitch_height >= hitch_threshold:
        return True
    return state in {"working", "lowering", "ready_to_engage"}


def build_coverage_overlay(
    replay_samples: List[Dict[str, Any]],
    implement_width_m: float,
    field_boundary: Optional[List[Tuple[float, float]]] = None,
    max_polygons: int = 500,
) -> Dict[str, Any]:
    """
    Build lightweight coverage polygons for visualization.

    This is an approximation for visual replay. It intentionally avoids heavy
    geometry dependencies and therefore estimates covered area by summing segment
    rectangles; overlap is not removed until a future Shapely-backed pass.
    """
    if implement_width_m <= 0 or len(replay_samples) < 2:
        field_area = calculate_polygon_area(field_boundary or [])
        return {
            "implement_width_m": implement_width_m,
            "field_area_m2": round(field_area, 2),
            "covered_area_m2": 0.0,
            "coverage_rate_percent": 0.0,
            "polygons": [],
            "planned_polygons": [],
            "active_segments": 0,
        }

    polygons: List[List[Tuple[float, float]]] = []
    covered_area_est = 0.0
    active_segments = 0

    for prev, cur in zip(replay_samples, replay_samples[1:]):
        x1 = prev.get("x")
        y1 = prev.get("y")
        x2 = cur.get("x")
        y2 = cur.get("y")
        if None in (x1, y1, x2, y2):
            continue

        if not (is_sample_working(prev) and is_sample_working(cur)):
            continue

        polygon = make_segment_coverage_polygon((x1, y1), (x2, y2), implement_width_m)
        if not polygon:
            continue

        active_segments += 1
        covered_area_est += euclidean_distance((x1, y1), (x2, y2)) * implement_width_m
        if len(polygons) < max_polygons:
            polygons.append(polygon)

    field_area = calculate_polygon_area(field_boundary or [])
    if field_area > 0:
        coverage_rate = min(100.0, covered_area_est / field_area * 100.0)
    else:
        coverage_rate = 0.0

    return {
        "implement_width_m": round(implement_width_m, 3),
        "field_area_m2": round(field_area, 2),
        "covered_area_m2": round(covered_area_est, 2),
        "coverage_rate_percent": round(coverage_rate, 1),
        "polygons": polygons,
        "planned_polygons": [],
        "active_segments": active_segments,
        "area_estimation": "segment_sum_no_overlap_subtraction",
    }


def _float_or_none(value: Any) -> Optional[float]:
    """Best-effort conversion for telemetry values."""
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def make_replay_sample(
    pose: Optional[Dict[str, Any]] = None,
    velocity_cmd: Optional[Dict[str, Any]] = None,
    next_point: Optional[Dict[str, Any]] = None,
    tillage_cmd: Optional[Dict[str, Any]] = None,
    tillage_status: Optional[Dict[str, Any]] = None,
    path_progress: Optional[Dict[str, Any]] = None,
    now: Optional[float] = None,
) -> Dict[str, Any]:
    """
    Build one compact replay sample from the latest runtime packets.

    The sample intentionally keeps only fields useful for visual replay and
    debugging. It does not mutate inputs and can be unit-tested without SDK.
    """
    pose = pose or {}
    velocity_cmd = velocity_cmd or {}
    next_point = next_point or {}
    tillage_cmd = tillage_cmd or {}
    tillage_status = tillage_status or {}
    path_progress = path_progress or {}

    sample = {
        "timestamp": now,
        "x": _float_or_none(pose.get("x")),
        "y": _float_or_none(pose.get("y")),
        "theta": _float_or_none(pose.get("theta")),
        "linear_velocity": _float_or_none(velocity_cmd.get("linear_velocity")),
        "angular_velocity": _float_or_none(velocity_cmd.get("angular_velocity")),
        "track_status": velocity_cmd.get("status", ""),
        "speed_factor": _float_or_none(velocity_cmd.get("speed_factor")),
        "dist_factor": _float_or_none(velocity_cmd.get("dist_factor")),
        "view_factor": _float_or_none(velocity_cmd.get("view_factor")),
        "mode_factor": _float_or_none(velocity_cmd.get("mode_factor")),
        "turn_factor": _float_or_none(velocity_cmd.get("turn_factor")),
        "target_x": _float_or_none(next_point.get("x")),
        "target_y": _float_or_none(next_point.get("y")),
        "next_index": next_point.get("index"),
        "next_mode": next_point.get("mode", ""),
        "in_view_count": next_point.get("in_view_count"),
        "upcoming_turn_angle_deg": _float_or_none(next_point.get("upcoming_turn_angle_deg")),
        "upcoming_turn_distance": _float_or_none(next_point.get("upcoming_turn_distance")),
        "zone": path_progress.get("zone") or next_point.get("zone", ""),
        "segment_id": path_progress.get("segment_id", ""),
        "segment_type": path_progress.get("segment_type", ""),
        "path_index": path_progress.get("path_index"),
        "distance_to_segment_end_m": _float_or_none(path_progress.get("distance_to_segment_end_m")),
        "cross_track_error_m": _float_or_none(path_progress.get("cross_track_error_m")),
        "heading_error_deg": _float_or_none(path_progress.get("heading_error_deg")),
        "tillage_state": tillage_status.get("state") or tillage_cmd.get("state", ""),
        "pto_on": tillage_status.get("pto_on", tillage_cmd.get("pto_on")),
        "hitch_height": _float_or_none(tillage_status.get("hitch_height", tillage_cmd.get("hitch_height"))),
        "pto_rpm": _float_or_none(tillage_status.get("pto_rpm", tillage_cmd.get("pto_rpm"))),
    }
    return sample


def detect_replay_events(
    previous: Optional[Dict[str, Any]],
    current: Dict[str, Any],
    turn_event_threshold_deg: float = 45.0,
) -> List[Dict[str, Any]]:
    """
    Detect sparse replay markers from consecutive samples.

    Events are for visualization only: state transitions, PTO toggles, tracker
    mode/status changes, segment changes, and entering a turn-preview window.
    """
    if not current:
        return []

    def make_event(kind: str, label: str, value: Any = None) -> Dict[str, Any]:
        return {
            "timestamp": current.get("timestamp"),
            "x": current.get("x"),
            "y": current.get("y"),
            "kind": kind,
            "label": label,
            "value": value,
        }

    events: List[Dict[str, Any]] = []

    if not previous:
        state = current.get("tillage_state")
        if state:
            events.append(make_event("tillage_state", f"机具:{state}", state))
        return events

    prev_status = previous.get("track_status") or ""
    cur_status = current.get("track_status") or ""
    if cur_status and cur_status != prev_status:
        events.append(make_event("track_status", f"底盘:{cur_status}", cur_status))

    prev_mode = previous.get("next_mode") or ""
    cur_mode = current.get("next_mode") or ""
    if cur_mode and cur_mode != prev_mode:
        events.append(make_event("waypoint_mode", f"前瞻:{cur_mode}", cur_mode))

    prev_segment = previous.get("segment_id") or previous.get("segment_type") or ""
    cur_segment = current.get("segment_id") or current.get("segment_type") or ""
    if cur_segment and cur_segment != prev_segment:
        events.append(make_event("segment", f"段:{cur_segment}", cur_segment))

    prev_tillage = previous.get("tillage_state") or ""
    cur_tillage = current.get("tillage_state") or ""
    if cur_tillage and cur_tillage != prev_tillage:
        events.append(make_event("tillage_state", f"机具:{cur_tillage}", cur_tillage))

    prev_pto = previous.get("pto_on")
    cur_pto = current.get("pto_on")
    if cur_pto is not None and cur_pto != prev_pto:
        events.append(make_event("pto", "PTO开" if cur_pto else "PTO关", cur_pto))

    prev_turn = previous.get("upcoming_turn_angle_deg") or 0.0
    cur_turn = current.get("upcoming_turn_angle_deg") or 0.0
    if prev_turn < turn_event_threshold_deg <= cur_turn:
        events.append(make_event("turn_preview", f"预判转角:{cur_turn:.0f}°", cur_turn))

    return events
