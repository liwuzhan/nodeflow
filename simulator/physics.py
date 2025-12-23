"""
运动学引擎

实现简单的 2D 差速驱动机器人运动学模型：
- 输入：油门 (throttle) 和 转向 (steering)
- 输出：更新后的机器人状态
"""

import math
try:
    from .state import RobotState
except ImportError:
    from state import RobotState


class KinematicsEngine:
    """运动学引擎"""

    def __init__(
        self,
        dt: float = 0.01,                # 时间步长 (秒)
        max_speed: float = 2.0,          # 最大速度 (米/秒)
        max_accel: float = 1.0,          # 最大加速度 (米/秒²)
        max_angular_vel: float = 1.0,    # 最大角速度 (弧度/秒)
        wheelbase: float = 0.5,          # 轮距 (米)
        slip_ratio: float = 0.05,        # 打滑比例 (0-1, 默认5%)
        enable_slip: bool = True,        # 是否启用打滑模拟
        terrain_roughness: float = 0.02, # 地面不平导致的角速度偏移幅度 (rad/s)
        enable_terrain_noise: bool = True # 是否启用地面不平噪声
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

        # 当前控制指令（支持两种模式）
        # 模式1：油门和转向
        self.throttle = 0.0  # [-1, 1]
        self.steering = 0.0  # [-1, 1]

        # 模式2：线速度和角速度（农田作业模式）
        self.linear_velocity = 0.0   # m/s
        self.angular_velocity = 0.0  # rad/s

        # 地面不平噪声状态（完全随机模型）
        # 每个时间步都是独立的随机偏移，会累积导致轨迹偏离
        self.terrain_noise_omega = 0.0    # 当前的角速度偏移值 (rad/s)

    def set_control(self, throttle: float, steering: float):
        """
        设置控制指令（油门+转向模式）

        Args:
            throttle: 油门，范围 [-1, 1]
                     正值前进，负值后退
            steering: 转向，范围 [-1, 1]
                     正值右转，负值左转
        """
        self.throttle = max(-1.0, min(1.0, throttle))
        self.steering = max(-1.0, min(1.0, steering))

    def set_velocity_control(self, linear_vel: float, angular_vel: float):
        """
        设置速度控制（农田作业模式）

        Args:
            linear_vel: 线速度 (m/s)
            angular_vel: 角速度 (rad/s)
        """
        self.linear_velocity = linear_vel
        self.angular_velocity = angular_vel

    def update_terrain_noise(self):
        """
        更新地面不平导致的角速度偏移

        使用完全随机模型（Random Walk）：
        - 每个时间步添加一个独立的随机偏移
        - 偏移会累积，不会自动回归到0
        - 符合实际情况：没有GPS反馈时，机器人会持续偏离

        这更真实地模拟了农田作业中的情况：
        - 地面不平是完全随机的
        - 偏移会累积导致轨迹偏离
        - 必须依靠GPS闭环控制来纠正
        """
        if not self.enable_terrain_noise:
            return

        import random

        # 完全随机的角速度偏移
        # 每次都是独立的随机值，范围在 [-roughness, +roughness]
        # 使用正态分布，标准差为 roughness/3（这样99.7%的值在±roughness内）
        white_noise = random.gauss(0, self.terrain_roughness / 3.0)

        # 限制在合理范围内（防止极端值）
        max_offset = self.terrain_roughness
        self.terrain_noise_omega = max(-max_offset, min(max_offset, white_noise))

    def apply_slip_noise(self, linear_vel: float, angular_vel: float) -> tuple:
        """
        应用打滑噪声模型

        农田作业中的打滑特点：
        - 线速度只能降低（打滑导致速度损失）
        - 角速度有偏差（左右轮速度不一致）
        - 速度越快，打滑越严重

        Args:
            linear_vel: 理想线速度
            angular_vel: 理想角速度

        Returns:
            (实际线速度, 实际角速度)
        """
        if not self.enable_slip:
            return linear_vel, angular_vel

        # 速度依赖的打滑系数
        # 速度越快，打滑系数越高
        speed_factor = abs(linear_vel) / self.max_speed if self.max_speed > 0 else 0
        slip_factor = self.slip_ratio * speed_factor

        # 线速度打滑（只能减少）
        # 使用随机的打滑程度，在 [0, slip_factor] 之间
        import random
        actual_slip = random.uniform(0, slip_factor)
        linear_vel_real = linear_vel * (1.0 - actual_slip)

        # 角速度打滑（可正可负，模拟左右轮不一致）
        # 角速度噪声通常比线速度小
        angular_slip = random.uniform(-slip_factor * 0.5, slip_factor * 0.5)
        angular_vel_real = angular_vel * (1.0 + angular_slip)

        return linear_vel_real, angular_vel_real

    def step(self, state: RobotState) -> RobotState:
        """
        更新机器人状态

        支持两种控制模式：
        1. 油门+转向模式（throttle/steering）
        2. 速度控制模式（linear_velocity/angular_velocity，农田作业模式）
        """
        # 判断使用哪种控制模式
        # 如果设置了速度控制，优先使用速度控制模式
        if abs(self.linear_velocity) > 1e-6 or abs(self.angular_velocity) > 1e-6:
            return self._step_velocity_control(state)
        else:
            return self._step_throttle_control(state)

    def _step_throttle_control(self, state: RobotState) -> RobotState:
        """油门+转向控制模式（也包含地面不平噪声）"""
        # 1. 更新地面不平导致的角速度偏移
        self.update_terrain_noise()

        # 2. 计算目标速度
        target_speed = self.throttle * self.max_speed

        # 当前速度
        current_speed = state.vx

        # 加速度限制
        speed_diff = target_speed - current_speed
        max_speed_change = self.max_accel * self.dt
        if abs(speed_diff) > max_speed_change:
            speed_diff = max_speed_change if speed_diff > 0 else -max_speed_change

        new_speed = current_speed + speed_diff

        # 3. 计算角速度，并加上地面不平偏移
        angular_vel = self.steering * self.max_angular_vel
        angular_vel += self.terrain_noise_omega  # 地面不平导致的偏移

        # 4. 更新姿态
        new_yaw = state.yaw + angular_vel * self.dt
        # 归一化到 [-pi, pi]
        new_yaw = math.atan2(math.sin(new_yaw), math.cos(new_yaw))

        # 5. 更新位置（使用中点法积分）
        avg_yaw = (state.yaw + new_yaw) / 2.0
        dx = new_speed * math.cos(avg_yaw) * self.dt
        dy = new_speed * math.sin(avg_yaw) * self.dt

        new_x = state.x + dx
        new_y = state.y + dy

        # 6. 计算加速度
        ax = (new_speed - current_speed) / self.dt if self.dt > 0 else 0.0

        # 7. 创建新状态
        new_state = state.copy()
        new_state.x = new_x
        new_state.y = new_y
        new_state.yaw = new_yaw
        new_state.vx = new_speed
        new_state.vy = 0.0  # 差速驱动无横向速度
        new_state.omega_yaw = angular_vel
        new_state.ax = ax
        new_state.sim_time += self.dt
        new_state.step_count += 1

        return new_state

    def _step_velocity_control(self, state: RobotState) -> RobotState:
        """速度控制模式（农田作业模式，带打滑噪声和地面不平噪声）"""
        # 1. 更新地面不平导致的角速度偏移
        self.update_terrain_noise()

        # 2. 应用打滑噪声
        linear_vel_real, angular_vel_real = self.apply_slip_noise(
            self.linear_velocity, self.angular_velocity
        )

        # 3. 应用地面不平导致的角速度偏移
        #    这是一个角度值（不是百分比），即使线速度为0也会存在
        angular_vel_real += self.terrain_noise_omega

        # 4. 更新姿态
        new_yaw = state.yaw + angular_vel_real * self.dt
        # 归一化到 [-pi, pi]
        new_yaw = math.atan2(math.sin(new_yaw), math.cos(new_yaw))

        # 5. 更新位置（使用中点法积分）
        avg_yaw = (state.yaw + new_yaw) / 2.0
        dx = linear_vel_real * math.cos(avg_yaw) * self.dt
        dy = linear_vel_real * math.sin(avg_yaw) * self.dt

        new_x = state.x + dx
        new_y = state.y + dy

        # 6. 计算加速度
        current_speed = state.vx
        ax = (linear_vel_real - current_speed) / self.dt if self.dt > 0 else 0.0

        # 7. 创建新状态
        new_state = state.copy()
        new_state.x = new_x
        new_state.y = new_y
        new_state.yaw = new_yaw
        new_state.vx = linear_vel_real
        new_state.vy = 0.0  # 差速驱动无横向速度
        new_state.omega_yaw = angular_vel_real
        new_state.ax = ax
        new_state.sim_time += self.dt
        new_state.step_count += 1

        return new_state

    def reset_control(self):
        """重置控制指令"""
        self.throttle = 0.0
        self.steering = 0.0
        self.linear_velocity = 0.0
        self.angular_velocity = 0.0
        self.terrain_noise_omega = 0.0  # 重置地面噪声


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

    def apply_friction(self, state: RobotState, dt: float) -> RobotState:
        """应用摩擦力"""
        new_state = state.copy()

        # 速度衰减
        decay = math.exp(-self.friction_coeff * dt)
        new_state.vx *= decay
        new_state.vy *= decay
        new_state.omega_yaw *= decay

        return new_state

    def apply_boundary(self, state: RobotState) -> RobotState:
        """边界碰撞"""
        new_state = state.copy()

        # X 边界
        if new_state.x < self.bounds_x[0]:
            new_state.x = self.bounds_x[0]
            new_state.vx = 0.0
        elif new_state.x > self.bounds_x[1]:
            new_state.x = self.bounds_x[1]
            new_state.vx = 0.0

        # Y 边界
        if new_state.y < self.bounds_y[0]:
            new_state.y = self.bounds_y[0]
            new_state.vy = 0.0
        elif new_state.y > self.bounds_y[1]:
            new_state.y = self.bounds_y[1]
            new_state.vy = 0.0

        return new_state
