"""可复现的二维差速运动学：目标速度、车辆响应、简单扰动。"""

import math
import random
from dataclasses import fields

try:
    from .state import RobotState
except ImportError:
    from state import RobotState


class KinematicsEngine:
    """两种指令共享相同的速度、加速度及一阶响应模型。

    这些参数用于比较闭环控制行为，不代表经过实车标定的土壤动力学。
    vx 为车体前向速度；正角速度为平面坐标中的逆时针转向。
    """

    def __init__(
        self,
        dt: float = 0.01,
        max_speed: float = 2.0,
        max_accel: float = 1.0,
        max_angular_vel: float = 1.0,
        wheelbase: float = 0.5,
        slip_ratio: float = 0.05,
        enable_slip: bool = True,
        terrain_roughness: float = 0.02,
        enable_terrain_noise: bool = True,
        seed: int | None = None,
        max_angular_accel: float = 2.0,
        velocity_response_time_s: float = 0.0,
        angular_response_time_s: float = 0.0,
    ):
        self.dt = dt
        self.max_speed = max_speed
        self.max_accel = max_accel
        self.max_angular_vel = max_angular_vel
        self.wheelbase = wheelbase
        self.slip_ratio = slip_ratio
        self.enable_slip = enable_slip
        self.terrain_roughness = terrain_roughness
        self.enable_terrain_noise = enable_terrain_noise
        self.max_angular_accel = max_angular_accel
        self.velocity_response_time_s = velocity_response_time_s
        self.angular_response_time_s = angular_response_time_s
        self.implement_drag_full = 0.3
        self.seed = seed
        self.rng = random.Random(seed)
        self._validate_parameters()
        self.reset_control()

    @staticmethod
    def _finite(name: str, value: float) -> None:
        try:
            valid = math.isfinite(value)
        except (TypeError, ValueError):
            valid = False
        if not valid:
            raise ValueError(f"{name} must be finite")

    def _validate_parameters(self):
        # 参数可在界面运行期间更改，因此每步也校验。
        for name in ("dt", "max_speed", "max_accel", "max_angular_vel",
                     "max_angular_accel", "wheelbase"):
            value = getattr(self, name)
            self._finite(name, value)
            if value <= 0:
                raise ValueError(f"{name} must be positive")
        for name in ("terrain_roughness", "velocity_response_time_s",
                     "angular_response_time_s"):
            value = getattr(self, name)
            self._finite(name, value)
            if value < 0:
                raise ValueError(f"{name} must be nonnegative")
        for name in ("slip_ratio", "implement_drag_full"):
            value = getattr(self, name)
            self._finite(name, value)
            if not 0 <= value <= 1:
                raise ValueError(f"{name} must be between 0 and 1")

    @staticmethod
    def _clip(value: float, limit: float) -> float:
        return max(-limit, min(limit, value))

    def set_control(self, throttle: float, steering: float):
        """油门/转向模式，输入为 [-1, 1]，正转向为逆时针。"""
        self._finite("throttle", throttle)
        self._finite("steering", steering)
        self.throttle = self._clip(throttle, 1.0)
        self.steering = self._clip(steering, 1.0)
        self.control_mode = "throttle"

    def set_velocity_control(self, linear_vel: float, angular_vel: float):
        """切换到速度模式；(0, 0) 是停车指令，不恢复旧油门。"""
        self._finite("linear_vel", linear_vel)
        self._finite("angular_vel", angular_vel)
        self.linear_velocity = linear_vel
        self.angular_velocity = angular_vel
        self.control_mode = "velocity"

    def set_implement_control(self, hitch_height: float, pto_on: bool,
                              pto_rpm: float = 540.0):
        """悬挂 0=抬起、1=放下；PTO 转速非负。"""
        self._finite("hitch_height", hitch_height)
        self._finite("pto_rpm", pto_rpm)
        if pto_rpm < 0:
            raise ValueError("pto_rpm must be nonnegative")
        self.target_hitch_height = max(0.0, min(1.0, hitch_height))
        self.target_pto_on = bool(pto_on)
        self.target_pto_rpm = pto_rpm

    def reset_rng(self, seed: int | None = None):
        """重播原随机序列；传入 seed 时切换到新的种子。"""
        if seed is not None:
            self.seed = seed
        self.rng.seed(self.seed)
        self.terrain_noise_omega = 0.0

    def reset_control(self):
        """复位指令、机具目标及随机序列；车辆状态由调用者重置。"""
        self.control_mode = "throttle"
        self.throttle = 0.0
        self.steering = 0.0
        self.linear_velocity = 0.0
        self.angular_velocity = 0.0
        self.target_hitch_height = 0.0
        self.target_pto_on = False
        self.target_pto_rpm = 540.0
        self.implement_drag_factor = 0.0
        self.reset_rng()

    def update_terrain_noise(self):
        """有界角速度白噪声，积分后的航向会漂移。"""
        self.terrain_noise_omega = 0.0
        if self.enable_terrain_noise:
            self.terrain_noise_omega = self._clip(
                self.rng.gauss(0.0, self.terrain_roughness / 3.0),
                self.terrain_roughness,
            )

    def apply_slip_noise(self, linear_vel: float, angular_vel: float) -> tuple:
        """简化打滑：降低前向速度，并扰动转弯速度。"""
        if not self.enable_slip:
            return linear_vel, angular_vel
        slip_factor = self.slip_ratio * min(1.0, abs(linear_vel) / self.max_speed)
        return (
            linear_vel * (1.0 - self.rng.uniform(0.0, slip_factor)),
            angular_vel * (1.0 + self.rng.uniform(-slip_factor * 0.5, slip_factor * 0.5)),
        )

    def _animate_implement(self, state: RobotState):
        """悬挂全行程 1.5 秒，PTO 按 0.5 秒启动时间渐变。"""
        state.hitch_height += self._clip(
            self.target_hitch_height - state.hitch_height, self.dt / 1.5,
        )
        target_rpm = self.target_pto_rpm if self.target_pto_on else 0.0
        # 即使目标 RPM 改成 0，也必须能停转。
        rpm_rate = max(540.0, self.target_pto_rpm) / 0.5
        state.pto_rpm += self._clip(target_rpm - state.pto_rpm, rpm_rate * self.dt)
        state.pto_on = state.pto_rpm > 10.0
        self.implement_drag_factor = state.hitch_height * self.implement_drag_full

    def _apply_implement_drag(self, linear_vel: float) -> float:
        if self.implement_drag_factor <= 0:
            return linear_vel
        drag = 1.0 - self.implement_drag_factor * self.rng.uniform(0.8, 1.2)
        return linear_vel * max(0.1, drag)

    def _respond(self, current: float, target: float, rate: float,
                 response_time: float) -> float:
        # 精确一阶响应离散式在 dt 大于时间常数时也不会过冲。
        gain = -math.expm1(-self.dt / response_time) if response_time > 0 else 1.0
        return current + self._clip((target - current) * gain, rate * self.dt)

    def step(self, state: RobotState) -> RobotState:
        """推进固定 dt；模式由最后一次 setter 决定。"""
        if self.control_mode == "velocity":
            return self._step_velocity_control(state)
        return self._step_throttle_control(state)

    def _step_throttle_control(self, state: RobotState) -> RobotState:
        return self._step_motion(state, self.throttle * self.max_speed,
                                 self.steering * self.max_angular_vel)

    def _step_velocity_control(self, state: RobotState) -> RobotState:
        return self._step_motion(state, self.linear_velocity, self.angular_velocity)

    def _step_motion(self, state: RobotState, target_speed: float,
                     target_omega: float) -> RobotState:
        self._validate_parameters()
        self._finite("target_speed", target_speed)
        self._finite("target_omega", target_omega)
        self._finite("target_hitch_height", self.target_hitch_height)
        self._finite("target_pto_rpm", self.target_pto_rpm)
        if not 0 <= self.target_hitch_height <= 1 or self.target_pto_rpm < 0:
            raise ValueError("invalid implement target")
        for item in fields(state):
            self._finite(f"state.{item.name}", getattr(state, item.name))

        new_state = state.copy()
        self._animate_implement(new_state)
        target_speed = self._clip(target_speed, self.max_speed)
        target_omega = self._clip(target_omega, self.max_angular_vel)
        target_speed, target_omega = self.apply_slip_noise(target_speed, target_omega)
        target_speed = self._apply_implement_drag(target_speed)
        self.update_terrain_noise()
        # 地面扰动随车移动产生；停车后不凭空转动。
        if abs(target_speed) > 1e-9 or abs(state.vx) > 1e-9:
            target_omega += self.terrain_noise_omega
        target_speed = self._clip(target_speed, self.max_speed)
        target_omega = self._clip(target_omega, self.max_angular_vel)
        new_state.vx = self._respond(state.vx, target_speed, self.max_accel,
                                     self.velocity_response_time_s)
        new_state.omega_yaw = self._respond(state.omega_yaw, target_omega,
                                            self.max_angular_accel,
                                            self.angular_response_time_s)

        # 在尚未包角的中点积分，避免 +pi/-pi 两侧的均值变成 0。
        delta_yaw = (state.omega_yaw + new_state.omega_yaw) * 0.5 * self.dt
        midpoint_yaw = state.yaw + delta_yaw * 0.5
        distance = (state.vx + new_state.vx) * 0.5 * self.dt
        new_state.x += distance * math.cos(midpoint_yaw)
        new_state.y += distance * math.sin(midpoint_yaw)
        new_state.yaw = math.atan2(math.sin(state.yaw + delta_yaw),
                                   math.cos(state.yaw + delta_yaw))
        new_state.vy = 0.0
        new_state.ax = (new_state.vx - state.vx) / self.dt
        new_state.sim_time += self.dt
        new_state.step_count += 1
        return new_state


