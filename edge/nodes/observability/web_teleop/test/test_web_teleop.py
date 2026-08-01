#!/usr/bin/env python3
"""
Web Teleop 单元测试

测试内容：
1. API 端点处理
2. 速度限制
3. 控制命令处理
4. 状态反馈
"""

import sys
import os
import json
import time
from pathlib import Path

# 添加项目根路径
test_dir = Path(__file__).parent
node_dir = test_dir.parent
sys.path.insert(0, str(node_dir))

import pytest
from unittest.mock import Mock, MagicMock, patch
from http.server import BaseHTTPRequestHandler
from io import BytesIO


# ========== 导入被测模块 ==========
# 模拟 SDK 环境
class MockSDK:
    class Logger:
        def info(self, msg): pass
        def warning(self, msg): pass
        def error(self, msg): pass
        def debug(self, msg): pass

    logger = Logger()

    def __init__(self):
        self.params = {}
        self.ports = {}

    def get_param(self, key, default=None):
        return self.params.get(key, default)

    def set_param(self, key, value):
        self.params[key] = value

    def create_input_port(self, port_name):
        port = Mock()
        port.recv_latest = Mock(return_value=None)
        self.ports[port_name] = port
        return port

    def create_output_port(self, port_name):
        port = Mock()
        port.send = Mock()
        self.ports[port_name] = port
        return port


# Mock SDK 模块
sys.modules['sdk'] = MagicMock()
sys.modules['sdk.nodeflow_sdk'] = MagicMock()
sys.modules['sdk.nodeflow_sdk'].NodeFlowSDK = MockSDK

# 导入被测代码
import run
run.TeleopHandler.node_instance = None


# ========== 测试工具函数 ==========
class MockRequest:
    """模拟 HTTP 请求"""

    def __init__(self, method, path, body=None):
        self.method = method
        self.path = path
        self.body = body

    def make_handler(self):
        """创建模拟的请求处理器"""
        handler = Mock()
        handler.method = self.method
        handler.path = self.path
        handler.headers = {'Content-Length': str(len(self.body)) if self.body else 0}
        handler.rfile = BytesIO(self.body) if self.body else BytesIO()
        handler.wfile = BytesIO()
        handler.send_response = Mock()
        handler.send_header = Mock()
        handler.end_headers = Mock()
        return handler


class TestSpeedLimits:
    """测试速度限制"""

    @pytest.fixture
    def node(self):
        """创建节点实例"""
        sdk = MockSDK()
        sdk.params = {
            'http_host': '0.0.0.0',
            'http_port': 9873,
            'max_linear_speed': 1.0,
            'max_angular_speed': 1.0,
            'continuous_output': True,
            'output_rate': 10.0,
            'require_stop_on_disconnect': False,
            'command_timeout': 5.0,
        }

        # 模拟 HTTP 服务器
        with patch('run.ThreadedHTTPServer'):
            with patch('run.threading.Thread'):
                node = run.WebTeleopNode(sdk)
                return node

    def test_set_velocity_within_limits(self, node):
        """测试设置速度在限制范围内"""
        node.set_velocity(0.5, 0.3)

        assert node.current_linear == 0.5
        assert node.current_angular == 0.3

    def test_set_velocity_exceeds_max_linear(self, node):
        """测试超过最大线速度时被限制"""
        node.set_velocity(2.0, 0.0)  # 超过 max_linear_speed (1.0)

        assert node.current_linear == 1.0  # 应该被限制
        assert node.current_angular == 0.0

    def test_set_velocity_exceeds_max_angular(self, node):
        """测试超过最大角速度时被限制"""
        node.set_velocity(0.0, 2.0)  # 超过 max_angular_speed (1.0)

        assert node.current_linear == 0.0
        assert node.current_angular == 1.0  # 应该被限制

    def test_set_velocity_negative_within_limits(self, node):
        """测试负向速度在限制范围内"""
        node.set_velocity(-0.5, -0.3)

        assert node.current_linear == -0.5
        assert node.current_angular == -0.3

    def test_set_velocity_negative_exceeds_limits(self, node):
        """测试负向速度超过限制时被限制"""
        node.set_velocity(-2.0, -2.0)

        assert node.current_linear == -1.0
        assert node.current_angular == -1.0

    def test_send_velocity_command(self, node):
        """测试发送速度命令"""
        node.set_velocity(0.5, 0.3)

        # 检查是否调用了 send
        node.velocity_cmd_port.send.assert_called()

        # 获取发送的命令
        call_args = node.velocity_cmd_port.send.call_args
        cmd = call_args[0][0]

        assert cmd['linear_velocity'] == 0.5
        assert cmd['angular_velocity'] == 0.3
        assert 'timestamp' in cmd


