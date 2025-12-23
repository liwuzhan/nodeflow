#!/usr/bin/env python3
"""
仿真电机控制节点

接收 NodeFlow 控制指令并发送给仿真器执行

ZMQ 协议：
    请求: {
        "type": "set_actuator",
        "actuator": "motor",
        "data": {"throttle": float, "steering": float}
    }
    响应: {"status": "ok", "applied_at": float}

输入数据格式：
    {
        "throttle": float,   # 油门，范围 [-1, 1]
        "steering": float,   # 转向，范围 [-1, 1]
        "timestamp": float   # 可选
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
logger = logging.getLogger("sim_motor")


def main():
    """主函数"""
    with NodeFlowSDK() as sdk:
        logger.info("=== sim_motor 节点启动 ===")

        # 读取参数
        simulator_host = sdk.get_param("simulator_host", "localhost")
        simulator_port = sdk.get_param("simulator_port", 5555)
        timeout = sdk.get_param("timeout", 1000)
        default_throttle = sdk.get_param("default_throttle", 0.0)
        default_steering = sdk.get_param("default_steering", 0.0)

        logger.info(f"仿真器地址: {simulator_host}:{simulator_port}")
        logger.info(f"默认控制: throttle={default_throttle}, steering={default_steering}")

        # 连接到仿真器
        context = zmq.Context()
        socket = context.socket(zmq.REQ)
        socket.connect(f"tcp://{simulator_host}:{simulator_port}")
        socket.setsockopt(zmq.RCVTIMEO, timeout)
        socket.setsockopt(zmq.SNDTIMEO, timeout)

        logger.info(f"已连接到仿真器: tcp://{simulator_host}:{simulator_port}")

        # 统计
        success_count = 0
        error_count = 0
        no_command_count = 0
        last_log_time = time.time()

        # 当前控制值
        current_throttle = default_throttle
        current_steering = default_steering

        logger.info("开始接收电机控制指令...")

        try:
            while True:
                loop_start = time.time()

                # 从 NodeFlow 接收控制指令
                motor_cmd = sdk.recv_latest("motor_cmd")

                if motor_cmd is not None:
                    # 提取控制值
                    current_throttle = motor_cmd.get("throttle", default_throttle)
                    current_steering = motor_cmd.get("steering", default_steering)

                    # 限制范围
                    current_throttle = max(-1.0, min(1.0, current_throttle))
                    current_steering = max(-1.0, min(1.0, current_steering))
                else:
                    # 无指令时使用默认值
                    no_command_count += 1

                # 发送控制指令到仿真器
                try:
                    request = {
                        "type": "set_actuator",
                        "actuator": "motor",
                        "data": {
                            "throttle": current_throttle,
                            "steering": current_steering
                        }
                    }
                    socket.send_json(request)

                    # 接收响应
                    response = socket.recv_json()

                    if response.get("status") == "ok":
                        success_count += 1

                        # 每秒打印一次统计
                        if time.time() - last_log_time >= 1.0:
                            logger.info(
                                f"电机控制: throttle={current_throttle:.3f}, "
                                f"steering={current_steering:.3f} | "
                                f"成功: {success_count}, 失败: {error_count}, "
                                f"无指令: {no_command_count}"
                            )
                            last_log_time = time.time()
                            no_command_count = 0
                    else:
                        error_msg = response.get("message", "Unknown error")
                        logger.error(f"仿真器返回错误: {error_msg}")
                        error_count += 1

                except zmq.Again:
                    logger.warning("仿真器请求超时")
                    error_count += 1

                except Exception as e:
                    logger.error(f"发送电机指令失败: {e}")
                    error_count += 1

                # 控制循环频率（50Hz，避免过载）
                elapsed = time.time() - loop_start
                sleep_time = 0.02  # 20ms = 50Hz
                if elapsed < sleep_time:
                    time.sleep(sleep_time - elapsed)

        except KeyboardInterrupt:
            logger.info("收到中断信号，正在退出...")

        finally:
            # 停止电机（发送零速度）
            try:
                stop_request = {
                    "type": "set_actuator",
                    "actuator": "motor",
                    "data": {
                        "throttle": 0.0,
                        "steering": 0.0
                    }
                }
                socket.send_json(stop_request)
                socket.recv_json()
                logger.info("已停止电机")
            except:
                pass

            socket.close()
            context.term()
            logger.info(f"=== sim_motor 节点退出 === (成功: {success_count}, 失败: {error_count})")


if __name__ == "__main__":
    main()
