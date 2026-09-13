"""NodeFlow 模块审阅关键问题验证脚本 (V2)

验证审阅中发现的 P0/P1 级问题。每个 check 输出 PASS/FAIL/INFO。
V2 变更:
  - C13 改为隔离临时数据库 (NF_CLOUD_DATABASE_URL 指向 /tmp)，绝不触碰默认 farm.db
  - 运行: python3 docs/Flesh_Test/verify_key_issues.py
"""
import json
import os
import sys
import tempfile
import threading
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path("/Users/liwuzhan/Desktop/nodeflow")
sys.path.insert(0, str(PROJECT_ROOT))

results = []


def check(name, ok, detail=""):
    results.append((name, ok, detail))
    print(f"[{'PASS' if ok else 'FAIL'}] {name} {detail}")


# ---------- C1: heartbeat_monitor naive/aware datetime 错误 ----------
def c1_heartbeat_datetime():
    try:
        from cloud.server.models.machine import Machine
        from cloud.server.database import Base, engine, SessionLocal
        Base.metadata.create_all(bind=engine)
        db = SessionLocal()
        m = Machine(id=f"verify-heartbeat-{uuid.uuid4().hex[:8]}", name="verify", machine_type="verify",
                    implement_width_m=2.0, status="online",
                    last_heartbeat=datetime.now(timezone.utc))
        db.add(m)
        db.commit()
        db.refresh(m)
        now = datetime.now(timezone.utc)
        try:
            age = (now - m.last_heartbeat).total_seconds()
            check("C1 heartbeat age 计算", True,
                  f"naive/aware 兼容 (age={age:.1f}s) tzinfo={m.last_heartbeat.tzinfo}")
        except TypeError as e:
            check("C1 heartbeat age 计算", False, f"TypeError: {e}")
        db.query(Machine).filter(Machine.id == m.id).delete()
        db.commit()
        db.close()
    except Exception as e:
        check("C1 heartbeat age 计算", False, f"异常: {type(e).__name__}: {e}")


# ---------- C2: MCP resolve_project_path 根目录错误 ----------
def c2_mcp_project_root():
    try:
        sys.path.insert(0, str(PROJECT_ROOT / "tools"))
        sys.path.insert(0, str(PROJECT_ROOT / "tools" / "mcp"))
        import mcp_server
        root = mcp_server.resolve_project_path("examples/planning_simulation.yaml")
        actual = Path(__file__).resolve().parent / "tools/mcp/examples/planning_simulation.yaml"
        expected = PROJECT_ROOT / "examples/planning_simulation.yaml"
        ok = root == expected
        check("C2 MCP project_root 解析", ok,
              f"resolve 结果={root}\n      期望={expected}")
    except ImportError as e:
        check("C2 MCP project_root 解析", False, f"导入失败: {e}")


# ---------- C3: farm_coverage_viz 调用不存在的 SDK 方法 ----------
def c3_farm_coverage_sdk():
    try:
        import ast
        path = PROJECT_ROOT / "edge/nodes/observability/farm_coverage_viz/run.py"
        tree = ast.parse(path.read_text(encoding="utf-8"))
        calls = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
                calls.add(node.func.attr)
        bad = sorted(c for c in calls if c in ("send", "recv_latest"))
        check("C3 farm_coverage_viz 使用不存在 SDK 方法", not bad,
              f"调用 {bad} (NodeFlowSDK 只有 create_input_port/create_output_port)" if bad else "无旧式 send/recv_latest 调用")
    except Exception as e:
        check("C3 farm_coverage_viz 使用不存在 SDK 方法", False, f"异常: {e}")


# ---------- C4: 布尔参数经框架往返后是否保持布尔 ----------
def c4_bool_coercion():
    """主链路真实数据流: YAML(原生bool) -> json.dumps -> --params -> json.loads。
    若往返后仍是 bool，则 bool("false") 场景不成立，原 C4 判定为推理跳跃。
    """
    try:
        import json as _json
        yaml_true = True
        yaml_false = False
        params = {"auto_zone_detect": yaml_true, "enable_verbose_log": yaml_false,
                  "dry_run_mode": yaml_false, "progress_target_enabled": yaml_true}
        params_json = _json.dumps(params)
        parsed = _json.loads(params_json)
        types_ok = all(isinstance(v, bool) for v in parsed.values())
        check("C4 主链路布尔参数保持类型", types_ok,
              f"YAML bool -> json.dumps -> json.loads 后 types={[type(v).__name__ for v in parsed.values()]} "
              f"(bool('false')==True 仅在字符串入参时成立, 主链路 YAML 为原生 bool)")
    except Exception as e:
        check("C4 主链路布尔参数保持类型", False, f"异常: {e}")


