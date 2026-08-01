"""
图验证器模块
验证节点和边的合法性
"""

from typing import Set

from edge.runtime.config.models import NodeInstance, Edge, ValidationResult
from edge.runtime.node_hub.node_registry import NodeRegistry
from edge.runtime.utils.errors import PortNotFoundError, TypeMismatchError
from edge.runtime.utils.logger import get_logger

logger = get_logger(__name__)


class GraphValidator:
    """图验证器"""

    @staticmethod
    def validate(nodes: list, edges: list, registry: NodeRegistry) -> ValidationResult:
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

        logger.debug(f"Graph validation: {'PASSED' if result.is_valid else 'FAILED'}")
        if not result.is_valid:
            logger.debug(f"Validation errors: {result.errors}")
        if result.warnings:
            logger.debug(f"Validation warnings: {result.warnings}")

        return result


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
