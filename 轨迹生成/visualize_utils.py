"""
可视化工具模块
包含所有可视化相关函数，用于生成安全区域、扫描射线、连接线和链式裁切的图像。
"""

import os
from typing import List, Tuple, Dict
import matplotlib.pyplot as plt
from shapely.geometry import Polygon, LineString, MultiPolygon
from pyproj import Transformer

from config_io import VehicleConfig
from config_io import export_linestring_local_to_wgs84_txt
from safe_area import build_safe_area, compute_job_direction, local_to_wgs84_transformer, wgs84_to_local_transformer, to_wgs84_coords
from scan_utils import generate_rays_first_contact, connect_rays_vertical, trim_rays_by_connectors
from scan_utils import build_open_polyline, compute_coverage_areas, filter_uncovered_by_edge_zone
from scan_utils import compute_coverage_areas_from_path
from scan_utils import select_even_row_spacing, build_open_polylines_for_components
from scan_utils import connect_polylines_along_outer_boundary, connect_path_with_entry_exit_along_outer_boundary


# 输出文件路径常量
CONFIG_DIR = r"e:\10\config"
SAFE_IMG = os.path.join(CONFIG_DIR, "safe_area.png")
SAFE_SCAN_IMG = os.path.join(CONFIG_DIR, "safe_area_scan.png")
SAFE_SCAN_CONNECT_IMG = os.path.join(CONFIG_DIR, "safe_area_scan_connect.png")
SAFE_SCAN_CHAIN_IMG = os.path.join(CONFIG_DIR, "safe_area_scan_chain.png")
SAFE_SCAN_POLYLINE_IMG = os.path.join(CONFIG_DIR, "safe_area_scan_polyline.png")
SAFE_UNCOVERED_IMG = os.path.join(CONFIG_DIR, "safe_area_uncovered.png")
SAFE_SECOND_POLYLINE_IMG = os.path.join(CONFIG_DIR, "safe_area_second_polyline.png")
SAFE_SECOND_POLYLINE_CONNECTED_IMG = os.path.join(CONFIG_DIR, "safe_area_second_polyline_connected.png")
SAFE_SECOND_POLYLINE_CONNECTED_TXT = os.path.join(CONFIG_DIR, "safe_area_second_polyline_connected.txt")


def _to_wgs_geometry(t_wgs: Transformer, geom):
    """将几何体从本地坐标系转换到 WGS84 坐标系"""
    def transform_coords(x, y, z=None):
        return t_wgs.transform(x, y)
    from shapely.ops import transform
    return transform(transform_coords, geom)


def visualize_safe_area(parcel: Dict, cfg: VehicleConfig) -> bool:
    """生成安全作业区域可视化图像"""
    print("构建安全作业区域...")
    work_area, (ref_lon, ref_lat) = build_safe_area(parcel, cfg)
    if work_area.is_empty:
        print("安全作业区域为空，退出。")
        return False
    # 回转到 WGS84
    t_wgs = local_to_wgs84_transformer(ref_lon, ref_lat)
    work_area_wgs = _to_wgs_geometry(t_wgs, work_area)

    # 准备绘图
    plt.figure(figsize=(8, 8), dpi=120)
    ax = plt.gca()
    ax.set_aspect('equal')
    ax.set_title('安全作业区域', fontsize=12)

    # 原始外环（蓝）
    if parcel['outer']:
        lons, lats = zip(*parcel['outer'])
        ax.plot(lons + (lons[0],), lats + (lats[0],), color='blue', linewidth=1.5, label='原始外环')

    # 原始孔洞（红）
    for h in parcel['holes']:
        if len(h) >= 3:
            hlons, hlats = zip(*h)
            ax.plot(hlons + (hlons[0],), hlats + (hlats[0],), color='red', linewidth=1.0, label='原始孔洞')

    # 原始点障碍（橙）
    for (lon, lat, diam) in parcel['points']:
        ax.plot(lon, lat, 'o', color='orange', markersize=4, label='点障碍')

    # 安全区域填充（浅绿）+ 边（深绿），孔洞覆盖为白色
    def draw_poly(poly: Polygon):
        ext = list(poly.exterior.coords)
        elons = [p[0] for p in ext]
        elats = [p[1] for p in ext]
        ax.fill(elons, elats, facecolor='palegreen', alpha=0.6, edgecolor='green', linewidth=1.2, label='安全区域')
        for hole in poly.interiors:
            h = list(hole.coords)
            hlons = [p[0] for p in h]
            hlats = [p[1] for p in h]
            ax.fill(hlons, hlats, facecolor='white', edgecolor='none', zorder=3)

    if isinstance(work_area_wgs, MultiPolygon):
        for poly in work_area_wgs.geoms:
            draw_poly(poly)
    else:
        draw_poly(work_area_wgs)

    # 范围使用外环包围盒
    if parcel['outer']:
        min_lon = min(p[0] for p in parcel['outer'])
        max_lon = max(p[0] for p in parcel['outer'])
        min_lat = min(p[1] for p in parcel['outer'])
        max_lat = max(p[1] for p in parcel['outer'])
        pad_lon = (max_lon - min_lon) * 0.05
        pad_lat = (max_lat - min_lat) * 0.05
        ax.set_xlim(min_lon - pad_lon, max_lon + pad_lon)
        ax.set_ylim(min_lat - pad_lat, max_lat + pad_lat)

    ax.legend(loc='upper right', fontsize=8)
    plt.tight_layout()
    plt.savefig(SAFE_IMG, dpi=300, bbox_inches='tight')
    plt.close()
    print(f"已生成安全区域图片: {SAFE_IMG}")
    return True


