#!/usr/bin/env python3.12
"""
NodeFlow MCP Server
提供 AI 辅助的 NodeFlow 数据流调试能力

实现以下工具：
- nodeflow/get-node-info: 节点库信息查询
- nodeflow/validate-yaml: YAML 配置验证
- nodeflow/edit-yaml: YAML 配置修改
- nodeflow/run-runtime: 启动运行时
- nodeflow/stop-runtime: 停止运行时
- nodeflow/read-logs: 读取节点日志
- nodeflow/get-runtime-status: 获取运行状态
"""

import asyncio
import json
import os
import sys
import tempfile
import time
from pathlib import Path
from typing import Dict, List, Optional, Any

# 导入 MCP SDK
try:
    from mcp.server import Server
    from mcp.server.models import InitializationOptions
    from mcp.server.stdio import stdio_server
    from mcp.types import (
        CallToolRequest,
        CallToolResult,
        ListToolsRequest,
        ListToolsResult,
        Tool,
        TextContent,
    )
except ImportError:
    print("Error: MCP SDK not installed. Please install with: pip install mcp>=1.0.0")
    sys.exit(1)

# 导入 NodeFlow 模块
try:
    from runtime_manager import RuntimeManager, RuntimeStatus
    from tools.cli.commands.node_cmd import scan_node_packages, load_manifest, find_node_manifest
    from runtime.config.yaml_parser import YAMLParser
    from runtime.config.validator import ConfigValidator
    from runtime.node_hub.node_registry import NodeRegistry
    from runtime.graph.validator import GraphValidator
    from runtime.graph.topology import TopologyAnalyzer
except ImportError as e:
    print(f"Error importing NodeFlow modules: {e}")
    print("Please ensure you're running from the NodeFlow project root directory.")
    sys.exit(1)

# 创建 MCP 服务器实例
server = Server("nodeflow")

# 创建运行时管理器实例
runtime_manager = RuntimeManager()


def create_tool_response(content: Any, success: bool = True) -> List[TextContent]:
    """
    创建统一的工具响应格式

    Args:
        content: 响应内容
        success: 是否成功

    Returns:
        TextContent 列表
    """
    response = {
        "success": success,
        "timestamp": time.time()
    }

    if success:
        response["result"] = content
    else:
        response["error"] = content

    return [TextContent(
        type="text",
        text=json.dumps(response, indent=2, ensure_ascii=False)
    )]


def safe_execute(func):
    """
    安全执行装饰器，捕获异常并返回结构化错误信息
    """
    async def wrapper(args):
        try:
            return await func(args)
        except Exception as e:
            return create_tool_response(
                {
                    "type": "EXECUTION_ERROR",
                    "message": str(e),
                    "details": f"Error in {func.__name__}: {type(e).__name__}"
                },
                success=False
            )
    return wrapper


