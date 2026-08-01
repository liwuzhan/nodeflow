"""
测试数据生成器 - global_coverage节点

生成符合节点输入格式的规划任务数据，用于独立测试
"""

from typing import Dict, Any, List, Tuple
import time


class TestDataGenerator:
    """生成global_coverage测试数据"""

    # 测试坐标（上海中心）
    DEFAULT_LAT = 31.2304
    DEFAULT_LON = 121.4737

    @staticmethod
    def generate_rectangular_parcel(
        center_lat: float = DEFAULT_LAT,
        center_lon: float = DEFAULT_LON,
        width_deg: float = 0.001,  # 约111米
        height_deg: float = 0.0005  # 约55米
    ) -> Dict[str, Any]:
        """
        生成矩形地块

        参数:
            center_lat: 中心纬度
            center_lon: 中心经度
            width_deg: 宽度（度）
            height_deg: 高度（度）

        返回:
            符合ParcelData格式的地块数据
        """
        # 计算四个顶点（WGS84坐标，格式为(lon, lat)）
        half_width = width_deg / 2
        half_height = height_deg / 2

        outer = [
            (center_lon - half_width, center_lat - half_height),  # 左下
            (center_lon + half_width, center_lat - half_height),  # 右下
            (center_lon + half_width, center_lat + half_height),  # 右上
            (center_lon - half_width, center_lat + half_height),  # 左上
        ]

        return {
            "outer": outer,
            "holes": [],
            "points": [],
            "entries": []
        }

    @staticmethod
    def generate_complex_parcel_with_hole(
        center_lat: float = DEFAULT_LAT,
        center_lon: float = DEFAULT_LON,
        outer_width_deg: float = 0.002,
        outer_height_deg: float = 0.0015,
        hole_width_deg: float = 0.0005,
        hole_height_deg: float = 0.0003
    ) -> Dict[str, Any]:
        """
        生成带内孔洞的复杂地块

        参数:
            center_lat: 中心纬度
            center_lon: 中心经度
            outer_width_deg: 外边界宽度（度）
            outer_height_deg: 外边界高度（度）
            hole_width_deg: 内孔洞宽度（度）
            hole_height_deg: 内孔洞高度（度）

        返回:
            带孔洞的地块数据
        """
        # 外边界
        half_width = outer_width_deg / 2
        half_height = outer_height_deg / 2

        outer = [
            (center_lon - half_width, center_lat - half_height),
            (center_lon + half_width, center_lat - half_height),
            (center_lon + half_width, center_lat + half_height),
            (center_lon - half_width, center_lat + half_height),
        ]

        # 内孔洞
        hole_half_width = hole_width_deg / 2
        hole_half_height = hole_height_deg / 2

        hole = [
            (center_lon - hole_half_width, center_lat - hole_half_height),
            (center_lon + hole_half_width, center_lat - hole_half_height),
            (center_lon + hole_half_width, center_lat + hole_half_height),
            (center_lon - hole_half_width, center_lat + hole_half_height),
        ]

        return {
            "outer": outer,
            "holes": [hole],  # 单个孔洞
            "points": [],
            "entries": []
        }

    @staticmethod
    def generate_vehicle_config(
        implement_width: float = 3.0,
        overlap_ratio: float = 0.1,
        path_inset: float = 1.0,
        pivot_turn: bool = True
    ) -> Dict[str, Any]:
        """
        生成车辆配置

        参数:
            implement_width: 实施宽度（米）
            overlap_ratio: 行重叠率（0-1）
            path_inset: 路径内缩距离（米）
            pivot_turn: 是否支持原地转向

        返回:
            车辆配置字典
        """
        return {
            "implement_width_m": implement_width,
            "overlap_ratio": overlap_ratio,
            "path_inset_m": path_inset,
            "pivot_turn": pivot_turn,
            "yaw_rate_max_deg_s": 60.0
        }

    @staticmethod
    def generate_path_output(
        task_id: str,
        waypoints: List[Tuple[float, float]],
        status: str = "success"
    ) -> Dict[str, Any]:
        """
        生成路径输出数据（期望的输出格式）

        参数:
            task_id: 任务ID
            waypoints: 路径点列表 [(lon, lat), ...]
            status: 规划状态

        返回:
            符合节点输出端口格式的字典
        """
        return {
            "task_id": task_id,
            "timestamp": time.time(),
            "path": waypoints,
            "status": status,
            "message": "Path found" if status == "success" else "No path found"
        }


