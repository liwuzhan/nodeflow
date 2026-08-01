"""
pytest配置文件 - trajectory_viz节点

提供测试夹具(fixtures)和测试环境配置
"""

import sys
import json
from pathlib import Path
from typing import Dict, Any

# 添加节点目录与项目根路径，确保导入本节点的 run.py
node_dir = Path(__file__).parent.parent
sys.path.insert(0, str(node_dir))
project_root = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(project_root))

import pytest


@pytest.fixture
def fixture_dir():
    """返回测试数据目录"""
    return Path(__file__).parent / "fixtures"


@pytest.fixture
def load_fixture():
    """
    加载JSON fixture文件的辅助函数

    使用方式:
        def test_something(load_fixture):
            data = load_fixture("scenario_basic.json")
    """
    def _load(filename: str) -> Dict[str, Any]:
        fixture_path = Path(__file__).parent / "fixtures" / filename
        if not fixture_path.exists():
            raise FileNotFoundError(f"Fixture file not found: {fixture_path}")

        with open(fixture_path, 'r', encoding='utf-8') as f:
            return json.load(f)

    return _load


@pytest.fixture
def basic_task_request(load_fixture) -> Dict[str, Any]:
    """基础场景的task_request数据"""
    return load_fixture("input_basic_task_request.json")


@pytest.fixture
def basic_global_path(load_fixture) -> Dict[str, Any]:
    """基础场景的global_path数据"""
    return load_fixture("input_basic_global_path.json")


@pytest.fixture
def basic_rtk_trajectory(load_fixture) -> list:
    """基础场景的RTK轨迹数据"""
    return load_fixture("input_basic_rtk_trajectory.json")


@pytest.fixture
def irregular_task_request(load_fixture) -> Dict[str, Any]:
    """不规则场景的task_request数据"""
    return load_fixture("input_irregular_task_request.json")


@pytest.fixture
def irregular_global_path(load_fixture) -> Dict[str, Any]:
    """不规则场景的global_path数据"""
    return load_fixture("input_irregular_global_path.json")


@pytest.fixture
def irregular_rtk_trajectory(load_fixture) -> list:
    """不规则场景的RTK轨迹数据"""
    return load_fixture("input_irregular_rtk_trajectory.json")


@pytest.fixture
def large_task_request(load_fixture) -> Dict[str, Any]:
    """大地块场景的task_request数据"""
    return load_fixture("input_large_task_request.json")


@pytest.fixture
def large_global_path(load_fixture) -> Dict[str, Any]:
    """大地块场景的global_path数据"""
    return load_fixture("input_large_global_path.json")


@pytest.fixture
def large_rtk_trajectory(load_fixture) -> list:
    """大地块场景的RTK轨迹数据"""
    return load_fixture("input_large_rtk_trajectory.json")


@pytest.fixture
def complete_scenario(load_fixture) -> Dict[str, Any]:
    """
    完整的基础场景（包含所有数据）

    返回结构:
    {
        "task_request": {...},
        "global_path": {...},
        "rtk_fixes": [...],
        "field_boundary": [...],
        "planned_path": [...],
        "actual_trajectory": [...]
    }
    """
    return load_fixture("scenario_basic.json")


@pytest.fixture
def temp_output_dir(tmp_path):
    """
    临时输出目录

    用于测试生成的图像文件
    """
    output_dir = tmp_path / "output"
    output_dir.mkdir(exist_ok=True)
    return output_dir


@pytest.fixture(autouse=True)
def reset_matplotlib():
    """
    重置matplotlib状态（每个测试前）

    防止测试间的matplotlib状态污染
    """
    import matplotlib.pyplot as plt

    yield

    # 清理
    plt.close('all')


def pytest_configure(config):
    """
    pytest初始化钩子
    """
    config.addinivalue_line(
        "markers",
        "unit: mark test as a unit test (fast, no external dependencies)"
    )
    config.addinivalue_line(
        "markers",
        "integration: mark test as an integration test (requires SDK/ports)"
    )
    config.addinivalue_line(
        "markers",
        "visualization: mark test as a visualization test (generates images)"
    )


def pytest_collection_modifyitems(config, items):
    """
    修改收集到的测试项
    """
    for item in items:
        # 根据文件名自动标记测试
        if "test_unit" in item.nodeid:
            item.add_marker(pytest.mark.unit)
        elif "test_integration" in item.nodeid:
            item.add_marker(pytest.mark.integration)
        elif "test_visualization" in item.nodeid:
            item.add_marker(pytest.mark.visualization)