@server.list_tools()
async def list_tools() -> ListToolsResult:
    """列出所有可用的工具"""
    tools = [
        Tool(
            name="nodeflow/get-node-info",
            description="查询节点库信息。列出所有可用节点或获取特定节点的详细信息",
            inputSchema={
                "type": "object",
                "properties": {
                    "hub_path": {
                        "type": "string",
                        "description": "节点库路径，默认为 ./node-hub",
                        "default": "./node-hub"
                    },
                    "package": {
                        "type": "string",
                        "description": "可选，特定节点包名称。如果提供，返回该节点的详细信息；如果省略，返回所有节点列表"
                    }
                }
            }
        ),
        Tool(
            name="nodeflow/validate-yaml",
            description="验证 runtime.yaml 配置文件的正确性，包括语法、节点存在性、端口兼容性和拓扑结构",
            inputSchema={
                "type": "object",
                "properties": {
                    "yaml_path": {
                        "type": "string",
                        "description": "YAML 配置文件路径"
                    },
                    "yaml_content": {
                        "type": "string",
                        "description": "可选，YAML 内容字符串。如果提供，将验证该内容而不是文件"
                    }
                },
                "oneOf": [
                    {"required": ["yaml_path"]},
                    {"required": ["yaml_content"]}
                ]
            }
        ),
        Tool(
            name="nodeflow/edit-yaml",
            description="修改 runtime.yaml 配置文件。支持修改节点参数、添加/删除节点或连接",
            inputSchema={
                "type": "object",
                "properties": {
                    "yaml_path": {
                        "type": "string",
                        "description": "YAML 配置文件路径"
                    },
                    "changes": {
                        "type": "object",
                        "description": "要修改的内容。支持嵌套路径，如 nodes.imu.params.rate 等",
                        "additionalProperties": True
                    },
                    "validate_after_edit": {
                        "type": "boolean",
                        "description": "修改后是否自动验证配置",
                        "default": True
                    }
                },
                "required": ["yaml_path", "changes"]
            }
        ),
        Tool(
            name="nodeflow/run-runtime",
            description="启动 NodeFlow 运行时。支持定时关机，便于 AI 收集数据",
            inputSchema={
                "type": "object",
                "properties": {
                    "yaml_path": {
                        "type": "string",
                        "description": "runtime.yaml 配置文件路径"
                    },
                    "duration": {
                        "type": "integer",
                        "description": "可选，运行时长（秒）。到期后自动关机。默认不自动关机",
                        "minimum": 1
                    }
                },
                "required": ["yaml_path"]
            }
        ),
        Tool(
            name="nodeflow/stop-runtime",
            description="停止当前运行的 NodeFlow 运行时。优雅关闭所有节点进程",
            inputSchema={
                "type": "object",
                "properties": {
                    "timeout": {
                        "type": "integer",
                        "description": "等待优雅关闭的超时时间（秒），默认 10 秒",
                        "default": 10,
                        "minimum": 1
                    }
                }
            }
        ),
        Tool(
            name="nodeflow/read-logs",
            description="读取节点日志文件。支持读取 stdout/stderr 或两者，可限制行数",
            inputSchema={
                "type": "object",
                "properties": {
                    "node_id": {
                        "type": "string",
                        "description": "节点 ID"
                    },
                    "stream": {
                        "type": "string",
                        "enum": ["stdout", "stderr", "both"],
                        "description": "日志流类型",
                        "default": "both"
                    },
                    "tail": {
                        "type": "integer",
                        "description": "可选，读取最后 N 行",
                        "minimum": 1
                    },
                    "max_lines": {
                        "type": "integer",
                        "description": "最大读取行数，默认 1000",
                        "default": 1000,
                        "minimum": 1
                    }
                },
                "required": ["node_id"]
            }
        ),
        Tool(
            name="nodeflow/get-runtime-status",
            description="获取当前运行时状态，包括进程信息、节点状态和运行时长",
            inputSchema={
                "type": "object",
                "properties": {
                    "include_details": {
                        "type": "boolean",
                        "description": "是否包含详细的节点进程信息",
                        "default": True
                    }
                }
            }
        )
    ]

    return ListToolsResult(tools=tools)


@server.call_tool()
async def call_tool(name: str, arguments: Dict[str, Any]) -> CallToolResult:
    """处理工具调用"""
    handlers = {
        "nodeflow/get-node-info": handle_get_node_info,
        "nodeflow/validate-yaml": handle_validate_yaml,
        "nodeflow/edit-yaml": handle_edit_yaml,
        "nodeflow/run-runtime": handle_run_runtime,
        "nodeflow/stop-runtime": handle_stop_runtime,
        "nodeflow/read-logs": handle_read_logs,
        "nodeflow/get-runtime-status": handle_get_runtime_status,
    }

    if name not in handlers:
        return CallToolResult(
            content=create_tool_response(
                {
                    "type": "UNKNOWN_TOOL",
                    "message": f"Unknown tool: {name}"
                },
                success=False
            )
        )

    try:
        content = await handlers[name](arguments)
        return CallToolResult(content=content)
    except Exception as e:
        return CallToolResult(
            content=create_tool_response(
                {
                    "type": "TOOL_ERROR",
                    "message": str(e),
                    "tool": name
                },
                success=False
            )
        )


@safe_execute
async def handle_get_node_info(arguments: Dict[str, Any]) -> List[TextContent]:
    """处理节点信息查询"""
    hub_path = arguments.get("hub_path", "./node-hub")
    package_name = arguments.get("package")

    # 验证路径安全性
    hub_path_abs = Path(hub_path).resolve()
    if not hub_path_abs.exists():
        return create_tool_response(
            {
                "type": "NODE_HUB_ERROR",
                "message": f"Node hub path not found: {hub_path}"
            },
            success=False
        )

    try:
        if package_name:
            # 获取特定节点信息
            manifest_path = find_node_manifest(hub_path_abs, package_name)
            if not manifest_path:
                return create_tool_response(
                    {
                        "type": "NODE_NOT_FOUND",
                        "message": f"Node package '{package_name}' not found in {hub_path}"
                    },
                    success=False
                )

            manifest = load_manifest(manifest_path)

            # 简化 manifest 结构，去掉不需要的字段
            simplified_manifest = {
                "name": manifest.get("name"),
                "version": manifest.get("version"),
                "description": manifest.get("description"),
                "entrypoints": manifest.get("entrypoints", {}),
                "ports": manifest.get("ports", {}),
                "params": manifest.get("params", {}),
                "package_path": str(manifest_path.parent.relative_to(Path.cwd()))
            }

            return create_tool_response(simplified_manifest)
        else:
            # 列出所有节点包
            packages = scan_node_packages(hub_path_abs)

            result = {
                "hub_path": str(hub_path_abs),
                "package_count": len(packages),
                "packages": [
                    {
                        "name": pkg['name'] if isinstance(pkg, dict) else str(pkg),
                        "description": pkg.get('description', '') if isinstance(pkg, dict) else '',
                        "version": pkg.get('version', '') if isinstance(pkg, dict) else '',
                        "path": pkg.get('path', '') if isinstance(pkg, dict) else ''
                    }
                    for pkg in packages
                ]
            }

            return create_tool_response(result)

    except Exception as e:
        return create_tool_response(
            {
                "type": "NODE_INFO_ERROR",
                "message": f"Failed to get node info: {str(e)}",
                "hub_path": hub_path,
                "package": package_name
            },
            success=False
        )


