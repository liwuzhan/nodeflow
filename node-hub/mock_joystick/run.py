#!/usr/bin/env python3
"""
Mock Joystick/Hand Controller Node

功能描述：
模拟手柄/遥控器HID输入设备，生成标准化的控制指令用于测试。

可配置参数：
- mode (str): 控制值生成模式
  * 'constant': 固定值输出
  * 'sine': 正弦波变化（模拟平滑操作）
  * 'random': 随机值（模拟不规则操作）
  [default: 'sine']

- update_rate_hz (float): 发布频率，单位Hz
  [default: 50]

- max_linear_velocity (float): 最大线速度，单位 m/s
  [default: 2.0]

- max_angular_velocity (float): 最大角速度，单位 rad/s
  [default: 1.57]

输出端口：
- control_input: 控制指令数据（JSON格式）
  {
    "timestamp": 1703024780.123,
    "seq": 1,
    "linear_velocity": 1.5,    // m/s (forward/backward)
    "angular_velocity": 0.5,   // rad/s (rotation)
    "buttons": {"a": true, "b": false}  // Optional button states
  }

数据生成逻辑：
- constant模式: 输出固定的50%最大速度
- sine模式: 使用正弦波在[-max, max]范围内变化
- random模式: 在[-max, max]范围内随机生成

用途：
- 测试控制指令的接收和传播
- 验证数据流的频率和时序
- 模拟不同的操作模式
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


def generate_control_value(mode, t, max_value):
    """
    生成控制值

    参数：
    - mode: 生成模式 ('constant', 'sine', 'random')
    - t: 时间戳（秒）
    - max_value: 最大值

    返回：
    - 控制值（在 [-max_value, max_value] 范围内）
    """
    if mode == 'constant':
        return max_value * 0.5
    elif mode == 'sine':
        # 周期为10秒的正弦波
        return max_value * math.sin(2 * math.pi * t / 10.0)
    elif mode == 'random':
        return random.uniform(-max_value, max_value)
    else:
        return 0.0


def main():
    """主函数"""
    with NodeFlowSDK(log_level="INFO") as sdk:
        sdk.logger.info(f"Mock Joystick node started: {sdk.node_id}")

        # 1. 读取参数
        mode = sdk.get_param('mode', 'sine')
        update_rate_hz = sdk.get_param('update_rate_hz', 50)
        max_linear_velocity = sdk.get_param('max_linear_velocity', 2.0)
        max_angular_velocity = sdk.get_param('max_angular_velocity', 1.57)

        sdk.logger.info(f"Configuration:")
        sdk.logger.info(f"  mode: {mode}")
        sdk.logger.info(f"  update_rate_hz: {update_rate_hz}")
        sdk.logger.info(f"  max_linear_velocity: {max_linear_velocity} m/s")
        sdk.logger.info(f"  max_angular_velocity: {max_angular_velocity} rad/s")

        # 验证参数
        if mode not in ['constant', 'sine', 'random']:
            sdk.logger.warning(f"Invalid mode '{mode}', using 'sine'")
            mode = 'sine'

        # 2. 创建输出端口
        control_output = sdk.create_output_port('control_input')
        sdk.logger.info("Output port 'control_input' created")

        # 3. 主循环
        seq = 0
        start_time = time.time()
        sleep_interval = 1.0 / update_rate_hz

        sdk.logger.info(f"Starting control generation loop (mode: {mode}, rate: {update_rate_hz} Hz)")

        try:
            while True:
                current_time = time.time()
                elapsed_time = current_time - start_time

                # 生成控制值
                linear_velocity = generate_control_value(mode, elapsed_time, max_linear_velocity)
                angular_velocity = generate_control_value(mode, elapsed_time + 2.5, max_angular_velocity)

                # 构建输出数据
                control_data = {
                    'timestamp': current_time,
                    'seq': seq,
                    'linear_velocity': round(linear_velocity, 3),
                    'angular_velocity': round(angular_velocity, 3),
                    'buttons': {
                        'a': seq % 100 == 0,  # 每100次按一次A按钮
                        'b': False
                    }
                }

                # 发送数据
                control_output.send(control_data)

                # 每秒记录一次
                if seq % update_rate_hz == 0:
                    sdk.logger.debug(
                        f"Sent control #{seq}: "
                        f"linear={control_data['linear_velocity']:.2f}, "
                        f"angular={control_data['angular_velocity']:.2f}"
                    )

                seq += 1
                time.sleep(sleep_interval)

        except KeyboardInterrupt:
            sdk.logger.info("Received shutdown signal")
        except Exception as e:
            sdk.logger.error(f"Error in main loop: {e}", exc_info=True)
        finally:
            sdk.logger.info(f"Mock Joystick node stopped after {seq} messages")


if __name__ == '__main__':
    main()
