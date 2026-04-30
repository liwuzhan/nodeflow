#!/usr/bin/env python3
"""
端到端集成测试工具

用法:
    python3 tests/e2e_cli.py start          # 启动所有服务
    python3 tests/e2e_cli.py test [--wait]  # 运行测试场景
    python3 tests/e2e_cli.py status         # 查看当前状态
    python3 tests/e2e_cli.py stop           # 停止所有服务
    python3 tests/e2e_cli.py clean          # 清理 (停止+删除DB+buffer)

环境变量:
    NF_MACHINE_ID   端侧机器 ID (默认: tractor-01)
    BROKER_PORT     MQTT broker 端口 (默认: 1883)
    CLOUD_PORT      云服务端口 (默认: 8080)
"""

import argparse
import json
import os
import signal
import subprocess
import sys
import time
import urllib.request
import urllib.error
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
CLOUD_DIR = PROJECT_ROOT / "cloud" / "server"
DB_PATH = CLOUD_DIR / "farm.db"
PID_DIR = Path("/tmp/nodeflow_e2e")

MACHINE_ID = os.getenv("NF_MACHINE_ID", "tractor-01")
BROKER_PORT = os.getenv("BROKER_PORT", "1883")
CLOUD_PORT = os.getenv("CLOUD_PORT", "8080")
CLOUD_URL = f"http://localhost:{CLOUD_PORT}"

MOSQUITTO_BIN = "/opt/homebrew/sbin/mosquitto"

# ── helpers ────────────────────────────────────────────────────────────


def _api(method: str, path: str, data: dict | None = None) -> dict:
    url = f"{CLOUD_URL}/api/v1{path}"
    body = json.dumps(data).encode() if data else None
    req = urllib.request.Request(url, data=body, method=method)
    req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        err = e.read().decode()
        try:
            err = json.loads(err).get("detail", err)
        except Exception:
            pass
        return {"error": True, "status": e.code, "detail": str(err)}
    except urllib.error.URLError as e:
        return {"error": True, "detail": f"Cannot connect to cloud server: {e.reason}"}


def _run_bg(cmd: list[str], name: str, env: dict | None = None) -> subprocess.Popen:
    PID_DIR.mkdir(parents=True, exist_ok=True)
    pidfile = PID_DIR / f"{name}.pid"
    logfile = PID_DIR / f"{name}.log"

    full_env = os.environ.copy()
    if env:
        full_env.update(env)

    with open(logfile, "w") as f:
        proc = subprocess.Popen(cmd, env=full_env, stdout=f, stderr=subprocess.STDOUT)
    pidfile.write_text(str(proc.pid))
    return proc


def _is_running(name: str) -> bool:
    pidfile = PID_DIR / f"{name}.pid"
    if not pidfile.exists():
        return False
    try:
        pid = int(pidfile.read_text().strip())
        os.kill(pid, 0)
        return True
    except (ValueError, OSError, ProcessLookupError):
        pidfile.unlink(missing_ok=True)
        return False


def _verify_pid(pid: int, expected_name: str) -> bool:
    """验证 PID 对应的进程命令行是否匹配预期"""
    try:
        result = subprocess.run(
            ["ps", "-p", str(pid), "-o", "command="],
            capture_output=True, text=True, timeout=3,
        )
        cmdline = result.stdout.strip()
        return expected_name in cmdline or "nodeflow" in cmdline.lower()
    except Exception:
        return False


def _stop(name: str):
    pidfile = PID_DIR / f"{name}.pid"
    if not pidfile.exists():
        return
    try:
        pid = int(pidfile.read_text().strip())
        if not _verify_pid(pid, name):
            print(f"  ⚠ PID {pid} 不是 {name} 进程，跳过")
            pidfile.unlink(missing_ok=True)
            return
        os.kill(pid, signal.SIGTERM)
        time.sleep(0.5)
        try:
            os.kill(pid, 0)
            os.kill(pid, signal.SIGKILL)
        except OSError:
            pass
    except (ValueError, OSError):
        pass
    pidfile.unlink(missing_ok=True)


def _log_tail(name: str, lines: int = 10):
    logfile = PID_DIR / f"{name}.log"
    if logfile.exists():
        content = logfile.read_text()
        return "\n".join(content.strip().split("\n")[-lines:])
    return "(no log)"