@safe_execute
async def handle_validate_yaml(arguments: Dict[str, Any]) -> List[TextContent]:
    """处理 YAML 验证"""
    yaml_path = arguments.get("yaml_path")
    yaml_content = arguments.get("yaml_content")

    try:
        if yaml_content:
            # 处理传入的 YAML 内容
            with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
                f.write(yaml_content)
                temp_path = f.name

            try:
                result = await _validate_yaml_file(temp_path)
            finally:
                os.unlink(temp_path)
        else:
            # 验证文件
            if not Path(yaml_path).exists():
                return create_tool_response(
                    {
                        "type": "FILE_NOT_FOUND",
                        "message": f"YAML file not found: {yaml_path}"
                    },
                    success=False
                )
            result = await _validate_yaml_file(yaml_path)

        return create_tool_response(result)

    except Exception as e:
        return create_tool_response(
            {
                "type": "VALIDATION_ERROR",
                "message": f"Failed to validate YAML: {str(e)}"
            },
            success=False
        )


async def _validate_yaml_file(yaml_path: str) -> Dict[str, Any]:
    """验证 YAML 文件的内部实现"""
    result = {
        "is_valid": False,
        "errors": [],
        "warnings": [],
        "normalized": None,
        "startup_layers": None
    }

    try:
        # 1. 解析 YAML
        parser = YAMLParser()
        config = parser.parse_runtime_config(yaml_path)

        # 2. 验证基础配置
        validator = ConfigValidator()
        validation_result = validator.validate_runtime_config(config)

        if not validation_result.is_valid:
            result["errors"].extend([
                {
                    "type": "CONFIG_ERROR",
                    "message": error,
                    "severity": "error"
                }
                for error in validation_result.errors
            ])

        if validation_result.warnings:
            result["warnings"].extend([
                {
                    "type": "CONFIG_WARNING",
                    "message": warning,
                    "severity": "warning"
                }
                for warning in validation_result.warnings
            ])

        # 3. 加载节点库
        try:
            registry = NodeRegistry(config.node_hub_path)
            registry.load_all()
        except Exception as e:
            result["errors"].append({
                "type": "NODE_HUB_ERROR",
                "message": f"Failed to load node hub: {str(e)}",
                "severity": "error"
            })
            return result

        # 4. 验证图结构
        try:
            graph_result = GraphValidator.validate(config.nodes, config.edges, registry)

            if not graph_result.is_valid:
                result["errors"].extend([
                    {
                        "type": "GRAPH_ERROR",
                        "message": error,
                        "severity": "error"
                    }
                    for error in graph_result.errors
                ])

            if graph_result.warnings:
                result["warnings"].extend([
                    {
                        "type": "GRAPH_WARNING",
                        "message": warning,
                        "severity": "warning"
                    }
                    for warning in graph_result.warnings
                ])

        except Exception as e:
            result["errors"].append({
                "type": "GRAPH_ERROR",
                "message": f"Graph validation failed: {str(e)}",
                "severity": "error"
            })

        # 5. 拓扑分析
        try:
            topology = TopologyAnalyzer(config.nodes, config.edges)
            layers = topology.topological_sort()
            result["startup_layers"] = layers
        except Exception as e:
            result["errors"].append({
                "type": "TOPOLOGY_ERROR",
                "message": f"Topology analysis failed: {str(e)}",
                "severity": "error"
            })

        result["is_valid"] = len(result["errors"]) == 0

        # 返回标准化配置
        result["normalized"] = {
            "graph_id": config.graph_id,
            "graph_version": config.graph_version,
            "node_hub_path": config.node_hub_path,
            "nodes": [
                {
                    "id": node.id,
                    "package": node.package,
                    "params": node.params or {}
                }
                for node in config.nodes
            ],
            "edges": [
                {
                    "from": f"{edge.from_node}.{edge.from_port}",
                    "to": f"{edge.to_node}.{edge.to_port}"
                }
                for edge in config.edges
            ]
        }

        return result

    except Exception as e:
        result["errors"].append({
            "type": "PARSE_ERROR",
            "message": f"YAML parsing failed: {str(e)}",
            "severity": "error"
        })
        return result