def visualize_safe_area_scan(parcel: Dict, cfg: VehicleConfig) -> bool:
    """在安全区域图上叠加"首段射线"并输出 safe_area_scan.png。"""
    print("构建安全作业区域并生成射线...")
    work_area, (ref_lon, ref_lat) = build_safe_area(parcel, cfg)
    if work_area.is_empty:
        print("安全作业区域为空，退出。")
        return False
    angle = compute_job_direction(work_area)
    spacing = cfg.effective_row_spacing
    rays_local = generate_rays_first_contact(work_area, spacing, angle)

    # 转到 WGS84 用于绘制
    t_wgs = local_to_wgs84_transformer(ref_lon, ref_lat)
    work_area_wgs = _to_wgs_geometry(t_wgs, work_area)

    # 准备绘图
    plt.figure(figsize=(8, 8), dpi=120)
    ax = plt.gca()
    ax.set_aspect('equal')
    ax.set_title('安全区域 + 射线（首段）', fontsize=12)

    # 原始外环/孔洞/点障碍
    if parcel['outer']:
        lons, lats = zip(*parcel['outer'])
        ax.plot(lons + (lons[0],), lats + (lats[0],), color='blue', linewidth=1.5, label='原始外环')
    for h in parcel['holes']:
        if len(h) >= 3:
            hlons, hlats = zip(*h)
            ax.plot(hlons + (hlons[0],), hlats + (hlats[0],), color='red', linewidth=1.0, label='原始孔洞')
    for (lon, lat, diam) in parcel['points']:
        ax.plot(lon, lat, 'o', color='orange', markersize=4, label='点障碍')

    # 安全区域填充
    def draw_poly(poly: Polygon):
        ext = list(poly.exterior.coords)
        elons = [p[0] for p in ext]
        elats = [p[1] for p in ext]
        ax.fill(elons, elats, facecolor='palegreen', alpha=0.6, edgecolor='green', linewidth=1.2, label='安全区域')
        for hole in poly.interiors:
            h = list(hole.coords)
            hlons = [p[0] for p in h]
            hlats = [p[1] for p in h]
            ax.fill(hlons, hlats, facecolor='white', edgecolor='none', zorder=3)
    if isinstance(work_area_wgs, MultiPolygon):
        for poly in work_area_wgs.geoms:
            draw_poly(poly)
    else:
        draw_poly(work_area_wgs)

    # 绘制射线（蓝青色）
    for ln in rays_local:
        # 转到 WGS84
        coords_wgs = to_wgs84_coords(t_wgs, list(ln.coords))
        xs = [p[0] for p in coords_wgs]
        ys = [p[1] for p in coords_wgs]
        ax.plot(xs, ys, '-', color='deepskyblue', linewidth=1.2, alpha=0.9)

    # 范围（外环包围盒）
    if parcel['outer']:
        min_lon = min(p[0] for p in parcel['outer'])
        max_lon = max(p[0] for p in parcel['outer'])
        min_lat = min(p[1] for p in parcel['outer'])
        max_lat = max(p[1] for p in parcel['outer'])
        pad_lon = (max_lon - min_lon) * 0.05
        pad_lat = (max_lat - min_lat) * 0.05
        ax.set_xlim(min_lon - pad_lon, max_lon + pad_lon)
        ax.set_ylim(min_lat - pad_lat, max_lat + pad_lat)

    ax.legend(loc='upper right', fontsize=8)
    plt.tight_layout()
    plt.savefig(SAFE_SCAN_IMG, dpi=300, bbox_inches='tight')
    plt.close()
    print(f"已生成安全区域扫描图片: {SAFE_SCAN_IMG}")
    return True


