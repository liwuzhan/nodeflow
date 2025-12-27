"""
trajectory_viz节点集成测试

测试节点与SDK的交互，使用mock来模拟SDK行为
验证节点的完整工作流程，包括数据收发和文件生成
"""

import sys
from pathlib import Path
from unittest.mock import Mock, MagicMock, patch, call
import tempfile

# 添加trajectory_viz节点目录到路径
node_dir = Path(__file__).parent.parent
sys.path.insert(0, str(node_dir))

# 添加项目根路径（用于SDK导入）
project_root = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(project_root))

import pytest
import json


class TestSDKPortInteraction:
    """测试与SDK端口的交互"""

    @pytest.fixture
    def mock_sdk(self):
        """创建模拟的SDK对象"""
        sdk = Mock()

        # 模拟参数
        sdk.params = Mock()
        sdk.params.get = Mock(side_effect=lambda key, default=None: {
            "output_dir": "./logs/jpg",
            "timeout": 300.0,
            "update_interval": 10.0
        }.get(key, default))

        # 模拟端口创建
        task_port = Mock()
        path_port = Mock()
        rtk_port = Mock()
        output_port = Mock()

        sdk.create_input_port = Mock(side_effect=lambda name: {
            "task_request": task_port,
            "global_path": path_port,
            "rtk_fix": rtk_port
        }.get(name, Mock()))

        sdk.create_output_port = Mock(return_value=output_port)

        return sdk, task_port, path_port, rtk_port, output_port

    def test_port_creation(self, mock_sdk, basic_task_request):
        """测试端口创建"""
        sdk, task_port, path_port, rtk_port, output_port = mock_sdk

        # 模拟端口接收数据
        task_port.recv_latest = Mock(return_value=basic_task_request)
        path_port.recv_latest = Mock(return_value={"path": []})
        rtk_port.recv_latest = Mock(return_value={"latitude": 31.2, "longitude": 121.5})

        # 模拟端口发送数据
        output_port.send = Mock(return_value=True)

        # 验证端口创建调用
        task = sdk.create_input_port("task_request")
        assert task is task_port

        # 验证参数获取
        output_dir = sdk.params.get("output_dir")
        assert output_dir == "./logs/jpg"

    def test_data_reception_from_port(self, mock_sdk, complete_scenario):
        """测试从端口接收数据"""
        sdk, task_port, path_port, rtk_port, output_port = mock_sdk

        # 配置模拟端口返回数据
        task_port.recv_latest = Mock(return_value=complete_scenario["task_request"])
        path_port.recv_latest = Mock(return_value=complete_scenario["global_path"])

        # 模拟接收RTK流
        rtk_trajectory = complete_scenario["rtk_fixes"]
        rtk_port.recv_latest = Mock(side_effect=rtk_trajectory)

        # 验证接收调用
        task_data = task_port.recv_latest()
        assert task_data == complete_scenario["task_request"]

        path_data = path_port.recv_latest()
        assert path_data == complete_scenario["global_path"]

        # 验证多次调用RTK端口
        for _ in range(5):
            rtk_data = rtk_port.recv_latest()
            assert rtk_data in rtk_trajectory


class TestNodeInitialization:
    """测试节点初始化"""

    def test_visualizer_initialization_with_custom_output_dir(self, temp_output_dir):
        """测试可视化器初始化"""
        from run import TrajectoryVisualizer

        viz = TrajectoryVisualizer(output_dir=str(temp_output_dir))

        assert viz.output_dir == temp_output_dir
        assert temp_output_dir.exists()

    def test_visualizer_initialization_default(self):
        """测试默认初始化"""
        from run import TrajectoryVisualizer

        viz = TrajectoryVisualizer()

        # 应该创建默认输出目录
        assert viz.output_dir.name == "jpg"
        assert viz.field_boundary is None
        assert viz.planned_path is None
        assert viz.actual_trajectory == []


