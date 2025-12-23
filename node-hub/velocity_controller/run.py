#!/usr/bin/env python3
"""
速度控制器 - 纯追踪算法

专为农田作业设计，输出线速度和角速度 (v, ω)

特点：
- 纯追踪控制算法（Pure Pursuit）
- 输出格式：{linear_velocity, angular_velocity}
- 支持RTK GPS输入（厘米级精度）
- 可处理路径跟踪或单点导航

控制流程：
  1. 接收当前位置 (RTK GPS)
  2. 找到前瞻点 (从路径或目标点)
  3. 计算期望航向
  4. 计算角速度 (ω = K_p * heading_error)
  5. 计算线速度 (v = max_speed * cos(heading_error))
  6. 输出控制命令

打滑补偿：
  虽然控制器输出理想速度，但仿真器会应用打滑噪声
  因此实际速度会略小于期望速度，这是正常的
"""

import sys
import time
import math
import logging
from pathlib import Path

# 添加项目根路径
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from sdk.nodeflow_sdk import NodeFlowSDK

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(name)s] %(levelname)s: %(message)s'
)
logger = logging.getLogger("velocity_controller")


def haversine_distance(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """
    计算两个GPS坐标之间的距离 (米)

    Args:
        lat1, lon1: 第一个点的纬度/经度 (度)
        lat2, lon2: 第二个点的纬度/经度 (度)

    Returns:
        距离 (米)
    """
    lat1, lon1, lat2, lon2 = map(math.radians, [lat1, lon1, lat2, lon2])
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    a = math.sin(dlat/2)**2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon/2)**2
    c = 2 * math.asin(math.sqrt(a))
    return 6371000 * c  # 地球半径 6371 km