def visualize_safe_area_scan_connect(parcel: Dict, cfg: VehicleConfig) -> bool:
    """在安全区域图上叠加"首段射线 + 垂直连线"，输出 safe_area_scan_connect.png。"""
    print("构建安全作业区域并生成射线+连线...")
    work_area, (ref_lon, ref_lat) = build_safe_area(parcel, cfg)
    if work_area.is_empty:
        print("安全作业区域为空，退出。")
        return False
    angle = compute_job_direction(work_area)
    spacing = cfg.effective_row_spacing
    rays_local = generate_rays_first_contact(work_area, spacing, angle)
    connectors_local = connect_rays_vertical(work_area, spacing, angle)

    # 转到 WGS84 用于绘制
    t_wgs = local_to_wgs84_transformer(ref_lon, ref_lat)
    work_area_wgs = _to_wgs_geometry(t_wgs, work_area)

    # 准备绘图
    plt.figure(figsize=(8, 8), dpi=120)
    ax = plt.gca()
    ax.set_aspect('equal')
    ax.set_title('安全区域 + 射线（首段）+ 垂直连线', fontsize=12)

    # 原始外环/孔洞/点障碍
    if parcel['outer']:
        lons, lats = zip(*parcel['outer'])
        ax.plot(lons + (lons[0],), lats + (lats[0],), color='blue', linewidth=1.5, label='原始外环')
    for h in parcel['holes']:
        if len(h) >= 3:
            hlons, hlats = zip(*h)
            ax.plot(hlons + (hlons[0],), hlats + (hlats[0],), color='red', linewidth=1.0, label='原始孔洞')
    for (lon, lat, diam) in parcel['points']:
        ax.plot(lon, lat, 'o', color='orange', markersize=4, label='点障碍')

    # 安全区域填充
    def draw_poly(poly: Polygon):
        ext = list(poly.exterior.coords)
        elons = [p[0] for p in ext]
        elats = [p[1] for p in ext]
        ax.fill(elons, elats, facecolor='palegreen', alpha=0.6, edgecolor='green', linewidth=1.2, label='安全区域')
        for hole in poly.interiors:
            h = list(hole.coords)
            hlons = [p[0] for p in h]
            hlats = [p[1] for p in h]
            ax.fill(hlons, hlats, facecolor='white', edgecolor='none', zorder=3)
    if isinstance(work_area_wgs, MultiPolygon):
        for poly in work_area_wgs.geoms:
            draw_poly(poly)
    else:
        draw_poly(work_area_wgs)

    # 绘制射线（蓝青色）
    for ln in rays_local:
        coords_wgs = to_wgs84_coords(t_wgs, list(ln.coords))
        xs = [p[0] for p in coords_wgs]
        ys = [p[1] for p in coords_wgs]
        ax.plot(xs, ys, '-', color='deepskyblue', linewidth=1.2, alpha=0.9)

    # 绘制连线（洋红色）
    for ln in connectors_local:
        coords_wgs = to_wgs84_coords(t_wgs, list(ln.coords))
        xs = [p[0] for p in coords_wgs]
        ys = [p[1] for p in coords_wgs]
        ax.plot(xs, ys, '-', color='magenta', linewidth=1.6, alpha=0.95, label='垂直连线')

    # 范围（外环包围盒）
    if parcel['outer']:
        min_lon = min(p[0] for p in parcel['outer'])
        max_lon = max(p[0] for p in parcel['outer'])
        min_lat = min(p[1] for p in parcel['outer'])
        max_lat = max(p[1] for p in parcel['outer'])
        pad_lon = (max_lon - min_lon) * 0.05
        pad_lat = (max_lat - min_lat) * 0.05
        ax.set_xlim(min_lon - pad_lon, max_lon + pad_lon)
        ax.set_ylim(min_lat - pad_lat, max_lat + pad_lat)

    ax.legend(loc='upper right', fontsize=8)
    plt.tight_layout()
    plt.savefig(SAFE_SCAN_CONNECT_IMG, dpi=300, bbox_inches='tight')
    plt.close()
    print(f"已生成安全区域扫描连线图片: {SAFE_SCAN_CONNECT_IMG}")
    return True


