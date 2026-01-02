#!/usr/bin/env python3
"""
轨迹可视化算法（L4纯函数层）

功能：
- 计算轨迹误差指标
- 生成轨迹对比图像

输入输出均为标准Python数据结构，无框架依赖
"""

import math
from typing import List, Tuple, Dict, Any, Optional
from datetime import datetime
from pathlib import Path

import numpy as np
import matplotlib
matplotlib.use('Agg')  # Non-interactive backend
import matplotlib.pyplot as plt
from matplotlib.patches import Polygon

# 配置中文字体支持
plt.rcParams['font.sans-serif'] = ['PingFang SC', 'Arial Unicode MS', 'Heiti TC', 'STHeiti', 'SimHei']
plt.rcParams['axes.unicode_minus'] = False


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


def generate_trajectory_image(field_boundary: Optional[List[Tuple[float, float]]],
                              planned_path: Optional[List[Tuple[float, float]]],
                              actual_trajectory: List[Tuple[float, float]],
                              actual_trajectory_with_heading: List[Tuple[float, float, float]],
                              metrics: Dict[str, Any],
                              output_path: Path,
                              figsize: Tuple[float, float] = (14, 12),
                              dpi: int = 150,
                              ref_lon: Optional[float] = None,
                              ref_lat: Optional[float] = None) -> bool:
    """
    生成轨迹对比可视化图像（纯函数）

    Args:
        field_boundary: 地块边界 [(x, y), ...] ENU坐标
        planned_path: 规划路径 [(x, y), ...] ENU坐标
        actual_trajectory: 实际轨迹 [(x, y), ...] ENU坐标
        actual_trajectory_with_heading: 带航向角的实际轨迹 [(x, y, theta), ...]
        metrics: 统计指标
        output_path: 输出文件路径
        figsize: 图像尺寸
        dpi: 图像分辨率
        ref_lon: GPS参考点经度（用于显示）
        ref_lat: GPS参考点纬度（用于显示）

    Returns:
        是否成功
    """
    try:
        fig, ax = plt.subplots(figsize=figsize, dpi=dpi)

        # 绘制地块边界
        if field_boundary and len(field_boundary) >= 3:
            boundary_array = np.array(field_boundary)
            polygon = Polygon(boundary_array, fill=True, alpha=0.2,
                            color='green', edgecolor='darkgreen', linewidth=2)
            ax.add_patch(polygon)

        # 绘制规划路径
        if planned_path and len(planned_path) >= 2:
            planned_array = np.array(planned_path)
            ax.plot(planned_array[:, 0], planned_array[:, 1],
                   'b-', linewidth=2, label='规划路径', alpha=0.7)
            ax.plot(planned_array[0, 0], planned_array[0, 1], 'bo', markersize=10)
            ax.plot(planned_array[-1, 0], planned_array[-1, 1], 'bs', markersize=10)

        # 绘制实际轨迹
        if actual_trajectory and len(actual_trajectory) >= 2:
            actual_array = np.array(actual_trajectory)
            ax.plot(actual_array[:, 0], actual_array[:, 1],
                   'r-', linewidth=2, label='实际轨迹', alpha=0.7)
            ax.plot(actual_array[0, 0], actual_array[0, 1], 'ro', markersize=10)
            ax.plot(actual_array[-1, 0], actual_array[-1, 1], 'rs', markersize=10)

            # 绘制航向角箭头（数学坐标系）
            if actual_trajectory_with_heading and len(actual_trajectory_with_heading) >= 2:
                heading_data = np.array(actual_trajectory_with_heading)
                step = max(1, len(heading_data) // 20)

                for idx in range(0, len(heading_data), step):
                    x, y, theta = heading_data[idx]
                    arrow_len = 3.0  # 箭头长度3米
                    dx = math.cos(theta) * arrow_len
                    dy = math.sin(theta) * arrow_len

                    ax.arrow(x, y, dx, dy, head_width=1.5, head_length=1.0,
                            fc='red', ec='red', alpha=0.6, linewidth=1.5)

        # 添加统计信息
        approach_info = f"接近起点: {metrics.get('approach_distance_m', 0)} m\n" if metrics.get('approach_distance_m', 0) > 0 else ""
        stats_text = f"""轨迹统计 (ENU坐标系)
────────────────
规划距离: {metrics.get('planned_distance_m', 0)} m
{approach_info}已跟踪距离: {metrics.get('actual_distance_m', 0)} m
距离误差: {metrics.get('distance_error_m', 0)} m ({metrics.get('distance_error_percent', 0)}%)

平均横向误差: {metrics.get('avg_lateral_error_m', 0)} m
最大横向误差: {metrics.get('max_lateral_error_m', 0)} m

有效轨迹点: {metrics.get('trajectory_points', 0)} / {metrics.get('total_points', 0)}"""

        ax.text(0.02, 0.98, stats_text, transform=ax.transAxes,
               fontsize=10, verticalalignment='top', fontfamily='monospace',
               bbox=dict(boxstyle='round', facecolor='wheat', alpha=0.8))

        # 设置坐标轴
        ax.set_xlabel('X - 东向 (m)', fontsize=11)
        ax.set_ylabel('Y - 北向 (m)', fontsize=11)

        title = f'轨迹对比 (ENU) - {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}'
        if ref_lon and ref_lat:
            title += f'\nGPS参考点: ({ref_lon:.6f}°, {ref_lat:.6f}°)'
        ax.set_title(title, fontsize=14, fontweight='bold')

        ax.grid(True, alpha=0.3)
        ax.legend(loc='upper right', fontsize=10)
        ax.set_aspect('equal')

        # 保存图像
        output_path.parent.mkdir(parents=True, exist_ok=True)
        plt.savefig(output_path, format='jpg', dpi=dpi, bbox_inches='tight')
        plt.close(fig)

        return True

    except Exception as e:
        print(f"✗ 生成可视化失败: {e}")
        import traceback
        traceback.print_exc()
        return False
