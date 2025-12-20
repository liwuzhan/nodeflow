#!/usr/bin/env python3
"""
Mock Sensor Fusion Node

模拟传感器融合节点，合并GPS和IMU数据生成更准确的位置和姿态估计。
"""

import time
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from sdk.nodeflow_sdk import NodeFlowSDK


def main():
    with NodeFlowSDK(log_level="INFO") as sdk:
        sdk.logger.info(f"Mock Sensor Fusion started: {sdk.node_id}")

        fusion_algorithm = sdk.get_param('fusion_algorithm', 'simple_avg')
        update_rate_hz = sdk.get_param('update_rate_hz', 50)

        sdk.logger.info(f"Configuration: algorithm={fusion_algorithm}, rate={update_rate_hz} Hz")

        gps_input = sdk.create_input_port('gps_fix')
        imu_input = sdk.create_input_port('imu_data')
        fused_output = sdk.create_output_port('fused_pose')

        sdk.logger.info("Ports created successfully")

        seq = 0
        sleep_interval = 1.0 / update_rate_hz

        latest_gps = None
        latest_imu = None

        try:
            while True:
                current_time = time.time()

                gps_data = gps_input.recv_latest()
                imu_data = imu_input.recv_latest()

                if gps_data:
                    latest_gps = gps_data
                if imu_data:
                    latest_imu = imu_data

                if latest_gps and latest_imu:
                    # 简单融合：直接组合
                    fused_pose = {
                        'timestamp': current_time,
                        'seq': seq,
                        'latitude': latest_gps.get('latitude'),
                        'longitude': latest_gps.get('longitude'),
                        'altitude': latest_gps.get('altitude'),
                        'orientation': {
                            'roll': 0.0,
                            'pitch': 0.0,
                            'yaw': 0.0
                        },
                        'linear_acceleration': [
                            latest_imu.get('accel_x', 0),
                            latest_imu.get('accel_y', 0),
                            latest_imu.get('accel_z', 0)
                        ],
                        'angular_velocity': [
                            latest_imu.get('gyro_x', 0),
                            latest_imu.get('gyro_y', 0),
                            latest_imu.get('gyro_z', 0)
                        ],
                        'fusion_algorithm': fusion_algorithm
                    }

                    fused_output.send(fused_pose)

                    if seq % update_rate_hz == 0:
                        sdk.logger.debug(f"Fused pose #{seq} generated")

                    seq += 1

                time.sleep(sleep_interval)

        except KeyboardInterrupt:
            sdk.logger.info("Shutting down")
        except Exception as e:
            sdk.logger.error(f"Error: {e}", exc_info=True)
        finally:
            sdk.logger.info(f"Stopped after {seq} fusions")


if __name__ == '__main__':
    main()
