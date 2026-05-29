import math

def normalize_angle(angle_rad: float) -> float:
    """
    归一化角度到 (-π, π] 区间
    """
    while angle_rad > math.pi:
        angle_rad -= 2 * math.pi
    while angle_rad <= -math.pi:
        angle_rad += 2 * math.pi
    return angle_rad

def compute_velocity_cmd(
    pose_enu: dict | None,
    npkt: dict | None,
    max_speed: float,
    min_speed: float,
    kp: float,
    max_w: float,
    pivot_th: float,
    decel_start_dist: float,
    final_stop_dist: float,
    now: float,
    decel_min_factor: float = 0.3,
    low_view_threshold: int = 2,
    low_view_speed_factor: float = 0.7,
    very_low_view_threshold: int = 1,
    very_low_view_speed_factor: float = 0.45,
    approach_mode_factor: float = 0.5,
    fallback_mode_factor: float = 0.3,
    turn_slowdown_angle_deg: float = 45.0,
    sharp_turn_angle_deg: float = 120.0,
    turn_speed_factor: float = 0.65,
    sharp_turn_speed_factor: float = 0.35,
    path_progress: dict | None = None,
    cross_track_slowdown_error_m: float = 0.5,
    cross_track_stop_error_m: float = 1.5,
    cross_track_recovery_factor: float = 0.15
) -> dict:
    """
    计算速度控制命令（ENU坐标系）

    Args:
        pose_enu: 当前位姿 {x, y, theta}
        npkt: 前瞻点 {x, y, final}
        max_speed: 最大线速度 (m/s)
        min_speed: 最小线速度 (m/s)
        kp: 航向P增益
        max_w: 最大角速度 (rad/s)
        pivot_th: 原地转向阈值 (度)
        decel_start_dist: 开始减速的距离 (米)
        final_stop_dist: 终点停止距离 (米)
        now: 当前时间戳
    """
    if not pose_enu or not npkt:
        return {"linear_velocity": 0.0, "angular_velocity": 0.0, "timestamp": now}

    cx = pose_enu.get("x", 0.0)
    cy = pose_enu.get("y", 0.0)
    nx = npkt.get("x", cx)
    ny = npkt.get("y", cy)
    is_final = npkt.get("final", False)
    mode = npkt.get("mode", "tracking")
    in_view_count = npkt.get("in_view_count", npkt.get("in_view"))
    upcoming_turn_angle_deg = float(npkt.get("upcoming_turn_angle_deg", 0.0) or 0.0)
    segment_speed_limit = None
    cross_track_error_m = None
    if path_progress:
        motion = path_progress.get("motion", {}) or {}
        segment_speed_limit = motion.get("speed_limit_mps")
        cte = path_progress.get("cross_track_error_m")
        if cte is not None:
            cross_track_error_m = abs(float(cte))

    # 1. 计算到目标点的距离（欧几里得距离）
    dist = math.sqrt((nx - cx)**2 + (ny - cy)**2)

    # 2. 如果是最终点且距离很近，停止
    if is_final and dist < final_stop_dist:
        return {
            "linear_velocity": 0.0,
            "angular_velocity": 0.0,
            "timestamp": now,
            "status": "arrived",
            "speed_factor": 0.0,
        }

    # 3. 计算目标方位角（数学坐标系，弧度）
    target_theta = math.atan2(ny - cy, nx - cx)

    # 4. 当前航向角（数学坐标系，弧度）
    current_theta = float(pose_enu.get("theta", 0.0))

    # 5. 计算航向角误差（数学坐标系，弧度）
    error_rad = normalize_angle(target_theta - current_theta)

    # 6. 计算角速度控制命令（P控制）
    # 数学坐标系: CCW为正，无需取反，直接兼容仿真器
    w = kp * error_rad
    w = max(-max_w, min(max_w, w))

    # 7. 计算线速度
    error_deg = math.degrees(abs(error_rad))
    if error_deg >= pivot_th:
        # 原地转向模式
        v = 0.0
        dist_factor = 1.0
    else:
        # 前进模式：根据角度误差和距离调整速度
        v = max_speed * abs(math.cos(error_rad))

        # 接近目标时减速
        if dist < decel_start_dist:
            dist_ratio = max(0.0, min(1.0, dist / decel_start_dist))
            dist_factor = decel_min_factor + (1.0 - decel_min_factor) * dist_ratio
            v = v * dist_factor
        else:
            dist_factor = 1.0

        # 最小速度限制（但接近最终点时允许更低）
        if is_final and dist < 1.0:
            v = max(v, 0.05)
        elif v < min_speed and v > 0:
            v = min_speed

    # 视野状态减速：只在视野极少或进入 approach/fallback 时明显降速，
    # 避免当前窄视野配置在普通直线段长期误触发。
    view_factor = 1.0
    if isinstance(in_view_count, (int, float)):
        if in_view_count <= very_low_view_threshold:
            view_factor = very_low_view_speed_factor
        elif in_view_count <= low_view_threshold:
            view_factor = low_view_speed_factor

    mode_factor = {
        "tracking": 1.0,
        "finished": 1.0,
        "approach": approach_mode_factor,
        "fallback": fallback_mode_factor,
    }.get(mode, 1.0)

    turn_factor = 1.0
    if upcoming_turn_angle_deg >= sharp_turn_angle_deg:
        turn_factor = sharp_turn_speed_factor
    elif upcoming_turn_angle_deg >= turn_slowdown_angle_deg:
        turn_factor = turn_speed_factor

    cte_factor = 1.0
    if cross_track_error_m is not None:
        if cross_track_error_m >= cross_track_stop_error_m:
            cte_factor = max(0.0, min(1.0, cross_track_recovery_factor))
        elif cross_track_error_m >= cross_track_slowdown_error_m:
            span = max(1e-6, cross_track_stop_error_m - cross_track_slowdown_error_m)
            ratio = (cross_track_error_m - cross_track_slowdown_error_m) / span
            cte_factor = max(cross_track_recovery_factor, 1.0 - 0.7 * ratio)

    speed_limit_factor = 1.0
    if segment_speed_limit is not None and max_speed > 0:
        speed_limit_factor = max(0.0, min(1.0, float(segment_speed_limit) / max_speed))

    speed_factor = min(view_factor, mode_factor, turn_factor, cte_factor, speed_limit_factor)
    if v > 0.0:
        v *= speed_factor
        if v < min_speed:
            v = min_speed

    # 角速度保留至少一半，低速时仍能完成转向。
    if speed_factor < 1.0:
        w *= max(speed_factor, 0.5)

    status = None
    if error_deg >= pivot_th:
        status = "pivot"
    elif speed_factor < 1.0:
        status = "slowdown"

    result = {
        "linear_velocity": v,
        "angular_velocity": w,
        "timestamp": now,
        "speed_factor": speed_factor,
        "dist_factor": dist_factor,
        "view_factor": view_factor,
        "mode_factor": mode_factor,
        "turn_factor": turn_factor,
        "cte_factor": cte_factor,
        "speed_limit_factor": speed_limit_factor,
    }
    if segment_speed_limit is not None:
        result["segment_speed_limit_mps"] = float(segment_speed_limit)
    if cross_track_error_m is not None:
        result["cross_track_error_m"] = cross_track_error_m
        result["cross_track_recovery_factor"] = cross_track_recovery_factor
    if status:
        result["status"] = status
    return result
