#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
扫描工具模块

包含射线生成、垂直连接和裁切相关功能。
"""

from typing import List, Tuple, Optional

from shapely.geometry import Polygon, LineString, MultiPolygon
from shapely.ops import unary_union
from shapely.affinity import rotate
from shapely.geometry import Point


def _is_vertical_corridor(rot_area: Polygon | MultiPolygon, x: float, y0: float, y1: float) -> bool:
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


def _find_vertical_x_near_endpoint(rot_area: Polygon | MultiPolygon, y0: float, y1: float,
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


def generate_rays_first_contact(work_area: Polygon | MultiPolygon, spacing_m: float, angle_deg: float) -> List[LineString]:
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


def connect_rays_vertical(work_area: Polygon | MultiPolygon, spacing_m: float, angle_deg: float) -> List[LineString]:
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


def trim_rays_by_connectors(work_area: Polygon | MultiPolygon, spacing_m: float, angle_deg: float) -> List[LineString]:
    """
    使用生成的垂直连线裁切掉水平射线的多余部分：
    - 除边缘线段外，通常会与上下两条连线相交，保留两个交点之间的部分；
    - 边缘线段仅有一个交点（或交点与端点重合），保留两段中更长的那一段；
    - 若某线段没有可用连线（无交点），保持原样。
    返回：已回转到原坐标系的"裁切后射线"线段列表。
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


