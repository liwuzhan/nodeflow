#!/usr/bin/env python3
"""
Waypoint Selector 节点 (L3 分子层)

功能: 基于视野区域的前瞻点选择
- 接收全局路径和车辆姿态
- 调用 atom.py 的核心算法
- 输出前瞻点给下游控制器

L3 职责: 只负责数据收发，不负责算法逻辑
"""

import time
from typing import Tuple

# Pydantic 导入
try:
    from pydantic import BaseModel, Field
except ImportError:
    class BaseModel: pass
    def Field(*args, **kwargs): return None

from edge.sdk.nodeflow_sdk import NodeFlowSDK
if __package__:
    from .atom import WaypointSelector, ViewConfig
else:
    from atom import WaypointSelector, ViewConfig

# --- Schema Definitions ---

class GlobalPath(BaseModel):
    task_id: str
    timestamp: float
    path: list  # List[Tuple[float, float]]
    status: str
    message: str

class OperationPlan(BaseModel):
    task_id: str
    timestamp: float
    path: list
    path_zones: list = []
    segments: list = []
    status: str = "success"
    summary: dict = {}

class PathProgress(BaseModel):
    task_id: str | None = None
    segment_type: str | None = None
    path_index: int = 0
    segment_fraction: float = 0.0
    cross_track_error_m: float = 0.0

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
    arrived: bool = False
    goal_distance_m: float = 0.0
    index: int = 0
    total: int = 0
    consumed: int = 0
    in_view_count: int = 0
    mode: str = "unknown"
    zone: str = ""  # "work" / "transit" / "" (auto)
    upcoming_turn_angle_deg: float = 0.0
    upcoming_turn_distance: float = 0.0
    execution_progress: dict | None = None
    execution_phase: str = ""
    execution_heading_rad: float | None = None
    execution_stage_index: int | None = None

# --- End Schema Definitions ---

