"""
地理坐标工具库

坐标系约定：
- WGS84: 世界大地测量系统 (GPS原始坐标系)
- GCJ02: 火星坐标系 (中国国测局加密，高德/腾讯地图使用)
- BD09:  百度坐标系 (百度地图使用)

航向角坐标系约定：
1. 地理坐标系 (Geographic): 北=0°, 顺时针(CW)为正, 范围 [0, 360)
   - 用于导航、GPS heading、地图显示
   - 推荐用于节点间传递航向角

2. 数学坐标系 (Mathematical): 东=0°, 逆时针(CCW)为正, 范围 (-π, π]
   - 用于数学计算、物理仿真
   - 内部计算可用，但不建议节点间传递
"""

import math
from typing import Tuple


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
# WGS84 坐标与局部笛卡尔坐标转换
# ============================================================================

def local_to_wgs84(x: float, y: float, ref_lon: float, ref_lat: float) -> Tuple[float, float]:
    """
    局部笛卡尔坐标转 WGS84 经纬度

    局部坐标系定义：
    - 原点：(ref_lon, ref_lat)
    - X轴：东方向（米）
    - Y轴：北方向（米）

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


def wgs84_to_local(lon: float, lat: float, ref_lon: float, ref_lat: float) -> Tuple[float, float]:
    """
    WGS84 经纬度转局部笛卡尔坐标

    Args:
        lon: 经度（度）
        lat: 纬度（度）
        ref_lon: 参考点经度（度）
        ref_lat: 参考点纬度（度）

    Returns:
        (x, y) 局部坐标（米），x=东向, y=北向
    """
    x = (lon - ref_lon) * meters_per_degree_lon(ref_lat)
    y = (lat - ref_lat) * METERS_PER_DEGREE_LAT
    return x, y


# ============================================================================
# 距离计算
# ============================================================================

def haversine(lon1: float, lat1: float, lon2: float, lat2: float) -> float:
    """
    使用 Haversine 公式计算两点间的大圆距离

    Args:
        lon1, lat1: 起点经纬度（度）
        lon2, lat2: 终点经纬度（度）

    Returns:
        距离（米）
    """
    lat1r = math.radians(lat1)
    lat2r = math.radians(lat2)
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat / 2) ** 2 + math.cos(lat1r) * math.cos(lat2r) * math.sin(dlon / 2) ** 2
    c = 2 * math.asin(math.sqrt(a))
    return EARTH_RADIUS_M * c


# ============================================================================
# 方位角计算 (Bearing)
# ============================================================================

def _bearing_rad(lon1: float, lat1: float, lon2: float, lat2: float) -> float:
    """
    内部函数：计算从点1到点2的大圆方位角（弧度）

    使用标准的初始方位角(initial bearing)公式，返回值符合地理坐标系：
    - 0 rad = 北方向
    - π/2 rad = 东方向
    - ±π rad = 南方向
    - -π/2 rad = 西方向
    - 顺时针(CW)为正
    - 范围：(-π, π] 弧度

    Args:
        lon1, lat1: 起点经纬度（度）
        lon2, lat2: 终点经纬度（度）

    Returns:
        方位角（弧度），范围 (-π, π]
    """
    lat1r = math.radians(lat1)
    lat2r = math.radians(lat2)
    dlon = math.radians(lon2 - lon1)
    y = math.sin(dlon) * math.cos(lat2r)
    x = math.cos(lat1r) * math.sin(lat2r) - math.sin(lat1r) * math.cos(lat2r) * math.cos(dlon)
    return math.atan2(y, x)


def bearing_geo(lon1: float, lat1: float, lon2: float, lat2: float) -> float:
    """
    计算从点1到点2的方位角（地理坐标系）

    地理坐标系定义：
    - 0° = 北方向 (正北)
    - 90° = 东方向 (正东)
    - 180° = 南方向 (正南)
    - 270° = 西方向 (正西)
    - 顺时针(CW)为正
    - 范围：[0, 360) 度

    Args:
        lon1, lat1: 起点经纬度（度）
        lon2, lat2: 终点经纬度（度）

    Returns:
        方位角（度），范围 [0, 360)

    Note:
        这是节点间传递航向角的推荐格式
        与 GPS heading、地图显示等使用相同的坐标系
    """
    bearing_rad = _bearing_rad(lon1, lat1, lon2, lat2)
    # 将弧度转为度，并归一化到 [0, 360)
    bearing_deg = math.degrees(bearing_rad)
    return bearing_deg % 360.0


def bearing_math(lon1: float, lat1: float, lon2: float, lat2: float) -> float:
    """
    计算从点1到点2的方位角（数学坐标系）

    数学坐标系定义：
    - 0 rad = 东方向 (+X)
    - π/2 rad = 北方向 (+Y)
    - π rad = 西方向 (-X)
    - -π/2 rad = 南方向 (-Y)
    - 逆时针(CCW)为正
    - 范围：(-π, π] 弧度

    Args:
        lon1, lat1: 起点经纬度（度）
        lon2, lat2: 终点经纬度（度）

    Returns:
        方位角（弧度），范围 (-π, π]

    Note:
        此函数用于仿真器等使用数学坐标系的场景
        节点间传递推荐使用 bearing_geo()
    """
    # 地理坐标系方位角（弧度）
    geo_rad = _bearing_rad(lon1, lat1, lon2, lat2)

    # 转换为数学坐标系
    # 地理坐标系: 北=0, CW正
    # 数学坐标系: 东=0, CCW正
    # 转换公式: math = π/2 - geo
    math_rad = math.pi / 2.0 - geo_rad

    # 归一化到 (-π, π]
    return normalize_angle_rad(math_rad)


def bearing(lon1: float, lat1: float, lon2: float, lat2: float) -> float:
    """
    计算从点1到点2的方位角（地理坐标系弧度，向后兼容）

    ⚠️ 历史遗留：此函数返回地理坐标系弧度值

    原始实现返回的是地理坐标系（北=0, CW正）的弧度值，
    为保持向后兼容性，保留此行为。

    新代码应使用：
    - bearing_geo(): 地理坐标系（度），推荐用于节点间传递
    - bearing_math(): 数学坐标系（弧度），用于仿真器/物理计算
    """
    return _bearing_rad(lon1, lat1, lon2, lat2)


# ============================================================================
# 角度归一化
# ============================================================================

def normalize_angle_rad(angle_rad: float) -> float:
    """
    归一化角度到 (-π, π] 区间（数学坐标系）

    Args:
        angle_rad: 角度（弧度）

    Returns:
        归一化后的角度（弧度），范围 (-π, π]
    """
    while angle_rad > math.pi:
        angle_rad -= 2 * math.pi
    while angle_rad <= -math.pi:
        angle_rad += 2 * math.pi
    return angle_rad


def normalize_heading_deg(heading_deg: float) -> float:
    """
    归一化航向角到 [0, 360) 区间（地理坐标系）

    Args:
        heading_deg: 航向角（度）

    Returns:
        归一化后的航向角（度），范围 [0, 360)
    """
    return heading_deg % 360.0


# ============================================================================
# 坐标系转换
# ============================================================================

def heading_geo_to_math(heading_deg: float) -> float:
    """
    地理坐标系航向角 → 数学坐标系角度

    坐标系定义：
    - 地理坐标系: 北=0°, 顺时针(CW)为正, 范围 [0, 360)
    - 数学坐标系: 东=0, 逆时针(CCW)为正, 范围 (-π, π]

    转换关系（以东方向为基准）：
    - 地理 0°(北) → 数学 π/2(北)
    - 地理 90°(东) → 数学 0(东)
    - 地理 180°(南) → 数学 -π/2(南)
    - 地理 270°(西) → 数学 π(西)

    Args:
        heading_deg: 地理坐标系航向角（度），北=0, CW正

    Returns:
        数学坐标系角度（弧度），东=0, CCW正
    """
    # 地理到数学的转换: math = π/2 - geo_rad
    # 先转弧度，再转换坐标系
    geo_rad = math.radians(heading_deg)
    math_rad = math.pi / 2.0 - geo_rad
    return normalize_angle_rad(math_rad)


def heading_math_to_geo(angle_rad: float) -> float:
    """
    数学坐标系角度 → 地理坐标系航向角

    坐标系定义：
    - 数学坐标系: 东=0, 逆时针(CCW)为正, 范围 (-π, π]
    - 地理坐标系: 北=0°, 顺时针(CW)为正, 范围 [0, 360)

    转换关系（以北方向为基准）：
    - 数学 π/2(北) → 地理 0°(北)
    - 数学 0(东) → 地理 90°(东)
    - 数学 -π/2(南) → 地理 180°(南)
    - 数学 π(西) → 地理 270°(西)

    Args:
        angle_rad: 数学坐标系角度（弧度），东=0, CCW正

    Returns:
        地理坐标系航向角（度），北=0, CW正，范围 [0, 360)
    """
    # 数学到地理的转换: geo_deg = (90 - math_deg) mod 360
    geo_deg = 90.0 - math.degrees(angle_rad)
    return geo_deg % 360.0
