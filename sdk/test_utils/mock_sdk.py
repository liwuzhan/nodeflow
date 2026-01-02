"""
NodeFlow SDK Mock实现 - 用于单元测试和集成测试

提供：
- MockParams: 参数模拟
- MockPort: 端口模拟（输入/输出）
- MockNodeFlowSDK: 完整SDK模拟

不依赖真实SDK，可独立运行。
"""

from typing import Dict, Any, Optional, List
import uuid
from unittest.mock import MagicMock


class MockParams:
    """
    模拟参数容器

    支持参数的get/set操作
    """

    def __init__(self, params: Optional[Dict[str, Any]] = None):
        """
        初始化参数容器

        参数：
        - params: 初始参数字典
        """
        self._params = params or {}

    def get(self, key: str, default: Any = None) -> Any:
        """获取参数值"""
        return self._params.get(key, default)

    def set(self, key: str, value: Any) -> None:
        """设置参数值"""
        self._params[key] = value

    def __contains__(self, key: str) -> bool:
        """检查参数是否存在"""
        return key in self._params

    def __getitem__(self, key: str) -> Any:
        """通过[]获取参数"""
        return self._params[key]

    def __setitem__(self, key: str, value: Any) -> None:
        """通过[]设置参数"""
        self._params[key] = value

    def __repr__(self) -> str:
        return f"MockParams({self._params})"


class MockPort:
    """
    模拟端口（输入/输出）

    支持：
    - 数据接收 (recv_latest)
    - 数据发送 (send)
    - 端口状态查询
    """

    def __init__(self, name: str, port_type: str = "json"):
        """
        初始化Mock端口

        参数：
        - name: 端口名称
        - port_type: 端口类型（如 "json", "planning.path", 等）
        """
        self.name = name
        self.port_type = port_type
        self._latest_data = None
        self._data_history: List[Any] = []
        self._send_calls: List[Dict[str, Any]] = []
        self._receive_count = 0

    def recv_latest(self) -> Optional[Any]:
        """接收最新数据"""
        self._receive_count += 1
        return self._latest_data

    def recv(self) -> Optional[Any]:
        """接收数据（同recv_latest）"""
        return self.recv_latest()

    def send(self, data: Any) -> bool:
        """
        发送数据

        返回：
        - True: 发送成功
        """
        self._send_calls.append({
            'data': data,
            'call_index': len(self._send_calls)
        })
        return True

    def set_data(self, data: Any) -> None:
        """设置最新数据（用于模拟接收）"""
        self._latest_data = data
        self._data_history.append(data)

    def get_send_calls(self) -> List[Dict[str, Any]]:
        """获取所有send调用的历史"""
        return self._send_calls

    def get_last_send_data(self) -> Optional[Any]:
        """获取最后一次send的数据"""
        if self._send_calls:
            return self._send_calls[-1]['data']
        return None

    def get_receive_count(self) -> int:
        """获取recv_latest被调用的次数"""
        return self._receive_count

    def was_called(self) -> bool:
        """检查recv_latest是否被调用过"""
        return self._receive_count > 0

    def was_send_called(self) -> bool:
        """检查send是否被调用过"""
        return len(self._send_calls) > 0

    def reset(self) -> None:
        """重置端口状态"""
        self._latest_data = None
        self._data_history = []
        self._send_calls = []
        self._receive_count = 0

    def __repr__(self) -> str:
        return f"MockPort(name={self.name}, type={self.port_type}, latest_data={self._latest_data})"


class MockNodeFlowSDK:
    """
    完整的NodeFlow SDK模拟实现

    支持：
    - 参数管理
    - 端口创建和管理
    - 上下文管理器
    """

    def __init__(self, params: Optional[Dict[str, Any]] = None):
        """
        初始化Mock SDK

        参数：
        - params: 初始参数字典
        """
        self.node_id = f"test_node_{uuid.uuid4().hex[:8]}"
        self.params = MockParams(params or {})
        self.inputs: Dict[str, MockPort] = {}
        self.outputs: Dict[str, MockPort] = {}
        self._context_entered = False

    def create_input_port(self, port_name: str, port_type: str = "json") -> MockPort:
        """
        创建输入端口

        参数：
        - port_name: 端口名
        - port_type: 端口类型

        返回：
        - MockPort对象
        """
        if port_name in self.inputs:
            return self.inputs[port_name]

        port = MockPort(port_name, port_type)
        self.inputs[port_name] = port
        return port

    def create_output_port(self, port_name: str, port_type: str = "json") -> MockPort:
        """
        创建输出端口

        参数：
        - port_name: 端口名
        - port_type: 端口类型

        返回：
        - MockPort对象
        """
        if port_name in self.outputs:
            return self.outputs[port_name]

        port = MockPort(port_name, port_type)
        self.outputs[port_name] = port
        return port

    def get_input_port(self, port_name: str) -> Optional[MockPort]:
        """获取已创建的输入端口"""
        return self.inputs.get(port_name)

    def get_output_port(self, port_name: str) -> Optional[MockPort]:
        """获取已创建的输出端口"""
        return self.outputs.get(port_name)

    def get_param(self, key: str, default: Any = None) -> Any:
        """获取参数（兼容性方法）"""
        return self.params.get(key, default)

    def require_param(self, key: str) -> Any:
        """
        获取必填参数

        异常：
        - ValueError: 参数不存在
        """
        if key not in self.params:
            raise ValueError(f"Required parameter '{key}' not found")
        return self.params[key]

    def set_param(self, key: str, value: Any) -> None:
        """设置参数（测试用）"""
        self.params.set(key, value)

    def is_input_port_connected(self, port_name: str) -> bool:
        """检查输入端口是否存在"""
        return port_name in self.inputs

    def is_output_port_connected(self, port_name: str) -> bool:
        """检查输出端口是否存在"""
        return port_name in self.outputs

    def __enter__(self):
        """上下文管理器入口"""
        self._context_entered = True
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """上下文管理器退出"""
        self._context_entered = False
        return False

    def reset(self) -> None:
        """重置SDK状态（用于测试清理）"""
        for port in self.inputs.values():
            port.reset()
        for port in self.outputs.values():
            port.reset()
        self.inputs.clear()
        self.outputs.clear()
        self.params = MockParams()

    def get_all_send_calls(self) -> Dict[str, List[Dict[str, Any]]]:
        """获取所有输出端口的send调用历史"""
        return {
            port_name: port.get_send_calls()
            for port_name, port in self.outputs.items()
        }

    def __repr__(self) -> str:
        return (
            f"MockNodeFlowSDK(node_id={self.node_id}, "
            f"inputs={len(self.inputs)}, outputs={len(self.outputs)})"
        )


# 便利函数用于测试
def create_mock_sdk_with_data(
    input_data: Dict[str, Any],
    params: Optional[Dict[str, Any]] = None
) -> MockNodeFlowSDK:
    """
    创建一个预设数据的Mock SDK

    参数：
    - input_data: 字典，格式: {port_name: data}
    - params: 参数字典

    返回：
    - 配置好的MockNodeFlowSDK实例

    示例：
    ```python
    sdk = create_mock_sdk_with_data(
        input_data={'global_path': {'path': [(31.2, 121.5)]}},
        params={'output_dir': '/tmp'}
    )
    ```
    """
    sdk = MockNodeFlowSDK(params)

    for port_name, data in input_data.items():
        port = sdk.create_input_port(port_name)
        port.set_data(data)

    return sdk
