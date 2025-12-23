#!/usr/bin/env python3
"""
仿真器输入节点
接收控制命令并发送到仿真器
"""

import sys
import time
import zmq
import json
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
logger = logging.getLogger("sim_input")


class SimInputNode:
    """仿真器输入节点"""

    def __init__(self, sdk: NodeFlowSDK):
        self.sdk = sdk
        self.params = sdk.params

        # 获取参数
        self.host = self.params.get('simulator_host', 'localhost')
        self.port = self.params.get('simulator_port', 5555)
        self.timeout = self.params.get('timeout', 1000)

        # ZMQ 连接（延迟到主循环中创建，避免与sim_output竞争）
        self.context = None
        self.socket = None
        logger.info(f"将在主循环中连接到仿真器: {self.host}:{self.port}")

        # 创建输入端口（仅创建已配置的端口）
        self.velocity_port = sdk.create_input_port('velocity_cmd')
        logger.info("速度控制 输入端口已创建")

        # 电机控制端口是可选的（如果没有配置就不创建）
        try:
            self.motor_port = sdk.create_input_port('motor_cmd')
            logger.info("电机控制 输入端口已创建")
        except ValueError:
            logger.info("电机控制 输入端口未配置（可选）")
            self.motor_port = None

        # 控制状态
        self.last_velocity_cmd = None
        self.last_motor_cmd = None

        # 频率控制和默认值
        self.input_frequency = self.params.get('input_frequency', 50.0)
        self.default_linear_velocity = self.params.get('default_linear_velocity', 0.0)
        self.default_angular_velocity = self.params.get('default_angular_velocity', 0.0)
        self.period = 1.0 / self.input_frequency
        logger.info(f"输入频率: {self.input_frequency} Hz (周期 {self.period*1000:.1f} ms)")

    def _send_velocity_command(self, linear_velocity: float, angular_velocity: float) -> bool:
        """发送速度控制命令到仿真器"""
        try:
            request = {
                "type": "set_actuator",
                "actuator": "velocity",
                "data": {
                    "linear_velocity": linear_velocity,
                    "angular_velocity": angular_velocity
                }
            }
            self.socket.send_json(request)
            response = self.socket.recv_json()

            if response.get("status") == "ok":
                return True
            else:
                logger.warning(f"速度命令被拒绝: {response.get('message', '')}")
                return False

        except zmq.error.Again:
            logger.warning("发送速度命令超时")
            return False
        except Exception as e:
            logger.error(f"发送速度命令异常: {e}")
            return False

    def _send_motor_command(self, throttle: float, steering: float) -> bool:
        """发送电机控制命令到仿真器"""
        try:
            request = {
                "type": "set_actuator",
                "actuator": "motor",
                "data": {
                    "throttle": throttle,
                    "steering": steering
                }
            }
            self.socket.send_json(request)
            response = self.socket.recv_json()

            if response.get("status") == "ok":
                return True
            else:
                logger.warning(f"电机命令被拒绝: {response.get('message', '')}")
                return False

        except zmq.error.Again:
            logger.warning("发送电机命令超时")
            return False
        except Exception as e:
            logger.error(f"发送电机命令异常: {e}")
            return False

    def _ensure_connected(self):
        """确保与仿真器的连接已建立（延迟初始化）"""
        if self.socket is None:
            try:
                logger.info(f"建立与仿真器的连接: {self.host}:{self.port}")
                self.context = zmq.Context()
                self.socket = self.context.socket(zmq.REQ)
                self.socket.connect(f"tcp://{self.host}:{self.port}")
                self.socket.setsockopt(zmq.RCVTIMEO, self.timeout)
                self.socket.setsockopt(zmq.SNDTIMEO, self.timeout)
                logger.info("与仿真器的连接已建立")
            except Exception as e:
                logger.error(f"连接仿真器失败: {e}")
                self.socket = None
                return False
        return True

    def run(self):
        """主循环"""
        logger.info("仿真器输入节点已启动")

        loop_count = 0
        last_log_time = time.time()
        connection_attempted = False

        try:
            while True:
                start_time = time.time()

                # 0. 延迟连接到仿真器（首次尝试发送命令时）
                if not connection_attempted:
                    self._ensure_connected()
                    connection_attempted = True

                # 1. 尝试读取速度控制命令（优先级1）
                velocity_cmd = self.velocity_port.recv_latest()

                if velocity_cmd:
                    # 如果收到新的速度命令，立即发送
                    linear_vel = velocity_cmd.get("linear_velocity", self.default_linear_velocity)
                    angular_vel = velocity_cmd.get("angular_velocity", self.default_angular_velocity)

                    if self._send_velocity_command(linear_vel, angular_vel):
                        self.last_velocity_cmd = velocity_cmd
                        if loop_count % 20 == 0:  # 每20次循环记录一次
                            logger.debug(f"发送速度命令: v={linear_vel:.2f} m/s, ω={angular_vel:.2f} rad/s")

                else:
                    # 2. 如果没有速度命令，尝试电机命令（优先级2）
                    motor_cmd = None
                    if self.motor_port:
                        motor_cmd = self.motor_port.recv_latest()

                    if motor_cmd:
                        throttle = motor_cmd.get("throttle", 0.0)
                        steering = motor_cmd.get("steering", 0.0)

                        if self._send_motor_command(throttle, steering):
                            self.last_motor_cmd = motor_cmd
                            if loop_count % 20 == 0:
                                logger.debug(f"发送电机命令: throttle={throttle:.2f}, steering={steering:.2f}")

                    else:
                        # 3. 两个命令都没有，发送零命令
                        if self.last_velocity_cmd or self.last_motor_cmd:
                            # 如果之前有命令，现在发送零命令（停止）
                            self._send_velocity_command(
                                self.default_linear_velocity,
                                self.default_angular_velocity
                            )
                            self.last_velocity_cmd = None
                            self.last_motor_cmd = None
                            logger.info("无输入命令，发送零命令停止")

                # 频率控制
                loop_count += 1
                elapsed = time.time() - start_time
                sleep_time = max(0, self.period - elapsed)

                if sleep_time > 0:
                    time.sleep(sleep_time)

                # 定期日志
                if time.time() - last_log_time > 10.0:
                    logger.info(f"运行中 - 已处理 {loop_count} 次循环")
                    last_log_time = time.time()

        except KeyboardInterrupt:
            logger.info("接收到停止信号")
        except Exception as e:
            logger.error(f"主循环异常: {e}", exc_info=True)
        finally:
            self.cleanup()

    def cleanup(self):
        """清理资源"""
        logger.info("清理资源...")

        # 发送最后的零命令确保机器人停止
        try:
            self._send_velocity_command(0.0, 0.0)
        except:
            pass

        self.socket.close()
        self.context.term()
        logger.info("仿真器输入节点已停止")


def main():
    """主函数"""
    try:
        with NodeFlowSDK(log_level="DEBUG") as sdk:
            node = SimInputNode(sdk)
            node.run()
    except Exception as e:
        logger.error(f"节点启动失败: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