def visualize_safe_area_scan_chain(parcel: Dict, cfg: VehicleConfig) -> bool:
    """生成安全区域 + 链式裁切射线 + 垂直连线的可视化图像"""
    print("构建安全作业区域并生成链式裁切...")
    work_area, (ref_lon, ref_lat) = build_safe_area(parcel, cfg)
    if work_area.is_empty:
        print("安全作业区域为空，退出。")
        return False
    angle = compute_job_direction(work_area)
    spacing = cfg.effective_row_spacing
    trimmed_local = trim_rays_by_connectors(work_area, spacing, angle)
    connectors_local = connect_rays_vertical(work_area, spacing, angle)

    # 转到 WGS84 用于绘制
    t_wgs = local_to_wgs84_transformer(ref_lon, ref_lat)
    work_area_wgs = _to_wgs_geometry(t_wgs, work_area)

    # 准备绘图
    plt.figure(figsize=(8, 8), dpi=120)
    ax = plt.gca()
    ax.set_aspect('equal')
    ax.set_title('安全区域 + 链式裁切（射线）+ 垂直连线', fontsize=12)

    # 原始外环/孔洞/点障碍
    if parcel['outer']:
        lons, lats = zip(*parcel['outer'])
        ax.plot(lons + (lons[0],), lats + (lats[0],), color='blue', linewidth=1.5, label='原始外环')
    for h in parcel['holes']:
        if len(h) >= 3:
            hlons, hlats = zip(*h)
            ax.plot(hlons + (hlons[0],), hlats + (hlats[0],), color='red', linewidth=1.0, label='原始孔洞')
    for (lon, lat, diam) in parcel['points']:
        ax.plot(lon, lat, 'o', color='orange', markersize=4, label='点障碍')

    # 安全区域填充
    def draw_poly(poly: Polygon):
        ext = list(poly.exterior.coords)
        elons = [p[0] for p in ext]
        elats = [p[1] for p in ext]
        ax.fill(elons, elats, facecolor='palegreen', alpha=0.6, edgecolor='green', linewidth=1.2, label='安全区域')
        for hole in poly.interiors:
            h = list(hole.coords)
            hlons = [p[0] for p in h]
            hlats = [p[1] for p in h]
            ax.fill(hlons, hlats, facecolor='white', edgecolor='none', zorder=3)
    if isinstance(work_area_wgs, MultiPolygon):
        for poly in work_area_wgs.geoms:
            draw_poly(poly)
    else:
        draw_poly(work_area_wgs)

    # 绘制裁切后的射线（深蓝）
    for ln in trimmed_local:
        coords_wgs = to_wgs84_coords(t_wgs, list(ln.coords))
        xs = [p[0] for p in coords_wgs]
        ys = [p[1] for p in coords_wgs]
        ax.plot(xs, ys, '-', color='navy', linewidth=1.6, alpha=0.95, label='裁切后射线')

    # 绘制连线（洋红）
    for ln in connectors_local:
        coords_wgs = to_wgs84_coords(t_wgs, list(ln.coords))
        xs = [p[0] for p in coords_wgs]
        ys = [p[1] for p in coords_wgs]
        ax.plot(xs, ys, '-', color='magenta', linewidth=1.4, alpha=0.95)

    # 范围（外环包围盒）
    if parcel['outer']:
        min_lon = min(p[0] for p in parcel['outer'])
        max_lon = max(p[0] for p in parcel['outer'])
        min_lat = min(p[1] for p in parcel['outer'])
        max_lat = max(p[1] for p in parcel['outer'])
        pad_lon = (max_lon - min_lon) * 0.05
        pad_lat = (max_lat - min_lat) * 0.05
        ax.set_xlim(min_lon - pad_lon, max_lon + pad_lon)
        ax.set_ylim(min_lat - pad_lat, max_lat + pad_lat)

    ax.legend(loc='upper right', fontsize=8)
    plt.tight_layout()
    plt.savefig(SAFE_SCAN_CHAIN_IMG, dpi=300, bbox_inches='tight')
    plt.close()
    print(f"已生成安全区域扫描链式图片: {SAFE_SCAN_CHAIN_IMG}")
    return True


def visualize_safe_area_scan_polyline(parcel: Dict, cfg: VehicleConfig) -> bool:
    """在安全区域图上叠加"开放折线路径"并输出 safe_area_scan_polyline.png。"""
    print("构建安全作业区域并生成开放折线...")
    work_area, (ref_lon, ref_lat) = build_safe_area(parcel, cfg)
    if work_area.is_empty:
        print("安全作业区域为空，退出。")
        return False
    angle = compute_job_direction(work_area)
    spacing = cfg.effective_row_spacing
    polyline_local = build_open_polyline(work_area, spacing, angle)

    # 转到 WGS84 用于绘制
    t_wgs = local_to_wgs84_transformer(ref_lon, ref_lat)
    work_area_wgs = _to_wgs_geometry(t_wgs, work_area)
    polyline_wgs = _to_wgs_geometry(t_wgs, polyline_local)

    # 准备绘图
    plt.figure(figsize=(8, 8), dpi=120)
    ax = plt.gca()
    ax.set_aspect('equal')
    ax.set_title('安全区域 + 开放折线路径', fontsize=12)

    # 原始外环/孔洞/点障碍
    if parcel['outer']:
        lons, lats = zip(*parcel['outer'])
        ax.plot(lons + (lons[0],), lats + (lats[0],), color='blue', linewidth=1.5, label='原始外环')
    for h in parcel['holes']:
        if len(h) >= 3:
            hlons, hlats = zip(*h)
            ax.plot(hlons + (hlons[0],), hlats + (hlats[0],), color='red', linewidth=1.0, label='原始孔洞')
    for (lon, lat, diam) in parcel['points']:
        ax.plot(lon, lat, 'o', color='orange', markersize=4, label='点障碍')

    # 安全区域填充
    def draw_poly(poly: Polygon):
        ext = list(poly.exterior.coords)
        elons = [p[0] for p in ext]
        elats = [p[1] for p in ext]
        ax.fill(elons, elats, facecolor='palegreen', alpha=0.6, edgecolor='green', linewidth=1.2, label='安全区域')
        for hole in poly.interiors:
            h = list(hole.coords)
            hlons = [p[0] for p in h]
            hlats = [p[1] for p in h]
            ax.fill(hlons, hlats, facecolor='white', edgecolor='none', zorder=3)
    if isinstance(work_area_wgs, MultiPolygon):
        for poly in work_area_wgs.geoms:
            draw_poly(poly)
    else:
        draw_poly(work_area_wgs)

    # 绘制开放折线（深紫色）
    if not polyline_wgs.is_empty:
        xs = [p[0] for p in polyline_wgs.coords]
        ys = [p[1] for p in polyline_wgs.coords]
        ax.plot(xs, ys, '-', color='purple', linewidth=1.8, alpha=0.95, label='开放折线')

    # 范围（外环包围盒）
    if parcel['outer']:
        min_lon = min(p[0] for p in parcel['outer'])
        max_lon = max(p[0] for p in parcel['outer'])
        min_lat = min(p[1] for p in parcel['outer'])
        max_lat = max(p[1] for p in parcel['outer'])
        pad_lon = (max_lon - min_lon) * 0.05
        pad_lat = (max_lat - min_lat) * 0.05
        ax.set_xlim(min_lon - pad_lon, max_lon + pad_lon)
        ax.set_ylim(min_lat - pad_lat, max_lat + pad_lat)

    ax.legend(loc='upper right', fontsize=8)
    plt.tight_layout()
    plt.savefig(SAFE_SCAN_POLYLINE_IMG, dpi=300, bbox_inches='tight')
    plt.close()
    print(f"已生成安全区域扫描折线图片: {SAFE_SCAN_POLYLINE_IMG}")
    return True


