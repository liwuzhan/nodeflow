#!/usr/bin/env python3
"""
PWM Driver - 原子层 (L4)

纯算法实现，无硬件依赖
- 速度命令 → PWM值转换
- 双轮差速运动学计算
- PWM范围检查和限制
"""

import time
import math
from typing import Dict, Tuple, Any
from dataclasses import dataclass


@dataclass
class VelocityCommand:
    """速度控制命令"""
    linear_velocity: float      # m/s，正向前进
    angular_velocity: float     # rad/s，正向逆时针转向
    timestamp: float            # Unix时间戳


@dataclass
class PWMCommand:
    """PWM输出命令"""
    left_pwm: int               # 左轮PWM值 (0-1023)
    right_pwm: int              # 右轮PWM值 (0-1023)
    timestamp: float            # 计算时间
    linear_velocity: float      # 实际线速度 (m/s)
    angular_velocity: float     # 实际角速度 (rad/s)


class DifferentialDriveKinematics:
    """双轮差速运动学计算"""

    def __init__(
        self,
        wheel_base: float,
        max_linear_speed: float,
        max_angular_speed: float
    ):
        """
        初始化差速驱动运动学

        参数：
        - wheel_base: 履带底盘宽度 (m)
        - max_linear_speed: 最大线速度 (m/s)
        - max_angular_speed: 最大角速度 (rad/s)
        """
        self.wheel_base = wheel_base
        self.max_linear_speed = max_linear_speed
        self.max_angular_speed = max_angular_speed

    def velocity_to_wheel_speeds(
        self,
        linear_velocity: float,
        angular_velocity: float
    ) -> Tuple[float, float]:
        """
        将线速度和角速度转换为左右轮速度

        差速驱动运动学公式：
        v_left = v_linear - (wheel_base/2) * w_angular
        v_right = v_linear + (wheel_base/2) * w_angular

        参数：
        - linear_velocity: 线速度 (m/s)
        - angular_velocity: 角速度 (rad/s)

        返回：
        - (left_wheel_speed, right_wheel_speed) m/s
        """
        half_base = self.wheel_base / 2.0

        v_left = linear_velocity - half_base * angular_velocity
        v_right = linear_velocity + half_base * angular_velocity

        return v_left, v_right

    def wheel_speeds_to_velocity(
        self,
        v_left: float,
        v_right: float
    ) -> Tuple[float, float]:
        """
        从轮速反推线速度和角速度 (用于验证)

        参数：
        - v_left: 左轮速度 (m/s)
        - v_right: 右轮速度 (m/s)

        返回：
        - (linear_velocity, angular_velocity)
        """
        v_linear = (v_left + v_right) / 2.0
        w_angular = (v_right - v_left) / self.wheel_base

        return v_linear, w_angular


class PWMMapper:
    """速度到PWM值的映射"""

    def __init__(
        self,
        pwm_range: int = 1024,
        neutral_pwm: int = 512,
        max_pwm_delta: int = 400,
        min_pwm_threshold: int = 50
    ):
        """
        初始化PWM映射

        参数：
        - pwm_range: PWM总范围 (0-pwm_range)
        - neutral_pwm: 中位PWM值（通常是pwm_range/2）
        - max_pwm_delta: 最大PWM变化量（从中位到最大速度）
        - min_pwm_threshold: 最小PWM阈值（死区）
        """
        self.pwm_range = pwm_range
        self.neutral_pwm = neutral_pwm
        self.max_pwm_delta = max_pwm_delta
        self.min_pwm_threshold = min_pwm_threshold

        self.min_pwm = neutral_pwm - max_pwm_delta
        self.max_pwm = neutral_pwm + max_pwm_delta

    def speed_to_pwm(self, wheel_speed: float, max_speed: float) -> int:
        """
        将轮速转换为PWM值

        映射关系：
        - speed = 0 → PWM = neutral (通常512)
        - speed = max_speed → PWM = neutral + max_delta
        - speed = -max_speed → PWM = neutral - max_delta

        参数：
        - wheel_speed: 轮速 (m/s，正向前进，负向后退)
        - max_speed: 最大轮速 (m/s)

        返回：
        - PWM值 (0-1023)
        """
        if max_speed == 0:
            return self.neutral_pwm

        # 规范化速度 (-1 到 1)
        normalized_speed = wheel_speed / max_speed
        # 限制范围
        normalized_speed = max(-1.0, min(1.0, normalized_speed))

        # 映射到PWM范围
        pwm_value = self.neutral_pwm + normalized_speed * self.max_pwm_delta

        # 应用死区处理
        if abs(pwm_value - self.neutral_pwm) < self.min_pwm_threshold:
            pwm_value = self.neutral_pwm

        # 限制PWM范围
        pwm_value = max(self.min_pwm, min(self.max_pwm, pwm_value))

        return int(round(pwm_value))

    def pwm_to_speed(self, pwm_value: int, max_speed: float) -> float:
        """
        从PWM值反推轮速 (用于验证)

        参数：
        - pwm_value: PWM值 (0-1023)
        - max_speed: 最大轮速 (m/s)

        返回：
        - 轮速 (m/s)
        """
        # 处理死区
        if abs(pwm_value - self.neutral_pwm) < self.min_pwm_threshold:
            return 0.0

        # 规范化PWM
        pwm_delta = pwm_value - self.neutral_pwm
        normalized_speed = pwm_delta / self.max_pwm_delta

        return normalized_speed * max_speed


