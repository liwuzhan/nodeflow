#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
安全区域构建模块（ENU纯净版）

输入输出均为ENU坐标（米），不涉及GPS坐标转换。
"""

import math
from typing import List, Tuple, Dict, Union

import numpy as np
from shapely.geometry import Polygon, Point, MultiPolygon
from shapely.ops import unary_union
from shapely import minimum_rotated_rectangle

# 修改导入路径
from .models import VehicleConfig


def build_safe_area(parcel: Dict, cfg: VehicleConfig) -> Tuple[Union[MultiPolygon, Polygon], Tuple[float, float]]:
    """
    构建安全作业区域（ENU版本）。

    Args:
        parcel: 地块信息字典 (支持 ParcelData.to_dict() 格式)
            - 'outer': [(x, y), ...] ENU外边界坐标（米）
            - 'holes': [[(x, y), ...], ...] 孔洞坐标（米）
            - 'points': [(x, y, diam), ...] 点障碍坐标和直径（米）
        cfg: 车辆配置

    Returns:
        (安全作业区域, (参考经度, 参考纬度))
        注意：参考点设为(0, 0)，仅用于占位符
    """
    # 输入已是ENU坐标，无需转换
    if not parcel.get('outer'):
        return Polygon(), (0, 0)

    # 直接使用ENU坐标
    outer_xy = parcel['outer']
    hole_polys = [Polygon(h) for h in parcel['holes'] if len(h) >= 3]

    point_buffers = []
    for point_data in parcel['points']:
        if len(point_data) >= 3:
            x, y, diam = point_data[0], point_data[1], point_data[2]
            r = diam * 0.5 + cfg.path_inset_m
            point_buffers.append(Point(x, y).buffer(r, resolution=16))
        elif len(point_data) >= 2:
            # 兼容没有直径的情况
            x, y = point_data[0], point_data[1]
            r = cfg.path_inset_m
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

    # 返回(0, 0)作为参考点占位符（ENU版本不需要GPS参考点）
    return work_area, (0.0, 0.0)


def compute_job_direction(work_area: Union[Polygon, MultiPolygon]) -> float:
    """
    计算作业方向（最小旋转矩形长边方向）。
    
    Args:
        work_area: 安全作业区域
        
    Returns:
        作业方向角度（度）
    """
    if work_area.is_empty:
        return 0.0

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