def calculate_bearing(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """
    计算从点1到点2的航向角 (弧度)

    Args:
        lat1, lon1: 起点纬度/经度 (度)
        lat2, lon2: 终点纬度/经度 (度)

    Returns:
        航向角 (弧度, 北向为0，顺时针为正)
    """
    lat1, lon1, lat2, lon2 = map(math.radians, [lat1, lon1, lat2, lon2])
    dlon = lon2 - lon1
    y = math.sin(dlon) * math.cos(lat2)
    x = math.cos(lat1) * math.sin(lat2) - math.sin(lat1) * math.cos(lat2) * math.cos(dlon)
    return math.atan2(y, x)


def normalize_angle(angle: float) -> float:
    """将角度归一化到 [-π, π]"""
    while angle > math.pi:
        angle -= 2 * math.pi
    while angle < -math.pi:
        angle += 2 * math.pi
    return angle


def clamp(value: float, min_val: float, max_val: float) -> float:
    """限制值在范围内"""
    return max(min_val, min(max_val, value))


class PurePursuitController:
    """
    纯追踪控制器

    输出：{linear_velocity, angular_velocity}
    """

    def __init__(self, max_speed: float = 1.0, min_speed: float = 0.2,
                 lookahead: float = 2.0, heading_gain: float = 2.0,
                 max_angular_vel: float = 1.0, goal_tolerance: float = 0.3):
        self.max_speed = max_speed
        self.min_speed = min_speed
        self.lookahead_distance = lookahead
        self.heading_p_gain = heading_gain
        self.max_angular_velocity = max_angular_vel
        self.goal_tolerance = goal_tolerance

        self.path = []  # [(lat, lon), ...]
        self.current_path_index = 0
        self.current_task_id = None  # ===== 修复: 路径版本号 =====
        self.target_point = None  # (lat, lon)

    def set_path(self, path: list, task_id: str = None):
        """设置路径 (with version tracking to avoid reset on duplicate)

        Args:
            path: 路径点列表
            task_id: 任务ID，用于检测是否是新路径
        """
        # ===== 修复: 避免重复接收相同路径导致索引重置 =====
        if task_id and task_id == self.current_task_id:
            logger.debug(f"接收到相同路径 (task_id={task_id})，跳过重置")
            return  # 跳过重复设置
        # ===== 修复结束 =====

        self.path = path
        self.current_path_index = 0
        self.current_task_id = task_id
        logger.info(f"路径已更新: {len(path)}个点 (task_id={task_id})")

    def set_target(self, target: tuple):
        """设置目标点"""
        self.target_point = target
        logger.info(f"目标点已更新: {target}")

    def find_lookahead_point(self, current_lat: float, current_lon: float):
        """
        查找前瞻点 (带路径点通过检测)

        优先级：
        1. 如果有路径，从路径中找前瞻点
        2. 否则使用单个目标点
        3. 否则返回None

        Returns:
            (lat, lon, distance) 或 (None, None, None)

        注意：global_coverage 输出格式是 [(lon, lat), ...]（WGS84标准）
        """
        if self.path:
            # ===== 修复: 检测并跳过已通过的路径点 =====
            # 从当前索引开始,检查是否到达了该点
            while self.current_path_index < len(self.path):
                lon, lat = self.path[self.current_path_index]
                d = haversine_distance(current_lat, current_lon, lat, lon)

                # 如果到达了当前点(距离<tolerance),则跳到下一个点
                if d < self.goal_tolerance:
                    logger.debug(f"已通过路径点 #{self.current_path_index + 1}/{len(self.path)}")
                    self.current_path_index += 1
                else:
                    # 找到第一个未通过的点
                    break

            # 如果所有点都已通过
            if self.current_path_index >= len(self.path):
                logger.info(f"已完成整条路径! (共 {len(self.path)} 个点)")
                return None, None, None

            # 从当前索引开始找前瞻点 (距离>前瞻距离)
            for i in range(self.current_path_index, len(self.path)):
                lon, lat = self.path[i]
                d = haversine_distance(current_lat, current_lon, lat, lon)
                if d >= self.lookahead_distance:
                    logger.debug(f"前瞻点: #{i + 1}/{len(self.path)}, 距离={d:.2f}m")
                    return lat, lon, d

            # 如果没找到前瞻点(所有后续点都<lookahead_distance),返回终点
            if self.path:
                lon, lat = self.path[-1]
                d = haversine_distance(current_lat, current_lon, lat, lon)
                logger.debug(f"返回终点, 距离={d:.2f}m")
                return lat, lon, d
            # ===== 修复结束 =====

        elif self.target_point:
            # 使用单个目标点
            lat, lon = self.target_point
            d = haversine_distance(current_lat, current_lon, lat, lon)
            return lat, lon, d

        return None, None, None

    def compute_control(self, rtk_data: dict) -> dict:
        """
        计算控制命令

        Args:
            rtk_data: RTK GPS数据
                {
                    "latitude": float,
                    "longitude": float,
                    "rtk_status": str,
                    ...
                }

        Returns:
            控制命令
                {
                    "linear_velocity": float,
                    "angular_velocity": float,
                    "timestamp": float
                }
        """
        if not rtk_data:
            logger.warning("无RTK数据，输出零速度")
            return {
                "linear_velocity": 0.0,
                "angular_velocity": 0.0,
                "timestamp": time.time()
            }

        # 当前位置
        current_lat = rtk_data.get("latitude", 0.0)
        current_lon = rtk_data.get("longitude", 0.0)

        # 查找前瞻点
        target_lat, target_lon, distance = self.find_lookahead_point(
            current_lat, current_lon
        )

        if target_lat is None:
            logger.warning("无目标点，输出零速度")
            return {
                "linear_velocity": 0.0,
                "angular_velocity": 0.0,
                "timestamp": time.time()
            }

        # 检查是否到达目标
        if distance < self.goal_tolerance:
            logger.info(f"已到达目标 (距离: {distance:.2f}m)")
            return {
                "linear_velocity": 0.0,
                "angular_velocity": 0.0,
                "timestamp": time.time()
            }

        # 计算目标航向
        target_bearing = calculate_bearing(
            current_lat, current_lon,
            target_lat, target_lon
        )

        # 获取当前航向 (从RTK双天线数据)
        # RTK数据应该包含heading信息 (度，北向为0，顺时针为正)
        current_heading_deg = rtk_data.get("heading", 0.0)
        current_heading = math.radians(current_heading_deg)

        # 计算航向误差
        heading_error = normalize_angle(target_bearing - current_heading)

        # 计算角速度 (P控制)
        angular_velocity = self.heading_p_gain * heading_error

        # 限制角速度
        angular_velocity = clamp(
            angular_velocity,
            -self.max_angular_velocity,
            self.max_angular_velocity
        )

        # 计算线速度 (根据航向误差调整)
        # 航向误差小：全速
        # 航向误差大：减速
        speed_factor = abs(math.cos(heading_error))
        linear_velocity = self.max_speed * speed_factor

        # 确保最小速度
        if linear_velocity < self.min_speed:
            linear_velocity = self.min_speed

        return {
            "linear_velocity": linear_velocity,
            "angular_velocity": angular_velocity,
            "distance_to_goal": distance,
            "heading_error_deg": math.degrees(heading_error),
            "timestamp": time.time()
        }


def main():
    """主函数"""
    with NodeFlowSDK(log_level="DEBUG") as sdk:
        logger.info("=== velocity_controller 节点启动 ===")

        # 读取参数
        max_speed = sdk.get_param("max_speed", 1.0)
        min_speed = sdk.get_param("min_speed", 0.2)
        lookahead = sdk.get_param("lookahead_distance", 2.0)
        heading_gain = sdk.get_param("heading_p_gain", 2.0)
        max_angular_vel = sdk.get_param("max_angular_velocity", 1.0)
        goal_tolerance = sdk.get_param("goal_tolerance", 0.3)
        control_freq = sdk.get_param("control_frequency", 20)
        enable_control = sdk.get_param("enable_control", True)

        logger.info(f"控制参数:")
        logger.info(f"  最大速度: {max_speed:.2f} m/s")
        logger.info(f"  最小速度: {min_speed:.2f} m/s")
        logger.info(f"  前瞻距离: {lookahead:.2f} m")
        logger.info(f"  航向增益: {heading_gain:.2f}")
        logger.info(f"  控制频率: {control_freq} Hz")

        # 创建控制器
        controller = PurePursuitController(
            max_speed=max_speed,
            min_speed=min_speed,
            lookahead=lookahead,
            heading_gain=heading_gain,
            max_angular_vel=max_angular_vel,
            goal_tolerance=goal_tolerance
        )

        # 创建输入输出端口
        rtk_port = sdk.create_input_port('rtk_fix')
        global_path_port = sdk.create_input_port('global_path')
        velocity_cmd_port = sdk.create_output_port('velocity_cmd')

        logger.info("输入/输出端口已创建")

        # 控制循环间隔
        loop_interval = 1.0 / control_freq

        # 统计
        loop_count = 0
        success_count = 0
        no_rtk_count = 0
        no_target_count = 0
        last_log_time = time.time()

        logger.info("开始控制循环...")
        logger.info("等待RTK数据和目标点/路径...")

        try:
            while True:
                loop_start = time.time()

                if not enable_control:
                    # 如果禁用控制，输出零速度
                    velocity_cmd_port.send({
                        "linear_velocity": 0.0,
                        "angular_velocity": 0.0,
                        "timestamp": time.time()
                    })
                    time.sleep(loop_interval)
                    continue

                # 读取RTK数据
                rtk_data = rtk_port.recv_latest()

                # 读取路径
                global_path = global_path_port.recv_latest()

                # ===== 数据验证日志 =====
                if loop_count == 0 and global_path:
                    logger.debug(f"[DATA_CHECK] global_path type: {type(global_path)}")
                    logger.debug(f"[DATA_CHECK] global_path keys: {global_path.keys() if isinstance(global_path, dict) else 'N/A'}")
                    if isinstance(global_path, dict) and 'path' in global_path:
                        path = global_path['path']
                        logger.debug(f"[DATA_CHECK] path length: {len(path) if isinstance(path, list) else 'N/A'}")
                        if isinstance(path, list) and len(path) > 0:
                            logger.debug(f"[DATA_CHECK] path[0] type: {type(path[0])}")
                # ===== 数据验证日志结束 =====

                # ===== 修复: 更新控制器 (传递task_id避免重复重置) =====
                if global_path and 'path' in global_path:
                    task_id = global_path.get('task_id', None)
                    controller.set_path(global_path['path'], task_id)
                # ===== 修复结束 =====

                # 计算控制命令
                velocity_cmd = controller.compute_control(rtk_data)

                # 发送控制命令
                velocity_cmd_port.send(velocity_cmd)
                success_count += 1
                loop_count += 1

                # 定期打印状态
                if time.time() - last_log_time >= 1.0:
                    logger.info(
                        f"控制: v={velocity_cmd['linear_velocity']:.3f} m/s, "
                        f"ω={velocity_cmd['angular_velocity']:.3f} rad/s | "
                        f"成功: {success_count}"
                    )
                    last_log_time = time.time()

                # 控制频率
                elapsed = time.time() - loop_start
                if elapsed < loop_interval:
                    time.sleep(loop_interval - elapsed)

        except KeyboardInterrupt:
            logger.info("收到中断信号，正在退出...")

        finally:
            # 发送停止命令
            sdk.send("velocity_cmd", {
                "linear_velocity": 0.0,
                "angular_velocity": 0.0,
                "timestamp": time.time()
            })
            logger.info(f"=== velocity_controller 节点退出 === (总计: {success_count})")


if __name__ == "__main__":
    main()