def build_open_polyline(work_area: Polygon | MultiPolygon, spacing_m: float, angle_deg: float) -> LineString:
    """
    构建首遍开放折线，但仅保留“最长的连续链”。
    规则：
    - 在旋转坐标系下生成每行的首段，并根据已验证的竖直连线（pair_conn_x）决定行间是否可连接；
    - 仅当存在合法竖直连线时，才在相邻行之间加入竖直连接段；
    - 若某相邻行之间不存在竖直连线，则在该处断开，形成多条独立链；
    - 返回所有链中“长度最长”的一条，避免凭空连接不相邻的行段。
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

    # 为每行计算与之相交的连线 x，得到裁切端点（与 trim_rays_by_connectors 保持一致）
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

    # 若某行裁切后的水平长度短于行距，则将该行以及与之相邻的竖直连线一起丢弃
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

    # 组装开放折线为“多条链”（仅在存在竖直连线时跨行连接）
    chains_pts_rot: List[List[Tuple[float, float]]] = []
    cur_pts: List[Tuple[float, float]] = []

    def append_pt(pt: Tuple[float, float]):
        if not cur_pts or (abs(cur_pts[-1][0] - pt[0]) > 1e-9 or abs(cur_pts[-1][1] - pt[1]) > 1e-9):
            cur_pts.append(pt)

    n = len(rows)
    for i, row in enumerate(rows):
        # 丢弃行：结束当前链并跳过
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

        # 若当前没有正在构建的链（或上一行未与本行连接），开启新链
        if not cur_pts:
            # 选择当前行的起止点
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
            # 若存在到下一行的竖直连线，则加入竖段并继续保持当前链
            if x_next is not None and i < n - 1:
                append_pt((x_next, rows[i + 1]['y']))
            else:
                # 不存在连线则结束当前链
                if len(cur_pts) >= 2:
                    chains_pts_rot.append(cur_pts)
                cur_pts = []
            continue

        # 正在构建的链：判断是否由上一行竖线连接到本行（必须有 x_prev）
        if x_prev is None:
            # 上一行未与本行连接，结束旧链，开启新链
            if len(cur_pts) >= 2:
                chains_pts_rot.append(cur_pts)
            cur_pts = []
            # 重新处理本行（作为新链起点）
            if x_next is None:
                # 独立行
                append_pt((xl, y0))
                append_pt((xr, y0))
                chains_pts_rot.append(cur_pts)
                cur_pts = []
            else:
                # 与下一行连接
                start_x = xr if abs(xl - x_next) <= 1e-7 else xl
                end_x = x_next
                if start_x <= end_x:
                    append_pt((start_x, y0))
                    append_pt((end_x, y0))
                else:
                    append_pt((start_x, y0))
                    append_pt((end_x, y0))
                if i < n - 1:
                    append_pt((x_next, rows[i + 1]['y']))
            continue

        # 本行与上一行通过竖线连接，继续当前链
        start_x = x_prev
        end_x = x_next if x_next is not None else (xl if abs(start_x - xr) <= 1e-7 else xr)
        if start_x <= end_x:
            append_pt((start_x, y0))
            append_pt((end_x, y0))
        else:
            append_pt((start_x, y0))
            append_pt((end_x, y0))
        if x_next is not None and i < n - 1:
            append_pt((x_next, rows[i + 1]['y']))
        else:
            # 链在此结束
            if len(cur_pts) >= 2:
                chains_pts_rot.append(cur_pts)
            cur_pts = []

    # 如果仍有未提交的链，提交之
    if cur_pts and len(cur_pts) >= 2:
        chains_pts_rot.append(cur_pts)

    # 选择“最长链”并返回
    if not chains_pts_rot:
        return LineString([])

    longest_chain = None
    longest_len = -1.0
    for pts in chains_pts_rot:
        ln_rot = LineString(pts)
        if ln_rot.length > longest_len:
            longest_len = ln_rot.length
            longest_chain = ln_rot

    polyline_local = rotate(longest_chain, angle_deg, origin=(0, 0), use_radians=False)
    return polyline_local


def build_open_polyline_chains(work_area: Polygon | MultiPolygon, spacing_m: float, angle_deg: float) -> List[LineString]:
    """
    构建首/次遍开放折线的所有连续链：
    - 在旋转坐标系下生成每行的首段；
    - 仅当存在合法竖直连线时，才在相邻行之间加入竖直连接段；
    - 若某相邻行之间不存在竖直连线，则在该处断开，形成多条独立链；
    - 返回所有链（不筛选长度，不丢弃短链）。
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
        return []

    # 生成竖直连线并转到旋转坐标系以便匹配
    connectors_local = connect_rays_vertical(work_area, spacing_m, angle_deg)
    connectors_rot = [rotate(ln, -angle_deg, origin=(0, 0), use_radians=False) for ln in connectors_local]

    # 为每行计算与之相交的连线 x，得到裁切端点（与 trim_rays_by_connectors 保持一致）
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

    # 若某行裁切后的水平长度短于行距，则丢弃该行并移除其相邻连线
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

    # 组装开放折线为“多条链”（仅在存在竖直连线时跨行连接）
    chains_pts_rot: List[List[Tuple[float, float]]] = []
    cur_pts: List[Tuple[float, float]] = []

    def append_pt(pt: Tuple[float, float]):
        if not cur_pts or (abs(cur_pts[-1][0] - pt[0]) > 1e-9 or abs(cur_pts[-1][1] - pt[1]) > 1e-9):
            cur_pts.append(pt)

    n = len(rows)
    for i, row in enumerate(rows):
        # 丢弃短行：结束当前链并跳过
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
                append_pt((start_x, y0))
                append_pt((end_x, y0))
                if i < n - 1:
                    append_pt((x_next, rows[i + 1]['y']))
            continue

        start_x = x_prev
        end_x = x_next if x_next is not None else (xl if abs(start_x - xr) <= 1e-7 else xr)
        append_pt((start_x, y0))
        append_pt((end_x, y0))
        if x_next is not None and i < n - 1:
            append_pt((x_next, rows[i + 1]['y']))
        else:
            if len(cur_pts) >= 2:
                chains_pts_rot.append(cur_pts)
            cur_pts = []

    if cur_pts and len(cur_pts) >= 2:
        chains_pts_rot.append(cur_pts)

    # 回转到原坐标系，返回所有链
    chains: List[LineString] = []
    for pts in chains_pts_rot:
        ln_rot = LineString(pts)
        ln_local = rotate(ln_rot, angle_deg, origin=(0, 0), use_radians=False)
        if ln_local.length > 1e-6:
            chains.append(ln_local)
    return chains