@safe_execute
async def handle_edit_yaml(arguments: Dict[str, Any]) -> List[TextContent]:
    """处理 YAML 编辑"""
    yaml_path = arguments.get("yaml_path")
    changes = arguments.get("changes", {})
    validate_after_edit = arguments.get("validate_after_edit", True)

    if not Path(yaml_path).exists():
        return create_tool_response(
            {
                "type": "FILE_NOT_FOUND",
                "message": f"YAML file not found: {yaml_path}"
            },
            success=False
        )

    try:
        import yaml

        # 读取现有 YAML
        with open(yaml_path, 'r', encoding='utf-8') as f:
            config = yaml.safe_load(f)

        # 应用更改（支持嵌套路径）
        for key_path, value in changes.items():
            keys = key_path.split('.')
            current = config
            for key in keys[:-1]:
                if key not in current:
                    current[key] = {}
                current = current[key]
            current[keys[-1]] = value

        # 写回文件
        with open(yaml_path, 'w', encoding='utf-8') as f:
            yaml.dump(config, f, default_flow_style=False, allow_unicode=True)

        result = {
            "yaml_path": yaml_path,
            "changes_applied": changes,
            "backup_created": False  # TODO: 实现备份功能
        }

        # 可选：验证修改后的配置
        if validate_after_edit:
            validation_result = await _validate_yaml_file(yaml_path)
            result["validation"] = validation_result

        return create_tool_response(result)

    except Exception as e:
        return create_tool_response(
            {
                "type": "EDIT_ERROR",
                "message": f"Failed to edit YAML: {str(e)}",
                "yaml_path": yaml_path,
                "changes": changes
            },
            success=False
        )


@safe_execute
async def handle_run_runtime(arguments: Dict[str, Any]) -> List[TextContent]:
    """处理运行时启动"""
    yaml_path = arguments.get("yaml_path")
    duration = arguments.get("duration")

    # 验证文件存在
    if not Path(yaml_path).exists():
        return create_tool_response(
            {
                "type": "FILE_NOT_FOUND",
                "message": f"YAML file not found: {yaml_path}"
            },
            success=False
        )

    # 启动运行时
    result = runtime_manager.start_runtime(yaml_path, duration)

    if result.get("success"):
        # 添加一些额外信息
        status = runtime_manager.get_runtime_status()
        result.update({
            "status": "running",
            "uptime": status.uptime_seconds,
            "node_count": status.node_count
        })

    return create_tool_response(result)


@safe_execute
async def handle_stop_runtime(arguments: Dict[str, Any]) -> List[TextContent]:
    """处理运行时停止"""
    timeout = arguments.get("timeout", 10)

    result = runtime_manager.stop_runtime(timeout)

    return create_tool_response(result)


@safe_execute
async def handle_read_logs(arguments: Dict[str, Any]) -> List[TextContent]:
    """处理日志读取"""
    node_id = arguments.get("node_id")
    stream = arguments.get("stream", "both")
    tail = arguments.get("tail")
    max_lines = arguments.get("max_lines", 1000)

    # 验证输入
    if not node_id:
        return create_tool_response(
            {
                "type": "INVALID_INPUT",
                "message": "node_id is required"
            },
            success=False
        )

    result = runtime_manager.read_logs(
        node_id=node_id,
        stream=stream,
        tail=tail,
        max_lines=max_lines
    )

    return create_tool_response(result)


@safe_execute
async def handle_get_runtime_status(arguments: Dict[str, Any]) -> List[TextContent]:
    """处理运行时状态查询"""
    include_details = arguments.get("include_details", True)

    status = runtime_manager.get_runtime_status()

    # 转换为字典格式
    result = {
        "is_running": status.is_running,
        "pid": status.pid,
        "start_time": status.start_time,
        "uptime_seconds": status.uptime_seconds,
        "node_count": status.node_count,
        "log_dir": status.log_dir
    }

    if include_details and status.active_nodes:
        result["active_nodes"] = status.active_nodes

    # 获取可用日志列表
    available_logs = runtime_manager.list_available_logs()
    if available_logs:
        result["available_logs"] = available_logs

    return create_tool_response(result)


async def main():
    """主函数 - 启动 MCP 服务器"""
    # 验证 NodeFlow 环境
    try:
        # 尝试导入关键模块以验证环境
        from runtime.config.yaml_parser import YAMLParser
        from tools.cli.commands.node_cmd import scan_node_packages
        print("NodeFlow MCP Server starting...")
    except ImportError as e:
        print(f"Error: NodeFlow environment not properly set up: {e}")
        sys.exit(1)

    # 启动服务器
    async with stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            InitializationOptions(
                server_name="nodeflow",
                server_version="1.0.0",
                capabilities={
                    "tools": {},
                },
            ),
        )


if __name__ == "__main__":
    asyncio.run(main())