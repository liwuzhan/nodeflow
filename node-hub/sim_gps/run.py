#!/usr/bin/env python3
"""
仿真 GPS 节点

从仿真器读取 GPS 数据并发布到 NodeFlow

ZMQ 协议：
    请求: {"type": "get_sensor", "sensor": "gps"}
    响应: {"status": "ok", "data": {...}}

输出数据格式：
    {
        "latitude": float,      # 纬度 (度)
        "longitude": float,     # 经度 (度)
        "altitude": float,      # 海拔 (米)
        "hdop": float,          # 水平精度因子
        "fix_quality": int,     # 定位质量 (4=RTK Fixed)
        "num_satellites": int,  # 卫星数量
        "timestamp": float      # 时间戳
    }
"""

import sys
import time
import json
import zmq
import logging
from pathlib import Path

# 添加项目根路径
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from sdk.nodeflow_sdk import NodeFlowSDK

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(name)s] %(levelname)s: %(message)s'
)
logger = logging.getLogger("sim_gps")


def main():
    """主函数"""
    with NodeFlowSDK() as sdk:
        logger.info("=== sim_gps 节点启动 ===")

        # 读取参数
        simulator_host = sdk.get_param("simulator_host", "localhost")
        simulator_port = sdk.get_param("simulator_port", 5555)
        frequency = sdk.get_param("frequency", 10)
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

        logger.info("开始读取 GPS 数据...")

        try:
            while True:
                loop_start = time.time()

                try:
                    # 向仿真器请求 GPS 数据
                    request = {
                        "type": "get_sensor",
                        "sensor": "gps"
                    }
                    socket.send_json(request)

                    # 接收响应
                    response = socket.recv_json()

                    if response.get("status") == "ok":
                        gps_data = response.get("data", {})

                        # 发布到 NodeFlow
                        sdk.send("gps_fix", gps_data)

                        success_count += 1

                        # 每秒打印一次统计
                        if time.time() - last_log_time >= 1.0:
                            logger.info(
                                f"GPS 数据: lat={gps_data['latitude']:.6f}, "
                                f"lon={gps_data['longitude']:.6f}, "
                                f"hdop={gps_data['hdop']:.2f} | "
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
                    logger.error(f"读取 GPS 数据失败: {e}")
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
            logger.info(f"=== sim_gps 节点退出 === (成功: {success_count}, 失败: {error_count})")


if __name__ == "__main__":
    main()
