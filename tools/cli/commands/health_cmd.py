import os
import time
import json
import sys
from pathlib import Path
from typing import Dict, List, Tuple, Any

from edge.runtime.config.yaml_parser import YAMLParser
from edge.sdk.shared_buffer_lite import SharedBufferLite
from tools.cli.utils.output import print_error, print_json, redirect_library_stdout_when_json
from tools.cli.commands.runtime_cmd import is_runtime_running

try:
    from jsonschema import validate, ValidationError
    HAS_JSONSCHEMA = True
except ImportError:
    HAS_JSONSCHEMA = False

def handle_health_command(args) -> int:
    subcommand = getattr(args, "subcommand", None)
    as_json = bool(getattr(args, "json", False))

    if subcommand == "check":
        return _handle_health_check(args)
    elif subcommand == "flow" or subcommand is None: # Default to flow for backward compatibility
        return _handle_health_flow(args)
    elif subcommand == "status":
        return handle_health_status(args)
    else:
        print_error(f"Unknown subcommand '{subcommand}'", as_json=as_json)
        return 1

def _handle_health_flow(args) -> int:
    config_path = Path(args.config)
    buffer_dir = Path(args.dir)
    interval = float(args.interval)
    as_json = bool(getattr(args, "json", False))
    runtime_running = is_runtime_running()

    if not config_path.exists():
        print_error(f"config not found: {config_path}", as_json=as_json, code="not_found")
        return 1

    if not buffer_dir.exists():
        results = {}
        graph_id = None
        with redirect_library_stdout_when_json(as_json):
            parser = YAMLParser()
            config = parser.parse_runtime_config(str(config_path))
        graph_id = config.graph_id
        expected = _expected_source_buffers(config.edges)
        for name in expected:
            results[name] = {
                "status": "MISSING",
                "seq_start": 0,
                "seq_end": 0,
                "delta": 0,
                "length": 0,
                "size_kb": 0,
            }
        return _emit_flow_results(graph_id, results, as_json, runtime_running)

    with redirect_library_stdout_when_json(as_json):
        parser = YAMLParser()
        config = parser.parse_runtime_config(str(config_path))

    expected = _expected_source_buffers(config.edges)
    results = _sample_buffers(expected, buffer_dir, interval)

    return _emit_flow_results(config.graph_id, results, as_json, runtime_running)

def _emit_flow_results(
    graph_id: str,
    results: Dict[str, Dict],
    as_json: bool,
    runtime_running: bool = True,
) -> int:
    counts: Dict[str, int] = {}
    for r in results.values():
        counts[r["status"]] = counts.get(r["status"], 0) + 1
    healthy_statuses = {"OK", "IDLE"}
    healthy = bool(results) and all(
        r["status"] in healthy_statuses for r in results.values()
    )
    summary = {
        "status": "ok" if healthy else "unhealthy",
        "graph_id": graph_id,
        "runtime_running": runtime_running,
        "total": len(results),
        "counts": counts,
        "buffers": results,
    }
    if not runtime_running:
        summary["reason"] = "runtime_not_running"
        summary["message"] = (
            "Runtime is not running; missing or stale buffers may simply mean "
            "the dataflow has not been started."
        )
    if as_json:
        print(json.dumps(summary, ensure_ascii=False, indent=2))
    else:
        print()
        print(f"Health check: {graph_id}")
        if not runtime_running:
            print("Runtime: not running (buffer status may reflect an idle dataflow)")
        print("-" * 80)
        for name, r in results.items():
            status = r["status"]
            seq0 = r["seq_start"]
            seq1 = r["seq_end"]
            delta = r["delta"]
            length = r["length"]
            size_kb = r["size_kb"]
            print(
                f"  {name:30s} status={status:8s} "
                f"seq={seq0}->{seq1} (+{delta}) len={length} bytes size={size_kb}KB"
            )
        print("-" * 80)
        print(f"Summary: {summary['status']} {counts}")
        print()

    return 0 if healthy else 2

