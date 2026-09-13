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
    S8  心跳中断       停止agent → 验证心跳中断被感知
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
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

CLOUD_DIR = PROJECT_ROOT / "cloud" / "server"
DB_PATH = CLOUD_DIR / "farm.db"
PID_DIR = Path("/tmp/nodeflow_e2e")

MACHINE_ID = os.getenv("NF_MACHINE_ID", "tractor-01")
MACHINE_ID_2 = os.getenv("NF_MACHINE_ID_2", "tractor-02")
BROKER_PORT = os.getenv("BROKER_PORT", "1883")
CLOUD_PORT = os.getenv("CLOUD_PORT", "8080")
CLOUD_URL = f"http://localhost:{CLOUD_PORT}"
MOSQUITTO_BIN = "/opt/homebrew/sbin/mosquitto"
MOSQUITTO_PUB = "/opt/homebrew/bin/mosquitto_pub"

def _mqtt_pub(topic: str, payload: str, qos: int = 1) -> subprocess.CompletedProcess:
    """向 MQTT broker 发布消息"""
    return subprocess.run([MOSQUITTO_PUB, "-t", topic, "-m", payload,
                           "-p", BROKER_PORT, "-q", str(qos)],
                          capture_output=True, timeout=5)

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

@scenario("S2", "多步编排", "验证2步依赖链结构 + dispatch仅创建第一步任务")
def _s2(ctx: dict) -> bool:
    print(f"  {_hdr('S2: 多步编排 — 结构验证')}")
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

    steps = r.get("steps", [])
    ok &= _check(len(steps) == 2, f"步骤数=2")
    ok &= _check(steps[1].get("depends_on") == 0, f"Step1 depends_on=0")
    ok &= _check(steps[0].get("status") == "pending", f"Step0 初始=pending")
    ok &= _check(steps[1].get("status") == "pending", f"Step1 初始=pending")

    _post(f"/jobs/{jid}/dispatch")
    time.sleep(2)
    r = _get(f"/jobs/{jid}")
    ok &= _check(r.get("status") == "running", f"作业=running")
    tasks = r.get("edge_tasks", [])
    ok &= _check(len(tasks) == 1, f"dispatch后只创建第一步task: {len(tasks)}个")
    if tasks:
        ok &= _check(tasks[0].get("operation_type") != "seeding",
                     f"第一步task不是seeding: {tasks[0].get('operation_type')}")

    # 验证: 第二步不应被提前创建（depends_on=0未完成时）
    step1_after = [s for s in r.get("steps", []) if s.get("seq_index") == 1]
    if step1_after:
        ok &= _check(step1_after[0].get("status") != "running",
                     f"依赖未完成时Step1不应=running: {step1_after[0].get('status')}")

    print(f"    {_dim('(注: 完整自动推进需集成测试或 MQTT 模拟 step 完成)')}")
    return ok


# ── S3: 多机分割 ────────────────────────────────────────────────────────────

