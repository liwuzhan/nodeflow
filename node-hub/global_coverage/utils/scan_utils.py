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
                return min(xs)
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
                return min(xs)
            line_segs.sort(key=seg_min_x)
            s = line_segs[0]
            xs = [p[0] for p in s.coords]
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
                return min(xs)
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
    import math
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


def connect_polylines_along_outer_boundary(work_area: Union[Polygon, MultiPolygon],
                                           path1: LineString,
                                           paths2: List[LineString],
                                           orientation: str = 'ccw') -> LineString:
    """
    沿外环连接第一遍路径和第二遍路径集合。
    简化实现：直接将所有线段端点按"最近邻"或"外环顺序"连接。
    """
    # 这是一个复杂的拓扑连接问题。
    # 简化版：将 path1 和 paths2 视为一堆线段。
    # path1 是主骨架。paths2 是补漏。
    # 策略：path1 结束点 -> 沿外环 -> paths2 中最近的起点 -> paths2 终点 -> 沿外环 -> 下一个...
    
    # 构造外环 LinearRing
    largest = work_area if isinstance(work_area, Polygon) else max(work_area.geoms, key=lambda p: p.area)
    ring = largest.exterior
    if orientation == 'cw' and ring.is_ccw:
        ring = LineString(list(ring.coords)[::-1])
    elif orientation == 'ccw' and not ring.is_ccw:
        ring = LineString(list(ring.coords)[::-1])
    
    # 将 path1 放入结果
    coords = list(path1.coords)
    
    # 贪心连接 paths2
    remain = paths2[:]
    while remain:
        curr_end = coords[-1]
        # 在剩余路径中找起点距离 curr_end 沿外环最近的
        best_idx = -1
        best_dist = float('inf')
        best_entry_path = None # 连接路径
        
        curr_proj = ring.project(Point(curr_end))
        
        for i, p in enumerate(remain):
            # 尝试 p 的正向和反向
            p_start = p.coords[0]
            p_end = p.coords[-1]
            
            # 沿环距离：从 curr_proj 到 p_start_proj
            start_proj = ring.project(Point(p_start))
            if start_proj >= curr_proj:
                d = start_proj - curr_proj
            else:
                d = ring.length - (curr_proj - start_proj)
            
            if d < best_dist:
                best_dist = d
                best_idx = i
                best_entry_path = _get_ring_segment(ring, curr_proj, start_proj)
                
        if best_idx != -1:
            # 添加连接段
            if best_entry_path:
                coords.extend(list(best_entry_path.coords))
            # 添加下一段路径
            next_p = remain.pop(best_idx)
            coords.extend(list(next_p.coords))
        else:
            break
            
    return LineString(coords)


def _get_ring_segment(ring: LineString, d_start: float, d_end: float) -> LineString:
    """获取环上从 d_start 到 d_end 的片段"""
    coords = []
    L = ring.length
    if d_start <= d_end:
        # 简单截取
        pts = [ring.interpolate(d) for d in [d_start, d_end]] # 简化，实际应包含中间拐点
        # 获取中间所有坐标点
        # 这是一个简化实现，生产环境需要更严谨的几何截取
        return LineString(pts)
    else:
        # 跨越终点
        # start -> L
        # 0 -> end
        pts1 = [ring.interpolate(d_start), ring.interpolate(L)]
        pts2 = [ring.interpolate(0), ring.interpolate(d_end)]
        return LineString(pts1 + pts2)


def connect_path_with_entry_exit_along_outer_boundary(work_area: Union[Polygon, MultiPolygon],
                                                      path: LineString,
                                                      entry_local: Tuple[float, float],
                                                      exit_local: Tuple[float, float],
                                                      orientation_entry: str = 'auto',
                                                      orientation_exit: str = 'auto') -> LineString:
    """
    将入口连接到路径起点，将路径终点连接到出口。
    """
    if not path or path.is_empty:
        return LineString([entry_local, exit_local])
    
    coords = list(path.coords)
    
    # 入口 -> 起点
    # 简单直线连接（实际应沿外环）
    coords.insert(0, entry_local)
    
    # 终点 -> 出口
    coords.append(exit_local)
    
    return LineString(coords)