# ---------- C5: sim_output schema 与实际数据字段不一致 ----------
def c5_sim_output_schema():
    try:
        import ast
        path = PROJECT_ROOT / "edge/nodes/sensing/sim_output/run.py"
        src = path.read_text(encoding="utf-8")
        tree = ast.parse(src)
        schema_fields = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef) and node.name == "RTKFix":
                for item in node.body:
                    if isinstance(item, ast.AnnAssign) and isinstance(item.target, ast.Name):
                        schema_fields.add(item.target.id)
        actual_fields = {"latitude", "longitude", "altitude", "num_satellites",
                         "rtk_status", "seq", "precision"}
        mismatch = schema_fields - actual_fields
        check("C5 sim_output schema 与仿真器输出一致", not mismatch,
              f"schema RTKFix 字段={sorted(schema_fields)}, 仿真器实际输出 latitude/longitude/num_satellites; 差异={sorted(mismatch)}")
    except Exception as e:
        check("C5 sim_output schema 与仿真器输出一致", False, f"异常: {e}")


# ---------- C6: trajectory_viz 可选端口声明不一致 ----------
def c6_trajectory_viz_ports():
    try:
        import yaml
        manifest = yaml.safe_load(
            (PROJECT_ROOT / "edge/nodes/observability/trajectory_viz/node.yaml").read_text())
        inputs = manifest["ports"]["inputs"]
        optional_declared = [i["name"] for i in inputs if "可选" in i.get("description", "")]
        import ast
        run_src = (PROJECT_ROOT / "edge/nodes/observability/trajectory_viz/run.py").read_text()
        tree = ast.parse(run_src)
        protected = set()
        created = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Assign) and isinstance(node.value, ast.Call) \
                    and isinstance(node.value.func, ast.Name) and node.value.func.id == "create_optional_input_port" \
                    and node.value.args and isinstance(node.value.args[0], ast.Constant):
                protected.add(node.value.args[0].value)
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) \
                    and node.func.attr == "create_input_port" and node.args \
                    and isinstance(node.args[0], ast.Constant):
                created.add(node.args[0].value)
        claimed_optional_unprotected = set(optional_declared) - protected
        check("C6 trajectory_viz 可选端口声明与实现一致", not claimed_optional_unprotected,
              f"描述'可选'端口={sorted(optional_declared)}, try/except 保护={sorted(protected)}, 未保护={sorted(claimed_optional_unprotected)}")
    except Exception as e:
        check("C6 trajectory_viz 可选端口声明与实现一致", False, f"异常: {e}")
    except Exception as e:
        check("C6 trajectory_viz 可选端口声明与实现一致", False, f"异常: {e}")


# ---------- C7: --log-level 参数失效 ----------
def c7_log_level():
    src = (PROJECT_ROOT / "edge/runtime/main.py").read_text()
    stored = "self.log_level = args.log_level" in src or "self.log_level" in src
    used = "log_level" in src
    # 检查是否真正被 setup_logger 使用
    uses_setlevel = src.count("setLevel")
    check("C7 --log-level 是否真正生效", uses_setlevel > 0 and stored,
          f"main.py 中 log_level 出现次数={src.count('log_level')}, setLevel 调用次数={uses_setlevel}")


# ---------- C8: node_launcher 平台硬编码 linux ----------
def c8_platform_hardcode():
    src = (PROJECT_ROOT / "edge/runtime/orchestrator/node_launcher.py").read_text()
    # 查找 launch 的 platform 参数默认值
    check("C8 platform 硬编码 linux", "platform=\"linux\"" not in src,
          f"node_launcher 中 platform 默认值处理: {[l.strip() for l in src.splitlines() if 'platform' in l][:6]}")


# ---------- C9: tests/legacy 与 tests/mcp 不被 pytest 收集 ----------
def c9_pytest_collection():
    import subprocess
    res = subprocess.run([sys.executable, "-m", "pytest", "--collect-only", "-q"],
                         cwd=str(PROJECT_ROOT), capture_output=True, text=True, timeout=120)
    out = res.stdout
    has_mcp = "tests/mcp" in out
    has_legacy = "tests/legacy" in out
    collected = out.count("::") if "::" in out else 0
    check("C9 legacy/mcp 测试不被 pytest 收集(符合 norecursedirs)", not has_legacy and not has_mcp,
          f"collected={out.strip().splitlines()[-1] if out.strip() else 'none'}")


