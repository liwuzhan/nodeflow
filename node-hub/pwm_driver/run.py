#!/usr/bin/env python3
"""
PWM Driver Node - 香橙派5 Ultra电机PWM驱动 (L3 分子层)

使用 Linux sysfs PWM 接口输出 RC PWM 信号 (50Hz, 1ms-2ms 高电平)
"""

import os
import sys
import time
from pathlib import Path

# 添加项目根路径
project_root = Path(__file__).parent.parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from sdk.nodeflow_sdk import NodeFlowSDK

# 导入 L4 原子层 (用于运动学计算)
import atom


class PWMDriverNode:
    """PWM驱动节点 (L3) - sysfs 接口版本"""

    def __init__(self, sdk: NodeFlowSDK):
        self.sdk = sdk
        self.running = True

        # ========== 读取参数 ==========
        # PWM硬件配置 (sysfs)
        self.pwm_frequency = float(sdk.get_param('pwm_frequency', 50.0))
        self.left_pwmchip = sdk.get_param('left_pwmchip', 'pwmchip0')
        self.left_pwm_channel = int(sdk.get_param('left_pwm_channel', 0))
        self.right_pwmchip = sdk.get_param('right_pwmchip', 'pwmchip1')
        self.right_pwm_channel = int(sdk.get_param('right_pwm_channel', 0))

        # RC PWM 脉宽参数 (纳秒)
        self.pwm_min_ns = int(sdk.get_param('pwm_min_ns', 1000000))      # 1ms
        self.pwm_center_ns = int(sdk.get_param('pwm_center_ns', 1500000)) # 1.5ms
        self.pwm_max_ns = int(sdk.get_param('pwm_max_ns', 2000000))      # 2ms
        self.pwm_duty_scale = float(sdk.get_param('pwm_duty_scale', 0.8))
        self.pwm_inverted_polarity = sdk.get_param('pwm_inverted_polarity', True)

        # 车辆参数
        self.wheel_base = float(sdk.get_param('wheel_base', 0.5))
        self.max_linear_speed = float(sdk.get_param('max_linear_speed', 2.0))
        self.max_angular_speed = float(sdk.get_param('max_angular_speed', 1.0))

        # 电机校准参数
        self.left_speed_scale = float(sdk.get_param('left_speed_scale', 1.0))
        self.right_speed_scale = float(sdk.get_param('right_speed_scale', 1.0))
        self.angular_velocity_bias = float(sdk.get_param('angular_velocity_bias', 0.0))
        self.pwm_deadzone_ns = int(sdk.get_param('pwm_deadzone_ns', 0))

        # 安全参数
        self.enable_safety_check = sdk.get_param('enable_safety_check', True)
        self.emergency_stop = sdk.get_param('emergency_stop', False)
        self.command_timeout = float(sdk.get_param('command_timeout', 0.5))

        # 调试参数
        self.enable_verbose_log = sdk.get_param('enable_verbose_log', False)
        self.dry_run_mode = sdk.get_param('dry_run_mode', False)

        # ========== 创建端口 ==========
        self.velocity_cmd_port = sdk.create_input_port('velocity_cmd')
        self.pwm_status_port = sdk.create_output_port('pwm_status')

        # ========== 构建PWM路径 ==========
        self.left_pwm_path = f"/sys/class/pwm/{self.left_pwmchip}/pwm{self.left_pwm_channel}"
        self.right_pwm_path = f"/sys/class/pwm/{self.right_pwmchip}/pwm{self.right_pwm_channel}"

        # ========== 计算PWM输出范围 (ns) ==========
        self.pwm_period_ns = int(1e9 / self.pwm_frequency)  # 50Hz = 20,000,000ns
        # 实际输出范围
        self.pwm_output_delta = int((self.pwm_max_ns - self.pwm_min_ns) / 2 * self.pwm_duty_scale)

        # ========== 初始化运动学 (L4 原子层) ==========
        self.kinematics = atom.DifferentialDriveKinematics(
            wheel_base=self.wheel_base,
            max_linear_speed=self.max_linear_speed,
            max_angular_speed=self.max_angular_speed
        )

        # ========== 初始化硬件PWM ==========
        self.gpio_available = False
        if not self.dry_run_mode:
            self._init_pwm_hardware()
        else:
            self.sdk.logger.warning("Running in DRY RUN mode - no actual PWM output")

        # 命令超时检查
        self.last_command_time = time.time()

        # 日志配置
        self.sdk.logger.info("PWM Driver initialized (sysfs mode)")
        self.sdk.logger.info(f"  Left: {self.left_pwm_path}")
        self.sdk.logger.info(f"  Right: {self.right_pwm_path}")
        self.sdk.logger.info(f"  Frequency: {self.pwm_frequency}Hz (period={self.pwm_period_ns}ns)")
        self.sdk.logger.info(f"  Pulse range: {self.pwm_min_ns/1e6}ms ~ {self.pwm_max_ns/1e6}ms")
        self.sdk.logger.info(f"  Center: {self.pwm_center_ns/1e6}ms")
        self.sdk.logger.info(f"  Inverted polarity: {self.pwm_inverted_polarity}")
        self.sdk.logger.info(f"  Wheel base: {self.wheel_base}m")

    def _pulse_to_duty_ns(self, pulse_ns: int) -> int:
        """将期望的高电平脉宽转换为 sysfs duty_cycle 值

        极性反转模式: duty_cycle = period - pulse (duty_cycle 指定低电平时间)
        正常模式:     duty_cycle = pulse (duty_cycle 指定高电平时间)
        """
        if self.pwm_inverted_polarity:
            return self.pwm_period_ns - pulse_ns
        return pulse_ns

    def _init_pwm_hardware(self) -> None:
        """初始化PWM硬件（使用 Linux sysfs 接口）"""
        try:
            # 导出左轮 PWM
            export_path = f"/sys/class/pwm/{self.left_pwmchip}/export"
            try:
                with open(export_path, "w") as f:
                    f.write(str(self.left_pwm_channel))
            except (FileExistsError, OSError):
                pass  # 已经导出

            # 导出右轮 PWM
            export_path = f"/sys/class/pwm/{self.right_pwmchip}/export"
            try:
                with open(export_path, "w") as f:
                    f.write(str(self.right_pwm_channel))
            except (FileExistsError, OSError):
                pass  # 已经导出

            # 等待 sysfs 节点创建
            time.sleep(0.1)

            # 配置左轮 PWM
            self._configure_pwm(self.left_pwm_path)

            # 配置右轮 PWM
            self._configure_pwm(self.right_pwm_path)

            # 设置初始中位 (停止)
            center_duty = self._pulse_to_duty_ns(self.pwm_center_ns)
            self._write_pwm_ns(center_duty, center_duty)

            self.gpio_available = True
            self.sdk.logger.info("PWM sysfs initialized successfully")

        except Exception as e:
            self.sdk.logger.error(f"Failed to initialize PWM sysfs: {e}")
            self.gpio_available = False

    def _configure_pwm(self, pwm_path: str) -> None:
        """配置单个 PWM 通道"""
        # 设置周期
        with open(f"{pwm_path}/period", "w") as f:
            f.write(str(self.pwm_period_ns))

        # 先设为中位
        center_duty = self._pulse_to_duty_ns(self.pwm_center_ns)
        with open(f"{pwm_path}/duty_cycle", "w") as f:
            f.write(str(center_duty))

        # 使能 PWM
        with open(f"{pwm_path}/enable", "w") as f:
            f.write("1")

    def _write_pwm_ns(self, left_ns: int, right_ns: int) -> None:
        """写入 PWM 值 (纳秒) 到 sysfs"""
        if self.gpio_available:
            try:
                with open(f"{self.left_pwm_path}/duty_cycle", "w") as f:
                    f.write(str(left_ns))
                with open(f"{self.right_pwm_path}/duty_cycle", "w") as f:
                    f.write(str(right_ns))
            except Exception as e:
                self.sdk.logger.error(f"Failed to write PWM: {e}")
        elif not self.dry_run_mode:
            self.sdk.logger.warning(
                f"GPIO not available, PWM not written: "
                f"L={left_ns}ns, R={right_ns}ns"
            )

    def _speed_to_ns(self, speed: float) -> int:
        """将轮速 (m/s) 转换为 sysfs duty_cycle 值 (ns)

        映射关系（高电平脉宽）：
        - speed = 0 → center_ns
        - speed > 0 → center_ns + deadzone ~ center_ns + output_delta
        - speed < 0 → center_ns - output_delta ~ center_ns - deadzone
        """
        if self.max_linear_speed == 0 or speed == 0.0:
            return self._pulse_to_duty_ns(self.pwm_center_ns)

        # 规范化速度 (-1 到 1)
        ratio = speed / self.max_linear_speed
        ratio = max(-1.0, min(1.0, ratio))

        # 有效输出范围 = output_delta - deadzone
        effective_range = self.pwm_output_delta - self.pwm_deadzone_ns
        if effective_range <= 0:
            effective_range = self.pwm_output_delta

        # 计算期望的高电平时间（跳过死区）
        sign = 1 if ratio > 0 else -1
        expected_ns = self.pwm_center_ns + sign * self.pwm_deadzone_ns \
            + int(ratio * effective_range)
        expected_ns = max(self.pwm_min_ns, min(self.pwm_max_ns, expected_ns))

        # 转换为 sysfs duty_cycle
        return self._pulse_to_duty_ns(expected_ns)

    def _stop_motors(self) -> None:
        """停止电机（输出中位PWM）"""
        center_duty = self._pulse_to_duty_ns(self.pwm_center_ns)
        self._write_pwm_ns(center_duty, center_duty)
        self.sdk.logger.info("Motors stopped (center PWM)")

    def run(self) -> None:
        """主循环"""
        self.sdk.logger.info("PWM Driver node started")
        self.sdk.logger.info(f"Listening on port: velocity_cmd")
        self.sdk.logger.info(f"Publishing on port: pwm_status")

        try:
            while self.running:
                # 检查紧急停止
                if self.emergency_stop:
                    self._stop_motors()
                    time.sleep(0.1)
                    continue

                # 读取速度命令（非阻塞）
                velocity_data = self.velocity_cmd_port.recv_latest()

                if velocity_data is not None:
                    # 更新最后命令时间
                    self.last_command_time = time.time()

                    # 获取速度命令
                    v_linear = velocity_data.get('linear_velocity', 0.0)
                    w_angular = velocity_data.get('angular_velocity', 0.0)
                    cmd_timestamp = velocity_data.get('timestamp', time.time())

                    # 应用角速度偏置校准
                    w_angular += self.angular_velocity_bias

                    # 安全检查：限制速度范围
                    if self.enable_safety_check:
                        v_linear = max(
                            -self.max_linear_speed,
                            min(self.max_linear_speed, v_linear)
                        )
                        w_angular = max(
                            -self.max_angular_speed,
                            min(self.max_angular_speed, w_angular)
                        )

                    # 运动学计算：速度 → 轮速
                    v_left, v_right = self.kinematics.velocity_to_wheel_speeds(
                        v_linear, w_angular
                    )

                    # 应用左右轮速度缩放校准
                    v_left *= self.left_speed_scale
                    v_right *= self.right_speed_scale

                    # 轮速 → PWM 脉宽 (ns)
                    left_ns = self._speed_to_ns(v_left)
                    right_ns = self._speed_to_ns(v_right)

                    # 输出PWM到硬件
                    self._write_pwm_ns(left_ns, right_ns)

                    # 详细日志
                    if self.enable_verbose_log:
                        self.sdk.logger.debug(
                            f"v={v_linear:.2f}m/s, w={w_angular:.2f}rad/s | "
                            f"v_L={v_left:.2f}, v_R={v_right:.2f} | "
                            f"PWM: L={left_ns}ns, R={right_ns}ns"
                        )

                    # 发布PWM状态
                    pwm_status = {
                        'timestamp': time.time(),
                        'left_duty_ns': left_ns,
                        'right_duty_ns': right_ns,
                        'linear_velocity': v_linear,
                        'angular_velocity': w_angular,
                        'left_wheel_speed': v_left,
                        'right_wheel_speed': v_right,
                        'command_age': time.time() - cmd_timestamp
                    }
                    self.pwm_status_port.send(pwm_status)

                else:
                    # 检查命令超时
                    time_since_last_cmd = time.time() - self.last_command_time
                    if time_since_last_cmd > self.command_timeout:
                        # 超时，停止电机
                        self._stop_motors()
                        # 只记录一次超时日志
                        if time_since_last_cmd < self.command_timeout + 0.1:
                            self.sdk.logger.warning(
                                f"Command timeout ({self.command_timeout}s), motors stopped"
                            )

                # 控制循环频率（200Hz）
                time.sleep(0.005)

        except KeyboardInterrupt:
            self.sdk.logger.info("PWM Driver shutting down (Ctrl+C)")
        except Exception as e:
            self.sdk.logger.error(f"Fatal error in main loop: {e}", exc_info=True)
        finally:
            self.running = False
            self._stop_motors()
            self.cleanup()

    def cleanup(self) -> None:
        """清理资源"""
        try:
            self._stop_motors()
            self.sdk.logger.info("PWM Driver cleanup complete")
        except Exception as e:
            self.sdk.logger.error(f"Error during cleanup: {e}")


def main():
    """节点主入口"""
    with NodeFlowSDK(log_level="INFO") as sdk:
        pwm_driver = PWMDriverNode(sdk)
        pwm_driver.run()


if __name__ == '__main__':
    main()
