#!/usr/bin/env python3
"""
仿真 IMU 节点

从仿真器读取惯性测量单元 (IMU) 数据并发布到 NodeFlow

ZMQ 协议：
    请求: {"type": "get_sensor", "sensor": "imu"}
    响应: {"status": "ok", "data": {...}}

输出数据格式：
    {
        "accel": {"x": float, "y": float, "z": float},  # 加速度 (m/s²)
        "gyro": {"x": float, "y": float, "z": float},   # 角速度 (rad/s)
        "mag": {"x": float, "y": float, "z": float},    # 磁力计
        "timestamp": float
    }
"""

import sys
import time
import json
import zmq
import logging
import math
from pathlib import Path

# 添加项目根路径
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from sdk.nodeflow_sdk import NodeFlowSDK

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(name)s] %(levelname)s: %(message)s'
)
logger = logging.getLogger("sim_imu")


def main():
    """主函数"""
    with NodeFlowSDK() as sdk:
        logger.info("=== sim_imu 节点启动 ===")

        # 读取参数
        simulator_host = sdk.get_param("simulator_host", "localhost")
        simulator_port = sdk.get_param("simulator_port", 5555)
        frequency = sdk.get_param("frequency", 100)
        timeout = sdk.get_param("timeout", 1000)

        logger.info(f"仿真器地址: {simulator_host}:{simulator_port}")
        logger.info(f"发布频率: {frequency} Hz")

        # 连接到仿真器
        context = zmq.Context()
        socket = context.socket(zmq.REQ)
        socket.connect(f"tcp://{simulator_host}:{simulator_port}")
        socket.setsockopt(zmq.RCVTIMEO, timeout)
        socket.setsockopt(zmq.SNDTIMEO, timeout)

        logger.info(f"已连接到仿真器: tcp://{simulator_host}:{simulator_port}")

        # 计算睡眠时间
        sleep_time = 1.0 / frequency

        # 统计
        success_count = 0
        error_count = 0
        last_log_time = time.time()

        logger.info("开始读取 IMU 数据...")

        try:
            while True:
                loop_start = time.time()

                try:
                    # 向仿真器请求 IMU 数据
                    request = {
                        "type": "get_sensor",
                        "sensor": "imu"
                    }
                    socket.send_json(request)

                    # 接收响应
                    response = socket.recv_json()

                    if response.get("status") == "ok":
                        imu_data = response.get("data", {})

                        # 发布到 NodeFlow
                        sdk.send("imu_data", imu_data)

                        success_count += 1

                        # 每秒打印一次统计
                        if time.time() - last_log_time >= 1.0:
                            accel = imu_data.get("accel", {})
                            gyro = imu_data.get("gyro", {})

                            # 计算加速度大小和角速度大小
                            accel_mag = math.sqrt(
                                accel.get("x", 0)**2 +
                                accel.get("y", 0)**2 +
                                accel.get("z", 0)**2
                            )
                            gyro_mag = math.sqrt(
                                gyro.get("x", 0)**2 +
                                gyro.get("y", 0)**2 +
                                gyro.get("z", 0)**2
                            )

                            logger.info(
                                f"IMU 数据: accel={accel_mag:.2f} m/s², "
                                f"gyro={gyro_mag:.3f} rad/s | "
                                f"成功: {success_count}, 失败: {error_count}"
                            )
                            last_log_time = time.time()
                    else:
                        error_msg = response.get("message", "Unknown error")
                        logger.error(f"仿真器返回错误: {error_msg}")
                        error_count += 1

                except zmq.Again:
                    logger.warning("仿真器请求超时")
                    error_count += 1

                except Exception as e:
                    logger.error(f"读取 IMU 数据失败: {e}")
                    error_count += 1

                # 控制频率
                elapsed = time.time() - loop_start
                if elapsed < sleep_time:
                    time.sleep(sleep_time - elapsed)

        except KeyboardInterrupt:
            logger.info("收到中断信号，正在退出...")

        finally:
            socket.close()
            context.term()
            logger.info(f"=== sim_imu 节点退出 === (成功: {success_count}, 失败: {error_count})")


if __name__ == "__main__":
    main()
