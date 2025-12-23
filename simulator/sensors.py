"""
传感器模拟

基于机器人状态生成各种传感器数据：
- GPS: 位置数据（带噪声）
- IMU: 加速度、角速度、磁力计
- 里程计: 编码器数据
"""

import math
import random
from typing import Dict, Any
try:
    from .state import RobotState
except ImportError:
    from state import RobotState


class SensorSimulator:
    """传感器模拟器"""

    def __init__(
        self,
        gps_noise_std: float = 0.5,      # GPS 噪声标准差 (米)
        imu_accel_noise: float = 0.1,    # 加速度噪声 (m/s²)
        imu_gyro_noise: float = 0.01,    # 陀螺仪噪声 (rad/s)
        seed: int = None
    ):
        self.gps_noise_std = gps_noise_std
        self.imu_accel_noise = imu_accel_noise
        self.imu_gyro_noise = imu_gyro_noise

        if seed is not None:
            random.seed(seed)

        # GPS 参考点 (用于转换为经纬度)
        self.gps_ref_lat = 40.7128  # 纽约纬度
        self.gps_ref_lon = -74.0060  # 纽约经度

        # 度/米转换系数（近似）
        self.meters_per_degree_lat = 111000.0  # 1度纬度 ≈ 111km
        self.meters_per_degree_lon = 85000.0   # 1度经度 ≈ 85km (at 40°N)

        # RTK GPS 状态模拟
        self.rtk_fix_count = 0
        self.rtk_float_count = 0
        self.rtk_single_count = 0
        self.last_rtk_status = "FIXED"
        self.rtk_failure_probability = 0.001  # 0.1% 的概率丢失RTK

    def get_rtk_gps_data(self, state: RobotState) -> Dict[str, Any]:
        """
        生成 RTK GPS 数据 (厘米级精度)

        支持多种RTK状态：
        - FIXED: RTK固定解 (2cm精度)
        - FLOAT: RTK浮点解 (10cm精度)
        - SINGLE: 单点定位 (0.5m精度)
        - NONE: 无定位
        """
        # RTK 状态模拟
        rtk_probability = random.random()

        if rtk_probability < 0.85:  # 85% 时间固定解
            rtk_status = "FIXED"
            gps_noise_std = 0.02  # 2cm
            self.rtk_fix_count += 1
        elif rtk_probability < 0.95:  # 10% 时间浮点解
            rtk_status = "FLOAT"
            gps_noise_std = 0.1   # 10cm
            self.rtk_float_count += 1
        elif rtk_probability < 0.99:  # 4% 时间单点定位
            rtk_status = "SINGLE"
            gps_noise_std = 0.5   # 50cm
            self.rtk_single_count += 1
        else:  # 1% 时间丢失定位
            rtk_status = "NONE"
            gps_noise_std = 5.0   # 5m
            self.rtk_single_count += 1

        # RTK 固定解的状态持续性（避免频繁切换）
        if self.last_rtk_status == "FIXED" and rtk_probability > 0.95:
            rtk_status = "FIXED"
            gps_noise_std = 0.02
            self.rtk_fix_count += 1

        # 添加位置噪声
        if rtk_status == "NONE":
            # 无定位时，使用最后已知位置加噪声
            if hasattr(self, '_last_position'):
                base_x, base_y = self._last_position
            else:
                base_x, base_y = state.x, state.y
            noise_x = random.gauss(0, gps_noise_std * 2)
            noise_y = random.gauss(0, gps_noise_std * 2)
        else:
            # 有定位时，基于当前位置
            noise_x = random.gauss(0, gps_noise_std)
            noise_y = random.gauss(0, gps_noise_std)
            base_x, base_y = state.x, state.y
            self._last_position = (base_x, base_y)

        noisy_x = base_x + noise_x
        noisy_y = base_y + noise_y

        # RTK 特有的误差模式
        if rtk_status in ["FIXED", "FLOAT"]:
            # 周跳误差（偶尔的厘米级跳变）
            if random.random() < 0.001:  # 0.1% 概率
                jump_x = random.gauss(0, 0.1)
                jump_y = random.gauss(0, 0.1)
                noisy_x += jump_x
                noisy_y += jump_y

            # 多路径效应（建筑、地形反射）
            if rtk_status == "FLOAT":
                # 浮点解更容易受多路径影响
                multipath_x = random.gauss(0, 0.05)
                multipath_y = random.gauss(0, 0.05)
                noisy_x += multipath_x
                noisy_y += multipath_y

        # 转换为经纬度
        lat = self.gps_ref_lat + (noisy_y / self.meters_per_degree_lat)
        lon = self.gps_ref_lon + (noisy_x / self.meters_per_degree_lon)

        # RTK 特有的精度指标
        if rtk_status == "FIXED":
            accuracy_h = 0.02  # 水平精度 2cm
            accuracy_v = 0.03  # 垂直精度 3cm
            hdop = 0.5
            vdop = 0.8
            fix_type = 50  # NMEA 固定解类型
        elif rtk_status == "FLOAT":
            accuracy_h = 0.1   # 水平精度 10cm
            accuracy_v = 0.15  # 垂直精度 15cm
            hdop = 0.8
            vdop = 1.2
            fix_type = 49  # NMEA 浮点解类型
        else:
            accuracy_h = 1.0   # 水平精度 1m
            accuracy_v = 1.5   # 垂直精度 1.5m
            hdop = 2.0
            vdop = 3.0
            fix_type = 1

        # 卫星数和信号质量
        if rtk_status == "FIXED":
            num_satellites = random.randint(12, 16)
            snr_avg = random.uniform(45, 50)  # 高信噪比
        elif rtk_status == "FLOAT":
            num_satellites = random.randint(8, 12)
            snr_avg = random.uniform(40, 45)
        else:
            num_satellites = random.randint(4, 8)
            snr_avg = random.uniform(35, 40)

        # RTK 年龄（距离上次改正的时间）
        if rtk_status in ["FIXED", "FLOAT"]:
            age_of_diff = random.uniform(0.1, 2.0)  # 秒
        else:
            age_of_diff = 0.0

        self.last_rtk_status = rtk_status

        return {
            # 基础位置信息
            "latitude": lat,
            "longitude": lon,
            "altitude": state.z + random.gauss(0, accuracy_v),

            # RTK 状态
            "rtk_status": rtk_status,
            "solution_type": "RTK_FIXED" if rtk_status == "FIXED" else (
                "RTK_FLOAT" if rtk_status == "FLOAT" else "GPS_SINGLE"
            ),

            # 精度信息
            "accuracy_h": accuracy_h,
            "accuracy_v": accuracy_v,
            "hdop": hdop,
            "vdop": vdop,

            # 卫星信息
            "num_satellites": num_satellites,
            "snr_avg": snr_avg,
            "fix_type": fix_type,

            # RTK 特有信息
            "age_of_diff": age_of_diff,
            "baseline_length": random.uniform(5.0, 30.0),  # 基线长度
            "ratio": random.uniform(3.0, 10.0) if rtk_status == "FIXED" else random.uniform(2.0, 3.0),

            # 双天线 RTK 输出（航向和俯仰）
            "heading": math.degrees(state.yaw),      # 航向角 (0-360度, 正北为0)
            "pitch": math.degrees(state.pitch),      # 俯仰角 (度, 机体向上为正)
            "roll": math.degrees(state.roll),        # 侧滚角 (度, 可选)

            # 标准信息
            "timestamp": state.sim_time,
            "fix_quality": 4 if rtk_status == "FIXED" else (
                3 if rtk_status == "FLOAT" else 1
            )
        }

    def get_gps_data(self, state: RobotState) -> Dict[str, Any]:
        """
        保持原有 GPS 数据格式（向后兼容）
        """
        # 使用普通GPS模式
        noise_x = random.gauss(0, self.gps_noise_std)
        noise_y = random.gauss(0, self.gps_noise_std)

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

    def get_imu_data(self, state: RobotState) -> Dict[str, Any]:
        """
        生成 IMU 数据

        包括：
        - 加速度 (m/s²)
        - 角速度 (rad/s)
        - 磁力计 (方向)
        """
        # 加速度（包含重力）
        # 在机器人坐标系中，需要考虑姿态
        ax_noise = random.gauss(0, self.imu_accel_noise)
        ay_noise = random.gauss(0, self.imu_accel_noise)
        az_noise = random.gauss(0, self.imu_accel_noise)

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
        gyro_x_noise = random.gauss(0, self.imu_gyro_noise)
        gyro_y_noise = random.gauss(0, self.imu_gyro_noise)
        gyro_z_noise = random.gauss(0, self.imu_gyro_noise)

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

    def get_odometry_data(self, state: RobotState) -> Dict[str, Any]:
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
            angle_idx = random.randint(0, num_rays - 1)
            ranges[angle_idx] = random.uniform(1.0, max_range)

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