def _wait_cloud_ready(timeout: float = 10) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            r = _api("GET", "/health")
            if r.get("status") == "ok":
                return True
        except Exception:
            pass
        time.sleep(0.5)
    return False


# ── commands ───────────────────────────────────────────────────────────


def cmd_start(args):
    """启动所有服务"""
    print("══ NodeFlow E2E — 启动所有服务 ══\n")

    # 1. mosquitto
    if _is_running("mosquitto"):
        print("⏭  mosquitto 已运行")
    else:
        print("▶  mosquitto", end=" ", flush=True)
        proc = _run_bg([MOSQUITTO_BIN, "-p", BROKER_PORT], "mosquitto")
        time.sleep(1.5)
        if _is_running("mosquitto"):
            print("✓")
        else:
            print("✗ 启动失败")
            return 1

    # 2. cloud server
    if _is_running("cloud"):
        print("⏭  cloud server 已运行")
    else:
        print("▶  cloud server", end=" ", flush=True)
        if DB_PATH.exists():
            DB_PATH.unlink()
        _run_bg(
            [sys.executable, "-m", "uvicorn", "cloud.server.app:app",
             "--host", "0.0.0.0", "--port", CLOUD_PORT],
            "cloud",
            env={"PYTHONPATH": str(PROJECT_ROOT)},
        )
        time.sleep(3)
        if _wait_cloud_ready():
            print("✓")
        else:
            print("✗ 启动超时")
            return 1

    # 3. edge daemon — auto-pick a config
    config_path = args.config or "examples/tillage_operation.yaml"
    if _is_running("daemon"):
        print("⏭  edge daemon 已运行")
    else:
        print(f"▶  edge daemon [{config_path}]", end=" ", flush=True)
        _run_bg(
            [sys.executable, "-m", "runtime.main", config_path, "--daemon"],
            "daemon",
            env={"PYTHONPATH": str(PROJECT_ROOT)},
        )
        time.sleep(3)
        if _is_running("daemon"):
            print("✓")
        else:
            print("✗ 启动失败")
            return 1

    # 4. TaskAgent
    if _is_running("agent"):
        print("⏭  TaskAgent 已运行")
    else:
        print("▶  TaskAgent", end=" ", flush=True)
        _run_bg(
            [sys.executable, "-m", "runtime.task.agent_main"],
            "agent",
            env={
                "PYTHONPATH": str(PROJECT_ROOT),
                "NF_MACHINE_ID": MACHINE_ID,
                "NF_MQTT_BROKER": "localhost",
                "NF_MQTT_PORT": BROKER_PORT,
            },
        )
        time.sleep(2)
        if _is_running("agent"):
            print("✓")
        else:
            print("✗ 启动失败")
            return 1

    print("\n✓ 所有服务已启动\n")
    cmd_status(args)
    return 0


def cmd_status(args):
    """查看当前状态"""
    print("══ NodeFlow E2E — 状态 ══\n")

    services = [
        ("mosquitto", "MQTT Broker"),
        ("cloud", "Cloud Server"),
        ("daemon", "Edge Daemon"),
        ("agent", "TaskAgent"),
    ]

    for name, label in services:
        ok = _is_running(name)
        icon = "●" if ok else "○"
        print(f"  {icon} {label:20s}", end="")
        if ok and (pidfile := PID_DIR / f"{name}.pid").exists():
            print(f"  PID={pidfile.read_text().strip()}")
        else:
            print("  stopped")

    # cloud API health
    try:
        health = _api("GET", "/health")
        if health.get("status") == "ok":
            print(f"\n  Cloud API: ✓ healthy (SSE subscribers: {health.get('sse_subscribers', 0)})")
    except Exception:
        pass

    # machines
    try:
        machines = _api("GET", "/machines")
        if isinstance(machines, list) and machines:
            print(f"\n  已注册机器:")
            for m in machines:
                age = m.get("seconds_since_heartbeat")
                age_str = f"{age:.0f}s前" if age else "从未心跳"
                print(f"    [{m['status']:8s}] {m['id']:15s} {m.get('name',''):20s} 心跳: {age_str}")
    except Exception:
        pass

    # jobs
    try:
        jobs = _api("GET", "/jobs")
        if isinstance(jobs, list) and jobs:
            print(f"\n  作业列表:")
            for j in jobs:
                steps = len(j.get("steps", []))
                print(f"    [{j['status']:10s}] {j['id']}  ({steps} steps)")
    except Exception:
        pass

    return 0


