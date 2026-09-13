"""
异常定义模块
定义框架使用的所有自定义异常
"""


class NodeFlowError(Exception):
    """框架基础异常类"""
    pass


# 配置相关异常
class ConfigError(NodeFlowError):
    """配置错误基类"""
    pass


class YAMLParseError(ConfigError):
    """YAML解析错误"""
    pass


class ValidationError(ConfigError):
    """配置验证错误"""
    pass


# 节点相关异常
class NodeError(NodeFlowError):
    """节点错误基类"""
    pass


class NodeNotFoundError(NodeError):
    """节点包不存在"""
    def __init__(self, package_name: str):
        super().__init__(f"Node package '{package_name}' not found")
        self.package_name = package_name


class ManifestInvalidError(NodeError):
    """节点说明书不合法"""
    def __init__(self, package_name: str, reason: str):
        super().__init__(f"Invalid manifest for '{package_name}': {reason}")
        self.package_name = package_name
        self.reason = reason


class NodeLaunchError(NodeError):
    """节点启动失败"""
    def __init__(self, node_id: str, reason: str):
        super().__init__(f"Failed to launch node '{node_id}': {reason}")
        self.node_id = node_id
        self.reason = reason


class NodeStartupError(NodeError):
    """节点启动错误（启动即退出）"""
    def __init__(self, node_id: str, reason: str):
        super().__init__(f"Node '{node_id}' failed at startup: {reason}")
        self.node_id = node_id
        self.reason = reason


# 图分析相关异常
class GraphError(NodeFlowError):
    """图分析错误基类"""
    pass


class CyclicDependencyError(GraphError):
    """循环依赖错误"""
    def __init__(self, nodes: list):
        super().__init__(f"Cyclic dependency detected: {nodes}")
        self.nodes = nodes


class InvalidEdgeError(GraphError):
    """非法的边连接"""
    def __init__(self, edge_from: str, edge_to: str, reason: str):
        super().__init__(f"Invalid edge from '{edge_from}' to '{edge_to}': {reason}")
        self.edge_from = edge_from
        self.edge_to = edge_to
        self.reason = reason


class PortNotFoundError(GraphError):
    """端口不存在"""
    def __init__(self, node_id: str, port_name: str):
        super().__init__(f"Port '{port_name}' not found in node '{node_id}'")
        self.node_id = node_id
        self.port_name = port_name


class TypeMismatchError(GraphError):
    """类型不匹配"""
    def __init__(self, from_type: str, to_type: str):
        super().__init__(f"Type mismatch: cannot connect '{from_type}' to '{to_type}'")
        self.from_type = from_type
        self.to_type = to_type


# IPC相关异常
class IPCError(NodeFlowError):
    """IPC通信错误基类"""
    pass


class SocketError(IPCError):
    """Socket错误"""
    pass


class ProtocolError(IPCError):
    """协议错误"""
    pass
