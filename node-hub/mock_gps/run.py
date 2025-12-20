#!/usr/bin/env python3
"""
Mock GPS/RTK Node

功能描述：
模拟GPS/RTK定位设备，生成高精度位置数据用于测试定位和导航功能。

可配置参数：
- mode (str): 位置生成模式
  * 'stationary': 静止模式，固定位置 + 小噪声
  * 'moving': 移动模式，按恒定速度和方向移动
  * 'trajectory': 轨迹模式（预留，未来可加载轨迹文件）
  [default: 'stationary']

- update_rate_hz (float): 发布频率，单位Hz
  [default: 10]

- start_latitude (float): 起始纬度（十进制度数）
  [default: 39.9042] (北京天安门附近)

- start_longitude (float): 起始经度（十进制度数）
  [default: 116.4074]

- start_altitude (float): 起始高程，单位米
  [default: 50.0]

- velocity_mps (float): 移动速度（米/秒），仅在moving模式生效
  [default: 1.0]

- heading_deg (float): 移动方向（度数，0=北，90=东）
  [default: 45.0]

- accuracy_meters (float): 模拟水平精度（米），用于添加噪声
  [default: 0.05] (RTK级精度)

输出端口：
- gps_fix: GPS定位数据（JSON格式）
  {
    "timestamp": 1703024780.123,
    "seq": 1,
    "latitude": 39.9042,
    "longitude": 116.4074,
    "altitude": 50.0,
    "fix_type": "RTK",
    "num_satellites": 24,
    "horizontal_accuracy": 0.05,
    "vertical_accuracy": 0.10,
    "velocity_east": 0.5,
    "velocity_north": 1.0,
    "velocity_up": 0.0
  }

数据生成逻辑：
- stationary: 固定位置 + 高斯噪声（标准差 = accuracy_meters）
- moving: 根据速度和方向线性移动，使用简化的平面坐标近似
  * 纬度变化 ≈ velocity_north / 111320 度/米
  * 经度变化 ≈ velocity_east / (111320 * cos(latitude)) 度/米

用途：
- 测试位置数据的接收和处理
- 验证地理坐标计算
- 模拟不同的运动状态
"""

import json
import time
import math
import random
from pathlib import Path
import sys

# Add SDK to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from sdk.nodeflow_sdk import NodeFlowSDK


def add_gps_noise(value, accuracy):
    """添加高斯噪声模拟GPS误差"""
    return value + random.gauss(0, accuracy)


def calculate_position_offset(velocity_mps, heading_deg, delta_t, latitude):
    """
    计算位置偏移（简化平面近似）

    参数：
    - velocity_mps: 速度（米/秒）
    - heading_deg: 方向角度（0=北，90=东）
    - delta_t: 时间间隔（秒）
    - latitude: 当前纬度（用于经度修正）

    返回：
    - (delta_lat, delta_lon): 纬度和经度的变化量（度）
    """
    # 将方向角转换为弧度
    heading_rad = math.radians(heading_deg)

    # 计算北向和东向速度分量
    velocity_north = velocity_mps * math.cos(heading_rad)
    velocity_east = velocity_mps * math.sin(heading_rad)

    # 移动距离
    distance_north = velocity_north * delta_t
    distance_east = velocity_east * delta_t

    # 转换为度数变化
    # 1度纬度 ≈ 111320米
    # 1度经度 ≈ 111320 * cos(latitude) 米
    delta_lat = distance_north / 111320.0
    delta_lon = distance_east / (111320.0 * math.cos(math.radians(latitude)))

    return delta_lat, delta_lon, velocity_north, velocity_east


