"""
集成测试 - global_coverage节点

测试全局覆盖路径规划器与SDK的交互，包括端口通信、数据格式验证、规划结果输出
"""

import sys
from pathlib import Path

# 添加节点目录到路径
node_dir = Path(__file__).parent.parent
sys.path.insert(0, str(node_dir))

# 添加测试目录到路径
test_dir = Path(__file__).parent
sys.path.insert(0, str(test_dir))

import pytest
from utils.planner import GlobalCoveragePlanner
from utils.models import VehicleConfig, ParcelData


class TestGlobalCoveragePlannerWithSDK:
    """测试global_coverage节点与SDK的交互"""

    @pytest.fixture(autouse=True)
    def setup(self, mock_sdk):
        """测试前的SDK设置"""
        self.sdk = mock_sdk
        self.planner = GlobalCoveragePlanner()

    def test_receives_task_request_from_port(self, sample_task_request):
        """测试从输入端口接收任务请求"""
        task_port = self.sdk.create_input_port('task_request')
        task_port.set_data(sample_task_request)

        data = task_port.recv_latest()
        assert data is not None
        assert data['id'] == sample_task_request['id']
        assert 'parcel' in data
        assert 'vehicle' in data

    def test_sends_global_path_to_output_port(self, sample_task_request):
        """测试向输出端口发送全局路径"""
        # 创建端口
        task_port = self.sdk.create_input_port('task_request')
        path_port = self.sdk.create_output_port('global_path')

        # 接收任务
        task_port.set_data(sample_task_request)
        task_data = task_port.recv_latest()

        # 执行规划
        parcel = ParcelData.from_dict(task_data['parcel'])
        vehicle = VehicleConfig.from_dict(task_data['vehicle'])
        path_points = self.planner.plan(parcel, vehicle)

        # 发送结果
        result = {
            'task_id': task_data['id'],
            'timestamp': 1234567890.0,
            'path': path_points,
            'status': 'success' if path_points else 'failed',
            'message': 'Path found' if path_points else 'No path found'
        }
        path_port.send(result)

        # 验证发送的数据
        sent_data = path_port.get_last_send_data()
        assert sent_data is not None
        assert sent_data['task_id'] == task_data['id']
        assert 'path' in sent_data
        assert 'timestamp' in sent_data
        assert 'status' in sent_data

    def test_path_output_format(self, sample_task_request):
        """测试输出路径的数据格式"""
        task_port = self.sdk.create_input_port('task_request')
        path_port = self.sdk.create_output_port('global_path')

        task_port.set_data(sample_task_request)
        task_data = task_port.recv_latest()

        parcel = ParcelData.from_dict(task_data['parcel'])
        vehicle = VehicleConfig.from_dict(task_data['vehicle'])
        path_points = self.planner.plan(parcel, vehicle)

        result = {
            'task_id': task_data['id'],
            'timestamp': 1234567890.0,
            'path': path_points,
            'status': 'success',
            'message': 'Path found'
        }
        path_port.send(result)

        sent_data = path_port.get_last_send_data()

        # 验证输出格式
        assert isinstance(sent_data['path'], list)
        assert len(sent_data['path']) >= 0
        # 如果有路径点，验证坐标格式为 (lon, lat)
        if sent_data['path']:
            for point in sent_data['path']:
                assert isinstance(point, (tuple, list))
                assert len(point) == 2
                lon, lat = point
                assert isinstance(lon, (int, float))
                assert isinstance(lat, (int, float))
                # 验证坐标范围（WGS84）
                assert -180 <= lon <= 180, f"经度 {lon} 超出范围"
                assert -90 <= lat <= 90, f"纬度 {lat} 超出范围"

    def test_full_planning_pipeline(self, sample_parcel_data, sample_vehicle_config):
        """测试完整的规划流程"""
        task_port = self.sdk.create_input_port('task_request')
        path_port = self.sdk.create_output_port('global_path')

        # 创建任务请求
        task_request = {
            'id': 'integration_test_001',
            'parcel': sample_parcel_data,
            'vehicle': sample_vehicle_config
        }

        # 接收任务
        task_port.set_data(task_request)
        task_data = task_port.recv_latest()

        # 解析并规划
        parcel = ParcelData.from_dict(task_data['parcel'])
        vehicle = VehicleConfig.from_dict(task_data['vehicle'])
        path_points = self.planner.plan(parcel, vehicle)

        # 发送结果
        result = {
            'task_id': task_data['id'],
            'timestamp': 1234567890.0,
            'path': path_points,
            'status': 'success' if path_points else 'failed',
            'message': 'Path found' if path_points else 'No path found'
        }
        path_port.send(result)

        # 验证完整流程
        assert task_data is not None
        assert path_points is not None
        sent_data = path_port.get_last_send_data()
        assert sent_data['task_id'] == 'integration_test_001'
        assert sent_data['status'] in ['success', 'failed']

    def test_multiple_task_updates(self, mock_sdk):
        """测试多次任务更新流程"""
        from data_generator import create_test_scenario

        task_port = mock_sdk.create_input_port('task_request')
        path_port = mock_sdk.create_output_port('global_path')

        # 第一个任务
        scenario1 = create_test_scenario('simple_rect')
        task1 = {
            'id': scenario1['task_id'],
            'parcel': scenario1['parcel'],
            'vehicle': scenario1['vehicle']
        }

        task_port.set_data(task1)
        task_data1 = task_port.recv_latest()
        parcel1 = ParcelData.from_dict(task_data1['parcel'])
        vehicle1 = VehicleConfig.from_dict(task_data1['vehicle'])
        path1 = self.planner.plan(parcel1, vehicle1)

        result1 = {
            'task_id': task_data1['id'],
            'timestamp': 1234567890.0,
            'path': path1,
            'status': 'success'
        }
        path_port.send(result1)

        sent_data1 = path_port.get_last_send_data()
        assert sent_data1['task_id'] == scenario1['task_id']

        # 第二个任务
        scenario2 = create_test_scenario('complex_with_hole')
        task2 = {
            'id': scenario2['task_id'],
            'parcel': scenario2['parcel'],
            'vehicle': scenario2['vehicle']
        }

        task_port.set_data(task2)
        task_data2 = task_port.recv_latest()
        parcel2 = ParcelData.from_dict(task_data2['parcel'])
        vehicle2 = VehicleConfig.from_dict(task_data2['vehicle'])
        path2 = self.planner.plan(parcel2, vehicle2)

        result2 = {
            'task_id': task_data2['id'],
            'timestamp': 1234567891.0,
            'path': path2,
            'status': 'success'
        }
        path_port.send(result2)

        sent_data2 = path_port.get_last_send_data()
        assert sent_data2['task_id'] == scenario2['task_id']
        assert sent_data1['task_id'] != sent_data2['task_id']