def select_even_row_spacing(area: Polygon | MultiPolygon,
                            base_spacing_m: float,
                            angle_deg: float,
                            factor_min: float = 0.6,
                            factor_max: float = 1.1,
                            step: float = 0.02) -> float:
    """
    在旋转坐标系下选择一个行距，使得扫描行数为偶数。
    行距在 [factor_min * base, factor_max * base] 范围内，优先选择接近 base 的值。

    计数方式：在旋转坐标系下，y 从 miny 到 maxy 以行距步进，
    若与区域在该 y 处存在线段相交（至少一条 LineString），则计为一行。
    """
    if base_spacing_m <= 1e-9:
        return base_spacing_m

    # 旋转到扫描坐标系
    merged = unary_union([p for p in area.geoms]) if isinstance(area, MultiPolygon) else area
    rot_area = rotate(merged, -angle_deg, origin=(0, 0), use_radians=False)
    minx, miny, maxx, maxy = rot_area.bounds
    width = maxx - minx
    height = maxy - miny
    if height <= 1e-9:
        return base_spacing_m

    extra = (width + height) * 0.5 + 10.0

    def count_rows(spacing: float) -> int:
        cnt = 0
        y = miny
        while y <= maxy + 1e-9:
            scan_line = LineString([(minx - extra, y), (maxx + extra, y)])
            inter = rot_area.intersection(scan_line)
            has_seg = False
            if isinstance(inter, LineString):
                has_seg = True
            elif hasattr(inter, 'geoms'):
                for g in inter.geoms:
                    if isinstance(g, LineString):
                        has_seg = True
                        break
            if has_seg:
                cnt += 1
            y += spacing
        return cnt

    # 候选行距（按接近 base 的优先级排序）
    s_min = max(1e-6, factor_min * base_spacing_m)
    s_max = max(s_min + 1e-6, factor_max * base_spacing_m)
    factors: List[float] = []
    f = factor_min
    while f <= factor_max + 1e-9:
        factors.append(f)
        f += step
    # 确保包含边界
    if factors[0] > factor_min + 1e-9:
        factors.insert(0, factor_min)
    if factors[-1] < factor_max - 1e-9:
        factors.append(factor_max)

    candidates = [base_spacing_m * fx for fx in factors]
    candidates.sort(key=lambda s: abs(s - base_spacing_m))

    # 优先选偶数行数
    best_even = None
    best_even_diff = None
    for s in candidates:
        if s < s_min - 1e-9 or s > s_max + 1e-9:
            continue
        rows = count_rows(s)
        if rows % 2 == 0 and rows > 0:
            diff = abs(s - base_spacing_m)
            if best_even is None or diff < best_even_diff:
                best_even = s
                best_even_diff = diff
                # 找到非常接近 base 的即可提前返回
                if diff <= base_spacing_m * 1e-3:
                    break

    if best_even is not None:
        return best_even

    # 若没有找到偶数，则退回到最接近 base 的候选
    return max(s_min, min(s_max, base_spacing_m))


