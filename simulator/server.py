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
        self.sensors = SensorSimulator()

        # 田地生成器和配置
        self.field_generator = FieldGenerator()
        self.field = self._generate_default_field()

        # 控制
        self.running = False
        self.sim_thread = None
        self.last_step_time = time.time()

        # 传感器频率限制
        sensor_config = self.config.get('sensors', {})
        rtk_config = sensor_config.get('rtk', {})
        self.rtk_frequency = rtk_config.get('frequency', 20.0)  # 默认20Hz
        self.rtk_period = 1.0 / self.rtk_frequency  # 秒
        self.last_rtk_time = 0.0

        # 统计
        self.step_count = 0
        self.request_count = 0

    def _generate_default_field(self) -> Dict[str, Any]:
        """生成默认的田地配置"""
        field_config = self.config.get('field', {})
        field_type = field_config.get('type', 'rectangular')
        width = field_config.get('width', 100.0)
        length = field_config.get('length', 200.0)

        logger.info(f"Generating {field_type} field: {width}m x {length}m")

        if field_type == 'rectangular':
            return self.field_generator.generate_rectangular_field(width, length)
        else:
            num_points = field_config.get('num_points', 6)
            field = self.field_generator.generate_irregular_field(width, length, num_points)
            num_obstacles = field_config.get('num_obstacles', 0)
            if num_obstacles > 0:
                field = self.field_generator.generate_simple_obstacles(field, num_obstacles)
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
            elif req_type == "reset":
                return self._reset()
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
            if current_time - self.last_rtk_time >= self.rtk_period:
                data = self.sensors.get_rtk_gps_data(self.state)
                self.last_rtk_time = current_time
            else:
                # 返回缓冲的数据（等待下一个周期）
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
