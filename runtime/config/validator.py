"""
配置验证器模块
验证运行时配置和节点说明书的合法性
"""

from typing import Dict, Set
from runtime.config.models import RuntimeConfig, NodeManifest, ValidationResult
from runtime.utils.logger import get_logger

logger = get_logger(__name__)


class ConfigValidator:
    """配置验证器"""

    @staticmethod
    def validate_runtime_config(config: RuntimeConfig) -> ValidationResult:
        """
        验证运行时配置

        检查项：
        - 节点ID唯一性
        - 引用的节点和端口存在性（需要配合node registry）
        - 边的格式正确性

        参数：
        - config: RuntimeConfig对象

        返回：
        - ValidationResult对象
        """
        result = ValidationResult()

        # 1. 验证节点ID唯一性
        node_ids: Set[str] = set()
        for node in config.nodes:
            if node.id in node_ids:
                result.add_error(f"Duplicate node ID: '{node.id}'")
            node_ids.add(node.id)

        # 2. 验证edges引用的节点存在
        for edge in config.edges:
            if edge.from_node not in node_ids:
                result.add_error(f"Edge references non-existent node: '{edge.from_node}'")
            if edge.to_node not in node_ids:
                result.add_error(f"Edge references non-existent node: '{edge.to_node}'")

        # 3. 验证重启策略参数
        if config.restart_policy.max_retries < 0:
            result.add_error("restart_policy.max_retries must be >= 0")
        if config.restart_policy.backoff_ms < 0:
            result.add_error("restart_policy.backoff_ms must be >= 0")

        logger.debug(f"Runtime config validation: {'PASSED' if result.is_valid else 'FAILED'}")
        if not result.is_valid:
            logger.debug(f"Validation errors: {result.errors}")

        return result

    @staticmethod
    def validate_node_manifest(manifest: NodeManifest) -> ValidationResult:
        """
        验证节点说明书

        检查项：
        - 必填字段存在
        - entrypoints至少有一个
        - 端口名称不重复

        参数：
        - manifest: NodeManifest对象

        返回：
        - ValidationResult对象
        """
        result = ValidationResult()

        # 1. 验证必填字段
        if not manifest.name:
            result.add_error("Node name is required")

        # 2. 验证至少有一个entrypoint
        if not manifest.entrypoints:
            result.add_error("At least one entrypoint is required")

        # 3. 验证entrypoint命令不为空
        for platform, ep in manifest.entrypoints.items():
            if not ep.cmd:
                result.add_error(f"Empty command for entrypoint '{platform}'")

        # 4. 验证输入端口名称唯一性
        input_names: Set[str] = set()
        for port in manifest.inputs:
            if port.name in input_names:
                result.add_error(f"Duplicate input port name: '{port.name}'")
            input_names.add(port.name)

        # 5. 验证输出端口名称唯一性
        output_names: Set[str] = set()
        for port in manifest.outputs:
            if port.name in output_names:
                result.add_error(f"Duplicate output port name: '{port.name}'")
            output_names.add(port.name)

        # 6. 验证输入输出端口名称不重叠
        overlap = input_names.intersection(output_names)
        if overlap:
            result.add_error(f"Port names overlap between inputs and outputs: {overlap}")

        logger.debug(f"Node manifest validation for '{manifest.name}': {'PASSED' if result.is_valid else 'FAILED'}")
        if not result.is_valid:
            logger.debug(f"Validation errors: {result.errors}")

        return result
