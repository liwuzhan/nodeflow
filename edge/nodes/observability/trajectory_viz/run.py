#!/usr/bin/env python3
"""
轨迹可视化节点 (L3层 - 数据搬运)

功能：
- 接收地块边界、规划路径、实际轨迹数据
- 计算轨迹指标（调用L4层atom）
- 启动Web服务器进行实时可视化
- 输出统计信息

职责：仅负责数据收发和调用原子函数，不包含业务逻辑
"""

import time
import os
import json
from datetime import datetime
from typing import Dict, Any, Optional, List, Tuple

from edge.sdk.nodeflow_sdk import NodeFlowSDK
if __package__:
    from . import atom, monitor, web_server
else:
    import atom
    import monitor
    import web_server

# Pydantic Schema (可选)
try:
    from pydantic import BaseModel, Field

    class TrajectoryWebURL(BaseModel):
        """Web可视化输出数据格式"""
        url: str
        timestamp: str
        update_count: int
        stats: Dict[str, Any]
except ImportError:
    TrajectoryWebURL = None


def create_optional_input_port(sdk: NodeFlowSDK, name: str):
    """Create an input port only when the runtime graph connects it."""
    if f"NODE_IN_{name}" not in os.environ:
        print(f"可选端口未连接: {name}")
        return None
    return sdk.create_input_port(name)


