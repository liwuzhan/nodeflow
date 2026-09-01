"""
图验证器模块
验证节点和边的合法性
"""

from typing import Dict, Optional, Set

from edge.runtime.config.models import (
    NodeInstance, Edge, ValidationResult, SafetyResourceBinding, resolve_event_fields,
)
from edge.runtime.node_hub.node_registry import NodeRegistry
from edge.runtime.utils.errors import PortNotFoundError, TypeMismatchError
from edge.runtime.utils.logger import get_logger

logger = get_logger(__name__)


class GraphValidator:
    """图验证器"""

    @staticmethod
    def validate(nodes: list, edges: list, registry: NodeRegistry,
                 safety_resources: Optional[Dict[str, SafetyResourceBinding]] = None
                 ) -> ValidationResult:
        """
        验证图的合法性

        检查项：
        - 节点ID唯一性（在ConfigValidator中已检查，这里重复检查）
        - edges引用的节点存在
        - edges引用的端口存在
        - 端口类型兼容性（非any必须匹配）

        参数：
        - nodes: NodeInstance列表
        - edges: Edge列表
        - registry: NodeRegistry对象

        返回：
        - ValidationResult对象
        """
        result = ValidationResult()

        # 建立节点ID到NodeInstance的映射
        node_map = {n.id: n for n in nodes}
        node_ids: Set[str] = set(node_map.keys())

        # 1. 验证节点ID唯一性
        if len(node_ids) != len(nodes):
            result.add_error("Duplicate node IDs found")

        # 2. 验证edges
        for edge in edges:
            # 2.1 验证from_node存在
            if edge.from_node not in node_ids:
                result.add_error(f"Edge references non-existent node: '{edge.from_node}'")
                continue

            # 2.2 验证to_node存在
            if edge.to_node not in node_ids:
                result.add_error(f"Edge references non-existent node: '{edge.to_node}'")
                continue

            from_node_instance = node_map[edge.from_node]
            to_node_instance = node_map[edge.to_node]

            # 2.3 验证from_node的输出端口存在
            from_manifest = registry.get_manifest(from_node_instance.package)
            if not from_manifest:
                result.add_error(f"Node '{edge.from_node}' package '{from_node_instance.package}' not found")
                continue

            from_port_names = {p.name for p in from_manifest.outputs}
            if edge.from_port not in from_port_names:
                result.add_error(
                    f"Output port '{edge.from_port}' not found in node '{edge.from_node}' "
                    f"(package '{from_node_instance.package}'). Available ports: {from_port_names}"
                )
                continue

            # 2.4 验证to_node的输入端口存在
            to_manifest = registry.get_manifest(to_node_instance.package)
            if not to_manifest:
                result.add_error(f"Node '{edge.to_node}' package '{to_node_instance.package}' not found")
                continue

            to_port_names = {p.name for p in to_manifest.inputs}
            if edge.to_port not in to_port_names:
                result.add_error(
                    f"Input port '{edge.to_port}' not found in node '{edge.to_node}' "
                    f"(package '{to_node_instance.package}'). Available ports: {to_port_names}"
                )
                continue

            # 2.5 验证端口类型兼容性
            from_port = next((p for p in from_manifest.outputs if p.name == edge.from_port), None)
            to_port = next((p for p in to_manifest.inputs if p.name == edge.to_port), None)

            if from_port and to_port:
                if not _is_type_compatible(from_port.type, to_port.type):
                    result.add_warning(
                        f"Type mismatch for edge: "
                        f"{edge.from_node}.{edge.from_port}({from_port.type}) -> "
                        f"{edge.to_node}.{edge.to_port}({to_port.type})"
                    )

        # 3. 安全契约交叉校验（2026-09-01 草案 §5.5）
        GraphValidator._validate_safety_contracts(
            node_map, registry, safety_resources or {}, result
        )

        logger.debug(f"Graph validation: {'PASSED' if result.is_valid else 'FAILED'}")
        if not result.is_valid:
            logger.debug(f"Validation errors: {result.errors}")
        if result.warnings:
            logger.debug(f"Validation warnings: {result.warnings}")

        return result

    @staticmethod
    def _validate_safety_contracts(node_map, registry, safety_resources, result):
        """安全契约图级校验：
        - 遗留 manifest 缺失 failure_policy → 聚合告警（迁移期 §11.2，不拒绝启动）
        - safety_resources 绑定：owner 存在、owner manifest 声明该资源动作
        - 真实输出模式（binding.dry_run=false）：deadline_ms 必填、
          replace payload 必须可序列化且不超过 buffer 容量
        """
        # 遗留告警（聚合为一条）
        legacy = []
        for node in node_map.values():
            manifest = registry.get_manifest(node.package)
            if manifest and manifest.failure_policy is None:
                legacy.append(node.id)
        if legacy:
            result.add_warning(
                f"节点缺少 failure_policy 声明（迁移期仅告警，异常退出时框架不执行处置）: "
                f"{sorted(legacy)}"
            )

        # 资源绑定校验
        for res_name, binding in safety_resources.items():
            if binding.owner not in node_map:
                result.add_error(
                    f"safety_resources.{res_name}.owner '{binding.owner}' 不在图的节点列表中"
                )
                continue
            owner_instance = node_map[binding.owner]
            owner_manifest = registry.get_manifest(owner_instance.package)
            if not owner_manifest:
                result.add_error(
                    f"safety_resources.{res_name}: owner 包 '{owner_instance.package}' 无法解析"
                )
                continue

            declared = (
                owner_manifest.failure_policy.resources.get(res_name)
                if owner_manifest.failure_policy else None
            )
            if declared is None:
                result.add_error(
                    f"safety_resources.{res_name}: owner '{binding.owner}' 的 manifest "
                    f"未声明该资源动作（failure_policy.resources）"
                )
                continue

            # 真实输出模式门槛（§11.2：安全关键资源缺失 deadline 时拒绝真实输出）
            if not binding.dry_run:
                if owner_manifest.failure_policy.deadline_ms is None:
                    result.add_error(
                        f"safety_resources.{res_name}: 真实输出模式（dry_run=false）要求 "
                        f"owner failure_policy.deadline_ms 已填写（待边侧停车预算冻结）"
                    )

        # replace payload 可序列化且不超容量（对已声明节点统一检查，与绑定无关）
        try:
            import msgpack
            from edge.sdk.shared_buffer_lite import SharedBufferLite

            for node in node_map.values():
                manifest = registry.get_manifest(node.package)
                if not manifest or not manifest.failure_policy:
                    continue
                port_defs = {p.name: p for p in manifest.outputs}
                for port_name, out_policy in manifest.failure_policy.outputs.items():
                    if out_policy.strategy != "replace" or not isinstance(out_policy.value, dict):
                        continue
                    try:
                        resolved = resolve_event_fields(
                            out_policy.value, wall_time=0.0, node_id=node.id, run_id="",
                        )
                        packed = msgpack.packb(resolved, use_bin_type=True)
                    except Exception as e:
                        result.add_error(
                            f"{node.id}.failure_policy.outputs.{port_name}: value 无法解析/序列化 ({e})"
                        )
                        continue
                    buf_size = port_defs[port_name].buffer_size if port_name in port_defs else SharedBufferLite.DEFAULT_SIZE
                    if len(packed) > buf_size - SharedBufferLite.HEADER_SIZE:
                        result.add_error(
                            f"{node.id}.failure_policy.outputs.{port_name}: value "
                            f"({len(packed)}B) 超过 buffer 容量 ({buf_size - SharedBufferLite.HEADER_SIZE}B)"
                        )
        except ImportError:
            result.add_warning("msgpack 不可用，跳过 replace payload 容量检查")


def _is_type_compatible(from_type: str, to_type: str) -> bool:
    """
    检查端口类型是否兼容

    规则：
    - 'any'与任何类型兼容
    - 相同类型兼容
    - 其他情况不兼容

    参数：
    - from_type: 输出端口类型
    - to_type: 输入端口类型

    返回：
    - True表示兼容，False表示不兼容
    """
    # any类型与任何类型兼容
    if from_type == "any" or to_type == "any":
        return True

    # 相同类型兼容
    if from_type == to_type:
        return True

    return False
