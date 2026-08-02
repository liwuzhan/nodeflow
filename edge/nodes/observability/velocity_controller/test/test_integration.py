"""
集成测试 - velocity_controller节点

测试Pure Pursuit控制器与SDK的交互
"""

import sys
from pathlib import Path

# 添加节点目录到路径
node_dir = Path(__file__).parent.parent
sys.path.insert(0, str(node_dir))

import pytest
from edge.nodes.observability.velocity_controller.run import PurePursuitController


class TestVelocityControllerWithSDK:
    """测试velocity_controller与SDK的交互"""

    @pytest.fixture(autouse=True)
    def setup(self, mock_sdk):
        """测试前的SDK设置"""
        self.sdk = mock_sdk
        self.controller = PurePursuitController(
            max_speed=self.sdk.params.get('max_speed', 1.0),
            min_speed=self.sdk.params.get('min_speed', 0.2),
            lookahead=self.sdk.params.get('lookahead_distance', 2.0),
            heading_gain=self.sdk.params.get('heading_p_gain', 2.0),
            max_angular_vel=self.sdk.params.get('max_angular_velocity', 1.0),
            goal_tolerance=self.sdk.params.get('goal_tolerance', 0.3)
        )

    def test_reads_parameters_from_sdk(self, mock_sdk_with_params):
        """测试从SDK正确读取参数"""
        max_speed = mock_sdk_with_params.params.get('max_speed')
        min_speed = mock_sdk_with_params.params.get('min_speed')
        lookahead = mock_sdk_with_params.params.get('lookahead_distance')

        assert max_speed == 1.0
        assert min_speed == 0.2
        assert lookahead == 2.0

    def test_receives_rtk_data_from_port(self, sample_rtk_data):
        """测试从输入端口接收RTK数据"""
        rtk_port = self.sdk.create_input_port('rtk_fix')
        rtk_port.set_data(sample_rtk_data)

        data = rtk_port.recv_latest()
        assert data is not None
        assert data['latitude'] == sample_rtk_data['latitude']
        assert data['longitude'] == sample_rtk_data['longitude']
        assert data['rtk_status'] == 'FIXED'

    def test_receives_path_data_from_port(self, sample_path_data):
        """测试从输入端口接收路径数据"""
        path_port = self.sdk.create_input_port('global_path')
        path_port.set_data(sample_path_data)

        data = path_port.recv_latest()
        assert data is not None
        assert 'waypoints' in data
        assert len(data['waypoints']) > 0

    def test_sends_velocity_command_to_port(self, sample_rtk_data, sample_path_data):
        """测试向输出端口发送速度命令"""
        # 设置路径
        self.controller.set_path(sample_path_data['waypoints'], sample_path_data['task_id'])

        # 计算控制命令
        cmd = self.controller.compute_control(sample_rtk_data)

        # 发送到输出端口
        cmd_port = self.sdk.create_output_port('velocity_cmd')
        cmd_port.send(cmd)

        # 验证发送的数据
        sent_data = cmd_port.get_last_send_data()
        assert sent_data is not None
        assert 'linear_velocity' in sent_data
        assert 'angular_velocity' in sent_data
        assert 'timestamp' in sent_data

    def test_full_control_pipeline(self, sample_rtk_data, sample_path_data):
        """测试完整的控制流水线：RTK输入 -> 控制计算 -> 速度输出"""
        # 创建端口
        rtk_port = self.sdk.create_input_port('rtk_fix')
        path_port = self.sdk.create_input_port('global_path')
        cmd_port = self.sdk.create_output_port('velocity_cmd')

        # 接收路径
        path_port.set_data(sample_path_data)
        path_data = path_port.recv_latest()
        self.controller.set_path(path_data['waypoints'], path_data['task_id'])

        # 接收RTK数据
        rtk_port.set_data(sample_rtk_data)
        rtk_data = rtk_port.recv_latest()

        # 计算控制命令
        cmd = self.controller.compute_control(rtk_data)

        # 发送命令
        cmd_port.send(cmd)

        # 验证完整流程
        assert cmd is not None
        sent_data = cmd_port.get_last_send_data()
        assert sent_data is not None
        assert sent_data['linear_velocity'] >= 0
        assert abs(sent_data['angular_velocity']) <= self.controller.max_angular_velocity

    def test_handles_no_rtk_data(self):
        """测试处理无RTK数据的情况"""
        rtk_port = self.sdk.create_input_port('rtk_fix')
        cmd_port = self.sdk.create_output_port('velocity_cmd')

        # 没有设置数据，端口为空
        rtk_data = rtk_port.recv_latest()  # 返回None

        # 计算控制命令（应该返回零速度）
        cmd = self.controller.compute_control(rtk_data)
        cmd_port.send(cmd)

        assert cmd['linear_velocity'] == 0.0
        assert cmd['angular_velocity'] == 0.0

    def test_parameter_changes(self):
        """测试参数变更"""
        # 修改参数
        self.sdk.params.set('max_speed', 2.0)
        self.sdk.params.set('lookahead_distance', 3.0)

        # 创建新控制器读取新参数
        new_controller = PurePursuitController(
            max_speed=self.sdk.params.get('max_speed'),
            lookahead=self.sdk.params.get('lookahead_distance')
        )

        assert new_controller.max_speed == 2.0
        assert new_controller.lookahead_distance == 3.0


