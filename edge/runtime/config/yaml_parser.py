"""
YAML解析器模块
负责解析运行时配置和节点说明书
"""

import yaml
from pathlib import Path
from typing import Dict, Any

from edge.runtime.config.models import (
    RuntimeConfig, NodeInstance, Edge, RestartPolicy,
    NodeManifest, PortDef, EntryPoint, ParamSchema
)
from edge.runtime.utils.errors import YAMLParseError
from edge.runtime.utils.logger import get_logger

logger = get_logger(__name__)


class YAMLParser:
    """YAML解析器"""

    @staticmethod
    def parse_runtime_config(file_path: str) -> RuntimeConfig:
        """
        解析运行时配置文件 (runtime.yaml)

        参数：
        - file_path: YAML文件路径

        返回：
        - RuntimeConfig对象

        异常：
        - YAMLParseError: 解析失败
        """
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                data = yaml.safe_load(f)

            if not data:
                raise YAMLParseError(f"Empty YAML file: {file_path}")

            # 解析节点实例列表
            nodes = []
            for node_data in data.get('nodes', []):
                # 解析entrypoint（如果有覆盖）
                entrypoint = None
                if 'entrypoint' in node_data:
                    ep_data = node_data['entrypoint']
                    entrypoint = EntryPoint(
                        kind=ep_data.get('kind', ''),
                        cmd=ep_data.get('cmd', [])
                    )

                node = NodeInstance(
                    id=node_data['id'],
                    package=node_data['package'],
                    params=node_data.get('params', {}),
                    entrypoint=entrypoint
                )
                nodes.append(node)

            # 解析边连接列表
            edges = []
            for edge_data in data.get('edges', []):
                # 解析 from 和 to 字段：格式为 "node_id.port_name"
                from_parts = edge_data['from'].split('.', 1)
                to_parts = edge_data['to'].split('.', 1)

                if len(from_parts) != 2:
                    raise YAMLParseError(f"Invalid edge 'from' format: {edge_data['from']}. Expected 'node_id.port_name'")
                if len(to_parts) != 2:
                    raise YAMLParseError(f"Invalid edge 'to' format: {edge_data['to']}. Expected 'node_id.port_name'")

                edge = Edge(
                    from_node=from_parts[0],
                    from_port=from_parts[1],
                    to_node=to_parts[0],
                    to_port=to_parts[1],
                    type=edge_data.get('type')
                )
                edges.append(edge)

            # 解析重启策略
            restart_policy_data = data.get('restart_policy', {})
            restart_policy = RestartPolicy(
                max_retries=restart_policy_data.get('max_retries', 3),
                backoff_ms=restart_policy_data.get('backoff_ms', 500)
            )

            # 创建RuntimeConfig对象
            config = RuntimeConfig(
                graph_id=data['graph_id'],
                graph_version=data.get('graph_version', 1),
                node_hub_path=data.get('node_hub_path', './edge/nodes'),
                nodes=nodes,
                edges=edges,
                restart_policy=restart_policy
            )

            logger.info(f"Parsed runtime config: {config.graph_id} (version {config.graph_version})")
            logger.debug(f"Loaded {len(nodes)} nodes, {len(edges)} edges")

            return config

        except yaml.YAMLError as e:
            raise YAMLParseError(f"Failed to parse YAML file {file_path}: {e}")
        except KeyError as e:
            raise YAMLParseError(f"Missing required field in {file_path}: {e}")
        except FileNotFoundError:
            raise YAMLParseError(f"File not found: {file_path}")
        except Exception as e:
            raise YAMLParseError(f"Unexpected error parsing {file_path}: {e}")

    @staticmethod
    def parse_node_manifest(file_path: str) -> NodeManifest:
        """
        解析节点说明书 (node.yaml)

        参数：
        - file_path: YAML文件路径

        返回：
        - NodeManifest对象

        异常：
        - YAMLParseError: 解析失败
        """
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                data = yaml.safe_load(f)

            if not data:
                raise YAMLParseError(f"Empty YAML file: {file_path}")

            # 解析entrypoints
            entrypoints = {}
            for platform, ep_data in data.get('entrypoints', {}).items():
                entrypoints[platform] = EntryPoint(
                    kind=ep_data.get('kind', ''),
                    cmd=ep_data.get('cmd', [])
                )

            # 解析ports
            ports_data = data.get('ports', {})

            # 输入端口
            inputs = []
            for port_data in ports_data.get('inputs', []):
                inputs.append(PortDef(
                    name=port_data['name'],
                    type=port_data.get('type', 'any'),
                    description=port_data.get('description', ''),
                    buffer_size=port_data.get('buffer_size', 1024 * 1024),
                    conflate=port_data.get('conflate', True)
                ))

            # 输出端口
            outputs = []
            for port_data in ports_data.get('outputs', []):
                outputs.append(PortDef(
                    name=port_data['name'],
                    type=port_data.get('type', 'any'),
                    description=port_data.get('description', ''),
                    buffer_size=port_data.get('buffer_size', 1024 * 1024),
                    conflate=port_data.get('conflate', True)
                ))

            # 解析params
            params = {}
            for param_name, param_data in data.get('params', {}).items():
                # 如果param_data是None，设置为默认值
                if param_data is None:
                    param_data = {}

                params[param_name] = ParamSchema(
                    type=param_data.get('type', 'any'),
                    required=param_data.get('required', False),
                    default=param_data.get('default'),
                    description=param_data.get('description', '')
                )

            # 创建NodeManifest对象
            manifest = NodeManifest(
                name=data['name'],
                version=data.get('version', '0.1.0'),
                description=data.get('description', ''),
                entrypoints=entrypoints,
                inputs=inputs,
                outputs=outputs,
                params=params,
                readiness=data.get('readiness', 'heartbeat'),
                input_watchdog={
                    str(k): float(v)
                    for k, v in (data.get('input_watchdog') or {}).items()
                    if v is not None
                },
            )

            logger.debug(f"Parsed node manifest: {manifest.name} (version {manifest.version})")

            return manifest

        except yaml.YAMLError as e:
            raise YAMLParseError(f"Failed to parse YAML file {file_path}: {e}")
        except KeyError as e:
            raise YAMLParseError(f"Missing required field in {file_path}: {e}")
        except FileNotFoundError:
            raise YAMLParseError(f"File not found: {file_path}")
        except Exception as e:
            raise YAMLParseError(f"Unexpected error parsing {file_path}: {e}")