def visualize_safe_area_second_polyline(parcel: Dict,
                                        cfg: VehicleConfig,
                                        apply_edge_filter: bool = True,
                                        edge_ratio_threshold: float = 0.6) -> bool:
    """
    生成第二遍（180°旋转）的未覆盖区域折线：
    - 先基于第一遍作业（原始角度、基础行距）计算未覆盖区；
    - 对未覆盖组件应用边界带剔除（可选）；
    - 在 180° 旋转角度下，为每个未覆盖组件选择 0.6x–1.1x 的行距使行数为偶数，并生成开放折线；
    - 绘制安全区域、未覆盖区域（过滤后）以及第二遍折线，保存为 safe_area_second_polyline.png。
    """
    print("构建安全作业区域并生成第二遍未覆盖折线...")
    work_area, (ref_lon, ref_lat) = build_safe_area(parcel, cfg)
    if work_area.is_empty:
        print("安全作业区域为空，退出。")
        return False

    angle0 = compute_job_direction(work_area)
    spacing0 = cfg.effective_row_spacing

    # 第一遍路径（仅水平作业段计入覆盖）
    primary_local = build_open_polyline(work_area, spacing0, angle0)
    covered1, uncovered1 = compute_coverage_areas_from_path(work_area, primary_local, spacing0, angle0, cfg.implement_width_m, horizontal_only=True)
    if apply_edge_filter:
        uncovered1 = filter_uncovered_by_edge_zone(uncovered1, work_area, cfg.implement_width_m, threshold_ratio=edge_ratio_threshold)

    # 第二遍：角度旋转 180°
    angle2 = angle0 + 180.0
    # 对每个未覆盖组件生成偶数行的开放折线
    polylines_local = build_open_polylines_for_components(uncovered1, spacing0, angle2, factor_min=0.6, factor_max=1.1)

    # 转到 WGS84
    t_wgs = local_to_wgs84_transformer(ref_lon, ref_lat)
    work_area_wgs = _to_wgs_geometry(t_wgs, work_area)
    uncovered_wgs = _to_wgs_geometry(t_wgs, uncovered1)
    polylines_wgs = [
        LineString(to_wgs84_coords(t_wgs, list(ln.coords)))
        for ln in polylines_local if ln and not ln.is_empty
    ]

    # 绘图
    plt.figure(figsize=(8, 8), dpi=120)
    ax = plt.gca()
    ax.set_aspect('equal')
    ax.set_title('安全区域 + 未覆盖区域(过滤后) + 第二遍开放折线', fontsize=12)

    # 原始外环/孔洞/点障碍
    if parcel['outer']:
        lons, lats = zip(*parcel['outer'])
        ax.plot(lons + (lons[0],), lats + (lats[0],), color='blue', linewidth=1.5, label='原始外环')
    for h in parcel['holes']:
        if len(h) >= 3:
            hlons, hlats = zip(*h)
            ax.plot(hlons + (hlons[0],), hlats + (hlats[0],), color='red', linewidth=1.0, label='原始孔洞')
    for (lon, lat, diam) in parcel['points']:
        ax.plot(lon, lat, 'o', color='orange', markersize=4, label='点障碍')

    # 安全区域填充
    def draw_poly(poly: Polygon):
        ext = list(poly.exterior.coords)
        elons = [p[0] for p in ext]
        elats = [p[1] for p in ext]
        ax.fill(elons, elats, facecolor='palegreen', alpha=0.4, edgecolor='green', linewidth=1.2, label='安全区域')
        for hole in poly.interiors:
            h = list(hole.coords)
            hlons = [p[0] for p in h]
            hlats = [p[1] for p in h]
            ax.fill(hlons, hlats, facecolor='white', edgecolor='none', zorder=3)
    if isinstance(work_area_wgs, MultiPolygon):
        for poly in work_area_wgs.geoms:
            draw_poly(poly)
    else:
        draw_poly(work_area_wgs)

    # 未覆盖区域（过滤后）可视化
    def draw_area(geom, color, label, alpha=0.5):
        geoms = geom.geoms if isinstance(geom, MultiPolygon) else [geom]
        for poly in geoms:
            ext = list(poly.exterior.coords)
            xs = [p[0] for p in ext]
            ys = [p[1] for p in ext]
            ax.fill(xs, ys, facecolor=color, alpha=alpha, edgecolor='none', label=label)
    if not uncovered_wgs.is_empty:
        draw_area(uncovered_wgs, color='salmon', label='未覆盖区域(过滤后)', alpha=0.45)

    # 第二遍开放折线（深绿色）
    for ln in polylines_wgs:
        if ln.is_empty:
            continue
        xs = [p[0] for p in ln.coords]
        ys = [p[1] for p in ln.coords]
        ax.plot(xs, ys, '-', color='darkgreen', linewidth=1.8, alpha=0.95, label='第二遍开放折线')

    # 范围（外环包围盒）
    if parcel['outer']:
        min_lon = min(p[0] for p in parcel['outer'])
        max_lon = max(p[0] for p in parcel['outer'])
        min_lat = min(p[1] for p in parcel['outer'])
        max_lat = max(p[1] for p in parcel['outer'])
        pad_lon = (max_lon - min_lon) * 0.05
        pad_lat = (max_lat - min_lat) * 0.05
        ax.set_xlim(min_lon - pad_lon, max_lon + pad_lon)
        ax.set_ylim(min_lat - pad_lat, max_lat + pad_lat)

    ax.legend(loc='upper right', fontsize=8)
    plt.tight_layout()
    plt.savefig(SAFE_SECOND_POLYLINE_IMG, dpi=300, bbox_inches='tight')
    plt.close()
    print(f"已生成第二遍未覆盖区域折线图片: {SAFE_SECOND_POLYLINE_IMG}")
    return True


