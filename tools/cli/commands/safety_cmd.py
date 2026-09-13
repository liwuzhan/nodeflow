#!/usr/bin/env python3
"""
Safety Command - 资源安全锁存的查看与人工 rearm

- safety status：读取控制面 runtime.safety buffer，展示各资源锁存状态
- safety rearm <resource>：人工授权解除锁存（manual_then_fresh），
  经 runtime.control 发送命令，由 daemon 执行并递增 epoch

注意：锁存 buffer 固定在根目录，不随 run 漂移，无需 runtime 运行也可 status。
"""

import time

from tools.cli.commands.runtime_cmd import is_runtime_running
from tools.cli.utils.output import print_json


def _read_latch_snapshot():
    try:
        from edge.sdk.shared_buffer_lite import SharedBufferLite

        buf = SharedBufferLite("runtime.safety", create=False)
        data = buf.read()
        buf.close()
        return data if isinstance(data, dict) else None
    except Exception:
        return None


def safety_status():
    """当前锁存快照（buffer 不存在 = 从未断言）"""
    snapshot = _read_latch_snapshot()
    if snapshot is None:
        return {"status": "no_latch_buffer", "resources": {},
                "message": "从未断言过资源锁存（无 runtime.safety buffer）"}

    resources = snapshot.get("resources") or {}
    return {
        "status": "ok",
        "ts": snapshot.get("ts"),
        "resources": {
            name: {
                "latched": bool(entry.get("latched")),
                "epoch": entry.get("epoch", 0),
                "faults": entry.get("faults", []),
                "rearmed_at": entry.get("rearmed_at"),
            }
            for name, entry in resources.items()
        },
    }


def safety_rearm(resource):
    """人工 rearm：经 daemon 控制通道执行（CLI 不直接写锁存 buffer）"""
    if not is_runtime_running():
        return {"status": "not_running",
                "message": "Runtime is not running; rearm must go through the runtime"}

    try:
        from edge.sdk.shared_buffer_lite import SharedBufferLite

        buf = SharedBufferLite("runtime.control", create=False)
        buf.write({
            "command": "safety_rearm",
            "resource": resource,
            "timestamp": time.time(),
            "source": "safety_cli",
        })
        buf.close()
    except Exception as e:
        return {"status": "error", "message": f"Failed to send rearm command: {e}"}

    # 等待 daemon 执行并落盘（锁存 buffer 状态翻转）
    deadline = time.time() + 5.0
    while time.time() < deadline:
        snapshot = _read_latch_snapshot() or {}
        entry = (snapshot.get("resources") or {}).get(resource)
        if entry and not entry.get("latched"):
            return {"status": "success",
                    "message": f"Resource '{resource}' rearmed (epoch={entry.get('epoch')})"}
        time.sleep(0.2)

    return {"status": "timeout",
            "message": f"Rearm command sent but '{resource}' still latched after 5s; "
                       f"check runtime logs"}


def handle_safety_command(args):
    subcommand = args.subcommand

    if subcommand == "status":
        result = safety_status()
    elif subcommand == "rearm":
        result = safety_rearm(args.resource)
    else:
        result = {"status": "error", "message": f"Unknown subcommand: {subcommand}"}

    if getattr(args, "json", False):
        print_json(result)
    else:
        if result.get("status") == "ok":
            print("Safety latch state:")
            for name, entry in result["resources"].items():
                state = "LATCHED" if entry["latched"] else "released"
                print(f"  {name}: {state} (epoch={entry['epoch']})")
                for f in entry.get("faults", []):
                    print(f"      fault: {f.get('source', '?')} @ {f.get('ts', '?')}")
        elif result.get("status") == "no_latch_buffer":
            print(f"ℹ {result.get('message')}")
        elif result.get("status") == "success":
            print(f"✓ {result.get('message')}")
        else:
            print(f"✗ {result.get('message', result.get('status'))}")

    if result.get("status") in {"ok", "success", "no_latch_buffer"}:
        return 0
    return 1
