#!/usr/bin/env python3
"""
Mock Data Generator Node

通用数据生成器，支持错误注入用于测试框架的容错能力。
"""

import time
import random
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from sdk.nodeflow_sdk import NodeFlowSDK


def generate_data(data_type, seq):
    """生成指定类型的测试数据"""
    if data_type == 'gps':
        return {
            'timestamp': time.time(),
            'seq': seq,
            'latitude': 39.9042 + random.uniform(-0.0001, 0.0001),
            'longitude': 116.4074 + random.uniform(-0.0001, 0.0001),
            'altitude': 50.0
        }
    elif data_type == 'imu':
        return {
            'timestamp': time.time(),
            'seq': seq,
            'accel_x': random.gauss(0, 0.1),
            'accel_y': random.gauss(0, 0.1),
            'accel_z': 9.81 + random.gauss(0, 0.1)
        }
    elif data_type == 'control':
        return {
            'timestamp': time.time(),
            'seq': seq,
            'velocity': random.uniform(0, 2.0),
            'steering_angle': random.uniform(-0.5, 0.5)
        }
    else:  # generic_json
        return {
            'timestamp': time.time(),
            'seq': seq,
            'value': random.random(),
            'data_type': 'generic'
        }


def should_inject_error(error_rate):
    """根据错误率决定是否注入错误"""
    return random.random() < error_rate


def main():
    with NodeFlowSDK(log_level="INFO") as sdk:
        sdk.logger.info(f"Mock Data Generator started: {sdk.node_id}")

        data_type = sdk.get_param('data_type', 'generic_json')
        rate_hz = sdk.get_param('rate_hz', 10)
        error_injection = sdk.get_param('error_injection', 'none')
        error_rate = sdk.get_param('error_rate', 0.01)

        sdk.logger.info(f"Configuration: type={data_type}, rate={rate_hz} Hz, error={error_injection}@{error_rate}")

        data_output = sdk.create_output_port('data_out')
        sdk.logger.info("Output port 'data_out' created")

        seq = 0
        error_count = 0
        sleep_interval = 1.0 / rate_hz

        try:
            while True:
                inject_error = should_inject_error(error_rate) if error_injection != 'none' else False

                if inject_error:
                    if error_injection == 'dropout':
                        # 丢包：不发送数据
                        error_count += 1
                        seq += 1
                        time.sleep(sleep_interval)
                        continue
                    elif error_injection == 'corruption':
                        # 数据损坏：发送无效数据
                        data = {'corrupted': True, 'seq': seq}
                        error_count += 1
                    elif error_injection == 'noise':
                        # 添加大噪声
                        data = generate_data(data_type, seq)
                        data['injected_noise'] = random.uniform(-100, 100)
                        error_count += 1
                    else:
                        data = generate_data(data_type, seq)
                else:
                    data = generate_data(data_type, seq)

                data_output.send(data)

                if seq % rate_hz == 0:
                    sdk.logger.debug(f"Sent data #{seq}, errors={error_count}")

                seq += 1
                time.sleep(sleep_interval)

        except KeyboardInterrupt:
            sdk.logger.info("Shutting down")
        except Exception as e:
            sdk.logger.error(f"Error: {e}", exc_info=True)
        finally:
            sdk.logger.info(f"Stopped after {seq} messages ({error_count} errors)")


if __name__ == '__main__':
    main()
