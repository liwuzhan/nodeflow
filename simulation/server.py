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
import random
import copy
import math
from functools import wraps
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


def _synchronized(method):
    @wraps(method)
    def locked(self, *args, **kwargs):
        with self._lock:
            return method(self, *args, **kwargs)
    return locked


class SimulatorServer:
    """仿真器服务器"""

    def __init__(
        self,
        zmq_port: int = None,
        sim_dt: float = None,
        realtime: bool = None,
        config_path: str = None,
        *,
        config: Dict[str, Any] = None,
        initial_sim_time: float = None,
        seed: int = None,
        command_timeout_s: float = None,
    ):
        """构造无需端口；start() 才建立服务，step_once() 可离线步进。

        显式参数仅在非 None 时覆盖配置。默认时间戳仍是 Unix 时间；
        离线试验可用 initial_sim_time=0 建立可重放的仿真时间轴。
        """
        self._lock = threading.RLock()
        self.config = copy.deepcopy(config) if config is not None else self._load_config(config_path)
        server_config = self.config.get('server', {})
        kinematics_config = self.config.get('kinematics', {})
        self.zmq_port = int(server_config.get('zmq_port', 5555) if zmq_port is None else zmq_port)
        self.sim_dt = float(kinematics_config.get('dt', 0.01) if sim_dt is None else sim_dt)
        self.realtime = bool(server_config.get('realtime', True) if realtime is None else realtime)
        self.command_timeout_s = float(server_config.get('command_timeout_s', 0.5)
                                       if command_timeout_s is None else command_timeout_s)
        if not math.isfinite(self.command_timeout_s) or self.command_timeout_s < 0:
            raise ValueError("command_timeout_s must be finite and nonnegative")
        self.seed = server_config.get('random_seed') if seed is None else seed
        self._rng = random.Random(self.seed)
        self._pose_rng_state = self._rng.getstate()
        self.initial_sim_time = initial_sim_time
        self.context = None
        self.socket = None
        self.state = RobotState(sim_time=time.time() if initial_sim_time is None else initial_sim_time)
        self.state_history = StateHistory(max_size=10000)
        slip_config = kinematics_config.get('slip', {})
        terrain_config = kinematics_config.get('terrain', {})
        self.kinematics = KinematicsEngine(
            dt=self.sim_dt,
            max_speed=kinematics_config.get('max_speed', 2.0),
            max_accel=kinematics_config.get('max_accel', 1.0),
            max_angular_vel=kinematics_config.get('max_angular_vel', 1.0),
            wheelbase=kinematics_config.get('wheelbase', 0.5),
            slip_ratio=slip_config.get('ratio', 0.05),
            enable_slip=slip_config.get('enabled', True),
            terrain_roughness=terrain_config.get('roughness', 0.02),
            enable_terrain_noise=terrain_config.get('enabled', True),
            seed=self.seed,
            max_angular_accel=kinematics_config.get('max_angular_accel', 2.0),
            velocity_response_time_s=kinematics_config.get('velocity_response_time_s', 0.0),
            angular_response_time_s=kinematics_config.get('angular_response_time_s', 0.0),
        )
        physics_config = self.config.get('physics', {})
        bounds = physics_config.get('bounds', {})
        self.physics = SimplePhysics(
            friction_coeff=physics_config.get('friction_coeff', 0.1),
            bounds_x=tuple(bounds.get('x', (-100.0, 100.0))),
            bounds_y=tuple(bounds.get('y', (-100.0, 100.0))),
        )
        sensor_config = self.config.get('sensors', {})
        gps_ref = self.config.get('gps_ref', {})
        self.sensors = SensorSimulator(
            ref_lat=gps_ref.get('lat', 31.2), ref_lon=gps_ref.get('lon', 121.5),
            gps_noise_std=sensor_config.get('gps_noise_std', 0.5),
            imu_accel_noise=sensor_config.get('imu_accel_noise', 0.1),
            imu_gyro_noise=sensor_config.get('imu_gyro_noise', 0.01),
            seed=self.seed, rtk_config=sensor_config.get('rtk', {}),
            frequencies=sensor_config.get('frequencies', {}),
        )
        field_config = self.config.get('field', {})
        self.field_generator = FieldGenerator(
            base_x=-field_config.get('width', 100.0) / 2,
            base_y=-field_config.get('length', 200.0) / 2,
            seed=self.seed,
        )
        self.field = self._generate_default_field()
        self.field_version = 1
        self._init_robot_from_config()
        self.sensors.update(self.state)
        self.state_history.add(self.state)
        self.running = False
        self.sim_thread = None
        self.last_step_time = time.monotonic()
        self._last_motion_command_at = None
        self._last_implement_command_at = None
        self.step_count = 0
        self.request_count = 0
        self.velocity_cmd_count = 0
        self.velocity_last_log_time = time.monotonic()
        self.last_velocity_cmd = (0.0, 0.0)
        self.rtk_log_interval = 5.0

    def _generate_default_field(self) -> Dict[str, Any]:
        """生成默认的田地配置"""
        field_config = self.config.get('field', {})
        field_type = field_config.get('type', 'rectangular')
        width = field_config.get('width', 100.0)
        length = field_config.get('length', 200.0)

        if field_config.get('boundary'):
            return self.field_generator.generate_fixed_field(
                field_config['boundary'], field_config.get('fixed_holes', []),
                field_config.get('entry_points'))
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

    def _init_robot_from_config(self):
        server_config = self.config.get('server', {})
        mode = server_config.get('initial_pose_mode', 'entry')
        max_distance = float(server_config.get('initial_max_distance_m', 1.0))
        pose = server_config.get('initial_pose')
        if pose is not None:
            self.state.x = float(pose.get('x', 0.0))
            self.state.y = float(pose.get('y', 0.0))
            self.state.yaw = float(pose.get('yaw', 0.0))
        elif mode == 'origin':
            self.state.x = self.state.y = self.state.yaw = 0.0
        elif mode == 'entry':
            self._init_robot_near_entry(max_distance_m=max_distance)
        else:
            raise ValueError("initial_pose_mode must be entry or origin")

    def _init_robot_near_entry(self, max_distance_m: float = 1.0):
        """将机器人初始位置设置在入口点附近（不超过指定距离）"""
        try:
            entry_points = self.field.get("entry_points", [])
            if not entry_points:
                return
            ex, ey = entry_points[0]
            cx, cy = self.field.get("center", (ex, ey))
            import math
            r = self._rng.uniform(0.0, max_distance_m)
            theta = self._rng.uniform(0.0, 2 * math.pi)
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
        self.context = zmq.Context()
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
            self.socket.close(linger=0)
            self.socket = None

        if self.context is not None:
            self.context.term()
            self.context = None
        logger.info("Simulator server stopped")

    @_synchronized
    def step_once(self, *, command_elapsed_s: float = None) -> RobotState:
        """完成一帧，返回真值副本。

        实时服务以 monotonic 检查各类命令。离线实验可显式传入自上条
        命令累计经过的秒数，消除电脑计算快慢对看门狗的影响；0 表示新命令。
        """
        if command_elapsed_s is not None:
            command_elapsed_s = float(command_elapsed_s)
            if not math.isfinite(command_elapsed_s) or command_elapsed_s < 0:
                raise ValueError("command_elapsed_s must be finite and nonnegative")
        now = time.monotonic()
        if self.command_timeout_s > 0:
            def stale(last):
                if last is None:
                    return False
                elapsed = now - last if command_elapsed_s is None else command_elapsed_s
                return elapsed >= self.command_timeout_s
            if stale(self._last_motion_command_at):
                self.kinematics.set_velocity_control(0.0, 0.0)
                self.last_velocity_cmd = (0.0, 0.0)
            if stale(self._last_implement_command_at):
                self.kinematics.set_implement_control(0.0, False, 540.0)
        self.state = self.kinematics.step(self.state)
        self.state = self.physics.apply_boundary(self.state)
        self.state_history.add(self.state)
        self.sensors.update(self.state)
        self.step_count += 1
        self.last_step_time = now
        return self.state.copy()

    def _simulation_loop(self):
        """实时模式与离线试验共享同一帧推进。"""
        logger.info("Simulation loop started")
        while self.running:
            loop_start = time.monotonic()
            self.step_once()
            if self.realtime:
                sleep_time = self.sim_dt - (time.monotonic() - loop_start)
                if sleep_time > 0:
                    time.sleep(sleep_time)

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
            "actuator": "motor" | "velocity" | "implement",              # for set_actuator
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

    @_synchronized
    def _get_sensor(self, request: Dict[str, Any]) -> Dict[str, Any]:
        """GET 只读最后已交付的样本，不改变采样相位或噪声。"""
        sensor_type = request.get("sensor")
        getters = {"gps": self.sensors.get_gps_data, "rtk_gps": self.sensors.get_rtk_gps_data,
                   "imu": self.sensors.get_imu_data, "odometry": self.sensors.get_odometry_data}
        if sensor_type not in getters:
            return {"status": "error", "message": f"Unknown sensor type: {sensor_type}"}
        return {"status": "ok", "sensor": sensor_type, "data": getters[sensor_type](),
                "sim_time": self.state.sim_time}

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

    @_synchronized
    def _set_actuator(self, request: Dict[str, Any]) -> Dict[str, Any]:
        """设置执行器"""
        actuator_type = request.get("actuator")
        data = request.get("data", {})

        if actuator_type == "motor":
            # 电机控制：throttle 和 steering
            throttle = data.get("throttle", 0.0)
            steering = data.get("steering", 0.0)

            self.kinematics.set_control(throttle, steering)
            self._last_motion_command_at = time.monotonic()

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
            self._last_motion_command_at = time.monotonic()
            self.velocity_cmd_count += 1
            self.last_velocity_cmd = (linear_vel, angular_vel)

            # 定期输出速度控制日志
            self._log_velocity_stats(time.monotonic())

            return {
                "status": "ok",
                "actuator": actuator_type,
                "applied_at": self.state.sim_time,
                "linear_velocity": linear_vel,
                "angular_velocity": angular_vel
            }
        elif actuator_type == "implement":
            # 机具控制：悬挂高度 + PTO
            hitch_height = data.get("hitch_height", 0.0)
            pto_on = data.get("pto_on", False)
            pto_rpm = data.get("pto_rpm", 540.0)

            self.kinematics.set_implement_control(hitch_height, pto_on, pto_rpm)
            self._last_implement_command_at = time.monotonic()

            return {
                "status": "ok",
                "actuator": actuator_type,
                "applied_at": self.state.sim_time,
                "hitch_height": hitch_height,
                "pto_on": pto_on,
                "pto_rpm": pto_rpm,
            }
        else:
            return {
                "status": "error",
                "message": f"Unknown actuator type: {actuator_type}"
            }

    @_synchronized
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

    @_synchronized
    def _get_field(self) -> Dict[str, Any]:
        """获取田地信息"""
        return {
            "status": "ok",
            "field": copy.deepcopy(self.field),
            "version": self.field_version,
            "sim_time": self.state.sim_time
        }

    @_synchronized
    def _reset(self) -> Dict[str, Any]:
        """同一地块重新开始；清掉旧命令、机具、传感器队列和历史。"""
        self.state = RobotState(sim_time=time.time() if self.initial_sim_time is None else self.initial_sim_time)
        self._rng.setstate(self._pose_rng_state)
        self._init_robot_from_config()
        self.state_history.clear()
        self.state_history.add(self.state)
        self.kinematics.reset_control()
        self.sensors.reset()
        self.sensors.update(self.state)
        self.step_count = self.request_count = self.velocity_cmd_count = 0
        self._last_motion_command_at = self._last_implement_command_at = None
        self.last_velocity_cmd = (0.0, 0.0)
        self.last_step_time = self.velocity_last_log_time = time.monotonic()
        return {"status": "ok", "message": "Simulation reset"}

    @_synchronized
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

    @_synchronized
    def _refresh_field(self, request: Dict[str, Any]) -> Dict[str, Any]:
        """刷新田地并重置初始位置"""
        logger.info("Refreshing field")
        try:
            self.field = self._generate_default_field()
            self.field_version += 1
            self._reset()
            return {
                "status": "ok",
                "field": copy.deepcopy(self.field),
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
    parser.add_argument("--port", type=int, default=None, help="ZMQ port")
    parser.add_argument("--dt", type=float, default=None, help="Simulation time step (seconds)")
    parser.add_argument("--no-realtime", action="store_true", help="Disable realtime mode")
    parser.add_argument("--config", type=str, default=None, help="Path to config file (YAML)")

    args = parser.parse_args()

    server = SimulatorServer(
        zmq_port=args.port,
        sim_dt=args.dt,
        realtime=False if args.no_realtime else None,
        config_path=args.config
    )

    try:
        server.start()
    except KeyboardInterrupt:
        logger.info("Shutting down")
        server.stop()


if __name__ == "__main__":
    main()