def _run_scenario(parcel_name: str, op_type: str, preset: str,
                  split_count: int, machine_id: str, wait: bool = False) -> bool:
    """Run a single test scenario. Returns True if dispatch succeeded."""

    # 1. ensure machine exists
    machines = _api("GET", "/machines")
    existing = [m["id"] for m in machines] if isinstance(machines, list) else []
    if machine_id not in existing:
        r = _api("POST", "/machines", {
            "id": machine_id,
            "name": f"Machine {machine_id}",
            "machine_type": "tractor",
        })
        if r.get("error"):
            print(f"  ✗ 注册机器失败: {r.get('detail')}")
            return False
        print(f"  ✓ 注册机器 {machine_id}")
    else:
        print(f"  ● 机器 {machine_id} 已存在")

    # 2. create parcel
    r = _api("POST", "/parcels", {
        "name": parcel_name,
        "geojson": {
            "type": "Feature",
            "geometry": {
                "type": "Polygon",
                "coordinates": [[[120.037328, 28.91685], [120.0385, 28.91685],
                                 [120.0385, 28.9179], [120.037328, 28.9179],
                                 [120.037328, 28.91685]]],
            },
            "properties": {},
        },
    })
    if r.get("error"):
        print(f"  ✗ 创建地块失败: {r.get('detail')}")
        return False
    parcel_id = r["id"]
    print(f"  ✓ 创建地块 {parcel_name}")

    # 3. create job
    r = _api("POST", "/jobs", {
        "parcel_id": parcel_id,
        "split_mode": "strip",
        "split_count": split_count,
        "steps": [{
            "operation_type": op_type,
            "preset_yaml": preset,
            "seq_index": 0,
        }],
        "machine_assignments": {str(i): machine_id for i in range(split_count)},
    })
    if r.get("error"):
        print(f"  ✗ 创建作业失败: {r.get('detail')}")
        return False
    job_id = r["id"]
    print(f"  ✓ 创建作业 {job_id}")

    # 4. dispatch
    r = _api("POST", f"/jobs/{job_id}/dispatch")
    if r.get("error"):
        print(f"  ✗ 下发失败: {r.get('detail')}")
        return False
    dispatched = r.get("dispatched", 0)
    print(f"  ✓ 下发 {dispatched} 个任务")

    if dispatched == 0:
        print(f"  ⚠ 下发数为0，检查 MQTT 连接")
        return False

    # 5. track progress
    if wait:
        print(f"\n  等待任务执行 (最多 30s)...")
        deadline = time.time() + 30
        last_state = ""
        while time.time() < deadline:
            time.sleep(2)
            r = _api("GET", f"/jobs/{job_id}")
            if r.get("error"):
                continue
            for t in r.get("edge_tasks", []):
                state = t.get("state", "")
                pct = t.get("progress_pct", 0)
                if state != last_state:
                    print(f"    [{state:12s}] progress={pct:.0f}%  machine={t.get('machine_id','?')}")
                    last_state = state
            # check if done
            all_done = all(
                t.get("state") in ("completed", "failed", "cancelled")
                for t in r.get("edge_tasks", [])
            )
            if all_done and r.get("edge_tasks"):
                break

        # final summary
        r = _api("GET", f"/jobs/{job_id}")
        print(f"\n  最终状态:")
        for t in r.get("edge_tasks", []):
            err = t.get("error_code") or "none"
            print(f"    [{t['state']:12s}] progress={t['progress_pct']:.0f}%  error={err}")
    else:
        time.sleep(2)
        r = _api("GET", f"/jobs/{job_id}")
        states = [t.get("state", "?") for t in r.get("edge_tasks", [])]
        print(f"  → 任务状态: {', '.join(states)}")

    return True


