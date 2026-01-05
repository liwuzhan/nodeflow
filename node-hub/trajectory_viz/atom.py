#!/usr/bin/env python3
"""
轨迹可视化算法（L4纯函数层）

功能：
- 计算轨迹误差指标

输入输出均为标准Python数据结构，无框架依赖
"""

import math
from typing import List, Tuple, Dict, Any

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
