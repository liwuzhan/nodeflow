"""
NodeFlow SDK主入口
为节点开发者提供便捷的API
"""

import os
from typing import Dict, Any, Optional

from sdk.param_parser import ParamParser
from sdk.port import InputPort, OutputPort
from runtime.utils.logger import get_logger, setup_logger

logger = get_logger(__name__)


class NodeFlowSDK:
    """
    NodeFlow SDK主类

    提供节点开发的核心API：
    - 参数解析
    - 端口创建
    - 数据收发
    """

    def __init__(self, log_level: str = "INFO"):
        """
        初始化SDK

        自动从环境变量读取：
        - NODE_ID: 节点实例ID
        - NODE_HUB_PATH: 节点库根目录
        - NODE_SOCKET_DIR: Socket临时目录
        - NODE_IN_<PORT>: 输入端口socket路径
        - NODE_OUT_<PORT>: 输出端口socket路径

        参数：
        - log_level: 日志级别
        """
        # 设置日志
        self.logger = setup_logger(f"nodeflow.node", log_level)

        # 从环境变量读取基本信息
        self.node_id = os.getenv('NODE_ID')
        self.node_hub_path = os.getenv('NODE_HUB_PATH')
        self.socket_dir = os.getenv('NODE_SOCKET_DIR')

        if not self.node_id:
            raise ValueError("NODE_ID environment variable not set")

        self.logger.info(f"NodeFlow SDK initialized for node '{self.node_id}'")

        # 解析命令行参数
        self.params = ParamParser.parse()
        self.logger.debug(f"Parsed parameters: {self.params}")

        # 端口字典
        self.inputs: Dict[str, InputPort] = {}
        self.outputs: Dict[str, OutputPort] = {}

    def get_param(self, key: str, default: Any = None) -> Any:
        """
        获取参数值

        参数：
        - key: 参数名
        - default: 默认值

        返回：
        - 参数值
        """
        return self.params.get(key, default)

    def require_param(self, key: str) -> Any:
        """
        获取必填参数

        参数：
        - key: 参数名

        返回：
        - 参数值

        异常：
        - ValueError: 参数不存在
        """
        if key not in self.params:
            raise ValueError(f"Required parameter '{key}' not found")
        return self.params[key]

    def create_input_port(self, port_name: str) -> InputPort:
        """
        创建输入端口

        参数：
        - port_name: 端口名（必须与node.yaml中定义的一致）

        返回：
        - InputPort对象

        异常：
        - ValueError: 端口未配置
        """
        env_var_name = f'NODE_IN_{port_name}'
        socket_path = os.getenv(env_var_name)

        if not socket_path:
            raise ValueError(
                f"Input port '{port_name}' not configured. "
                f"Environment variable '{env_var_name}' not found."
            )

        port = InputPort(port_name, socket_path)
        self.inputs[port_name] = port

        self.logger.info(f"Created input port: {port_name}")
        return port

    def create_output_port(self, port_name: str) -> OutputPort:
        """
        创建输出端口

        参数：
        - port_name: 端口名（必须与node.yaml中定义的一致）

        返回：
        - OutputPort对象

        异常：
        - ValueError: 端口未配置
        """
        env_var_name = f'NODE_OUT_{port_name}'
        socket_path = os.getenv(env_var_name)

        if not socket_path:
            raise ValueError(
                f"Output port '{port_name}' not configured. "
                f"Environment variable '{env_var_name}' not found."
            )

        port = OutputPort(port_name, socket_path)
        self.outputs[port_name] = port

        self.logger.info(f"Created output port: {port_name}")
        return port

    def get_input_port(self, port_name: str) -> Optional[InputPort]:
        """
        获取已创建的输入端口

        参数：
        - port_name: 端口名

        返回：
        - InputPort对象，如果不存在返回None
        """
        return self.inputs.get(port_name)

    def get_output_port(self, port_name: str) -> Optional[OutputPort]:
        """
        获取已创建的输出端口

        参数：
        - port_name: 端口名

        返回：
        - OutputPort对象，如果不存在返回None
        """
        return self.outputs.get(port_name)

    def shutdown(self):
        """
        清理资源

        关闭所有端口
        """
        self.logger.info("Shutting down NodeFlow SDK")

        for port in self.inputs.values():
            port.close()

        for port in self.outputs.values():
            port.close()

        self.logger.info("NodeFlow SDK shutdown complete")

    def __enter__(self):
        """上下文管理器入口"""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """上下文管理器退出"""
        self.shutdown()
        return False