def build_open_polylines_for_components(area: Polygon | MultiPolygon,
                                        base_spacing_m: float,
                                        angle_deg: float,
                                        factor_min: float = 0.6,
                                        factor_max: float = 1.1,
                                        step: float = 0.02,
                                        boundary_tolerance: float = 1e-6) -> List[LineString]:
    """
    针对输入区域的每个独立多边形组件：
    - 在 [factor_min, factor_max] * base_spacing_m 范围内，按“±0.1m 对称步进”的顺序枚举候选行距（优先尝试 base，其次 base-0.1、base+0.1、base-0.2、base+0.2 ...）
    - 仅尝试偶数行距的候选，生成折线并校验“起点/终点是否在组件边界上”
    - 若某候选通过校验则采用；若全部失败则放弃该组件（尝试上限为 10 次）
    返回所有组件的折线列表。
    """
    if area.is_empty:
        return []
    comps = list(area.geoms) if isinstance(area, MultiPolygon) else [area]
    polylines: List[LineString] = []
    for poly in comps:
        if poly.is_empty:
            continue
        # 旋转到扫描坐标系（用于行计数）
        rot_poly = rotate(poly, -angle_deg, origin=(0, 0), use_radians=False)
        minx, miny, maxx, maxy = rot_poly.bounds
        extra = (maxx - minx + maxy - miny) * 0.5 + 10.0

        def count_rows(spacing: float) -> int:
            cnt = 0
            y = miny
            while y <= maxy + 1e-9:
                scan_line = LineString([(minx - extra, y), (maxx + extra, y)])
                inter = rot_poly.intersection(scan_line)
                has_seg = False
                if isinstance(inter, LineString):
                    has_seg = True
                elif hasattr(inter, 'geoms'):
                    for g in inter.geoms:
                        if isinstance(g, LineString):
                            has_seg = True
                            break
                if has_seg:
                    cnt += 1
                y += spacing
            return cnt

        # 候选行距：以 0.1 米为步进，围绕 base 对称展开，限定在 [s_min, s_max] 范围内
        s_min = max(1e-6, factor_min * base_spacing_m)
        s_max = max(s_min + 1e-6, factor_max * base_spacing_m)
        step_abs = 0.1
        max_attempts = 10
        seq: List[float] = [base_spacing_m]
        i = 1
        # 按 base-0.1, base+0.1, base-0.2, base+0.2 ... 生成序列
        while len(seq) < max_attempts * 2:  # 生成足够多，后面再截断到有效范围
            minus = base_spacing_m - i * step_abs
            plus = base_spacing_m + i * step_abs
            seq.append(minus)
            seq.append(plus)
            i += 1
        # 过滤到有效范围，并截断到最多 max_attempts 个候选
        candidates: List[float] = []
        for s in seq:
            if s_min - 1e-9 <= s <= s_max + 1e-9:
                candidates.append(s)
            if len(candidates) >= max_attempts:
                break

        # 校验函数：端点距离边界是否在容忍度
        def endpoints_on_boundary(ln: LineString) -> bool:
            if ln.is_empty:
                return False
            start = ln.coords[0]
            end = ln.coords[-1]
            # 仅使用外环线作为边界（不把内孔/障碍物视为边界）
            bd = poly.exterior
            ds = bd.distance(Point(start))
            de = bd.distance(Point(end))
            return ds <= boundary_tolerance and de <= boundary_tolerance

        # 统计：在删除过短行后（由 build_open_polyline_chains 已应用过滤），
        # 二次生成的行（不同的 y 水平）数量是否仍为偶数。
        def count_rows_from_chains(chains: List[LineString], rounding_digits: int = 8) -> int:
            if not chains:
                return 0
            ys = set()
            for ln in chains:
                # 将链回转到扫描坐标系，便于按水平行计数
                ln_rot = rotate(ln, -angle_deg, origin=(0, 0), use_radians=False)
                for pt in ln_rot.coords:
                    y = round(pt[1], rounding_digits)
                    ys.add(y)
            return len(ys)

        accepted_any = False
        attempts = 0
        for s in candidates:
            if s < s_min - 1e-9 or s > s_max + 1e-9:
                continue
            rows = count_rows(s)
            if rows % 2 != 0 or rows <= 0:
                attempts += 1
                if attempts >= max_attempts:
                    break
                continue
            # 对该行距生成所有链，并保留端点在外环上的所有链（不丢弃短链）
            chains = build_open_polyline_chains(poly, s, angle_deg)
            if chains:
                # 删除过短行后，仍需确保最终行数为偶数，否则尝试其他候选行距
                rows_after = count_rows_from_chains(chains)
                if rows_after % 2 != 0 or rows_after <= 0:
                    attempts += 1
                    if attempts >= max_attempts:
                        break
                    continue
                valid_chains = [ln for ln in chains if endpoints_on_boundary(ln)]
                if valid_chains:
                    polylines.extend(valid_chains)
                    accepted_any = True
                    break
            # 无链或未通过校验也计入一次尝试
            attempts += 1
            if attempts >= max_attempts:
                break
        # 否则放弃该组件（不加入 polylines）
    return polylines


