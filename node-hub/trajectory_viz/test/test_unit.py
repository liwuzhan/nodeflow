"""
trajectory_viz节点单元测试

测试节点内部逻辑，不依赖SDK或外部系统
仅测试数据处理、坐标转换、计算等纯函数逻辑
"""

import sys
from pathlib import Path

# 添加trajectory_viz节点目录到路径
node_dir = Path(__file__).parent.parent
sys.path.insert(0, str(node_dir))

# 添加项目根路径（用于SDK导入）
project_root = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(project_root))

import pytest
import math


class TestTrajectoryVisualizerDataProcessing:
    """测试TrajectoryVisualizer的数据处理逻辑"""

    def test_add_field_data_basic(self, basic_task_request):
        """测试基础地块数据添加"""
        from run import TrajectoryVisualizer

        viz = TrajectoryVisualizer()

        # 添加地块数据
        result = viz.add_field_data(basic_task_request)

        assert result is True
        assert viz.field_boundary is not None
        assert len(viz.field_boundary) == 4  # 矩形有4个顶点

        # 验证坐标转换：输入是 (lon, lat)，应转换为 (lat, lon)
        first_point = viz.field_boundary[0]
        assert isinstance(first_point, tuple)
        assert len(first_point) == 2

        # 检查坐标范围合理性（上海地区）
        lat, lon = first_point
        assert 30.0 < lat < 32.0  # 纬度范围
        assert 120.0 < lon < 122.0  # 经度范围

    def test_add_field_data_irregular(self, irregular_task_request):
        """测试不规则地块数据添加"""
        from run import TrajectoryVisualizer

        viz = TrajectoryVisualizer()
        result = viz.add_field_data(irregular_task_request)

        assert result is True
        assert len(viz.field_boundary) == 8  # 不规则多边形8个顶点

    def test_add_field_data_invalid(self):
        """测试无效地块数据的处理"""
        from run import TrajectoryVisualizer

        viz = TrajectoryVisualizer()

        # 测试空数据
        assert viz.add_field_data(None) is False
        assert viz.add_field_data({}) is False

        # 测试缺少parcel
        assert viz.add_field_data({"task_id": "test"}) is False

        # 测试缺少outer
        assert viz.add_field_data({"parcel": {}}) is False

        # 测试empty outer
        assert viz.add_field_data({"parcel": {"outer": []}}) is False

    def test_add_path_data_basic(self, basic_global_path):
        """测试路径数据添加"""
        from run import TrajectoryVisualizer

        viz = TrajectoryVisualizer()
        result = viz.add_path_data(basic_global_path)

        assert result is True
        assert viz.planned_path is not None
        assert len(viz.planned_path) >= 2

        # 验证坐标转换
        first_point = viz.planned_path[0]
        lat, lon = first_point
        assert 30.0 < lat < 32.0
        assert 120.0 < lon < 122.0

    def test_add_path_data_invalid(self):
        """测试无效路径数据的处理"""
        from run import TrajectoryVisualizer

        viz = TrajectoryVisualizer()

        # 测试空数据
        assert viz.add_path_data(None) is False
        assert viz.add_path_data({}) is False

        # 测试缺少path
        assert viz.add_path_data({"task_id": "test"}) is False

        # 测试路径点不足
        assert viz.add_path_data({"path": []}) is False
        assert viz.add_path_data({"path": [(121.5, 31.2)]}) is False

    def test_add_gps_point(self, basic_rtk_trajectory):
        """测试GPS点添加"""
        from run import TrajectoryVisualizer

        viz = TrajectoryVisualizer()

        # 添加第一个GPS点
        first_rtk = basic_rtk_trajectory[0]
        viz.add_gps_point(first_rtk)

        assert len(viz.actual_trajectory) == 1

        # 验证坐标格式（已经是 lat, lon）
        lat, lon = viz.actual_trajectory[0]
        assert 30.0 < lat < 32.0
        assert 120.0 < lon < 122.0

        # 添加多个GPS点
        for rtk in basic_rtk_trajectory[1:10]:
            viz.add_gps_point(rtk)

        assert len(viz.actual_trajectory) == 10

    def test_add_gps_point_invalid(self):
        """测试无效GPS数据的处理"""
        from run import TrajectoryVisualizer

        viz = TrajectoryVisualizer()

        # 无效数据不应导致崩溃，但也不添加点
        viz.add_gps_point(None)
        assert len(viz.actual_trajectory) == 0

        viz.add_gps_point({})
        assert len(viz.actual_trajectory) == 0

        viz.add_gps_point({"latitude": None, "longitude": 121.5})
        assert len(viz.actual_trajectory) == 0

    def test_is_ready(self, complete_scenario):
        """测试数据就绪检查"""
        from run import TrajectoryVisualizer

        viz = TrajectoryVisualizer()

        # 初始状态：未就绪
        assert not viz.is_ready()

        # 仅有地块：未就绪
        viz.add_field_data(complete_scenario["task_request"])
        assert not viz.is_ready()

        # 有地块和路径：未就绪（缺轨迹）
        viz.add_path_data(complete_scenario["global_path"])
        assert not viz.is_ready()

        # 添加至少2个GPS点：就绪
        viz.add_gps_point(complete_scenario["rtk_fixes"][0])
        assert not viz.is_ready()  # 只有1个点

        viz.add_gps_point(complete_scenario["rtk_fixes"][1])
        assert viz.is_ready() is True  # 有2个点了