def main():
    with NodeFlowSDK(log_level="INFO") as sdk:
        sdk.logger.info("Waypoint Selector Node started (视野区域算法)")

        # 1. 读取参数
        view_distance = float(sdk.params.get("view_distance", 3.0))
        view_width = float(sdk.params.get("view_width", 4.0))
        view_depth = float(sdk.params.get("view_depth", 1.5))
        goal_tolerance = float(sdk.params.get("goal_tolerance", 1.5))
        max_search_points = int(sdk.params.get("max_search_points", 100))

        sdk.logger.info(
            f"视野参数: 距离={view_distance}m, 宽度={view_width}m, 深度={view_depth}m"
        )
        sdk.logger.info(f"终点容差: {goal_tolerance}m, 最大搜索: {max_search_points}点")

        # 初始消费参数
        initial_check_points = int(sdk.params.get("initial_check_points", 10))
        initial_consume_distance = float(sdk.params.get("initial_consume_distance", 2.0))

        # 视野自动扩宽参数
        min_view_points = int(sdk.params.get("min_view_points", 3))
        view_expand_factor = float(sdk.params.get("view_expand_factor", 2.0))
        max_view_width = float(sdk.params.get("max_view_width", 12.0))

        # 持续消费参数
        continuous_consume_distance = float(sdk.params.get("continuous_consume_distance", 1.5))
        turn_preview_distance = float(sdk.params.get("turn_preview_distance", 8.0))
        progress_sync_max_cross_track_m = float(sdk.params.get("progress_sync_max_cross_track_m", 6.0))
        progress_sync_fraction_threshold = float(sdk.params.get("progress_sync_fraction_threshold", 0.2))
        progress_target_enabled = bool(sdk.params.get("progress_target_enabled", True))
        progress_target_lookahead_m = float(sdk.params.get("progress_target_lookahead_m", view_distance))
        progress_target_turn_lookahead_m = float(
            sdk.params.get("progress_target_turn_lookahead_m", 1.5)
        )
        progress_target_max_cross_track_m = float(
            sdk.params.get("progress_target_max_cross_track_m", progress_sync_max_cross_track_m)
        )
        progress_timeout_s = float(sdk.params.get("progress_timeout_s", 0.5))

        sdk.logger.info(f"初始消费: 检查{initial_check_points}点, 距离<{initial_consume_distance}m")
        sdk.logger.info(f"视野扩宽: 最少{min_view_points}点, 扩宽x{view_expand_factor}, 最大{max_view_width}m")
        sdk.logger.info(f"持续消费: 距离<{continuous_consume_distance}m")
        sdk.logger.info(f"转弯预判: 向前预览{turn_preview_distance}m")
        sdk.logger.info(
            f"路径进度同步: 横向误差<={progress_sync_max_cross_track_m}m, "
            f"segment_fraction>={progress_sync_fraction_threshold}"
        )
        sdk.logger.info(
            f"路径进度前瞻: enabled={progress_target_enabled}, "
            f"lookahead={progress_target_lookahead_m}m, "
            f"turn_lookahead={progress_target_turn_lookahead_m}m, "
            f"横向误差<={progress_target_max_cross_track_m}m"
        )

        # 2. 初始化 L4 原子层算法
        config = ViewConfig(
            view_distance=view_distance,
            view_width=view_width,
            view_depth=view_depth,
            goal_tolerance=goal_tolerance,
            max_search_points=max_search_points,
            initial_check_points=initial_check_points,
            initial_consume_distance=initial_consume_distance,
            min_view_points=min_view_points,
            view_expand_factor=view_expand_factor,
            max_view_width=max_view_width,
            continuous_consume_distance=continuous_consume_distance,
            turn_preview_distance=turn_preview_distance,
            progress_sync_max_cross_track_m=progress_sync_max_cross_track_m,
            progress_sync_fraction_threshold=progress_sync_fraction_threshold,
            progress_target_enabled=progress_target_enabled,
            progress_target_lookahead_m=progress_target_lookahead_m,
            progress_target_turn_lookahead_m=progress_target_turn_lookahead_m,
            progress_target_max_cross_track_m=progress_target_max_cross_track_m
        )
        selector = WaypointSelector(config)

        # 3. 创建端口
        in_path = sdk.create_input_port("global_path")
        in_plan = sdk.create_input_port("operation_plan")
        in_pose = sdk.create_input_port("pose_enu")
        in_progress = sdk.create_input_port("path_progress")
        out_np = sdk.create_output_port("next_point", schema=NextPoint)

        # 缓存最新位置
        last_pose = None
        last_progress = None
        last_progress_received_at = None

        # 4. 主循环 (L3 职责: 数据搬运)
        while True:
            # 4a. 接收输入 (非阻塞)
            plan_pkt = in_plan.recv_latest()
            path_pkt = in_path.recv_latest()
            pose = in_pose.recv_latest()
            progress = in_progress.recv_latest()
            received_at = time.monotonic()

            # 更新位置缓存
            if pose:
                last_pose = pose

            # operation_plan 优先，兼容旧 global_path。
            if plan_pkt:
                plan_path = plan_pkt.get("path", [])
                if isinstance(plan_path, dict):
                    plan_path = plan_path.get("points", [])
                path_pkt = {
                    "task_id": plan_pkt.get("task_id"),
                    "plan_revision": plan_pkt.get("plan_revision", 0),
                    "timestamp": plan_pkt.get("timestamp"),
                    "path": plan_path,
                    "path_zones": plan_pkt.get("path_zones", []),
                    "segments": plan_pkt.get("segments", []),
                    "summary": plan_pkt.get("summary", {}),
                    "status": plan_pkt.get("status", "success"),
                    "message": "Loaded from operation_plan",
                }

            # 接收新路径时，调用 L4 原子设置路径
            if path_pkt:
                info = selector.set_path(path_pkt, initial_pose=last_pose)
                if info:
                    last_progress = None
                    last_progress_received_at = None
                    sdk.logger.info(
                        f"[路径更新] 起点: ({info['start_x']:.1f}, {info['start_y']:.1f}), "
                        f"共 {info['count']} 个点, 初始消费: {info['initial_consumed']} 个"
                    )
                    if last_pose:
                        cx, cy = last_pose.get("x", 0), last_pose.get("y", 0)
                        dist = WaypointSelector.euclidean_distance(
                            cx, cy, info['start_x'], info['start_y']
                        )
                        sdk.logger.info(
                            f"[路径更新] 当前位置: ({cx:.1f}, {cy:.1f}), 距起点: {dist:.1f}m"
                        )

            if progress:
                last_progress = progress
                last_progress_received_at = received_at
                selector.sync_progress(progress)

            if (
                last_progress_received_at is not None
                and progress_timeout_s > 0
                and received_at - last_progress_received_at > progress_timeout_s
            ):
                # 上游投影停止更新时，用当前位姿继续本地选点，不能持续重发旧目标。
                last_progress = None
                last_progress_received_at = None

            # 4b. 调用 L4 原子层算法选择前瞻点
            if last_pose:
                npkt = selector.select(last_pose, progress=last_progress)

                # 4c. 发送输出 (L3 职责)
                if npkt:
                    out_np.send(npkt)

                    # 定期输出状态日志 (每 5 秒)
                    if int(time.time()) % 5 == 0:
                        sdk.logger.debug(
                            f"[前瞻点] ({npkt['x']:.1f}, {npkt['y']:.1f}) "
                            f"| 模式: {npkt['mode']} "
                            f"| 已消费: {npkt['consumed']}/{npkt['total']} "
                            f"| 视野内: {npkt['in_view_count']}"
                        )

            # 4d. 休眠
            time.sleep(0.005)  # 200Hz


if __name__ == "__main__":
    main()