def _largest_polygon(area: Polygon | MultiPolygon) -> Polygon:
    if isinstance(area, MultiPolygon):
        polys = list(area.geoms)
        if not polys:
            from shapely.geometry import Polygon as _Polygon
            return _Polygon()
        polys.sort(key=lambda p: p.area, reverse=True)
        return polys[0]
    return area


def _ring_orientation(coords: List[Tuple[float, float]]) -> float:
    """返回环的有符号面积（>0 视为 CCW，<0 视为 CW）。"""
    a = 0.0
    n = len(coords)
    for i in range(n - 1):
        x1, y1 = coords[i]
        x2, y2 = coords[i + 1]
        a += (x1 * y2 - x2 * y1)
    return a * 0.5


def _ensure_ring_orientation(coords: List[Tuple[float, float]], cw: bool) -> List[Tuple[float, float]]:
    # 输入 coords 可能闭合或未闭合；统一去重闭合点，只保留一次首点。
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
    """返回 line 上 [d0, d1] 的子线段（不考虑闭合环）。"""
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
        import math
        seg_len = math.hypot(x1 - x0, y1 - y0)
        if seg_len <= 1e-12:
            continue
        seg_start = acc
        seg_end = acc + seg_len
        # intersect [seg_start, seg_end] with [d0, d1]
        a = max(seg_start, d0)
        b = min(seg_end, d1)
        if a <= b + 1e-12:
            # include segment from a to b
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
                # avoid duplicate
                if abs(res[-1][0] - px_a) > 1e-9 or abs(res[-1][1] - py_a) > 1e-9:
                    res.append((px_a, py_a))
            res.append((px_b, py_b))
        acc += seg_len
    if len(res) < 2:
        # fallback: single point
        pt = line.interpolate(d0)
        return LineString([pt.coords[0], pt.coords[0]])
    return LineString(res)