class TestDistanceCalculation:
    """测试距离计算函数"""

    def test_distance_calculation_same_point(self):
        """测试同一点的距离（应为0）"""
        from run import TrajectoryVisualizer

        viz = TrajectoryVisualizer()
        # 准备数据以调用calculate_metrics
        viz.planned_path = [(31.2, 121.5), (31.2, 121.5)]
        viz.actual_trajectory = [(31.2, 121.5), (31.2, 121.5)]

        metrics = viz.calculate_metrics()

        # 同一点，路径长度应该为0或接近0
        assert metrics["planned_distance_m"] < 1.0  # 小于1米
        assert metrics["actual_distance_m"] < 1.0

    def test_distance_calculation_known_distance(self):
        """测试已知距离的计算准确性"""
        from run import TrajectoryVisualizer

        viz = TrajectoryVisualizer()

        # 北移约111米（1度纬度 ≈ 111km）
        p1 = (31.2, 121.5)
        p2 = (31.201, 121.5)  # 0.001度 ≈ 111米

        viz.planned_path = [p1, p2]
        viz.actual_trajectory = [p1, p2]

        metrics = viz.calculate_metrics()

        # 验证距离（允许10%误差）
        expected_distance = 111.0  # 米
        assert 100.0 < metrics["planned_distance_m"] < 120.0

    def test_lateral_error_calculation(self, complete_scenario):
        """测试横向误差计算"""
        from run import TrajectoryVisualizer

        viz = TrajectoryVisualizer()

        # 添加数据
        viz.add_path_data(complete_scenario["global_path"])

        # 添加GPS轨迹（有横向误差）
        for rtk in complete_scenario["rtk_fixes"][:20]:
            viz.add_gps_point(rtk)

        metrics = viz.calculate_metrics()

        # 应该有横向误差统计
        assert "avg_lateral_error_m" in metrics
        assert "max_lateral_error_m" in metrics

        # 横向误差应该是合理的数值（不应该是inf或nan）
        assert math.isfinite(metrics["avg_lateral_error_m"])
        assert math.isfinite(metrics["max_lateral_error_m"])

        # 测试数据有约0.5m的横向误差，应该在合理范围内
        assert 0.0 <= metrics["avg_lateral_error_m"] < 10.0  # 小于10米
        assert 0.0 <= metrics["max_lateral_error_m"] < 20.0