class TestMultiplePathUpdates:
    """测试多次路径更新场景"""

    @pytest.fixture(autouse=True)
    def setup(self, mock_sdk):
        """测试前的SDK设置"""
        self.sdk = mock_sdk
        self.controller = PurePursuitController()

    def test_path_update_workflow(self, sample_path_data, sample_rtk_data):
        """测试路径更新工作流"""
        path_port = self.sdk.create_input_port('global_path')
        cmd_port = self.sdk.create_output_port('velocity_cmd')

        # 第一条路径
        path_port.set_data(sample_path_data)
        path1 = path_port.recv_latest()
        self.controller.set_path(path1['waypoints'], path1['task_id'])

        cmd1 = self.controller.compute_control(sample_rtk_data)
        cmd_port.send(cmd1)

        # 验证第一条路径的命令
        sent_data1 = cmd_port.get_last_send_data()
        assert sent_data1 is not None
        assert sent_data1['linear_velocity'] > 0

        # 更新为新路径
        new_path_data = {
            'task_id': 'new_path_002',
            'waypoints': [(121.5, 31.25), (121.51, 31.25)]
        }
        path_port.set_data(new_path_data)
        path2 = path_port.recv_latest()
        self.controller.set_path(path2['waypoints'], path2['task_id'])

        cmd2 = self.controller.compute_control(sample_rtk_data)
        cmd_port.send(cmd2)

        # 验证新路径的命令
        sent_data2 = cmd_port.get_last_send_data()
        assert sent_data2 is not None
        assert self.controller.current_task_id == 'new_path_002'


class TestErrorScenarios:
    """测试错误场景处理"""

    def test_invalid_rtk_data(self, mock_sdk):
        """测试无效RTK数据"""
        controller = PurePursuitController()

        # 缺失关键字段的RTK数据
        invalid_rtk = {"rtk_status": "FIXED"}  # 缺少latitude/longitude

        cmd = controller.compute_control(invalid_rtk)

        # 应该返回零速度
        assert cmd['linear_velocity'] == 0.0
        assert cmd['angular_velocity'] == 0.0

    def test_empty_path(self, mock_sdk, sample_rtk_data):
        """测试空路径"""
        controller = PurePursuitController()
        controller.set_path([])  # 空路径

        cmd = controller.compute_control(sample_rtk_data)

        # 无路径应该返回零速度
        assert cmd['linear_velocity'] == 0.0
        assert cmd['angular_velocity'] == 0.0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