class PWMController:
    """PWM控制器 - 整合所有计算逻辑"""

    def __init__(
        self,
        wheel_base: float,
        max_linear_speed: float,
        max_angular_speed: float,
        pwm_range: int = 1024,
        neutral_pwm: int = 512,
        max_pwm_delta: int = 400,
        min_pwm_threshold: int = 50,
        enable_safety_check: bool = True
    ):
        """
        初始化PWM控制器

        参数：
        - wheel_base: 履带底盘宽度 (m)
        - max_linear_speed: 最大线速度 (m/s)
        - max_angular_speed: 最大角速度 (rad/s)
        - pwm_range: PWM范围
        - neutral_pwm: 中位PWM值
        - max_pwm_delta: 最大PWM变化量
        - min_pwm_threshold: 最小PWM阈值
        - enable_safety_check: 启用安全检查
        """
        self.kinematics = DifferentialDriveKinematics(
            wheel_base,
            max_linear_speed,
            max_angular_speed
        )
        self.pwm_mapper = PWMMapper(
            pwm_range,
            neutral_pwm,
            max_pwm_delta,
            min_pwm_threshold
        )
        self.enable_safety_check = enable_safety_check
        self.last_command_time = time.time()

    def calculate_pwm(
        self,
        velocity_cmd: VelocityCommand,
        emergency_stop: bool = False
    ) -> PWMCommand:
        """
        根据速度命令计算PWM输出

        参数：
        - velocity_cmd: 速度控制命令
        - emergency_stop: 紧急停止标志

        返回：
        - PWM命令（包含左右轮PWM值）
        """
        # 紧急停止
        if emergency_stop:
            return PWMCommand(
                left_pwm=self.pwm_mapper.neutral_pwm,
                right_pwm=self.pwm_mapper.neutral_pwm,
                timestamp=time.time(),
                linear_velocity=0.0,
                angular_velocity=0.0
            )

        # 获取速度命令
        v_linear = velocity_cmd.linear_velocity
        w_angular = velocity_cmd.angular_velocity

        # 安全检查：限制速度范围
        if self.enable_safety_check:
            v_linear = max(
                -self.kinematics.max_linear_speed,
                min(self.kinematics.max_linear_speed, v_linear)
            )
            w_angular = max(
                -self.kinematics.max_angular_speed,
                min(self.kinematics.max_angular_speed, w_angular)
            )

        # 运动学计算：速度 → 轮速
        v_left, v_right = self.kinematics.velocity_to_wheel_speeds(
            v_linear, w_angular
        )

        # PWM映射：轮速 → PWM值
        left_pwm = self.pwm_mapper.speed_to_pwm(
            v_left,
            self.kinematics.max_linear_speed
        )
        right_pwm = self.pwm_mapper.speed_to_pwm(
            v_right,
            self.kinematics.max_linear_speed
        )

        # 反推实际速度（用于监测）
        actual_v_left = self.pwm_mapper.pwm_to_speed(
            left_pwm,
            self.kinematics.max_linear_speed
        )
        actual_v_right = self.pwm_mapper.pwm_to_speed(
            right_pwm,
            self.kinematics.max_linear_speed
        )
        actual_v_linear, actual_w_angular = \
            self.kinematics.wheel_speeds_to_velocity(
                actual_v_left, actual_v_right
            )

        return PWMCommand(
            left_pwm=left_pwm,
            right_pwm=right_pwm,
            timestamp=time.time(),
            linear_velocity=actual_v_linear,
            angular_velocity=actual_w_angular
        )

    def get_status(self) -> Dict[str, Any]:
        """获取控制器状态"""
        return {
            'wheel_base': self.kinematics.wheel_base,
            'max_linear_speed': self.kinematics.max_linear_speed,
            'max_angular_speed': self.kinematics.max_angular_speed,
            'pwm_range': self.pwm_mapper.pwm_range,
            'neutral_pwm': self.pwm_mapper.neutral_pwm,
            'min_pwm': self.pwm_mapper.min_pwm,
            'max_pwm': self.pwm_mapper.max_pwm,
            'min_pwm_threshold': self.pwm_mapper.min_pwm_threshold,
            'safety_check_enabled': self.enable_safety_check
        }