def connect_polylines_along_outer_boundary(work_area: Polygon | MultiPolygon,
                                           primary: LineString,
                                           secondaries: List[LineString],
                                           orientation: str = 'cw') -> LineString:
    """
    沿安全区域外环（顺时针或逆时针）连接第一次折线与第二次折线，生成单条连续路径：
    - 取面积最大多边形的外环作为连接环；
    - 从第一次折线的“结束端点”作为起锚点，按环方向依次连接到每一条第二次折线的起点；
    - 每条折线内部若起点不匹配，则反转该折线坐标序列；
    - 连接段严格沿外环。

    orientation: 'cw' 或 'ccw'
    返回：单条 LineString。
    """
    if not primary or primary.is_empty:
        return LineString([])
    # 构建环
    largest = _largest_polygon(work_area)
    ring_coords = list(largest.exterior.coords)
    cw = True if orientation.lower() == 'cw' else False
    oriented = _ensure_ring_orientation(ring_coords, cw)
    ring_line = LineString(oriented + [oriented[0]])  # 闭合
    L = ring_line.length

    def anchor_dist(pt_xy: Tuple[float, float]) -> float:
        return ring_line.project(Point(pt_xy))

    # 初始锚点：第一次折线的末端
    p0 = list(primary.coords)[0]
    p1 = list(primary.coords)[-1]
    # 将路径按“末端”为入口，以保持与用户描述一致（先跑第一次折线，再沿外环连接）
    primary_coords = list(primary.coords)
    current_anchor = p1
    current_path: List[Tuple[float, float]] = []
    # 先加入第一次折线（确保开头与当前锚点匹配）
    # 如果第一次折线当前尾端作为起始锚点，则在连接之前应先跑完第一次折线。
    # 为了保证单条路径连续，我们从第一次折线的起点开始加入，再以其尾端作为外环连接的起始。
    current_path.extend(primary_coords)

    # 遍历 secondaries，按外环距离选择“下一个”起点
    remaining = [ln for ln in secondaries if ln and not ln.is_empty]
    while remaining:
        ca_d = anchor_dist(current_anchor)
        # 选择距离 ca_d 之后（按环方向）的最近起点作为下一个目标
        best = None
        best_delta = None
        best_start = None
        best_end = None
        for ln in remaining:
            a = list(ln.coords)[0]
            b = list(ln.coords)[-1]
            da = anchor_dist(a)
            db = anchor_dist(b)
            # 候选起点为 a 或 b，取相对于 ca_d 最小的正向环距离
            def delta(d):
                # 正向距离（wrap around）
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
        # 外环连接 current_anchor -> best_start
        d0 = ca_d
        d1 = anchor_dist(best_start)
        seg = _slice_line_by_distance(ring_line, d0, d1) if d0 <= d1 else LineString(list(_slice_line_by_distance(ring_line, d0, L).coords) + list(_slice_line_by_distance(ring_line, 0.0, d1).coords))
        # 追加连接段（避免重复点）
        for xy in list(seg.coords):
            if not current_path or abs(current_path[-1][0] - xy[0]) > 1e-9 or abs(current_path[-1][1] - xy[1]) > 1e-9:
                current_path.append(xy)
        # 追加该折线（方向由 start/end 决定）
        coords_ln = list(best.coords)
        if coords_ln[0] != best_start:
            coords_ln = list(reversed(coords_ln))
        # 避免重复
        for xy in coords_ln:
            if not current_path or abs(current_path[-1][0] - xy[0]) > 1e-9 or abs(current_path[-1][1] - xy[1]) > 1e-9:
                current_path.append(xy)
        # 更新当前锚点与剩余列表
        current_anchor = best_end
        remaining.remove(best)

    if len(current_path) < 2:
        return LineString([])
    return LineString(current_path)


def connect_path_with_entry_exit_along_outer_boundary(work_area: Polygon | MultiPolygon,
                                                      path: LineString,
                                                      entry_local: Tuple[float, float] | None = None,
                                                      exit_local: Tuple[float, float] | None = None,
                                                      orientation_entry: str = 'auto',
                                                      orientation_exit: str = 'auto') -> LineString:
    """
    将完整路径与“入口/出口”的锚点沿安全区域外环连接：
    - 仅使用“面积最大多边形”的外环作为连接环；
    - 若提供入口点，则沿外环连接入口点到路径起点；
    - 若提供出口点，则沿外环连接路径终点到出口点；
    - 方向 'cw'/'ccw' 或 'auto'（自动选择较短弧长）。

    返回：包含前置/后置外环连接段的单条 LineString。
    """
    if not path or path.is_empty:
        return LineString([])

    largest = _largest_polygon(work_area)
    ring_coords = list(largest.exterior.coords)
    ring_line = LineString(ring_coords + [ring_coords[0]])  # 闭合环
    L = ring_line.length

    def to_ring_point_and_dist(pt: Tuple[float, float]) -> Tuple[Tuple[float, float], float]:
        d = ring_line.project(Point(pt))
        p = ring_line.interpolate(d)
        return p.coords[0], d

    def slice_by_orientation(d0: float, d1: float, ori: str) -> LineString:
        # 正向（CW）片段
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
            # 反向：从 d1 到 d0 的正向，再反转坐标
            seg = forward(d1, d0)
            return LineString(list(reversed(list(seg.coords))))
        # auto：选择较短弧长
        def arc_len(d0_: float, d1_: float) -> float:
            return (d1_ - d0_) if (d1_ >= d0_) else (L - d0_ + d1_)
        cw_len = arc_len(d0, d1)
        ccw_len = L - cw_len
        return forward(d0, d1) if cw_len <= ccw_len else LineString(list(reversed(list(forward(d1, d0).coords))))

    coords = list(path.coords)

    # 入口 -> 路径起点
    if entry_local is not None and coords:
        entry_xy, de = to_ring_point_and_dist(entry_local)
        start_xy, ds = to_ring_point_and_dist(coords[0])
        seg = slice_by_orientation(de, ds, orientation_entry)
        pre: List[Tuple[float, float]] = []
        for xy in list(seg.coords):
            if not pre or abs(pre[-1][0] - xy[0]) > 1e-9 or abs(pre[-1][1] - xy[1]) > 1e-9:
                pre.append(xy)
        coords = pre + coords

    # 路径终点 -> 出口
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


