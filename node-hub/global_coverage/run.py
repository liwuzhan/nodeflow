#!/usr/bin/env python3
"""
全局路径规划节点
接收作业任务请求，输出全覆盖路径（ENU坐标）
"""

import sys
import os
import time
import json
import traceback
from pathlib import Path

# 添加SDK路径
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from sdk.nodeflow_sdk import NodeFlowSDK
from utils.planner import GlobalCoveragePlanner
from utils.models import VehicleConfig, ParcelData


def get_gps_ref(sdk) -> tuple:
    """
    获取GPS参考点（优先级: 参数 > 环境变量 > 默认值）
    """
    # 1. 从参数读取
    ref_lon = sdk.params.get('ref_longitude')
    ref_lat = sdk.params.get('ref_latitude')

    if ref_lon is not None and ref_lat is not None:
        sdk.logger.info(f"GPS参考点从参数读取: ({ref_lon}, {ref_lat})")
        return float(ref_lon), float(ref_lat)

    # 2. 从环境变量读取
    env_lon = os.getenv('GPS_REF_LON')
    env_lat = os.getenv('GPS_REF_LAT')

    if env_lon and env_lat:
        sdk.logger.info(f"GPS参考点从环境变量读取: ({env_lon}, {env_lat})")
        return float(env_lon), float(env_lat)

    # 3. 默认值
    sdk.logger.warning("GPS参考点未配置，使用默认值 (121.5, 31.2)")
    return 121.5, 31.2


def main():
    """主函数"""
    try:
        # 初始化SDK
        with NodeFlowSDK(log_level="INFO") as sdk:
            sdk.logger.info("Global Coverage Planner Node started (ENU output)")

            # 获取GPS参考点
            ref_lon, ref_lat = get_gps_ref(sdk)
            sdk.logger.info(f"GPS参考点: ({ref_lon:.6f}, {ref_lat:.6f})")

            # 初始化规划器（输出ENU坐标）
            planner = GlobalCoveragePlanner(ref_lon=ref_lon, ref_lat=ref_lat, output_enu=True)
            
            # 创建端口
            input_port = sdk.create_input_port('task_request')
            output_port = sdk.create_output_port('global_path')
            
            last_task_id = None
            
            sdk.logger.info("Waiting for tasks...")
            
            try:
                while True:
                    # 读取最新任务请求
                    task_data = input_port.recv_latest()

                    if task_data:
                        # ===== 数据验证日志 =====
                        sdk.logger.debug(f"[DATA_CHECK] Received task_data type: {type(task_data)}")
                        sdk.logger.debug(f"[DATA_CHECK] task_data: {task_data}")

                        # 验证数据结构
                        if not isinstance(task_data, dict):
                            sdk.logger.error(f"[DATA_ERROR] task_data should be dict but got: {type(task_data)}")
                            sdk.logger.error(f"[DATA_ERROR] Content: {task_data}")
                            time.sleep(0.1)
                            continue
                        # ===== 数据验证日志结束 =====

                        task_id = task_data.get('id')
                        
                        # 仅处理新任务
                        if task_id and task_id != last_task_id:
                            sdk.logger.info(f"Received new task: {task_id}")
                            
                            try:
                                # 解析数据
                                parcel_dict = task_data.get('parcel', {})
                                vehicle_dict = task_data.get('vehicle', {})
                                
                                parcel = ParcelData.from_dict(parcel_dict)
                                vehicle = VehicleConfig.from_dict(vehicle_dict)
                                
                                sdk.logger.info(f"Planning path for parcel with {len(parcel.outer)} outer points...")
                                start_time = time.time()
                                
                                # 执行规划
                                path_points = planner.plan(parcel, vehicle)
                                
                                duration = time.time() - start_time
                                sdk.logger.info(f"Planning completed in {duration:.3f}s. Path length: {len(path_points)}")
                                
                                # 发送结果
                                result = {
                                    'task_id': task_id,
                                    'timestamp': time.time(),
                                    'path': path_points,
                                    'status': 'success' if path_points else 'failed',
                                    'message': 'Path found' if path_points else 'No path found'
                                }

                                # ===== 修复: 持续发送路径 (确保下游随时可接收) =====
                                sdk.logger.info(f"开始持续发送路径 (task_id={task_id}, points={len(path_points)})")
                                last_task_id = task_id
                                send_count = 0

                                while True:
                                    # 持续发送当前路径
                                    output_port.send(result)
                                    send_count += 1

                                    # 定期日志
                                    if send_count % 10 == 0:
                                        sdk.logger.debug(f"已发送路径 {send_count} 次 (task_id={task_id})")

                                    # 检查是否有新任务
                                    new_task = input_port.recv_latest()
                                    if new_task and isinstance(new_task, dict):
                                        new_task_id = new_task.get('id')
                                        if new_task_id and new_task_id != last_task_id:
                                            sdk.logger.info(f"收到新任务: {new_task_id}，停止发送旧路径")
                                            break  # 退出循环，重新规划新任务

                                    time.sleep(0.1)  # 10Hz发送频率，与RTK发送频率协调
                                # ===== 修复结束 =====
                                
                            except Exception as e:
                                sdk.logger.error(f"Planning failed: {e}")
                                traceback.print_exc()
                                # 发送错误状态
                                error_result = {
                                    'task_id': task_id,
                                    'timestamp': time.time(),
                                    'path': [],
                                    'status': 'error',
                                    'message': str(e)
                                }
                                output_port.send(error_result)
                    
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