def create_test_scenario(scenario: str = "simple_rect") -> Dict[str, Any]:
    """
    创建完整的测试场景

    参数:
        scenario: 场景类型
            - "simple_rect": 简单矩形地块
            - "complex_with_hole": 带孔洞的复杂地块
            - "wide_field": 宽阔的田地
            - "narrow_strip": 狭长的条形地块

    返回:
        包含所有测试数据的字典
    """
    gen = TestDataGenerator()

    if scenario == "simple_rect":
        # 基础场景：简单矩形地块
        parcel = gen.generate_rectangular_parcel(
            width_deg=0.001,    # 约111米
            height_deg=0.0005   # 约55米
        )
        return {
            "task_id": "test_simple_001",
            "parcel": parcel,
            "vehicle": gen.generate_vehicle_config(implement_width=3.0),
            "expected_path_count_min": 10,  # 预期至少10个路径点
            "description": "简单矩形地块规划"
        }

    elif scenario == "complex_with_hole":
        # 复杂场景：带孔洞的地块
        parcel = gen.generate_complex_parcel_with_hole(
            outer_width_deg=0.002,
            outer_height_deg=0.0015
        )
        return {
            "task_id": "test_hole_001",
            "parcel": parcel,
            "vehicle": gen.generate_vehicle_config(implement_width=3.0),
            "expected_path_count_min": 15,
            "description": "带内孔洞的地块规划"
        }

    elif scenario == "wide_field":
        # 宽阔田地：宽度大
        parcel = gen.generate_rectangular_parcel(
            width_deg=0.002,    # 约222米
            height_deg=0.001    # 约111米
        )
        return {
            "task_id": "test_wide_001",
            "parcel": parcel,
            "vehicle": gen.generate_vehicle_config(implement_width=3.0, overlap_ratio=0.05),
            "expected_path_count_min": 30,
            "description": "宽阔田地规划"
        }

    elif scenario == "narrow_strip":
        # 狭长条形：高度小
        parcel = gen.generate_rectangular_parcel(
            width_deg=0.0005,   # 约55米
            height_deg=0.002    # 约222米
        )
        return {
            "task_id": "test_narrow_001",
            "parcel": parcel,
            "vehicle": gen.generate_vehicle_config(implement_width=2.0),
            "expected_path_count_min": 20,
            "description": "狭长条形地块规划"
        }

    else:
        raise ValueError(f"Unknown scenario: {scenario}")


def create_vehicle_scenarios() -> Dict[str, Dict[str, Any]]:
    """
    创建多个车辆配置场景

    返回:
        包含不同车辆配置的测试场景字典
    """
    gen = TestDataGenerator()
    parcel = gen.generate_rectangular_parcel()

    return {
        "narrow_implement": {
            "task_id": "test_narrow_impl_001",
            "parcel": parcel,
            "vehicle": gen.generate_vehicle_config(implement_width=2.0),
            "description": "窄实施宽度"
        },
        "wide_implement": {
            "task_id": "test_wide_impl_001",
            "parcel": parcel,
            "vehicle": gen.generate_vehicle_config(implement_width=5.0),
            "description": "宽实施宽度"
        },
        "high_overlap": {
            "task_id": "test_high_overlap_001",
            "parcel": parcel,
            "vehicle": gen.generate_vehicle_config(overlap_ratio=0.2),
            "description": "高重叠率"
        },
        "low_overlap": {
            "task_id": "test_low_overlap_001",
            "parcel": parcel,
            "vehicle": gen.generate_vehicle_config(overlap_ratio=0.05),
            "description": "低重叠率"
        }
    }


if __name__ == "__main__":
    # 测试数据生成器
    import json

    print("生成global_coverage测试数据...\n")

    for scenario in ["simple_rect", "complex_with_hole", "wide_field", "narrow_strip"]:
        data = create_test_scenario(scenario)
        print(f"\n========== 场景: {scenario} ==========")
        print(f"描述: {data['description']}")
        print(f"任务ID: {data['task_id']}")
        print(f"地块外边界点数: {len(data['parcel']['outer'])}")
        print(f"地块孔洞数: {len(data['parcel']['holes'])}")
        print(f"车辆实施宽度: {data['vehicle']['implement_width_m']}m")
        print(f"预期路径点数: >= {data['expected_path_count_min']}")
