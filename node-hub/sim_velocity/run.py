#!/usr/bin/env python3
"""
仿真速度控制节点

接收 NodeFlow 速度控制指令并发送给仿真器执行

与 sim_motor 的区别：
- sim_motor: 油门/转向模式 (throttle, steering)
- sim_velocity: 速度模式 (linear_velocity, angular_velocity)

ZMQ 协议：
    请求: {
        "type": "set_actuator",
        "actuator": "velocity",
        "data": {
            "linear_velocity": float,   # m/s
            "angular_velocity": float   # rad/s
        }
    }
    响应: {"status": "ok", "applied_at": float}

输入数据格式：
    {
        "linear_velocity": float,   # 线速度 (m/s)，推荐范围 [-2.0, 2.0]
        "angular_velocity": float,  # 角速度 (rad/s)，推荐范围 [-1.0, 1.0]
        "timestamp": float          # 可选
    }

速度模式的优势：
- 直接控制线速度和角速度，物理意义清晰
- 仿真器会自动应用打滑噪声模型
- 更适合农田作业场景
- 输出RTK定位是打滑后的真实位置

打滑模型说明：
- 线速度: 只能减少，不能增加 (v_real = v_cmd * (1 - slip))
- 打滑比例: 5% (可配置)
- 打滑大小: 速度越快打滑越严重
- 实时变化: 每帧都有新的噪声，不是累积的
"""

import sys
import time
import json
import zmq
import math
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
logger = logging.getLogger("sim_velocity")


def clamp(value: float, min_val: float, max_val: float) -> float:
    """限制值在指定范围内"""
    return max(min_val, min(max_val, value))


def main():
    """主函数"""
    with NodeFlowSDK() as sdk:
        logger.info("=== sim_velocity 节点启动 ===")

        # 读取参数
        simulator_host = sdk.get_param("simulator_host", "localhost")
        simulator_port = sdk.get_param("simulator_port", 5555)
        timeout = sdk.get_param("timeout", 1000)
        default_linear = sdk.get_param("default_linear_velocity", 0.0)
        default_angular = sdk.get_param("default_angular_velocity", 0.0)
        control_freq = sdk.get_param("control_frequency", 50)
        max_linear = sdk.get_param("max_linear_velocity", 2.0)
        max_angular = sdk.get_param("max_angular_velocity", 1.0)

        logger.info(f"仿真器地址: {simulator_host}:{simulator_port}")
        logger.info(f"控制循环频率: {control_freq} Hz ({1000.0/control_freq:.1f}ms)")
        logger.info(f"速度限制: linear=[{-max_linear:.2f}, {max_linear:.2f}], "
                    f"angular=[{-max_angular:.2f}, {max_angular:.2f}]")

        # 连接到仿真器
        context = zmq.Context()
        socket = context.socket(zmq.REQ)
        socket.connect(f"tcp://{simulator_host}:{simulator_port}")
        socket.setsockopt(zmq.RCVTIMEO, timeout)
        socket.setsockopt(zmq.SNDTIMEO, timeout)

        logger.info(f"已连接到仿真器: tcp://{simulator_host}:{simulator_port}")

        # 计算循环间隔
        loop_interval = 1.0 / control_freq

        # 统计
        success_count = 0
        error_count = 0
        no_command_count = 0
        last_log_time = time.time()

        # 当前控制值
        current_linear = default_linear
        current_angular = default_angular

        logger.info("开始接收速度控制指令...")
        logger.info("注意: 仿真器会应用打滑模型，实际速度会小于指令速度")

        try:
            while True:
                loop_start = time.time()

                # 从 NodeFlow 接收控制指令
                velocity_cmd = sdk.recv_latest("velocity_cmd")

                if velocity_cmd is not None:
                    # 提取速度值
                    current_linear = velocity_cmd.get("linear_velocity", default_linear)
                    current_angular = velocity_cmd.get("angular_velocity", default_angular)

                    # 限制速度范围
                    current_linear = clamp(current_linear, -max_linear, max_linear)
                    current_angular = clamp(current_angular, -max_angular, max_angular)
                else:
                    # 无指令时使用默认值
                    no_command_count += 1

                # 发送控制指令到仿真器
                try:
                    request = {
                        "type": "set_actuator",
                        "actuator": "velocity",
                        "data": {
                            "linear_velocity": current_linear,
                            "angular_velocity": current_angular
                        }
                    }
                    socket.send_json(request)

                    # 接收响应
                    response = socket.recv_json()

                    if response.get("status") == "ok":
                        success_count += 1

                        # 每秒打印一次统计
                        if time.time() - last_log_time >= 1.0:
                            # 计算速度大小 (m/s)
                            speed_magnitude = math.sqrt(
                                current_linear**2 if current_linear != 0 else 0
                            )

                            # 计算期望的打滑量
                            slip_pct = (speed_magnitude / max_linear * 100 * 5) if max_linear > 0 else 0

                            logger.info(
                                f"速度控制: v={current_linear:.3f} m/s, "
                                f"ω={current_angular:.3f} rad/s, "
                                f"预期打滑≈{slip_pct:.1f}% | "
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
                    logger.error(f"发送速度指令失败: {e}")
                    error_count += 1

                # 控制循环频率
                elapsed = time.time() - loop_start
                if elapsed < loop_interval:
                    time.sleep(loop_interval - elapsed)

        except KeyboardInterrupt:
            logger.info("收到中断信号，正在退出...")

        finally:
            # 停止运动（发送零速度）
            try:
                stop_request = {
                    "type": "set_actuator",
                    "actuator": "velocity",
                    "data": {
                        "linear_velocity": 0.0,
                        "angular_velocity": 0.0
                    }
                }
                socket.send_json(stop_request)
                socket.recv_json()
                logger.info("已停止运动")
            except:
                pass

            socket.close()
            context.term()
            logger.info(
                f"=== sim_velocity 节点退出 === "
                f"(成功: {success_count}, 失败: {error_count})"
            )


if __name__ == "__main__":
    main()