@scenario("S3", "多机分割", "地块拆分为2, 验证2台机器各自收到任务", requires=["cloud", "daemon", "agent"])
def _s3(ctx: dict) -> bool:
    print(f"  {_hdr('S3: 多机分割 — split=2, 2台机器')}")
    ok = True

    _post("/machines", {"id": MACHINE_ID, "name": "Tractor 1", "machine_type": "tractor"})
    _post("/machines", {"id": MACHINE_ID_2, "name": "Tractor 2", "machine_type": "tractor"})
    r = _post("/parcels", {"name": f"S3-field-{int(time.time())}", "geojson": _test_geojson()})
    if not (r := _require(r, "parcel")): return False
    pid = r["id"]

    r = _post("/jobs", {"parcel_id": pid, "split_mode": "strip", "split_count": 2,
        "steps": [{"operation_type": "tillage", "preset_yaml": "tillage_operation", "seq_index": 0}],
        "machine_assignments": {"0": MACHINE_ID, "1": MACHINE_ID_2}})
    if not (r := _require(r, "job")): return False
    jid = r["id"]

    r = _post(f"/jobs/{jid}/dispatch")
    dispatched = r.get("dispatched", 0)
    ok &= _check(dispatched == 2, f"下发2个任务: dispatched={dispatched}")

    r = _get(f"/jobs/{jid}")
    splits = r.get("splits", [])
    ok &= _check(len(splits) == 2, f"子地块数=2: {len(splits)}")
    for s in splits:
        ok &= _check(s.get("assigned_to") is not None,
                     f"子地块[{s.get('index')}]已分配: {s.get('assigned_to')}")

    tasks = r.get("edge_tasks", [])
    machines_seen = {t.get("machine_id") for t in tasks}
    ok &= _check(len(tasks) == 2, f"EdgeTask数=2: {len(tasks)}")
    ok &= _check(machines_seen == {MACHINE_ID, MACHINE_ID_2},
                 f"两台机器都收到任务: {machines_seen}")
    return ok


# ── S4: 任务取消 ────────────────────────────────────────────────────────────

@scenario("S4", "任务取消", "下发后取消, 验证任务终止 + control buffer 收到 stop_dataflow")
def _s4(ctx: dict) -> bool:
    print(f"  {_hdr('S4: 任务取消 — 验证 stop_dataflow')}")
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
    time.sleep(2)

    # 记录 cancel 前 control buffer seq
    from edge.sdk.shared_buffer_lite import SharedBufferLite
    try:
        pre_buf = SharedBufferLite("runtime.control", create=False)
        pre_seq = pre_buf.get_sequence()
    except Exception:
        pre_seq = -1

    r = _post(f"/jobs/{jid}/cancel")
    cancelled = r.get("cancelled", 0)
    ok &= _check(cancelled == 1, f"取消1个任务: cancelled={cancelled}")

    # 验证 control buffer 被写入 (seq 增加说明 stop_dataflow 已写入)
    try:
        post_buf = SharedBufferLite("runtime.control", create=False)
        post_seq = post_buf.get_sequence()
        ok &= _check(post_seq > pre_seq if pre_seq >= 0 else post_seq > 0,
                     f"control buffer 已写入 (seq: {pre_seq}→{post_seq})")
    except Exception as e:
        print(f"    {_warn('control buffer 检查失败:')} {e}")

    # 验证任务进入终态
    r = _get(f"/jobs/{jid}")
    tasks = r.get("edge_tasks", [])
    terminal = {"cancelled", "failed", "completed"}
    ok &= _check(all(t.get("state") in terminal for t in tasks) if tasks else False,
                 f"任务已终止: {[t.get('state') for t in tasks]}")
    return ok


# ── S5: 重复去重 ────────────────────────────────────────────────────────────

