"""
传感器模拟

基于机器人状态生成各种传感器数据：
- GPS: 位置数据（带噪声）
- IMU: 加速度、角速度、磁力计
- 里程计: 编码器数据
"""

import math
import random
import copy
from collections import deque
from typing import Dict, Any
try:
    from .state import RobotState
except ImportError:
    from state import RobotState


class SensorSimulator:
    """传感器模拟器"""

    def __init__(
        self,
        ref_lat: float = 31.2,
        ref_lon: float = 121.5,
        gps_noise_std: float = 0.5,      # GPS 噪声标准差 (米)
        imu_accel_noise: float = 0.1,    # 加速度噪声 (m/s²)
        imu_gyro_noise: float = 0.01,    # 陀螺仪噪声 (rad/s)
        seed: int = None,
        rtk_config: Dict[str, Any] = None,
        frequencies: Dict[str, float] = None
    ):
        self.gps_noise_std = gps_noise_std
        self.imu_accel_noise = imu_accel_noise
        self.imu_gyro_noise = imu_gyro_noise

        self._rng = random.Random(seed)
        self._initial_rng_state = self._rng.getstate()
        self.rtk_config = dict(rtk_config or {})
        self.heading_mode = self.rtk_config.get("heading_mode", "dual_antenna")
        if self.heading_mode not in ("dual_antenna", "position_delta"):
            raise ValueError("rtk.heading_mode must be dual_antenna or position_delta")
        self.heading_noise_std_deg = self._nonnegative("heading_noise_std_deg", 0.0)
        self.position_noise_std = self.rtk_config.get("position_noise_std")
        if self.position_noise_std is not None:
            self.position_noise_std = self._nonnegative("position_noise_std", 0.02)
        self.latency_s = self._nonnegative("latency_s", 0.0)
        self.min_heading_displacement_m = self._nonnegative("min_heading_displacement_m", 0.01)
        self.fixed_status = self.rtk_config.get("status")
        if self.fixed_status is not None and self.fixed_status not in ("FIXED", "FLOAT", "SINGLE", "NONE"):
            raise ValueError("rtk.status must be FIXED, FLOAT, SINGLE or NONE")
        self.status_ratios = [float(self.rtk_config.get(key, default)) for key, default in (
            ("fixed_ratio", 0.85), ("float_ratio", 0.10),
            ("single_ratio", 0.04), ("none_ratio", 0.01))]
        if any(not math.isfinite(x) or x < 0 for x in self.status_ratios) or sum(self.status_ratios) <= 0:
            raise ValueError("RTK state ratios must be nonnegative with positive total")
        rates = {"gps": 10.0, "rtk_gps": self.rtk_config.get("frequency", 50.0),
                 "imu": 100.0, "odometry": 50.0}
        rates.update(frequencies or {})
        self._periods = {}
        for name, rate in rates.items():
            rate = float(rate)
            if not math.isfinite(rate) or rate <= 0:
                raise ValueError(f"{name} frequency must be finite and positive")
            self._periods[name] = 1.0 / rate

        # GPS 参考点 (用于转换为经纬度)
        self.gps_ref_lat = ref_lat
        self.gps_ref_lon = ref_lon

        # 度/米转换系数（近似）
        self.meters_per_degree_lat = 111320.0  # WGS84 平均
        self.meters_per_degree_lon = 111320.0 * math.cos(math.radians(self.gps_ref_lat))

        self.reset()

    def _nonnegative(self, name, default):
        value = float(self.rtk_config.get(name, default))
        if not math.isfinite(value) or value < 0:
            raise ValueError(f"rtk.{name} must be finite and nonnegative")
        return value

    def reset(self):
        """清除交付缓存和延迟队列，并重放本实例的噪声序列。"""
        self._rng.setstate(self._initial_rng_state)
        self._cache = {name: None for name in self._periods}
        self._pending = {name: deque() for name in self._periods}
        self._sample_count = {name: 0 for name in self._periods}
        self._epoch = None
        self._last_update = None
        self._previous_state = None
        self._last_position = None
        self._last_observed_position = None
        self._last_heading = 0.0
        self.rtk_fix_count = self.rtk_float_count = self.rtk_single_count = 0
        self.last_rtk_status = "FIXED"

    def update(self, state: RobotState):
        """只由仿真步进调用；按固定仿真时间采样，查询不消耗随机数。

        当步长不能整除采样周期时，在相邻真值之间插值采样；timestamp
        始终是采集时刻，latency_s 只决定何时能从 get_* 读到它。
        """
        now = state.sim_time
        if self._last_update is not None and now < self._last_update - 1e-7:
            raise ValueError("Sensor time moved backwards; call reset() before a new run")
        if self._epoch is None:
            self._epoch = now
        generators = {"gps": self._sample_gps, "rtk_gps": self._sample_rtk,
                      "imu": self._sample_imu, "odometry": self._sample_odometry}
        for name, period in self._periods.items():
            if name not in generators:
                continue
            while self._epoch + self._sample_count[name] * period <= now + 1e-7:
                acquired = self._epoch + self._sample_count[name] * period
                sampled = self._interpolate_state(state, acquired)
                data = generators[name](sampled)
                self._sample_count[name] += 1
                data["seq"] = self._sample_count[name]
                delay = self.latency_s if name == "rtk_gps" else 0.0
                self._pending[name].append((acquired + delay, data))
            while self._pending[name] and self._pending[name][0][0] <= now + 1e-7:
                _, self._cache[name] = self._pending[name].popleft()
        self._last_update = now
        self._previous_state = state.copy()

    def _interpolate_state(self, state, acquired):
        result = state.copy()
        previous = self._previous_state
        if previous is not None and state.sim_time > previous.sim_time:
            alpha = max(0.0, min(1.0, (acquired - previous.sim_time) / (state.sim_time - previous.sim_time)))
            for name in ("x", "y", "z", "vx", "vy", "vz", "ax", "ay", "az", "omega_yaw"):
                setattr(result, name, getattr(previous, name) + alpha * (getattr(state, name) - getattr(previous, name)))
            delta = math.atan2(math.sin(state.yaw - previous.yaw), math.cos(state.yaw - previous.yaw))
            result.yaw = previous.yaw + alpha * delta
        result.sim_time = acquired
        return result

    def get_rtk_gps_data(self, state=None):
        return copy.deepcopy(self._cache["rtk_gps"])

    def get_gps_data(self, state=None):
        return copy.deepcopy(self._cache["gps"])

    def get_imu_data(self, state=None):
        return copy.deepcopy(self._cache["imu"])

    def get_odometry_data(self, state=None):
        return copy.deepcopy(self._cache["odometry"])

    def _sample_rtk(self, state: RobotState) -> Dict[str, Any]:
        status = self.fixed_status or self._rng.choices(
            ["FIXED", "FLOAT", "SINGLE", "NONE"], weights=self.status_ratios)[0]
        default_std = {"FIXED": 0.02, "FLOAT": 0.1, "SINGLE": 0.5, "NONE": 5.0}[status]
        noise_std = default_std if self.position_noise_std is None else self.position_noise_std
        base = (state.x, state.y)
        if status == "NONE" and self._last_position is not None:
            base = self._last_position
        if status != "NONE":
            self._last_position = base
        x = base[0] + self._rng.gauss(0, noise_std)
        y = base[1] + self._rng.gauss(0, noise_std)
        heading_valid = status != "NONE"
        if self.heading_mode == "position_delta":
            heading_valid = False
            if self._last_observed_position is not None and status != "NONE":
                dx = x - self._last_observed_position[0]
                dy = y - self._last_observed_position[1]
                if math.hypot(dx, dy) >= self.min_heading_displacement_m:
                    self._last_heading = math.degrees(math.atan2(dx, dy)) % 360.0
                    heading_valid = True
            heading = self._last_heading
        else:
            heading = (90.0 - math.degrees(state.yaw)) % 360.0
        self._last_observed_position = (x, y) if status != "NONE" else None
        heading = (heading + self._rng.gauss(0, self.heading_noise_std_deg)) % 360.0
        self.last_rtk_status = status
        if status == "FIXED":
            self.rtk_fix_count += 1
        elif status == "FLOAT":
            self.rtk_float_count += 1
        else:
            self.rtk_single_count += 1
        satellites = {"FIXED": 14, "FLOAT": 10, "SINGLE": 6, "NONE": 0}[status]
        accuracy_v = noise_std * 1.5
        return {
            "latitude": self.gps_ref_lat + y / self.meters_per_degree_lat,
            "longitude": self.gps_ref_lon + x / self.meters_per_degree_lon,
            "altitude": state.z + self._rng.gauss(0, accuracy_v),
            "rtk_status": status,
            "solution_type": {"FIXED": "RTK_FIXED", "FLOAT": "RTK_FLOAT", "SINGLE": "GPS_SINGLE", "NONE": "NONE"}[status],
            "accuracy_h": noise_std, "accuracy_v": accuracy_v,
            "hdop": 0.5 if status == "FIXED" else 2.0,
            "vdop": 0.8 if status == "FIXED" else 3.0,
            "num_satellites": satellites, "snr_avg": 47.0 if status == "FIXED" else 40.0,
            "fix_type": {"FIXED": 50, "FLOAT": 49, "SINGLE": 1, "NONE": 0}[status],
            "age_of_diff": 0.1 if status in ("FIXED", "FLOAT") else 0.0,
            "baseline_length": 10.0, "ratio": 5.0 if status == "FIXED" else 2.0,
            "heading": heading, "heading_valid": heading_valid, "heading_mode": self.heading_mode,
            "pitch": math.degrees(state.pitch), "roll": math.degrees(state.roll),
            "timestamp": state.sim_time,
            "fix_quality": {"FIXED": 4, "FLOAT": 3, "SINGLE": 1, "NONE": 0}[status],
        }

    def _sample_gps(self, state: RobotState) -> Dict[str, Any]:
        """
        保持原有 GPS 数据格式（向后兼容）
        """
        # 使用普通GPS模式
        noise_x = self._rng.gauss(0, self.gps_noise_std)
        noise_y = self._rng.gauss(0, self.gps_noise_std)

        noisy_x = state.x + noise_x
        noisy_y = state.y + noise_y

        # 转换为经纬度
        lat = self.gps_ref_lat + (noisy_y / self.meters_per_degree_lat)
        lon = self.gps_ref_lon + (noisy_x / self.meters_per_degree_lon)

        # 计算 HDOP
        hdop = self.gps_noise_std / 0.5

        return {
            "latitude": lat,
            "longitude": lon,
            "altitude": state.z,
            "hdop": hdop,
            "fix_quality": 4,  # 4 = RTK Fixed
            "num_satellites": 12,
            "timestamp": state.sim_time
        }

    def _sample_imu(self, state: RobotState) -> Dict[str, Any]:
        """
        生成 IMU 数据

        包括：
        - 加速度 (m/s²)
        - 角速度 (rad/s)
        - 磁力计 (方向)
        """
        # 加速度（包含重力）
        # 在机器人坐标系中，需要考虑姿态
        ax_noise = self._rng.gauss(0, self.imu_accel_noise)
        ay_noise = self._rng.gauss(0, self.imu_accel_noise)
        az_noise = self._rng.gauss(0, self.imu_accel_noise)

        # 世界坐标系加速度
        ax_world = state.ax
        ay_world = state.ay
        az_world = state.az  # 包含重力

        # 旋转到机体坐标系（简化：只考虑 yaw）
        cos_yaw = math.cos(state.yaw)
        sin_yaw = math.sin(state.yaw)

        ax_body = ax_world * cos_yaw + ay_world * sin_yaw
        ay_body = -ax_world * sin_yaw + ay_world * cos_yaw
        az_body = az_world

        # 角速度
        gyro_x_noise = self._rng.gauss(0, self.imu_gyro_noise)
        gyro_y_noise = self._rng.gauss(0, self.imu_gyro_noise)
        gyro_z_noise = self._rng.gauss(0, self.imu_gyro_noise)

        # 磁力计（指向北方）
        # 简化：在世界坐标系中，北方是 +Y 方向
        mag_north_x = -math.sin(state.yaw)
        mag_north_y = math.cos(state.yaw)
        mag_north_z = 0.0

        return {
            "accel": {
                "x": ax_body + ax_noise,
                "y": ay_body + ay_noise,
                "z": az_body + az_noise
            },
            "gyro": {
                "x": state.omega_roll + gyro_x_noise,
                "y": state.omega_pitch + gyro_y_noise,
                "z": state.omega_yaw + gyro_z_noise
            },
            "mag": {
                "x": mag_north_x,
                "y": mag_north_y,
                "z": mag_north_z
            },
            "timestamp": state.sim_time
        }

    def _sample_odometry(self, state: RobotState) -> Dict[str, Any]:
        """
        生成里程计数据

        基于轮式编码器的位置估计
        """
        # 里程计通常有累积误差
        # 这里简化处理，直接使用状态
        return {
            "position": {
                "x": state.x,
                "y": state.y,
                "theta": state.yaw
            },
            "velocity": {
                "linear": state.vx,
                "angular": state.omega_yaw
            },
            "timestamp": state.sim_time
        }

    def get_lidar_scan(self, state: RobotState, num_rays: int = 360) -> Dict[str, Any]:
        """
        生成 LiDAR 扫描数据（简化版）

        这里只是占位实现，实际需要光线追踪
        """
        # 简化：假设在空旷环境，所有距离都是最大值
        max_range = 30.0
        ranges = [max_range] * num_rays

        # 添加一些随机障碍物
        for _ in range(5):
            angle_idx = self._rng.randint(0, num_rays - 1)
            ranges[angle_idx] = self._rng.uniform(1.0, max_range)

        return {
            "ranges": ranges,
            "angle_min": -math.pi,
            "angle_max": math.pi,
            "angle_increment": 2 * math.pi / num_rays,
            "range_min": 0.1,
            "range_max": max_range,
            "timestamp": state.sim_time
        }


class SensorNoise:
    """传感器噪声模型"""

    @staticmethod
    def white_noise(std: float) -> float:
        """白噪声"""
        return random.gauss(0, std)

    @staticmethod
    def random_walk(current: float, std: float, dt: float) -> float:
        """随机游走（用于漂移）"""
        return current + random.gauss(0, std * math.sqrt(dt))

    @staticmethod
    def dropout(value: float, dropout_rate: float = 0.01) -> float:
        """数据丢失"""
        if random.random() < dropout_rate:
            return None
        return value