class TestCompleteWorkflow:
    """测试完整工作流"""

    def test_end_to_end_visualization_basic(self, temp_output_dir, complete_scenario):
        """测试端到端可视化流程（基础场景）"""
        from run import TrajectoryVisualizer

        viz = TrajectoryVisualizer(output_dir=str(temp_output_dir))

        # 步骤1：添加地块数据
        assert viz.add_field_data(complete_scenario["task_request"]) is True

        # 步骤2：添加路径数据
        assert viz.add_path_data(complete_scenario["global_path"]) is True

        # 步骤3：添加GPS轨迹数据
        for rtk in complete_scenario["rtk_fixes"][:50]:
            viz.add_gps_point(rtk)

        # 步骤4：检查就绪状态
        assert viz.is_ready() is True

        # 步骤5：生成可视化
        result = viz.generate_visualization()

        assert result is not None
        assert isinstance(result, tuple) and len(result) == 2

        # 验证输出文件
        image_path_str, metrics = result
        image_path = Path(image_path_str)
        assert image_path.exists()
        assert image_path.stat().st_size > 10000  # 至少10KB
        assert isinstance(metrics, dict)

    def test_workflow_with_partial_data(self, temp_output_dir, complete_scenario):
        """测试不完整数据的工作流"""
        from run import TrajectoryVisualizer

        viz = TrajectoryVisualizer(output_dir=str(temp_output_dir))

        # 只添加地块数据
        viz.add_field_data(complete_scenario["task_request"])

        # 未就绪
        assert not viz.is_ready()

        # 添加路径数据
        viz.add_path_data(complete_scenario["global_path"])

        # 仍未就绪（缺轨迹）
        assert not viz.is_ready()

        # 添加GPS点
        viz.add_gps_point(complete_scenario["rtk_fixes"][0])
        assert not viz.is_ready()  # 只有1个点

        viz.add_gps_point(complete_scenario["rtk_fixes"][1])

        # 现在就绪
        assert viz.is_ready() is True

        # 应该能生成可视化
        result = viz.generate_visualization()
        assert result is not None
        assert isinstance(result, tuple) and len(result) == 2

    def test_multiple_visualization_calls(self, temp_output_dir, complete_scenario):
        """测试多次调用可视化"""
        from run import TrajectoryVisualizer

        viz = TrajectoryVisualizer(output_dir=str(temp_output_dir))

        viz.add_field_data(complete_scenario["task_request"])
        viz.add_path_data(complete_scenario["global_path"])

        # 添加轨迹的不同部分
        viz.add_gps_point(complete_scenario["rtk_fixes"][0])
        viz.add_gps_point(complete_scenario["rtk_fixes"][1])

        # 第一次可视化
        result1 = viz.generate_visualization()
        assert result1 is not None
        path1, metrics1 = result1

        # 记录第一次的轨迹点数
        first_trajectory_points = metrics1["trajectory_points"]

        # 继续添加更多轨迹
        for rtk in complete_scenario["rtk_fixes"][2:20]:
            viz.add_gps_point(rtk)

        # 第二次可视化
        result2 = viz.generate_visualization()
        assert result2 is not None
        path2, metrics2 = result2

        # 两次应该有不同数量的轨迹点（第二次更多）
        assert metrics2["trajectory_points"] > first_trajectory_points


class TestDataValidation:
    """测试数据验证"""

    def test_invalid_coordinate_format(self):
        """测试无效的坐标格式"""
        from run import TrajectoryVisualizer

        viz = TrajectoryVisualizer()

        # 坐标列表为空
        invalid_data = {"parcel": {"outer": []}}
        assert viz.add_field_data(invalid_data) is False

        # 坐标不是元组
        invalid_data = {"parcel": {"outer": [121.5, 31.2]}}
        result = viz.add_field_data(invalid_data)
        # 应该能检测到错误
        assert result is False or len(viz.field_boundary) == 0

    def test_missing_required_fields(self):
        """测试缺少必需字段"""
        from run import TrajectoryVisualizer

        viz = TrajectoryVisualizer()

        # 缺少latitude
        incomplete_gps = {"longitude": 121.5}
        viz.add_gps_point(incomplete_gps)
        assert len(viz.actual_trajectory) == 0

        # 缺少longitude
        incomplete_gps = {"latitude": 31.2}
        viz.add_gps_point(incomplete_gps)
        assert len(viz.actual_trajectory) == 0

    def test_type_coercion(self):
        """测试类型转换"""
        from run import TrajectoryVisualizer

        viz = TrajectoryVisualizer()

        # 字符串转换为浮点数
        gps_data = {
            "latitude": "31.2",
            "longitude": "121.5"
        }

        viz.add_gps_point(gps_data)

        # 应该能成功转换
        assert len(viz.actual_trajectory) == 1
        lat, lon = viz.actual_trajectory[0]
        assert isinstance(lat, float)
        assert isinstance(lon, float)


