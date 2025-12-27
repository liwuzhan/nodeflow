#!/usr/bin/env python3
"""
轨迹跟踪控制器（ENU版本）
使用ENU坐标系，直接输出兼容仿真器的速度命令
"""
import sys
import time
import math
from pathlib import Path

project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from sdk.nodeflow_sdk import NodeFlowSDK


def normalize_angle(angle_rad: float) -> float:
    """
    归一化角度到 (-π, π] 区间

    Args:
        angle_rad: 角度（弧度）

    Returns:
        归一化后的角度（弧度）
    """
    while angle_rad > math.pi:
        angle_rad -= 2 * math.pi
    while angle_rad <= -math.pi:
        angle_rad += 2 * math.pi
    return angle_rad


def compute_cmd(pose_enu, npkt, max_speed, min_speed, kp, max_w, pivot_th):
    """
    计算速度控制命令（ENU坐标系）

    坐标系约定：
    - pose_enu.theta: 数学坐标系（东=0, CCW正, 弧度）
    - 目标角度: 数学坐标系（atan2计算）
    - angular_velocity: 数学坐标系（CCW正），直接兼容仿真器

    Args:
        pose_enu: 当前姿态 {x, y, theta}
        npkt: 目标点 {x, y, final}
        max_speed: 最大线速度 (m/s)
        min_speed: 最小线速度 (m/s)
        kp: 航向角P增益
        max_w: 最大角速度 (rad/s)
        pivot_th: 原地转向阈值 (度)

    Returns:
        速度命令 {linear_velocity, angular_velocity, timestamp}
    """
    if not pose_enu or not npkt:
        return {"linear_velocity": 0.0, "angular_velocity": 0.0, "timestamp": time.time()}

    cx = pose_enu.get("x", 0.0)
    cy = pose_enu.get("y", 0.0)
    nx = npkt.get("x", cx)
    ny = npkt.get("y", cy)
    is_final = npkt.get("final", False)

    # 1. 计算到目标点的距离（欧几里得距离）
    dist = math.sqrt((nx - cx)**2 + (ny - cy)**2)

    # 2. 如果是最终点且距离很近，停止
    if is_final and dist < 0.5:
        return {"linear_velocity": 0.0, "angular_velocity": 0.0, "timestamp": time.time(), "status": "arrived"}

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
    else:
        # 前进模式：根据角度误差和距离调整速度
        v = max_speed * abs(math.cos(error_rad))

        # 接近目标时减速（距离小于2m时开始减速）
        if dist < 2.0:
            v = v * (dist / 2.0)

        # 最小速度限制（但接近最终点时允许更低）
        if is_final and dist < 1.0:
            v = max(v, 0.05)
        elif v < min_speed and v > 0:
            v = min_speed

    return {"linear_velocity": v, "angular_velocity": w, "timestamp": time.time()}


def main():
    with NodeFlowSDK(log_level="INFO") as sdk:
        sdk.logger.info("Track Controller Node started (ENU coordinates)")

        max_speed = float(sdk.params.get("max_speed", 1.0))
        min_speed = float(sdk.params.get("min_speed", 0.0))
        kp = float(sdk.params.get("heading_p_gain", 2.5))
        max_w = float(sdk.params.get("max_angular_velocity", 1.0))
        pivot_th = float(sdk.params.get("pivot_threshold_deg", 15.0))

        sdk.logger.info(f"参数: max_speed={max_speed}, kp={kp}, max_w={max_w}, pivot_th={pivot_th}°")

        # 使用ENU坐标
        in_pose = sdk.create_input_port("pose_enu")
        in_np = sdk.create_input_port("next_point")
        out = sdk.create_output_port("velocity_cmd")

        # 本地缓存
        last_pose = None
        last_np = None

        while True:
            # 尝试读取新数据
            pose = in_pose.recv_latest()
            npkt = in_np.recv_latest()

            # 更新本地缓存
            if pose:
                last_pose = pose
            if npkt:
                last_np = npkt

            # 计算控制命令
            cmd = compute_cmd(last_pose, last_np, max_speed, min_speed, kp, max_w, pivot_th)
            out.send(cmd)
            time.sleep(0.02)


if __name__ == "__main__":
    main()
