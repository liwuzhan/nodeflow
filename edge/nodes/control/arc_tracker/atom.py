"""
弧线跟踪控制器 - L4层原子算法

纯函数实现，无框架依赖：
- 三次贝塞尔曲线数学（求值、切线、曲率、弧长）
- 路径投影（最近点搜索）
- Pure Pursuit 弧线跟踪控制律
"""

import math
import time
from typing import List, Tuple, Dict, Any, Optional


# ============================================================================
# 贝塞尔曲线基础数学
# ============================================================================

def bezier_point(seg: Dict[str, Any], t: float) -> Tuple[float, float]:
    """
    三次贝塞尔曲线求值 B(t)

    Args:
        seg: 贝塞尔段 {'p0', 'p1', 'p2', 'p3'}，每个是 [x, y]
        t: 参数 [0, 1]

    Returns:
        (x, y) 曲线上的点
    """
    u = 1.0 - t
    p0, p1, p2, p3 = seg['p0'], seg['p1'], seg['p2'], seg['p3']
    x = u*u*u*p0[0] + 3*u*u*t*p1[0] + 3*u*t*t*p2[0] + t*t*t*p3[0]
    y = u*u*u*p0[1] + 3*u*u*t*p1[1] + 3*u*t*t*p2[1] + t*t*t*p3[1]
    return x, y


def bezier_tangent(seg: Dict[str, Any], t: float) -> Tuple[float, float]:
    """
    三次贝塞尔曲线一阶导 B'(t)

    Returns:
        (dx, dy) 切线向量（未归一化）
    """
    u = 1.0 - t
    p0, p1, p2, p3 = seg['p0'], seg['p1'], seg['p2'], seg['p3']
    # B'(t) = 3(1-t)^2(P1-P0) + 6(1-t)t(P2-P1) + 3t^2(P3-P2)
    dx = (3*u*u*(p1[0]-p0[0]) + 6*u*t*(p2[0]-p1[0]) + 3*t*t*(p3[0]-p2[0]))
    dy = (3*u*u*(p1[1]-p0[1]) + 6*u*t*(p2[1]-p1[1]) + 3*t*t*(p3[1]-p2[1]))
    return dx, dy


def bezier_second_deriv(seg: Dict[str, Any], t: float) -> Tuple[float, float]:
    """
    三次贝塞尔曲线二阶导 B''(t)

    Returns:
        (ddx, ddy) 二阶导向量
    """
    u = 1.0 - t
    p0, p1, p2, p3 = seg['p0'], seg['p1'], seg['p2'], seg['p3']
    # B''(t) = 6(1-t)(P2-2P1+P0) + 6t(P3-2P2+P1)
    a0 = p2[0] - 2*p1[0] + p0[0]
    a1 = p3[0] - 2*p2[0] + p1[0]
    b0 = p2[1] - 2*p1[1] + p0[1]
    b1 = p3[1] - 2*p2[1] + p1[1]
    ddx = 6*u*a0 + 6*t*a1
    ddy = 6*u*b0 + 6*t*b1
    return ddx, ddy


def bezier_curvature(seg: Dict[str, Any], t: float) -> float:
    """
    三次贝塞尔曲线有符号曲率 κ(t)

    κ = (dx*ddy - dy*ddx) / (dx^2 + dy^2)^(3/2)
    正值 = 左转（逆时针），负值 = 右转（顺时针）

    Returns:
        有符号曲率值
    """
    dx, dy = bezier_tangent(seg, t)
    ddx, ddy = bezier_second_deriv(seg, t)
    denom = (dx*dx + dy*dy) ** 1.5
    if denom < 1e-12:
        return 0.0
    return (dx*ddy - dy*ddx) / denom


def bezier_arc_length(seg: Dict[str, Any], t0: float, t1: float, steps: int = 16) -> float:
    """
    用 Simpson 复合积分估算贝塞尔段 [t0, t1] 上的弧长

    Args:
        seg: 贝塞尔段
        t0: 起始参数
        t1: 结束参数
        steps: 积分步数（偶数，越大越精确）

    Returns:
        弧长（米）
    """
    if steps % 2 != 0:
        steps += 1
    h = (t1 - t0) / steps

    def speed(t):
        dx, dy = bezier_tangent(seg, t)
        return math.sqrt(dx*dx + dy*dy)

    # Simpson 1/3 规则
    s = speed(t0) + speed(t1)
    for i in range(1, steps):
        t = t0 + i * h
        if i % 2 == 0:
            s += 2 * speed(t)
        else:
            s += 4 * speed(t)
    return s * h / 3.0


# ============================================================================
# 路径操作
# ============================================================================

def _point_to_seg_dist_sq(px: float, py: float, seg: Dict[str, Any], t: float) -> float:
    """点到贝塞尔段上某 t 处的距离平方"""
    bx, by = bezier_point(seg, t)
    dx = px - bx
    dy = py - by
    return dx*dx + dy*dy


