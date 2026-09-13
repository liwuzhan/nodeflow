#!/usr/bin/env python3
import time
import math
import os
from typing import Optional, Any

# Pydantic 导入
try:
    from pydantic import BaseModel, Field
except ImportError:
    class BaseModel: pass
    def Field(*args, **kwargs): return None

from edge.sdk.nodeflow_sdk import NodeFlowSDK
if __package__:
    from .atom import ControlSafetyGuard, compute_velocity_cmd, validate_tracking_configuration
else:
    from atom import ControlSafetyGuard, compute_velocity_cmd, validate_tracking_configuration

# --- Schema Definitions ---

class PoseENU(BaseModel):
    x: float
    y: float
    theta: float
    timestamp: float
    rtk_status: Any

class NextPoint(BaseModel):
    x: float
    y: float
    final: bool
    arrived: bool = False
    index: Optional[int] = None
    total: Optional[int] = None
    consumed: Optional[int] = None
    in_view_count: Optional[int] = None
    mode: Optional[str] = None
    upcoming_turn_angle_deg: Optional[float] = None
    upcoming_turn_distance: Optional[float] = None

class PathProgress(BaseModel):
    segment_id: Optional[str] = None
    segment_type: Optional[str] = None
    zone: Optional[str] = None
    path_index: Optional[int] = None
    distance_to_segment_end_m: Optional[float] = None
    cross_track_error_m: Optional[float] = None
    heading_error_deg: Optional[float] = None
    motion: Optional[dict] = None
    implement: Optional[dict] = None

class VelocityCmd(BaseModel):
    linear_velocity: float
    angular_velocity: float
    timestamp: float
    safety_stop: bool = False
    input_age_s: Optional[float] = None
    pivot_elapsed_s: Optional[float] = None
    tracking_method: Optional[str] = None
    curvature_inv_m: Optional[float] = None
    status: Optional[str] = None
    arrived: Optional[bool] = None
    speed_factor: Optional[float] = None
    dist_factor: Optional[float] = None
    view_factor: Optional[float] = None
    mode_factor: Optional[float] = None
    turn_factor: Optional[float] = None
    cte_factor: Optional[float] = None
    speed_limit_factor: Optional[float] = None
    segment_speed_limit_mps: Optional[float] = None
    cross_track_error_m: Optional[float] = None
    cross_track_recovery_factor: Optional[float] = None
    target_mode: Optional[str] = None
    headland_turn: Optional[bool] = None
    heading_error_deg: Optional[float] = None
    progress_heading_error_deg: Optional[float] = None
    headland_turn_align_threshold_deg: Optional[float] = None

# --- End Schema Definitions ---

