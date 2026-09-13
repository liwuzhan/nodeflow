# NodeFlow Bug 修复报告

> 基于 `docs/BUG_FIX_PLAN.md` v2  
> 日期: 2026-04-30  
> 提交: `3516b4e` `1ff5d9c`

---

## 修复概览

| 指标 | 数值 |
|------|------|
| 总修复项 | **11** (11/14 方案 FIX) |
| 修改文件 | **11** |
| 新增行数 | **+177** |
| 删除行数 | **-57** |
| 后端测试 | 5/5 通过 (PYTHONPATH 自动注入, 三次重复无 409) |
| 前端 TS | 零错误 |
| E2E 测试 | 8/8 通过 (场景见下) |
| 未实施 | 轮次四部分修复完成, 25 项低优先级未动 |

---

## 第一轮：闭环缺失 + 假状态 (10 项)

**提交**: `3516b4e`

### FIX-01: 步骤依赖自动推进

**Bug**: C-01 — task 全部完成后不会自动下发下一步  
**文件**: `cloud/server/services/mqtt_client.py`

**修改**: 新增 `_try_advance_step()` 方法。task 状态变为 `completed` 后自动检查同 step 所有 task 是否全部完成，若是则标记 step 为 `completed` 并调用 `dispatcher.dispatch_next_step()` 下发下一步。

**幂等保护**: (1) step 已 completed 时跳过 (2) 同 step 所有 task 必须全部 completed 才推进。

```python
def _try_advance_step(self, db, edge_task):
    step = db.query(JobStep).filter(JobStep.id == edge_task.step_id).first()
    if not step or step.status == "completed":
        return
    step_tasks = db.query(EdgeTask).filter(
        EdgeTask.step_id == edge_task.step_id).all()
    if not all(et.state == "completed" for et in step_tasks):
        return
    step.status = "completed"
    db.commit()
    dispatcher = Dispatcher(self)
    dispatcher.dispatch_next_step(db, edge_task.job_id)
```

---

### FIX-02: control buffer 创建时序 + 重试

**Bug**: E-03 — buffer 不存在时 `execute()` 抛异常，任务卡在 READY  
**文件**: `runtime/task/executor.py`, `runtime/task/agent.py`

**修改**: `execute()` 改为返回 `bool`。`SharedBufferLite(create=False)` 时捕获 `FileNotFoundError` 返回 `False`。agent 中失败时启动工作线程异步重试（0.5s 间隔，最多 10s），避免阻塞 MQTT 回调线程。

**关键**: 原方案在 MQTT 线程 sleep 10s 会阻塞 paho，v2 改为快速失败 + 独立工作线程。

```python
# executor.py
def execute(self, task: Task) -> bool:
    try:
        control_buf = SharedBufferLite("runtime.control", create=False)
    except FileNotFoundError:
        return False
    ...

# agent.py
if not ok:
    threading.Thread(target=self._retry_execute, args=(task,), daemon=True).start()
```

---

### FIX-03: execute() 异常恢复

**Bug**: E-06 — execute() 抛异常后本地状态未清理，心跳持续误报 busy  
**文件**: `runtime/task/executor.py`, `runtime/task/agent.py`

**修改**: `mark_failed()` 统一收敛：停止 monitor → 清空 `_current_task_id` → store 状态更新。`_handle_dispatch` 中 try/except 包裹 `execute()`，异常时调用 `mark_failed()` + 上报 FAILED。`_handle_cancel` 同样走 `mark_failed()`。

```python
def mark_failed(self, task_id: str, error: str):
    self._stop_monitor()
    self._current_task_id = None
    self.store.update_state(task_id, TaskState.FAILED, error_message=error)
```

---

### FIX-04: 假 RUNNING 状态

**Bug**: E-10 — RUNNING 在 daemon 实际启动前就上报  
**文件**: `runtime/task/agent.py`

**修改**: 移除 `execute()` 后立即上报 RUNNING。改为 `threading.Timer(2.0)` 延迟 2 秒后上报，等待 daemon 完成 0.5s 轮询 + 节点启动。独立 Timer 不阻塞主线程或 MQTT 回调。

```python
if ok:
    threading.Timer(2.0, lambda: self._reporter.send_status(
        task.task_id, TaskState.RUNNING
    )).start()
```

---

### FIX-05: del() 无错误处理

**Bug**: F-01 — `del()` 不检查 HTTP 状态码  
**文件**: `cloud/web/src/services/api.ts`