def visualize_safe_area_second_polyline_connected(parcel: Dict,
                                                  cfg: VehicleConfig,
                                                  orientation: str = 'auto',
                                                  apply_edge_filter: bool = True,
                                                  edge_ratio_threshold: float = 0.6) -> bool:
    """
    沿安全边界外环将第一次折线与第二次折线连接为单条路径，并输出 safe_area_second_polyline_connected.png。
    - 第一次折线使用原角度与基础行距；
    - 第二次折线在 180° 角度上按偶数行距规则生成；
    - 连接段严格沿安全区域外环，方向可选 'cw' 或 'ccw'。
    """
    print("构建安全作业区域并沿外环连接两遍折线...")
    work_area, (ref_lon, ref_lat) = build_safe_area(parcel, cfg)
    if work_area.is_empty:
        print("安全作业区域为空，退出。")
        return False

    angle0 = compute_job_direction(work_area)
    spacing0 = cfg.effective_row_spacing

    # 第一遍折线
    primary_local = build_open_polyline(work_area, spacing0, angle0)
    # 第二遍：基于“第一遍实际路径的水平作业段”计算未覆盖并过滤，再对每个组件生成偶数行折线
    covered1, uncovered1 = compute_coverage_areas_from_path(work_area, primary_local, spacing0, angle0, cfg.implement_width_m, horizontal_only=True)
    if apply_edge_filter:
        uncovered1 = filter_uncovered_by_edge_zone(uncovered1, work_area, cfg.implement_width_m, threshold_ratio=edge_ratio_threshold)
    angle2 = angle0 + 180.0
    second_local = build_open_polylines_for_components(uncovered1, spacing0, angle2, factor_min=0.6, factor_max=1.1)

    # 决定外环方向
    if orientation.lower() == 'auto':
        from scan_utils import choose_boundary_orientation_by_far_vertex
        anchor = list(primary_local.coords)[-1]
        ori = choose_boundary_orientation_by_far_vertex(work_area, anchor)
    else:
        ori = orientation
    # 沿外环连接
    connected_local = connect_polylines_along_outer_boundary(work_area, primary_local, second_local, orientation=ori)

    # 若 parcel 定义了出入口，则将“入口 -> 路径起点”和“路径终点 -> 出口”沿外环连接
    entry_local = None
    exit_local = None
    entries = parcel.get('entries', [])
    if entries:
        # 选择入口：优先 type=='main' 的第一个，否则第一个
        main_entries = [e for e in entries if (e.get('type') or '').lower() == 'main']
        entry = main_entries[0] if main_entries else entries[0]
        t_local = wgs84_to_local_transformer(parcel['outer'][0][0], parcel['outer'][0][1])
        entry_local = t_local.transform(entry['lon'], entry['lat'])
        # 选择出口：若存在多个，则取与入口“在外环上最远”的一个；否则沿用同一个
        if len(entries) >= 2:
            from shapely.geometry import Point
            # 构造外环线并计算环距
            largest = work_area if isinstance(work_area, Polygon) else max(work_area.geoms, key=lambda p: p.area)
            ring = LineString(list(largest.exterior.coords) + [largest.exterior.coords[0]])
            d_entry = ring.project(Point(entry_local))
            def ring_dist(lp):
                p_local = t_local.transform(lp['lon'], lp['lat'])
                d = ring.project(Point(p_local))
                # 最远 = max(min(|d - d_entry|, L - |d - d_entry|))
                import math
                L = ring.length
                delta = abs(d - d_entry)
                return max(delta, L - delta)
            # 选择最远的一个作为出口（避免入口与出口过近）
            other_candidates = [e for e in entries if e is not entry]
            exit_e = max(other_candidates, key=ring_dist)
            exit_local = t_local.transform(exit_e['lon'], exit_e['lat'])
        else:
            exit_local = entry_local

        connected_local = connect_path_with_entry_exit_along_outer_boundary(
            work_area, connected_local, entry_local=entry_local, exit_local=exit_local,
            orientation_entry='auto', orientation_exit='auto'
        )

    # 转 WGS84
    t_wgs = local_to_wgs84_transformer(ref_lon, ref_lat)
    work_area_wgs = _to_wgs_geometry(t_wgs, work_area)
    connected_wgs = _to_wgs_geometry(t_wgs, connected_local)

    # 绘图
    plt.figure(figsize=(8, 8), dpi=120)
    ax = plt.gca()
    ax.set_aspect('equal')
    ax.set_title('安全区域 + 两遍折线沿外环连接 + 入口/终点外环连接', fontsize=12)

    # 原始外环/孔洞/点障碍
    if parcel['outer']:
        lons, lats = zip(*parcel['outer'])
        ax.plot(lons + (lons[0],), lats + (lats[0],), color='blue', linewidth=1.5, label='原始外环')
    for h in parcel['holes']:
        if len(h) >= 3:
            hlons, hlats = zip(*h)
            ax.plot(hlons + (hlons[0],), hlats + (hlats[0],), color='red', linewidth=1.0, label='原始孔洞')
    for (lon, lat, diam) in parcel['points']:
        ax.plot(lon, lat, 'o', color='orange', markersize=4, label='点障碍')
    # 出入口标记（紫色）
    for e in parcel.get('entries', []):
        ax.plot(e['lon'], e['lat'], 'o', color='purple', markersize=5, label='出入口')

    # 安全区域填充
    def draw_poly(poly: Polygon):
        ext = list(poly.exterior.coords)
        elons = [p[0] for p in ext]
        elats = [p[1] for p in ext]
        ax.fill(elons, elats, facecolor='palegreen', alpha=0.4, edgecolor='green', linewidth=1.2, label='安全区域')
        for hole in poly.interiors:
            h = list(hole.coords)
            hlons = [p[0] for p in h]
            hlats = [p[1] for p in h]
            ax.fill(hlons, hlats, facecolor='white', edgecolor='none', zorder=3)
    if isinstance(work_area_wgs, MultiPolygon):
        for poly in work_area_wgs.geoms:
            draw_poly(poly)
    else:
        draw_poly(work_area_wgs)

    # 绘制连接后的单条路径（酒红色）
    if not connected_wgs.is_empty:
        xs = [p[0] for p in connected_wgs.coords]
        ys = [p[1] for p in connected_wgs.coords]
        ax.plot(xs, ys, '-', color='firebrick', linewidth=2.0, alpha=0.95, label='两遍折线（沿外环连接）')

    # 范围（外环包围盒）
    if parcel['outer']:
        min_lon = min(p[0] for p in parcel['outer'])
        max_lon = max(p[0] for p in parcel['outer'])
        min_lat = min(p[1] for p in parcel['outer'])
        max_lat = max(p[1] for p in parcel['outer'])
        pad_lon = (max_lon - min_lon) * 0.05
        pad_lat = (max_lat - min_lat) * 0.05
        ax.set_xlim(min_lon - pad_lon, max_lon + pad_lon)
        ax.set_ylim(min_lat - pad_lat, max_lat + pad_lat)

    ax.legend(loc='upper right', fontsize=8)
    plt.tight_layout()
    plt.savefig(SAFE_SECOND_POLYLINE_CONNECTED_IMG, dpi=300, bbox_inches='tight')
    plt.close()
    print(f"已生成两遍折线沿外环连接图片: {SAFE_SECOND_POLYLINE_CONNECTED_IMG}")
    # 追加：输出经纬度TXT（8位小数）
    try:
        export_linestring_local_to_wgs84_txt(
            connected_local,
            ref_lon,
            ref_lat,
            SAFE_SECOND_POLYLINE_CONNECTED_TXT,
            precision=8
        )
        print(f"已输出两遍折线沿外环连接经纬度TXT: {SAFE_SECOND_POLYLINE_CONNECTED_TXT}")
    except Exception as e:
        print(f"输出经纬度TXT失败: {e}")
    return True


