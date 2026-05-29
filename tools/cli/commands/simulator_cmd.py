import zmq
import json
import sys

from tools.cli.utils.output import print_error, print_json


def handle_simulator_command(args) -> int:
    as_json = bool(getattr(args, "json", False))
    if args.subcommand == 'refresh':
        return _refresh_field(args.host, int(args.port), as_json=as_json)
    print_error(f"Unknown simulator subcommand '{args.subcommand}'", as_json=as_json)
    return 1


def _refresh_field(host: str, port: int, *, as_json: bool = False) -> int:
    ctx = None
    sock = None
    try:
        ctx = zmq.Context()
        sock = ctx.socket(zmq.REQ)
        sock.setsockopt(zmq.LINGER, 0)
        sock.setsockopt(zmq.RCVTIMEO, 2000)
        sock.setsockopt(zmq.SNDTIMEO, 2000)
        sock.connect(f"tcp://{host}:{port}")
        req = {"type": "refresh_field"}
        sock.send_json(req)
        resp = sock.recv_json()
        if resp.get("status") == "ok":
            ver = resp.get("version")
            fld = resp.get("field") or {}
            result = {"status": "ok", "version": ver, "field_summary": {
                "type": fld.get("type"),
                "area": fld.get("area"),
                "outer_points": len(fld.get("boundary", [])),
                "holes": len(fld.get("holes", [])),
            }}
            if as_json:
                print_json(result)
            else:
                print(json.dumps(result, ensure_ascii=False, indent=2))
            return 0
        else:
            print_error(resp.get('message', 'unknown error'), as_json=as_json)
            return 1
    except zmq.Again:
        print_error(
            f"Simulator request timed out: tcp://{host}:{port}",
            as_json=as_json,
            code="timeout",
        )
        return 1
    except Exception as e:
        print_error(str(e), as_json=as_json)
        return 1
    finally:
        if sock is not None:
            sock.close(0)
        if ctx is not None:
            ctx.term()
