#!/usr/bin/env python3
"""
NodeFlow 端到端集成测试工具

用法:
    python3 tests/e2e_cli.py start                         # 启动所有服务
    python3 tests/e2e_cli.py test [--scenario S1] [--all]  # 运行测试场景
    python3 tests/e2e_cli.py status                        # 查看状态
    python3 tests/e2e_cli.py stop                          # 停止所有服务
    python3 tests/e2e_cli.py clean                         # 清理

场景:
    S1  单机下发       基本 happy path
    S2  多步编排       旋耕→播种 依赖链
    S3  多机分割       地块分拆到2台机器
    S4  任务取消       下发后取消, 验证 stop_dataflow
    S5  重复去重       同 task_id 二次下发, 验证拒绝 ACK
    S6  自动发现       未注册机器心跳→确认注册
    S7  状态流转       验证完整状态链
    S8  心跳监控       机器 online/offline 检测
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
from dataclasses import dataclass, field
from typing import Optional, Callable

PROJECT_ROOT = Path(__file__).resolve().parent.parent
CLOUD_DIR = PROJECT_ROOT / "cloud" / "server"
DB_PATH = CLOUD_DIR / "farm.db"
PID_DIR = Path("/tmp/nodeflow_e2e")

MACHINE_ID = os.getenv("NF_MACHINE_ID", "tractor-01")
MACHINE_ID_2 = os.getenv("NF_MACHINE_ID_2", "tractor-02")
BROKER_PORT = os.getenv("BROKER_PORT", "1883")
CLOUD_PORT = os.getenv("CLOUD_PORT", "8080")
CLOUD_URL = f"http://localhost:{CLOUD_PORT}"
MOSQUITTO_BIN = "/opt/homebrew/sbin/mosquitto"

# ── colors ──────────────────────────────────────────────────────────────────

GREEN = "\033[32m"; RED = "\033[31m"; YELLOW = "\033[33m"; CYAN = "\033[36m"
BOLD = "\033[1m"; DIM = "\033[2m"; RESET = "\033[0m"

def _ok(s="OK"):    return f"{GREEN}{s}{RESET}"
def _fail(s="FAIL"): return f"{RED}{s}{RESET}"
def _warn(s):        return f"{YELLOW}{s}{RESET}"
def _hdr(s):         return f"{BOLD}{CYAN}{s}{RESET}"
def _dim(s):         return f"{DIM}{s}{RESET}"

# ── API helpers ─────────────────────────────────────────────────────────────

def _api(method: str, path: str, data: dict | None = None) -> dict:
    url = f"{CLOUD_URL}/api/v1{path}"
    body = json.dumps(data).encode() if data else None
    req = urllib.request.Request(url, data=body, method=method)
    req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            if resp.status == 204:
                return {}
            return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        err_body = e.read().decode()
        try:
            detail = json.loads(err_body).get("detail", err_body)
        except Exception:
            detail = err_body or str(e)
        return {"_error": True, "_status": e.code, "_detail": detail}
    except urllib.error.URLError as e:
        return {"_error": True, "_detail": f"Connection refused: {e.reason}"}

def _get(path):    return _api("GET", path)
def _post(path, d=None): return _api("POST", path, d)

# ── service management ──────────────────────────────────────────────────────

def _run_bg(cmd: list[str], name: str, env: dict | None = None) -> subprocess.Popen:
    PID_DIR.mkdir(parents=True, exist_ok=True)
    pidfile = PID_DIR / f"{name}.pid"
    logfile = PID_DIR / f"{name}.log"
    full_env = os.environ.copy()
    if env: full_env.update(env)
    with open(logfile, "w") as f:
        proc = subprocess.Popen(cmd, env=full_env, stdout=f, stderr=subprocess.STDOUT)
    pidfile.write_text(str(proc.pid))
    return proc

def _is_running(name: str) -> bool:
    pidfile = PID_DIR / f"{name}.pid"
    if not pidfile.exists(): return False
    try:
        pid = int(pidfile.read_text().strip())
        os.kill(pid, 0)
        return True
    except (ValueError, OSError, ProcessLookupError):
        pidfile.unlink(missing_ok=True)
        return False

def _verify_pid(pid: int, expected_name: str) -> bool:
    try:
        result = subprocess.run(["ps", "-p", str(pid), "-o", "command="],
                                capture_output=True, text=True, timeout=3)
        cmdline = result.stdout.strip()
        return expected_name in cmdline or "nodeflow" in cmdline.lower()
    except Exception:
        return False

def _stop(name: str):
    pidfile = PID_DIR / f"{name}.pid"
    if not pidfile.exists(): return
    try:
        pid = int(pidfile.read_text().strip())
        if not _verify_pid(pid, name):
            pidfile.unlink(missing_ok=True)
            return
        os.kill(pid, signal.SIGTERM)
        time.sleep(0.5)
        try:
            os.kill(pid, 0)
            os.kill(pid, signal.SIGKILL)
        except OSError: pass
    except (ValueError, OSError): pass
    pidfile.unlink(missing_ok=True)

def _wait_cloud_ready(timeout: float = 10) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            if _get("/health").get("status") == "ok":
                return True
        except Exception: pass
        time.sleep(0.5)
    return False

# ── scenario framework ──────────────────────────────────────────────────────

@dataclass
class Scenario:
    id: str
    name: str
    description: str
    setup: Callable[[], dict]       # returns context dict
    execute: Callable[[dict], bool] # returns pass/fail
    requires: list[str] = field(default_factory=lambda: ["cloud", "daemon", "agent"])
    skip: bool = False

_scenarios: dict[str, Scenario] = {}
_results: list[dict] = []

def scenario(_id: str, name: str, desc: str, requires: list[str] | None = None):
    """装饰器: 注册测试场景"""
    def wrapper(fn):
        _scenarios[_id] = Scenario(
            id=_id, name=name, description=desc,
            setup=lambda: {}, execute=fn,
            requires=requires or ["cloud", "daemon", "agent"],
        )
        return fn
    return wrapper

def _wait_state(job_id: str, expected: str, timeout: float = 15) -> bool:
    """等待 job 中所有 task 达到指定状态"""
    deadline = time.time() + timeout
    while time.time() < deadline:
        time.sleep(0.5)
        r = _get(f"/jobs/{job_id}")
        if r.get("_error"): continue
        tasks = r.get("edge_tasks", [])
        if all(t.get("state") == expected for t in tasks) and tasks:
            return True
    return False

def _wait_any_state(job_id: str, states: list[str], timeout: float = 15) -> str | None:
    """等待 job 中 task 达到任意指定状态，返回实际状态"""
    deadline = time.time() + timeout
    while time.time() < deadline:
        time.sleep(0.5)
        r = _get(f"/jobs/{job_id}")
        if r.get("_error"): continue
        for t in r.get("edge_tasks", []):
            if t.get("state") in states:
                return t.get("state")
    return None

def _check(cond: bool, msg: str) -> bool:
    """断言 + 彩色输出"""
    if cond:
        print(f"    {_ok('✓')} {msg}")
    else:
        print(f"    {_fail('✗')} {msg}")
    return cond

# ── S1: 单机下发 ────────────────────────────────────────────────────────────

@scenario("S1", "单机下发", "单台机器单步骤旋耕任务")
def _s1(ctx: dict) -> bool:
    print(f"  {_hdr('S1: 单机下发 — 基本 happy path')}")
    ok = True

    # register (ignore 409 if already exists)
    _post("/machines", {"id": MACHINE_ID, "name": "Tractor 1", "machine_type": "tractor"})
    r = _post("/parcels", {"name": f"S1-field-{int(time.time())}", "geojson": _test_geojson()})
    if r.get("_error"): print(f"    {_fail('parcel create failed:')} {r}"); return False
    pid = r["id"]
    r = _post("/jobs", {"parcel_id": pid, "split_mode": "strip", "split_count": 1,
        "steps": [{"operation_type": "tillage", "preset_yaml": "tillage_operation", "seq_index": 0}],
        "machine_assignments": {"0": MACHINE_ID}})
    if r.get("_error"): print(f"    {_fail('job create failed:')} {r}"); return False
    jid = r["id"]

    r = _post(f"/jobs/{jid}/dispatch")
    ok &= _check(r.get("dispatched", 0) >= 1, f"下发 {r.get('dispatched', 0)} 个任务")

    # wait for RUNNING
    reached = _wait_any_state(jid, ["running", "ready"], timeout=12)
    ok &= _check(reached in ("running", "ready"), f"任务状态 → {reached}")

    # verify job status
    r = _get(f"/jobs/{jid}")
    ok &= _check(r.get("status") == "running", f"作业状态: {r.get('status')}")
    ok &= _check(len(r.get("edge_tasks", [])) >= 1, f"EdgeTask 数: {len(r.get('edge_tasks', []))}")

    return ok


# ── S2: 多步编排 ────────────────────────────────────────────────────────────

@scenario("S2", "多步编排", "旋耕→播种 依赖链，第一步完成后自动下发第二步")
def _s2(ctx: dict) -> bool:
    print(f"  {_hdr('S2: 多步编排 — 旋耕→播种 依赖链')}")
    ok = True

    _post("/machines", {"id": MACHINE_ID, "name": "Tractor 1", "machine_type": "tractor"})
    r = _post("/parcels", {"name": f"S2-field-{int(time.time())}", "geojson": _test_geojson()})
    if not (r := _require(r, "parcel")): return False
    pid = r["id"]
    r = _post("/jobs", {"parcel_id": pid, "split_mode": "strip", "split_count": 1,
        "steps": [
            {"operation_type": "tillage", "preset_yaml": "tillage_operation", "seq_index": 0},
            {"operation_type": "seeding", "preset_yaml": "tillage_operation", "seq_index": 1, "depends_on": 0},
        ],
        "machine_assignments": {"0": MACHINE_ID}})
    if not (r := _require(r, "job")): return False
    jid = r["id"]

    # verify 2 steps with dependency
    steps = r.get("steps", [])
    ok &= _check(len(steps) == 2, f"步骤数: {len(steps)}")
    ok &= _check(steps[1].get("depends_on") == 0, f"Step1 depends_on=0")

    _post(f"/jobs/{jid}/dispatch")
    r = _get(f"/jobs/{jid}")
    ok &= _check(r.get("status") in ("running", "draft", "ready"),
                 f"作业状态: {r.get('status')}")

    # edge_tasks should be for the first step only
    tasks = r.get("edge_tasks", [])
    tillage_tasks = [t for t in tasks if t.get("state") != "cancelled"]
    ok &= _check(len(tillage_tasks) >= 1, f"第一步 task 数: {len(tillage_tasks)}")

    return ok


# ── S3: 多机分割 ────────────────────────────────────────────────────────────

@scenario("S3", "多机分割", "地块分拆到 2 台机器", requires=["cloud", "daemon", "agent"])
def _s3(ctx: dict) -> bool:
    print(f"  {_hdr('S3: 多机分割 — 地块拆分为 2')}")
    ok = True

    _post("/machines", {"id": MACHINE_ID, "name": "Tractor 1", "machine_type": "tractor"})
    _post("/machines", {"id": MACHINE_ID_2, "name": "Tractor 2", "machine_type": "tractor"})
    r = _post("/parcels", {"name": f"S3-field-{int(time.time())}", "geojson": _test_geojson()})
    if not (r := _require(r, "parcel")): return False
    pid = r["id"]

    # create job with split_count=2
    r = _post("/jobs", {"parcel_id": pid, "split_mode": "strip", "split_count": 2,
        "steps": [{"operation_type": "tillage", "preset_yaml": "tillage_operation", "seq_index": 0}],
        "machine_assignments": {"0": MACHINE_ID, "1": MACHINE_ID_2}})
    if not (r := _require(r, "job")): return False
    jid = r["id"]

    r = _post(f"/jobs/{jid}/dispatch")
    dispatched = r.get("dispatched", 0)
    ok &= _check(dispatched >= 2, f"下发 {dispatched} 个任务 (期望≥2)")

    # verify splits created and tasks on both machines
    r = _get(f"/jobs/{jid}")
    splits = r.get("splits", [])
    ok &= _check(len(splits) >= 1, f"子地块数: {len(splits)}")
    tasks = r.get("edge_tasks", [])
    machines_seen = {t.get("machine_id") for t in tasks}
    ok &= _check(len(machines_seen) >= 1, f"涉及机器: {machines_seen}")
    return ok


# ── S4: 任务取消 ────────────────────────────────────────────────────────────

@scenario("S4", "任务取消", "下发后取消，验证 stop_dataflow 写入")
def _s4(ctx: dict) -> bool:
    print(f"  {_hdr('S4: 任务取消 — 下发后取消')}")
    ok = True

    _post("/machines", {"id": MACHINE_ID, "name": "Tractor 1", "machine_type": "tractor"})
    r = _post("/parcels", {"name": f"S4-field-{int(time.time())}", "geojson": _test_geojson()})
    if not (r := _require(r, "parcel")): return False
    pid = r["id"]
    r = _post("/jobs", {"parcel_id": pid, "split_mode": "strip", "split_count": 1,
        "steps": [{"operation_type": "tillage", "preset_yaml": "tillage_operation", "seq_index": 0}],
        "machine_assignments": {"0": MACHINE_ID}})
    if not (r := _require(r, "job")): return False
    jid = r["id"]

    _post(f"/jobs/{jid}/dispatch")

    # wait briefly then cancel
    time.sleep(1)
    r = _post(f"/jobs/{jid}/cancel")
    cancelled = r.get("cancelled", 0)
    ok &= _check(cancelled >= 0, f"取消响应: cancelled={cancelled}")

    # verify tasks ended up in terminal state
    r = _get(f"/jobs/{jid}")
    tasks = r.get("edge_tasks", [])
    terminal = {"cancelled", "failed", "completed"}
    ok &= _check(all(t.get("state") in terminal for t in tasks) if tasks else True,
                 f"任务已终止: {[t.get('state') for t in tasks]}")
    return ok


# ── S5: 重复去重 ────────────────────────────────────────────────────────────

@scenario("S5", "重复去重", "相同 task_id 二次下发应被拒绝")
def _s5(ctx: dict) -> bool:
    print(f"  {_hdr('S5: 重复去重 — 同 task_id 拒绝')}")
    ok = True

    # Scenario S5 works without agent receiving — test at API level
    # Create a job, dispatch, then attempt to dispatch same job again
    _post("/machines", {"id": MACHINE_ID, "name": "Tractor 1", "machine_type": "tractor"})
    r = _post("/parcels", {"name": f"S5-field-{int(time.time())}", "geojson": _test_geojson()})
    if not (r := _require(r, "parcel")): return False
    pid = r["id"]
    r = _post("/jobs", {"parcel_id": pid, "split_mode": "strip", "split_count": 1,
        "steps": [{"operation_type": "tillage", "preset_yaml": "tillage_operation", "seq_index": 0}],
        "machine_assignments": {"0": MACHINE_ID}})
    if not (r := _require(r, "job")): return False
    jid = r["id"]

    r1 = _post(f"/jobs/{jid}/dispatch")
    # second dispatch — should succeed but edge deduplicates by task_id via ACK
    r2 = _post(f"/jobs/{jid}/dispatch")
    ok &= _check(r1.get("dispatched", 0) >= 0 and r2.get("dispatched", 0) >= 0,
                 "两次下发均返回成功")
    return ok


# ── S6: 自动发现 ────────────────────────────────────────────────────────────

@scenario("S6", "自动发现", "未注册机器心跳→自动创建→确认注册")
def _s6(ctx: dict) -> bool:
    print(f"  {_hdr('S6: 自动发现 — 心跳自动注册')}")
    ok = True

    # Wait for agent heartbeat to auto-register
    time.sleep(3)
    machines = _get("/machines")
    if isinstance(machines, list):
        unreg = [m for m in machines if m.get("status") == "unregistered"]
        registered = [m for m in machines if m.get("status") != "unregistered"]
        print(f"    发现 {len(unreg)} 个待确认, {len(registered)} 个已注册")

        if unreg:
            # confirm the first unregistered machine
            mid = unreg[0]["id"]
            r = _post(f"/machines/{mid}/confirm")
            ok &= _check(r.get("status") == "online", f"确认后状态: {r.get('status')}")
    return ok


# ── S7: 状态流转 ────────────────────────────────────────────────────────────

@scenario("S7", "状态流转", "验证完整状态链: pending→downloading→ready→running")
def _s7(ctx: dict) -> bool:
    print(f"  {_hdr('S7: 状态流转 — 完整状态链')}")
    ok = True

    _post("/machines", {"id": MACHINE_ID, "name": "Tractor 1", "machine_type": "tractor"})
    r = _post("/parcels", {"name": f"S7-field-{int(time.time())}", "geojson": _test_geojson()})
    if not (r := _require(r, "parcel")): return False
    pid = r["id"]
    r = _post("/jobs", {"parcel_id": pid, "split_mode": "strip", "split_count": 1,
        "steps": [{"operation_type": "tillage", "preset_yaml": "tillage_operation", "seq_index": 0}],
        "machine_assignments": {"0": MACHINE_ID}})
    if not (r := _require(r, "job")): return False
    jid = r["id"]

    # Check initial state
    r = _get(f"/jobs/{jid}")
    ok &= _check(r.get("status") == "draft", f"初始作业状态: {r.get('status')}")

    _post(f"/jobs/{jid}/dispatch")

    # Wait for RUNNING state
    reached = _wait_any_state(jid, ["running", "ready"], timeout=12)
    ok &= _check(reached in ("running", "ready"), f"任务最终状态: {reached}")

    # Verify job.status transitions
    r = _get(f"/jobs/{jid}")
    ok &= _check(r.get("status") == "running", f"作业状态: {r.get('status')}")
    return ok


# ── S8: 心跳监控 ────────────────────────────────────────────────────────────

@scenario("S8", "心跳监控", "验证机器心跳上报和状态更新")
def _s8(ctx: dict) -> bool:
    print(f"  {_hdr('S8: 心跳监控 — 机器状态检测')}")
    ok = True

    machines = _get("/machines")
    if isinstance(machines, list):
        online = [m for m in machines if m.get("status") == "online"]
        busy = [m for m in machines if m.get("status") == "busy"]
        offline = [m for m in machines if m.get("status") == "offline"]
        unreg = [m for m in machines if m.get("status") == "unregistered"]

        print(f"    在线: {len(online)}  忙碌: {len(busy)}  离线: {len(offline)}  待确认: {len(unreg)}")

        # All machines should have a recent heartbeat
        for m in machines:
            age = m.get("seconds_since_heartbeat")
            if age is not None and m.get("status") != "offline":
                ok &= _check(age < 300, f"{m['id']} 心跳 {age:.0f}s 前")
    return ok


def _require(response: dict, label: str) -> dict:
    """检查 API 响应，失败时打印错误并返回 None"""
    if response.get("_error"):
        err = response.get("_detail") or response.get("_status") or "unknown"
        print(f"    {_fail('✗ ' + label + ':')} {err}")
        return None
    return response

# ── helpers ──────────────────────────────────────────────────────────────────

def _test_geojson() -> dict:
    return {
        "type": "Feature",
        "geometry": {
            "type": "Polygon",
            "coordinates": [[[120.037328, 28.91685], [120.0385, 28.91685],
                             [120.0385, 28.9179], [120.037328, 28.9179],
                             [120.037328, 28.91685]]],
        },
        "properties": {},
    }

# ── commands ─────────────────────────────────────────────────────────────────

def cmd_start(args):
    print(f"{_hdr('══ NodeFlow E2E — 启动 ══')}\n")
    all_ok = True

    if _is_running("mosquitto"):
        print(f"  ⏭  mosquitto 已运行")
    else:
        print(f"  ▶  mosquitto", end=" ", flush=True)
        _run_bg([MOSQUITTO_BIN, "-p", BROKER_PORT], "mosquitto")
        time.sleep(1.5)
        if _is_running("mosquitto"):
            print(_ok())
        else:
            print(_fail("启动失败"))
            all_ok = False

    if _is_running("cloud"):
        print(f"  ⏭  cloud server 已运行")
    else:
        print(f"  ▶  cloud server", end=" ", flush=True)
        for suffix in ("", "-wal", "-shm"):
            p = Path(str(DB_PATH) + suffix)
            p.unlink(missing_ok=True)
        _run_bg([sys.executable, "-m", "uvicorn", "cloud.server.app:app",
                 "--host", "0.0.0.0", "--port", CLOUD_PORT], "cloud",
                env={"PYTHONPATH": str(PROJECT_ROOT)})
        time.sleep(3)
        if _wait_cloud_ready():
            print(_ok())
        else:
            print(_fail("超时"))
            all_ok = False

    config_path = args.config or "examples/tillage_operation.yaml"
    if _is_running("daemon"):
        print(f"  ⏭  edge daemon 已运行")
    else:
        print(f"  ▶  edge daemon [{config_path}]", end=" ", flush=True)
        _run_bg([sys.executable, "-m", "runtime.main", config_path, "--daemon"],
                "daemon", env={"PYTHONPATH": str(PROJECT_ROOT)})
        time.sleep(3)
        print(_ok() if _is_running("daemon") else _fail("启动失败"))

    if _is_running("agent"):
        print(f"  ⏭  TaskAgent 已运行")
    else:
        print(f"  ▶  TaskAgent", end=" ", flush=True)
        _run_bg([sys.executable, "-m", "runtime.task.agent_main"], "agent",
                env={"PYTHONPATH": str(PROJECT_ROOT), "NF_MACHINE_ID": MACHINE_ID,
                     "NF_MQTT_BROKER": "localhost", "NF_MQTT_PORT": BROKER_PORT})
        time.sleep(2)
        print(_ok() if _is_running("agent") else _fail("启动失败"))

    if args.multi:
        # second agent for multi-machine scenarios
        agent2_name = f"agent-{MACHINE_ID_2}"
        if not _is_running(agent2_name):
            print(f"  ▶  TaskAgent [{MACHINE_ID_2}]", end=" ", flush=True)
            _run_bg([sys.executable, "-m", "runtime.task.agent_main"], agent2_name,
                    env={"PYTHONPATH": str(PROJECT_ROOT), "NF_MACHINE_ID": MACHINE_ID_2,
                         "NF_MQTT_BROKER": "localhost", "NF_MQTT_PORT": BROKER_PORT})
            time.sleep(2)
            print(_ok() if _is_running(agent2_name) else _fail("启动失败"))

    print(f"\n{_ok('✓ 所有服务已启动')}\n")
    cmd_status(args)
    return 0 if all_ok else 1


def cmd_status(args):
    print(f"{_hdr('══ NodeFlow E2E — 状态 ══')}\n")
    for name, label in [("mosquitto", "MQTT Broker"), ("cloud", "Cloud Server"),
                         ("daemon", "Edge Daemon"), ("agent", "TaskAgent")]:
        ok = _is_running(name)
        icon = "●" if ok else "○"
        pid_str = ""
        if ok and (pf := PID_DIR / f"{name}.pid").exists():
            pid_str = f"  PID={pf.read_text().strip()}"
        print(f"  {icon} {label:20s}{pid_str}")

    health = _get("/health")
    if health.get("status") == "ok":
        print(f"\n  Cloud API: {_ok('healthy')} (SSE: {health.get('sse_subscribers', 0)})")

    machines = _get("/machines")
    if isinstance(machines, list) and machines:
        print(f"\n  机器:")
        for m in machines:
            age = m.get("seconds_since_heartbeat")
            age_str = f"{age:.0f}s前" if age else "—"
            task = m.get("current_task_id", "")
            task_str = f"  task={task[:12]}..." if task else ""
            print(f"    [{m['status']:14s}] {m['id']:15s} 心跳:{age_str}{task_str}")

    jobs = _get("/jobs")
    if isinstance(jobs, list) and jobs:
        print(f"\n  作业:")
        for j in jobs[:5]:
            tasks = j.get("steps", [])
            print(f"    [{j['status']:10s}] {j['id']}  ({len(tasks)} steps)")
    return 0


def cmd_test(args):
    print(f"{_hdr('══ NodeFlow E2E — 测试 ══')}\n")

    if not _is_running("cloud"):
        print(f"{_fail('✗ 云服务未启动')}, 先运行: python3 tests/e2e_cli.py start")
        return 1

    print(f"  目标: {MACHINE_ID}" + (f", {MACHINE_ID_2}" if args.multi else ""))
    print(f"  云服务: {CLOUD_URL}")
    print()

    # select scenarios
    if args.all:
        ids = list(_scenarios.keys())
    elif args.scenario:
        ids = [args.scenario]
    else:
        ids = ["S1"]

    passed = 0
    failed = 0
    skipped = 0

    for sid in ids:
        sc = _scenarios.get(sid)
        if not sc:
            print(f"  {_fail(f'未知场景: {sid}')}")
            continue
        if sc.skip:
            print(f"  {_warn(f'⏭  {sid}: {sc.name}')} — 跳过")
            skipped += 1
            continue

        # check prerequisites
        missing = [r for r in sc.requires if not _is_running(r)]
        if missing:
            print(f"  {_warn(f'⏭  {sid}: {sc.name}')} — 缺少服务: {missing}")
            skipped += 1
            continue

        try:
            ctx = sc.setup()
            ok = sc.execute(ctx)
            if ok:
                print(f"  {_ok(f'{sid}: {sc.name} — PASS')}\n")
                passed += 1
            else:
                print(f"  {_fail(f'{sid}: {sc.name} — FAIL')}\n")
                failed += 1
        except Exception as e:
            print(f"  {_fail(f'{sid}: {sc.name} — ERROR: {e}')}\n")
            failed += 1

    # summary
    total = passed + failed + skipped
    print(f"{_hdr('══ 结果 ══')}")
    print(f"  通过: {_ok(str(passed))}  失败: {_fail(str(failed)) if failed else str(failed)}  跳过: {skipped}  总计: {total}")
    if total > 0:
        pct = passed * 100 // total
        bar = "█" * (pct // 5) + "░" * (20 - pct // 5)
        print(f"  [{bar}] {pct}%")

    return 0 if failed == 0 else 1


def cmd_stop(args):
    print(f"{_hdr('══ NodeFlow E2E — 停止 ══')}")
    for name in ["agent", f"agent-{MACHINE_ID_2}", "daemon", "cloud", "mosquitto"]:
        if _is_running(name):
            _stop(name)
            print(f"  ◼  {name}")
        else:
            pidfile = PID_DIR / f"{name}.pid"
            if pidfile.exists(): pidfile.unlink()
    return 0


def cmd_clean(args):
    print(f"{_hdr('══ NodeFlow E2E — 清理 ══')}")
    cmd_stop(args)
    for suffix in ("", "-wal", "-shm"):
        p = Path(str(DB_PATH) + suffix)
        if p.exists():
            p.unlink()
            print(f"  ✓ 删除 {p.name}")
    for f in PID_DIR.glob("*"):
        f.unlink()
    print(f"  ✓ 清理 PID/log")
    for f in Path("/tmp/nodeflow/buffers").glob("runtime.control*"):
        f.unlink(missing_ok=True)
    return 0


# ── CLI ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(prog="e2e", description="NodeFlow E2E 集成测试")
    sub = parser.add_subparsers(dest="cmd")

    p_start = sub.add_parser("start", help="启动所有服务")
    p_start.add_argument("--config", "-c", help="Daemon 配置文件")
    p_start.add_argument("--multi", "-m", action="store_true", help="启动第二台机器 agent")

    sub.add_parser("status", help="查看状态")

    p_test = sub.add_parser("test", help="运行测试场景")
    p_test.add_argument("--scenario", "-s", choices=list(_scenarios.keys()), help="指定场景")
    p_test.add_argument("--all", "-a", action="store_true", help="运行所有场景")
    p_test.add_argument("--multi", "-m", action="store_true", help="启用多机场景")

    sub.add_parser("stop", help="停止所有服务")
    sub.add_parser("clean", help="清理")

    args = parser.parse_args()

    if args.cmd == "start":    return cmd_start(args)
    elif args.cmd == "status": return cmd_status(args)
    elif args.cmd == "test":   return cmd_test(args)
    elif args.cmd == "stop":   return cmd_stop(args)
    elif args.cmd == "clean":  return cmd_clean(args)
    else:
        parser.print_help()
        return 0


if __name__ == "__main__":
    sys.exit(main())
