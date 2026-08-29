#!/usr/bin/env python3
"""
Status Command - 单命令聚合运行时事实

回答四个问题：哪些节点在跑、哪些输入断流、数据多旧、最近谁死过。
聚合来源：
- PID 文件（进程存活、启动时间）
- runtime.status 缓冲区（daemon 模式的图配置与数据流状态）
- 图配置 YAML（节点/边，可解析时）
- {node_id}.health 缓冲区（节点心跳新鲜度）
- 数据缓冲区（每输出端口 seq）
- incidents 目录（最近死亡记录摘要）
"""

import json
import time
from pathlib import Path

from tools.cli.commands.runtime_cmd import (
    PID_FILE,
    get_runtime_pid,
    is_runtime_running,
)
from tools.cli.utils.output import print_json


def _read_runtime_status_buffer():
    """读取 daemon 模式发布的 runtime.status 缓冲区（尽力而为）"""
    try:
        from edge.sdk.shared_buffer_lite import SharedBufferLite

        buf = SharedBufferLite("runtime.status", create=False)
        data = buf.read()
        buf.close()
        return data if isinstance(data, dict) else None
    except Exception:
        return None


def _read_pid_file():
    """读取 PID 文件，兼容两行文本与 JSON 两种格式"""
    if not PID_FILE.exists():
        return None
    try:
        raw = PID_FILE.read_text().strip()
        if raw.startswith("{"):
            return json.loads(raw)
        lines = raw.splitlines()
        return {"pid": int(lines[0]), "started_at": float(lines[1]) if len(lines) > 1 else None}
    except (ValueError, IOError, json.JSONDecodeError):
        return None


def _read_health(node_id):
    """读取节点 health 缓冲区并判定新鲜度（与 health status 同一契约：interval*3）"""
    try:
        from edge.sdk.shared_buffer_lite import SharedBufferLite

        buf = SharedBufferLite(f"{node_id}.health", create=False)
        data = buf.read()
        buf.close()
        if not isinstance(data, dict):
            return None
        interval = max(0.1, float(data.get("heartbeat_interval", 2.0)))
        ts = float(data.get("timestamp", 0))
        age = max(0.0, time.time() - ts)
        data["age_seconds"] = round(age, 1)
        data["stale"] = age > interval * 3
        return data
    except Exception:
        return None