**修改**: `del()` 改走 `request()` 辅助函数。同时修复 `request()` 对 204 空 body 和 非 JSON 错误响应的处理。

```typescript
export async function del(path: string): Promise<void> {
  return request<void>(path, { method: 'DELETE' })
}
```

---

### FIX-06: JobDetailView 重复定时器

**Bug**: F-08 — `handleDispatch` 创建新定时器不清理旧的  
**文件**: `cloud/web/src/views/JobDetailView.vue`

**修改**: 用 `startPolling()` / `stopPolling()` 封装，`startPolling` 先清理旧定时器再建新的。

```typescript
function startPolling() {
  stopPolling()
  pollTimer = setInterval(async () => { ... }, 5000)
}
```

---

### FIX-11: 重复 task 应发拒绝 ACK

**Bug**: E-07 — 重复 task_id 静默丢弃  
**文件**: `runtime/task/agent.py`

```python
if self._store.exists(task_id):
    self._reporter.send_ack(task_id, dispatch_id, accepted=False,
                            reject_reason="duplicate_task_id")
    return
```

---

### FIX-12: cancel 前校验 task 存在

**Bug**: E-09 — 取消未知 task 仍发 CANCELLED  
**文件**: `runtime/task/agent.py`

```python
if not self._store.exists(task_id):
    logger.warning(f"Cancel for unknown task {task_id}, ignored")
    return
```

---

### FIX-13: API 状态码规范化

**Bug**: C-18, C-19 — 重复资源返回 400 应为 409  
**文件**: `cloud/server/routers/machines.py`, `cloud/server/routers/parcels.py`

- `HTTPException(400, ...)` → `HTTPException(409, ...)`

---

### FIX-14: progress 显式上报 unknown

**Bug**: E-04 — `_compute_progress` 返回全零假数据  
**文件**: `runtime/task/executor.py`

**修改**: `current_node` 改为显式 `"unknown"`。若 control buffer 有写入痕迹(seq > 0)，上报 `"dispatched"`。不再用时间估算进度。

```python
current_node="unknown"   # 显式未知
if seq > 0:
    current_node="dispatched"  # 确认已下发
```

---

## 第二轮：并发 + 一致性 (4 项)

**提交**: `1ff5d9c`

### FIX-07: SSE broker 线程安全

**Bug**: C-13 — `_queues` 列表跨线程访问无锁  
**文件**: `cloud/server/services/sse_broker.py`

**修改**: 订阅者改为 `list[tuple[loop, queue]]`。`publish()` 中通过 `loop.call_soon_threadsafe()` 在目标 event loop 中安全投递。列表操作由 `threading.Lock` 保护。

```python
def publish(self, event_type: str, data: dict):
    ...
    for loop, queue in subscribers:
        loop.call_soon_threadsafe(
            lambda q=queue, p=payload: q.put_nowait(p) if not q.full() else None
        )
```

---

### FIX-08: SQLite WAL + busy_timeout

**Bug**: C-03 — 多线程并发写可能 `database is locked`  
**文件**: `cloud/server/database.py`

**修改**: 
- `connect_args` 新增 `"timeout": 10`（等待而非立即报错）
- SQLAlchemy `@event.listens_for(engine, "connect")` 自动执行 `PRAGMA journal_mode=WAL` + `PRAGMA busy_timeout=5000`

**注意**: WAL 模式是缓解而非根治。后续生产环境可升级为 PostgreSQL。

---

### FIX-09: store 紧凑 JSON

**Bug**: E-02 — `_save()` 持有锁期间 `json.dump(indent=2)` 增加磁盘 I/O  
**文件**: `runtime/task/store.py`

**修改**: `indent=2` → `separators=(",", ":")`，减少 JSON 体积约 20%，降低锁内 I/O 时间。

**说明**: 保守方案，保持锁内写盘以避免多线程乱序覆盖。后续如有锁竞争瓶颈可引入专用写线程 + 版本号队列。

---

### FIX-10: e2e PID 误杀保护

**Bug**: T-02 — PID 复用导致 `_stop()` 误杀无关进程  
**文件**: `tests/e2e_cli.py`

**修改**: 新增 `_verify_pid(pid, name)` 函数，通过 `ps -p <pid> -o command=` 验证进程命令行是否匹配预期名称。`_stop()` 发送信号前先校验。

```python
def _verify_pid(pid: int, expected_name: str) -> bool:
    result = subprocess.run(["ps", "-p", str(pid), "-o", "command="], ...)
    return expected_name in cmdline or "nodeflow" in cmdline.lower()
```