class SimplePhysics:
    """
    简单物理模拟（可选）

    添加简单的物理效果：
    - 摩擦力
    - 惯性
    - 碰撞检测（边界）
    """

    def __init__(
        self,
        friction_coeff: float = 0.1,
        bounds_x: tuple = (-100.0, 100.0),
        bounds_y: tuple = (-100.0, 100.0)
    ):
        self.friction_coeff = friction_coeff
        self.bounds_x = bounds_x
        self.bounds_y = bounds_y
        self._validate_parameters()

    def _validate_parameters(self):
        KinematicsEngine._finite("friction_coeff", self.friction_coeff)
        if self.friction_coeff < 0:
            raise ValueError("friction_coeff must be nonnegative")
        for name in ("bounds_x", "bounds_y"):
            bounds = getattr(self, name)
            if len(bounds) != 2:
                raise ValueError(f"{name} must contain two bounds")
            for value in bounds:
                KinematicsEngine._finite(name, value)
            if bounds[0] >= bounds[1]:
                raise ValueError(f"{name} must be increasing")

    def apply_friction(self, state: RobotState, dt: float) -> RobotState:
        """应用摩擦力"""
        self._validate_parameters()
        KinematicsEngine._finite("dt", dt)
        if dt < 0:
            raise ValueError("dt must be nonnegative")
        new_state = state.copy()

        # 速度衰减
        decay = math.exp(-self.friction_coeff * dt)
        new_state.vx *= decay
        new_state.vy *= decay
        new_state.omega_yaw *= decay

        return new_state

    def apply_boundary(self, state: RobotState) -> RobotState:
        """边界碰撞"""
        self._validate_parameters()
        new_state = state.copy()
        new_state.x = max(self.bounds_x[0], min(self.bounds_x[1], state.x))
        new_state.y = max(self.bounds_y[0], min(self.bounds_y[1], state.y))
        if new_state.x != state.x or new_state.y != state.y:
            # vx/vy 是车体坐标速度，并非世界 X/Y 分量。
            new_state.vx = new_state.vy = 0.0

        return new_state
