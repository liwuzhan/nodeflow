"""
集成测试 - <your_node>节点

测试节点与SDK的交互，包括端口通信、参数读取、输出发送等

TODO: 修改测试类名和测试方法以适配你的节点
"""

import sys
from pathlib import Path

# 添加节点目录到路径
node_dir = Path(__file__).parent.parent
sys.path.insert(0, str(node_dir))

import pytest


class TestNodeWithSDK:
    """
    TODO: 重命名此类为你的节点名称 + SDK交互测试

    例如：TestTrajectoryVisualizerWithSDK, TestVelocityControllerWithSDK等

    这个测试类测试节点与SDK的交互，包括：
    - 从输入端口接收数据
    - 读取节点参数
    - 处理数据
    - 向输出端口发送结果
    """

    @pytest.fixture(autouse=True)
    def setup(self, mock_sdk):
        """
        测试前的SDK设置

        TODO: 如果需要初始化SDK相关的对象，在这里进行

        参数:
            mock_sdk: pytest fixture，提供MockNodeFlowSDK实例
        """
        self.sdk = mock_sdk
        # TODO: 如果需要创建你的节点实例，在这里进行
        # from run import MyNodeClass
        # self.node = MyNodeClass(self.sdk)

    def test_receives_input_and_sends_output(self):
        """
        TODO: 测试基本的输入-处理-输出流程

        这是集成测试的核心：验证节点能够通过SDK正确地接收输入和发送输出

        示例：
        def test_receives_input_and_sends_output(self):
            # 1. 准备输入端口和数据
            input_port = self.sdk.create_input_port('input')
            input_data = {'task_id': 'test_001', 'data': [...]}
            input_port.set_data(input_data)

            # 2. 准备输出端口
            output_port = self.sdk.create_output_port('output')

            # 3. 运行节点的主处理函数
            self.node.process(input_port, output_port)

            # 4. 验证输出
            output_data = output_port.get_data()
            assert output_data is not None
            assert output_data['result'] == 'expected_value'
        """
        pass  # TODO: 修改为实际测试

    def test_reads_parameters(self):
        """
        TODO: 测试节点是否正确读取参数

        验证节点能够从SDK获取配置参数

        示例：
        def test_reads_parameters(self):
            # 1. 设置参数
            self.sdk.params.set('threshold', 0.5)
            self.sdk.params.set('mode', 'fast')

            # 2. 调用节点代码获取参数
            threshold = self.sdk.params.get('threshold')
            mode = self.sdk.params.get('mode')

            # 3. 验证参数值
            assert threshold == 0.5
            assert mode == 'fast'
        """
        pass  # TODO: 修改为实际测试

    def test_handles_sdk_exceptions(self):
        """
        TODO: 测试节点对SDK异常的处理

        验证节点在端口或参数出错时的行为

        示例：
        def test_handles_sdk_exceptions(self):
            # 测试端口不存在时的处理
            with pytest.raises(Exception):  # TODO: 修改为具体异常类型
                self.node.process(non_existent_port)

            # 或测试节点是否优雅地处理异常
            result = self.node.safe_process(invalid_data)
            assert result is None or result['error'] is not None
        """
        pass  # TODO: 修改为实际测试

    @pytest.mark.parametrize("input_data,expected_result", [
        # TODO: 添加多组测试数据
        # 示例：
        # ({'task_id': '001', 'data': [...]}, {'result': 'success'}),
        # ({'task_id': '002', 'data': [...]}, {'result': 'success'}),
    ])
    def test_multiple_input_scenarios(self, input_data, expected_result):
        """
        TODO: 使用parametrize测试多个输入场景

        pytest的@pytest.mark.parametrize装饰器允许用一个测试函数测试多组数据

        示例：
        @pytest.mark.parametrize("task_type,expected_output", [
            ("type_a", "output_a"),
            ("type_b", "output_b"),
        ])
        def test_multiple_input_scenarios(self, task_type, expected_output):
            result = self.node.process({'type': task_type})
            assert result == expected_output
        """
        # TODO: 实现参数化测试
        pass


class TestNodePortInteraction:
    """
    TODO: 添加端口交互测试类

    如果你的节点有多个输入/输出端口或复杂的端口交互，
    添加专门的测试类来验证多端口场景
    """

    def test_multiple_input_ports(self, mock_sdk):
        """
        TODO: 测试多个输入端口的交互

        示例：
        def test_multiple_input_ports(self, mock_sdk):
            # 创建多个输入端口
            port_a = mock_sdk.create_input_port('sensor_data')
            port_b = mock_sdk.create_input_port('config')

            # 设置不同的数据
            port_a.set_data({'sensor': 'imu', 'value': [1, 2, 3]})
            port_b.set_data({'sensitivity': 0.8})

            # 验证节点能够正确处理多端口数据
            result = self.node.process(port_a, port_b)
            assert result['processed'] is True
        """
        pass  # TODO: 修改为实际测试

    def test_output_port_broadcast(self, mock_sdk):
        """
        TODO: 测试向多个输出端口发送数据

        如果节点向多个输出端口发送数据，测试广播功能

        示例：
        def test_output_port_broadcast(self, mock_sdk):
            output_main = mock_sdk.create_output_port('main_output')
            output_debug = mock_sdk.create_output_port('debug_output')

            self.node.process_and_broadcast(input_data, output_main, output_debug)

            assert output_main.data is not None
            assert output_debug.data is not None
        """
        pass  # TODO: 修改为实际测试


class TestNodeWithRealData:
    """
    TODO: 添加真实数据集成测试类

    如果节点处理特定格式的真实数据（GPS、IMU、规划任务等），
    添加使用实际数据格式的集成测试
    """

    def test_with_fixture_data(self, load_fixture):
        """
        TODO: 使用fixture中的真实数据进行测试

        示例：
        def test_with_fixture_data(self, load_fixture):
            # 从fixtures目录加载测试数据
            test_data = load_fixture('sample_input.json')

            # 使用真实数据运行节点
            result = self.node.process(test_data)

            # 验证结果
            assert result is not None
            assert 'output_field' in result
        """
        pass  # TODO: 修改为实际测试

    def test_output_file_generation(self, temp_output_dir):
        """
        TODO: 测试节点是否正确生成输出文件

        如果节点生成文件（图像、日志、数据等），验证文件输出

        示例：
        def test_output_file_generation(self, temp_output_dir):
            self.sdk.params.set('output_dir', str(temp_output_dir))

            # 运行节点
            self.node.process(input_data)

            # 验证文件是否被生成
            output_file = temp_output_dir / 'result.png'
            assert output_file.exists()
            assert output_file.stat().st_size > 0
        """
        pass  # TODO: 修改为实际测试


# TODO: 其他建议
# 1. 集成测试应该测试完整的数据流，从输入到输出
# 2. 使用mock_sdk fixture 来模拟SDK，不依赖真实系统
# 3. 验证节点对错误条件的处理（无效输入、缺失参数等）
# 4. 如果节点与外部系统交互，使用mock来隔离外部依赖
# 5. 使用fixture来管理测试数据和临时资源
#
# 集成测试 vs 单元测试：
# - 单元测试 (test_unit.py): 测试单个函数或类的方法，不涉及SDK
# - 集成测试 (test_integration.py): 测试完整的节点流程，包括SDK交互
#
# 示例：
# 单元测试: test_calculate_distance(lat1, lon1, lat2, lon2) -> float
# 集成测试: test_node_receives_gps_sends_waypoint(input_port, output_port)
