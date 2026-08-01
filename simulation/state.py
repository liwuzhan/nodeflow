"""
机器人状态管理

维护机器人的完整状态，包括：
- 位置和姿态
- 速度和角速度
- 时间戳
"""

import time
import math
from dataclasses import dataclass, field
from typing import Tuple, Dict, Any


@dataclass
class RobotState:
    """机器人状态"""

    # 位置 (米)
    x: float = 0.0
    y: float = 0.0
    z: float = 0.0  # 对于地面机器人通常为高度

    # 姿态 (弧度)
    roll: float = 0.0   # 翻滚角
    pitch: float = 0.0  # 俯仰角
    yaw: float = 0.0    # 航向角

    # 线速度 (米/秒)
    vx: float = 0.0  # 前进方向
    vy: float = 0.0  # 横向
    vz: float = 0.0  # 垂直

    # 角速度 (弧度/秒)
    omega_roll: float = 0.0
    omega_pitch: float = 0.0
    omega_yaw: float = 0.0

    # 加速度 (米/秒²)
    ax: float = 0.0
    ay: float = 0.0
    az: float = 9.81  # 重力加速度

    # 仿真时间
    sim_time: float = field(default_factory=time.time)

    # 仿真步数
    step_count: int = 0

    # 机具状态
    hitch_height: float = 0.0   # 0=完全抬起，1=完全放下
    pto_on: bool = False
    pto_rpm: float = 0.0        # 当前 PTO 转速

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "position": {
                "x": self.x,
                "y": self.y,
                "z": self.z
            },
            "orientation": {
                "roll": self.roll,
                "pitch": self.pitch,
                "yaw": self.yaw
            },
            "velocity": {
                "vx": self.vx,
                "vy": self.vy,
                "vz": self.vz
            },
            "angular_velocity": {
                "omega_roll": self.omega_roll,
                "omega_pitch": self.omega_pitch,
                "omega_yaw": self.omega_yaw
            },
            "acceleration": {
                "ax": self.ax,
                "ay": self.ay,
                "az": self.az
            },
            "implement": {
                "hitch_height": self.hitch_height,
                "pto_on": self.pto_on,
                "pto_rpm": self.pto_rpm,
            },
            "sim_time": self.sim_time,
            "step_count": self.step_count
        }

    def get_position_2d(self) -> Tuple[float, float]:
        """获取 2D 位置"""
        return (self.x, self.y)

    def get_heading(self) -> float:
        """获取航向角 (yaw)"""
        return self.yaw

    def get_speed(self) -> float:
        """获取速度大小"""
        return math.sqrt(self.vx**2 + self.vy**2 + self.vz**2)

    def get_speed_2d(self) -> float:
        """获取 2D 速度大小"""
        return math.sqrt(self.vx**2 + self.vy**2)

    def copy(self) -> 'RobotState':
        """创建状态副本"""
        return RobotState(
            x=self.x, y=self.y, z=self.z,
            roll=self.roll, pitch=self.pitch, yaw=self.yaw,
            vx=self.vx, vy=self.vy, vz=self.vz,
            omega_roll=self.omega_roll,
            omega_pitch=self.omega_pitch,
            omega_yaw=self.omega_yaw,
            ax=self.ax, ay=self.ay, az=self.az,
            sim_time=self.sim_time,
            step_count=self.step_count,
            hitch_height=self.hitch_height,
            pto_on=self.pto_on,
            pto_rpm=self.pto_rpm,
        )


class StateHistory:
    """状态历史记录"""

    def __init__(self, max_size: int = 1000):
        self.max_size = max_size
        self.history = []

    def add(self, state: RobotState):
        """添加状态"""
        self.history.append(state.copy())
        if len(self.history) > self.max_size:
            self.history.pop(0)

    def get_latest(self) -> RobotState:
        """获取最新状态"""
        if self.history:
            return self.history[-1]
        return RobotState()

    def get_at_time(self, sim_time: float) -> RobotState:
        """获取指定时间的状态（线性插值）"""
        if not self.history:
            return RobotState()

        # 找到最接近的两个状态
        for i in range(len(self.history) - 1):
            if self.history[i].sim_time <= sim_time <= self.history[i+1].sim_time:
                # 线性插值
                t0 = self.history[i].sim_time
                t1 = self.history[i+1].sim_time
                alpha = (sim_time - t0) / (t1 - t0) if t1 > t0 else 0.0

                s0 = self.history[i]
                s1 = self.history[i+1]

                return RobotState(
                    x=s0.x + alpha * (s1.x - s0.x),
                    y=s0.y + alpha * (s1.y - s0.y),
                    z=s0.z + alpha * (s1.z - s0.z),
                    yaw=s0.yaw + alpha * (s1.yaw - s0.yaw),
                    vx=s0.vx + alpha * (s1.vx - s0.vx),
                    vy=s0.vy + alpha * (s1.vy - s0.vy),
                    sim_time=sim_time
                )

        return self.get_latest()

    def clear(self):
        """清空历史"""
        self.history.clear()
