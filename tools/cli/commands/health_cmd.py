import time
import json
import sys
from pathlib import Path
from typing import Dict, List, Tuple, Any

from runtime.config.yaml_parser import YAMLParser
from sdk.shared_buffer_lite import SharedBufferLite

try:
    from jsonschema import validate, ValidationError
    HAS_JSONSCHEMA = True
except ImportError:
    HAS_JSONSCHEMA = False

def handle_health_command(args) -> int:
    subcommand = getattr(args, "subcommand", None)

    if subcommand == "check":
        return _handle_health_check(args)
    elif subcommand == "flow" or subcommand is None: # Default to flow for backward compatibility
        return _handle_health_flow(args)
    else:
        print(f"Error: Unknown subcommand '{subcommand}'")
        return 1

def _handle_health_flow(args) -> int:
    config_path = Path(args.config)
    buffer_dir = Path(args.dir)
    interval = float(args.interval)
    as_json = bool(getattr(args, "json", False))

    if not config_path.exists():
        print(f"Error: config not found: {config_path}")
        return 1

    if not buffer_dir.exists():
        print(f"Error: buffer dir not found: {buffer_dir}")
        return 1

    parser = YAMLParser()
    config = parser.parse_runtime_config(str(config_path))

    expected = _expected_source_buffers(config.edges)
    results = _sample_buffers(expected, buffer_dir, interval)

    if as_json:
        print(json.dumps({"buffers": results}, ensure_ascii=False, indent=2))
    else:
        print()
        print(f"Health check: {config.graph_id}")
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
        print()

    return 0

def _handle_health_check(args) -> int:
    node_id = args.node_id
    samples = args.samples
    interval = args.interval
    as_json = bool(getattr(args, "json", False))
    
    if not HAS_JSONSCHEMA:
        print("Error: 'jsonschema' library is required for health check.", file=sys.stderr)
        print("Please install it via 'pip install jsonschema' or 'pip install pydantic'", file=sys.stderr)
        return 1

    # 1. 读取元数据
    metadata_buffer_name = f"{node_id}.metadata"
    try:
        meta_buf = SharedBufferLite(metadata_buffer_name, create=False)
        metadata = meta_buf.read()
        meta_buf.close()
    except FileNotFoundError:
        print(f"Error: Metadata buffer not found for node '{node_id}'", file=sys.stderr)
        print("Make sure the node is running and supports schema metadata.", file=sys.stderr)
        return 1
    except Exception as e:
        print(f"Error reading metadata: {e}", file=sys.stderr)
        return 1

    if not metadata or "ports" not in metadata:
        print(f"Error: Invalid metadata for node '{node_id}'", file=sys.stderr)
        return 1

    ports_meta = metadata["ports"]
    results = {}

    print(f"Checking health for node '{node_id}'...")
    if not as_json:
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

    if as_json:
        print(json.dumps(results, ensure_ascii=False, indent=2))
    else:
        print("-" * 60)
        
    return 0

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
            results[name]["status"] = "OK" if delta > 0 else "STALE"
            buf.close()
        except Exception:
            results[name]["status"] = "ERROR"

    return results