class TestStatusAPI:
    """测试状态 API"""

    @pytest.fixture
    def node(self):
        """创建节点实例"""
        sdk = MockSDK()
        sdk.params = {
            'http_host': '0.0.0.0',
            'http_port': 9873,
            'max_linear_speed': 1.0,
            'max_angular_speed': 1.0,
            'continuous_output': False,
            'output_rate': 10.0,
            'require_stop_on_disconnect': False,
            'command_timeout': 5.0,
        }

        with patch('run.ThreadedHTTPServer'):
            with patch('run.threading.Thread'):
                node = run.WebTeleopNode(sdk)
                return node

    def test_get_status_zero_velocity(self, node):
        """测试零速度状态"""
        node.current_linear = 0.0
        node.current_angular = 0.0
        node.feedback_linear = 0.0
        node.feedback_angular = 0.0

        status = node.get_status()

        assert status['command']['linear_velocity'] == 0.0
        assert status['command']['angular_velocity'] == 0.0
        assert status['feedback']['linear_velocity'] == 0.0
        assert status['feedback']['angular_velocity'] == 0.0
        assert status['limits']['max_linear_speed'] == 1.0
        assert status['limits']['max_angular_speed'] == 1.0

    def test_get_status_with_velocity(self, node):
        """测试有速度时的状态"""
        node.current_linear = 0.5
        node.current_angular = 0.3
        node.feedback_linear = 0.48
        node.feedback_angular = 0.29

        status = node.get_status()

        assert status['command']['linear_velocity'] == 0.5
        assert status['command']['angular_velocity'] == 0.3
        assert status['feedback']['linear_velocity'] == 0.48
        assert status['feedback']['angular_velocity'] == 0.29

    def test_get_status_includes_limits(self, node):
        """测试状态包含限制信息"""
        node.max_linear_speed = 2.0
        node.max_angular_speed = 1.5

        status = node.get_status()

        assert status['limits']['max_linear_speed'] == 2.0
        assert status['limits']['max_angular_speed'] == 1.5


class TestControlCommand:
    """测试控制命令处理"""

    @pytest.fixture
    def node(self):
        """创建节点实例"""
        sdk = MockSDK()
        sdk.params = {
            'http_host': '0.0.0.0',
            'http_port': 9873,
            'max_linear_speed': 1.0,
            'max_angular_speed': 1.0,
            'continuous_output': False,
            'output_rate': 10.0,
            'require_stop_on_disconnect': False,
            'command_timeout': 5.0,
        }

        with patch('run.ThreadedHTTPServer'):
            with patch('run.threading.Thread'):
                node = run.WebTeleopNode(sdk)
                return node

    def test_control_command_forward(self, node):
        """测试前进命令"""
        node.set_velocity(1.0, 0.0)

        assert node.current_linear == 1.0
        assert node.current_angular == 0.0

    def test_control_command_backward(self, node):
        """测试后退命令"""
        node.set_velocity(-1.0, 0.0)

        assert node.current_linear == -1.0
        assert node.current_angular == 0.0

    def test_control_command_turn_left(self, node):
        """测试左转命令"""
        node.set_velocity(0.0, 1.0)

        assert node.current_linear == 0.0
        assert node.current_angular == 1.0

    def test_control_command_turn_right(self, node):
        """测试右转命令"""
        node.set_velocity(0.0, -1.0)

        assert node.current_linear == 0.0
        assert node.current_angular == -1.0

    def test_control_command_forward_left(self, node):
        """测试前进左转（复合命令）"""
        node.set_velocity(0.5, 0.5)

        assert node.current_linear == 0.5
        assert node.current_angular == 0.5

    def test_control_command_stop(self, node):
        """测试停止命令"""
        node.set_velocity(0.5, 0.3)
        assert node.current_linear != 0.0

        node.set_velocity(0.0, 0.0)

        assert node.current_linear == 0.0
        assert node.current_angular == 0.0


class TestTimeoutBehavior:
    """测试超时行为"""

    @pytest.fixture
    def node(self):
        """创建节点实例"""
        sdk = MockSDK()
        sdk.params = {
            'http_host': '0.0.0.0',
            'http_port': 9873,
            'max_linear_speed': 1.0,
            'max_angular_speed': 1.0,
            'continuous_output': True,
            'output_rate': 10.0,
            'require_stop_on_disconnect': False,
            'command_timeout': 0.5,  # 短超时用于测试
        }

        with patch('run.ThreadedHTTPServer'):
            with patch('run.threading.Thread'):
                node = run.WebTeleopNode(sdk)
                return node

    def test_timeout_no_auto_stop_before_timeout(self, node):
        """测试超时前不自动停止"""
        node.set_velocity(0.5, 0.0)
        assert node.current_linear == 0.5

        # 超时时间未到，不应该停止
        time_since = time.time() - node.last_command_time
        assert time_since < node.command_timeout

    def test_timeout_updates_on_new_command(self, node):
        """测试新命令更新超时时间"""
        node.set_velocity(0.5, 0.0)
        first_time = node.last_command_time

        time.sleep(0.1)
        node.set_velocity(0.3, 0.0)

        assert node.last_command_time > first_time


class TestJSONEncoding:
    """测试 JSON 编码/解码"""

    def test_status_json_serializable(self):
        """测试状态可以序列化为 JSON"""
        sdk = MockSDK()
        sdk.params = {
            'http_host': '0.0.0.0',
            'http_port': 9873,
            'max_linear_speed': 1.0,
            'max_angular_speed': 1.0,
            'continuous_output': False,
            'output_rate': 10.0,
            'require_stop_on_disconnect': False,
            'command_timeout': 5.0,
        }

        with patch('run.ThreadedHTTPServer'):
            with patch('run.threading.Thread'):
                node = run.WebTeleopNode(sdk)
                node.current_linear = 0.5
                node.current_angular = 0.3

                status = node.get_status()

                # 应该可以序列化为 JSON
                json_str = json.dumps(status)
                assert json_str is not None

                # 反序列化后值应该相同
                parsed = json.loads(json_str)
                assert parsed['command']['linear_velocity'] == 0.5


# ========== 运行测试 ==========
if __name__ == "__main__":
    # 直接运行此文件执行测试
    pytest.main([__file__, "-v", "--tb=short"])