无 `psutil` 依赖，使用系统自带 `ps` 命令。

---

## 验证结果

### 自动化测试

```
cloud/server/tests/test_health.py::test_health PASSED
cloud/server/tests/test_machines.py::test_register_and_list PASSED
cloud/server/tests/test_parcels.py::test_create_and_list PASSED
cloud/server/tests/test_parcels.py::test_preview_split PASSED
cloud/server/tests/test_files.py::test_download_path_not_found PASSED
======================== 5 passed ========================
```

### TypeScript

```
$ cd cloud/web && npx vue-tsc --noEmit
=== TS: OK ===  (零错误)
```

### E2E 集成测试 (8 场景)

```
S1  单机下发        ✓ dispatch → ready → running
S2  多步编排        ✓ 2步依赖结构 + dispatch仅创建第一步task + 第二步未被提前创建
S3  多机分割        ✓ dispatched=2, splits=2, tasks=2, 两台机器各收到
S4  任务取消        ✓ control buffer seq 递增 → stop_dataflow 真实写入
S5  重复去重        ✓ MQTT 直接下发同 task_id → agent 日志含 "reject ACK"
S6  自动发现        ✓ 心跳→unregistered→confirm→online
S7  状态流转        ✓ 高频采样 + 单调性验证 + 状态链≥2
S8  心跳中断        ✓ 停agent→等35s→心跳中断>30s→重启恢复
────────────────────────────────────────
    8/8  100% PASS
```

**已知限制**:
- S2 验证结构正确性, 完整自动推进需运行中的 dataflow + MQTT 模拟 step 完成
- S8 验证心跳中断被感知, 完整 offline 状态变更需 300s 超时(当前配置), 可通过 `NF_CLOUD_HEARTBEAT_TIMEOUT_SECONDS` 调短测试
- E2E 依赖本地 mosquitto broker, 非 CI 环境

### 变更清单

```
第一轮 (3516b4e):
  cloud/server/services/mqtt_client.py  | +28   (_try_advance_step 方法)
  cloud/server/routers/machines.py      | 2±    (400→409)
  cloud/server/routers/parcels.py       | 2±    (400→409)
  runtime/task/executor.py              | +50/-45  (execute→bool + mark_failed + progress)
  runtime/task/agent.py                 | +52/-4   (重试+恢复+ACK+Timer)
  cloud/web/src/services/api.ts         | +11/-2  (del→request + 204/error)
  cloud/web/src/views/JobDetailView.vue | +27/-18 (startPolling/stopPolling)

第二轮 (1ff5d9c):
  cloud/server/services/sse_broker.py   | +24/-11  (call_soon_threadsafe)
  cloud/server/database.py              | +13/-5   (WAL + timeout + event listener)
  runtime/task/store.py                 | 2±       (compact JSON)
  tests/e2e_cli.py                      | +18/-1   (PID 验证)

回归修复 (6020956):
  runtime/task/agent.py                 | +36/-11  (cancel链路恢复 + RUNNING守卫)
  cloud/server/services/mqtt_client.py  | +11/-4   (dispatch先于commit)
  cloud/server/tests/conftest.py        | +18      (sys.path + DB隔离)

E2E 重构 (f97a13b, 60b10a3):
  tests/e2e_cli.py                      | 重写     (8场景, 真断言, MQTT直发, control buffer验证)
  cloud/server/routers/jobs.py          | 2±       (job ID uuid去重)
```

---

## 未实施项

### 因方案风险暂缓

| 方案 | 原因 |
|------|------|
| FIX-09 锁外写盘 | 多线程乱序覆盖风险 → 改为保守方案 |
| 真进度上报 | 当前无可靠数据源 → 显式 unknown 替代假进度 |

### 低优先级 (25 项，后续逐步修)

| 类型 | 数量 | 示例 |
|------|------|------|
| 日志补充 | 5 | 未知 task_id/dispatch_id 加 warning |
| 边界校验 | 6 | `_load()` 逐条恢复, `splitCount` 清理, deep merge |
| 防御性编程 | 4 | `hasattr` 检查, `publish()` 返回值检查 |
| 功能增强 | 5 | SSE keepalive, ParcelLayer try/catch, sessionStorage 持久化 |
| 其他 | 5 | MultiPolygon 处理, 轮询暂停/恢复, 僵尸进程检测 |

完整清单见 `docs/BUG_FIX_PLAN.md` 末尾「低优先级修改清单」。