def _handle_health_check(args) -> int:
    node_id = args.node_id
    samples = args.samples
    interval = args.interval
    as_json = bool(getattr(args, "json", False))
    
    if not HAS_JSONSCHEMA:
        print_error("'jsonschema' library is required for health check.", as_json=as_json, code="dependency_missing")
        return 1

    # 1. 读取元数据
    metadata_buffer_name = f"{node_id}.metadata"
    try:
        meta_buf = SharedBufferLite(metadata_buffer_name, create=False)
        metadata = meta_buf.read()
        meta_buf.close()
    except FileNotFoundError:
        print_error(
            f"Metadata buffer not found for node '{node_id}'",
            as_json=as_json,
            code="not_found",
        )
        return 1
    except Exception as e:
        print_error(f"Error reading metadata: {e}", as_json=as_json)
        return 1

    if not metadata or "ports" not in metadata:
        print_error(f"Invalid metadata for node '{node_id}'", as_json=as_json)
        return 1

    ports_meta = metadata["ports"]
    results = {}

    if not as_json:
        print(f"Checking health for node '{node_id}'...")
        print("-" * 60)

    # 2. 遍历每个端口进行检查
    for port_name, meta in ports_meta.items():
        if meta.get("type") != "output":
            continue
            
        schema = meta.get("schema")
        buffer_name = f"{node_id}.{port_name}"
        
        port_result = {
            "has_schema": bool(schema),
            "sampled": 0,
            "valid": 0,
            "invalid": 0,
            "errors": {}
        }

        if not schema:
            if not as_json:
                print(f"Port: {port_name} (No Schema Defined) - SKIPPED")
            results[port_name] = port_result
            continue

        try:
            data_buf = SharedBufferLite(buffer_name, create=False)
        except FileNotFoundError:
            if not as_json:
                print(f"Port: {port_name} (Buffer Not Found) - SKIPPED")
            results[port_name] = port_result
            continue

        # 采样校验
        last_seq = 0
        collected = 0
        
        if not as_json:
            print(f"Port: {port_name} (Checking...) ", end="", flush=True)

        for _ in range(samples):
            current_seq = data_buf.get_sequence()
            if current_seq > last_seq:
                data = data_buf.read()
                last_seq = current_seq
                
                if data is not None:
                    collected += 1
                    try:
                        validate(instance=data, schema=schema)
                        port_result["valid"] += 1
                    except ValidationError as e:
                        port_result["invalid"] += 1
                        error_msg = e.message
                        port_result["errors"][error_msg] = port_result["errors"].get(error_msg, 0) + 1
            
            time.sleep(interval)
        
        port_result["sampled"] = collected
        data_buf.close()
        results[port_name] = port_result

        if not as_json:
            rate = (port_result["valid"] / collected * 100) if collected > 0 else 0.0
            print(f"Sampled: {collected}, Valid: {port_result['valid']} ({rate:.1f}%)")
            if port_result["invalid"] > 0:
                print("  Errors:")
                for msg, count in port_result["errors"].items():
                    print(f"    - {msg} (x{count})")

    invalid = sum(r["invalid"] for r in results.values())
    if as_json:
        print(json.dumps({
            "status": "ok" if invalid == 0 else "unhealthy",
            "node_id": node_id,
            "ports": results,
        }, ensure_ascii=False, indent=2))
    else:
        print("-" * 60)
        
    return 0 if invalid == 0 else 2

def _expected_source_buffers(edges) -> List[Tuple[str, str]]:
    items = []
    for e in edges:
        items.append((e.from_node, e.from_port))
    uniq = sorted(set(items))
    names = [f"{n}.{p}" for (n, p) in uniq]
    return names


