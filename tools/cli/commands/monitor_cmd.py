import time
import json
from pathlib import Path
from runtime.config.yaml_parser import YAMLParser
from sdk.shared_buffer_lite import SharedBufferLite

def _expected_source_buffers(edges):
    items = []
    for e in edges:
        items.append((e.from_node, e.from_port))
    uniq = sorted(set(items))
    return [f"{n}.{p}" for (n, p) in uniq]

def _open_buffers(names):
    res = {}
    for name in names:
        try:
            buf = SharedBufferLite(name, create=False)
            res[name] = buf
        except Exception:
            res[name] = None
    return res

def _read_summary(buf):
    try:
        seq = buf.get_sequence()
        data = buf.read()
        length = 0
        preview = None
        if data is not None:
            try:
                enc = json.dumps(data, ensure_ascii=False)
                length = len(enc.encode("utf-8"))
                if isinstance(data, dict):
                    preview = list(data.keys())[:5]
                else:
                    preview = type(data).__name__
            except Exception:
                length = 0
        return seq, length, preview
    except Exception:
        return 0, 0, None

def handle_monitor_command(args) -> int:
    config_path = Path(args.config)
    interval = float(args.interval)
    iterations = int(args.iterations)
    as_json = bool(getattr(args, "json", False))
    if not config_path.exists():
        print(f"Error: config not found: {config_path}")
        return 1
    parser = YAMLParser()
    config = parser.parse_runtime_config(str(config_path))
    names = args.names if args.names else _expected_source_buffers(config.edges)
    bufs = _open_buffers(names)
    prev = {n: 0 for n in names}
    count = 0
    try:
        while True:
            rows = []
            for n in names:
                b = bufs.get(n)
                if b is None:
                    rows.append({"name": n, "status": "MISSING", "seq": 0, "delta": 0, "len": 0, "preview": None})
                    continue
                seq, length, preview = _read_summary(b)
                delta = seq - prev.get(n, 0)
                prev[n] = seq
                rows.append({"name": n, "status": "OK" if delta > 0 else "STALE", "seq": seq, "delta": delta, "len": length, "preview": preview})
            if as_json:
                print(json.dumps({"timestamp": time.time(), "buffers": rows}, ensure_ascii=False))
            else:
                print(f"\nBuffers @ {time.strftime('%H:%M:%S')} (interval={interval}s)")
                for r in rows:
                    pv = r["preview"]
                    pv_str = ""
                    if pv is None:
                        pv_str = ""
                    elif isinstance(pv, list):
                        pv_str = ",".join(pv)
                    else:
                        pv_str = str(pv)
                    print(f"  {r['name']:30s} {r['status']:6s} seq={r['seq']:6d} Δ={r['delta']:3d} len={r['len']:5d} {pv_str}")
            count += 1
            if iterations > 0 and count >= iterations:
                break
            time.sleep(max(0.01, interval))
    except KeyboardInterrupt:
        pass
    finally:
        for b in bufs.values():
            if b:
                try:
                    b.close()
                except Exception:
                    pass
    return 0

