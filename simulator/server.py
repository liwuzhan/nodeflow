#!/usr/bin/env python3
"""
仿真器 ZMQ 服务器

提供 REQ/REP 协议的 API 接口：
- GET /sensors/gps
- GET /sensors/imu
- GET /sensors/odometry
- POST /actuators/motor
- GET /state
"""

import zmq
import json
import time
import threading
import logging
import yaml
from pathlib import Path
from typing import Dict, Any

try:
    from .state import RobotState, StateHistory
    from .physics import KinematicsEngine, SimplePhysics
    from .sensors import SensorSimulator
    from .field_generator import FieldGenerator, PredefinedFields
except ImportError:
    # 直接运行时使用绝对导入
    from state import RobotState, StateHistory
    from physics import KinematicsEngine, SimplePhysics
    from sensors import SensorSimulator
    from field_generator import FieldGenerator, PredefinedFields

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s'
)
logger = logging.getLogger(__name__)


class SimulatorServer:
    """仿真器服务器"""

    def __init__(
        self,
        zmq_port: int = 5555,
        sim_dt: float = 0.01,  # 10ms 时间步长
        realtime: bool = True,  # 实时模式 vs 加速模式
        config_path: str = None  # 配置文件路径
    ):
        self.zmq_port = zmq_port
        self.sim_dt = sim_dt
        self.realtime = realtime

        # 加载配置文件
        self.config = self._load_config(config_path)

        # ZMQ 上下文
        self.context = zmq.Context()
        self.socket = None

        # 机器人状态
        self.state = RobotState()
        self.state_history = StateHistory(max_size=10000)

        # 物理引擎 - 从配置中读取参数
        kinematics_config = self.config.get('kinematics', {})
        slip_config = kinematics_config.get('slip', {})
        terrain_config = kinematics_config.get('terrain', {})

        self.kinematics = KinematicsEngine(
            dt=sim_dt,
            max_speed=kinematics_config.get('max_speed', 2.0),
            max_accel=kinematics_config.get('max_accel', 1.0),
            max_angular_vel=kinematics_config.get('max_angular_vel', 1.0),
            wheelbase=kinematics_config.get('wheelbase', 0.5),
            slip_ratio=slip_config.get('ratio', 0.05),
            enable_slip=slip_config.get('enabled', True),
            terrain_roughness=terrain_config.get('roughness', 0.02),  # rad/s
            enable_terrain_noise=terrain_config.get('enabled', True)
        )
        self.physics = SimplePhysics()

        # 传感器模拟器
        gps_ref = self.config.get('gps_ref', {})
        ref_lat = gps_ref.get('lat', 31.2)
        ref_lon = gps_ref.get('lon', 121.5)
        self.sensors = SensorSimulator(ref_lat=ref_lat, ref_lon=ref_lon)

        # 田地生成器和配置（田地中心在原点）
        field_config = self.config.get('field', {})
        field_width = field_config.get('width', 100.0)
        field_length = field_config.get('length', 200.0)
        # 计算base坐标使田地几何中心在(0, 0)
        base_x = -field_width / 2
        base_y = -field_length / 2
        self.field_generator = FieldGenerator(base_x=base_x, base_y=base_y)
        self.field = self._generate_default_field()
        self.field_version = 1
        self._init_robot_near_entry(max_distance_m=50.0)

        # 控制
        self.running = False
        self.sim_thread = None
        self.last_step_time = time.time()

        # 传感器频率限制
        sensor_config = self.config.get('sensors', {})
        rtk_config = sensor_config.get('rtk', {})
        self.rtk_frequency = rtk_config.get('frequency', 50.0)  # 默认50Hz
        self.rtk_period = 1.0 / self.rtk_frequency  # 秒
        self.last_rtk_time = 0.0

        # 统计
        self.step_count = 0
        self.request_count = 0

        # RTK 日志统计
        self.rtk_request_count = 0
        self.rtk_success_count = 0
        self.rtk_rate_limited_count = 0
        self.rtk_last_log_time = time.time()
        self.rtk_log_interval = 5.0  # 每5秒输出一次统计日志

        # 速度控制日志统计
        self.velocity_cmd_count = 0
        self.velocity_last_log_time = time.time()
        self.last_velocity_cmd = (0.0, 0.0)

        logger.info(f"RTK 配置: 频率={self.rtk_frequency}Hz, 周期={self.rtk_period*1000:.1f}ms")

    def _generate_default_field(self) -> Dict[str, Any]:
        """生成默认的田地配置"""
        field_config = self.config.get('field', {})
        field_type = field_config.get('type', 'rectangular')
        width = field_config.get('width', 100.0)
        length = field_config.get('length', 200.0)

        logger.info(f"Generating {field_type} field: {width}m x {length}m")

        if field_type == 'rectangular':
            field = self.field_generator.generate_rectangular_field(width, length)
        else:
            num_points = field_config.get('num_points', 6)
            field = self.field_generator.generate_irregular_field(width, length, num_points)
            num_obstacles = field_config.get('num_obstacles', 0)
            if num_obstacles > 0:
                field = self.field_generator.generate_simple_obstacles(field, num_obstacles)
        holes_cfg = field_config.get('holes', {})
        enabled = holes_cfg.get('enabled', False)
        num_holes = holes_cfg.get('num_holes', 0)
        size_ratio = holes_cfg.get('size_ratio', 0.05)
        if enabled and num_holes > 0 and size_ratio > 0.0:
            field = self.field_generator.generate_random_holes(field, num_holes, size_ratio)
        return field

    def _load_config(self, config_path: str = None) -> Dict[str, Any]:
        """加载配置文件"""
        if config_path is None:
            # 尝试在相同目录查找默认配置文件
            config_path = Path(__file__).parent / "config.yaml"
        else:
            config_path = Path(config_path)

        if config_path.exists():
            logger.info(f"Loading config from: {config_path}")
            with open(config_path, 'r', encoding='utf-8') as f:
                return yaml.safe_load(f) or {}
        else:
            logger.warning(f"Config file not found: {config_path}, using defaults")
            return {}

    def _init_robot_near_entry(self, max_distance_m: float = 50.0):
        """将机器人初始位置设置在入口点附近（不超过指定距离）"""
        try:
            entry_points = self.field.get("entry_points", [])
            if not entry_points:
                return
            ex, ey = entry_points[0]
            cx, cy = self.field.get("center", (ex, ey))
            import random, math
            r = random.uniform(0.0, max_distance_m)
            theta = random.uniform(0.0, 2 * math.pi)
            self.state.x = ex + r * math.cos(theta)
            self.state.y = ey + r * math.sin(theta)
            # 使航向朝向田地中心
            dx = cx - self.state.x
            dy = cy - self.state.y
            self.state.yaw = math.atan2(dy, dx)
        except Exception:
            # 安全降级：保持默认原点
            pass

    def start(self):
        """启动服务器"""
        logger.info(f"Starting simulator server on port {self.zmq_port}")

        # 绑定 ZMQ socket
        self.socket = self.context.socket(zmq.REP)
        self.socket.bind(f"tcp://*:{self.zmq_port}")
        logger.info(f"ZMQ socket bound to tcp://*:{self.zmq_port}")

        # 启动仿真线程
        self.running = True
        self.sim_thread = threading.Thread(target=self._simulation_loop, daemon=True)
        self.sim_thread.start()
        logger.info("Simulation thread started")

        # 主线程处理请求
        self._request_loop()

    def stop(self):
        """停止服务器"""
        logger.info("Stopping simulator server")
        self.running = False

        if self.sim_thread:
            self.sim_thread.join(timeout=2.0)

        if self.socket:
            self.socket.close()

        self.context.term()
        logger.info("Simulator server stopped")

    def _simulation_loop(self):
        """仿真循环（在独立线程运行）"""
        logger.info("Simulation loop started")

        while self.running:
            loop_start = time.time()

            # 更新物理状态
            self.state = self.kinematics.step(self.state)
            self.state = self.physics.apply_boundary(self.state)

            # 记录历史
            self.state_history.add(self.state)

            self.step_count += 1

            # 实时模式：等待到下一个时间步
            if self.realtime:
                elapsed = time.time() - loop_start
                sleep_time = self.sim_dt - elapsed
                if sleep_time > 0:
                    time.sleep(sleep_time)
                else:
                    # 警告：仿真运行速度慢于实时
                    if self.step_count % 100 == 0:
                        logger.warning(f"Simulation running slower than realtime: {elapsed:.4f}s > {self.sim_dt:.4f}s")

            self.last_step_time = time.time()

    def _request_loop(self):
        """请求处理循环"""
        logger.info("Request loop started")

        try:
            while self.running:
                # 接收请求（阻塞）
                try:
                    message = self.socket.recv_json(flags=zmq.NOBLOCK)
                    self.request_count += 1

                    # 处理请求
                    response = self._handle_request(message)

                    # 发送响应
                    self.socket.send_json(response)

                except zmq.Again:
                    # 没有消息，继续
                    time.sleep(0.001)
                    continue

        except KeyboardInterrupt:
            logger.info("Received interrupt signal")
        finally:
            self.stop()

    def _handle_request(self, request: Dict[str, Any]) -> Dict[str, Any]:
        """
        处理 API 请求

        请求格式：
        {
            "type": "get_sensor" | "set_actuator" | "get_state" | "get_field",
            "sensor": "gps" | "imu" | "odometry" | "rtk_gps",  # for get_sensor
            "actuator": "motor" | "velocity",                   # for set_actuator
            "data": {...}                                       # for set_actuator
        }
        """
        req_type = request.get("type")

        try:
            if req_type == "get_sensor":
                return self._get_sensor(request)
            elif req_type == "set_actuator":
                return self._set_actuator(request)
            elif req_type == "get_state":
                return self._get_state()
            elif req_type == "get_field":
                return self._get_field()
            elif req_type == "refresh_field":
                return self._refresh_field(request)
            elif req_type == "reset":
                return self._reset()
            elif req_type == "get_config":
                return self._get_config()
            else:
                return {
                    "status": "error",
                    "message": f"Unknown request type: {req_type}"
                }

        except Exception as e:
            logger.error(f"Error handling request: {e}", exc_info=True)
            return {
                "status": "error",
                "message": str(e)
            }

    def _get_sensor(self, request: Dict[str, Any]) -> Dict[str, Any]:
        """获取传感器数据"""
        sensor_type = request.get("sensor")

        if sensor_type == "gps":
            data = self.sensors.get_gps_data(self.state)
        elif sensor_type == "rtk_gps":
            # RTK GPS 频率限制
            current_time = time.time()
            self.rtk_request_count += 1

            if current_time - self.last_rtk_time >= self.rtk_period:
                data = self.sensors.get_rtk_gps_data(self.state)
                self.last_rtk_time = current_time
                self.rtk_success_count += 1

                # 定期输出RTK统计日志
                self._log_rtk_stats(current_time, data)
            else:
                # 返回缓冲的数据（等待下一个周期）
                self.rtk_rate_limited_count += 1
                return {
                    "status": "ok",
                    "sensor": sensor_type,
                    "data": None,
                    "sim_time": self.state.sim_time,
                    "note": f"Rate limited: next update in {self.rtk_period - (current_time - self.last_rtk_time):.3f}s"
                }
        elif sensor_type == "imu":
            data = self.sensors.get_imu_data(self.state)
        elif sensor_type == "odometry":
            data = self.sensors.get_odometry_data(self.state)
        else:
            return {
                "status": "error",
                "message": f"Unknown sensor type: {sensor_type}"
            }

        return {
            "status": "ok",
            "sensor": sensor_type,
            "data": data,
            "sim_time": self.state.sim_time
        }

    def _log_rtk_stats(self, current_time: float, data: Dict[str, Any]):
        """定期输出RTK统计日志"""
        if current_time - self.rtk_last_log_time >= self.rtk_log_interval:
            elapsed = current_time - self.rtk_last_log_time
            total = self.rtk_request_count
            success = self.rtk_success_count
            limited = self.rtk_rate_limited_count

            if total > 0:
                success_rate = (success / total) * 100
                # 输出统计
                logger.info(
                    f"[RTK统计] 请求={total}, 成功={success} ({success_rate:.1f}%), "
                    f"限流={limited}, 实际频率={success/elapsed:.1f}Hz"
                )

                # 输出当前RTK数据摘要
                lat = data.get('latitude', 0)
                lon = data.get('longitude', 0)
                heading = data.get('heading', 0)
                rtk_status = data.get('rtk_status', 'UNKNOWN')
                logger.info(
                    f"[RTK数据] lat={lat:.8f}, lon={lon:.8f}, "
                    f"heading={heading:.2f}°, status={rtk_status}"
                )

                # 输出车辆位置（世界坐标）
                logger.info(
                    f"[车辆位置] x={self.state.x:.2f}m, y={self.state.y:.2f}m, "
                    f"yaw={self.state.yaw:.4f}rad ({self.state.yaw*180/3.14159:.1f}°)"
                )

            # 重置统计
            self.rtk_request_count = 0
            self.rtk_success_count = 0
            self.rtk_rate_limited_count = 0
            self.rtk_last_log_time = current_time

    def _log_velocity_stats(self, current_time: float):
        """定期输出速度控制统计日志"""
        if current_time - self.velocity_last_log_time >= self.rtk_log_interval:
            elapsed = current_time - self.velocity_last_log_time
            count = self.velocity_cmd_count
            v, w = self.last_velocity_cmd

            if count > 0:
                freq = count / elapsed
                logger.info(
                    f"[速度控制] 接收命令={count}, 频率={freq:.1f}Hz, "
                    f"当前: v={v:.3f}m/s, w={w:.3f}rad/s"
                )

            # 重置统计
            self.velocity_cmd_count = 0
            self.velocity_last_log_time = current_time

    def _set_actuator(self, request: Dict[str, Any]) -> Dict[str, Any]:
        """设置执行器"""
        actuator_type = request.get("actuator")
        data = request.get("data", {})

        if actuator_type == "motor":
            # 电机控制：throttle 和 steering
            throttle = data.get("throttle", 0.0)
            steering = data.get("steering", 0.0)

            self.kinematics.set_control(throttle, steering)

            return {
                "status": "ok",
                "actuator": actuator_type,
                "applied_at": self.state.sim_time
            }
        elif actuator_type == "velocity":
            # 速度控制模式（农田作业模式）
            # 输入：linear_velocity (m/s) 和 angular_velocity (rad/s)
            linear_vel = data.get("linear_velocity", 0.0)
            angular_vel = data.get("angular_velocity", 0.0)

            self.kinematics.set_velocity_control(linear_vel, angular_vel)
            self.velocity_cmd_count += 1
            self.last_velocity_cmd = (linear_vel, angular_vel)

            # 定期输出速度控制日志
            self._log_velocity_stats(time.time())

            return {
                "status": "ok",
                "actuator": actuator_type,
                "applied_at": self.state.sim_time,
                "linear_velocity": linear_vel,
                "angular_velocity": angular_vel
            }
        else:
            return {
                "status": "error",
                "message": f"Unknown actuator type: {actuator_type}"
            }

    def _get_state(self) -> Dict[str, Any]:
        """获取完整状态"""
        return {
            "status": "ok",
            "state": self.state.to_dict(),
            "stats": {
                "step_count": self.step_count,
                "request_count": self.request_count,
                "sim_time": self.state.sim_time
            }
        }

    def _get_field(self) -> Dict[str, Any]:
        """获取田地信息"""
        return {
            "status": "ok",
            "field": self.field,
            "version": self.field_version,
            "sim_time": self.state.sim_time
        }

    def _reset(self) -> Dict[str, Any]:
        """重置仿真"""
        logger.info("Resetting simulation")

        self.state = RobotState()
        self.state_history.clear()
        self.kinematics.reset_control()
        self.step_count = 0

        return {
            "status": "ok",
            "message": "Simulation reset"
        }

    def _get_config(self) -> Dict[str, Any]:
        """获取仿真器配置（GPS参考点等）"""
        gps_ref = self.config.get('gps_ref', {})
        return {
            "status": "ok",
            "config": {
                "gps_ref": {
                    "lon": gps_ref.get('lon', 121.5),
                    "lat": gps_ref.get('lat', 31.2)
                }
            }
        }

    def _refresh_field(self, request: Dict[str, Any]) -> Dict[str, Any]:
        """刷新田地并重置初始位置"""
        logger.info("Refreshing field")
        try:
            self.field = self._generate_default_field()
            self.field_version += 1
            self._init_robot_near_entry(max_distance_m=50.0)
            return {
                "status": "ok",
                "field": self.field,
                "version": self.field_version,
                "message": "Field refreshed"
            }
        except Exception as e:
            return {
                "status": "error",
                "message": str(e)
            }


def main():
    """启动仿真器服务器"""
    import argparse

    parser = argparse.ArgumentParser(description="NodeFlow Robot Simulator")
    parser.add_argument("--port", type=int, default=5555, help="ZMQ port")
    parser.add_argument("--dt", type=float, default=0.01, help="Simulation time step (seconds)")
    parser.add_argument("--no-realtime", action="store_true", help="Disable realtime mode")
    parser.add_argument("--config", type=str, default=None, help="Path to config file (YAML)")

    args = parser.parse_args()

    server = SimulatorServer(
        zmq_port=args.port,
        sim_dt=args.dt,
        realtime=not args.no_realtime,
        config_path=args.config
    )

    try:
        server.start()
    except KeyboardInterrupt:
        logger.info("Shutting down")
        server.stop()


if __name__ == "__main__":
    main()
