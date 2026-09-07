import math
from typing import Any, Optional


class ControlSafetyGuard:
    """Track input freshness and stop an unrecoverable continuous pivot."""

    PIVOT_STATUSES = {"pivot", "turn_align"}

    def __init__(
        self,
        pose_timeout_s: float = 0.5,
        target_timeout_s: float = 0.5,
        pivot_timeout_s: float = 8.0,
    ):
        self.pose_timeout_s = max(0.0, float(pose_timeout_s))
        self.target_timeout_s = max(0.0, float(target_timeout_s))
        self.pivot_timeout_s = max(0.0, float(pivot_timeout_s))
        self.last_pose_received_at: Optional[float] = None
        self.last_target_received_at: Optional[float] = None
        self._target_signature = None
        self._pivot_started_at: Optional[float] = None
        self._pivot_timed_out = False

    @staticmethod
    def _signature(target: dict) -> tuple[Any, ...]:
        index = target.get("index")
        if index is not None:
            return ("index", index, bool(target.get("final")), target.get("zone"))
        return (
            "point",
            round(float(target.get("x", 0.0)), 2),
            round(float(target.get("y", 0.0)), 2),
            bool(target.get("final")),
        )

    def note_pose(self, received_at: float) -> None:
        self.last_pose_received_at = received_at

    def note_target(self, target: dict, received_at: float) -> None:
        signature = self._signature(target)
        if signature != self._target_signature:
            self._pivot_started_at = None
            self._pivot_timed_out = False
            self._target_signature = signature
        self.last_target_received_at = received_at

    @staticmethod
    def _stop(timestamp: float, status: str, **details: Any) -> dict:
        return {
            "linear_velocity": 0.0,
            "angular_velocity": 0.0,
            "timestamp": timestamp,
            "status": status,
            "speed_factor": 0.0,
            "safety_stop": True,
            **details,
        }

    def apply(self, command: dict, now: float, timestamp: float) -> dict:
        if self.last_pose_received_at is None:
            return self._stop(timestamp, "waiting_for_pose")
        pose_age = max(0.0, now - self.last_pose_received_at)
        if self.pose_timeout_s > 0 and pose_age > self.pose_timeout_s:
            self._pivot_started_at = None
            self._pivot_timed_out = False
            return self._stop(timestamp, "stale_pose", input_age_s=round(pose_age, 3))

        if self.last_target_received_at is None:
            return self._stop(timestamp, "waiting_for_target")
        target_age = max(0.0, now - self.last_target_received_at)
        if self.target_timeout_s > 0 and target_age > self.target_timeout_s:
            self._pivot_started_at = None
            self._pivot_timed_out = False
            return self._stop(timestamp, "stale_target", input_age_s=round(target_age, 3))

        status = command.get("status")
        if status not in self.PIVOT_STATUSES:
            self._pivot_started_at = None
            self._pivot_timed_out = False
            return command

        if self._pivot_started_at is None:
            self._pivot_started_at = now
        pivot_elapsed = max(0.0, now - self._pivot_started_at)
        if self.pivot_timeout_s > 0 and pivot_elapsed >= self.pivot_timeout_s:
            self._pivot_timed_out = True

        if self._pivot_timed_out:
            return self._stop(
                timestamp,
                "pivot_timeout",
                pivot_elapsed_s=round(pivot_elapsed, 3),
            )
        return command

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
    cross_track_recovery_factor: float = 0.15,
    headland_turn_heading_gain: float = 2.0,
    headland_turn_align_threshold_deg: float = 35.0,
    headland_turn_min_speed_factor: float = 0.25,
    headland_turn_use_path_heading: bool = False,
    tillage_status: dict | None = None,
    require_implement_ready: bool = False,
    allow_work_pivot: bool = False,
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
        tillage_status: 可选机具状态；只使用本次运行收到的未过期状态
        require_implement_ready: 作业段先等机具 ready；未接机具的图保持 false
        allow_work_pivot: 作业段是否允许原地转向，默认禁止
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
    segment_type = None
    path_heading_rad = None
    heading_error_deg_from_progress = None
    work_requested = npkt.get("zone") == "work"
    if path_progress:
        segment_type = path_progress.get("segment_type")
        path_heading_rad = path_progress.get("path_heading_rad")
        heading_error_deg_from_progress = path_progress.get("heading_error_deg")
        motion = path_progress.get("motion", {}) or {}
        segment_speed_limit = motion.get("speed_limit_mps")
        cte = path_progress.get("cross_track_error_m")
        if cte is not None:
            cross_track_error_m = abs(float(cte))
        zone = path_progress.get("zone")
        if zone in ("work", "transit"):
            work_requested = zone == "work"
        elif segment_type:
            work_requested = segment_type == "work"
        implement = path_progress.get("implement", {}) or {}
        if implement.get("pto") == "on" or implement.get("hitch") == "down":
            work_requested = True
        elif implement.get("pto") == "off" or implement.get("hitch") == "up":
            work_requested = False

    # 1. 计算到目标点的距离（欧几里得距离）
    dist = math.sqrt((nx - cx)**2 + (ny - cy)**2)

    # 2. 如果是最终点且距离很近，停止
    if is_final and dist <= final_stop_dist:
        return {
            "linear_velocity": 0.0,
            "angular_velocity": 0.0,
            "timestamp": now,
            "status": "arrived",
            "arrived": True,
            "speed_factor": 0.0,
        }

    if require_implement_ready and work_requested:
        ready = bool(
            tillage_status
            and tillage_status.get("state") == "working"
            and tillage_status.get("pto_on")
            and tillage_status.get("ready", True)
            and not tillage_status.get("emergency_stop", False)
        )
        if not ready:
            return {
                "linear_velocity": 0.0,
                "angular_velocity": 0.0,
                "timestamp": now,
                "status": "waiting_for_implement",
                "speed_factor": 0.0,
            }

    # 3. 计算目标方位角（数学坐标系，弧度）
    target_theta = math.atan2(ny - cy, nx - cx)

    # 4. 当前航向角（数学坐标系，弧度）
    current_theta = float(pose_enu.get("theta", 0.0))

    # 5. 计算航向角误差（数学坐标系，弧度）
    error_rad = normalize_angle(target_theta - current_theta)
    target_mode = "point"
    is_headland_turn = segment_type == "headland_turn"
    if is_headland_turn and headland_turn_use_path_heading and path_heading_rad is not None:
        try:
            path_heading = float(path_heading_rad)
            error_rad = normalize_angle(path_heading - current_theta)
            target_mode = "path_heading"
        except (TypeError, ValueError):
            pass

    # 6. 计算角速度控制命令（P控制）
    # 数学坐标系: CCW为正，无需取反，直接兼容仿真器
    w = kp * error_rad
    if target_mode == "path_heading":
        w = headland_turn_heading_gain * error_rad
    w = max(-max_w, min(max_w, w))

    # 7. 计算线速度
    error_deg = math.degrees(abs(error_rad))
    active_pivot_threshold = pivot_th
    if target_mode == "path_heading":
        active_pivot_threshold = min(pivot_th, headland_turn_align_threshold_deg)

    implement_engaged = bool(
        tillage_status and (
            tillage_status.get("pto_on")
            or float(tillage_status.get("hitch_height", 0.0) or 0.0) > 0.05
        )
    )
    if (
        error_deg >= active_pivot_threshold
        and not allow_work_pivot
        and (work_requested or implement_engaged)
    ):
        # 入土作业不能悄悄退化为原地拧转。保留目标/误差供复盘，
        # 路径入口或过急连接需要重新定位或重新规划。
        return {
            "linear_velocity": 0.0,
            "angular_velocity": 0.0,
            "timestamp": now,
            "status": "needs_reposition",
            "speed_factor": 0.0,
            "heading_error_deg": round(error_deg, 2),
        }

    if error_deg >= active_pivot_threshold:
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
    if is_headland_turn:
        speed_factor = min(speed_factor, max(0.0, min(1.0, headland_turn_min_speed_factor)))

    if v > 0.0:
        v *= speed_factor
        if v < min_speed:
            v = min_speed

    # 边走边转时保留至少一半角速度；原地转向不能再被速度因子削弱。
    if speed_factor < 1.0 and target_mode != "path_heading" and v > 0.0:
        w *= max(speed_factor, 0.5)

    status = None
    if error_deg >= active_pivot_threshold:
        status = "turn_align" if target_mode == "path_heading" else "pivot"
    elif is_headland_turn:
        status = "headland_turn"
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
        "target_mode": target_mode,
    }
    if is_headland_turn:
        result["headland_turn"] = True
        result["heading_error_deg"] = round(error_deg, 2)
        result["headland_turn_align_threshold_deg"] = float(active_pivot_threshold)
        if heading_error_deg_from_progress is not None:
            try:
                result["progress_heading_error_deg"] = float(heading_error_deg_from_progress)
            except (TypeError, ValueError):
                pass
    if segment_speed_limit is not None:
        result["segment_speed_limit_mps"] = float(segment_speed_limit)
    if cross_track_error_m is not None:
        result["cross_track_error_m"] = cross_track_error_m
        result["cross_track_recovery_factor"] = cross_track_recovery_factor
    if status:
        result["status"] = status
    return result