def _buffer_info(buffer_name, buffers_dir):
    """输出端口的 seq/尺寸快照（buffer 不存在时返回 exists=False）"""
    path = Path(buffers_dir) / f"{buffer_name}.buf"
    if not path.exists():
        return {"exists": False}
    info = {"exists": True, "size_kb": path.stat().st_size // 1024}
    try:
        from edge.sdk.shared_buffer_lite import SharedBufferLite

        buf = SharedBufferLite(buffer_name, create=False)
        info["seq"] = buf.get_sequence()
        buf.close()
    except Exception as e:
        info["error"] = str(e)
    return info


def _recent_incidents(limit=5):
    """最近死亡记录摘要（incident store 由死亡记录机制提供，未落地时为空）"""
    try:
        from edge.runtime.monitoring.incident_store import list_recent_incidents

        return list_recent_incidents(limit=limit)
    except Exception:
        return []


def collect_status():
    """聚合全部事实，返回 status 字典"""
    from edge.runtime.utils.constants import BUFFERS_DIR

    pid_info = _read_pid_file()
    running = is_runtime_running()
    daemon_status = _read_runtime_status_buffer()

    runtime = {
        "running": running,
        "pid": get_runtime_pid() if running else None,
    }
    if pid_info:
        started_at = pid_info.get("started_at")
        if started_at:
            runtime["started_at"] = started_at
            runtime["uptime_seconds"] = round(time.time() - started_at, 1)
    if daemon_status:
        runtime["mode"] = "daemon"
        runtime["dataflow_running"] = bool(daemon_status.get("dataflow_running"))
        runtime["graph_id"] = daemon_status.get("graph_id", "")
        runtime["config_path"] = daemon_status.get("config_path", "")

    # 图配置（daemon 可提供 config_path；否则从缓冲区名推导）
    nodes_cfg, edges_cfg = _load_graph(runtime.get("config_path"))
    if nodes_cfg is None:
        nodes_cfg, edges_cfg = _derive_graph_from_buffers(BUFFERS_DIR)

    nodes = {}
    problems = []

    for node_id in sorted(nodes_cfg):
        health = _read_health(node_id)
        entry = {
            "running": bool(health and not health.get("stale")),
            "health_status": (health or {}).get("status"),
            "health_age_seconds": (health or {}).get("age_seconds"),
        }
        if health is None:
            entry["health_status"] = "no_heartbeat"
            problems.append(f"node '{node_id}': no health heartbeat")
        elif health.get("stale"):
            entry["health_status"] = "stale"
            problems.append(
                f"node '{node_id}': health stale (age={health['age_seconds']}s)"
            )

        # 输出端口（有配置用配置，没有则跳过）
        entry["outputs"] = {
            port: _buffer_info(f"{node_id}.{port}", BUFFERS_DIR)
            for port in sorted(nodes_cfg[node_id])
        }
        for port, info in entry["outputs"].items():
            if not info.get("exists"):
                problems.append(f"output buffer '{node_id}.{port}' missing")

        # 输入连通性：按边推导，源 buffer 存在且生产者心跳新鲜才算连通
        inputs = {}
        for edge in edges_cfg:
            if edge["to_node"] == node_id:
                source = f"{edge['from_node']}.{edge['from_port']}"
                buf = _buffer_info(source, BUFFERS_DIR)
                producer = _read_health(edge["from_node"])
                connected = bool(buf.get("exists") and producer and not producer.get("stale"))
                inputs[edge["to_port"]] = {
                    "source": source,
                    "connected": connected,
                    "source_seq": buf.get("seq"),
                    "producer_alive": bool(producer and not producer.get("stale")),
                }
                if not connected:
                    problems.append(
                        f"input '{node_id}.{edge['to_port']}' from '{source}' disconnected"
                    )
        entry["inputs"] = inputs
        nodes[node_id] = entry

    return {
        "timestamp": time.time(),
        "runtime": runtime,
        "nodes": nodes,
        "problems": problems,
        "recent_incidents": _recent_incidents(),
    }


def _load_graph(config_path):
    """解析图配置 → ({node_id: [output_ports]}, [edge dicts])；失败返回 (None, None)"""
    if not config_path or not Path(config_path).exists():
        return None, None
    try:
        from edge.runtime.config.yaml_parser import YAMLParser

        config = YAMLParser.parse_runtime_config(config_path)
        nodes_cfg = {}
        for node in config.nodes:
            nodes_cfg[node.id] = []
        edges_cfg = [
            {
                "from_node": e.from_node,
                "from_port": e.from_port,
                "to_node": e.to_node,
                "to_port": e.to_port,
            }
            for e in config.edges
        ]
        # 输出端口名从 buffer 文件反推（node.yaml 端口不进 runtime.yaml）
        for node_id in nodes_cfg:
            nodes_cfg[node_id] = _ports_of_node(node_id)
        return nodes_cfg, edges_cfg
    except Exception:
        return None, None


def _derive_graph_from_buffers(buffers_dir):
    """无图配置时从缓冲区文件名推导节点与边（{node}.{port} 命名约定）"""
    nodes_cfg = {}
    edges_cfg = []
    buf_dir = Path(buffers_dir)
    if not buf_dir.exists():
        return nodes_cfg, edges_cfg

    for f in buf_dir.glob("*.buf"):
        name = f.stem
        if "." not in name or name.endswith((".health", ".metadata")):
            continue
        node_id, port = name.rsplit(".", 1)
        nodes_cfg.setdefault(node_id, []).append(port)

    node_ids = set(nodes_cfg)
    for node_id in node_ids:
        nodes_cfg[node_id] = _ports_of_node(node_id)
    # 无法从文件名推导边，输出空边列表（health/输入连通性仍可用）
    return nodes_cfg, edges_cfg


def _ports_of_node(node_id):
    from edge.runtime.utils.constants import BUFFERS_DIR

    buf_dir = Path(BUFFERS_DIR)
    ports = []
    if buf_dir.exists():
        for f in buf_dir.glob(f"{node_id}.*.buf"):
            name = f.stem
            if name.endswith((".health", ".metadata")):
                continue
            ports.append(name.rsplit(".", 1)[1])
    return sorted(set(ports))


def handle_status_command(args):
    """处理 status 命令"""
    result = collect_status()

    if getattr(args, "json", False):
        print_json(result)
        return 0

    # 人类可读输出
    runtime = result["runtime"]
    if runtime["running"]:
        print(f"✓ Runtime running (PID {runtime['pid']}, uptime {runtime.get('uptime_seconds', 0):.0f}s)")
        if runtime.get("dataflow_running"):
            print(f"  Dataflow: running (graph: {runtime.get('graph_id') or 'unknown'})")
        else:
            print("  Dataflow: not running")
    else:
        print("ℹ Runtime not running")

    print()
    print("Nodes:")
    for node_id, entry in result["nodes"].items():
        marker = "✓" if entry["running"] else "✗"
        health = entry["health_status"] or "unknown"
        age = entry.get("health_age_seconds")
        age_str = f", age={age}s" if age is not None else ""
        print(f"  {marker} {node_id}: {health}{age_str}")
        for in_port, info in entry["inputs"].items():
            state = "connected" if info["connected"] else "DISCONNECTED"
            print(f"      in  {in_port} <- {info['source']}: {state}")
        for out_port, info in entry["outputs"].items():
            if info.get("exists"):
                print(f"      out {out_port}: seq={info.get('seq', '?')}")
            else:
                print(f"      out {out_port}: MISSING")

    if result["recent_incidents"]:
        print()
        print("Recent incidents:")
        for inc in result["recent_incidents"]:
            print(f"  ! {inc.get('ts_wall', '?')} node={inc.get('node_id', '?')} "
                  f"incarnation={inc.get('incarnation', '?')} exit_code={inc.get('exit_code', '?')}")

    if result["problems"]:
        print()
        print("Problems:")
        for p in result["problems"]:
            print(f"  ! {p}")

    return 0