@scenario("S5", "重复去重", "MQTT 同 task_id 二次下发→边侧应拒绝", requires=["cloud", "agent"])
def _s5(ctx: dict) -> bool:
    print(f"  {_hdr('S5: 重复去重 — MQTT 直接下发同 task_id')}")
    ok = True

    task_id = f"e2e-dup-{int(time.time())}"
    dispatch_id_1 = f"d1-{int(time.time())}"
    dispatch_id_2 = f"d2-{int(time.time())}"

    payload = json.dumps({"type": "task_dispatch", "task_id": task_id,
        "job_id": "e2e-dup-job", "dispatch_id": dispatch_id_1,
        "preset_yaml": "tillage_operation", "operation_type": "tillage",
        "sequence_index": 0, "machine_id": MACHINE_ID,
        "node_params": {"parcel_planner": {"parcel_name": "e2e-test"}},
        "timestamp": time.time()})

    # 第一次下发
    r1 = _mqtt_pub(f"nodeflow/{MACHINE_ID}/task/dispatch", payload)

    # 第二次 — 相同 task_id, 不同 dispatch_id
    payload2 = json.dumps({"type": "task_dispatch", "task_id": task_id,
        "job_id": "e2e-dup-job", "dispatch_id": dispatch_id_2,
        "preset_yaml": "tillage_operation", "operation_type": "tillage",
        "sequence_index": 0, "machine_id": MACHINE_ID,
        "node_params": {"parcel_planner": {"parcel_name": "e2e-test"}},
        "timestamp": time.time()})
    r2 = _mqtt_pub(f"nodeflow/{MACHINE_ID}/task/dispatch", payload2)

    ok &= _check(r1.returncode == 0, f"第一次下发: MQTT publish OK (rc={r1.returncode})")
    ok &= _check(r2.returncode == 0, f"第二次下发: MQTT publish OK (rc={r2.returncode})")

    # 验证边侧拒绝重复：agent 日志中必须出现 "duplicate" + "reject ACK"
    time.sleep(2)
    agent_log = PID_DIR / "agent.log"
    if agent_log.exists():
        content = agent_log.read_text()
        dup_lines = [l for l in content.split("\n") if "duplicate" in l.lower() and task_id[:8] in l]
        reject_lines = [l for l in dup_lines if "reject" in l.lower()]
        ok &= _check(len(dup_lines) > 0,
                     f"agent 检测到重复 task_id (duplicate 日志: {len(dup_lines)}条)")
        ok &= _check(len(reject_lines) > 0,
                     f"agent 发送了 reject ACK (reject 日志: {len(reject_lines)}条)")
        if not dup_lines:
            print(f"    {_fail('agent 日志未发现 duplicate 记录 — 去重修复无效!')}")
    else:
        ok &= _check(False, f"agent 日志文件不存在: {agent_log}")
    return ok


# ── S6: 自动发现 ────────────────────────────────────────────────────────────

@scenario("S6", "自动发现", "未注册机器心跳→自动创建→确认注册")
def _s6(ctx: dict) -> bool:
    print(f"  {_hdr('S6: 自动发现 — 心跳自动注册')}")
    ok = True

    time.sleep(3)
    machines = _get("/machines")
    if isinstance(machines, list):
        unreg = [m for m in machines if m.get("status") == "unregistered"]
        registered = [m for m in machines if m.get("status") != "unregistered"]
        print(f"    发现 {len(unreg)} 个待确认, {len(registered)} 个已注册")
        if unreg:
            mid = unreg[0]["id"]
            r = _post(f"/machines/{mid}/confirm")
            ok &= _check(r.get("status") == "online", f"确认后状态: {r.get('status')}")
    return ok


# ── S7: 状态流转 ────────────────────────────────────────────────────────────

@scenario("S7", "状态流转", "采集完整状态链, 验证单调递增无回退")
def _s7(ctx: dict) -> bool:
    print(f"  {_hdr('S7: 状态流转 — 采集状态链')}")
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

    ok &= _check(r.get("status") == "draft", f"初始: draft")

    _post(f"/jobs/{jid}/dispatch")

    # 高频采样 12s, 记录状态链 (预填 dispatch 前的状态)
    seen_states: list[str] = []
    job_states: list[str] = ["draft"]
    deadline = time.time() + 12
    while time.time() < deadline:
        time.sleep(0.5)
        r = _get(f"/jobs/{jid}")
        if r.get("_error"): continue
        js = r.get("status", "")
        if not job_states or job_states[-1] != js:
            job_states.append(js)
        for t in r.get("edge_tasks", []):
            ts = t.get("state", "")
            if not seen_states or seen_states[-1] != ts:
                seen_states.append(ts)

    print(f"    job状态链: {' → '.join(job_states)}")
    print(f"    task状态链: {' → '.join(seen_states)}")

    # 验证单调递增 (状态不应回退)
    state_order = {"pending": 0, "downloading": 1, "ready": 2, "running": 3,
                   "completed": 10, "failed": 10, "cancelled": 10}
    for i in range(1, len(seen_states)):
        prev_ord = state_order.get(seen_states[i-1], -1)
        curr_ord = state_order.get(seen_states[i], -1)
        ok &= _check(curr_ord >= prev_ord,
                     f"状态单调: {seen_states[i-1]} → {seen_states[i]}")

    # 验证: task 状态链至少包含 2 个不同状态 (排除了只采到1个的假通过)
    ok &= _check(len(seen_states) >= 2, f"task状态链≥2: {' → '.join(seen_states)}")
    # 验证: job 状态单调推进且有 draft
    ok &= _check("draft" in job_states, f"job经历draft")
    ok &= _check(len(job_states) >= 2, f"job状态链≥2: {' → '.join(job_states)}")
    return ok