def project_to_path(
    px: float, py: float,
    segments: List[Dict[str, Any]],
    hint_seg: int = 0,
    hint_t: float = 0.0
) -> Tuple[int, float, float]:
    """
    将点投影到贝塞尔路径上，找最近点

    使用粗搜索+细搜索两阶段策略，hint 附近优先搜索。

    Args:
        px, py: 待投影点
        segments: 贝塞尔段列表
        hint_seg: 上一次投影的段索引（加速搜索）
        hint_t: 上一次投影的 t 值

    Returns:
        (seg_idx, t, cross_track_dist)
        - seg_idx: 最近段索引
        - t: 最近段上的参数 [0, 1]
        - cross_track_dist: 有符号横向误差（正=左侧，负=右侧）
    """
    n_seg = len(segments)
    if n_seg == 0:
        return 0, 0.0, 0.0

    # 搜索范围：hint 附近优先，然后扩展到全部
    search_range = min(n_seg, max(5, n_seg // 2))
    start = max(0, hint_seg - 2)
    end = min(n_seg, hint_seg + search_range)

    best_seg = hint_seg
    best_t = hint_t
    best_dist_sq = float('inf')

    # 粗搜索：每段采样 20 点
    sample_n = 20
    for si in range(start, end):
        seg = segments[si]
        for j in range(sample_n + 1):
            t = j / sample_n
            d2 = _point_to_seg_dist_sq(px, py, seg, t)
            if d2 < best_dist_sq:
                best_dist_sq = d2
                best_seg = si
                best_t = t

    # 如果粗搜索没覆盖全部，检查剩余段
    if start > 0 or end < n_seg:
        for si in list(range(0, start)) + list(range(end, n_seg)):
            seg = segments[si]
            # 只粗采样边界端点和中点，跳过明显远的段
            for t in (0.0, 0.5, 1.0):
                d2 = _point_to_seg_dist_sq(px, py, seg, t)
                if d2 < best_dist_sq:
                    # 找到更近的段，做细搜索
                    for j in range(sample_n + 1):
                        t2 = j / sample_n
                        d2b = _point_to_seg_dist_sq(px, py, seg, t2)
                        if d2b < best_dist_sq:
                            best_dist_sq = d2b
                            best_seg = si
                            best_t = t2
                    break  # 已经细搜了这一段

    # 细搜索：在最佳点 ±1 步间二分 3 次
    seg = segments[best_seg]
    step = 1.0 / sample_n
    for _ in range(3):
        lo = max(0.0, best_t - step)
        hi = min(1.0, best_t + step)
        mid1 = (lo + best_t) / 2.0
        mid2 = (best_t + hi) / 2.0

        d_lo = _point_to_seg_dist_sq(px, py, seg, lo)
        d_mid1 = _point_to_seg_dist_sq(px, py, seg, mid1)
        d_mid2 = _point_to_seg_dist_sq(px, py, seg, mid2)
        d_hi = _point_to_seg_dist_sq(px, py, seg, hi)

        candidates = [(d_lo, lo), (d_mid1, mid1),
                      (best_dist_sq, best_t), (d_mid2, mid2), (d_hi, hi)]
        best_dist_sq, best_t = min(candidates, key=lambda x: x[0])
        step /= 2.0

    # 计算有符号横向误差
    bx, by = bezier_point(seg, best_t)
    dx, dy = bezier_tangent(seg, best_t)
    # 叉积判断左右: tangent × (point - curve_point)
    cross = dx * (py - by) - dy * (px - bx)
    dist = math.sqrt(best_dist_sq)
    cross_track = dist if cross >= 0 else -dist

    return best_seg, best_t, cross_track


def advance_along_path(
    segments: List[Dict[str, Any]],
    seg_idx: int,
    t: float,
    distance: float
) -> Tuple[int, float]:
    """
    沿贝塞尔路径前进指定距离

    Args:
        segments: 贝塞尔段列表
        seg_idx: 当前段索引
        t: 当前段参数
        distance: 前进距离（米，正值向前）

    Returns:
        (new_seg_idx, new_t) 新位置
    """
    remaining = distance
    si = seg_idx
    ct = t

    while remaining > 0 and si < len(segments):
        seg = segments[si]
        # 估算当前段从 ct 到 1.0 的剩余弧长
        seg_remaining = bezier_arc_length(seg, ct, 1.0, steps=8)

        if seg_remaining >= remaining:
            # 目标在当前段内，用二分查找精确 t
            lo, hi = ct, 1.0
            for _ in range(10):
                mid = (lo + hi) / 2.0
                arc = bezier_arc_length(seg, ct, mid, steps=8)
                if arc < remaining:
                    lo = mid
                else:
                    hi = mid
            ct = (lo + hi) / 2.0
            return si, ct
        else:
            remaining -= seg_remaining
            si += 1
            ct = 0.0

    # 到达路径末端
    if si >= len(segments):
        return len(segments) - 1, 1.0
    return si, ct


def distance_to_end(
    segments: List[Dict[str, Any]],
    seg_idx: int,
    t: float
) -> float:
    """
    计算从当前位置到路径末端的剩余弧长

    Args:
        segments: 贝塞尔段列表
        seg_idx: 当前段索引
        t: 当前段参数

    Returns:
        剩余距离（米）
    """
    if not segments:
        return 0.0

    total = 0.0
    # 当前段剩余
    total += bezier_arc_length(segments[seg_idx], t, 1.0, steps=8)
    # 后续段全长
    for si in range(seg_idx + 1, len(segments)):
        total += bezier_arc_length(segments[si], 0.0, 1.0, steps=8)
    return total


# ============================================================================
# Pure Pursuit 控制律
# ============================================================================

def _normalize_angle(a: float) -> float:
    """将角度归一化到 (-pi, pi]"""
    while a > math.pi:
        a -= 2.0 * math.pi
    while a <= -math.pi:
        a += 2.0 * math.pi
    return a


def compute_pursuit_cmd(
    pose: Dict[str, Any],
    segments: List[Dict[str, Any]],
    state: Dict[str, Any],
    params: Dict[str, Any]
) -> Dict[str, Any]:
    """
    Pure Pursuit 弧线跟踪控制律

    Args:
        pose: 车辆位姿 {'x', 'y', 'theta'} (ENU, 数学坐标系)
        segments: 贝塞尔段列表
        state: 可变投影缓存 {'seg_idx', 't', 'initialized'}
        params: 控制参数 {
            'cruise_speed', 'min_speed', 'lookahead_base', 'lookahead_k',
            'max_angular_velocity', 'pivot_threshold_rad',
            'curvature_decel_factor', 'decel_distance', 'stop_distance'
        }

    Returns:
        velocity_cmd 字典 {'linear_velocity', 'angular_velocity', 'timestamp', 'status'}
    """
    now = time.time()

    if not segments or pose is None:
        return {
            'linear_velocity': 0.0,
            'angular_velocity': 0.0,
            'timestamp': now,
            'status': 'no_data',
        }

    px, py = pose['x'], pose['y']
    theta = pose['theta']

    cruise = params['cruise_speed']
    min_speed = params['min_speed']
    ld_base = params['lookahead_base']
    ld_k = params['lookahead_k']
    max_w = params['max_angular_velocity']
    pivot_th = params['pivot_threshold_rad']
    curv_decel = params['curvature_decel_factor']
    decel_dist = params['decel_distance']
    stop_dist = params['stop_distance']

    # 1. 投影：找路径上最近点
    hint_seg = state.get('seg_idx', 0)
    hint_t = state.get('t', 0.0)
    seg_idx, t, cross_err = project_to_path(px, py, segments, hint_seg, hint_t)

    # 更新状态缓存
    state['seg_idx'] = seg_idx
    state['t'] = t
    state['initialized'] = True

    # 2. 到终点距离
    dist_end = distance_to_end(segments, seg_idx, t)

    # 到达终点 → 停车
    if dist_end < stop_dist:
        return {
            'linear_velocity': 0.0,
            'angular_velocity': 0.0,
            'timestamp': now,
            'status': 'arrived',
        }

    # 3. 自适应前瞻距离 L_d = base + k * v
    # 用 cruise 作为速度估计（在启动时还没有实际速度反馈）
    v_est = cruise
    ld = ld_base + ld_k * v_est
    ld = max(ld, 0.3)  # 最小前瞻

    # 4. 求前瞻点
    la_seg, la_t = advance_along_path(segments, seg_idx, t, ld)
    lx, ly = bezier_point(segments[la_seg], la_t)

    # 5. 计算前瞻点在车体坐标系下的角度 α
    dx = lx - px
    dy = ly - py
    target_heading = math.atan2(dy, dx)
    alpha = _normalize_angle(target_heading - theta)

    # 6. 原地转判断
    if abs(alpha) > pivot_th:
        # 原地转：v=0, ω 方向跟随 α
        w = max_w if alpha > 0 else -max_w
        return {
            'linear_velocity': 0.0,
            'angular_velocity': w,
            'timestamp': now,
            'status': 'pivot',
        }

    # 7. Pure Pursuit 曲率
    # κ = 2·sin(α) / L_d
    kappa = 2.0 * math.sin(alpha) / ld

    # 8. 速度计算
    v = cruise

    # 曲率减速：κ 越大越减速
    kappa_at_proj = abs(bezier_curvature(segments[seg_idx], t))
    v *= max(0.3, 1.0 / (1.0 + curv_decel * kappa_at_proj))

    # 终点减速
    if dist_end < decel_dist:
        v *= max(0.1, dist_end / decel_dist)

    # 下限
    v = max(v, min_speed)

    # 角速度 ω = v · κ
    w = v * kappa
    w = max(-max_w, min(max_w, w))

    return {
        'linear_velocity': v,
        'angular_velocity': w,
        'timestamp': now,
        'status': 'tracking',
    }
