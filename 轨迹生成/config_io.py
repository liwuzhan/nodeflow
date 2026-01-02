#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
配置解析模块

包含 VehicleConfig 类和相关的配置文件解析函数。
"""

import re
from typing import List, Tuple, Dict, Optional
from shapely.geometry import LineString, MultiLineString
from pyproj import Transformer


class VehicleConfig:
    """车辆配置类，包含作业参数和计算属性。"""
    
    def __init__(self):
        self.implement_width_m: float = 3.0
        self.overlap_ratio: float = 0.1
        self.path_inset_m: float = 1.0
        self.pivot_turn: bool = True
        self.yaw_rate_max_deg_s: float = 60.0
        self.min_turn_radius_m: Optional[float] = None
        self.pivot_radius_m: Optional[float] = None

    @property
    def effective_row_spacing(self) -> float:
        """有效行距（考虑重叠率）。"""
        return self.implement_width_m * (1.0 - self.overlap_ratio)

    @property
    def turn_radius(self) -> float:
        """转弯半径，优先使用 MIN_TURN_RADIUS_M，其次使用 PIVOT_RADIUS_M。"""
        if self.min_turn_radius_m is not None:
            return self.min_turn_radius_m
        if self.pivot_radius_m is not None:
            return self.pivot_radius_m
        return max(0.5, 0.5 * self.implement_width_m)


def parse_parcel(path: str) -> Dict:
    """
    解析地块配置文件。
    
    Args:
        path: 地块配置文件路径
        
    Returns:
        包含外环、孔洞、点障碍和出入口信息的字典
    """
    outer: List[Tuple[float, float]] = []
    holes: List[List[Tuple[float, float]]] = []
    points: List[Tuple[float, float, float]] = []  # (lon, lat, diameter_m)
    entries: List[Dict] = []

    default_diam = 1.0
    with open(path, 'r', encoding='utf-8') as f:
        lines = [ln.strip() for ln in f.readlines()]
    
    i = 0
    while i < len(lines):
        ln = lines[i]
        if ln.upper().startswith('POINTS_DEFAULT_DIAMETER_M'):
            parts = ln.split()
            default_diam = float(parts[-1])
            i += 1
            continue
        if ln.upper() == 'OUTER':
            i += 1
            ring = []
            while i < len(lines) and lines[i].upper() != 'END':
                lon, lat = map(float, lines[i].split(','))
                ring.append((lon, lat))
                i += 1
            outer = ring
            i += 1
            continue
        if ln.upper().startswith('HOLE'):
            i += 1
            ring = []
            while i < len(lines) and lines[i].upper() != 'END':
                lon, lat = map(float, lines[i].split(','))
                ring.append((lon, lat))
                i += 1
            holes.append(ring)
            i += 1
            continue
        if ln.upper().startswith('POINT '):
            # 支持可选 DIAMETER_M
            # 例如：POINT p-01 障碍点1 121.50097390,31.19982725 DIAMETER_M 0.50
            m = re.search(r"POINT\s+\S+\s+\S+\s+([0-9\.-]+,[0-9\.-]+)(?:\s+DIAMETER_M\s+([0-9\.-]+))?", ln, re.I)
            if m:
                lon, lat = map(float, m.group(1).split(','))
                diam = float(m.group(2)) if m.group(2) is not None else default_diam
                points.append((lon, lat, diam))
            i += 1
            continue
        if ln.upper().startswith('ENTRY_EXIT'):
            # 示例：ENTRY_EXIT entry-01 "主入口" 121.50030429,31.19911756 HEADING_DEG 180 WIDTH_M 5.0 TYPE main
            m = re.search(r"ENTRY_EXIT\s+(\S+)\s+\"?(.*?)\"?\s+([0-9\.-]+),([0-9\.-]+)(?:\s+HEADING_DEG\s+([0-9\.-]+))?(?:\s+WIDTH_M\s+([0-9\.-]+))?(?:\s+TYPE\s+(\S+))?", ln, re.I)
            if m:
                entries.append({
                    'id': m.group(1),
                    'name': m.group(2),
                    'lon': float(m.group(3)),
                    'lat': float(m.group(4)),
                    'heading': float(m.group(5)) if m.group(5) else None,
                    'width': float(m.group(6)) if m.group(6) else None,
                    'type': m.group(7) if m.group(7) else None,
                })
            i += 1
            continue
        i += 1

    return {
        'outer': outer,
        'holes': holes,
        'points': points,
        'entries': entries,
    }


def parse_vehicle(path: str) -> VehicleConfig:
    """
    解析车辆配置文件。
    
    Args:
        path: 车辆配置文件路径
        
    Returns:
        VehicleConfig 实例
    """
    cfg = VehicleConfig()
    with open(path, 'r', encoding='utf-8') as f:
        for ln in f:
            ln = ln.strip()
            if not ln or ln.startswith(';'):
                continue
            if 'IMPLEMENT_WIDTH_M' in ln:
                m = re.search(r'IMPLEMENT_WIDTH_M\s+([0-9\.-]+)', ln)
                if m:
                    cfg.implement_width_m = float(m.group(1))
            if 'OVERLAP_RATIO' in ln:
                m = re.search(r'OVERLAP_RATIO\s+([0-9\.-]+)', ln)
                if m:
                    cfg.overlap_ratio = float(m.group(1))
            if 'PATH_INSET_M' in ln:
                m = re.search(r'PATH_INSET_M\s+([0-9\.-]+)', ln)
                if m:
                    cfg.path_inset_m = float(m.group(1))
            if re.search(r'PIVOT_TURN\s+yes', ln, re.I):
                cfg.pivot_turn = True
            if 'YAW_RATE_MAX_DEGS' in ln:
                m = re.search(r'YAW_RATE_MAX_DEGS\s+([0-9\.-]+)', ln)
                if m:
                    cfg.yaw_rate_max_deg_s = float(m.group(1))
            if 'MIN_TURN_RADIUS_M' in ln:
                m = re.search(r'MIN_TURN_RADIUS_M\s+([0-9\.-]+)', ln)
                if m:
                    cfg.min_turn_radius_m = float(m.group(1))
            if 'PIVOT_RADIUS_M' in ln:
                m = re.search(r'PIVOT_RADIUS_M\s+([0-9\.-]+)', ln)
                if m:
                    cfg.pivot_radius_m = float(m.group(1))
    return cfg


# === 结果输出（经纬度TXT） ===
def _guess_utm_epsg(lon: float, lat: float) -> int:
    """根据经纬度猜测对应的 UTM EPSG 代码。"""
    zone = int((lon + 180) / 6) + 1
    if lat >= 0:
        return 32600 + zone  # WGS84 / UTM 北半球
    else:
        return 32700 + zone  # WGS84 / UTM 南半球


def _local_to_wgs84_transformer(ref_lon: float, ref_lat: float) -> Transformer:
    """创建本地（UTM）到 WGS84 的转换器，参考点用于选择 UTM 带。"""
    epsg = _guess_utm_epsg(ref_lon, ref_lat)
    return Transformer.from_crs(epsg, 4326, always_xy=True)


def export_linestring_local_to_wgs84_txt(line_local: LineString,
                                         ref_lon: float,
                                         ref_lat: float,
                                         output_path: str,
                                         precision: int = 8) -> None:
    """
    将本地坐标系的 LineString 转换为经纬度并按每行 "lon,lat" 写入 TXT。

    - 精度：小数点后 `precision` 位（默认 8 位，约厘米级）。
    - 输出顺序：保持 LineString 坐标顺序。

    Args:
        line_local: 本地坐标系下的折线（UTM米）
        ref_lon: 参考经度（用于确定 UTM 带）
        ref_lat: 参考纬度（用于确定 UTM 带）
        output_path: 输出 TXT 文件路径
        precision: 小数位数（默认 8）
    """
    if line_local.is_empty:
        # 若为空则仍创建空文件，便于下游流程感知
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write('')
        return

    t_wgs = _local_to_wgs84_transformer(ref_lon, ref_lat)
    fmt = f"{{:.{precision}f}}"
    lines: List[str] = []
    for x, y in line_local.coords:
        lon, lat = t_wgs.transform(x, y)
        lines.append(f"{fmt.format(lon)},{fmt.format(lat)}")
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines))


def export_multilines_local_to_wgs84_txt(paths_local: List[LineString] | MultiLineString,
                                          ref_lon: float,
                                          ref_lat: float,
                                          output_path: str,
                                          precision: int = 8,
                                          separator: str = ''
                                          ) -> None:
    """
    将多条本地折线转换为经纬度并写入 TXT（可选分隔符用于链之间的间隔）。

    - 每个点一行："lon,lat"；多条折线之间插入 `separator`（例如空行）。
    - 若传入 MultiLineString，则按其子几何顺序输出。
    """
    t_wgs = _local_to_wgs84_transformer(ref_lon, ref_lat)
    fmt = f"{{:.{precision}f}}"
    lines: List[str] = []

    def dump_line(ls: LineString):
        if ls.is_empty:
            return
        for x, y in ls.coords:
            lon, lat = t_wgs.transform(x, y)
            lines.append(f"{fmt.format(lon)},{fmt.format(lat)}")

    if isinstance(paths_local, MultiLineString):
        geoms = list(paths_local.geoms)
        for idx, ls in enumerate(geoms):
            dump_line(ls)
            if separator and idx < len(geoms) - 1:
                lines.append(separator)
    else:
        for idx, ls in enumerate(paths_local):
            dump_line(ls)
            if separator and idx < len(paths_local) - 1:
                lines.append(separator)

    with open(output_path, 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines))