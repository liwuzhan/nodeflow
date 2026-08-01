#!/usr/bin/env python3
"""
测试数据生成器 - trajectory_viz节点

生成符合节点输入格式的模拟数据，用于独立测试
"""

import math
import random
from typing import List, Tuple, Dict, Any


class TestDataGenerator:
    """生成trajectory_viz测试数据"""

    @staticmethod
    def generate_rectangular_field(
        center_lat: float = 31.2,
        center_lon: float = 121.5,
        width_m: float = 100.0,
        height_m: float = 200.0
    ) -> List[Tuple[float, float]]:
        """
        生成矩形地块边界（WGS84坐标）

        Args:
            center_lat: 中心纬度
            center_lon: 中心经度
            width_m: 宽度（米）
            height_m: 高度（米）

        Returns:
            边界点列表 [(lon, lat), ...] - 注意是(lon, lat)格式
        """
        # 经纬度转换系数（近似）
        lat_per_meter = 1.0 / 111000.0
        lon_per_meter = 1.0 / (111000.0 * math.cos(math.radians(center_lat)))

        half_width = width_m / 2.0
        half_height = height_m / 2.0

        # 逆时针方向定义四个角（lon, lat）
        corners = [
            (center_lon - half_width * lon_per_meter, center_lat - half_height * lat_per_meter),  # 左下
            (center_lon + half_width * lon_per_meter, center_lat - half_height * lat_per_meter),  # 右下
            (center_lon + half_width * lon_per_meter, center_lat + half_height * lat_per_meter),  # 右上
            (center_lon - half_width * lon_per_meter, center_lat + half_height * lat_per_meter),  # 左上
        ]

        return corners

    @staticmethod
    def generate_irregular_field(
        center_lat: float = 31.2,
        center_lon: float = 121.5,
        radius_m: float = 100.0,
        num_points: int = 8
    ) -> List[Tuple[float, float]]:
        """
        生成不规则多边形地块

        Args:
            center_lat: 中心纬度
            center_lon: 中心经度
            radius_m: 半径（米）
            num_points: 顶点数量

        Returns:
            边界点列表 [(lon, lat), ...]
        """
        lat_per_meter = 1.0 / 111000.0
        lon_per_meter = 1.0 / (111000.0 * math.cos(math.radians(center_lat)))

        points = []
        for i in range(num_points):
            angle = 2 * math.pi * i / num_points
            # 添加随机扰动
            r = radius_m * (0.8 + 0.4 * random.random())

            dx = r * math.cos(angle)
            dy = r * math.sin(angle)

            lon = center_lon + dx * lon_per_meter
            lat = center_lat + dy * lat_per_meter

            points.append((lon, lat))

        return points

    @staticmethod
    def generate_coverage_path(
        field_boundary: List[Tuple[float, float]],
        row_spacing_m: float = 3.0,
        angle_deg: float = 0.0
    ) -> List[Tuple[float, float]]:
        """
        生成覆盖路径（简化版，生成平行线）

        Args:
            field_boundary: 地块边界 [(lon, lat), ...]
            row_spacing_m: 行距（米）
            angle_deg: 路径角度

        Returns:
            路径点列表 [(lon, lat), ...]
        """
        if not field_boundary or len(field_boundary) < 3:
            return []

        # 获取边界范围
        lons = [p[0] for p in field_boundary]
        lats = [p[1] for p in field_boundary]

        min_lon, max_lon = min(lons), max(lons)
        min_lat, max_lat = min(lats), max(lats)

        center_lat = (min_lat + max_lat) / 2.0
        center_lon = (min_lon + max_lon) / 2.0

        # 转换系数
        lat_per_meter = 1.0 / 111000.0
        lon_per_meter = 1.0 / (111000.0 * math.cos(math.radians(center_lat)))

        # 生成平行线路径
        path = []
        width_m = (max_lon - min_lon) / lon_per_meter
        height_m = (max_lat - min_lat) / lat_per_meter

        num_rows = max(2, int(height_m / row_spacing_m))

        for i in range(num_rows):
            y_offset = (i * row_spacing_m - height_m / 2.0) * lat_per_meter
            y = center_lat + y_offset

            if i % 2 == 0:  # 偶数行从左到右
                path.append((min_lon + 0.1 * (max_lon - min_lon), y))
                path.append((max_lon - 0.1 * (max_lon - min_lon), y))
            else:  # 奇数行从右到左
                path.append((max_lon - 0.1 * (max_lon - min_lon), y))
                path.append((min_lon + 0.1 * (max_lon - min_lon), y))

        return path

    @staticmethod
    def generate_gps_trajectory(
        planned_path: List[Tuple[float, float]],
        lateral_error_m: float = 0.5,
        noise_m: float = 0.1
    ) -> List[Tuple[float, float]]:
        """
        生成模拟GPS轨迹（基于规划路径添加误差）

        Args:
            planned_path: 规划路径 [(lon, lat), ...]
            lateral_error_m: 横向误差（米）
            noise_m: 随机噪声（米）

        Returns:
            GPS轨迹点列表 [(lat, lon), ...] - 注意转换为(lat, lon)格式
        """
        if not planned_path or len(planned_path) < 2:
            return []

        # 获取中心纬度用于转换
        center_lat = sum(p[1] for p in planned_path) / len(planned_path)

        lat_per_meter = 1.0 / 111000.0
        lon_per_meter = 1.0 / (111000.0 * math.cos(math.radians(center_lat)))

        trajectory = []

        for i, (lon, lat) in enumerate(planned_path):
            # 添加横向偏移
            if i < len(planned_path) - 1:
                next_lon, next_lat = planned_path[i + 1]
                # 计算垂直于路径的方向
                dx = next_lon - lon
                dy = next_lat - lat
                length = math.sqrt(dx**2 + dy**2)

                if length > 0:
                    # 归一化并旋转90度得到垂直方向
                    perp_x = -dy / length
                    perp_y = dx / length

                    # 添加横向误差和随机噪声
                    offset = lateral_error_m + random.gauss(0, noise_m)

                    new_lon = lon + perp_x * offset * lon_per_meter
                    new_lat = lat + perp_y * offset * lat_per_meter
                else:
                    new_lon, new_lat = lon, lat
            else:
                new_lon, new_lat = lon, lat

            # 添加额外的随机噪声
            new_lon += random.gauss(0, noise_m) * lon_per_meter
            new_lat += random.gauss(0, noise_m) * lat_per_meter

            # 注意：返回格式为 (lat, lon)
            trajectory.append((new_lat, new_lon))

        return trajectory

    @staticmethod
    def generate_task_request(field_boundary: List[Tuple[float, float]]) -> Dict[str, Any]:
        """
        生成task_request格式的数据

        Args:
            field_boundary: 地块边界 [(lon, lat), ...]

        Returns:
            符合planning.task格式的字典
        """
        return {
            "task_id": "test_task_001",
            "parcel": {
                "outer": field_boundary,  # [(lon, lat), ...]
                "holes": [],
                "points": [],
                "entries": [
                    {"point": list(field_boundary[0]), "heading_deg": 0.0}
                ]
            },
            "work_type": "coverage",
            "timestamp": "2025-12-24T12:00:00Z"
        }

    @staticmethod
    def generate_global_path(path_points: List[Tuple[float, float]]) -> Dict[str, Any]:
        """
        生成global_path格式的数据

        Args:
            path_points: 路径点 [(lon, lat), ...]

        Returns:
            符合planning.path格式的字典
        """
        return {
            "task_id": "test_task_001",
            "path": path_points,  # [(lon, lat), ...]
            "metadata": {
                "algorithm": "test_generator",
                "timestamp": "2025-12-24T12:00:01Z"
            }
        }

    @staticmethod
    def generate_rtk_fix(lat: float, lon: float, heading: float = 0.0) -> Dict[str, Any]:
        """
        生成单个rtk_fix格式的数据

        Args:
            lat: 纬度
            lon: 经度
            heading: 航向角（度）

        Returns:
            RTK数据字典
        """
        return {
            "latitude": lat,
            "longitude": lon,
            "altitude": 10.0,
            "heading": heading,
            "quality": "RTK_FIXED",
            "timestamp": "2025-12-24T12:00:00Z"
        }


