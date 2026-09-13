"""
pytest配置文件 - global_coverage 节点测试

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

# TODO: 如需自定义SDK参数，修改下面的字典
DEFAULT_MOCK_SDK_PARAMS = {
    "output_dir": "/tmp/nodeflow_test",
    "timeout": 300.0,
    "update_interval": 10.0,
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
    from nodeflow_test_support.mock_nodeflow_sdk import MockNodeFlowSDK

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
    from nodeflow_test_support.mock_nodeflow_sdk import MockNodeFlowSDK

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
def sample_vehicle_config():
    """生成样本车辆配置"""
    return {
        "implement_width_m": 3.0,
        "overlap_ratio": 0.1,
        "path_inset_m": 1.0,
        "pivot_turn": True,
        "yaw_rate_max_deg_s": 60.0
    }

@pytest.fixture
def sample_parcel_data():
    """生成样本地块数据（矩形）"""
    from nodeflow_test_support.mock_nodeflow_sdk import SHANGHAI_CENTER
    lat_center, lon_center = SHANGHAI_CENTER

    # 创建一个约100m x 50m的矩形地块
    return {
        "outer": [
            (lon_center, lat_center),
            (lon_center + 0.001, lat_center),
            (lon_center + 0.001, lat_center + 0.0005),
            (lon_center, lat_center + 0.0005),
        ],
        "holes": [],
        "points": [],
        "entries": []
    }

@pytest.fixture
def sample_task_request(sample_parcel_data, sample_vehicle_config):
    """生成完整的任务请求"""
    return {
        "id": "test_task_001",
        "parcel": sample_parcel_data,
        "vehicle": sample_vehicle_config
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


# global_coverage不使用matplotlib，删除了reset_matplotlib fixture
