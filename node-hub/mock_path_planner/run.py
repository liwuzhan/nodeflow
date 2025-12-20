#!/usr/bin/env python3
"""
Mock Path Planner Node

功能描述：
模拟路径规划算法，根据目标点请求生成导航路径（一系列航点）。

可配置参数：
- plan_mode (str): 规划算法模式
  * 'direct_line': 直线路径（最简单）
  * 'grid_search': 网格搜索（模拟障碍物避让）
  * 'astar': A*算法（预留）
  [default: 'direct_line']

- path_length (int): 生成路径的航点数量
  [default: 10]

- spacing_meters (float): 航点间距（米）
  [default: 5.0]

- computation_delay_ms (int): 模拟计算延迟（毫秒）
  用于测试异步处理
  [default: 50]

输入端口：
- target: 目标点请求（JSON格式）
  {
    "task_id": "task_001",
    "target_latitude": 39.9050,
    "target_longitude": 116.4080
  }

输出端口：
- path: 规划路径（JSON格式）
  {
    "task_id": "task_001",
    "timestamp": 1703024780.5,
    "path": [[116.4074, 39.9042], [116.4076, 39.9044], ...],
    "status": "success",
    "computation_time_ms": 25.5
  }

规划逻辑：
- direct_line: 在起点和终点之间生成等间距航点
- grid_search: 添加轻微偏移模拟绕行
- astar: （预留未来扩展）

用途：
- 测试异步请求-响应模式
- 验证路径数据传输
- 模拟计算密集型节点
"""

import json
import time
import math
from pathlib import Path
import sys

# Add SDK to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from sdk.nodeflow_sdk import NodeFlowSDK


def haversine_distance(lat1, lon1, lat2, lon2):
    """
    计算两点间的大圆距离（米）

    使用Haversine公式
    """
    R = 6371000  # 地球半径（米）

    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    delta_phi = math.radians(lat2 - lat1)
    delta_lambda = math.radians(lon2 - lon1)

    a = math.sin(delta_phi / 2)**2 + \
        math.cos(phi1) * math.cos(phi2) * \
        math.sin(delta_lambda / 2)**2

    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))

    return R * c


def interpolate_waypoints(start_lat, start_lon, end_lat, end_lon, num_points):
    """
    在起点和终点之间插值生成航点

    参数：
    - start_lat, start_lon: 起点坐标
    - end_lat, end_lon: 终点坐标
    - num_points: 航点数量

    返回：
    - 航点列表 [[lon, lat], ...]
    """
    waypoints = []

    for i in range(num_points):
        t = i / (num_points - 1) if num_points > 1 else 0

        lat = start_lat + t * (end_lat - start_lat)
        lon = start_lon + t * (end_lon - start_lon)

        waypoints.append([round(lon, 7), round(lat, 7)])

    return waypoints


def plan_path_direct_line(start_lat, start_lon, target_lat, target_lon, num_points):
    """直线路径规划"""
    return interpolate_waypoints(start_lat, start_lon, target_lat, target_lon, num_points)


def plan_path_grid_search(start_lat, start_lon, target_lat, target_lon, num_points):
    """网格搜索路径（模拟绕行）"""
    # 先向右偏移，再向目标点移动（模拟绕过障碍物）
    mid_lat = (start_lat + target_lat) / 2
    mid_lon = start_lon + (target_lon - start_lon) * 0.3

    # 分段插值
    first_half = interpolate_waypoints(start_lat, start_lon, mid_lat, mid_lon, num_points // 2)
    second_half = interpolate_waypoints(mid_lat, mid_lon, target_lat, target_lon, num_points - num_points // 2)

    return first_half + second_half


def main():
    """主函数"""
    with NodeFlowSDK(log_level="INFO") as sdk:
        sdk.logger.info(f"Mock Path Planner node started: {sdk.node_id}")

        # 1. 读取参数
        plan_mode = sdk.get_param('plan_mode', 'direct_line')
        path_length = sdk.get_param('path_length', 10)
        spacing_meters = sdk.get_param('spacing_meters', 5.0)
        computation_delay_ms = sdk.get_param('computation_delay_ms', 50)

        sdk.logger.info(f"Configuration:")
        sdk.logger.info(f"  plan_mode: {plan_mode}")
        sdk.logger.info(f"  path_length: {path_length} waypoints")
        sdk.logger.info(f"  spacing_meters: {spacing_meters} m")
        sdk.logger.info(f"  computation_delay_ms: {computation_delay_ms} ms")

        # 验证参数
        if plan_mode not in ['direct_line', 'grid_search', 'astar']:
            sdk.logger.warning(f"Invalid plan_mode '{plan_mode}', using 'direct_line'")
            plan_mode = 'direct_line'

        # 2. 创建端口
        target_input = sdk.create_input_port('target')
        path_output = sdk.create_output_port('path')

        sdk.logger.info("Ports created: 'target' (input), 'path' (output)")

        # 3. 假设起始位置（可以从配置读取）
        start_latitude = 39.9042
        start_longitude = 116.4074

        sdk.logger.info(f"Starting position: ({start_latitude:.6f}, {start_longitude:.6f})")

        # 4. 主循环
        task_count = 0

        sdk.logger.info("Waiting for target requests...")

        try:
            while True:
                # 非阻塞读取目标请求
                target_request = target_input.recv_latest()

                if target_request is not None:
                    task_start = time.time()

                    task_id = target_request.get('task_id', f'task_{task_count}')
                    target_lat = target_request.get('target_latitude')
                    target_lon = target_request.get('target_longitude')

                    sdk.logger.info(f"Received target request: {task_id}")
                    sdk.logger.debug(f"  Target: ({target_lat:.6f}, {target_lon:.6f})")

                    # 模拟计算延迟
                    time.sleep(computation_delay_ms / 1000.0)

                    # 规划路径
                    if plan_mode == 'direct_line':
                        path = plan_path_direct_line(
                            start_latitude, start_longitude,
                            target_lat, target_lon,
                            path_length
                        )
                    elif plan_mode == 'grid_search':
                        path = plan_path_grid_search(
                            start_latitude, start_longitude,
                            target_lat, target_lon,
                            path_length
                        )
                    else:
                        path = []

                    computation_time = (time.time() - task_start) * 1000  # ms

                    # 计算路径距离
                    total_distance = haversine_distance(
                        start_latitude, start_longitude,
                        target_lat, target_lon
                    )

                    # 构建输出
                    path_data = {
                        'task_id': task_id,
                        'timestamp': time.time(),
                        'path': path,
                        'num_waypoints': len(path),
                        'total_distance_meters': round(total_distance, 2),
                        'status': 'success',
                        'computation_time_ms': round(computation_time, 2),
                        'algorithm': plan_mode
                    }

                    # 发送路径
                    path_output.send(path_data)

                    sdk.logger.info(
                        f"Path generated for {task_id}: {len(path)} waypoints, "
                        f"distance={total_distance:.1f}m, time={computation_time:.1f}ms"
                    )

                    task_count += 1

                # 休眠避免CPU占用过高
                time.sleep(0.1)

        except KeyboardInterrupt:
            sdk.logger.info("Received shutdown signal")
        except Exception as e:
            sdk.logger.error(f"Error in main loop: {e}", exc_info=True)
        finally:
            sdk.logger.info(f"Mock Path Planner stopped after processing {task_count} tasks")


if __name__ == '__main__':
    main()
