"""
配置数据模型模块
定义运行时配置和节点说明书的数据结构
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any


# ========== 节点说明书 (node.yaml) 数据结构 ==========

@dataclass
class ParamSchema:
    """参数定义"""
    type: str = "any"  # string/int/float/bool/any
    required: bool = False
    default: Optional[Any] = None
    description: str = ""


@dataclass
class PortDef:
    """端口定义"""
    name: str
    type: str = "any"  # 端口类型，用于连线校验
    description: str = ""
    buffer_size: int = 1024 * 1024  # 缓冲区大小（字节），默认1MB
    conflate: bool = True  # 是否覆盖旧数据（最新值语义），默认True


@dataclass
class EntryPoint:
    """启动入口"""
    kind: str  # python, sh, binary, bat 等
    cmd: List[str]  # 命令数组，如 ["python3", "run.py"]


@dataclass
class NodeManifest:
    """节点说明书 (node.yaml)"""
    name: str
    version: str = "0.1.0"
    description: str = ""
    entrypoints: Dict[str, EntryPoint] = field(default_factory=dict)  # platform -> EntryPoint
    inputs: List[PortDef] = field(default_factory=list)  # 输入端口列表
    outputs: List[PortDef] = field(default_factory=list)  # 输出端口列表
    params: Dict[str, ParamSchema] = field(default_factory=dict)  # 参数定义
    # 就绪信号（W2-5）：heartbeat = health 心跳新鲜（默认）；
    # first_output = 全部输出 buffer seq>0（静态输出节点 opt-in）
    readiness: str = "heartbeat"


# ========== 运行时配置 (runtime.yaml) 数据结构 ==========

@dataclass
class RestartPolicy:
    """重启策略"""
    max_retries: int = 3
    backoff_ms: int = 500


@dataclass
class NodeInstance:
    """节点实例"""
    id: str
    package: str
    params: Dict[str, Any] = field(default_factory=dict)
    entrypoint: Optional[EntryPoint] = None  # 可选的覆盖入口


@dataclass
class Edge:
    """连接关系"""
    from_node: str
    from_port: str
    to_node: str
    to_port: str
    type: Optional[str] = None  # 可选的类型说明


@dataclass
class RuntimeConfig:
    """运行时配置 (runtime.yaml)"""
    graph_id: str
    graph_version: int = 1
    node_hub_path: str = "./edge/nodes"
    nodes: List[NodeInstance] = field(default_factory=list)
    edges: List[Edge] = field(default_factory=list)
    restart_policy: RestartPolicy = field(default_factory=RestartPolicy)


# ========== 验证结果 ==========

@dataclass
class ValidationResult:
    """验证结果"""
    is_valid: bool = True
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)

    def add_error(self, error: str):
        """添加错误"""
        self.is_valid = False
        self.errors.append(error)

    def add_warning(self, warning: str):
        """添加警告"""
        self.warnings.append(warning)

    def has_errors(self) -> bool:
        """是否有错误"""
        return not self.is_valid

    def has_warnings(self) -> bool:
        """是否有警告"""
        return len(self.warnings) > 0