def visualize_safe_area_uncovered(parcel: Dict, cfg: VehicleConfig, include_connectors: bool = False,
                                  apply_edge_filter: bool = True, edge_ratio_threshold: float = 0.6) -> bool:
    """生成未覆盖区域图像：安全区域减去裁切后线段缓冲覆盖带。"""
    print("计算未覆盖区域...")
    work_area, (ref_lon, ref_lat) = build_safe_area(parcel, cfg)
    if work_area.is_empty:
        print("安全作业区域为空，退出。")
        return False
    angle = compute_job_direction(work_area)
    spacing = cfg.effective_row_spacing
    # 改为基于“实际首遍路径”的覆盖计算：仅计入水平作业段（可选包含竖段）
    primary_local = build_open_polyline(work_area, spacing, angle)
    horizontal_only = not include_connectors  # 若需要包含连线，则允许非水平段参与覆盖
    covered, uncovered = compute_coverage_areas_from_path(work_area, primary_local, spacing, angle, cfg.implement_width_m, horizontal_only=horizontal_only)
    # 应用边界带过滤：剔除“超过阈值比例位于边界带”的未覆盖组件
    if apply_edge_filter:
        filtered_uncovered = filter_uncovered_by_edge_zone(uncovered, work_area, cfg.implement_width_m, threshold_ratio=edge_ratio_threshold)
    else:
        filtered_uncovered = uncovered

    # 转到 WGS84 用于绘制
    t_wgs = local_to_wgs84_transformer(ref_lon, ref_lat)
    work_area_wgs = _to_wgs_geometry(t_wgs, work_area)
    covered_wgs = _to_wgs_geometry(t_wgs, covered)
    uncovered_wgs = _to_wgs_geometry(t_wgs, filtered_uncovered)

    # 准备绘图
    plt.figure(figsize=(8, 8), dpi=120)
    ax = plt.gca()
    ax.set_aspect('equal')
    ax.set_title('安全区域 + 覆盖/未覆盖', fontsize=12)

    # 原始外环/孔洞/点障碍
    if parcel['outer']:
        lons, lats = zip(*parcel['outer'])
        ax.plot(lons + (lons[0],), lats + (lats[0],), color='blue', linewidth=1.5, label='原始外环')
    for h in parcel['holes']:
        if len(h) >= 3:
            hlons, hlats = zip(*h)
            ax.plot(hlons + (hlons[0],), hlats + (hlats[0],), color='red', linewidth=1.0, label='原始孔洞')
    for (lon, lat, diam) in parcel['points']:
        ax.plot(lon, lat, 'o', color='orange', markersize=4, label='点障碍')

    # 安全区域填充
    def draw_poly(poly: Polygon):
        ext = list(poly.exterior.coords)
        elons = [p[0] for p in ext]
        elats = [p[1] for p in ext]
        ax.fill(elons, elats, facecolor='palegreen', alpha=0.4, edgecolor='green', linewidth=1.2, label='安全区域')
        for hole in poly.interiors:
            h = list(hole.coords)
            hlons = [p[0] for p in h]
            hlats = [p[1] for p in h]
            ax.fill(hlons, hlats, facecolor='white', edgecolor='none', zorder=3)
    if isinstance(work_area_wgs, MultiPolygon):
        for poly in work_area_wgs.geoms:
            draw_poly(poly)
    else:
        draw_poly(work_area_wgs)

    # 覆盖区域（浅蓝填充）
    def draw_area(geom, color, label, alpha=0.5):
        if isinstance(geom, MultiPolygon):
            geoms = geom.geoms
        else:
            geoms = [geom]
        for poly in geoms:
            ext = list(poly.exterior.coords)
            xs = [p[0] for p in ext]
            ys = [p[1] for p in ext]
            ax.fill(xs, ys, facecolor=color, alpha=alpha, edgecolor='none', label=label)

    draw_area(covered_wgs, 'skyblue', '覆盖区域', alpha=0.5)
    draw_area(uncovered_wgs, 'salmon', '未覆盖区域(过滤后)', alpha=0.6)

    # 范围（外环包围盒）
    if parcel['outer']:
        min_lon = min(p[0] for p in parcel['outer'])
        max_lon = max(p[0] for p in parcel['outer'])
        min_lat = min(p[1] for p in parcel['outer'])
        max_lat = max(p[1] for p in parcel['outer'])
        pad_lon = (max_lon - min_lon) * 0.05
        pad_lat = (max_lat - min_lat) * 0.05
        ax.set_xlim(min_lon - pad_lon, max_lon + pad_lon)
        ax.set_ylim(min_lat - pad_lat, max_lat + pad_lat)

    ax.legend(loc='upper right', fontsize=8)
    plt.tight_layout()
    plt.savefig(SAFE_UNCOVERED_IMG, dpi=300, bbox_inches='tight')
    plt.close()
    print(f"已生成未覆盖区域图片: {SAFE_UNCOVERED_IMG}")
    return True