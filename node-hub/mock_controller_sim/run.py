#!/usr/bin/env python3
"""
Mock Control Algorithm Simulator Node

功能描述：
模拟自主控制算法，实现纯追踪（Pure Pursuit）算法进行路径跟踪。

可配置参数：
- control_mode (str): 控制模式
  * 'pure_pursuit': 纯追踪算法
  * 'pid': PID控制（预留）
  * 'manual': 手动模式（遵循摇杆输入）
  [default: 'pure_pursuit']

- lookahead_distance (float): 纯追踪的前瞻距离（米）
  [default: 2.0]

- max_steering_angle (float): 最大转向角（弧度）
  [default: 0.5] (约28.6度)

- max_velocity (float): 最大速度（m/s）
  [default: 2.0]

- update_rate_hz (float): 控制更新频率（Hz）
  [default: 50]

- wheelbase (float): 车轴距离（米）
  [default: 1.0]

输入端口：
1. gps_fix: GPS定位数据（从mock_gps或真实定位）
   {
     "latitude": 39.9042,
     "longitude": 116.4074,
     ...
   }

2. path_reference: 参考路径（从mock_path_planner）
   {
     "path": [[116.4074, 39.9042], ...],
     "status": "success"
   }

3. joystick_input: 摇杆输入（可选）
   {
     "linear_velocity": 1.5,
     "angular_velocity": 0.5
   }

输出端口：
- control_command: 控制指令
  {
    "timestamp": 1703024780.5,
    "seq": 1,
    "velocity": 1.5,          // 目标速度 (m/s)
    "steering_angle": 0.2,    // 转向角 (rad)
    "control_mode": "pure_pursuit",
    "crosstrack_error": 0.05  // 路径偏差 (m)
  }

纯追踪算法：
1. 找到距离车辆最近的路径点
2. 计算前瞻距离内的目标点
3. 计算转向角使车向目标点靠近

用途：
- 测试路径跟踪控制
- 验证控制指令的生成和执行
- 模拟自主导航系统
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
    """计算两点间的大圆距离（米）"""
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


def find_nearest_path_point(current_lat, current_lon, path_waypoints):
    """
    找到路径上距离当前位置最近的点

    返回：
    - (index, distance): 最近点的索引和距离
    """
    min_distance = float('inf')
    nearest_index = 0

    for i, waypoint in enumerate(path_waypoints):
        lon, lat = waypoint
        dist = haversine_distance(current_lat, current_lon, lat, lon)

        if dist < min_distance:
            min_distance = dist
            nearest_index = i

    return nearest_index, min_distance


def find_lookahead_target(nearest_index, lookahead_distance, path_waypoints):
    """
    找到前瞻距离内的目标点

    从最近点开始，沿路径方向找到距离最近点大约 lookahead_distance 的点
    """
    cumulative_distance = 0
    current_index = nearest_index

    for i in range(nearest_index, len(path_waypoints) - 1):
        lon1, lat1 = path_waypoints[i]
        lon2, lat2 = path_waypoints[i + 1]

        segment_distance = haversine_distance(lat1, lon1, lat2, lon2)
        cumulative_distance += segment_distance

        if cumulative_distance >= lookahead_distance:
            # 线性插值找到精确的前瞻点
            excess = cumulative_distance - lookahead_distance
            ratio = 1.0 - (excess / segment_distance) if segment_distance > 0 else 0

            target_lat = lat1 + ratio * (lat2 - lat1)
            target_lon = lon1 + ratio * (lon2 - lon1)

            return target_lat, target_lon

    # 如果路径不够长，返回最后一个点
    if len(path_waypoints) > 0:
        lon, lat = path_waypoints[-1]
        return lat, lon

    return None, None


def pure_pursuit_steering(current_lat, current_lon, target_lat, target_lon, wheelbase):
    """
    实现纯追踪算法计算转向角

    参数：
    - current_lat, current_lon: 当前位置
    - target_lat, target_lon: 目标位置
    - wheelbase: 车轴距离（米）

    返回：
    - steering_angle (rad): 转向角（正数=向左，负数=向右）
    """
    # 简化模型：使用方向角直接计算
    # 实际应该包括车辆朝向，这里简化处理

    # 计算目标方向
    delta_lon = target_lon - current_lon
    delta_lat = target_lat - current_lat

    # 转换为米
    delta_lon_m = delta_lon * 111320 * math.cos(math.radians(current_lat))
    delta_lat_m = delta_lat * 111320

    distance_to_target = math.sqrt(delta_lon_m**2 + delta_lat_m**2)

    if distance_to_target < 0.01:
        return 0.0

    # 纯追踪公式：δ = atan(2L * sin(α) / d)
    # 其中：L=轴距，α=目标点相对方向，d=距离
    # 简化版本：δ = atan2(delta_lat_m, delta_lon_m)

    steering_angle = math.atan2(delta_lat_m, delta_lon_m)

    return steering_angle


def main():
    """主函数"""
    with NodeFlowSDK(log_level="INFO") as sdk:
        sdk.logger.info(f"Mock Controller Simulator started: {sdk.node_id}")

        # 1. 读取参数
        control_mode = sdk.get_param('control_mode', 'pure_pursuit')
        lookahead_distance = sdk.get_param('lookahead_distance', 2.0)
        max_steering_angle = sdk.get_param('max_steering_angle', 0.5)
        max_velocity = sdk.get_param('max_velocity', 2.0)
        update_rate_hz = sdk.get_param('update_rate_hz', 50)
        wheelbase = sdk.get_param('wheelbase', 1.0)

        sdk.logger.info(f"Configuration:")
        sdk.logger.info(f"  control_mode: {control_mode}")
        sdk.logger.info(f"  lookahead_distance: {lookahead_distance} m")
        sdk.logger.info(f"  max_steering_angle: {max_steering_angle} rad")
        sdk.logger.info(f"  max_velocity: {max_velocity} m/s")
        sdk.logger.info(f"  update_rate_hz: {update_rate_hz} Hz")
        sdk.logger.info(f"  wheelbase: {wheelbase} m")

        # 2. 创建端口
        gps_input = sdk.create_input_port('gps_fix')
        path_input = sdk.create_input_port('path_reference')
        joystick_input = sdk.create_input_port('joystick_input')
        control_output = sdk.create_output_port('control_command')

        sdk.logger.info("Ports created successfully")

        # 3. 状态变量
        current_path = None
        seq = 0
        sleep_interval = 1.0 / update_rate_hz

        sdk.logger.info("Waiting for sensor inputs...")

        try:
            while True:
                current_time = time.time()

                # 读取最新输入
                gps_data = gps_input.recv_latest()
                path_data = path_input.recv_latest()
                joystick_data = joystick_input.recv_latest()

                # 更新路径缓存
                if path_data is not None:
                    current_path = path_data
                    sdk.logger.info(f"Updated path: {len(current_path.get('path', []))} waypoints")

                # 计算控制指令
                velocity = 0.0
                steering_angle = 0.0
                crosstrack_error = 0.0

                if control_mode == 'manual' and joystick_data:
                    # 手动模式：直接使用摇杆输入
                    velocity = joystick_data.get('linear_velocity', 0.0)
                    steering_angle = joystick_data.get('angular_velocity', 0.0)

                elif control_mode == 'pure_pursuit' and gps_data and current_path:
                    # 纯追踪模式
                    current_lat = gps_data.get('latitude')
                    current_lon = gps_data.get('longitude')
                    path_waypoints = current_path.get('path', [])

                    if current_lat and current_lon and len(path_waypoints) > 1:
                        # 找最近的路径点
                        nearest_idx, nearest_distance = find_nearest_path_point(
                            current_lat, current_lon, path_waypoints
                        )

                        crosstrack_error = nearest_distance

                        # 找前瞻目标点
                        target_lat, target_lon = find_lookahead_target(
                            nearest_idx, lookahead_distance, path_waypoints
                        )

                        if target_lat and target_lon:
                            # 计算转向角
                            steering_angle = pure_pursuit_steering(
                                current_lat, current_lon,
                                target_lat, target_lon,
                                wheelbase
                            )

                            # 限制转向角
                            steering_angle = max(-max_steering_angle, min(max_steering_angle, steering_angle))

                            # 根据偏差调整速度（偏差大时减速）
                            if crosstrack_error > 0.5:
                                velocity = max_velocity * 0.5
                            else:
                                velocity = max_velocity

                # 构建控制指令
                control_cmd = {
                    'timestamp': current_time,
                    'seq': seq,
                    'velocity': round(velocity, 3),
                    'steering_angle': round(steering_angle, 4),
                    'control_mode': control_mode,
                    'crosstrack_error': round(crosstrack_error, 4)
                }

                # 发送控制指令
                control_output.send(control_cmd)

                if seq % update_rate_hz == 0:
                    sdk.logger.debug(
                        f"Control #{seq}: vel={control_cmd['velocity']:.2f} m/s, "
                        f"angle={control_cmd['steering_angle']:.3f} rad, "
                        f"error={control_cmd['crosstrack_error']:.3f} m"
                    )

                seq += 1
                time.sleep(sleep_interval)

        except KeyboardInterrupt:
            sdk.logger.info("Received shutdown signal")
        except Exception as e:
            sdk.logger.error(f"Error in main loop: {e}", exc_info=True)
        finally:
            sdk.logger.info(f"Mock Controller stopped after {seq} control cycles")


if __name__ == '__main__':
    main()
