"""
NodeFlow SDK 测试工具库

提供Mock对象和fixtures用于节点的单元测试和集成测试

主要导出：
- MockNodeFlowSDK: 完整的SDK模拟
- MockPort: 端口模拟
- MockParams: 参数容器
- Mock fixtures: pytest集成
- 测试常量

使用示例：

```python
# 导入Mock对象
from sdk.test_utils import MockNodeFlowSDK, MockPort

# 导入fixtures
from sdk.test_utils.mock_fixtures import mock_sdk, temp_output_dir

# 导入常量
from sdk.test_utils import TEST_CONSTANTS

# 在测试中使用
def test_my_node(mock_sdk):
    # mock_sdk是预配置的MockNodeFlowSDK实例
    port = mock_sdk.create_input_port('input')
    port.set_data({'key': 'value'})

    # 运行你的节点代码
    assert port.recv_latest() == {'key': 'value'}
```
"""

__version__ = "1.0.0"

# Mock核心类
from sdk.test_utils.mock_sdk import (
    MockNodeFlowSDK,
    MockPort,
    MockParams,
    create_mock_sdk_with_data,
)

# Fixtures (lazy import to avoid pytest dependency for non-test usage)
from sdk.test_utils.mock_fixtures import (
    assert_port_send_called,
    assert_port_recv_called,
    get_mock_sdk_state,
)

# 常量
from sdk.test_utils.test_constants import (
    TestConstants,
    TEST_CONSTANTS,
    SHANGHAI_CENTER,
    BEIJING_CENTER,
    DEFAULT_TEST_PARAMS,
)

__all__ = [
    # Mock类
    "MockNodeFlowSDK",
    "MockPort",
    "MockParams",
    "create_mock_sdk_with_data",

    # 便利函数
    "assert_port_send_called",
    "assert_port_recv_called",
    "get_mock_sdk_state",

    # 常量
    "TestConstants",
    "TEST_CONSTANTS",
    "SHANGHAI_CENTER",
    "BEIJING_CENTER",
    "DEFAULT_TEST_PARAMS",
]

# 版本信息
def get_version() -> str:
    """获取工具库版本"""
    return __version__
