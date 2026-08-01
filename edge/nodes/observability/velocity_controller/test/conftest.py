"""
pytest配置文件 - velocity_controller 节点测试

提供fixtures和测试环境配置

使用方法：
    fixtures会自动被pytest加载，在测试函数中使用即可
    def test_something(mock_sdk, temp_output_dir):
        ...
"""

import sys
import json
from pathlib import Path
from typing import Dict, Any

# 添加节点目录到路径，用于导入节点代码
node_dir = Path(__file__).parent.parent
sys.path.insert(0, str(node_dir))

# 添加项目根路径
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

import pytest

# velocity_controller节点的SDK参数
DEFAULT_MOCK_SDK_PARAMS = {
    "output_dir": "/tmp/nodeflow_test",
    "timeout": 300.0,
    "update_interval": 10.0,
    # 控制参数
    "max_speed": 1.0,
    "min_speed": 0.2,
    "lookahead_distance": 2.0,
    "goal_tolerance": 0.3,
    "heading_p_gain": 2.0,
    "max_angular_velocity": 1.0,
    "control_frequency": 20,
    "enable_control": True,
}


@pytest.fixture
def fixture_dir():
    """
    返回fixtures目录路径

    使用方法：
        def test_something(fixture_dir):
            fixture_path = fixture_dir / 'sample_input.json'
    """
    return Path(__file__).parent / "fixtures"


@pytest.fixture
def load_fixture():
    """
    加载JSON fixture文件

    使用方法：
        def test_something(load_fixture):
            data = load_fixture('sample_input.json')
            assert data['key'] == 'value'
    """
    def _load(filename: str) -> Dict[str, Any]:
        fixture_path = Path(__file__).parent / "fixtures" / filename
        if not fixture_path.exists():
            raise FileNotFoundError(f"Fixture file not found: {fixture_path}")

        with open(fixture_path, 'r', encoding='utf-8') as f:
            return json.load(f)

    return _load


# ============ Mock SDK Fixtures ============

@pytest.fixture
def mock_sdk():
    """
    创建Mock SDK实例

    TODO: 如需自定义参数，使用 mock_sdk_with_params fixture

    使用方法：
        def test_something(mock_sdk):
            port = mock_sdk.create_input_port('input')
            port.set_data({'test': 'data'})
    """
    from edge.sdk.test_utils import MockNodeFlowSDK

    sdk = MockNodeFlowSDK()
    yield sdk
    sdk.reset()


@pytest.fixture
def mock_sdk_with_params():
    """
    创建带默认参数的Mock SDK

    参数来自 DEFAULT_MOCK_SDK_PARAMS

    TODO: 如需自定义参数，修改该fixture或在test中直接设置
    """
    from edge.sdk.test_utils import MockNodeFlowSDK

    sdk = MockNodeFlowSDK(DEFAULT_MOCK_SDK_PARAMS)
    yield sdk
    sdk.reset()


@pytest.fixture
def temp_output_dir(tmp_path):
    """
    创建临时输出目录

    自动清理（由pytest的tmp_path管理）

    使用方法：
        def test_something(temp_output_dir):
            output_file = temp_output_dir / 'output.jpg'
            # ... 生成文件 ...
            assert output_file.exists()
    """
    output_dir = tmp_path / "output"
    output_dir.mkdir(exist_ok=True)
    return output_dir


# ============ 测试数据Fixtures ============

@pytest.fixture
def sample_rtk_data():
    """生成样本RTK GPS数据"""
    from edge.sdk.test_utils.test_constants import SHANGHAI_CENTER
    return {
        "latitude": SHANGHAI_CENTER[0],
        "longitude": SHANGHAI_CENTER[1],
        "altitude": 10.0,
        "rtk_status": "FIXED",
        "timestamp": 1234567890.0
    }

@pytest.fixture
def sample_path_data():
    """生成样本路径数据"""
    from edge.sdk.test_utils.test_constants import SHANGHAI_CENTER
    lat_center, lon_center = SHANGHAI_CENTER
    return {
        "task_id": "test_path_001",
        "waypoints": [
            (lon_center, lat_center),
            (lon_center + 0.0001, lat_center),
            (lon_center + 0.0002, lat_center),
            (lon_center + 0.0003, lat_center),
        ]
    }


# ============ pytest配置钩子 ============

def pytest_configure(config):
    """pytest初始化钩子"""
    config.addinivalue_line(
        "markers",
        "unit: 单元测试（快速，无外部依赖）"
    )
    config.addinivalue_line(
        "markers",
        "integration: 集成测试（涉及SDK交互）"
    )
    config.addinivalue_line(
        "markers",
        "slow: 慢速测试（可选运行）"
    )


def pytest_collection_modifyitems(config, items):
    """自动标记测试"""
    for item in items:
        if "test_unit" in item.nodeid:
            item.add_marker(pytest.mark.unit)
        elif "test_integration" in item.nodeid:
            item.add_marker(pytest.mark.integration)


# velocity_controller不使用matplotlib，删除了reset_matplotlib fixture
