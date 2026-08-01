#!/usr/bin/env python3
"""
地块规划节点 - L4层坐标转换算法

功能：
- GPS 坐标转 ENU 坐标
- ENU 坐标转 GPS 坐标
- 批量转换地块边界
"""

import math
from typing import Tuple, List


# ============================================================================
# 坐标转换常量
# ============================================================================

EARTH_RADIUS_M = 6371000.0  # 地球半径（米）
METERS_PER_DEGREE_LAT = 111320.0  # 纬度每度对应的米数 (WGS84 平均值)


def meters_per_degree_lon(ref_lat: float) -> float:
    """
    计算给定纬度处，经度每度对应的米数

    Args:
        ref_lat: 参考纬度（度）

    Returns:
        经度每度对应的米数
    """
    return METERS_PER_DEGREE_LAT * math.cos(math.radians(ref_lat))


# ============================================================================
# GPS 坐标与 ENU 坐标转换
# ============================================================================

def gps_to_enu(lon: float, lat: float, ref_lon: float, ref_lat: float) -> Tuple[float, float]:
    """
    将 GPS 坐标转换为 ENU 坐标

    ENU 坐标系定义：
    - 原点：(ref_lon, ref_lat)
    - X轴：东方向（米）
    - Y轴：北方向（米）

    Args:
        lon: 经度（度）
        lat: 纬度（度）
        ref_lon: 参考点经度（度）
        ref_lat: 参考点纬度（度）

    Returns:
        (x, y) ENU 坐标（米），x=东向, y=北向
    """
    x = (lon - ref_lon) * meters_per_degree_lon(ref_lat)
    y = (lat - ref_lat) * METERS_PER_DEGREE_LAT
    return x, y


def enu_to_gps(x: float, y: float, ref_lon: float, ref_lat: float) -> Tuple[float, float]:
    """
    将 ENU 坐标转换为 GPS 坐标

    Args:
        x: 东向距离（米）
        y: 北向距离（米）
        ref_lon: 参考点经度（度）
        ref_lat: 参考点纬度（度）

    Returns:
        (lon, lat) WGS84 经纬度（度）
    """
    lon = ref_lon + (x / meters_per_degree_lon(ref_lat))
    lat = ref_lat + (y / METERS_PER_DEGREE_LAT)
    return lon, lat


def convert_boundary_gps_to_enu(boundary_gps: List[Tuple[float, float]],
                                 ref_lon: float, ref_lat: float) -> List[Tuple[float, float]]:
    """
    批量转换地块边界从 GPS 到 ENU

    Args:
        boundary_gps: GPS 坐标边界点列表 [(lon, lat), ...]
        ref_lon: 参考点经度（度）
        ref_lat: 参考点纬度（度）

    Returns:
        ENU 坐标边界点列表 [(x, y), ...]
    """
    return [gps_to_enu(lon, lat, ref_lon, ref_lat) for lon, lat in boundary_gps]


def convert_boundary_enu_to_gps(boundary_enu: List[Tuple[float, float]],
                                 ref_lon: float, ref_lat: float) -> List[Tuple[float, float]]:
    """
    批量转换地块边界从 ENU 到 GPS

    Args:
        boundary_enu: ENU 坐标边界点列表 [(x, y), ...]
        ref_lon: 参考点经度（度）
        ref_lat: 参考点纬度（度）

    Returns:
        GPS 坐标边界点列表 [(lon, lat), ...]
    """
    return [enu_to_gps(x, y, ref_lon, ref_lat) for x, y in boundary_enu]


def calculate_polygon_area(boundary_enu: List[Tuple[float, float]]) -> float:
    """
    计算多边形面积（平方米）

    使用鞋带公式（Shoelace formula）

    Args:
        boundary_enu: ENU 坐标边界点列表 [(x, y), ...]

    Returns:
        面积（平方米）
    """
    if len(boundary_enu) < 3:
        return 0.0

    area = 0.0
    n = len(boundary_enu)

    for i in range(n):
        x1, y1 = boundary_enu[i]
        x2, y2 = boundary_enu[(i + 1) % n]
        area += x1 * y2 - x2 * y1

    return abs(area) / 2.0


def calculate_perimeter(boundary_enu: List[Tuple[float, float]]) -> float:
    """
    计算多边形周长（米）

    Args:
        boundary_enu: ENU 坐标边界点列表 [(x, y), ...]

    Returns:
        周长（米）
    """
    if len(boundary_enu) < 2:
        return 0.0

    perimeter = 0.0
    n = len(boundary_enu)

    for i in range(n):
        x1, y1 = boundary_enu[i]
        x2, y2 = boundary_enu[(i + 1) % n]
        perimeter += math.sqrt((x2 - x1) ** 2 + (y2 - y1) ** 2)

    return perimeter


# ============================================================================
# 验证函数
# ============================================================================

def validate_boundary(boundary: List[Tuple[float, float]], min_points: int = 3) -> Tuple[bool, str]:
    """
    验证边界数据有效性

    Args:
        boundary: 边界点列表
        min_points: 最小点数

    Returns:
        (is_valid, error_message)
    """
    if not boundary:
        return False, "边界为空"

    if len(boundary) < min_points:
        return False, f"边界点数不足，需要至少 {min_points} 个点，当前 {len(boundary)} 个"

    # 检查是否所有坐标都是有效的数值
    for i, point in enumerate(boundary):
        if len(point) != 2:
            return False, f"第 {i+1} 个点格式错误，应为 (x, y) 或 (lon, lat)"

        x, y = point
        if not isinstance(x, (int, float)) or not isinstance(y, (int, float)):
            return False, f"第 {i+1} 个点坐标类型错误"

        if math.isnan(x) or math.isnan(y):
            return False, f"第 {i+1} 个点坐标包含 NaN"

        if math.isinf(x) or math.isinf(y):
            return False, f"第 {i+1} 个点坐标包含无穷大"

    return True, ""