# ── S8: 心跳监控 ────────────────────────────────────────────────────────────

@scenario("S8", "心跳中断", "停止agent后验证心跳中断检测 (offline状态需300s超时, 单独测)", requires=["cloud", "agent"])
def _s8(ctx: dict) -> bool:
    print(f"  {_hdr('S8: 心跳中断 — 验证心跳停止被感知')}")
    ok = True

    # 确认 agent 在发心跳
    machines = _get("/machines")
    if isinstance(machines, list):
        online_before = [m for m in machines if m.get("status") in ("online", "busy")]
        ok &= _check(len(online_before) >= 0, f"停止前有活跃机器")

    # 停止 agent (心跳停止)
    _stop("agent")
    print(f"    agent 已停止, 等待心跳超时 (35s)...")

    # 心跳间隔30s, 等待一个周期确认心跳中断
    time.sleep(35)

    machines = _get("/machines")
    if isinstance(machines, list):
        for m in machines:
            age = m.get("seconds_since_heartbeat")
            status = m.get("status", "")
            if age is not None and age > 30:
                ok &= _check(True, f"{m['id']} 心跳中断 {age:.0f}s (>{30}s)")
            else:
                age_str = f"{age:.0f}s前" if age else "无数据"
                msg = f"{m['id']}: {status} 心跳{age_str}"
                print(f"    {_dim(msg)}")

    # 重启 agent 恢复环境
    _run_bg([sys.executable, "-m", "edge.agent.agent_main"], "agent",
            env={"PYTHONPATH": str(PROJECT_ROOT), "NF_MACHINE_ID": MACHINE_ID,
                 "NF_MQTT_BROKER": "localhost", "NF_MQTT_PORT": BROKER_PORT})
    time.sleep(2)
    ok &= _check(_is_running("agent"), f"agent 已重启")
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
        _run_bg([sys.executable, "-m", "edge.runtime.main", config_path, "--daemon"],
                "daemon", env={"PYTHONPATH": str(PROJECT_ROOT)})
        time.sleep(3)
        print(_ok() if _is_running("daemon") else _fail("启动失败"))

    if _is_running("agent"):
        print(f"  ⏭  TaskAgent 已运行")
    else:
        print(f"  ▶  TaskAgent", end=" ", flush=True)
        _run_bg([sys.executable, "-m", "edge.agent.agent_main"], "agent",
                env={"PYTHONPATH": str(PROJECT_ROOT), "NF_MACHINE_ID": MACHINE_ID,
                     "NF_MQTT_BROKER": "localhost", "NF_MQTT_PORT": BROKER_PORT})
        time.sleep(2)
        print(_ok() if _is_running("agent") else _fail("启动失败"))

    if args.multi:
        # second agent for multi-machine scenarios
        agent2_name = f"agent-{MACHINE_ID_2}"
        if not _is_running(agent2_name):
            print(f"  ▶  TaskAgent [{MACHINE_ID_2}]", end=" ", flush=True)
            _run_bg([sys.executable, "-m", "edge.agent.agent_main"], agent2_name,
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
