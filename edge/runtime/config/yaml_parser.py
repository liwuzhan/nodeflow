"""
YAML解析器模块
负责解析运行时配置和节点说明书
"""

import yaml
from pathlib import Path
from typing import Dict, Any

from edge.runtime.config.models import (
    RuntimeConfig, NodeInstance, Edge, RestartPolicy,
    NodeManifest, PortDef, EntryPoint, ParamSchema,
    FailurePolicy, OutputPolicy, ResourceAction, SafetyResourceBinding,
    VALID_OUTPUT_STRATEGIES, VALID_APPLY_ON, VALID_ANTI_REPLAY,
    VALID_SAFETY_HANDLERS,
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

            # 解析图级安全资源绑定（2026-09-01 草案，缺省为空 = 全 dry-run）
            safety_resources = {}
            for res_name, res_data in (data.get('safety_resources') or {}).items():
                if not res_data or 'owner' not in res_data:
                    raise YAMLParseError(
                        f"safety_resources.{res_name} must declare 'owner'"
                    )
                handler = res_data.get('handler', '')
                if handler not in VALID_SAFETY_HANDLERS:
                    raise YAMLParseError(
                        f"safety_resources.{res_name}: handler '{handler}' not in whitelist "
                        f"{sorted(VALID_SAFETY_HANDLERS)}"
                    )
                safety_resources[res_name] = SafetyResourceBinding(
                    owner=res_data['owner'],
                    handler=handler,
                    params_from_owner=dict(res_data.get('params_from_owner') or {}),
                    dry_run=bool(res_data.get('dry_run', True)),
                )

            # 创建RuntimeConfig对象
            config = RuntimeConfig(
                graph_id=data['graph_id'],
                graph_version=data.get('graph_version', 1),
                node_hub_path=data.get('node_hub_path', './edge/nodes'),
                nodes=nodes,
                edges=edges,
                restart_policy=restart_policy,
                safety_resources=safety_resources,
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

            # 解析异常退出安全契约（草案 2026-09-01）：非法枚举必须报错，
            # 杜绝"写进 node.yaml 被静默忽略、误以为已有安全行为"（§3.1）
            failure_policy = None
            fp_data = data.get('failure_policy')
            if fp_data:
                apply_on = [str(a) for a in fp_data.get('apply_on', ['abnormal_exit'])]
                bad_apply = [a for a in apply_on if a not in VALID_APPLY_ON]
                if bad_apply:
                    raise YAMLParseError(
                        f"failure_policy.apply_on contains unsupported values {bad_apply}; "
                        f"supported: {sorted(VALID_APPLY_ON)}"
                    )

                fp_outputs = {}
                for port_name, out_data in (fp_data.get('outputs') or {}).items():
                    strategy = out_data.get('strategy', '')
                    if strategy not in VALID_OUTPUT_STRATEGIES:
                        raise YAMLParseError(
                            f"failure_policy.outputs.{port_name}.strategy '{strategy}' invalid; "
                            f"must be one of {sorted(VALID_OUTPUT_STRATEGIES)}"
                        )
                    fp_outputs[port_name] = OutputPolicy(
                        strategy=strategy,
                        value=out_data.get('value'),
                        reason=out_data.get('reason'),
                        completion=out_data.get('completion'),
                    )

                anti_replay = {}
                for port_name, mode in (fp_data.get('anti_replay') or {}).items():
                    if mode not in VALID_ANTI_REPLAY:
                        raise YAMLParseError(
                            f"failure_policy.anti_replay.{port_name} '{mode}' invalid; "
                            f"must be one of {sorted(VALID_ANTI_REPLAY)}"
                        )
                    anti_replay[port_name] = mode

                deadline = fp_data.get('deadline_ms')
                if deadline is not None:
                    try:
                        deadline = float(deadline)
                    except (TypeError, ValueError):
                        raise YAMLParseError(
                            f"failure_policy.deadline_ms must be a number or null, got: {deadline}"
                        )

                failure_policy = FailurePolicy(
                    apply_on=apply_on,
                    outputs=fp_outputs,
                    resources={
                        str(r): ResourceAction(action=(rdata or {}).get('action', ''))
                        for r, rdata in (fp_data.get('resources') or {}).items()
                    },
                    anti_replay=anti_replay,
                    rearm=fp_data.get('rearm'),
                    deadline_ms=deadline,
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
                failure_policy=failure_policy,
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
