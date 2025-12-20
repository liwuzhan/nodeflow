#!/usr/bin/env python3
"""
Mock IMU (Inertial Measurement Unit) Node

功能描述：
模拟惯性测量单元（IMU），包含加速度计、陀螺仪、磁力计三个传感器的数据。
用于测试传感器融合、姿态估计和运动检测算法。

可配置参数：
- mode (str): 运动模式
  * 'stationary': 静止状态（仅重力加速度 + 噪声）
  * 'accelerating': 加速运动（周期性加速度变化）
  * 'rotating': 旋转运动（周期性角速度变化）
  * 'vibrating': 振动模式（高频小幅振动）
  [default: 'stationary']

- update_rate_hz (float): 发布频率，单位Hz
  [default: 100] (典型IMU频率: 50-200 Hz)

- noise_level (float): 传感器噪声标准差
  [default: 0.01]

- accel_bias_{x,y,z} (float): 加速度计偏置（m/s²）
  [default: 0.0]

- gyro_bias_{x,y,z} (float): 陀螺仪偏置（rad/s）
  [default: 0.0]

输出端口：
- imu_data: IMU传感器数据（JSON格式）
  {
    "timestamp": 1703024780.001,
    "seq": 1,
    "accel_x": 0.1,      // m/s² (X轴加速度)
    "accel_y": 0.0,      // m/s²
    "accel_z": 9.81,     // m/s² (包含重力)
    "gyro_x": 0.0,       // rad/s (X轴角速度)
    "gyro_y": 0.0,       // rad/s
    "gyro_z": 0.05,      // rad/s
    "mag_x": 100,        // μT (X轴磁场强度)
    "mag_y": 50,         // μT
    "mag_z": 200,        // μT
    "temperature": 25.0  // °C (传感器温度)
  }

坐标系定义（NED - North-East-Down）：
- X轴: 前进方向
- Y轴: 右侧方向
- Z轴: 向下方向
- 重力加速度在Z轴正方向（+9.81 m/s²）

数据生成逻辑：
- stationary: accel_z ≈ 9.81, 其他轴接近0 + 噪声
- accelerating: 周期性加速度变化（正弦波）
- rotating: 周期性角速度变化（正弦波）
- vibrating: 高频振动叠加在静止状态上

用途：
- 测试传感器数据融合算法
- 验证姿态估计（AHRS）
- 测试高频数据流处理
- 模拟不同运动状态
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


# 物理常数
GRAVITY = 9.81  # m/s² (地球重力加速度)
EARTH_MAG_FIELD = 50.0  # μT (地球磁场强度，典型值)


def add_noise(value, noise_level):
    """添加高斯噪声"""
    return value + random.gauss(0, noise_level)


def generate_imu_data(mode, t, noise_level, biases):
    """
    生成IMU数据

    参数：
    - mode: 运动模式
    - t: 时间戳（秒）
    - noise_level: 噪声水平
    - biases: 偏置字典 {'accel': [x,y,z], 'gyro': [x,y,z]}

    返回：
    - IMU数据字典
    """
    # 默认值（静止状态）
    accel_x = 0.0
    accel_y = 0.0
    accel_z = GRAVITY  # 重力加速度

    gyro_x = 0.0
    gyro_y = 0.0
    gyro_z = 0.0

    # 根据模式生成运动数据
    if mode == 'accelerating':
        # 周期为5秒的正弦加速度（前进方向）
        accel_x = 2.0 * math.sin(2 * math.pi * t / 5.0)
        accel_y = 0.5 * math.sin(2 * math.pi * t / 7.0)

    elif mode == 'rotating':
        # 周期为4秒的旋转运动
        gyro_x = 0.3 * math.sin(2 * math.pi * t / 4.0)
        gyro_y = 0.2 * math.sin(2 * math.pi * t / 6.0)
        gyro_z = 0.5 * math.sin(2 * math.pi * t / 3.0)

    elif mode == 'vibrating':
        # 高频振动（20 Hz）
        vib_freq = 20.0
        accel_x = 0.5 * math.sin(2 * math.pi * vib_freq * t)
        accel_y = 0.3 * math.sin(2 * math.pi * vib_freq * t + math.pi/4)
        accel_z = GRAVITY + 0.2 * math.sin(2 * math.pi * vib_freq * t)

    # 添加偏置
    accel_x += biases['accel'][0]
    accel_y += biases['accel'][1]
    accel_z += biases['accel'][2]

    gyro_x += biases['gyro'][0]
    gyro_y += biases['gyro'][1]
    gyro_z += biases['gyro'][2]

    # 添加噪声
    accel_x = add_noise(accel_x, noise_level)
    accel_y = add_noise(accel_y, noise_level)
    accel_z = add_noise(accel_z, noise_level)

    gyro_x = add_noise(gyro_x, noise_level * 0.1)
    gyro_y = add_noise(gyro_y, noise_level * 0.1)
    gyro_z = add_noise(gyro_z, noise_level * 0.1)

    # 磁力计数据（简化：假设朝北，磁场在X-Z平面）
    # 磁倾角约60度（北半球）
    mag_x = EARTH_MAG_FIELD * math.cos(math.radians(60)) + add_noise(0, noise_level * 5)
    mag_y = add_noise(0, noise_level * 5)
    mag_z = EARTH_MAG_FIELD * math.sin(math.radians(60)) + add_noise(0, noise_level * 5)

    # 温度（模拟小幅波动）
    temperature = 25.0 + add_noise(0, 0.5)

    return {
        'accel_x': round(accel_x, 4),
        'accel_y': round(accel_y, 4),
        'accel_z': round(accel_z, 4),
        'gyro_x': round(gyro_x, 5),
        'gyro_y': round(gyro_y, 5),
        'gyro_z': round(gyro_z, 5),
        'mag_x': round(mag_x, 2),
        'mag_y': round(mag_y, 2),
        'mag_z': round(mag_z, 2),
        'temperature': round(temperature, 1)
    }


def main():
    """主函数"""
    with NodeFlowSDK(log_level="INFO") as sdk:
        sdk.logger.info(f"Mock IMU node started: {sdk.node_id}")

        # 1. 读取参数
        mode = sdk.get_param('mode', 'stationary')
        update_rate_hz = sdk.get_param('update_rate_hz', 100)
        noise_level = sdk.get_param('noise_level', 0.01)

        accel_bias_x = sdk.get_param('accel_bias_x', 0.0)
        accel_bias_y = sdk.get_param('accel_bias_y', 0.0)
        accel_bias_z = sdk.get_param('accel_bias_z', 0.0)

        gyro_bias_x = sdk.get_param('gyro_bias_x', 0.0)
        gyro_bias_y = sdk.get_param('gyro_bias_y', 0.0)
        gyro_bias_z = sdk.get_param('gyro_bias_z', 0.0)

        biases = {
            'accel': [accel_bias_x, accel_bias_y, accel_bias_z],
            'gyro': [gyro_bias_x, gyro_bias_y, gyro_bias_z]
        }

        sdk.logger.info(f"Configuration:")
        sdk.logger.info(f"  mode: {mode}")
        sdk.logger.info(f"  update_rate_hz: {update_rate_hz}")
        sdk.logger.info(f"  noise_level: {noise_level}")
        sdk.logger.info(f"  accel_bias: {biases['accel']}")
        sdk.logger.info(f"  gyro_bias: {biases['gyro']}")

        # 验证参数
        if mode not in ['stationary', 'accelerating', 'rotating', 'vibrating']:
            sdk.logger.warning(f"Invalid mode '{mode}', using 'stationary'")
            mode = 'stationary'

        # 2. 创建输出端口
        imu_output = sdk.create_output_port('imu_data')
        sdk.logger.info("Output port 'imu_data' created")

        # 3. 主循环
        seq = 0
        start_time = time.time()
        sleep_interval = 1.0 / update_rate_hz

        sdk.logger.info(f"Starting IMU data generation (mode: {mode}, rate: {update_rate_hz} Hz)")

        try:
            while True:
                current_time = time.time()
                elapsed_time = current_time - start_time

                # 生成IMU数据
                imu_data = generate_imu_data(mode, elapsed_time, noise_level, biases)
                imu_data['timestamp'] = current_time
                imu_data['seq'] = seq

                # 发送数据
                imu_output.send(imu_data)

                # 每秒记录一次（避免日志过多）
                if seq % update_rate_hz == 0:
                    sdk.logger.debug(
                        f"Sent IMU data #{seq}: "
                        f"accel=({imu_data['accel_x']:.2f}, {imu_data['accel_y']:.2f}, {imu_data['accel_z']:.2f}), "
                        f"gyro=({imu_data['gyro_x']:.3f}, {imu_data['gyro_y']:.3f}, {imu_data['gyro_z']:.3f})"
                    )

                seq += 1
                time.sleep(sleep_interval)

        except KeyboardInterrupt:
            sdk.logger.info("Received shutdown signal")
        except Exception as e:
            sdk.logger.error(f"Error in main loop: {e}", exc_info=True)
        finally:
            sdk.logger.info(f"Mock IMU node stopped after {seq} messages")


if __name__ == '__main__':
    main()
