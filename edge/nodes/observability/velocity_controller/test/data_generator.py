"""
测试数据生成器 - velocity_controller节点

生成符合节点输入格式的模拟数据，用于独立测试
"""

from typing import Dict, Any, List
import random
import time


class TestDataGenerator:
    """生成velocity_controller测试数据"""

    # 测试坐标（上海中心）
    DEFAULT_LAT = 31.2304
    DEFAULT_LON = 121.4737

    @staticmethod
    def generate_rtk_data(
        lat: float = DEFAULT_LAT,
        lon: float = DEFAULT_LON,
        altitude: float = 10.0,
        rtk_status: str = "FIXED"
    ) -> Dict[str, Any]:
        """
        生成RTK GPS数据

        参数:
            lat: 纬度 (度)
            lon: 经度 (度)
            altitude: 海拔高度 (米)
            rtk_status: RTK状态 ("FIXED", "FLOAT", "SINGLE")

        返回:
            符合节点rtk_fix输入端口格式的字典
        """
        return {
            "latitude": lat,
            "longitude": lon,
            "altitude": altitude,
            "rtk_status": rtk_status,
            "timestamp": time.time(),
            "horizontal_accuracy": 0.02 if rtk_status == "FIXED" else 0.5,
            "vertical_accuracy": 0.03 if rtk_status == "FIXED" else 1.0,
        }

    @staticmethod
    def generate_path_data(
        start_lat: float = DEFAULT_LAT,
        start_lon: float = DEFAULT_LON,
        num_waypoints: int = 10,
        spacing: float = 0.00001  # 约1.1米
    ) -> Dict[str, Any]:
        """
        生成路径数据（沿东方向的直线）

        参数:
            start_lat: 起点纬度
            start_lon: 起点经度
            num_waypoints: 路径点数量
            spacing: 路径点间距 (度)

        返回:
            符合节点global_path输入端口格式的字典
            格式：[(lon, lat), ...]  (WGS84标准)
        """
        waypoints = [
            (start_lon + i * spacing, start_lat)
            for i in range(num_waypoints)
        ]

        return {
            "task_id": f"test_path_{int(time.time())}",
            "waypoints": waypoints,
            "path_type": "coverage",
            "total_length": num_waypoints * spacing * 111000,  # 近似米
        }

    @staticmethod
    def generate_circular_path(
        center_lat: float = DEFAULT_LAT,
        center_lon: float = DEFAULT_LON,
        radius_deg: float = 0.0001,  # 约11米
        num_waypoints: int = 12
    ) -> Dict[str, Any]:
        """
        生成圆形路径

        参数:
            center_lat: 圆心纬度
            center_lon: 圆心经度
            radius_deg: 半径 (度)
            num_waypoints: 路径点数量

        返回:
            圆形路径数据
        """
        import math

        waypoints = []
        for i in range(num_waypoints):
            angle = 2 * math.pi * i / num_waypoints
            lat = center_lat + radius_deg * math.sin(angle)
            lon = center_lon + radius_deg * math.cos(angle)
            waypoints.append((lon, lat))

        # 闭合圆形
        waypoints.append(waypoints[0])

        return {
            "task_id": f"circular_path_{int(time.time())}",
            "waypoints": waypoints,
            "path_type": "circular",
        }

    @staticmethod
    def generate_velocity_cmd(
        linear: float = 0.5,
        angular: float = 0.0
    ) -> Dict[str, Any]:
        """
        生成速度控制命令（预期输出）

        参数:
            linear: 线速度 (m/s)
            angular: 角速度 (rad/s)

        返回:
            符合节点velocity_cmd输出端口格式的字典
        """
        return {
            "linear_velocity": linear,
            "angular_velocity": angular,
            "timestamp": time.time()
        }


def create_test_scenario(scenario: str = "basic") -> Dict[str, Any]:
    """
    创建完整的测试场景

    参数:
        scenario: 场景类型
            - "basic": 基础直线跟踪
            - "turning": 转弯场景
            - "reached_goal": 到达目标点
            - "no_path": 无路径数据
            - "circular": 圆形路径

    返回:
        包含所有测试数据的字典
    """
    gen = TestDataGenerator()

    if scenario == "basic":
        # 基础场景：机器人在路径起点，沿直线前进
        return {
            "rtk_data": gen.generate_rtk_data(),
            "path_data": gen.generate_path_data(num_waypoints=10),
            "expected_behavior": "向东直线前进",
        }

    elif scenario == "turning":
        # 转弯场景：机器人在起点，需要左转
        return {
            "rtk_data": gen.generate_rtk_data(
                lat=gen.DEFAULT_LAT - 0.0001,  # 南偏离
                lon=gen.DEFAULT_LON
            ),
            "path_data": gen.generate_path_data(),
            "expected_behavior": "需要向北转向",
        }

    elif scenario == "reached_goal":
        # 到达目标：机器人在路径终点附近
        path_data = gen.generate_path_data(num_waypoints=5)
        last_lon, last_lat = path_data["waypoints"][-1]

        return {
            "rtk_data": gen.generate_rtk_data(
                lat=last_lat,
                lon=last_lon - 0.000001  # 距离终点很近
            ),
            "path_data": path_data,
            "expected_behavior": "应该输出零速度（已到达）",
        }

    elif scenario == "no_path":
        # 无路径：只有RTK数据，无路径
        return {
            "rtk_data": gen.generate_rtk_data(),
            "path_data": None,
            "expected_behavior": "应该输出零速度（无目标）",
        }

    elif scenario == "circular":
        # 圆形路径跟踪
        return {
            "rtk_data": gen.generate_rtk_data(),
            "path_data": gen.generate_circular_path(),
            "expected_behavior": "圆形路径跟踪，需要持续转向",
        }

    else:
        raise ValueError(f"Unknown scenario: {scenario}")


if __name__ == "__main__":
    # 测试数据生成器
    import json

    print("生成velocity_controller测试数据...\n")

    for scenario in ["basic", "turning", "reached_goal", "no_path", "circular"]:
        data = create_test_scenario(scenario)
        print(f"\n========== 场景: {scenario} ==========")
        print(f"期望行为: {data.get('expected_behavior')}")
        print("\nRTK数据:")
        print(json.dumps(data["rtk_data"], indent=2, ensure_ascii=False))
        if data.get("path_data"):
            print(f"\n路径数据: {len(data['path_data']['waypoints'])} 个点")
            print(f"前3个点: {data['path_data']['waypoints'][:3]}")
