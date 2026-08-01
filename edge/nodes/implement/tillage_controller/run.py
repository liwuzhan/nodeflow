#!/usr/bin/env python3
"""
旋耕控制器节点 (L3 分子层)

功能: 旋耕机具的 PTO + 三点悬挂控制
- 接收车辆姿态、航点 zone 提示、地块边界
- 调用 atom.py 的状态机算法
- 输出 tillage_cmd 逻辑指令

L3 职责: 只负责数据收发，不负责算法逻辑
"""

import time

try:
    from pydantic import BaseModel, Field
except ImportError:
    class BaseModel: pass
    def Field(*args, **kwargs): return None

from edge.sdk.nodeflow_sdk import NodeFlowSDK
from atom import TillageController, TillageConfig

# --- Schema Definitions ---

class PoseENU(BaseModel):
    x: float
    y: float
    theta: float
    timestamp: float
    rtk_status: dict = {}

class NextPoint(BaseModel):
    x: float
    y: float
    final: bool
    index: int = 0
    total: int = 0
    consumed: int = 0
    in_view_count: int = 0
    mode: str = "unknown"
    zone: str = ""   # "work" / "transit" / "" (auto)

class TaskENU(BaseModel):
    id: str
    parcel: dict
    vehicle: dict
    ref_lon: float
    ref_lat: float
    timestamp: float

class PathProgress(BaseModel):
    segment_id: str = ""
    segment_type: str = ""
    zone: str = ""
    path_index: int = 0
    distance_to_segment_end_m: float = 0.0
    cross_track_error_m: float = 0.0
    heading_error_deg: float = 0.0
    motion: dict = {}
    implement: dict = {}

class TillageCmd(BaseModel):
    pto_on: bool
    hitch_height: float
    timestamp: float
    state: str
    pto_rpm: float = 0.0

class TillageStatus(BaseModel):
    state: str
    hitch_height: float
    pto_on: bool
    pto_rpm: float
    state_elapsed_s: float
    emergency_stop: bool
    last_zone: str
    timestamp: float

# --- End Schema Definitions ---


def main():
    with NodeFlowSDK(log_level="INFO") as sdk:
        sdk.logger.info("Tillage Controller Node started (旋耕状态机)")

        # 1. 读取参数
        hitch_lower_time_s = float(sdk.get_param("hitch_lower_time_s", 1.5))
        hitch_raise_time_s = float(sdk.get_param("hitch_raise_time_s", 1.5))
        headland_width_m = float(sdk.get_param("headland_width_m", 3.0))
        pto_engage_delay_s = float(sdk.get_param("pto_engage_delay_s", 0.5))
        auto_zone_detect = bool(sdk.get_param("auto_zone_detect", True))
        hitch_working_height = float(sdk.get_param("hitch_working_height", 1.0))

        emergency_stop = sdk.get_param("emergency_stop", False)
        if isinstance(emergency_stop, str):
            emergency_stop = emergency_stop.lower() in ("true", "1", "yes")

        enable_verbose_log = bool(sdk.get_param("enable_verbose_log", False))

        sdk.logger.info(
            f"旋耕参数: 降下={hitch_lower_time_s}s, 提升={hitch_raise_time_s}s, "
            f"地头宽={headland_width_m}m, PTO延迟={pto_engage_delay_s}s"
        )
        sdk.logger.info(f"自动区域检测: {auto_zone_detect}, 作业高度: {hitch_working_height}")

        # 2. 初始化 L4 原子层
        config = TillageConfig(
            hitch_lower_time_s=hitch_lower_time_s,
            hitch_raise_time_s=hitch_raise_time_s,
            headland_width_m=headland_width_m,
            pto_engage_delay_s=pto_engage_delay_s,
            auto_zone_detect=auto_zone_detect,
            hitch_working_height=hitch_working_height,
        )
        controller = TillageController(config)

        # 3. 创建端口
        in_pose = sdk.create_input_port("pose_enu")
        in_next_point = sdk.create_input_port("next_point")
        in_task = sdk.create_input_port("task_enu")
        in_progress = sdk.create_input_port("path_progress")
        out_cmd = sdk.create_output_port("tillage_cmd", schema=TillageCmd)
        out_status = sdk.create_output_port("tillage_status", schema=TillageStatus)

        # 缓存最新数据
        last_pose = None
        last_next_point = None
        last_task = None
        last_progress = None
        last_state = None  # 用于检测状态变化

        # 4. 主循环 (L3 职责: 数据搬运)
        sdk.logger.info("Tillage Controller running, waiting for inputs...")

        while True:
            # 4a. 接收输入 (非阻塞)
            pose = in_pose.recv_latest()
            next_point = in_next_point.recv_latest()
            task = in_task.recv_latest()
            progress = in_progress.recv_latest()

            if pose:
                last_pose = pose
            if next_point:
                last_next_point = next_point
            if task:
                last_task = task
                sdk.logger.info(
                    f"[地块] 边界顶点数: {len(task.get('parcel', {}).get('outer', []))}"
                )
            if progress:
                last_progress = progress

            # 4b. 调用 L4 原子层
            cmd = controller.update(
                pose=last_pose,
                next_point=last_next_point,
                task_enu=last_task,
                emergency_stop=emergency_stop,
                path_progress=last_progress,
            )

            # 4c. 发送输出
            out_cmd.send(cmd)

            # 4d. 状态输出
            status = controller.get_status()
            status["timestamp"] = time.time()
            out_status.send(status)

            # 状态变化日志
            current_state = status["state"]
            if current_state != last_state:
                sdk.logger.info(
                    f"[状态] {last_state or 'START'} → {current_state} "
                    f"| PTO={'ON' if cmd['pto_on'] else 'OFF'} "
                    f"| Hitch={cmd['hitch_height']:.2f} "
                    f"| Zone={status['last_zone'] or 'N/A'}"
                )
                last_state = current_state
            elif enable_verbose_log and int(time.time()) % 5 == 0:
                sdk.logger.debug(
                    f"[{current_state}] PTO={'ON' if cmd['pto_on'] else 'OFF'}, "
                    f"Hitch={cmd['hitch_height']:.2f}, "
                    f"Elapsed={status['state_elapsed_s']}s"
                )

            # 4e. 休眠 (50Hz — 机具控制不需要太高频率)
            time.sleep(0.02)


if __name__ == "__main__":
    main()
