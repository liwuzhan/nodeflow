#!/usr/bin/env python3
"""
PWM Driver Node - 香橙派5 Ultra电机PWM驱动 (L3 分子层)

使用 Linux sysfs PWM 接口输出 RC PWM 信号 (50Hz, 1ms-2ms 高电平)
"""

import os
import time

from edge.sdk.nodeflow_sdk import NodeFlowSDK

# 导入 L4 原子层 (用于运动学计算)
import atom


class DriveLatchGuard:
    """资源安全锁存守卫（2026-09-01 草案 §5.4 路径一）。

    runtime 在上游控制链故障时断言 drive_pwm 锁存；本节点在每次应用
    速度命令前检查锁存——锁存期间只允许中位，拒绝一切非零命令。
    读取控制面 runtime.safety buffer（固定根目录），seq 未变化时零解码。
    """

    def __init__(self, logger, resource: str = "drive_pwm", reopen_interval: float = 2.0):
        self.logger = logger
        self.resource = resource
        self.reopen_interval = reopen_interval
        self._buf = None
        self._last_seq = -1
        self._latched = False
        self._next_open_attempt = 0.0

    def is_latched(self) -> bool:
        buf = self._acquire()
        if buf is None:
            return False
        try:
            seq = buf.get_sequence()
            if seq != self._last_seq:
                self._last_seq = seq
                data = buf.read()
                resources = (data or {}).get("resources", {})
                entry = resources.get(self.resource) or {}
                self._latched = bool(entry.get("latched"))
            return self._latched
        except Exception:
            self._buf = None  # 下次重开
            return self._latched

    def _acquire(self):
        if self._buf is not None:
            return self._buf
        now = time.monotonic()
        if now < self._next_open_attempt:
            return None
        self._next_open_attempt = now + self.reopen_interval
        try:
            from edge.sdk.shared_buffer_lite import SharedBufferLite

            self._buf = SharedBufferLite("runtime.safety", create=False)
            return self._buf
        except Exception:
            return None  # 锁存 buffer 不存在 = 从未断言

    def close(self):
        if self._buf is not None:
            try:
                self._buf.close()
            except Exception:
                pass
            self._buf = None


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
        self.right_pwmchip = sdk.get_param('right_pwmchip', 'pwmchip4')
        self.right_pwm_channel = int(sdk.get_param('right_pwm_channel', 0))

        # RC PWM 脉宽参数 (纳秒)
        self.pwm_min_ns = int(sdk.get_param('pwm_min_ns', 1000000))      # 1ms
        self.pwm_center_ns = int(sdk.get_param('pwm_center_ns', 1500000)) # 1.5ms
        self.pwm_max_ns = int(sdk.get_param('pwm_max_ns', 2000000))      # 2ms
        self.pwm_duty_scale = float(sdk.get_param('pwm_duty_scale', 0.8))
        self.pwm_inverted_polarity = sdk.get_param('pwm_inverted_polarity', True)

        # 车辆参数
        self.drive_mode = sdk.get_param('drive_mode', 'differential')
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

        # 输入看门狗回调（W3-3）：SDK 看门狗检测断流超时后回中位安全值。
        # 主循环内的 200Hz 内联超时检查保留为快路径，两者幂等。
        self._watchdog_stop_logged = False
        sdk.set_on_input_lost('velocity_cmd', self._on_velocity_cmd_lost)

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
        self._timeout_logged = False

        # 资源安全锁存守卫（2026-09-01 草案）：锁存期间拒绝非零命令
        self.latch_guard = DriveLatchGuard(sdk.logger, resource="drive_pwm")
        self._latch_logged = False

        # 日志配置
        self.sdk.logger.info("PWM Driver initialized (sysfs mode)")
        self.sdk.logger.info(f"  Drive mode: {self.drive_mode}")
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

    def _speed_to_ns(self, speed: float, max_speed: float = None) -> int:
        """将速度转换为 sysfs duty_cycle 值 (ns)

        映射关系（高电平脉宽）：
        - speed = 0 → center_ns
        - speed > 0 → center_ns + deadzone ~ center_ns + output_delta
        - speed < 0 → center_ns - output_delta ~ center_ns - deadzone

        Args:
            speed: 速度值 (m/s 或 rad/s)
            max_speed: 归一化基准速度，默认使用 max_linear_speed
        """
        if max_speed is None:
            max_speed = self.max_linear_speed

        if max_speed == 0 or speed == 0.0:
            return self._pulse_to_duty_ns(self.pwm_center_ns)

        # 规范化速度 (-1 到 1)
        ratio = speed / max_speed
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

    def _stop_motors(self, log: bool = True) -> None:
        """停止电机（输出中位PWM）。

        周期性保持中位的调用方（超时分支 200Hz、看门狗回调）传 log=False，
        自行只记一次日志——否则空闲时每秒刷 200 行。
        """
        center_duty = self._pulse_to_duty_ns(self.pwm_center_ns)
        self._write_pwm_ns(center_duty, center_duty)
        if log:
            self.sdk.logger.info("Motors stopped (center PWM)")

    def _on_velocity_cmd_lost(self, port_name: str) -> None:
        """SDK 输入看门狗回调：断流超时 → 电机回中位（安全值输出，P2 例外）"""
        self._stop_motors(log=False)
        if not self._watchdog_stop_logged:
            self.sdk.logger.warning(
                f"Input watchdog: '{port_name}' stale over timeout, motors at center"
            )
            self._watchdog_stop_logged = True

    def _apply_safety_stop(self, cmd_timestamp: float) -> dict:
        """安全停止命令（safety_stop 语义，草案 §3.8）。

        零线速/零角速在存在 angular_velocity_bias、deadzone 等补偿时仍可能
        产生差速输出——安全停止必须绕过一切补偿，直接输出中位。
        """
        center_duty = self._pulse_to_duty_ns(self.pwm_center_ns)
        self._write_pwm_ns(center_duty, center_duty)
        self.sdk.logger.warning("Safety stop command applied (center PWM, bypassing bias/deadzone)")
        return {
            'timestamp': time.time(),
            'left_duty_ns': center_duty,
            'right_duty_ns': center_duty,
            'linear_velocity': 0.0,
            'angular_velocity': 0.0,
            'safety_stop': True,
            'command_age': time.time() - cmd_timestamp,
        }

    def run(self) -> None:
        """主循环"""
        try:
            # 日志放在 try 内：启动日志期间收到 SIGTERM 也要走 finally 回中位
            self.sdk.logger.info("PWM Driver node started")
            self.sdk.logger.info(f"Listening on port: velocity_cmd")
            self.sdk.logger.info(f"Publishing on port: pwm_status")

            while self.running:
                # 检查紧急停止
                if self.emergency_stop:
                    self._stop_motors()
                    time.sleep(0.1)
                    continue

                # 资源安全锁存（草案 §5.4 路径一）：锁存期间拒绝一切非零命令，
                # 持续中位；唯一解除路径是人工 rearm（runtime.safety epoch 递增）
                if self.latch_guard.is_latched():
                    center_duty = self._pulse_to_duty_ns(self.pwm_center_ns)
                    self._write_pwm_ns(center_duty, center_duty)
                    if not self._latch_logged:
                        self.sdk.logger.warning(
                            "Drive latch asserted: rejecting commands until manual rearm"
                        )
                        self._latch_logged = True
                    self.pwm_status_port.send({
                        'timestamp': time.time(),
                        'left_duty_ns': center_duty,
                        'right_duty_ns': center_duty,
                        'linear_velocity': 0.0,
                        'angular_velocity': 0.0,
                        'latched': True,
                    })
                    time.sleep(0.005)
                    continue
                if self._latch_logged:
                    self.sdk.logger.info("Drive latch released (rearmed)")
                    self._latch_logged = False

                # 读取速度命令（非阻塞）
                velocity_data = self.velocity_cmd_port.recv_latest()

                if velocity_data is not None:
                    # 更新最后命令时间；指令恢复后重新允许超时/看门狗各记一次日志
                    self.last_command_time = time.time()
                    self._timeout_logged = False
                    self._watchdog_stop_logged = False

                    # 获取速度命令
                    v_linear = velocity_data.get('linear_velocity', 0.0)
                    w_angular = velocity_data.get('angular_velocity', 0.0)
                    cmd_timestamp = velocity_data.get('timestamp', time.time())

                    if velocity_data.get('safety_stop'):
                        # 框架 failsafe 命令（草案 §3.8）：绕过 bias/deadzone 直接中位
                        pwm_status = self._apply_safety_stop(cmd_timestamp)
                    elif self.drive_mode == 'direct':
                        # ---- direct 模式：通道1=油门，通道2=转向 ----
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

                        # 直接映射：线速度→通道1, 角速度→通道2
                        ch1_ns = self._speed_to_ns(v_linear, self.max_linear_speed)
                        ch2_ns = self._speed_to_ns(w_angular, self.max_angular_speed)

                        # 输出PWM到硬件
                        self._write_pwm_ns(ch1_ns, ch2_ns)

                        # 详细日志
                        if self.enable_verbose_log:
                            self.sdk.logger.debug(
                                f"[direct] v={v_linear:.2f}m/s, w={w_angular:.2f}rad/s | "
                                f"PWM: CH1={ch1_ns}ns, CH2={ch2_ns}ns"
                            )

                        # 发布PWM状态
                        pwm_status = {
                            'timestamp': time.time(),
                            'left_duty_ns': ch1_ns,
                            'right_duty_ns': ch2_ns,
                            'linear_velocity': v_linear,
                            'angular_velocity': w_angular,
                            'left_wheel_speed': v_linear,
                            'right_wheel_speed': w_angular,
                            'command_age': time.time() - cmd_timestamp
                        }
                    else:
                        # ---- differential 模式（默认）----
                        # 零指令始终保持中位；偏置只校准有意的行走或原地转向。
                        if v_linear != 0.0 or w_angular != 0.0:
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
                        # 超时，持续保持中位；每次超时只记录一次日志
                        self._stop_motors(log=False)
                        if not self._timeout_logged:
                            self.sdk.logger.warning(
                                f"Command timeout ({self.command_timeout}s), motors stopped"
                            )
                            self._timeout_logged = True

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
            self.latch_guard.close()
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
