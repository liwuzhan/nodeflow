#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
扫描工具模块

包含射线生成、垂直连接和裁切相关功能。
"""

from typing import List, Tuple, Optional, Union

from shapely.geometry import Polygon, LineString, MultiPolygon
from shapely.ops import unary_union
from shapely.affinity import rotate
from shapely.geometry import Point
import math
import math


def _is_vertical_corridor(rot_area: Union[Polygon, MultiPolygon], x: float, y0: float, y1: float) -> bool:
    """检查在旋转坐标系下，x 处从 y0 到 y1 的竖直线段是否完全处于区域内（含边界）。"""
    line = LineString([(x, y0), (x, y1)])
    try:
        return rot_area.covers(line)
    except Exception:
        # MultiPolygon 情形：分片检查（要求任何一个片区能完全覆盖该直线）
        if isinstance(rot_area, MultiPolygon):
            return any(p.covers(line) for p in rot_area.geoms)
        return False


def _clamp(x: float, a: float, b: float) -> float:
    """将值限制在指定范围内。"""
    return max(a, min(b, x))


def _find_vertical_x_near_endpoint(rot_area: Union[Polygon, MultiPolygon], y0: float, y1: float,
                                   x_start: float, x_min: float, x_max: float,
                                   step: float, prefer_left: bool) -> Optional[float]:
    """
    在允许区间 [x_min, x_max] 内，从靠近端点的 x_start 开始，沿端点另一侧方向（prefer_left 决定）
    逐步搜索一个能形成竖直通道（完全覆盖于 rot_area 内）的 x；尽量靠近端点。
    """
    if x_min > x_max:
        return None
    x0 = _clamp(x_start, x_min, x_max)
    # 先尝试端点处
    if _is_vertical_corridor(rot_area, x0, y0, y1):
        return x0
    # 再向内逐步搜索（只在允许区间内）
    if prefer_left:
        x = x0
        while x >= x_min:
            x -= step
            if x < x_min:
                break
            if _is_vertical_corridor(rot_area, x, y0, y1):
                return x
    else:
        x = x0
        while x <= x_max:
            x += step
            if x > x_max:
                break
            if _is_vertical_corridor(rot_area, x, y0, y1):
                return x
    return None


def generate_rays_first_contact(work_area: Union[Polygon, MultiPolygon], spacing_m: float, angle_deg: float) -> List[LineString]:
    """
    在旋转坐标系下（长边方向对齐 X 轴），沿长边方向发射平行射线，
    每条射线与区域的交集可能为多个线段，仅保留"从外环进入的首段"。
    返回：已回转到原坐标系的线段列表。
    """
    # 统一为单个多边形进行扫描
    if isinstance(work_area, MultiPolygon):
        area = unary_union([p for p in work_area.geoms])
    else:
        area = work_area
    # 旋转到 X 轴对齐长边方向
    rot_area = rotate(area, -angle_deg, origin=(0, 0), use_radians=False)
    minx, miny, maxx, maxy = rot_area.bounds
    extra = (maxx - minx + maxy - miny) * 0.5 + 10.0
    rays_rot: List[LineString] = []
    y = miny
    while y <= maxy:
        scan_line = LineString([(minx - extra, y), (maxx + extra, y)])
        inter = rot_area.intersection(scan_line)
        segs: List[LineString] = []
        if isinstance(inter, LineString):
            segs = [inter]
        elif hasattr(inter, 'geoms'):
            segs = [g for g in inter.geoms if isinstance(g, LineString)]
        # 仅保留"首段"（按起点最小 x 排序取第一段）
        if segs:
            def seg_min_x(s: LineString) -> float:
                xs = [p[0] for p in s.coords]
                return min(xs) if xs else float('inf')
            segs.sort(key=seg_min_x)
            rays_rot.append(segs[0])
        y += spacing_m
    # 回转到原角度
    rays = [rotate(s, angle_deg, origin=(0, 0), use_radians=False) for s in rays_rot]
    # 过滤掉短于行距的线段
    short_tol = max(1e-9, spacing_m * 1e-6)
    rays = [ln for ln in rays if ln.length >= (spacing_m - short_tol)]
    return rays


def connect_rays_vertical(work_area: Union[Polygon, MultiPolygon], spacing_m: float, angle_deg: float) -> List[LineString]:
    """
    规则生成连线：
    - 在旋转坐标系下，按 y 递增顺序连接相邻"首段射线"线段；连线为垂直（长度等于行距）。
    - 从最外侧的线段开始，在其端点处尝试连接下一线段；若端点 x 不可用，则沿线段向内退着找（只在两段 x 重叠区间内）。
    - 连线尽可能靠近端点，且必须完全处于安全区域内，不穿越边界/孔洞。
    - 若两段在垂直方向的投影（此处指 x 范围）没有重合，则跳过该连接。
    返回：已回转到原坐标系的连线列表。
    """
    # 统一为单个多边形并旋转到作业坐标系
    area = unary_union([p for p in work_area.geoms]) if isinstance(work_area, MultiPolygon) else work_area
    rot_area = rotate(area, -angle_deg, origin=(0, 0), use_radians=False)
    minx, miny, maxx, maxy = rot_area.bounds
    extra = (maxx - minx + maxy - miny) * 0.5 + 10.0

    # 先生成每条扫描线的首段（旋转坐标系下），并记录其 x 范围与 y 值
    segs: List[Tuple[float, float, float]] = []  # (y, xmin, xmax)
    y = miny
    while y <= maxy:
        scan_line = LineString([(minx - extra, y), (maxx + extra, y)])
        inter = rot_area.intersection(scan_line)
        line_segs: List[LineString] = []
        if isinstance(inter, LineString):
            line_segs = [inter]
        elif hasattr(inter, 'geoms'):
            line_segs = [g for g in inter.geoms if isinstance(g, LineString)]
        if line_segs:
            # 取"首段"（最小 x 起点）
            def seg_min_x(s: LineString) -> float:
                xs = [p[0] for p in s.coords]
                return min(xs) if xs else float('inf')
            line_segs.sort(key=seg_min_x)
            s = line_segs[0]
            xs = [p[0] for p in s.coords]
            if not xs:
                continue
            xmin = min(xs)
            xmax = max(xs)
            segs.append((y, xmin, xmax))
        y += spacing_m

    # 相邻段之间生成竖直连线（长度等于 spacing_m），端点交替（之字形）
    connectors_rot: List[LineString] = []
    use_right_end = True  # 从第一段的"内侧"端开始（通常为右端）
    step = max(0.1, spacing_m / 30.0)
    for i in range(len(segs) - 1):
        y0, x0_min, x0_max = segs[i]
        y1, x1_min, x1_max = segs[i + 1]
        # x 重叠区间决定可连通的竖直线集合
        ov_min = max(x0_min, x1_min)
        ov_max = min(x0_max, x1_max)
        if ov_min >= ov_max:
            # 无可连接区间，跳过
            use_right_end = not use_right_end
            continue
        # 端点选择与搜索方向
        if use_right_end:
            x_pref = x0_max
            prefer_left = True
        else:
            x_pref = x0_min
            prefer_left = False
        x_conn = _find_vertical_x_near_endpoint(rot_area, y0, y1, x_pref, ov_min, ov_max, step, prefer_left)
        if x_conn is not None:
            ln = LineString([(x_conn, y0), (x_conn, y1)])
            # 再次保险校验覆盖
            if _is_vertical_corridor(rot_area, x_conn, y0, y1):
                connectors_rot.append(ln)
        # 交替端点
        use_right_end = not use_right_end

    # 根据裁切后的行长度，过滤掉与“短行”关联的连线
    # 计算每一行的裁切端点（与 trim_rays_by_connectors 逻辑一致）
    rows: List[dict] = []
    for (y0, xmin, xmax) in segs:
        rows.append({'y': y0, 'xmin': xmin, 'xmax': xmax})
    for row in rows:
        y0 = row['y']
        xmin = row['xmin']
        xmax = row['xmax']
        xints: List[float] = []
        for c in connectors_rot:
            minx_c, miny_c, maxx_c, maxy_c = c.bounds
            if (miny_c - 1e-7) <= y0 <= (maxy_c + 1e-7):
                x_c = (minx_c + maxx_c) * 0.5
                if xmin - 1e-7 <= x_c <= xmax + 1e-7:
                    xints.append(x_c)
        xints = sorted(set(round(x, 7) for x in xints))
        if len(xints) >= 2:
            xl = xints[0]
            xr = xints[-1]
        elif len(xints) == 1:
            x = xints[0]
            left_len = abs(x - xmin)
            right_len = abs(xmax - x)
            if right_len >= left_len:
                xl, xr = x, xmax
            else:
                xl, xr = xmin, x
            # 修正逻辑错误：如果只有一个交点，xl, xr 应该基于交点和端点确定
            # 但这里逻辑似乎有点复杂，保持原逻辑
            pass
        else:
            xl, xr = xmin, xmax
        if xl > xr:
            xl, xr = xr, xl
        row['xl'] = xl
        row['xr'] = xr

    # 标记短行并过滤与之相邻的竖直连线
    short_tol = max(1e-9, spacing_m * 1e-6)
    eps_y = max(1e-6, spacing_m * 1e-6)
    dropped_idx = set()
    for idx, row in enumerate(rows):
        if abs(row['xr'] - row['xl']) < (spacing_m - short_tol):
            dropped_idx.add(idx)

    filtered_connectors_rot: List[LineString] = []
    for c in connectors_rot:
        minx_c, miny_c, maxx_c, maxy_c = c.bounds
        i = None
        j = None
        for idx, row in enumerate(rows):
            if abs(row['y'] - miny_c) <= eps_y:
                i = idx
            if abs(row['y'] - maxy_c) <= eps_y:
                j = idx
        if i is not None and j is not None and j == i + 1:
            if (i not in dropped_idx) and (j not in dropped_idx):
                filtered_connectors_rot.append(c)

    # 回转到原坐标系
    connectors = [rotate(s, angle_deg, origin=(0, 0), use_radians=False) for s in filtered_connectors_rot]
    return connectors


def trim_rays_by_connectors(work_area: Union[Polygon, MultiPolygon], spacing_m: float, angle_deg: float) -> List[LineString]:
    """
    使用生成的垂直连线裁切掉水平射线的多余部分。
    """
    # 统一为单个多边形并旋转到作业坐标系
    area = unary_union([p for p in work_area.geoms]) if isinstance(work_area, MultiPolygon) else work_area
    rot_area = rotate(area, -angle_deg, origin=(0, 0), use_radians=False)
    minx, miny, maxx, maxy = rot_area.bounds
    extra = (maxx - minx + maxy - miny) * 0.5 + 10.0

    # 扫描生成"首段射线"（旋转坐标系下）
    rays_rot: List[Tuple[float, LineString]] = []  # (y, segment)
    y = miny
    while y <= maxy:
        scan_line = LineString([(minx - extra, y), (maxx + extra, y)])
        inter = rot_area.intersection(scan_line)
        line_segs: List[LineString] = []
        if isinstance(inter, LineString):
            line_segs = [inter]
        elif hasattr(inter, 'geoms'):
            line_segs = [g for g in inter.geoms if isinstance(g, LineString)]
        if line_segs:
            # 取"首段"（最小 x 起点）
            def seg_min_x(s: LineString) -> float:
                xs = [p[0] for p in s.coords]
                return min(xs) if xs else float('inf')
            line_segs.sort(key=seg_min_x)
            s = line_segs[0]
            rays_rot.append((y, s))
        y += spacing_m

    # 生成连线并回转至旋转坐标系以便快速求交
    connectors_local = connect_rays_vertical(work_area, spacing_m, angle_deg)
    connectors_rot = [rotate(ln, -angle_deg, origin=(0, 0), use_radians=False) for ln in connectors_local]

    # 裁切每条射线
    trimmed_rot: List[LineString] = []
    for (y0, s) in rays_rot:
        xs = [p[0] for p in s.coords]
        if not xs:
            continue
        xmin = min(xs)
        xmax = max(xs)
        # 收集与此 y0 相交的连线 x 位置
        xints: List[float] = []
        for c in connectors_rot:
            minx_c, miny_c, maxx_c, maxy_c = c.bounds
            # 纵向覆盖 y0，且 x 在射线范围内
            if (miny_c - 1e-7) <= y0 <= (maxy_c + 1e-7):
                x_c = (minx_c + maxx_c) * 0.5  # 竖线的 x
                if xmin - 1e-7 <= x_c <= xmax + 1e-7:
                    xints.append(x_c)
        # 去重与排序
        xints = sorted(set(round(x, 7) for x in xints))
        # 根据交点数量裁切
        if len(xints) >= 2:
            # 保留两个交点之间的部分（取最左与最右）
            xl = xints[0]
            xr = xints[-1]
            trimmed_rot.append(LineString([(xl, y0), (xr, y0)]))
        elif len(xints) == 1:
            x = xints[0]
            left_len = abs(x - xmin)
            right_len = abs(xmax - x)
            if right_len >= left_len:
                trimmed_rot.append(LineString([(x, y0), (xmax, y0)]))
            else:
                trimmed_rot.append(LineString([(xmin, y0), (x, y0)]))
        else:
            # 无交点，保持原样
            trimmed_rot.append(s)

    # 回转到原坐标系并过滤短于行距的线段
    trimmed = [rotate(s, angle_deg, origin=(0, 0), use_radians=False) for s in trimmed_rot]
    short_tol = max(1e-9, spacing_m * 1e-6)
    trimmed = [ln for ln in trimmed if ln.length >= (spacing_m - short_tol)]
    return trimmed


def build_open_polyline(work_area: Union[Polygon, MultiPolygon], spacing_m: float, angle_deg: float) -> LineString:
    """
    构建首遍开放折线，但仅保留“最长的连续链”。
    """
    area = unary_union([p for p in work_area.geoms]) if isinstance(work_area, MultiPolygon) else work_area
    rot_area = rotate(area, -angle_deg, origin=(0, 0), use_radians=False)
    minx, miny, maxx, maxy = rot_area.bounds
    extra = (maxx - minx + maxy - miny) * 0.5 + 10.0

    # 生成每条扫描线的首段（旋转坐标系下）
    rows: List[dict] = []
    y = miny
    while y <= maxy + 1e-9:
        scan_line = LineString([(minx - extra, y), (maxx + extra, y)])
        inter = rot_area.intersection(scan_line)
        line_segs: List[LineString] = []
        if isinstance(inter, LineString):
            line_segs = [inter]
        elif hasattr(inter, 'geoms'):
            line_segs = [g for g in inter.geoms if isinstance(g, LineString)]
        if line_segs:
            def seg_min_x(s: LineString) -> float:
                xs = [p[0] for p in s.coords]
                return min(xs)
            line_segs.sort(key=seg_min_x)
            s = line_segs[0]
            xs = [p[0] for p in s.coords]
            xmin = min(xs)
            xmax = max(xs)
            rows.append({'y': y, 'segment': s, 'xmin': xmin, 'xmax': xmax})
        y += spacing_m

    if not rows:
        return LineString([])

    # 生成竖直连线并转到旋转坐标系以便匹配
    connectors_local = connect_rays_vertical(work_area, spacing_m, angle_deg)
    connectors_rot = [rotate(ln, -angle_deg, origin=(0, 0), use_radians=False) for ln in connectors_local]

    # 为每行计算与之相交的连线 x，得到裁切端点
    for row in rows:
        y0 = row['y']
        xmin = row['xmin']
        xmax = row['xmax']
        xints: List[float] = []
        for c in connectors_rot:
            minx_c, miny_c, maxx_c, maxy_c = c.bounds
            if (miny_c - 1e-7) <= y0 <= (maxy_c + 1e-7):
                x_c = (minx_c + maxx_c) * 0.5
                if xmin - 1e-7 <= x_c <= xmax + 1e-7:
                    xints.append(x_c)
        xints = sorted(set(round(x, 7) for x in xints))
        if len(xints) >= 2:
            xl = xints[0]
            xr = xints[-1]
        elif len(xints) == 1:
            x = xints[0]
            left_len = abs(x - xmin)
            right_len = abs(xmax - x)
            if right_len >= left_len:
                xl, xr = x, xmax
            else:
                xl, xr = xmin, x
        else:
            xl, xr = xmin, xmax
        if xl > xr:
            xl, xr = xr, xl
        row['xl'] = xl
        row['xr'] = xr

    # 将相邻行的连线 x 记录为 pair -> x
    ys = [row['y'] for row in rows]
    eps_y = max(1e-6, spacing_m * 1e-6)
    pair_conn_x: dict[int, float] = {}
    for c in connectors_rot:
        minx_c, miny_c, maxx_c, maxy_c = c.bounds
        x_c = (minx_c + maxx_c) * 0.5
        i = None
        j = None
        for idx, yv in enumerate(ys):
            if abs(yv - miny_c) <= eps_y:
                i = idx
            if abs(yv - maxy_c) <= eps_y:
                j = idx
        if i is not None and j is not None and j == i + 1:
            pair_conn_x[i] = x_c

    # 丢弃短行
    short_tol = max(1e-9, spacing_m * 1e-6)
    dropped_indices = set()
    for idx, row in enumerate(rows):
        row_len = abs(row['xr'] - row['xl'])
        if row_len < (spacing_m - short_tol):
            dropped_indices.add(idx)
            row['drop'] = True
    for di in dropped_indices:
        if di in pair_conn_x:
            try:
                del pair_conn_x[di]
            except KeyError:
                pass
        prev_key = di - 1
        if prev_key in pair_conn_x:
            try:
                del pair_conn_x[prev_key]
            except KeyError:
                pass

    # 组装开放折线为“多条链”
    chains_pts_rot: List[List[Tuple[float, float]]] = []
    cur_pts: List[Tuple[float, float]] = []

    def append_pt(pt: Tuple[float, float]):
        if not cur_pts or (abs(cur_pts[-1][0] - pt[0]) > 1e-9 or abs(cur_pts[-1][1] - pt[1]) > 1e-9):
            cur_pts.append(pt)

    n = len(rows)
    for i, row in enumerate(rows):
        if row.get('drop'):
            if len(cur_pts) >= 2:
                chains_pts_rot.append(cur_pts)
            cur_pts = []
            continue
        y0 = row['y']
        xl = row['xl']
        xr = row['xr']
        x_prev = pair_conn_x.get(i - 1)
        x_next = pair_conn_x.get(i)

        if not cur_pts:
            if x_prev is None and x_next is None:
                start_x, end_x = xl, xr
            elif x_prev is None and x_next is not None:
                start_x = xr if abs(xl - x_next) <= 1e-7 else xl
                end_x = x_next
            elif x_prev is not None and x_next is None:
                start_x = x_prev
                end_x = (xl if abs(start_x - xr) <= 1e-7 else xr)
            else:
                start_x, end_x = x_prev, x_next
            if start_x <= end_x:
                append_pt((start_x, y0))
                append_pt((end_x, y0))
            else:
                append_pt((start_x, y0))
                append_pt((end_x, y0))
            if x_next is not None and i < n - 1:
                append_pt((x_next, rows[i + 1]['y']))
            else:
                if len(cur_pts) >= 2:
                    chains_pts_rot.append(cur_pts)
                cur_pts = []
            continue

        if x_prev is None:
            if len(cur_pts) >= 2:
                chains_pts_rot.append(cur_pts)
            cur_pts = []
            if x_next is None:
                append_pt((xl, y0))
                append_pt((xr, y0))
                chains_pts_rot.append(cur_pts)
                cur_pts = []
            else:
                start_x = xr if abs(xl - x_next) <= 1e-7 else xl
                end_x = x_next
                if start_x <= end_x:
                    append_pt((start_x, y0))
                    append_pt((end_x, y0))
                else:
                    append_pt((start_x, y0))
                    append_pt((end_x, y0))
                append_pt((x_next, rows[i + 1]['y']))
            continue

        # 已在链中，仅处理当前行水平段及下一竖线
        last_pt = cur_pts[-1]
        if abs(last_pt[0] - x_prev) > 1e-7:
            # 理论上不会发生，除非竖线倾斜
            append_pt((x_prev, y0))
        
        # 确定本行终点
        if x_next is None:
            target_x = (xl if abs(x_prev - xr) <= 1e-7 else xr)
        else:
            target_x = x_next
        
        append_pt((target_x, y0))
        
        if x_next is not None and i < n - 1:
            append_pt((x_next, rows[i + 1]['y']))
        else:
            if len(cur_pts) >= 2:
                chains_pts_rot.append(cur_pts)
            cur_pts = []

    if len(cur_pts) >= 2:
        chains_pts_rot.append(cur_pts)

    if not chains_pts_rot:
        return LineString([])
    
    # 返回最长的一条链
    longest_chain = max(chains_pts_rot, key=lambda pts: LineString(pts).length)
    chain_ls = LineString(longest_chain)
    return rotate(chain_ls, angle_deg, origin=(0, 0), use_radians=False)


def compute_coverage_areas_from_path(work_area: Union[Polygon, MultiPolygon],
                                     path: LineString,
                                     spacing_m: float,
                                     angle_deg: float,
                                     width_m: float,
                                     horizontal_only: bool = True) -> Tuple[Union[Polygon, MultiPolygon], Union[Polygon, MultiPolygon]]:
    """
    根据路径计算覆盖区域和未覆盖区域。
    """
    if not path or path.is_empty:
        return Polygon(), work_area

    # 旋转路径以判断"水平"
    path_rot = rotate(path, -angle_deg, origin=(0, 0), use_radians=False)
    coords = list(path_rot.coords)
    lines = []
    for i in range(len(coords) - 1):
        p1 = coords[i]
        p2 = coords[i + 1]
        dx = abs(p2[0] - p1[0])
        dy = abs(p2[1] - p1[1])
        # 判定是否为水平作业段（dy 很小）
        is_horz = (dy < 1e-3)
        if horizontal_only and not is_horz:
            continue
        # 构造原始坐标系下的线段
        seg_rot = LineString([p1, p2])
        seg = rotate(seg_rot, angle_deg, origin=(0, 0), use_radians=False)
        lines.append(seg)
    
    if not lines:
        return Polygon(), work_area
    
    # 对每段作业路径进行缓冲（宽度的一半）
    buffers = [ln.buffer(width_m * 0.5) for ln in lines]
    covered_union = unary_union(buffers)
    
    # 限制在安全区域内
    area = unary_union([p for p in work_area.geoms]) if isinstance(work_area, MultiPolygon) else work_area
    covered_in_area = covered_union.intersection(area)
    uncovered = area.difference(covered_in_area)
    
    return covered_in_area, uncovered


def filter_uncovered_by_edge_zone(uncovered: Union[Polygon, MultiPolygon],
                                  work_area: Union[Polygon, MultiPolygon],
                                  width_m: float,
                                  threshold_ratio: float = 0.6) -> Union[Polygon, MultiPolygon]:
    """
    过滤掉主要位于"边缘带"的未覆盖区域组件。
    """
    if uncovered.is_empty:
        return uncovered
    
    area = unary_union([p for p in work_area.geoms]) if isinstance(work_area, MultiPolygon) else work_area
    # 边缘带：外边界向内 width_m 范围
    # 注意：work_area 已经是内缩过的，这里的边缘带是指"作业区域边缘"
    # 或者理解为：如果未覆盖区域紧贴着作业边界，且很窄，则忽略
    # 这里定义边缘带为：作业区域向内 0.5 * width_m 的环
    inner_safe = area.buffer(-width_m * 0.5)
    edge_zone = area.difference(inner_safe)
    
    geoms = uncovered.geoms if isinstance(uncovered, MultiPolygon) else [uncovered]
    kept = []
    for g in geoms:
        if g.is_empty:
            continue
        g_area = g.area
        if g_area < 1e-6:
            continue
        in_edge = g.intersection(edge_zone).area
        ratio = in_edge / g_area
        if ratio < threshold_ratio:
            kept.append(g)
            
    return unary_union(kept)


def select_even_row_spacing(poly: Polygon, angle_deg: float, min_spacing: float, max_spacing: float) -> Optional[float]:
    """
    为多边形选择一个行距，使得在该角度下覆盖该多边形的行数为偶数。
    """
    rot_poly = rotate(poly, -angle_deg, origin=(0, 0), use_radians=False)
    minx, miny, maxx, maxy = rot_poly.bounds
    height = maxy - miny
    if height < 1e-3:
        return None

    # 尝试寻找最佳行距 s，使得 height ~= k * s，且 k 为偶数
    # k = height / s => s = height / k
    # min_spacing <= height / k <= max_spacing
    # height / max_spacing <= k <= height / min_spacing
    k_min = math.ceil(height / max_spacing)
    k_max = math.floor(height / min_spacing)

    best_s = None
    # 优先找偶数 k
    for k in range(k_min, k_max + 1):
        if k % 2 == 0 and k > 0:
            s = height / k
            # 偏好接近 (min+max)/2 的
            best_s = s
            break # 找到一个即可
            
    # 如果找不到偶数 k，尝试退而求其次（这里简单返回 None 或默认值）
    # 或者强制使用偶数行（可能超出 max_spacing 稍微一点？）
    if best_s is None:
        # 尝试强制偶数
        k_target = k_min if k_min % 2 == 0 else k_min + 1
        s = height / k_target
        if s > 0:
            best_s = s

    return best_s


def build_open_polylines_for_components(uncovered: Union[Polygon, MultiPolygon],
                                        base_spacing: float,
                                        angle_deg: float,
                                        factor_min: float = 0.6,
                                        factor_max: float = 1.1) -> List[LineString]:
    """
    对未覆盖区域的每个组件，计算自适应偶数行距，并生成开放折线。
    """
    geoms = uncovered.geoms if isinstance(uncovered, MultiPolygon) else [uncovered]
    res = []
    for g in geoms:
        if g.is_empty:
            continue
        s = select_even_row_spacing(g, angle_deg, base_spacing * factor_min, base_spacing * factor_max)
        if s is None:
            s = base_spacing
        ln = build_open_polyline(g, s, angle_deg)
        if not ln.is_empty:
            res.append(ln)
    return res


def choose_boundary_orientation_by_far_vertex(work_area: Union[Polygon, MultiPolygon], anchor_pt: Tuple[float, float]) -> str:
    """
    根据锚点位置，选择外环方向（cw 或 ccw），使得"远端顶点"遍历顺序更优（启发式）。
    此处简化为：默认 'ccw' (逆时针)。
    """
    return 'ccw'


def _largest_polygon(area: Union[Polygon, MultiPolygon]) -> Polygon:
    if isinstance(area, MultiPolygon):
        polys = list(area.geoms)
        if not polys:
            from shapely.geometry import Polygon as _Polygon
            return _Polygon()
        polys.sort(key=lambda p: p.area, reverse=True)
        return polys[0]
    return area

def _ring_orientation(coords: List[Tuple[float, float]]) -> float:
    a = 0.0
    n = len(coords)
    for i in range(n - 1):
        x1, y1 = coords[i]
        x2, y2 = coords[i + 1]
        a += (x1 * y2 - x2 * y1)
    return a * 0.5

def _ensure_ring_orientation(coords: List[Tuple[float, float]], cw: bool) -> List[Tuple[float, float]]:
    if len(coords) >= 2 and coords[0] == coords[-1]:
        coords = coords[:-1]
    area_sign = _ring_orientation(coords + [coords[0]])
    want_ccw = not cw
    is_ccw = area_sign > 0
    if want_ccw == is_ccw:
        return coords
    else:
        return list(reversed(coords))

def _slice_line_by_distance(line: LineString, d0: float, d1: float) -> LineString:
    if d0 == d1:
        pt = line.interpolate(d0)
        return LineString([pt.coords[0], pt.coords[0]])
    if d0 > d1:
        d0, d1 = d1, d0
    coords = list(line.coords)
    segs: List[Tuple[Tuple[float, float], Tuple[float, float]]] = []
    for i in range(len(coords) - 1):
        segs.append((coords[i], coords[i + 1]))
    res: List[Tuple[float, float]] = []
    acc = 0.0
    started = False
    for (x0, y0), (x1, y1) in segs:
        seg_len = math.hypot(x1 - x0, y1 - y0)
        if seg_len <= 1e-12:
            continue
        seg_start = acc
        seg_end = acc + seg_len
        a = max(seg_start, d0)
        b = min(seg_end, d1)
        if a <= b + 1e-12:
            ra = (a - seg_start) / seg_len
            rb = (b - seg_start) / seg_len
            px_a = x0 + (x1 - x0) * ra
            py_a = y0 + (y1 - y0) * ra
            px_b = x0 + (x1 - x0) * rb
            py_b = y0 + (y1 - y0) * rb
            if not started:
                res.append((px_a, py_a))
                started = True
            else:
                if abs(res[-1][0] - px_a) > 1e-9 or abs(res[-1][1] - py_a) > 1e-9:
                    res.append((px_a, py_a))
            res.append((px_b, py_b))
        acc += seg_len
    if len(res) < 2:
        pt = line.interpolate(d0)
        return LineString([pt.coords[0], pt.coords[0]])
    return LineString(res)

def connect_polylines_along_outer_boundary(work_area: Union[Polygon, MultiPolygon],
                                           path1: LineString,
                                           paths2: List[LineString],
                                           orientation: str = 'cw') -> LineString:
    if not path1 or path1.is_empty:
        return LineString([])
    largest = _largest_polygon(work_area)
    ring_coords = list(largest.exterior.coords)
    cw = True if orientation.lower() == 'cw' else False
    oriented = _ensure_ring_orientation(ring_coords, cw)
    ring_line = LineString(oriented + [oriented[0]])
    L = ring_line.length
    def anchor_dist(pt_xy: Tuple[float, float]) -> float:
        return ring_line.project(Point(pt_xy))
    p1 = list(path1.coords)[-1]
    current_anchor = p1
    current_path: List[Tuple[float, float]] = []
    current_path.extend(list(path1.coords))
    remaining = [ln for ln in paths2 if ln and not ln.is_empty]
    while remaining:
        ca_d = anchor_dist(current_anchor)
        best = None
        best_delta = None
        best_start = None
        best_end = None
        for ln in remaining:
            a = list(ln.coords)[0]
            b = list(ln.coords)[-1]
            da = anchor_dist(a)
            db = anchor_dist(b)
            def delta(d):
                dd = d - ca_d
                if dd < 0:
                    dd += L
                return dd
            da_delta = delta(da)
            db_delta = delta(db)
            if da_delta <= db_delta:
                start_pt, end_pt, dsel = a, b, da_delta
            else:
                start_pt, end_pt, dsel = b, a, db_delta
            if best is None or dsel < best_delta:
                best = ln
                best_delta = dsel
                best_start = start_pt
                best_end = end_pt
        d0 = ca_d
        d1 = anchor_dist(best_start)
        seg = _slice_line_by_distance(ring_line, d0, d1) if d0 <= d1 else LineString(list(_slice_line_by_distance(ring_line, d0, L).coords) + list(_slice_line_by_distance(ring_line, 0.0, d1).coords))
        for xy in list(seg.coords):
            if not current_path or abs(current_path[-1][0] - xy[0]) > 1e-9 or abs(current_path[-1][1] - xy[1]) > 1e-9:
                current_path.append(xy)
        coords_ln = list(best.coords)
        if coords_ln[0] != best_start:
            coords_ln = list(reversed(coords_ln))
        for xy in coords_ln:
            if not current_path or abs(current_path[-1][0] - xy[0]) > 1e-9 or abs(current_path[-1][1] - xy[1]) > 1e-9:
                current_path.append(xy)
        current_anchor = best_end
        remaining.remove(best)
    if len(current_path) < 2:
        return LineString([])
    return LineString(current_path)


def connect_path_with_entry_exit_along_outer_boundary(work_area: Union[Polygon, MultiPolygon],
                                                      path: LineString,
                                                      entry_local: Tuple[float, float] = None,
                                                      exit_local: Tuple[float, float] = None,
                                                      orientation_entry: str = 'auto',
                                                      orientation_exit: str = 'auto') -> LineString:
    if not path or path.is_empty:
        return LineString([])
    largest = _largest_polygon(work_area)
    ring_coords = list(largest.exterior.coords)
    ring_line = LineString(ring_coords + [ring_coords[0]])
    L = ring_line.length
    def to_ring_point_and_dist(pt: Tuple[float, float]) -> Tuple[Tuple[float, float], float]:
        d = ring_line.project(Point(pt))
        p = ring_line.interpolate(d)
        return p.coords[0], d
    def slice_by_orientation(d0: float, d1: float, ori: str) -> LineString:
        def forward(d0_: float, d1_: float) -> LineString:
            if d0_ <= d1_:
                return _slice_line_by_distance(ring_line, d0_, d1_)
            else:
                a = _slice_line_by_distance(ring_line, d0_, L)
                b = _slice_line_by_distance(ring_line, 0.0, d1_)
                return LineString(list(a.coords) + list(b.coords))
        if ori.lower() in ('cw', 'clockwise'):
            return forward(d0, d1)
        if ori.lower() in ('ccw', 'counterclockwise'):
            seg = forward(d1, d0)
            return LineString(list(reversed(list(seg.coords))))
        def arc_len(d0_: float, d1_: float) -> float:
            return (d1_ - d0_) if (d1_ >= d0_) else (L - d0_ + d1_)
        cw_len = arc_len(d0, d1)
        ccw_len = L - cw_len
        return forward(d0, d1) if cw_len <= ccw_len else LineString(list(reversed(list(forward(d1, d0).coords))))
    coords = list(path.coords)
    if entry_local is not None and coords:
        entry_xy, de = to_ring_point_and_dist(entry_local)
        start_xy, ds = to_ring_point_and_dist(coords[0])
        seg = slice_by_orientation(de, ds, orientation_entry)
        pre: List[Tuple[float, float]] = []
        for xy in list(seg.coords):
            if not pre or abs(pre[-1][0] - xy[0]) > 1e-9 or abs(pre[-1][1] - xy[1]) > 1e-9:
                pre.append(xy)
        coords = pre + coords
    if exit_local is not None and coords:
        end_xy, dd = to_ring_point_and_dist(coords[-1])
        exit_xy, dx = to_ring_point_and_dist(exit_local)
        seg = slice_by_orientation(dd, dx, orientation_exit)
        post: List[Tuple[float, float]] = []
        for xy in list(seg.coords):
            if abs(coords[-1][0] - xy[0]) > 1e-9 or abs(coords[-1][1] - xy[1]) > 1e-9:
                post.append(xy)
        coords = coords + post
    if len(coords) < 2:
        return LineString([])
    return LineString(coords)


def choose_boundary_orientation_by_far_vertex(work_area: Union[Polygon, MultiPolygon], anchor_pt: Tuple[float, float]) -> str:
    largest = _largest_polygon(work_area)
    ring_coords = list(largest.exterior.coords)
    oriented_cw = _ensure_ring_orientation(ring_coords, cw=True)
    closed = oriented_cw + [oriented_cw[0]]
    ring_line = LineString(closed)
    L = ring_line.length
    d = ring_line.project(Point(anchor_pt))
    seg_starts: List[float] = [0.0]
    for i in range(len(closed) - 1):
        x0, y0 = closed[i]
        x1, y1 = closed[i + 1]
        seg_len = math.hypot(x1 - x0, y1 - y0)
        seg_starts.append(seg_starts[-1] + seg_len)
    k = 0
    for i in range(len(seg_starts) - 1):
        if seg_starts[i] <= d <= seg_starts[i + 1] + 1e-12:
            k = i
            break
    cw_dist = seg_starts[k + 1] - d
    ccw_dist = d - seg_starts[k]
    return 'cw' if cw_dist >= ccw_dist else 'ccw'
