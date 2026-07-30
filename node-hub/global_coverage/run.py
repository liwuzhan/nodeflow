#!/usr/bin/env python3
"""
全局路径规划节点
接收作业任务请求，输出全覆盖路径（ENU坐标）
"""

import sys
import time
import json
import traceback
import os
from pathlib import Path
from typing import List, Optional, Dict, Any, Tuple
from datetime import datetime

# Pydantic 导入
try:
    from pydantic import BaseModel, Field
except ImportError:
    # 简单的兼容性处理
    class BaseModel: pass
    def Field(*args, **kwargs): return None

from sdk.nodeflow_sdk import NodeFlowSDK
from utils.planner import GlobalCoveragePlanner
from utils.models import VehicleConfig, ParcelData
from utils.operation_plan import build_operation_plan

# --- Schema Definitions ---

class TaskENU(BaseModel):
    id: str
    parcel: Dict[str, Any]
    vehicle: Dict[str, Any]
    ref_lon: float
    ref_lat: float
    timestamp: float
    plan_revision: int = 0

class GlobalPath(BaseModel):
    task_id: str
    timestamp: float
    path: List[Tuple[float, float]]
    status: str
    message: str
    plan_revision: int = 0

class OperationPlan(BaseModel):
    task_id: str
    timestamp: float
    frame: str
    path: List[Tuple[float, float]]
    path_zones: List[str]
    segments: List[Dict[str, Any]]
    status: str
    summary: Dict[str, Any]
    plan_revision: int = 0

# --- End Schema Definitions ---