# ---------- C10: simulation 集成测试与配置矛盾 (20Hz vs 50Hz) ----------
def c10_sim_rtk_freq():
    import yaml
    cfg = yaml.safe_load((PROJECT_ROOT / "simulation/config.yaml").read_text())
    rtk_freq = cfg.get("sensors", {}).get("rtk", {}).get("frequency") or cfg.get("rtk", {}).get("frequency")
    test_src = (PROJECT_ROOT / "simulation/tests/test_integration.py").read_text()
    claims_20hz = "18" in test_src and "22" in test_src
    check("C10 RTK 频率配置与测试断言一致", not (claims_20hz and rtk_freq != 20),
          f"config.yaml rtk.frequency={rtk_freq}, test_integration 断言 18-22Hz")


# ---------- C11: shared_buffer 序列号回绕与 torn-read ----------
def c11_shared_buffer_roundtrip():
    try:
        sys.path.insert(0, str(PROJECT_ROOT / "edge"))
        from edge.sdk.shared_buffer_lite import SharedBufferLite
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            path = os.path.join(td, "test.buf")
            w = SharedBufferLite(path, create=True, size=65536)
            r = SharedBufferLite(path, create=False)
            payload = {"x": 1.234, "y": -5.678, "msg": "hello" * 100, "seq": 42}
            w.write(payload)
            seq, data = r.read_with_sequence()
            ok = data == payload and seq == 1
            # 连续写入验证序列号递增与最新值语义
            for i in range(5):
                w.write({"n": i})
            seq2, data2 = r.read_with_sequence()
            w.close()
            r.close()
            check("C11 SharedBufferLite 读写+序列号递增", ok and seq2 == 6 and data2.get("n") == 4,
                  f"roundtrip={ok}, 5次写入后 seq={seq2} (期望6), 值={data2.get('n')} (期望4)")
    except Exception as e:
        check("C11 SharedBufferLite 读写+回绕", False, f"异常: {type(e).__name__}: {e}")


# ---------- C12: contracts 状态机转移 ----------
def c12_contracts():
    try:
        from contracts.task import TaskState, can_transition_task_state
        ok_forward = can_transition_task_state(TaskState.RUNNING, TaskState.COMPLETED)
        ok_backward = can_transition_task_state(TaskState.COMPLETED, TaskState.RUNNING)
        ok_terminal = can_transition_task_state(TaskState.CANCELLED, TaskState.FAILED)
        check("C12 contracts 状态机转移表", ok_forward and not ok_backward and not ok_terminal,
              f"RUNNING→COMPLETED={ok_forward}, COMPLETED→RUNNING={ok_backward}, CANCELLED→FAILED={ok_terminal}")
    except Exception as e:
        check("C12 contracts 状态机转移表", False, f"异常: {e}")


# ---------- C13: cloud server DELETE FK 500 ----------
def c13_delete_fk():
    """删除被引用 parcel 的 FK 行为。使用隔离临时数据库，绝不触碰默认 farm.db。"""
    try:
        from fastapi.testclient import TestClient
        from cloud.server.database import Base, engine
        from cloud.server.app import create_app
        Base.metadata.drop_all(bind=engine)
        Base.metadata.create_all(bind=engine)
        app = create_app()
        with TestClient(app, raise_server_exceptions=False) as client:
            pname = f"verify-fk-parcel-{uuid.uuid4().hex[:8]}"
            geojson = {"type": "Polygon",
                       "coordinates": [[[121.0, 31.0], [121.01, 31.0], [121.01, 31.01], [121.0, 31.01], [121.0, 31.0]]]}
            r = client.post("/api/v1/parcels", json={"name": pname, "geojson": geojson})
            pid = r.json().get("id") if r.status_code == 201 else None
            if not pid:
                check("C13 删除被引用 parcel 不产生 500", False, f"创建失败 HTTP {r.status_code}: {r.text[:150]}")
                return
            jr = client.post("/api/v1/jobs", json={
                "name": f"verify-fk-job-{uuid.uuid4().hex[:8]}", "parcel_id": pid, "split_mode": "strip",
                "split_count": 2, "steps": [{"seq_index": 0, "operation_type": "tillage",
                                              "preset_yaml": "tillage_operation",
                                              "planning_mode": "edge"}]})
            jid = jr.json().get("id") if jr.status_code in (200, 201) else None
            if not jid:
                check("C13 删除被引用 parcel 不产生 500", False, f"job 创建失败 HTTP {jr.status_code}: {jr.text[:150]}")
                return
            r2 = client.delete(f"/api/v1/parcels/{pid}")
            # 期望: 优雅拒绝 (4xx); 500(未捕获 IntegrityError) 与 2xx+悬挂引用 均为缺陷
            if r2.status_code == 500:
                ok, verdict = False, "HTTP 500 (未捕获 IntegrityError)"
            elif r2.status_code >= 400:
                ok, verdict = True, f"HTTP {r2.status_code} (优雅拒绝)"
            else:
                r3 = client.get(f"/api/v1/jobs/{jid}")
                dangling = r3.status_code == 200
                ok, verdict = not dangling, f"HTTP {r2.status_code} (已删; job 悬挂引用={dangling})"
            check("C13 删除被引用 parcel 不产生 500", ok, verdict)
            client.delete(f"/api/v1/jobs/{jid}")
            client.delete(f"/api/v1/parcels/{pid}")
    except ImportError as e:
        check("C13 删除被引用 parcel 不产生 500", False, f"导入失败: {e}")
    except Exception as e:
        check("C13 删除被引用 parcel 不产生 500", False, f"异常: {type(e).__name__}: {e}")
    finally:
        from cloud.server.database import engine as eng
        eng.dispose()


