"""
NodeFlow SDK Mock Fixtures - pytest集成

提供可复用的pytest fixtures用于节点测试：
- mock_sdk: Mock SDK实例
- mock_port: Mock端口
- temp_output_dir: 临时输出目录

使用方法：
```python
import pytest
from sdk.test_utils.mock_fixtures import mock_sdk

def test_my_node(mock_sdk):
    # mock_sdk是预配置的MockNodeFlowSDK实例
    port = mock_sdk.create_input_port('input')
    port.set_data({'key': 'value'})
    ...
```
"""

import pytest
import tempfile
from pathlib import Path
from typing import Dict, Any, Optional

from sdk.test_utils.mock_sdk import MockNodeFlowSDK, MockPort, create_mock_sdk_with_data


@pytest.fixture
def mock_sdk() -> MockNodeFlowSDK:
    """
    创建Mock SDK fixture

    返回：
    - 预初始化的MockNodeFlowSDK实例

    使用示例：
    ```python
    def test_something(mock_sdk):
        input_port = mock_sdk.create_input_port('my_input')
        input_port.set_data({'test': 'data'})
        assert input_port.recv_latest() == {'test': 'data'}
    ```
    """
    sdk = MockNodeFlowSDK()
    yield sdk
    # 清理
    sdk.reset()


@pytest.fixture
def mock_sdk_with_params() -> MockNodeFlowSDK:
    """
    创建带有默认参数的Mock SDK

    默认参数：
    - output_dir: 临时目录
    - timeout: 300
    - update_interval: 10

    返回：
    - 预配置的MockNodeFlowSDK实例
    """
    params = {
        'output_dir': tempfile.gettempdir(),
        'timeout': 300.0,
        'update_interval': 10.0
    }
    sdk = MockNodeFlowSDK(params)
    yield sdk
    sdk.reset()


@pytest.fixture
def temp_output_dir(tmp_path) -> Path:
    """
    创建临时输出目录

    使用pytest的tmp_path fixture，自动清理

    返回：
    - Path对象，指向临时目录

    使用示例：
    ```python
    def test_output_files(temp_output_dir):
        output_file = temp_output_dir / 'output.txt'
        output_file.write_text('test')
        assert output_file.exists()
    ```
    """
    output_dir = tmp_path / "output"
    output_dir.mkdir(exist_ok=True)
    return output_dir


@pytest.fixture
def mock_port(mock_sdk) -> MockPort:
    """
    创建Mock端口fixture

    返回：
    - 已添加到SDK中的MockPort实例

    使用示例：
    ```python
    def test_port(mock_port):
        mock_port.set_data({'key': 'value'})
        data = mock_port.recv_latest()
        assert data == {'key': 'value'}
    ```
    """
    port = mock_sdk.create_input_port('test_port')
    return port


@pytest.fixture
def make_mock_sdk():
    """
    工厂fixture - 创建多个Mock SDK实例

    返回：
    - 可调用的函数，用于创建新的MockNodeFlowSDK实例

    使用示例：
    ```python
    def test_multiple_sdks(make_mock_sdk):
        sdk1 = make_mock_sdk()
        sdk2 = make_mock_sdk({'param': 'value'})

        port1 = sdk1.create_input_port('port1')
        port2 = sdk2.create_input_port('port2')
    ```
    """
    sdks = []

    def _make_sdk(params: Optional[Dict[str, Any]] = None) -> MockNodeFlowSDK:
        sdk = MockNodeFlowSDK(params)
        sdks.append(sdk)
        return sdk

    yield _make_sdk

    # 清理所有创建的SDK
    for sdk in sdks:
        sdk.reset()


# 便利函数


def assert_port_send_called(port: MockPort, count: Optional[int] = None) -> bool:
    """
    检查端口send是否被调用

    参数：
    - port: Mock端口
    - count: 预期调用次数（可选）

    返回：
    - True: 调用了，False: 没有调用

    异常：
    - AssertionError: 调用次数与预期不符

    使用示例：
    ```python
    output_port = sdk.create_output_port('output')
    output_port.send({'result': 'data'})
    assert_port_send_called(output_port, count=1)
    ```
    """
    send_calls = port.get_send_calls()

    if count is None:
        # 只检查是否被调用
        return len(send_calls) > 0
    else:
        # 检查调用次数
        actual_count = len(send_calls)
        assert actual_count == count, (
            f"Expected port '{port.name}' to be sent {count} times, "
            f"but it was sent {actual_count} times"
        )
        return True


def assert_port_recv_called(port: MockPort, count: Optional[int] = None) -> bool:
    """
    检查端口recv_latest是否被调用

    参数：
    - port: Mock端口
    - count: 预期调用次数（可选）

    返回：
    - True: 调用了，False: 没有调用

    异常：
    - AssertionError: 调用次数与预期不符

    使用示例：
    ```python
    input_port = sdk.create_input_port('input')
    input_port.set_data({'data': 'value'})
    input_port.recv_latest()
    assert_port_recv_called(input_port, count=1)
    ```
    """
    recv_count = port.get_receive_count()

    if count is None:
        # 只检查是否被调用
        return recv_count > 0
    else:
        # 检查调用次数
        assert recv_count == count, (
            f"Expected port '{port.name}' recv_latest to be called {count} times, "
            f"but it was called {recv_count} times"
        )
        return True


def get_mock_sdk_state(sdk: MockNodeFlowSDK) -> Dict[str, Any]:
    """
    获取Mock SDK的完整状态

    用于调试和断言

    参数：
    - sdk: MockNodeFlowSDK实例

    返回：
    - 状态字典，包含：
        - inputs: 输入端口及其数据
        - outputs: 输出端口及其send调用
        - params: 所有参数

    使用示例：
    ```python
    state = get_mock_sdk_state(sdk)
    print(state['inputs'])
    print(state['outputs'])
    ```
    """
    return {
        'inputs': {
            name: {
                'latest_data': port._latest_data,
                'receive_count': port.get_receive_count(),
                'type': port.port_type
            }
            for name, port in sdk.inputs.items()
        },
        'outputs': {
            name: {
                'send_calls': port.get_send_calls(),
                'type': port.port_type
            }
            for name, port in sdk.outputs.items()
        },
        'params': sdk.params._params
    }