def main():
    """节点主函数 (L3 - 傻瓜式循环)"""

    with NodeFlowSDK(log_level="INFO") as sdk:
        print("=" * 70)
        print("轨迹可视化节点启动 (Web 实时版本)")
        print("=" * 70)

        # 1. 读取参数
        web_host = sdk.get_param('web_host', '127.0.0.1')
        web_port = int(sdk.get_param('web_port', 8080))
        update_interval = float(sdk.get_param('update_interval', 5.0))
        frame_interval_s = float(sdk.get_param('frame_interval_s', 0.1))
        scene_interval_s = float(sdk.get_param('scene_interval_s', 1.0))
        stale_after_s = float(sdk.get_param('stale_after_s', 1.0))
        timeout = float(sdk.get_param('timeout', 0.0))
        max_replay_samples = int(sdk.get_param('max_replay_samples', 3000))
        replay_sample_interval = float(sdk.get_param('replay_sample_interval', 0.2))
        implement_length_m = float(sdk.get_param('implement_length_m', 0.2))
        implement_offset_m = float(sdk.get_param('implement_offset_m', 0.0))
        default_implement_length_m = implement_length_m
        default_implement_offset_m = implement_offset_m
        for name, value in (("frame_interval_s", frame_interval_s),
                            ("scene_interval_s", scene_interval_s),
                            ("stale_after_s", stale_after_s)):
            if not 0 < value < float('inf'):
                raise ValueError(f"{name} must be finite and positive")

        print(
            f"配置: host={web_host}, port={web_port}, frame={frame_interval_s}s, "
            f"scene={scene_interval_s}s, log={update_interval}s, "
            f"replay={max_replay_samples}@{replay_sample_interval}s"
        )

        # 2. 启动 Web 服务器 (工具层，daemon线程)
        web_server.start_web_server(host=web_host, port=web_port)
        web_server.reset_monitor_data(max_history=max_replay_samples)
        print(f"Web服务器已启动: http://{web_host}:{web_port}")
        print()

        # 3. 创建端口
        task_port = sdk.create_input_port('task_enu')
        path_port = sdk.create_input_port('global_path')
        plan_port = sdk.create_input_port('operation_plan')
        pose_port = sdk.create_input_port('pose_enu')
        next_point_port = sdk.create_input_port('next_point')
        velocity_port = sdk.create_input_port('velocity_cmd')
        tillage_cmd_port = create_optional_input_port(sdk, 'tillage_cmd')
        tillage_status_port = create_optional_input_port(sdk, 'tillage_status')
        implement_state_port = create_optional_input_port(sdk, 'implement_state')
        truth_port = create_optional_input_port(sdk, 'state_info')
        raw_rtk_port = create_optional_input_port(sdk, 'raw_rtk')
        path_progress_port = sdk.create_input_port('path_progress')
        output_port = sdk.create_output_port('web_url', schema=TrajectoryWebURL)

        print(
            "端口已创建: task_enu, global_path, operation_plan, pose_enu, next_point, "
            "velocity_cmd, tillage_cmd, tillage_status, path_progress -> web_url"
        )
        print()

        # 4. 状态变量 (L3 职责：状态管理)
        current_task_id: Optional[str] = None
        current_task_signature = None
        field_boundary: Optional[List[Tuple[float, float]]] = None
        field_holes = []
        planned_path: Optional[List[Tuple[float, float]]] = None
        path_zones: List[str] = []
        operation_segments: List[Dict[str, Any]] = []
        actual_trajectory: List[Tuple[float, float]] = []
        actual_trajectory_with_heading: List[Tuple[float, float, float]] = []
        implement_width_m = 0.0
        coverage_overlay: Dict[str, Any] = {}
        coverage_accumulator = None
        replay_samples: List[Dict[str, Any]] = []
        replay_events: List[Dict[str, Any]] = []
        last_replay_sample: Optional[Dict[str, Any]] = None
        last_replay_sample_time = 0.0

        # 最新控制/状态包。端口是可选输入，没有连接时保持 None。
        last_pose = None
        last_next_point = None
        last_velocity_cmd = None
        last_tillage_cmd = None
        last_tillage_status = None
        last_tillage_status_received = 0.0
        last_tillage_cmd_received = 0.0
        last_path_progress = None
        last_truth_state = None
        last_truth_received = 0.0
        last_pose_received = 0.0
        last_sample_source_time = -1.0
        monitor_pose = None
        monitor_pose_received = None
        monitor_truth = None
        monitor_truth_received = None
        last_next_point_received = None
        last_velocity_received = None
        last_raw_rtk = None
        last_raw_rtk_received = None
        last_implement_state = None
        last_implement_state_received = None
        last_monitor_record_source = None
        monitor_record_pending = False

        # 统计
        update_count = 0
        pose_count = 0
        last_scene_time = -float('inf')
        last_frame_time = -float('inf')
        last_log_time = time.monotonic()
        start_time = time.monotonic()

        print("等待数据...")

        # 5. 主循环 (L3 核心职责)
        try:
            while True:
                elapsed = time.monotonic() - start_time

                # 5a. 检查超时
                if timeout > 0 and elapsed > timeout:
                    print(f"\n[超时] 达到{timeout}秒，关闭节点")
                    break

                # 5b. 接收数据 (非阻塞，Latest-Value语义)
                task_data = task_port.recv_latest()
                plan_data = plan_port.recv_latest()
                path_data = path_port.recv_latest()
                pose_data = pose_port.recv_latest()
                next_point_data = next_point_port.recv_latest()
                velocity_data = velocity_port.recv_latest()
                tillage_cmd_data = tillage_cmd_port.recv_latest() if tillage_cmd_port else None
                tillage_status_data = tillage_status_port.recv_latest() if tillage_status_port else None
                implement_state_data = implement_state_port.recv_latest() if implement_state_port else None
                path_progress_data = path_progress_port.recv_latest()
                truth_data = truth_port.recv_latest() if truth_port else None
                raw_rtk_data = raw_rtk_port.recv_latest() if raw_rtk_port else None
                received_time = time.monotonic()

                # 5c. 处理 task_enu (地块边界)
                if task_data:
                    task_id = task_data.get("id")
                    task_signature = json.dumps(
                        {key: task_data.get(key) for key in ("id", "parcel", "vehicle")},
                        sort_keys=True,
                    )

                    # 任务切换：清空轨迹
                    if task_signature != current_task_signature:
                        print(f"[新任务] {task_id}")
                        current_task_id = task_id
                        current_task_signature = task_signature
                        field_boundary = None
                        field_holes = []
                        planned_path = None
                        path_zones = []
                        operation_segments = []
                        actual_trajectory = []
                        actual_trajectory_with_heading = []
                        coverage_overlay = {}
                        coverage_accumulator = None
                        replay_samples = []
                        replay_events = []
                        last_replay_sample = None
                        last_replay_sample_time = 0.0
                        last_sample_source_time = -1.0
                        implement_width_m = 0.0
                        implement_length_m = default_implement_length_m
                        implement_offset_m = default_implement_offset_m
                        last_pose = last_truth_state = None
                        last_next_point = last_velocity_cmd = None
                        last_tillage_cmd = last_tillage_status = last_path_progress = None
                        last_pose_received = last_truth_received = 0.0
                        last_tillage_status_received = last_tillage_cmd_received = 0.0
                        monitor_pose = monitor_truth = None
                        monitor_pose_received = monitor_truth_received = None
                        last_next_point_received = last_velocity_received = None
                        last_raw_rtk = last_raw_rtk_received = None
                        last_implement_state = last_implement_state_received = None
                        last_monitor_record_source = None
                        monitor_record_pending = False
                        last_scene_time = last_frame_time = -float('inf')
                        web_server.reset_monitor_data(max_history=max_replay_samples)

                    # 提取边界
                    parcel = task_data.get("parcel", {})
                    outer = parcel.get("outer")
                    if isinstance(outer, list) and len(outer) >= 3:
                        field_boundary = outer
                        field_holes = parcel.get("holes", []) or []
                        print(f"✓ 地块边界: {len(outer)}个点")

                    vehicle = task_data.get("vehicle", {})
                    width = vehicle.get("implement_width_m")
                    if width is not None:
                        try:
                            implement_width_m = float(width)
                        except (TypeError, ValueError):
                            implement_width_m = 0.0
                    implement_length_m = float(vehicle.get("implement_length_m", implement_length_m))
                    implement_offset_m = float(vehicle.get("implement_offset_m", implement_offset_m))
                    if field_boundary and implement_width_m > 0 and coverage_accumulator is None:
                        coverage_accumulator = atom.CoverageAccumulator(
                            field_boundary, implement_width_m, field_holes=field_holes,
                            implement_length_m=implement_length_m, implement_offset_m=implement_offset_m,
                        )

                # operation_plan 优先，兼容旧 global_path。
                if plan_data and (plan_data.get("task_id") is None or current_task_id is None
                                  or plan_data.get("task_id") == current_task_id):
                    plan_path = plan_data.get("path", [])
                    if isinstance(plan_path, dict):
                        plan_path = plan_path.get("points", [])
                    path_data = {
                        "task_id": plan_data.get("task_id"),
                        "timestamp": plan_data.get("timestamp"),
                        "path": plan_path,
                        "path_zones": plan_data.get("path_zones", []),
                        "segments": plan_data.get("segments", []),
                    }

                # 5d. 处理 global_path / operation_plan (规划路径)
                if path_data and (path_data.get("task_id") is None or current_task_id is None
                                  or path_data.get("task_id") == current_task_id):
                    path = path_data.get("path")
                    segments = path_data.get("segments", []) or []
                    if isinstance(path, dict):
                        segments = segments or path.get("segments", []) or []
                        path = path.get("points", []) or []

                    if isinstance(path, list) and len(path) >= 2:
                        planned_path = path
                        path_zones = path_data.get("path_zones", []) or []
                        operation_segments = segments
                        print(f"✓ 规划路径: {len(path)}个点")

                # 5e. 处理 pose_enu (实际轨迹，持续累积)
                if pose_data:
                    last_pose = pose_data
                    last_pose_received = received_time
                    x = pose_data.get("x")
                    y = pose_data.get("y")
                    theta = pose_data.get("theta")

                    if monitor.valid_pose(pose_data):
                        monitor_pose = pose_data
                        monitor_pose_received = received_time
                        actual_trajectory.append((float(x), float(y)))
                        actual_trajectory_with_heading.append((float(x), float(y), float(theta)))
                        pose_count += 1
                        actual_trajectory = actual_trajectory[-max_replay_samples:]
                        actual_trajectory_with_heading = actual_trajectory_with_heading[-max_replay_samples:]

                if truth_data:
                    last_truth_state = truth_data
                    last_truth_received = received_time
                    if monitor.valid_pose(truth_data):
                        monitor_truth = truth_data
                        monitor_truth_received = received_time

                if next_point_data:
                    last_next_point = next_point_data
                    last_next_point_received = received_time
                if velocity_data:
                    last_velocity_cmd = velocity_data
                    last_velocity_received = received_time
                if tillage_cmd_data:
                    last_tillage_cmd = tillage_cmd_data
                    last_tillage_cmd_received = received_time
                if tillage_status_data:
                    last_tillage_status = tillage_status_data
                    last_tillage_status_received = received_time
                if implement_state_data:
                    last_implement_state = implement_state_data
                    last_implement_state_received = received_time
                if path_progress_data:
                    last_path_progress = path_progress_data
                if raw_rtk_data:
                    last_raw_rtk = raw_rtk_data
                    last_raw_rtk_received = received_time

                # 5f. 复盘采样：把最新 pose/control/implement 状态压成低频历史。
                current_time = time.time()
                source_time = last_truth_received if truth_port else last_pose_received
                source_fresh = time.monotonic() - source_time <= max(1.0, replay_sample_interval * 3)
                if (source_fresh and source_time > last_sample_source_time
                        and current_time - last_replay_sample_time >= replay_sample_interval):
                    sample = atom.make_replay_sample(
                        pose=last_pose,
                        velocity_cmd=last_velocity_cmd,
                        next_point=last_next_point,
                        tillage_cmd=(last_tillage_cmd if not tillage_status_port and
                                     time.monotonic()-last_tillage_cmd_received <= 1.0 else None),
                        tillage_status=(last_tillage_status if
                                        time.monotonic()-last_tillage_status_received <= 1.0 else None),
                        path_progress=last_path_progress,
                        now=current_time,
                        truth_state=last_truth_state if truth_port else None,
                    )
                    if coverage_accumulator is not None:
                        if (last_sample_source_time > 0 and source_time-last_sample_source_time
                                > max(1.0, replay_sample_interval*3)):
                            coverage_accumulator.break_segment()
                        coverage_accumulator.add(sample)
                    replay_samples.append(sample)
                    replay_events.extend(atom.detect_replay_events(last_replay_sample, sample))
                    last_replay_sample = sample
                    last_replay_sample_time = current_time
                    last_sample_source_time = source_time

                    if len(replay_samples) > max_replay_samples:
                        overflow = len(replay_samples) - max_replay_samples
                        replay_samples = replay_samples[overflow:]
                    max_events = max(100, max_replay_samples)
                    if len(replay_events) > max_events:
                        replay_events = replay_events[-max_events:]

                    primary_received = monitor_truth_received if truth_port else monitor_pose_received
                    if (primary_received is not None and
                            (last_monitor_record_source is None or primary_received > last_monitor_record_source)):
                        monitor_record_pending = True

                # 5g. 姿态心跳独立发送；断流时冻结最后姿态，并持续增长年龄。
                now_monotonic = time.monotonic()
                if now_monotonic - last_frame_time >= frame_interval_s:
                    frame = monitor.build_monitor_frame(
                        now_monotonic=now_monotonic, timestamp=current_time,
                        task_id=current_task_id, truth_connected=truth_port is not None,
                        truth=monitor_truth, truth_received=monitor_truth_received,
                        estimate=monitor_pose, estimate_received=monitor_pose_received,
                        implement_feedback=last_implement_state,
                        implement_received=last_implement_state_received,
                        implement_status=last_tillage_status,
                        implement_status_received=last_tillage_status_received,
                        target=last_next_point, target_received=last_next_point_received,
                        command=last_velocity_cmd, command_received=last_velocity_received,
                        raw_rtk=last_raw_rtk, rtk_received=last_raw_rtk_received,
                        stale_after_s=stale_after_s,
                    )
                    record_frame = monitor_record_pending and frame["status"] == "live"
                    web_server.update_monitor_frame(frame, record=record_frame)
                    if record_frame:
                        last_monitor_record_source = monitor_truth_received if truth_port else monitor_pose_received
                    monitor_record_pending = False
                    last_frame_time = now_monotonic

                # 地块、路径、覆盖仍按慢速场景节拍处理，不跟随姿态逐帧计算。
                should_update = now_monotonic - last_scene_time >= scene_interval_s

                # 检查是否有足够数据
                has_boundary = field_boundary and len(field_boundary) >= 3
                has_path = planned_path and len(planned_path) >= 2
                has_trajectory = len(actual_trajectory) >= 2
                is_ready = has_boundary and has_path and has_trajectory

                if should_update and (has_boundary or has_path or len(actual_trajectory) > 0):
                    # 计算指标 (调用 L4 原子)
                    metrics = {}
                    if is_ready:
                        try:
                            metrics = atom.calculate_trajectory_metrics(
                                planned_path, actual_trajectory, approach_threshold_m=5.0
                            )
                            metrics["trajectory_metric_scope"] = "recent_observation_window"
                        except Exception as e:
                            print(f"✗ 计算指标失败: {e}")

                    if implement_width_m > 0 and replay_samples:
                        coverage_overlay = atom.build_coverage_overlay(
                            replay_samples,
                            implement_width_m=implement_width_m,
                            field_boundary=field_boundary,
                            field_holes=field_holes,
                            implement_length_m=implement_length_m,
                            implement_offset_m=implement_offset_m,
                            accumulator=coverage_accumulator,
                        )
                        metrics.update({
                            "implement_width_m": coverage_overlay.get("implement_width_m"),
                            "field_area_m2": coverage_overlay.get("field_area_m2"),
                            "covered_area_m2": coverage_overlay.get("covered_area_m2"),
                            "coverage_rate_percent": coverage_overlay.get("coverage_rate_percent"),
                            "coverage_active_segments": coverage_overlay.get("active_segments"),
                            "coverage_sample_count": coverage_overlay.get("sample_count"),
                            "coverage_working_sample_count": coverage_overlay.get("working_sample_count"),
                            "coverage_working_sample_percent": coverage_overlay.get("working_sample_percent"),
                            "coverage_latest_active": coverage_overlay.get("latest_active"),
                            "missed_area_m2": coverage_overlay.get("missed_area_m2"),
                            "repeated_area_m2": coverage_overlay.get("repeated_area_m2"),
                            "outside_area_m2": coverage_overlay.get("outside_area_m2"),
                            "coverage_position_source": coverage_overlay.get("position_source"),
                            "coverage_implement_source": coverage_overlay.get("implement_source"),
                            "coverage_scope": "cumulative",
                        })

                    # 推送到 Web 客户端
                    try:
                        web_server.update_trajectory_data(
                            task_id=current_task_id,
                            field_boundary=field_boundary,
                            field_holes=field_holes,
                            planned_path=planned_path,
                            path_zones=path_zones,
                            operation_segments=operation_segments,
                            actual_trajectory=actual_trajectory,
                            actual_trajectory_with_heading=actual_trajectory_with_heading,
                            metrics=metrics,
                            next_point=last_next_point,
                            velocity_cmd=last_velocity_cmd,
                            tillage_cmd=last_tillage_cmd,
                            tillage_status=last_tillage_status,
                            path_progress=last_path_progress,
                            replay_samples=replay_samples,
                            replay_events=replay_events,
                            coverage_overlay=coverage_overlay,
                        )

                        update_count += 1
                        last_scene_time = now_monotonic

                        # 输出统计信息
                        output_data = {
                            "url": f"http://{web_host}:{web_port}",
                            "timestamp": datetime.now().isoformat(),
                            "update_count": update_count,
                            "stats": metrics
                        }
                        output_port.send(output_data)

                        if now_monotonic - last_log_time >= update_interval:
                            status = "✓ 就绪" if is_ready else "⏳ 等待数据"
                            print(f"[{status}] 轨迹点: {len(actual_trajectory)} | 更新: {update_count}次")
                            last_log_time = now_monotonic

                    except Exception as e:
                        print(f"✗ 推送失败: {e}")

                # 5g. 休眠 (控制CPU占用)
                time.sleep(min(0.1, frame_interval_s))

        except KeyboardInterrupt:
            print("\n[中断] 收到中断信号，关闭节点")

        except Exception as e:
            print(f"\n[错误] {e}")
            import traceback
            traceback.print_exc()

        # 6. 退出统计
        print()
        print("=" * 70)
        print(f"节点统计:")
        print(f"  接收轨迹点数: {pose_count}")
        print(f"  生成可视化次数: {update_count}")
        print(f"  最后任务ID: {current_task_id}")
        print("=" * 70)
        print("🔴 节点退出，Web 服务器将自动关闭（daemon 线程）")
        print("=" * 70)


if __name__ == "__main__":
    main()