def _sample_buffers(names: List[str], buffer_dir: Path, interval: float) -> Dict[str, Dict]:
    results: Dict[str, Dict] = {}
    instances: Dict[str, SharedBufferLite] = {}

    for name in names:
        path = buffer_dir / f"{name}.buf"
        if not path.exists():
            results[name] = {
                "status": "MISSING",
                "seq_start": 0,
                "seq_end": 0,
                "delta": 0,
                "length": 0,
                "size_kb": 0,
            }
            continue
        try:
            buf = SharedBufferLite(name, create=False)
            instances[name] = buf
            seq0 = buf.get_sequence()
            length = 0
            if seq0 > 0:
                data = buf.read()
                if data is not None:
                    try:
                        encoded = json.dumps(data).encode("utf-8")
                        length = len(encoded)
                    except Exception:
                        length = 0
            results[name] = {
                "status": "PRESENT",
                "seq_start": seq0,
                "seq_end": seq0,
                "delta": 0,
                "length": length,
                "size_kb": (buf.size // 1024),
            }
        except Exception:
            results[name] = {
                "status": "ERROR",
                "seq_start": 0,
                "seq_end": 0,
                "delta": 0,
                "length": 0,
                "size_kb": 0,
            }

    time.sleep(max(0.01, interval))

    for name, buf in instances.items():
        try:
            seq1 = buf.get_sequence()
            delta = seq1 - results[name]["seq_start"]
            results[name]["seq_end"] = seq1
            results[name]["delta"] = delta
            if delta > 0:
                results[name]["status"] = "OK"
            elif results[name]["length"] > 0 and _producer_health_is_fresh(name):
                # Static outputs such as task/field configuration are valid even
                # when their sequence does not change during the sample window.
                # A fresh producer heartbeat distinguishes that normal idle state
                # from a dead producer leaving stale data behind.
                results[name]["status"] = "IDLE"
            else:
                results[name]["status"] = "STALE"
            buf.close()
        except Exception:
            results[name]["status"] = "ERROR"

    return results


def _producer_health_is_fresh(buffer_name: str, now: float | None = None) -> bool:
    node_id = buffer_name.split(".", 1)[0]
    health_buf = None
    try:
        health_buf = SharedBufferLite(f"{node_id}.health", create=False)
        health = health_buf.read()
        if not health or health.get("status") not in {"ok", "healthy"}:
            return False

        timestamp = float(health.get("timestamp", 0))
        heartbeat_interval = max(0.1, float(health.get("heartbeat_interval", 2.0)))
        age = (time.time() if now is None else now) - timestamp
        return 0 <= age <= heartbeat_interval * 3
    except Exception:
        return False
    finally:
        if health_buf is not None:
            try:
                health_buf.close()
            except Exception:
                pass


def handle_health_status(args) -> int:
    """查询节点健康状态"""
    node_id = args.node_id
    as_json = bool(getattr(args, "json", False))

    buffer_name = f"{node_id}.health"

    try:
        buf = SharedBufferLite(buffer_name, create=False)
        health_data = buf.read()
        buf.close()
    except FileNotFoundError:
        print_error(
            f"Health buffer not found for node '{node_id}'",
            as_json=as_json,
            code="not_found",
        )
        return 1
    except Exception as e:
        print_error(f"Error reading health data: {e}", as_json=as_json)
        return 1

    if not health_data:
        print_error(
            f"No health data available for node '{node_id}'",
            as_json=as_json,
            code="empty",
        )
        return 1

    ts = health_data.get("timestamp", 0)
    # 从健康数据中读取心跳间隔（生产者写入的契约），兜底 2s
    interval = float(health_data.get("heartbeat_interval", 2.0))
    stale_timeout = interval * 3
    age = time.time() - ts
    is_stale = age > stale_timeout
    effective_status = "stale" if is_stale else health_data.get("status", "unknown")

    if as_json:
        print_json({
            "status": effective_status,
            "stale": is_stale,
            "age_seconds": round(age, 1),
            "node_id": node_id,
            "incarnation": health_data.get("incarnation"),
            "health": health_data,
        })
    else:
        status_label = f"{effective_status} (stale, age={age:.0f}s)" if is_stale else effective_status
        print(f"\nHealth Status for '{node_id}':")
        print(f"  Status: {status_label}")
        print(f"  Timestamp: {health_data.get('timestamp', 'N/A')}")
        # incarnation 为 health v2 字段；旧节点缺失时降级显示
        incarnation = health_data.get("incarnation")
        if incarnation is not None:
            print(f"  Incarnation: {incarnation}")
        print(f"  Inputs: {json.dumps(health_data.get('inputs', {}), indent=4)}")
        print(f"  Outputs: {json.dumps(health_data.get('outputs', {}), indent=4)}")
        print()

    return 0