def create_test_scenario(scenario: str = "basic") -> Dict[str, Any]:
    """
    创建完整的测试场景数据

    Args:
        scenario: 场景类型 ("basic", "irregular", "large")

    Returns:
        包含所有测试数据的字典
    """
    gen = TestDataGenerator()

    if scenario == "basic":
        # 基础矩形地块
        field = gen.generate_rectangular_field(
            center_lat=31.2,
            center_lon=121.5,
            width_m=100.0,
            height_m=200.0
        )
        path = gen.generate_coverage_path(field, row_spacing_m=3.0)

    elif scenario == "irregular":
        # 不规则地块
        field = gen.generate_irregular_field(
            center_lat=31.2,
            center_lon=121.5,
            radius_m=150.0,
            num_points=8
        )
        path = gen.generate_coverage_path(field, row_spacing_m=4.0)

    elif scenario == "large":
        # 大地块
        field = gen.generate_rectangular_field(
            center_lat=31.2,
            center_lon=121.5,
            width_m=300.0,
            height_m=500.0
        )
        path = gen.generate_coverage_path(field, row_spacing_m=3.5)

    else:
        raise ValueError(f"Unknown scenario: {scenario}")

    # 生成GPS轨迹
    trajectory = gen.generate_gps_trajectory(
        path,
        lateral_error_m=0.5,
        noise_m=0.1
    )

    return {
        "task_request": gen.generate_task_request(field),
        "global_path": gen.generate_global_path(path),
        "rtk_fixes": [gen.generate_rtk_fix(lat, lon) for lat, lon in trajectory],
        "field_boundary": field,
        "planned_path": path,
        "actual_trajectory": trajectory
    }


if __name__ == "__main__":
    # 测试数据生成器
    import json

    print("生成测试数据...")

    for scenario in ["basic", "irregular", "large"]:
        data = create_test_scenario(scenario)

        print(f"\n场景: {scenario}")
        print(f"  地块顶点数: {len(data['field_boundary'])}")
        print(f"  规划路径点数: {len(data['planned_path'])}")
        print(f"  GPS轨迹点数: {len(data['rtk_fixes'])}")

        # 保存为JSON
        output_file = f"fixtures/scenario_{scenario}.json"
        # with open(output_file, 'w', encoding='utf-8') as f:
        #     json.dump(data, f, indent=2, ensure_ascii=False)
        # print(f"  已保存到: {output_file}")