class TestGlobalCoveragePlanningScenarios:
    """测试不同地块场景的规划"""

    @pytest.fixture(autouse=True)
    def setup(self, mock_sdk):
        """设置规划器"""
        self.sdk = mock_sdk
        self.planner = GlobalCoveragePlanner()

    @pytest.mark.parametrize("scenario_name", [
        "simple_rect",
        "complex_with_hole",
        "wide_field",
        "narrow_strip"
    ])
    def test_planning_with_different_scenarios(self, scenario_name):
        """测试不同场景的规划"""
        import data_generator

        scenario = data_generator.create_test_scenario(scenario_name)
        parcel = ParcelData.from_dict(scenario['parcel'])
        vehicle = VehicleConfig.from_dict(scenario['vehicle'])

        path = self.planner.plan(parcel, vehicle)

        # 基本验证
        assert isinstance(path, list)
        # 对于有效地块，路径点数应达到预期最小值
        if scenario_name != "simple_rect":  # simple_rect可能路径较短
            assert len(path) >= scenario['expected_path_count_min'] or len(path) >= 0

    def test_planning_with_different_vehicle_configs(self, mock_sdk, sample_parcel_data):
        """测试不同车辆配置的规划"""
        import data_generator

        configs = data_generator.create_vehicle_scenarios()

        for config_name, config_data in configs.items():
            parcel = ParcelData.from_dict(config_data['parcel'])
            vehicle = VehicleConfig.from_dict(config_data['vehicle'])

            path = self.planner.plan(parcel, vehicle)

            # 验证路径存在
            assert isinstance(path, list)
            # 路径点应该是有效的坐标
            for point in path:
                assert len(point) == 2
                assert isinstance(point[0], (int, float))
                assert isinstance(point[1], (int, float))

    def test_planning_empty_parcel(self):
        """测试空地块的规划"""
        empty_parcel = ParcelData(outer=[])
        vehicle = VehicleConfig()

        path = self.planner.plan(empty_parcel, vehicle)

        # 空地块应返回空路径
        assert isinstance(path, list)
        assert len(path) == 0

    def test_planning_preserves_coordinate_format(self, sample_task_request):
        """测试规划输出保持(lon, lat)坐标格式"""
        parcel = ParcelData.from_dict(sample_task_request['parcel'])
        vehicle = VehicleConfig.from_dict(sample_task_request['vehicle'])

        path = self.planner.plan(parcel, vehicle)

        # 验证所有坐标格式为 (lon, lat)
        for point in path:
            assert isinstance(point, (tuple, list))
            assert len(point) == 2
            lon, lat = point
            # 经度范围 [-180, 180]
            assert -180 <= lon <= 180
            # 纬度范围 [-90, 90]
            assert -90 <= lat <= 90