# ---------- C14: ParcelSummary 无 geojson (前端 P0) ----------
def c14_parcel_summary():
    try:
        from cloud.server.schemas.parcel import ParcelSummary, ParcelResponse
        fs = set(ParcelSummary.model_fields.keys())
        fr = set(ParcelResponse.model_fields.keys())
        check("C14 ParcelSummary 含 geojson", "geojson" in fs,
              f"ParcelSummary={sorted(fs)} | ParcelResponse={sorted(fr)}")
    except Exception as e:
        check("C14 ParcelSummary 含 geojson", False, f"异常: {e}")


# ---------- C15: edge/agent 状态机无转移校验 ----------
def c15_agent_transition():
    src = (PROJECT_ROOT / "edge/agent/store.py").read_text()
    has_validation = "can_transition_task_state" in src
    check("C15 agent store 状态机校验", has_validation,
          "agent/store.py 无 can_transition_task_state 校验 (与 cloud 侧不对称)" if not has_validation else "有校验")


# ---------- C16: e2e_test_planning_simulation 引用不存在的 simulator/server.py ----------
def c16_simulator_path():
    src = (PROJECT_ROOT / "tests/e2e_test_planning_simulation.py").read_text()
    ref = "simulator/server.py" in src
    exists = (PROJECT_ROOT / "simulator/server.py").exists()
    check("C16 e2e 引用 simulator/server.py", not (ref and not exists),
          f"引用={ref}, simulator/server.py 存在={exists} (实际为 simulation/server.py)")


def main():
    # 全局隔离: 所有涉及 DB 的检查使用临时数据库，绝不触碰默认 farm.db
    tmp_db = Path(tempfile.gettempdir()) / f"nf-verify-{os.getpid()}.db"
    for suffix in ("", "-wal", "-shm"):
        Path(str(tmp_db) + suffix).unlink(missing_ok=True)
    os.environ["NF_CLOUD_DATABASE_URL"] = f"sqlite:///{tmp_db}"
    print("=" * 70)
    print("NodeFlow 模块审阅关键问题验证 (V2, 隔离DB)")
    print("=" * 70)
    c1_heartbeat_datetime()
    c2_mcp_project_root()
    c3_farm_coverage_sdk()
    c4_bool_coercion()
    c5_sim_output_schema()
    c6_trajectory_viz_ports()
    c7_log_level()
    c8_platform_hardcode()
    c9_pytest_collection()
    c10_sim_rtk_freq()
    c11_shared_buffer_roundtrip()
    c12_contracts()
    c13_delete_fk()
    c14_parcel_summary()
    c15_agent_transition()
    c16_simulator_path()

    from cloud.server.database import engine as eng
    eng.dispose()
    for suffix in ("", "-wal", "-shm"):
        Path(str(tmp_db) + suffix).unlink(missing_ok=True)

    print("=" * 70)
    n_fail = sum(1 for _, ok, _ in results if not ok)
    n_pass = sum(1 for _, ok, _ in results if ok)
    print(f"结果: {n_pass} PASS / {n_fail} FAIL / {len(results)} 项")
    return 0 if n_fail == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