def main():
    """主函数"""
    with NodeFlowSDK(log_level="INFO") as sdk:
        sdk.logger.info(f"Mock GPS node started: {sdk.node_id}")

        # 1. 读取参数
        mode = sdk.get_param('mode', 'stationary')
        update_rate_hz = sdk.get_param('update_rate_hz', 10)
        start_latitude = sdk.get_param('start_latitude', 39.9042)
        start_longitude = sdk.get_param('start_longitude', 116.4074)
        start_altitude = sdk.get_param('start_altitude', 50.0)
        velocity_mps = sdk.get_param('velocity_mps', 1.0)
        heading_deg = sdk.get_param('heading_deg', 45.0)
        accuracy_meters = sdk.get_param('accuracy_meters', 0.05)

        sdk.logger.info(f"Configuration:")
        sdk.logger.info(f"  mode: {mode}")
        sdk.logger.info(f"  update_rate_hz: {update_rate_hz}")
        sdk.logger.info(f"  start_position: ({start_latitude:.6f}, {start_longitude:.6f}, {start_altitude:.1f})")
        sdk.logger.info(f"  velocity: {velocity_mps} m/s, heading: {heading_deg}°")
        sdk.logger.info(f"  accuracy: {accuracy_meters} m")

        # 验证参数
        if mode not in ['stationary', 'moving', 'trajectory']:
            sdk.logger.warning(f"Invalid mode '{mode}', using 'stationary'")
            mode = 'stationary'

        # 2. 创建输出端口
        gps_output = sdk.create_output_port('gps_fix')
        sdk.logger.info("Output port 'gps_fix' created")

        # 3. 初始化位置
        current_latitude = start_latitude
        current_longitude = start_longitude
        current_altitude = start_altitude

        # 4. 主循环
        seq = 0
        start_time = time.time()
        last_time = start_time
        sleep_interval = 1.0 / update_rate_hz

        sdk.logger.info(f"Starting GPS data generation (mode: {mode}, rate: {update_rate_hz} Hz)")

        try:
            while True:
                current_time = time.time()
                delta_t = current_time - last_time

                # 根据模式更新位置
                velocity_north = 0.0
                velocity_east = 0.0

                if mode == 'moving' and delta_t > 0:
                    delta_lat, delta_lon, velocity_north, velocity_east = calculate_position_offset(
                        velocity_mps, heading_deg, delta_t, current_latitude
                    )
                    current_latitude += delta_lat
                    current_longitude += delta_lon
                    # 高程可以保持不变或添加小的变化
                    current_altitude += random.gauss(0, 0.01)

                # 添加噪声
                noisy_latitude = add_gps_noise(current_latitude, accuracy_meters / 111320.0)
                noisy_longitude = add_gps_noise(
                    current_longitude,
                    accuracy_meters / (111320.0 * math.cos(math.radians(current_latitude)))
                )
                noisy_altitude = add_gps_noise(current_altitude, accuracy_meters * 2)

                # 构建GPS数据
                gps_data = {
                    'timestamp': current_time,
                    'seq': seq,
                    'latitude': round(noisy_latitude, 8),
                    'longitude': round(noisy_longitude, 8),
                    'altitude': round(noisy_altitude, 2),
                    'fix_type': 'RTK',
                    'num_satellites': 24,
                    'horizontal_accuracy': accuracy_meters,
                    'vertical_accuracy': accuracy_meters * 2,
                    'velocity_east': round(velocity_east, 3),
                    'velocity_north': round(velocity_north, 3),
                    'velocity_up': 0.0
                }

                # 发送数据
                gps_output.send(gps_data)

                # 每秒记录一次
                if seq % update_rate_hz == 0:
                    sdk.logger.debug(
                        f"Sent GPS fix #{seq}: "
                        f"lat={gps_data['latitude']:.6f}, "
                        f"lon={gps_data['longitude']:.6f}, "
                        f"alt={gps_data['altitude']:.1f}m"
                    )

                seq += 1
                last_time = current_time
                time.sleep(sleep_interval)

        except KeyboardInterrupt:
            sdk.logger.info("Received shutdown signal")
        except Exception as e:
            sdk.logger.error(f"Error in main loop: {e}", exc_info=True)
        finally:
            sdk.logger.info(f"Mock GPS node stopped after {seq} messages")


if __name__ == '__main__':
    main()