def cmd_test(args):
    """运行端到端测试场景"""
    print("══ NodeFlow E2E — 测试场景 ══\n")

    # ensure services are running
    if not _is_running("cloud"):
        print("✗ 云服务未启动，请先运行: python3 tests/e2e_cli.py start")
        return 1
    if not _is_running("daemon"):
        print("✗ Daemon 未启动，请先运行: python3 tests/e2e_cli.py start")
        return 1

    print(f"  目标机器: {MACHINE_ID}")
    print(f"  云服务:   {CLOUD_URL}")
    print()

    # ── Scenario: single-machine tillage ──
    print("── 场景1: 单机旋耕 ──")
    ok = _run_scenario(
        parcel_name=f"e2e-test-{int(time.time())}",
        op_type="tillage",
        preset="tillage_operation",
        split_count=1,
        machine_id=MACHINE_ID,
        wait=args.wait,
    )

    print()
    if ok:
        print("✓ 场景1 完成")
    else:
        print("✗ 场景1 失败")
    return 0 if ok else 1


def cmd_stop(args):
    """停止所有服务"""
    print("══ NodeFlow E2E — 停止 ══")
    for name in ["agent", "daemon", "cloud", "mosquitto"]:
        if _is_running(name):
            print(f"  ◼  {name}")
            _stop(name)
        else:
            print(f"  ●  {name} (已停止)")
    return 0


def cmd_clean(args):
    """清理所有状态"""
    print("══ NodeFlow E2E — 清理 ══\n")

    cmd_stop(args)

    if DB_PATH.exists():
        DB_PATH.unlink()
        print(f"  ✓ 删除 DB: {DB_PATH}")

    for f in PID_DIR.glob("*.pid"):
        f.unlink()
    for f in PID_DIR.glob("*.log"):
        f.unlink()
    print(f"  ✓ 清理 PID/log 文件")

    # cleanup edge-side buffers too
    buf_dir = Path("/tmp/nodeflow/buffers")
    if buf_dir.exists():
        for f in buf_dir.glob("runtime.control*"):
            f.unlink(missing_ok=True)
        print(f"  ✓ 清理 control buffer")

    return 0


def cmd_watch(args):
    """轮询状态直到中断"""
    print("══ NodeFlow E2E — 监控 (Ctrl+C 退出) ══\n")
    try:
        while True:
            print("\033[H\033[J", end="")  # clear screen
            cmd_status(args)

            # latest job details
            try:
                jobs = _api("GET", "/jobs")
                if isinstance(jobs, list) and jobs:
                    latest = jobs[0]
                    r = _api("GET", f"/jobs/{latest['id']}")
                    if not r.get("error"):
                        print(f"\n  最新作业 [{latest['id']}]:")
                        for t in r.get("edge_tasks", []):
                            bar_len = int(t.get("progress_pct", 0) / 5)
                            bar = "█" * bar_len + "░" * (20 - bar_len)
                            print(f"    [{t['state']:12s}] {bar} {t['progress_pct']:.0f}%  → {t['machine_id']}")
            except Exception:
                pass

            print(f"\n  刷新中 (每 3s)...")
            time.sleep(3)
    except KeyboardInterrupt:
        print("\n退出")
    return 0


# ── CLI ────────────────────────────────────────────────────────────────


def main():
    parser = argparse.ArgumentParser(
        prog="e2e",
        description="NodeFlow 端到端集成测试工具",
    )
    sub = parser.add_subparsers(dest="cmd")

    p_start = sub.add_parser("start", help="启动所有服务")
    p_start.add_argument("--config", "-c", help="Edge daemon 配置文件", default=None)

    sub.add_parser("status", help="查看当前状态")
    p_test = sub.add_parser("test", help="运行测试场景")
    p_test.add_argument("--wait", "-w", action="store_true", help="等待任务完成 (最多30s)")
    sub.add_parser("stop", help="停止所有服务")
    sub.add_parser("clean", help="清理 (停止+删除DB+缓冲区)")
    sub.add_parser("watch", help="轮询监控状态")

    args = parser.parse_args()

    if args.cmd == "start":
        return cmd_start(args)
    elif args.cmd == "status":
        return cmd_status(args)
    elif args.cmd == "test":
        return cmd_test(args)
    elif args.cmd == "stop":
        return cmd_stop(args)
    elif args.cmd == "clean":
        return cmd_clean(args)
    elif args.cmd == "watch":
        return cmd_watch(args)
    else:
        parser.print_help()
        return 0


if __name__ == "__main__":
    sys.exit(main())
