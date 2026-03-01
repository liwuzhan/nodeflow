"""
轨迹加载器 - L4层原子算法

纯函数实现，无框架依赖：
- 读取 position_recorder 保存的轨迹文件（CSV/JSON）
- WGS84 坐标批量转换为 ENU 坐标
- 构建 global_path 兼容格式
"""

import csv
import json
import math
import time
from pathlib import Path
from typing import List, Tuple, Dict, Any, Optional


# ============================================================================
# 坐标转换
# ============================================================================

METERS_PER_DEGREE_LAT = 111320.0


def meters_per_degree_lon(ref_lat: float) -> float:
    """计算给定纬度处经度每度对应的米数"""
    return METERS_PER_DEGREE_LAT * math.cos(math.radians(ref_lat))


def wgs84_to_enu(
    lon: float, lat: float, ref_lon: float, ref_lat: float
) -> Tuple[float, float]:
    """WGS84 经纬度 → ENU 局部坐标（米）"""
    x = (lon - ref_lon) * meters_per_degree_lon(ref_lat)
    y = (lat - ref_lat) * METERS_PER_DEGREE_LAT
    return x, y


# ============================================================================
# 轨迹文件读取
# ============================================================================

def load_trajectory_csv(filepath: str) -> List[Dict[str, Any]]:
    """
    读取 CSV 格式的轨迹文件

    Args:
        filepath: CSV 文件路径

    Returns:
        轨迹点列表，每个点包含 lat, lon, alt, heading, timestamp
    """
    points = []
    with open(filepath, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            point = {
                'lat': float(row['lat']),
                'lon': float(row['lon']),
                'alt': float(row.get('alt', 0)),
                'heading': float(row.get('heading', 0)),
                'timestamp': float(row.get('timestamp', 0)),
            }
            points.append(point)
    return points


def load_trajectory_json(filepath: str) -> List[Dict[str, Any]]:
    """
    读取 JSON 格式的轨迹文件

    Args:
        filepath: JSON 文件路径

    Returns:
        轨迹点列表
    """
    with open(filepath, 'r', encoding='utf-8') as f:
        data = json.load(f)

    raw_points = data.get('points', [])
    points = []
    for p in raw_points:
        point = {
            'lat': float(p['lat']),
            'lon': float(p['lon']),
            'alt': float(p.get('alt', 0)),
            'heading': float(p.get('heading', 0)),
            'timestamp': float(p.get('timestamp', 0)),
        }
        points.append(point)
    return points


def load_trajectory(filepath: str) -> List[Dict[str, Any]]:
    """
    自动检测格式并读取轨迹文件

    Args:
        filepath: 文件路径（.csv 或 .json）

    Returns:
        轨迹点列表
    """
    if str(filepath).endswith('.json'):
        return load_trajectory_json(filepath)
    return load_trajectory_csv(filepath)


# ============================================================================
# 轨迹文件管理
# ============================================================================

def list_trajectory_files(records_dir: str) -> List[Dict[str, Any]]:
    """
    列出记录目录中可用的轨迹文件

    Args:
        records_dir: 记录目录路径

    Returns:
        文件信息列表（按修改时间倒序）
    """
    records_path = Path(records_dir)
    if not records_path.exists():
        return []

    files = []
    for f in records_path.glob('record_*.*'):
        if f.suffix in ('.csv', '.json') and f.is_file():
            stat = f.stat()
            files.append({
                'name': f.name,
                'path': str(f),
                'size': stat.st_size,
                'modified': stat.st_mtime,
            })

    files.sort(key=lambda x: x['modified'], reverse=True)
    return files


def get_latest_trajectory(records_dir: str) -> Optional[str]:
    """
    获取最新的轨迹文件路径

    Args:
        records_dir: 记录目录路径

    Returns:
        最新轨迹文件的完整路径，如果不存在返回 None
    """
    files = list_trajectory_files(records_dir)
    if files:
        return files[0]['path']
    return None


# ============================================================================
# 坐标转换与路径构建
# ============================================================================

def compute_ref_point(points: List[Dict[str, Any]]) -> Tuple[float, float]:
    """
    从轨迹点计算 GPS 参考点（使用第一个点的经纬度）

    Args:
        points: 轨迹点列表

    Returns:
        (ref_lon, ref_lat) GPS参考点
    """
    if not points:
        raise ValueError("空的轨迹点列表")
    return points[0]['lon'], points[0]['lat']


def convert_to_enu_path(
    points: List[Dict[str, Any]],
    ref_lon: float,
    ref_lat: float
) -> List[Tuple[float, float]]:
    """
    将 WGS84 轨迹点批量转换为 ENU 路径

    Args:
        points: WGS84 轨迹点列表
        ref_lon: 参考点经度
        ref_lat: 参考点纬度

    Returns:
        ENU 路径点列表 [(x, y), ...]
    """
    enu_path = []
    for p in points:
        x, y = wgs84_to_enu(p['lon'], p['lat'], ref_lon, ref_lat)
        enu_path.append((x, y))
    return enu_path


def compute_path_length(enu_path: List[Tuple[float, float]]) -> float:
    """
    计算路径总长度（米）

    Args:
        enu_path: ENU 路径点列表

    Returns:
        路径总长度（米）
    """
    total = 0.0
    for i in range(1, len(enu_path)):
        dx = enu_path[i][0] - enu_path[i - 1][0]
        dy = enu_path[i][1] - enu_path[i - 1][1]
        total += math.sqrt(dx * dx + dy * dy)
    return total


def build_global_path(
    enu_path: List[Tuple[float, float]],
    task_id: str
) -> Dict[str, Any]:
    """
    构建与 global_coverage 兼容的 global_path 消息

    Args:
        enu_path: ENU 路径点列表
        task_id: 任务ID

    Returns:
        global_path 消息字典
    """
    return {
        'task_id': task_id,
        'timestamp': time.time(),
        'path': enu_path,
        'status': 'success' if enu_path else 'failed',
        'message': f'Loaded {len(enu_path)} points' if enu_path else 'Empty path',
    }


def build_task_enu(
    ref_lon: float,
    ref_lat: float,
    task_id: str
) -> Dict[str, Any]:
    """
    构建 task_enu 消息（提供 GPS 参考点给 coord_transform）

    Args:
        ref_lon: 参考点经度
        ref_lat: 参考点纬度
        task_id: 任务ID

    Returns:
        task_enu 消息字典
    """
    return {
        'id': task_id,
        'ref_lon': ref_lon,
        'ref_lat': ref_lat,
        'parcel': {'outer': [], 'holes': []},
        'vehicle': {},
        'timestamp': time.time(),
    }


# ============================================================================
# 贝塞尔曲线平滑路径
# ============================================================================

def _normalize(vx: float, vy: float) -> Tuple[float, float]:
    """归一化二维向量，零向量返回 (0, 0)"""
    d = math.sqrt(vx * vx + vy * vy)
    if d < 1e-12:
        return 0.0, 0.0
    return vx / d, vy / d


def _lerp(p0: Tuple[float, float], p1: Tuple[float, float], t: float) -> Tuple[float, float]:
    """线性插值"""
    return (p0[0] + t * (p1[0] - p0[0]),
            p0[1] + t * (p1[1] - p0[1]))


def _dist(a: Tuple[float, float], b: Tuple[float, float]) -> float:
    """两点欧氏距离"""
    dx = b[0] - a[0]
    dy = b[1] - a[1]
    return math.sqrt(dx * dx + dy * dy)


def _make_line_segment(p0: Tuple[float, float], p1: Tuple[float, float]) -> Dict[str, Any]:
    """
    构造退化贝塞尔段（直线），控制点在 1/3 和 2/3 处
    """
    return {
        'p0': list(p0),
        'p1': list(_lerp(p0, p1, 1.0 / 3.0)),
        'p2': list(_lerp(p0, p1, 2.0 / 3.0)),
        'p3': list(p1),
    }


def waypoints_to_bezier(
    path: List[Tuple[float, float]],
    corner_radius: float
) -> List[Dict[str, Any]]:
    """
    将折线路径转换为贝塞尔曲线段序列（圆角平滑）

    对每个中间航点生成圆角段，直线部分用退化贝塞尔表示。

    Args:
        path: 航点列表 [(x, y), ...]
        corner_radius: 期望圆角半径（米）

    Returns:
        贝塞尔段列表，每段 {'p0', 'p1', 'p2', 'p3'}（四个控制点）
    """
    n = len(path)
    if n < 2:
        return []
    if n == 2:
        return [_make_line_segment(path[0], path[1])]

    # 对每个中间航点计算切入/切出点
    cut_in = []   # 第 i 个中间航点的切入点 (i=1..n-2)
    cut_out = []  # 第 i 个中间航点的切出点
    corners = []  # 圆角贝塞尔段

    for i in range(1, n - 1):
        prev, curr, nxt = path[i - 1], path[i], path[i + 1]

        edge_prev = _dist(prev, curr)
        edge_next = _dist(curr, nxt)
        if edge_prev < 1e-9 or edge_next < 1e-9:
            # 退化（重叠点），不做圆角
            cut_in.append(curr)
            cut_out.append(curr)
            corners.append(None)
            continue

        # 实际圆角半径：不超过相邻边长度的一半
        r = min(corner_radius, edge_prev / 2.0, edge_next / 2.0)

        # 从当前点向前/后偏移 r 得到切入/切出点
        d_prev = _normalize(prev[0] - curr[0], prev[1] - curr[1])
        d_next = _normalize(nxt[0] - curr[0], nxt[1] - curr[1])

        q = (curr[0] + r * d_prev[0], curr[1] + r * d_prev[1])  # 切入
        rr = (curr[0] + r * d_next[0], curr[1] + r * d_next[1])  # 切出

        cut_in.append(q)
        cut_out.append(rr)

        # 圆角贝塞尔段：P0=Q, P1=Q+2/3*(Wi-Q), P2=R+2/3*(Wi-R), P3=R
        seg = {
            'p0': list(q),
            'p1': [q[0] + 2.0 / 3.0 * (curr[0] - q[0]),
                   q[1] + 2.0 / 3.0 * (curr[1] - q[1])],
            'p2': [rr[0] + 2.0 / 3.0 * (curr[0] - rr[0]),
                   rr[1] + 2.0 / 3.0 * (curr[1] - rr[1])],
            'p3': list(rr),
        }
        corners.append(seg)

    # 组装最终段序列
    segments = []

    # 首段：W0 → 第一个切入点
    segments.append(_make_line_segment(path[0], cut_in[0]))

    for i in range(len(corners)):
        # 圆角段
        if corners[i] is not None:
            segments.append(corners[i])

        # 直线段：当前切出点 → 下一个切入点（或终点）
        if i < len(corners) - 1:
            segments.append(_make_line_segment(cut_out[i], cut_in[i + 1]))
        else:
            # 末段：最后切出点 → Wn
            segments.append(_make_line_segment(cut_out[i], path[-1]))

    return segments


def _bezier_point_from_seg(seg: Dict[str, Any], t: float) -> Tuple[float, float]:
    """在单段贝塞尔上求点（用于弧长估算）"""
    u = 1.0 - t
    p0, p1, p2, p3 = seg['p0'], seg['p1'], seg['p2'], seg['p3']
    x = u*u*u*p0[0] + 3*u*u*t*p1[0] + 3*u*t*t*p2[0] + t*t*t*p3[0]
    y = u*u*u*p0[1] + 3*u*u*t*p1[1] + 3*u*t*t*p2[1] + t*t*t*p3[1]
    return x, y


def _estimate_segment_length(seg: Dict[str, Any], steps: int = 16) -> float:
    """用线段近似估算单段贝塞尔弧长"""
    length = 0.0
    prev = _bezier_point_from_seg(seg, 0.0)
    for i in range(1, steps + 1):
        t = i / steps
        cur = _bezier_point_from_seg(seg, t)
        length += _dist(prev, cur)
        prev = cur
    return length


def build_bezier_path(
    enu_path: List[Tuple[float, float]],
    task_id: str,
    corner_radius: float = 1.0
) -> Dict[str, Any]:
    """
    从 ENU 路径构建贝塞尔平滑路径消息

    Args:
        enu_path: ENU 路径点列表 [(x, y), ...]
        task_id: 任务ID
        corner_radius: 圆角半径（米）

    Returns:
        贝塞尔路径消息字典
    """
    segments = waypoints_to_bezier(enu_path, corner_radius)

    total_length = sum(_estimate_segment_length(s) for s in segments)

    return {
        'task_id': task_id,
        'timestamp': time.time(),
        'segments': segments,
        'total_length': total_length,
        'num_waypoints': len(enu_path),
        'corner_radius': corner_radius,
        'status': 'success' if segments else 'failed',
    }