def choose_boundary_orientation_by_far_vertex(work_area: Polygon | MultiPolygon,
                                              anchor_point: Tuple[float, float]) -> str:
    """
    根据锚点（通常为第一次折线的终点）在外环上的位置，选择顺时针或逆时针方向：
    - 比较从锚点出发沿外环到“下一个顶点”的距离（CW）与到“上一个顶点”的距离（CCW）；
    - 选择较远的一侧，以避免立即在近顶点处发生极限掉头或急拐弯。
    返回：'cw' 或 'ccw'
    """
    largest = _largest_polygon(work_area)
    ring_coords = list(largest.exterior.coords)
    # 统一以 CW 坐标序计算分段与累计长度
    oriented_cw = _ensure_ring_orientation(ring_coords, cw=True)
    closed = oriented_cw + [oriented_cw[0]]
    ring_line = LineString(closed)
    L = ring_line.length
    d = ring_line.project(Point(anchor_point))

    # 构建段的累计长度表
    seg_starts: List[float] = [0.0]
    import math
    for i in range(len(closed) - 1):
        x0, y0 = closed[i]
        x1, y1 = closed[i + 1]
        seg_len = math.hypot(x1 - x0, y1 - y0)
        seg_starts.append(seg_starts[-1] + seg_len)
    # seg_starts[-1] 应等于 L

    # 定位 d 所处段索引 k，使 seg_starts[k] <= d < seg_starts[k+1]
    k = 0
    for i in range(len(seg_starts) - 1):
        if seg_starts[i] <= d <= seg_starts[i + 1] + 1e-12:
            k = i
            break
    # CW 方向到下一个顶点的距离：seg_starts[k+1] - d
    cw_dist = seg_starts[k + 1] - d
    # CCW 方向到上一个顶点的距离：d - seg_starts[k]
    ccw_dist = d - seg_starts[k]
    if cw_dist >= ccw_dist:
        return 'cw'
    else:
        return 'ccw'


def compute_coverage_areas(work_area: Polygon | MultiPolygon,
                           spacing_m: float,
                           angle_deg: float,
                           implement_width_m: float,
                           include_connectors: bool = False):
    """
    计算覆盖区域与未覆盖区域：
    - 使用裁切后的水平线段，按半幅宽 (implement_width_m / 2) 进行缓冲得到覆盖带；
    - 可选地将竖直连线也计入覆盖（通常为移动通道，默认不计入）。
    - 将所有覆盖带合并后与工作区相交得到覆盖区，未覆盖区为工作区布尔减覆盖区。

    返回：(covered_area, uncovered_area)
    """
    # 生成裁切后线段（原坐标系下）
    trimmed = trim_rays_by_connectors(work_area, spacing_m, angle_deg)
    buffers = [s.buffer(max(0.0, implement_width_m * 0.5), cap_style=2, join_style=2) for s in trimmed]

    if include_connectors:
        connectors = connect_rays_vertical(work_area, spacing_m, angle_deg)
        buffers += [c.buffer(max(0.0, implement_width_m * 0.5), cap_style=2, join_style=2) for c in connectors]

    cover_union = unary_union(buffers) if buffers else None
    if cover_union:
        covered = cover_union.intersection(work_area)
    else:
        covered = work_area.buffer(0.0)  # 空补偿，确保类型一致

    uncovered = work_area.difference(covered)
    return covered, uncovered