def _as_bool(value: Any, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    if isinstance(value, str):
        return value.strip().lower() in ("true", "1", "yes", "on")
    return default

def save_path_to_txt(path_points: List[Tuple[float, float]], task_id: str, txt_dir: Path, logger) -> None:
    """
    保存关键转折点到txt文件，最多保存5个文件

    Args:
        path_points: 关键转折点列表（密化前的原始路径点）[(x, y), ...]
        task_id: 任务ID
        txt_dir: txt目录路径
        logger: 日志记录器
    """
    try:
        # 确保txt目录存在
        txt_dir.mkdir(exist_ok=True)

        # 生成带时间戳的文件名
        timestamp_str = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"path_{timestamp_str}_{task_id}.txt"
        filepath = txt_dir / filename

        # 写入关键转折点数据
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(f"# Task ID: {task_id}\n")
            f.write(f"# Timestamp: {timestamp_str}\n")
            f.write(f"# Keypoints: {len(path_points)} (关键转折点，密化前)\n")
            f.write(f"# Format: x(m), y(m)\n")
            f.write("#" + "-" * 50 + "\n")

            for i, (x, y) in enumerate(path_points):
                f.write(f"{x:.6f}, {y:.6f}\n")

        logger.info(f"✓ 关键转折点已保存: {filename} ({len(path_points)}个点)")

        # 清理旧文件，保持最多5个
        txt_files = sorted(txt_dir.glob("path_*.txt"), key=lambda p: p.stat().st_mtime, reverse=True)
        if len(txt_files) > 5:
            for old_file in txt_files[5:]:
                old_file.unlink()
                logger.info(f"✓ 删除旧文件: {old_file.name}")

    except Exception as e:
        logger.error(f"✗ 保存轨迹点失败: {e}")
        logger.debug(f"错误堆栈:\n{traceback.format_exc()}")

def main():
    """主函数"""
    try:
        # 初始化SDK
        with NodeFlowSDK(log_level="DEBUG") as sdk:
            sdk.logger.info("=" * 70)
            sdk.logger.info("全球覆盖路径规划节点启动 (ENU模式)")
            sdk.logger.info("模式: 接收ENU任务 -> 规划全覆盖路径 -> 输出ENU坐标")
            sdk.logger.info("=" * 70)

            # 初始化txt目录
            txt_dir = Path(__file__).parent / "txt"
            sdk.logger.info(f"轨迹保存目录: {txt_dir}")

            # 读取参数
            path_point_spacing = float(sdk.params.get('path_point_spacing', 0.5))
            planning_strategy = str(sdk.params.get('planning_strategy', 'parallel'))
            turn_angle_threshold_deg = float(sdk.params.get('turn_angle_threshold_deg', 45.0))
            turn_zone_radius_m = float(sdk.params.get('turn_zone_radius_m', 4.0))
            work_speed_limit_mps = float(sdk.params.get('work_speed_limit_mps', 1.2))
            turn_speed_limit_mps = float(sdk.params.get('turn_speed_limit_mps', 0.5))
            smooth_turns = _as_bool(sdk.params.get('smooth_turns', False))
            turn_smoothing_radius_m = sdk.params.get('turn_smoothing_radius_m', None)
            if turn_smoothing_radius_m is not None:
                turn_smoothing_radius_m = float(turn_smoothing_radius_m)
            turn_smoothing_min_angle_deg = float(sdk.params.get('turn_smoothing_min_angle_deg', 35.0))
            sdk.logger.info(f"路径点间距: {path_point_spacing}m")
            sdk.logger.info(f"规划策略: {planning_strategy}")
            sdk.logger.info(
                f"作业语义: 转角阈值={turn_angle_threshold_deg}°, "
                f"掉头半径={turn_zone_radius_m}m, "
                f"作业限速={work_speed_limit_mps}m/s, 掉头限速={turn_speed_limit_mps}m/s"
            )
            sdk.logger.info(
                f"掉头圆角: {'启用' if smooth_turns else '关闭'}, "
                f"半径={turn_smoothing_radius_m if turn_smoothing_radius_m is not None else 'auto'}m, "
                f"最小角={turn_smoothing_min_angle_deg}°"
            )

            # 初始化规划器（输出ENU坐标），传递logger用于详细日志
            planner = GlobalCoveragePlanner(output_enu=True, logger=sdk.logger)

            # 创建端口
            input_port = sdk.create_input_port('task_enu')
            output_port = sdk.create_output_port('global_path', schema=GlobalPath)
            operation_plan_port = sdk.create_output_port('operation_plan', schema=OperationPlan)

            last_task_identity = None
            task_count = 0

            sdk.logger.info("等待任务数据...")
            sdk.logger.info("端口已创建: input=task_enu, output=global_path")

            try:
                while True:
                    # 读取最新任务请求
                    task_data = input_port.recv_latest()

                    if task_data:
                        # ===== 数据验证日志 =====
                        sdk.logger.debug(f"[数据校验] 接收数据类型: {type(task_data)}")

                        # 验证数据结构
                        if not isinstance(task_data, dict):
                            sdk.logger.error(f"[数据错误] 期望字典但得到: {type(task_data)}")
                            time.sleep(0.1)
                            continue
                        # ===== 数据验证日志结束 =====

                        task_id = task_data.get('id')
                        plan_revision = int(task_data.get('plan_revision', 0) or 0)
                        task_identity = (task_id, plan_revision)

                        # 仅处理新任务
                        if task_id and task_identity != last_task_identity:
                            task_count += 1
                            # 显示任务的参考点信息（从task_enu获取）
                            ref_lon = task_data.get('ref_lon')
                            ref_lat = task_data.get('ref_lat')

                            sdk.logger.info("-" * 70)
                            sdk.logger.info(
                                f"[任务#{task_count}] 收到新任务: {task_id} v{plan_revision}"
                            )
                            if ref_lon and ref_lat:
                                sdk.logger.info(f"  GPS参考点: ({ref_lon:.6f}°, {ref_lat:.6f}°)")
                            else:
                                sdk.logger.warning(f"  警告: GPS参考点缺失")

                            try:
                                # 解析数据
                                parcel_dict = task_data.get('parcel', {})
                                vehicle_dict = task_data.get('vehicle', {})

                                sdk.logger.debug(f"  解析地块数据...")
                                parcel = ParcelData.from_dict(parcel_dict)
                                vehicle = VehicleConfig.from_dict(vehicle_dict)

                                # 数据验证
                                if not parcel.outer or len(parcel.outer) < 3:
                                    sdk.logger.error(f"  [数据错误] 地块边界点不足 (需要≥3个, 实际{len(parcel.outer)}个)")
                                    continue

                                sdk.logger.info(f"  地块数据: {len(parcel.outer)}个外边界点, {len(parcel.holes)}个孔洞, {len(parcel.points)}个点障碍")
                                sdk.logger.info(f"  车辆配置: 幅宽={vehicle.implement_width_m}m, 重叠率={vehicle.overlap_ratio}, 内缩={vehicle.path_inset_m}m")
                                sdk.logger.info(f"开始执行路径规划...")

                                start_time = time.time()

                                # 执行规划（使用配置的点间距）
                                path_points = planner.plan(
                                    parcel,
                                    vehicle,
                                    path_point_spacing,
                                    smooth_turns=smooth_turns,
                                    turn_smoothing_radius_m=turn_smoothing_radius_m,
                                    turn_smoothing_min_angle_deg=turn_smoothing_min_angle_deg,
                                    planning_strategy=planning_strategy,
                                )

                                duration = time.time() - start_time
                                sdk.logger.info(f"✓ 规划执行完成 - 耗时={duration*1000:.1f}ms, 生成{len(path_points)}个路径点")

                                # 保存关键转折点到txt文件（密化前的原始路径点）
                                if planner.last_keypoints:
                                    save_path_to_txt(planner.last_keypoints, task_id, txt_dir, sdk.logger)

                                # 发送结果
                                timestamp = time.time()
                                operation_plan = build_operation_plan(
                                    task_id=task_id,
                                    path=path_points,
                                    vehicle=vehicle,
                                    timestamp=timestamp,
                                    turn_angle_threshold_deg=turn_angle_threshold_deg,
                                    turn_zone_radius_m=turn_zone_radius_m,
                                    work_speed_mps=work_speed_limit_mps,
                                    turn_speed_mps=turn_speed_limit_mps,
                                    path_zones=planner.last_path_zones,
                                    planner_metadata=planner.last_plan_metadata,
                                )
                                operation_plan['plan_revision'] = plan_revision
                                result = {
                                    'task_id': task_id,
                                    'timestamp': timestamp,
                                    'path': path_points,
                                    'path_zones': operation_plan.get('path_zones', []),
                                    'segments': operation_plan.get('segments', []),
                                    'planner': planner.last_plan_metadata,
                                    'status': 'success' if path_points else 'failed',
                                    'message': 'Path found' if path_points else 'No path found',
                                    'plan_revision': plan_revision,
                                }

                                # ===== 持续发送路径 (确保下游随时可接收) =====
                                sdk.logger.info(f"开始持续发送规划结果: {len(path_points)}个路径点 @ 10Hz频率")
                                last_task_identity = task_identity
                                send_count = 0

                                while True:
                                    # 持续发送当前路径
                                    now = time.time()
                                    result['timestamp'] = now
                                    operation_plan['timestamp'] = now
                                    output_port.send(result)
                                    operation_plan_port.send(operation_plan)
                                    send_count += 1

                                    # 定期日志
                                    if send_count % 10 == 0:
                                        sdk.logger.debug(f"[发送计数] 已发送{send_count}次 (task={task_id})")

                                    # 检查是否有新任务
                                    new_task = input_port.recv_latest()
                                    if new_task and isinstance(new_task, dict):
                                        new_task_id = new_task.get('id')
                                        new_revision = int(new_task.get('plan_revision', 0) or 0)
                                        if new_task_id and (new_task_id, new_revision) != last_task_identity:
                                            sdk.logger.info(
                                                f"接收到新任务/计划版本，停止发送当前路径: "
                                                f"{new_task_id} v{new_revision}"
                                            )
                                            break  # 退出循环，重新规划新任务

                                    time.sleep(0.1)  # 10Hz发送频率，与RTK发送频率协调
                                # ===== 持续发送结束 =====

                            except Exception as e:
                                sdk.logger.error(f"✗ 规划失败: {e}")
                                sdk.logger.debug(f"错误堆栈:\n{traceback.format_exc()}")
                                # 发送错误状态
                                error_result = {
                                    'task_id': task_id,
                                    'timestamp': time.time(),
                                    'path': [],
                                    'path_zones': [],
                                    'segments': [],
                                    'status': 'error',
                                    'message': str(e)
                                }
                                output_port.send(error_result)
                                operation_plan_port.send({
                                    'task_id': task_id,
                                    'timestamp': time.time(),
                                    'frame': 'ENU',
                                    'path': [],
                                    'path_zones': [],
                                    'segments': [],
                                    'status': 'error',
                                    'summary': {'path_points': 0, 'segment_count': 0},
                                    'message': str(e),
                                })
                    
                    # 避免空转占用CPU，但保持一定的响应速度
                    time.sleep(0.1)
                    
            except KeyboardInterrupt:
                sdk.logger.info("Received interrupt signal, shutting down...")

    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        traceback.print_exc()
        sys.exit(1)

if __name__ == '__main__':
    main()
