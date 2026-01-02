#!/usr/bin/env python3
import sys
import time
import math
from pathlib import Path
from typing import Optional, Any

# Pydantic 导入
try:
    from pydantic import BaseModel, Field
except ImportError:
    class BaseModel: pass
    def Field(*args, **kwargs): return None

project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from sdk.nodeflow_sdk import NodeFlowSDK
from atom import compute_velocity_cmd

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
    index: Optional[int] = None
    total: Optional[int] = None
    mode: Optional[str] = None

class VelocityCmd(BaseModel):
    linear_velocity: float
    angular_velocity: float
    timestamp: float
    status: Optional[str] = None

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

        sdk.logger.info(f"参数: max_speed={max_speed}, kp={kp}, max_w={max_w}, pivot_th={pivot_th}°")
        sdk.logger.info(f"减速参数: decel_start={decel_start_dist}m, final_stop={final_stop_dist}m")

        # 使用ENU坐标
        in_pose = sdk.create_input_port("pose_enu")
        in_np = sdk.create_input_port("next_point")
        out = sdk.create_output_port("velocity_cmd", schema=VelocityCmd)

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
                now
            )
            out.send(cmd)
            time.sleep(0.02)


if __name__ == "__main__":
    main()
