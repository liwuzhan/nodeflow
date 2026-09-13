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


# ========== 节点异常退出安全契约（草案 2026-09-01，首期=静态实现+仿真） ==========
#
# 术语约定：死亡记录中的 will = 节点生前 health 证词（事故归因）；
# 本节的 failure_policy = 节点不可用后由框架执行的处置（故障收敛）。
# 字段名 failure_policy 为草案暂定名（DEC-01），策略枚举为 DEC-04 最小集合。

VALID_OUTPUT_STRATEGIES = frozenset({"replace", "invalidate", "retain", "none"})
VALID_APPLY_ON = frozenset({"abnormal_exit"})  # planned_stop / hang 待 DEC-06
VALID_ANTI_REPLAY = frozenset({"require_new_commit"})
VALID_SAFETY_HANDLERS = frozenset({"linux_sysfs_pwm_pair"})


def resolve_event_fields(value: Any, *, wall_time: Any = None,
                         node_id: Any = None, run_id: Any = None) -> Any:
    """解析安全 payload literal 中的 $event.* 动态字段（DEC-05 首期最小集）。

    未知 $event 字段抛 ValueError——校验期即报错，不静默写入占位符。
    """
    if isinstance(value, dict):
        return {
            k: resolve_event_fields(v, wall_time=wall_time, node_id=node_id, run_id=run_id)
            for k, v in value.items()
        }
    if isinstance(value, list):
        return [
            resolve_event_fields(v, wall_time=wall_time, node_id=node_id, run_id=run_id)
            for v in value
        ]
    if isinstance(value, str) and value.startswith("$event."):
        field = value[len("$event."):]
        if field == "wall_time":
            return wall_time
        if field == "node_id":
            return node_id
        if field == "run_id":
            return run_id
        raise ValueError(f"unknown event field: {value}")
    return value


@dataclass
class OutputPolicy:
    """单个输出端口的异常退出处置策略"""
    strategy: str                                  # replace/invalidate/retain/none
    value: Optional[Dict[str, Any]] = None         # replace 的安全 payload（可含 $event.wall_time）
    reason: Optional[str] = None                   # invalidate 的原因标记
    completion: Optional[Dict[str, Any]] = None    # 如 {resource: drive_pwm, require: {latch: asserted}}


@dataclass
class ResourceAction:
    """资源面安全动作声明（真实执行需图级 safety_resources 绑定）"""
    action: str = ""                                # 如 neutral


@dataclass
class FailurePolicy:
    """节点异常退出安全契约（node.yaml 的 failure_policy 段）"""
    apply_on: List[str] = field(default_factory=lambda: ["abnormal_exit"])
    outputs: Dict[str, OutputPolicy] = field(default_factory=dict)
    resources: Dict[str, ResourceAction] = field(default_factory=dict)
    anti_replay: Dict[str, str] = field(default_factory=dict)  # 输入端口 -> require_new_commit
    rearm: Optional[Dict[str, Any]] = None          # 如 {mode: manual_then_fresh, input: velocity_cmd}
    deadline_ms: Optional[float] = None             # 真实输出模式必须填写（待边侧停车预算冻结）


@dataclass
class SafetyResourceBinding:
    """图级资源绑定：语义在 node.yaml 声明，机器配置在 runtime.yaml 绑定（DEC-02）"""
    owner: str                                      # 拥有该资源的节点 id
    handler: str                                    # 白名单 handler（VALID_SAFETY_HANDLERS）
    params_from_owner: Dict[str, str] = field(default_factory=dict)  # handler 参数 <- owner 参数名
    dry_run: bool = True                            # 默认 dry-run：绝不触碰真实 sysfs


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
    # 输入看门狗（W3-3，opt-in）：{端口名: 超时秒}。
    # 断流超时 → 节点 on_input_lost 回调，未注册则默认 sdk.die。
    # 只应声明在持续输出的上游端口上（静态输出端口不适用）
    input_watchdog: Dict[str, float] = field(default_factory=dict)
    # 异常退出安全契约（2026-09-01 草案；缺失 = 框架不做任何数据面/资源面处置）
    failure_policy: Optional[FailurePolicy] = None


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
    # 图级安全资源绑定（2026-09-01 草案）：缺省为空 → 所有 failure_policy 资源动作
    # 只做锁存断言与 dry-run 记录，不触碰任何真实设备接口
    safety_resources: Dict[str, SafetyResourceBinding] = field(default_factory=dict)


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