class TestCoordinateConversion:
    """测试坐标转换逻辑"""

    def test_field_boundary_conversion(self):
        """测试地块边界坐标转换"""
        from run import TrajectoryVisualizer

        viz = TrajectoryVisualizer()

        # 模拟输入：(lon, lat) 格式
        input_data = {
            "parcel": {
                "outer": [
                    (121.5, 31.2),  # (lon, lat)
                    (121.51, 31.21),
                    (121.52, 31.22)
                ]
            }
        }

        viz.add_field_data(input_data)

        # 应该转换为 (lat, lon) 格式
        assert viz.field_boundary[0] == (31.2, 121.5)  # (lat, lon)
        assert viz.field_boundary[1] == (31.21, 121.51)
        assert viz.field_boundary[2] == (31.22, 121.52)

    def test_path_conversion(self):
        """测试路径坐标转换"""
        from run import TrajectoryVisualizer

        viz = TrajectoryVisualizer()

        # 模拟输入：(lon, lat) 格式
        input_data = {
            "path": [
                (121.5, 31.2),  # (lon, lat)
                (121.51, 31.21)
            ]
        }

        viz.add_path_data(input_data)

        # 应该转换为 (lat, lon) 格式
        assert viz.planned_path[0] == (31.2, 121.5)  # (lat, lon)
        assert viz.planned_path[1] == (31.21, 121.51)


class TestMetricsCalculation:
    """测试统计指标计算"""

    def test_metrics_with_complete_data(self, complete_scenario):
        """测试完整数据的指标计算"""
        from run import TrajectoryVisualizer

        viz = TrajectoryVisualizer()

        viz.add_path_data(complete_scenario["global_path"])

        # 添加部分GPS轨迹
        for rtk in complete_scenario["rtk_fixes"][:30]:
            viz.add_gps_point(rtk)

        metrics = viz.calculate_metrics()

        # 验证所有必需指标存在
        required_keys = [
            "planned_distance_m",
            "actual_distance_m",
            "distance_error_m",
            "distance_error_percent",
            "avg_lateral_error_m",
            "max_lateral_error_m",
            "trajectory_points"
        ]

        for key in required_keys:
            assert key in metrics, f"Missing metric: {key}"

        # 验证数值合理性
        assert metrics["planned_distance_m"] > 0
        assert metrics["actual_distance_m"] > 0
        assert 0 <= metrics["distance_error_percent"] <= 200  # 允许一定范围
        assert metrics["trajectory_points"] == 30

    def test_metrics_with_no_data(self):
        """测试无数据时的指标计算"""
        from run import TrajectoryVisualizer

        viz = TrajectoryVisualizer()

        metrics = viz.calculate_metrics()

        # 无数据应返回空字典
        assert metrics == {}


class TestEdgeCases:
    """测试边界情况"""

    def test_very_large_field(self, large_task_request, large_global_path):
        """测试大地块处理"""
        from run import TrajectoryVisualizer

        viz = TrajectoryVisualizer()

        # 大地块应该能正常处理
        assert viz.add_field_data(large_task_request) is True
        assert viz.add_path_data(large_global_path) is True

        # 验证数据量
        assert len(viz.field_boundary) >= 3
        assert len(viz.planned_path) >= 2

    def test_minimum_valid_data(self):
        """测试最小有效数据集"""
        from run import TrajectoryVisualizer

        viz = TrajectoryVisualizer()

        # 最小地块（三角形）
        min_field = {
            "parcel": {
                "outer": [(121.5, 31.2), (121.51, 31.2), (121.5, 31.21)]
            }
        }

        # 最小路径（2个点）
        min_path = {
            "path": [(121.5, 31.2), (121.51, 31.21)]
        }

        assert viz.add_field_data(min_field) is True
        assert viz.add_path_data(min_path) is True

        # 添加2个GPS点
        viz.add_gps_point({"latitude": 31.2, "longitude": 121.5})
        viz.add_gps_point({"latitude": 31.21, "longitude": 121.51})

        # 应该就绪
        assert viz.is_ready() is True