def compute_coverage_areas_from_path(work_area: Polygon | MultiPolygon,
                                     path: LineString | None,
                                     spacing_m: float,
                                     angle_deg: float,
                                     implement_width_m: float,
                                     horizontal_only: bool = True):
    """
    基于“实际首遍路径”的覆盖计算：
    - 仅将路径中的“水平作业段”（在扫描坐标系下 dy≈0）视为覆盖来源；
    - 忽略垂直连线（移动通道，不计入作业覆盖）；
    - 仅缓冲长度不小于行距的水平段（避免将被抛弃的短折线计入覆盖）。

    返回：(covered_area, uncovered_area)
    """
    from shapely.geometry import Polygon as _Polygon
    if path is None or path.is_empty:
        # 无路径，视为未覆盖整个工作区
        return _Polygon(), work_area.buffer(0.0)

    # 统一为单个多边形
    area = unary_union([p for p in work_area.geoms]) if isinstance(work_area, MultiPolygon) else work_area

    # 旋转到扫描坐标系，识别水平段
    rot_path = rotate(path, -angle_deg, origin=(0, 0), use_radians=False)
    coords = list(rot_path.coords)
    segments_rot: List[LineString] = []
    eps_y = max(1e-7, spacing_m * 1e-6)
    for i in range(len(coords) - 1):
        (x0, y0) = coords[i]
        (x1, y1) = coords[i + 1]
        if not horizontal_only or abs(y1 - y0) <= eps_y:
            seg = LineString([(x0, y0), (x1, y1)])
            # 过滤掉长度短于行距的水平段
            if seg.length >= (spacing_m - max(1e-9, spacing_m * 1e-6)):
                segments_rot.append(seg)

    # 回到原坐标系并缓冲得到覆盖带
    segments_local = [rotate(s, angle_deg, origin=(0, 0), use_radians=False) for s in segments_rot]
    buffers = [s.buffer(max(0.0, implement_width_m * 0.5), cap_style=2, join_style=2) for s in segments_local]
    cover_union = unary_union(buffers) if buffers else None
    covered = cover_union.intersection(area) if cover_union else _Polygon()
    uncovered = area.difference(covered)
    return covered, uncovered


def filter_uncovered_by_edge_zone(uncovered: Polygon | MultiPolygon,
                                  work_area: Polygon | MultiPolygon,
                                  implement_width_m: float,
                                  threshold_ratio: float = 0.6) -> Polygon | MultiPolygon:
    """
    过滤未覆盖组件：
    - 计算安全区域的“边界带”（在安全边界内侧 implement_width_m 的条带）。
    - 对每个独立未覆盖多边形，若其与边界带的重叠面积占比 >= threshold_ratio，则剔除。

    返回：过滤后的未覆盖几何。
    """
    if uncovered.is_empty:
        return uncovered
    area = unary_union([p for p in work_area.geoms]) if isinstance(work_area, MultiPolygon) else work_area
    # 内缩得到内部区域，差集得到边界带。
    inner = area.buffer(-max(0.0, implement_width_m))
    if inner.is_empty:
        edge_zone = area  # 极端情形：内缩完全消失，则边界带近似整个区域
    else:
        edge_zone = area.difference(inner)

    comps = list(uncovered.geoms) if isinstance(uncovered, MultiPolygon) else [uncovered]
    kept = []
    for poly in comps:
        if poly.is_empty:
            continue
        a = poly.area
        if a <= 1e-9:
            continue
        overlap = poly.intersection(edge_zone)
        r = (overlap.area / a) if overlap and not overlap.is_empty else 0.0
        if r < threshold_ratio:
            kept.append(poly)

    if not kept:
        from shapely.geometry import Polygon as _Polygon
        return _Polygon()  # 空
    if len(kept) == 1:
        return kept[0]
    return unary_union(kept)