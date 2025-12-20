#!/usr/bin/env python3
"""
Mock Motor Controller Node

模拟电机控制器，接收控制指令并模拟执行，用于测试控制流的完整性。
"""

import time
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from sdk.nodeflow_sdk import NodeFlowSDK


def main():
    with NodeFlowSDK(log_level="INFO") as sdk:
        sdk.logger.info(f"Mock Motor Controller started: {sdk.node_id}")

        motor_count = sdk.get_param('motor_count', 2)
        response_delay_ms = sdk.get_param('response_delay_ms', 100)
        max_pwm = sdk.get_param('max_pwm', 1500)

        sdk.logger.info(f"Configuration: {motor_count} motors, max_pwm={max_pwm}")

        control_input = sdk.create_input_port('control_cmd')
        sdk.logger.info("Input port 'control_cmd' created")

        cmd_count = 0

        try:
            while True:
                cmd_data = control_input.recv_latest()

                if cmd_data:
                    velocity = cmd_data.get('velocity', 0)
                    steering = cmd_data.get('steering_angle', 0)

                    # 模拟电机响应延迟
                    time.sleep(response_delay_ms / 1000.0)

                    # 计算PWM值
                    pwm_left = int(min(max_pwm, abs(velocity) * 500 + steering * 200))
                    pwm_right = int(min(max_pwm, abs(velocity) * 500 - steering * 200))

                    if cmd_count % 50 == 0:
                        sdk.logger.debug(f"Executing command #{cmd_count}: PWM_L={pwm_left}, PWM_R={pwm_right}")

                    cmd_count += 1

                time.sleep(0.02)  # 50 Hz

        except KeyboardInterrupt:
            sdk.logger.info("Shutting down")
        except Exception as e:
            sdk.logger.error(f"Error: {e}", exc_info=True)
        finally:
            sdk.logger.info(f"Stopped after executing {cmd_count} commands")


if __name__ == '__main__':
    main()
