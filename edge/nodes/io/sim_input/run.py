#!/usr/bin/env python3
import sys
import time
import zmq
import json
import logging
from typing import Optional

# Pydantic 导入
try:
    from pydantic import BaseModel, Field
except ImportError:
    class BaseModel: pass
    def Field(*args, **kwargs): return None

from edge.sdk.nodeflow_sdk import NodeFlowSDK, die

# --- Schema Definitions ---

class VelocityCmd(BaseModel):
    linear_velocity: float
    angular_velocity: float
    timestamp: float
    status: Optional[str] = None

class MotorCmd(BaseModel):
    throttle: float
    steering: float
    timestamp: Optional[float] = None

# --- End Schema Definitions ---

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

        # 机具控制端口（可选）
        try:
            self.tillage_port = sdk.create_input_port('tillage_cmd')
            logger.info("机具控制 输入端口已创建")
        except ValueError:
            logger.info("机具控制 输入端口未配置（可选）")
            self.tillage_port = None

        # 控制状态
        self.last_velocity_cmd = None
        self.last_motor_cmd = None

        # 频率控制和默认值
        self.input_frequency = self.params.get('input_frequency', 50.0)
        self.default_linear_velocity = self.params.get('default_linear_velocity', 0.0)
        self.default_angular_velocity = self.params.get('default_angular_velocity', 0.0)
        self.period = 1.0 / self.input_frequency
        logger.info(f"输入频率: {self.input_frequency} Hz (周期 {self.period*1000:.1f} ms)")

        # 命令年龄使用单调时钟，通信阻塞不再拖长“若干帧”的超时。
        self.watchdog_timeout_sec = float(self.params.get('watchdog_timeout_sec', 0.5))
        if self.watchdog_timeout_sec <= 0:
            raise ValueError("watchdog_timeout_sec 必须大于 0")
        self._last_command_received_at = None
        self._pending_drive = None
        self._pending_implement = None
        self._stop_pending = False
        self._drive_active = False
        logger.info(f"看门狗超时: {self.watchdog_timeout_sec}s")

    def _reset_connection(self):
        """丢弃等待旧回复的 REQ socket，保留 context 供下一轮重连。"""
        if self.socket is not None:
            self.socket.close(linger=0)
            self.socket = None

    def _ensure_connected(self):
        if self.socket is not None:
            return True
        try:
            if self.context is None:
                self.context = zmq.Context()
            self.socket = self.context.socket(zmq.REQ)
            self.socket.setsockopt(zmq.LINGER, 0)
            self.socket.setsockopt(zmq.RCVTIMEO, self.timeout)
            self.socket.setsockopt(zmq.SNDTIMEO, self.timeout)
            self.socket.connect(f"tcp://{self.host}:{self.port}")
            return True
        except Exception as exc:
            logger.error(f"连接仿真器失败: {exc}")
            self._reset_connection()
            return False

    def _send_actuator(self, actuator: str, data: dict) -> bool:
        if not self._ensure_connected():
            return False
        try:
            self.socket.send_json({"type": "set_actuator", "actuator": actuator, "data": data})
            response = self.socket.recv_json()
        except Exception as exc:
            # recv 超时后 REQ 仍在等待回复，直接再次 send 会永久陷入 EFSM。
            logger.warning(f"发送 {actuator} 命令失败: {exc}；下一轮重新连接")
            self._reset_connection()
            return False
        if response.get("status") != "ok":
            logger.warning(f"{actuator} 命令被拒绝: {response.get('message', '')}")
            return False
        return True

    def _send_velocity_command(self, linear_velocity: float, angular_velocity: float) -> bool:
        return self._send_actuator("velocity", {
            "linear_velocity": linear_velocity, "angular_velocity": angular_velocity,
        })

    def _send_motor_command(self, throttle: float, steering: float) -> bool:
        return self._send_actuator("motor", {"throttle": throttle, "steering": steering})

    def _send_implement_command(self, tillage_cmd: dict) -> bool:
        return self._send_actuator("implement", {
            "hitch_height": tillage_cmd.get("hitch_height", 0.0),
            "pto_on": tillage_cmd.get("pto_on", False),
            "pto_rpm": tillage_cmd.get("pto_rpm", 540.0),
        })

    def _step(self):
        """读取一次输入并发送待确认命令；发送失败不能记作已停止。"""
        velocity_cmd = self.velocity_port.recv_latest()
        motor_cmd = self.motor_port.recv_latest() if self.motor_port else None
        if velocity_cmd:
            self._pending_drive = ("velocity", velocity_cmd)
            self._last_command_received_at = time.monotonic()
        elif motor_cmd:
            self._pending_drive = ("motor", motor_cmd)
            self._last_command_received_at = time.monotonic()

        if self.tillage_port:
            tillage_cmd = self.tillage_port.recv_latest()
            if tillage_cmd:
                self._pending_implement = tillage_cmd

        if (self._last_command_received_at is not None and
                time.monotonic() - self._last_command_received_at >= self.watchdog_timeout_sec):
            self._pending_drive = None  # 失效的运动命令不允许在恢复连接后重放。
            if self._drive_active:
                self._stop_pending = True

        if self._stop_pending:
            if self._send_velocity_command(0.0, 0.0):
                self._stop_pending = False
                self._drive_active = False
                self.last_velocity_cmd = None
                self.last_motor_cmd = None
                logger.info("看门狗停车命令已确认")
            else:
                # 保留 pending；下轮无新输入时仍会重试停车。
                return
        elif self._pending_drive is not None:
            kind, command = self._pending_drive
            # 回复丢失不等于服务器没执行，超时后仍需发停车命令。
            self._drive_active = True
            if kind == "velocity":
                sent = self._send_velocity_command(
                    command.get("linear_velocity", self.default_linear_velocity),
                    command.get("angular_velocity", self.default_angular_velocity),
                )
                if sent:
                    self.last_velocity_cmd = command
            else:
                sent = self._send_motor_command(command.get("throttle", 0.0), command.get("steering", 0.0))
                if sent:
                    self.last_motor_cmd = command
            if sent:
                self._pending_drive = None
            else:
                return

        if self._pending_implement is not None:
            if self._send_implement_command(self._pending_implement):
                self._pending_implement = None

    def run(self):
        logger.info("仿真器输入节点已启动")
        try:
            while True:
                start_time = time.monotonic()
                self._step()
                sleep_time = max(0, self.period - (time.monotonic() - start_time))
                if sleep_time > 0:
                    time.sleep(sleep_time)
        except KeyboardInterrupt:
            logger.info("接收到停止信号")
        except Exception as exc:
            logger.error(f"主循环异常: {exc}", exc_info=True)
        finally:
            self.cleanup()

    def cleanup(self):
        """有界地尝试停车；没有确认时如实记录，随后释放 socket。"""
        try:
            if not self._send_velocity_command(0.0, 0.0):
                logger.warning("节点退出时未收到仿真器停车确认")
        finally:
            self._reset_connection()
            if self.context is not None:
                self.context.term()
                self.context = None


def main():
    """主函数"""
    try:
        with NodeFlowSDK(log_level="DEBUG") as sdk:
            node = SimInputNode(sdk)
            node.run()
    except Exception as e:
        die(f"节点启动失败: {e}")


if __name__ == "__main__":
    main()
