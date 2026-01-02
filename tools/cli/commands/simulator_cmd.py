import zmq
import json
import sys


def handle_simulator_command(args) -> int:
    if args.subcommand == 'refresh':
        return _refresh_field(args.host, int(args.port))
    print(f"Error: Unknown simulator subcommand '{args.subcommand}'", file=sys.stderr)
    return 1


def _refresh_field(host: str, port: int) -> int:
    try:
        ctx = zmq.Context()
        sock = ctx.socket(zmq.REQ)
        sock.connect(f"tcp://{host}:{port}")
        sock.setsockopt(zmq.RCVTIMEO, 2000)
        sock.setsockopt(zmq.SNDTIMEO, 2000)
        req = {"type": "refresh_field"}
        sock.send_json(req)
        resp = sock.recv_json()
        if resp.get("status") == "ok":
            ver = resp.get("version")
            fld = resp.get("field")
            print(json.dumps({"status": "ok", "version": ver, "field_summary": {
                "type": fld.get("type"),
                "area": fld.get("area"),
                "outer_points": len(fld.get("boundary", [])),
                "holes": len(fld.get("holes", [])),
            }}, ensure_ascii=False, indent=2))
            sock.close()
            ctx.term()
            return 0
        else:
            print(f"Error: {resp.get('message','unknown error')}", file=sys.stderr)
            sock.close()
            ctx.term()
            return 1
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1

