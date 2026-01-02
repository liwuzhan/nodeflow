#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
安全区域构建模块

包含安全区域构建、坐标转换和作业方向计算等功能。
"""

import math
from typing import List, Tuple, Dict

import numpy as np
from shapely.geometry import Polygon, Point, MultiPolygon
from shapely.ops import unary_union, transform
from shapely import minimum_rotated_rectangle
from pyproj import Transformer

from config_io import VehicleConfig


def guess_utm_epsg(lon: float, lat: float) -> int:
    """根据经纬度猜测UTM投影的EPSG代码。"""
    zone = int((lon + 180) / 6) + 1
    if lat >= 0:
        return 32600 + zone  # WGS84 / UTM 北半球
    else:
        return 32700 + zone  # 南半球


def wgs84_to_local_transformer(ref_lon: float, ref_lat: float) -> Transformer:
    """创建WGS84到本地UTM坐标系的转换器。"""
    epsg = guess_utm_epsg(ref_lon, ref_lat)
    return Transformer.from_crs(4326, epsg, always_xy=True)


def local_to_wgs84_transformer(ref_lon: float, ref_lat: float) -> Transformer:
    """创建本地UTM坐标系到WGS84的转换器。"""
    epsg = guess_utm_epsg(ref_lon, ref_lat)
    return Transformer.from_crs(epsg, 4326, always_xy=True)


def to_local_coords(transformer: Transformer, coords: List[Tuple[float, float]]) -> List[Tuple[float, float]]:
    """将WGS84坐标转换为本地坐标。"""
    return [transformer.transform(lon, lat) for lon, lat in coords]


def to_wgs84_coords(transformer: Transformer, coords: List[Tuple[float, float]]) -> List[Tuple[float, float]]:
    """将本地坐标转换为WGS84坐标。"""
    return [transformer.transform(x, y) for x, y in coords]


def to_wgs_geometry(t_wgs: Transformer, geom):
    """将几何对象从本地坐标系转换为WGS84坐标系。"""
    return transform(lambda x, y, z=None: t_wgs.transform(x, y), geom)


def build_safe_area(parcel: Dict, cfg: VehicleConfig) -> Tuple[MultiPolygon | Polygon, Tuple[float, float]]:
    """
    构建安全作业区域。
    
    Args:
        parcel: 地块信息字典
        cfg: 车辆配置
        
    Returns:
        (安全作业区域, (参考经度, 参考纬度))
    """
    # 参考点：用外环第一个点确定UTM
    ref_lon, ref_lat = parcel['outer'][0]
    t_local = wgs84_to_local_transformer(ref_lon, ref_lat)

    outer_xy = to_local_coords(t_local, parcel['outer'])
    hole_polys = [Polygon(to_local_coords(t_local, h)) for h in parcel['holes'] if len(h) >= 3]
    point_buffers = []
    for (lon, lat, diam) in parcel['points']:
        x, y = t_local.transform(lon, lat)
        r = diam * 0.5 + cfg.path_inset_m
        point_buffers.append(Point(x, y).buffer(r, resolution=16))

    outer_poly = Polygon(outer_xy)
    # 外边界安全内缩
    safe_outer = outer_poly.buffer(-cfg.path_inset_m)

    # 孔洞安全膨胀
    safe_holes = [hp.buffer(cfg.path_inset_m) for hp in hole_polys]

    obstacles = safe_holes + point_buffers
    obstacles_union = unary_union(obstacles) if obstacles else None

    if obstacles_union:
        work_area = safe_outer.difference(obstacles_union)
    else:
        work_area = safe_outer

    return work_area, (ref_lon, ref_lat)


def compute_job_direction(work_area: Polygon | MultiPolygon) -> float:
    """
    计算作业方向（最小旋转矩形长边方向）。
    
    Args:
        work_area: 安全作业区域
        
    Returns:
        作业方向角度（度）
    """
    # 合并为单个多边形以计算最小旋转矩形
    if isinstance(work_area, MultiPolygon):
        merged = unary_union([p for p in work_area.geoms])
    else:
        merged = work_area
    
    rect = minimum_rotated_rectangle(merged)
    coords = list(rect.exterior.coords)[:4]  # 四个角点（不含重复闭合点）
    
    # 计算两条边长度
    edges = [(coords[i], coords[(i + 1) % 4]) for i in range(4)]
    lengths = [math.hypot(b[0] - a[0], b[1] - a[1]) for a, b in edges]
    
    # 找到长边对应的方向
    idx = int(np.argmax(lengths))
    a, b = edges[idx]
    dx = b[0] - a[0]
    dy = b[1] - a[1]
    angle = math.degrees(math.atan2(dy, dx))
    return angle