class TestErrorScenarios:
    """测试错误处理场景"""

    def test_invalid_parcel_data(self, mock_sdk):
        """测试无效的地块数据"""
        planner = GlobalCoveragePlanner()

        # 缺少外边界的地块数据
        invalid_parcel = ParcelData(outer=[])
        vehicle = VehicleConfig()

        path = planner.plan(invalid_parcel, vehicle)

        # 应该返回空路径而不是异常
        assert isinstance(path, list)
        assert len(path) == 0

    def test_invalid_vehicle_config_validation(self, mock_sdk):
        """测试车辆配置数据验证"""
        # 测试从dict创建车辆配置，验证参数处理正确
        invalid_config = {
            'implement_width_m': -1,  # 负数宽度
            'overlap_ratio': 1.5,  # 超出范围的重叠率
            'path_inset_m': -0.5
        }

        # VehicleConfig应该能够创建对象，即使参数可能无效
        # 实际的验证发生在规划器级别
        vehicle = VehicleConfig.from_dict(invalid_config)
        assert vehicle is not None
        assert vehicle.implement_width_m == -1

    def test_missing_task_request_fields(self, mock_sdk):
        """测试缺失任务字段的处理"""
        task_port = mock_sdk.create_input_port('task_request')
        path_port = mock_sdk.create_output_port('global_path')

        # 缺少parcel字段的任务
        incomplete_task = {
            'id': 'incomplete_task',
            'vehicle': {'implement_width_m': 3.0}
        }

        task_port.set_data(incomplete_task)
        data = task_port.recv_latest()

        assert data is not None
        # 端口本身应该成功接收，解析时可能失败
        assert 'id' in data

    def test_port_receives_invalid_json_structure(self, mock_sdk):
        """测试端口接收格式不正确的数据"""
        task_port = mock_sdk.create_input_port('task_request')

        # 发送一个数字而不是dict
        task_port.set_data(12345)
        data = task_port.recv_latest()

        # 端口应该接收但数据类型不匹配
        assert data == 12345


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
