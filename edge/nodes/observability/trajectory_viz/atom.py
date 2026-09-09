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

from simulation.evaluation import CoverageAccumulator, is_working
from shapely import STRtree, distance as geometry_distance, linestrings, points
from shapely.geometry import Polygon
from shapely.ops import triangulate


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
    if not trajectory or len(planned_path) < 2:
        return []

    # Index every segment, not sampled vertices: nearest distance remains the
    # exact distance to the complete polyline, including sharp corners.
    coordinates = np.asarray(planned_path, dtype=float)[:, :2]
    segments = linestrings(np.stack((coordinates[:-1], coordinates[1:]), axis=1))
    repeated = np.all(coordinates[:-1] == coordinates[1:], axis=1)
    if np.any(repeated):
        # A zero-length segment has the same distance as its endpoint. Represent
        # it as a valid Point rather than indexing a degenerate LineString.
        segments[repeated] = points(coordinates[:-1][repeated])

    tree = STRtree(segments)
    observations = points(np.asarray(trajectory, dtype=float)[:, :2])
    nearest_indices = tree.nearest(observations)
    return geometry_distance(observations, segments[nearest_indices]).tolist()


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


def is_sample_working(sample: Dict[str, Any], hitch_threshold: float = 0.95) -> bool:
    """
    Decide whether a replay sample should count as active implement coverage.
    """
    return bool(sample) and is_working(sample, hitch_threshold)


def summarize_coverage_samples(replay_samples: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Summarize implement activity in replay samples for visual diagnostics.
    """
    total = len(replay_samples)
    working = sum(1 for sample in replay_samples if is_sample_working(sample))
    latest = replay_samples[-1] if replay_samples else {}
    latest_state = latest.get("tillage_state", "") if latest else ""
    latest_pto = latest.get("pto_on") if latest else None
    latest_hitch = latest.get("hitch_height") if latest else None

    return {
        "sample_count": total,
        "working_sample_count": working,
        "working_sample_percent": round((working / total * 100.0) if total else 0.0, 1),
        "latest_active": is_sample_working(latest) if latest else False,
        "latest_tillage_state": latest_state,
        "latest_pto_on": latest_pto,
        "latest_hitch_height": latest_hitch,
    }


def build_coverage_overlay(
    replay_samples: List[Dict[str, Any]],
    implement_width_m: float,
    field_boundary: Optional[List[Tuple[float, float]]] = None,
    max_polygons: int = 500,
    field_holes=None,
    implement_length_m: float = 0.2,
    implement_offset_m: float = 0.0,
    accumulator=None,
) -> Dict[str, Any]:
    """Cumulative statistics plus a bounded display overlay of recent samples."""
    polygons: List[List[Tuple[float, float]]] = []
    summary = summarize_coverage_samples(replay_samples)
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

        if len(polygons) < max_polygons:
            polygons.append(polygon)
    if accumulator is None and implement_width_m > 0 and field_boundary:
        accumulator = CoverageAccumulator(
            field_boundary, implement_width_m, field_holes=field_holes,
            implement_length_m=implement_length_m, implement_offset_m=implement_offset_m,
        ).extend(replay_samples)
    metrics = accumulator.metrics() if accumulator is not None else {
        "field_area_m2": 0.0, "covered_area_m2": 0.0, "coverage_rate_percent": 0.0,
        "active_segments": 0, "implement_width_m": implement_width_m,
    }
    display_geometry_truncated = False
    spatial_layers = {key: [] for key in ("covered", "repeated", "missed", "outside")}
    if accumulator is not None:
        polygons = []
        geometries = accumulator.geometries()

        def polygon_regions(geometry):
            if isinstance(geometry, Polygon):
                if not geometry.is_empty:
                    yield geometry
            elif hasattr(geometry, "geoms"):
                for child in geometry.geoms:
                    yield from polygon_regions(child)

        # The 3D view accepts holes directly; keep legacy flattened polygons for
        # the 2D page. Display simplification never feeds back into area metrics.
        for key, geometry in geometries.items():
            display = geometry.simplify(0.03, preserve_topology=True)
            if key != "outside":
                display = display.intersection(accumulator.field)
            for region in polygon_regions(display):
                if len(spatial_layers[key]) >= max_polygons:
                    display_geometry_truncated = True
                    break
                spatial_layers[key].append({
                    "exterior": list(region.exterior.coords),
                    "holes": [list(ring.coords) for ring in region.interiors],
                })
        covered = geometries["covered"].simplify(
            0.03, preserve_topology=True).intersection(accumulator.field)
        regions = [covered] if isinstance(covered, Polygon) else list(covered.geoms)
        for region in regions:
            if not isinstance(region, Polygon):
                continue
            # Plotly's old array format has no holes. Triangulate only regions
            # with holes so drawing never paints uncultivated islands green.
            parts = (triangulate(region) if region.interiors else [region])
            for part in parts:
                if region.interiors and not region.covers(part):
                    continue
                if len(polygons) < max_polygons:
                    polygons.append(list(part.exterior.coords))
                else:
                    display_geometry_truncated = True
    # Summary remains latest/window-based where appropriate; cumulative counters
    # come from the accumulator and do not fall when display history is trimmed.
    result = {
        **summary,
        **metrics,
        **spatial_layers,
        "polygons": polygons,
        "planned_polygons": [],
        "display_sample_count": len(replay_samples),
        "display_scope": "cumulative_sweep_recent_trajectory",
        "display_geometry_limit": max_polygons,
        "display_geometry_truncated": display_geometry_truncated,
        "position_source": (replay_samples[-1].get("position_source", "estimated_pose")
                            if replay_samples else "unknown"),
        "implement_source": (replay_samples[-1].get("implement_source", "unknown")
                             if replay_samples else "unknown"),
    }
    result["working_sample_percent"] = 100.0*result["working_sample_count"]/max(1, result["sample_count"])
    return result


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
    truth_state: Optional[Dict[str, Any]] = None,
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

    implement_intent = path_progress.get("implement", {}) or {}
    intent_pto = implement_intent.get("pto")
    intent_hitch = implement_intent.get("hitch")
    intent_working = (path_progress.get("zone") == "work") or (path_progress.get("segment_type") == "work")

    position_source = "estimated_pose"
    # TillageStatus is the controller's logical state, even when readiness
    # was confirmed using feedback; its hitch fields are not measurements.
    implement_source = "controller_status" if tillage_status else "command_estimate" if tillage_cmd else "unknown"
    if truth_state:
        pose = truth_state
        if "position" in truth_state:
            pose = {**truth_state.get("position", {}),
                    "theta": truth_state.get("orientation", {}).get("yaw")}
        position_source = "simulation_truth"
        truth_implement = truth_state.get("implement", truth_state)
        if "pto_on" in truth_implement and "hitch_height" in truth_implement:
            tillage_status = truth_implement
            implement_source = "simulation_truth"

    sample = {
        "timestamp": now,
        "x": _float_or_none(pose.get("x")),
        "y": _float_or_none(pose.get("y")),
        "theta": _float_or_none(pose.get("theta")),
        "position_source": position_source,
        "implement_source": implement_source,
        "planned_working": bool(intent_pto == "on" and intent_hitch == "down" or intent_working),
        "linear_velocity": _float_or_none(velocity_cmd.get("linear_velocity")),
        "angular_velocity": _float_or_none(velocity_cmd.get("angular_velocity")),
        "track_status": velocity_cmd.get("status", ""),
        "target_mode": velocity_cmd.get("target_mode", ""),
        "headland_turn": velocity_cmd.get("headland_turn"),
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