def main():
    with NodeFlowSDK(log_level="INFO") as sdk:
        sdk.logger.info("Track Controller Node started (ENU coordinates)")

        max_speed = float(sdk.params.get("max_speed", 1.0))
        min_speed = float(sdk.params.get("min_speed", 0.0))
        kp = float(sdk.params.get("heading_p_gain", 2.5))
        max_w = float(sdk.params.get("max_angular_velocity", 1.0))
        pivot_th = float(sdk.params.get("pivot_threshold_deg", 15.0))
        decel_start_dist = float(sdk.params.get("decel_start_distance", 2.0))
        final_stop_dist = float(sdk.params.get("final_stop_distance", 0.5))
        decel_min_factor = float(sdk.params.get("decel_min_factor", 0.3))
        low_view_threshold = int(sdk.params.get("low_view_threshold", 2))
        low_view_speed_factor = float(sdk.params.get("low_view_speed_factor", 0.7))
        very_low_view_threshold = int(sdk.params.get("very_low_view_threshold", 1))
        very_low_view_speed_factor = float(sdk.params.get("very_low_view_speed_factor", 0.45))
        approach_mode_factor = float(sdk.params.get("approach_mode_factor", 0.5))
        fallback_mode_factor = float(sdk.params.get("fallback_mode_factor", 0.3))
        turn_slowdown_angle_deg = float(sdk.params.get("turn_slowdown_angle_deg", 45.0))
        sharp_turn_angle_deg = float(sdk.params.get("sharp_turn_angle_deg", 120.0))
        turn_speed_factor = float(sdk.params.get("turn_speed_factor", 0.65))
        sharp_turn_speed_factor = float(sdk.params.get("sharp_turn_speed_factor", 0.35))
        cross_track_slowdown_error_m = float(sdk.params.get("cross_track_slowdown_error_m", 0.5))
        cross_track_stop_error_m = float(sdk.params.get("cross_track_stop_error_m", 1.5))
        cross_track_recovery_factor = float(sdk.params.get("cross_track_recovery_factor", 0.15))
        headland_turn_heading_gain = float(sdk.params.get("headland_turn_heading_gain", 2.0))
        headland_turn_align_threshold_deg = float(sdk.params.get("headland_turn_align_threshold_deg", 35.0))
        headland_turn_min_speed_factor = float(sdk.params.get("headland_turn_min_speed_factor", 0.25))
        headland_turn_use_path_heading = bool(sdk.params.get("headland_turn_use_path_heading", False))
        tracking_method = sdk.params.get("tracking_method", "heading_p")
        pure_pursuit_min_distance_m = float(sdk.params.get("pure_pursuit_min_distance_m", 0.1))
        validate_tracking_configuration(tracking_method, pure_pursuit_min_distance_m,
                                        headland_turn_use_path_heading)
        pose_timeout_s = float(sdk.params.get("pose_timeout_s", 0.5))
        target_timeout_s = float(sdk.params.get("target_timeout_s", 0.5))
        progress_timeout_s = float(sdk.params.get("progress_timeout_s", 0.5))
        pivot_timeout_s = float(sdk.params.get("pivot_timeout_s", 8.0))
        require_implement_ready = bool(sdk.params.get("require_implement_ready", False))
        allow_work_pivot = bool(sdk.params.get("allow_work_pivot", False))
        implement_status_timeout_s = float(sdk.params.get("implement_status_timeout_s", 0.5))

        sdk.logger.info(f"参数: method={tracking_method}, max_speed={max_speed}, kp={kp}, max_w={max_w}, pivot_th={pivot_th}°")
        sdk.logger.info(
            f"减速参数: decel_start={decel_start_dist}m, min_factor={decel_min_factor}, "
            f"final_stop={final_stop_dist}m"
        )
        sdk.logger.info(
            f"视野/模式减速: low_view<={low_view_threshold}->{low_view_speed_factor}, "
            f"very_low<={very_low_view_threshold}->{very_low_view_speed_factor}, "
            f"approach={approach_mode_factor}, fallback={fallback_mode_factor}"
        )
        sdk.logger.info(
            f"转角预判减速: turn>={turn_slowdown_angle_deg}°->{turn_speed_factor}, "
            f"sharp>={sharp_turn_angle_deg}°->{sharp_turn_speed_factor}"
        )
        sdk.logger.info(
            f"掉头控制: use_path_heading={headland_turn_use_path_heading}, "
            f"heading_gain={headland_turn_heading_gain}, "
            f"align_threshold={headland_turn_align_threshold_deg}°, "
            f"speed_factor<={headland_turn_min_speed_factor}"
        )
        sdk.logger.info(
            f"控制保护: pose_timeout={pose_timeout_s}s, target_timeout={target_timeout_s}s, "
            f"progress_timeout={progress_timeout_s}s, pivot_timeout={pivot_timeout_s}s"
        )

        # 使用ENU坐标
        in_pose = sdk.create_input_port("pose_enu")
        in_np = sdk.create_input_port("next_point")
        in_progress = sdk.create_input_port("path_progress")
        in_tillage = (
            sdk.create_input_port("tillage_status")
            if os.getenv("NODE_IN_tillage_status") else None
        )
        out = sdk.create_output_port("velocity_cmd", schema=VelocityCmd)

        # 本地缓存
        last_pose = None
        last_np = None
        last_progress = None
        last_progress_received_at = None
        last_tillage = None
        last_tillage_received_at = None
        safety_guard = ControlSafetyGuard(
            pose_timeout_s=pose_timeout_s,
            target_timeout_s=target_timeout_s,
            pivot_timeout_s=pivot_timeout_s,
        )

        while True:
            # 尝试读取新数据
            pose = in_pose.recv_latest()
            npkt = in_np.recv_latest()
            progress = in_progress.recv_latest()
            tillage = in_tillage.recv_latest() if in_tillage else None
            received_at = time.monotonic()

            # 更新本地缓存
            if pose:
                last_pose = pose
                safety_guard.note_pose(received_at)
            if npkt:
                last_np = npkt
                safety_guard.note_target(npkt, received_at)
            if progress:
                last_progress = progress
                last_progress_received_at = received_at
            if tillage:
                last_tillage = tillage
                last_tillage_received_at = received_at

            active_progress = last_progress
            if (
                last_progress_received_at is None
                or (
                    progress_timeout_s > 0
                    and received_at - last_progress_received_at > progress_timeout_s
                )
            ):
                active_progress = None

            active_tillage = last_tillage
            if (
                last_tillage_received_at is None
                or (
                    implement_status_timeout_s > 0
                    and received_at - last_tillage_received_at > implement_status_timeout_s
                )
            ):
                active_tillage = None

            # 计算控制命令
            now = time.time()
            cmd = compute_velocity_cmd(
                last_pose,
                last_np,
                max_speed,
                min_speed,
                kp,
                max_w,
                pivot_th,
                decel_start_dist,
                final_stop_dist,
                now,
                decel_min_factor,
                low_view_threshold,
                low_view_speed_factor,
                very_low_view_threshold,
                very_low_view_speed_factor,
                approach_mode_factor,
                fallback_mode_factor,
                turn_slowdown_angle_deg,
                sharp_turn_angle_deg,
                turn_speed_factor,
                sharp_turn_speed_factor,
                active_progress,
                cross_track_slowdown_error_m,
                cross_track_stop_error_m,
                cross_track_recovery_factor,
                headland_turn_heading_gain,
                headland_turn_align_threshold_deg,
                headland_turn_min_speed_factor,
                headland_turn_use_path_heading,
                tillage_status=active_tillage,
                require_implement_ready=require_implement_ready,
                allow_work_pivot=allow_work_pivot,
                tracking_method=tracking_method,
                pure_pursuit_min_distance_m=pure_pursuit_min_distance_m,
            )
            cmd = safety_guard.apply(cmd, now=received_at, timestamp=now)
            cmd["tracking_method"] = tracking_method
            out.send(cmd)
            time.sleep(0.005)  # 200Hz


if __name__ == "__main__":
    main()
