#!/usr/bin/env python3
"""
全局路径规划节点
接收作业任务请求，输出全覆盖路径
"""

import sys
import time
import json
import traceback
from pathlib import Path

# 添加SDK路径
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from sdk.nodeflow_sdk import NodeFlowSDK
from utils.planner import GlobalCoveragePlanner
from utils.models import VehicleConfig, ParcelData

def main():
    """主函数"""
    try:
        # 初始化SDK
        with NodeFlowSDK(log_level="INFO") as sdk:
            sdk.logger.info("Global Coverage Planner Node started")
            
            # 初始化规划器
            planner = GlobalCoveragePlanner()
            
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
                                output_port.send(result)
                                
                                last_task_id = task_id
                                
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