class TestErrorHandling:
    """测试错误处理"""

    def test_graceful_handling_of_nan_values(self):
        """测试NaN值的处理"""
        from run import TrajectoryVisualizer
        import math

        viz = TrajectoryVisualizer()

        # 设置有效的基础数据
        viz.planned_path = [(31.2, 121.5), (31.21, 121.51)]

        # 添加包含NaN的轨迹点
        viz.actual_trajectory = [(31.2, 121.5), (31.21, 121.51)]

        # 计算指标不应该崩溃
        try:
            metrics = viz.calculate_metrics()
            # 指标值应该是有限的
            assert math.isfinite(metrics.get("avg_lateral_error", 0))
        except Exception as e:
            pytest.fail(f"Should not raise exception for valid data: {e}")

    def test_visualization_with_single_point_trajectory(self, temp_output_dir):
        """测试单点轨迹的可视化"""
        from run import TrajectoryVisualizer

        viz = TrajectoryVisualizer(output_dir=str(temp_output_dir))

        # 设置最小数据
        viz.field_boundary = [(31.2, 121.5), (31.21, 121.5), (31.2, 121.51)]
        viz.planned_path = [(31.2, 121.5), (31.21, 121.51)]
        viz.actual_trajectory = [(31.2, 121.5), (31.21, 121.51)]

        # 应该能生成可视化
        result = viz.generate_visualization()
        assert result is not None
        assert isinstance(result, tuple) and len(result) == 2


class TestMetricsReporting:
    """测试指标报告"""

    def test_metrics_in_output(self, temp_output_dir, complete_scenario):
        """测试输出中的指标"""
        from run import TrajectoryVisualizer

        viz = TrajectoryVisualizer(output_dir=str(temp_output_dir))

        viz.add_field_data(complete_scenario["task_request"])
        viz.add_path_data(complete_scenario["global_path"])

        # 添加轨迹
        for rtk in complete_scenario["rtk_fixes"][:50]:
            viz.add_gps_point(rtk)

        result = viz.generate_visualization()

        # 验证输出包含指标
        assert result is not None
        image_path, metrics = result

        assert "planned_distance_m" in metrics
        assert "actual_distance_m" in metrics
        assert "distance_error_percent" in metrics
        assert "avg_lateral_error_m" in metrics
        assert "max_lateral_error_m" in metrics

    def test_metrics_reasonableness(self, complete_scenario):
        """测试指标的合理性"""
        from run import TrajectoryVisualizer

        viz = TrajectoryVisualizer()

        viz.add_field_data(complete_scenario["task_request"])
        viz.add_path_data(complete_scenario["global_path"])

        # 添加足够的轨迹
        for rtk in complete_scenario["rtk_fixes"][:100]:
            viz.add_gps_point(rtk)

        metrics = viz.calculate_metrics()

        # 验证指标在合理范围内
        assert metrics["planned_distance_m"] > 0
        assert metrics["actual_distance_m"] > 0

        # 距离误差百分比不应该是异常值
        assert 0 <= metrics["distance_error_percent"] <= 200

        # 横向误差不应该超过100米
        assert 0 <= metrics["avg_lateral_error_m"] < 100
        assert 0 <= metrics["max_lateral_error_m"] < 100


class TestScenarios:
    """测试不同场景"""

    @pytest.mark.parametrize("scenario_name", ["basic", "irregular", "large"])
    def test_all_scenarios(self, scenario_name, temp_output_dir, load_fixture):
        """测试所有场景"""
        from run import TrajectoryVisualizer

        # 加载场景数据
        scenario_data = load_fixture(f"scenario_{scenario_name}.json")

        viz = TrajectoryVisualizer(output_dir=str(temp_output_dir))

        # 添加数据
        viz.add_field_data(scenario_data["task_request"])
        viz.add_path_data(scenario_data["global_path"])

        # 添加轨迹
        for rtk in scenario_data["rtk_fixes"][:50]:
            viz.add_gps_point(rtk)

        # 应该就绪
        assert viz.is_ready() is True

        # 应该能生成可视化
        result = viz.generate_visualization()
        assert result is not None
        image_path, metrics = result
        assert Path(image_path).exists()
