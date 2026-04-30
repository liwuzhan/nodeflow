# NodeFlow Bug 修复方案

> 基于 `docs/BUG_REPORT.md`（GPT 交叉验证版）  
> 审阅反馈: `docs/BUG_FIX_PLAN_REVIEW_20260430.md`  
> 日期: 2026-04-30  
> 状态: 方案已修订（v2）

---

## 审阅后的方案调整

> 标注 `[REVISED]` 的条目为根据审阅意见重写的方案。

| 原方案 | 问题 | 修订方向 |
|--------|------|----------|
| FIX-09 锁外写盘 | 多线程写盘乱序 → 数据回退 | 保持锁内写盘，仅加 WAL/journal 优化 |
| FIX-07 threading.Lock | 跨线程操作 asyncio.Queue 仍不安全 | loop.call_soon_threadsafe + event loop 记录 |
| FIX-04 RUNNING 延迟 | wait(60) 在循环体前，实际延迟 62s | 分离首次上报逻辑，用短周期(500ms)独立确认 |
| FIX-02 buffer 等待 | MQTT 线程 sleep 10s 阻塞全部消息 | 快速失败 + 工作线程异步重试 |
| FIX-14 假进度 | 时间估算比未知更误导 | 显式上报 unknown，不加推测 |
| FIX-03 异常恢复 | 只上报 FAILED 不清理本地状态 | 统一 mark_failed() 收口 |
| FIX-01 步骤推进 | 缺幂等保护 | 加 step 状态守卫 |
| FIX-08 WAL | 表述过度承诺 | 改为"缓解"措辞 |
| FIX-10 psutil | 测试工具引入新依赖 | 用 subprocess + `ps` 替代 |

---

## 修复总览

| 轮次 | 目标 | 数量 | 
|------|------|------|
| **第一轮** | 闭环缺失 + 假状态 | 6 项 |
| **第二轮** | 并发 + 一致性 | 4 项 |
| **第三轮** | 鲁棒性 + 体验 | 4 项 |
| **低优先级** | 日志/边界/API 规范 | 23 项 |

---

## 第一轮：闭环缺失 + 假状态（🔴 必须修）

### FIX-01: 步骤依赖自动推进 [REVISED]

**Bug**: C-01 — task 全部完成后不会自动下发下一步  
**文件**: `cloud/server/services/mqtt_client.py:157-165`

**审阅建议**: 加幂等保护，避免重复 completed 消息触发重复下发。

```python
# _handle_task_status 内，t.state 更新后添加幂等推进:

if t.state == "completed" and t.step_id:
    self._try_advance_step(db, t)

# 新增方法:
def _try_advance_step(self, db, edge_task):
    from cloud.server.services.dispatcher import Dispatcher

    # 幂等守卫: 先检查 step 当前状态
    step = db.query(JobStep).filter(JobStep.id == edge_task.step_id).first()
    if not step or step.status == "completed":
        return  # 已经推进过了，跳过

    # 检查该 step 所有 task 是否都 completed
    step_tasks = db.query(EdgeTask).filter(
        EdgeTask.step_id == edge_task.step_id
    ).all()
    if not all(et.state == "completed" for et in step_tasks):
        return

    # 标记 step 完成（原子推进）
    step.status = "completed"
    db.commit()

    # 下发下一步
    dispatcher = Dispatcher(self)
    dispatcher.dispatch_next_step(db, edge_task.job_id)
```

**风险**: 低。改动在现有回调内，幂等守卫防止重复下发。

---

### FIX-02: control buffer 创建时序 [REVISED]

**Bug**: E-03 — buffer 不存在时 `execute()` 抛异常，任务卡在 READY  
**文件**: `runtime/task/executor.py:26-42`, `runtime/task/agent.py:77-108`

**审阅建议**: [REVISED] 原方案在 MQTT 回调线程 sleep 10s 会阻塞 paho 网络线程。改为快速失败 + 工作线程重试。

```python
# executor.py — 改造 execute() 为快速失败:
def execute(self, task: Task) -> bool:
    """返回 True 表示 buffer 写入成功，False 表示需要重试"""
    self._current_task_id = task.task_id
    self.store.update_state(task.task_id, TaskState.READY)

    try:
        control_buf = SharedBufferLite("runtime.control", create=False)
    except FileNotFoundError:
        return False  # buffer 尚不存在

    payload = {"command": "start_dataflow", "task_id": task.task_id,
               "node_params": task.node_params, "timestamp": time.time()}
    control_buf.write(payload)
    self.store.update_state(task.task_id, TaskState.RUNNING)
    self._start_monitor(task)
    return True

# agent.py — 在 _handle_dispatch 中，将重试移到工作线程:
def _handle_dispatch(self, payload: dict):
    task_id = payload["task_id"]
    ...
    if self._config.auto_accept:
        self._reporter.send_status(task_id, TaskState.DOWNLOADING)
        self._reporter.send_status(task_id, TaskState.READY)

        # 第一次尝试（在 MQTT 回调线程，非阻塞）
        if self._executor.execute(task):
            self._reporter.send_status(task_id, TaskState.RUNNING)
        else:
            # 转到工作线程重试
            threading.Thread(
                target=self._retry_execute,
                args=(task,),
                daemon=True,
            ).start()

def _retry_execute(self, task: Task):
    """工作线程中重试 execute，避免阻塞 MQTT 回调"""
    deadline = time.time() + 10
    retry_interval = 0.5
    while time.time() < deadline:
        time.sleep(retry_interval)
        try:
            if self._executor.execute(task):
                self._reporter.send_status(task.task_id, TaskState.RUNNING)
                return
        except Exception:
            pass
    # 超时: 标记失败
    logger.error(f"Task {task.task_id} failed: control buffer unavailable")
    self._executor.mark_failed(task.task_id, "Control buffer unavailable after retries")
    self._reporter.send_status(task.task_id, TaskState.FAILED,
                               error_detail="Control buffer unavailable")

# cancel() 同理改为非阻塞快速失败:
def cancel(self, task_id: str):
    self._stop_monitor()
    try:
        control_buf = SharedBufferLite("runtime.control", create=False)
        control_buf.write({"command": "stop_dataflow", "task_id": task_id,
                           "timestamp": time.time()})
    except FileNotFoundError:
        logger.warning(f"Cannot cancel {task_id}: control buffer not found")
    self.store.update_state(task_id, TaskState.CANCELLED)
    if self._current_task_id == task_id:
        self._current_task_id = None
```

**风险**: 中。改造 execute 返回值为 bool，影响调用方。工作线程重试逻辑简单清晰。

---

### FIX-03: execute() 异常恢复 [REVISED]

**Bug**: E-06 — execute() 抛异常后本地状态和心跳未清理  
**文件**: `runtime/task/agent.py:103-108`, `runtime/task/executor.py`

**审阅建议**: [REVISED] 原方案只发送 FAILED 状态，不清理 `_current_task_id` 和本地 store。改为统一 `mark_failed()` 收口。

```python
# executor.py — 可靠的失败收口:
def mark_failed(self, task_id: str, error: str):
    """统一的失败收敛逻辑"""
    self._stop_monitor()
    self._current_task_id = None
    self.store.update_state(task_id, TaskState.FAILED, error_message=error)

# agent.py — _handle_dispatch 的异常路径:
try:
    ok = self._executor.execute(task)
    if ok:
        self._reporter.send_status(task_id, TaskState.RUNNING)
    # 不 ok 的情况由 _retry_execute 处理
except Exception as e:
    logger.error(f"Task {task_id} dispatch failed: {e}")
    self._executor.mark_failed(task_id, str(e))
    self._reporter.send_status(task_id, TaskState.FAILED, error_detail=str(e))

# agent.py — _handle_cancel 同样收敛:
def _handle_cancel(self, payload: dict):
    task_id = payload["task_id"]
    if not self._store.exists(task_id):
        logger.warning(f"Cancel for unknown task {task_id}, ignored")
        return
    self._executor.mark_failed(task_id, "cancelled by operator")
    self._reporter.send_status(task_id, TaskState.CANCELLED)
```

**风险**: 低。`mark_failed()` 统一收敛 `_current_task_id` 清理 + store 状态 + monitor 停止。

---

### FIX-04: 假 RUNNING 状态 [REVISED]

**Bug**: E-10 — RUNNING 在 daemon 实际启动前就上报  
**文件**: `runtime/task/agent.py:108`, `runtime/task/executor.py`

**审阅建议**: [REVISED] 原方案 wait(60) 在循环体前，实际延迟 62s。改为独立短周期确认。

```python
# agent.py — 在 _handle_dispatch 中，RUNNING 上报改为延迟确认:
def _handle_dispatch(self, payload: dict):
    ...
    if self._config.auto_accept:
        ...
        if self._executor.execute(task):
            # 延迟 2s 再报 RUNNING（等 daemon 完成 0.5s 轮询 + 启动）
            threading.Timer(2.0, lambda: self._reporter.send_status(
                task.task_id, TaskState.RUNNING
            )).start()

# executor.py — 监控线程发首次 RUNNING 后可以后续做真实检测:
def _monitor_loop(self, task: Task):
    # 注: RUNNING 上报已移到 agent 中，此线程只做进度日志
    while not self._monitor_stop.wait(60):
        try:
            progress = self._compute_progress(task)
            logger.info(f"Task {task.task_id}: {progress.current_node}")
        except Exception as e:
            logger.error(f"Progress monitor error: {e}")
```

**风险**: 低。2s 的 `threading.Timer` 独立于主循环，不阻塞 MQTT 线程。

---

### FIX-05: del() 无错误处理

**Bug**: F-01 — `del()` 不检查 HTTP 状态码  
**文件**: `cloud/web/src/services/api.ts:28-30`

**无审阅异议，保持原方案**:

```typescript
export async function del(path: string): Promise<void> {
  await request<void>(path, { method: 'DELETE' })
}
```

同时修复 `request` 对 204 空 body 的处理 (F-03):

```typescript
async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    headers: { 'Content-Type': 'application/json', ...options?.headers },
    ...options,
  })
  if (!res.ok) {
    let detail = res.statusText || `HTTP ${res.status}`
    try {
      const err = await res.json()
      detail = err.detail || detail
    } catch (_) { /* non-JSON error body */ }
    throw new Error(detail)
  }
  if (res.status === 204) return undefined as T
  const body = await res.json()
  return body.data ?? body
}
```

**风险**: 低。

---

### FIX-06: JobDetailView 重复定时器

**Bug**: F-08 — handleDispatch 创建新定时器不清理旧的  
**文件**: `cloud/web/src/views/JobDetailView.vue:77-97`

**无审阅异议，保持原方案**:

```typescript
function startPolling() {
  stopPolling()
  pollTimer = setInterval(async () => {
    job.value = await jobStore.fetchJobDetail(route.params.id as string)
  }, 5000)
}

function stopPolling() {
  if (pollTimer) { clearInterval(pollTimer); pollTimer = null }
}
```

**风险**: 低。

---

## 第二轮：并发 + 一致性（🟡 应尽快修）

### FIX-07: SSE broker 线程安全 [REVISED]

**Bug**: C-13 — `_queues` 无锁保护  
**文件**: `cloud/server/services/sse_broker.py:9-31`

**审阅建议**: [REVISED] `threading.Lock` 只能保护列表操作，不能解决跨线程操作 `asyncio.Queue` 的问题。改用 `loop.call_soon_threadsafe`。

```python
import threading
import asyncio
import json

class SSEBroker:
    def __init__(self):
        self._subscribers: list[tuple[asyncio.AbstractEventLoop, asyncio.Queue]] = []
        self._lock = threading.Lock()

    def publish(self, event_type: str, data: dict):
        payload = {"event": event_type, "data": json.dumps(data, default=str)}
        with self._lock:
            subscribers = list(self._subscribers)  # 快照
        for loop, queue in subscribers:
            # 线程安全投递: 在目标 event loop 上下文中执行 put
            loop.call_soon_threadsafe(
                lambda q=queue, p=payload: q.put_nowait(p) if not q.full() else None
            )

    async def subscribe(self) -> AsyncGenerator[dict, None]:
        queue: asyncio.Queue = asyncio.Queue(maxsize=256)
        loop = asyncio.get_running_loop()
        with self._lock:
            self._subscribers.append((loop, queue))
        try:
            while True:
                msg = await queue.get()
                yield msg
        except asyncio.CancelledError:
            pass
        finally:
            with self._lock:
                self._subscribers.remove((loop, queue))
```

**风险**: 中。`asyncio.Queue.put_nowait` 本身是线程安全的 1，`call_soon_threadsafe` 确保在正确的 event loop 中执行。

---

### FIX-08: SQLite 写入串行化缓解 [REVISED]

**Bug**: C-03 — 多线程并发写可能 `database is locked`  
**文件**: `cloud/server/database.py:5-11`, `cloud/server/app.py`

**审阅建议**: [REVISED] 原方案表述过度承诺。WAL + timeout 是缓解而非根治。改措辞为"降低概率"。

```python
# database.py
engine = create_engine(
    settings.DATABASE_URL,
    connect_args={
        "check_same_thread": False,
        "timeout": 10,  # 等待 10s 而非立即报错
    },
    echo=False,
)

# app.py lifespan startup 中:
@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(bind=engine)
    with engine.connect() as conn:
        conn.exec_driver_sql("PRAGMA journal_mode=WAL")  # 读写并发
        conn.exec_driver_sql("PRAGMA busy_timeout=5000")  # 5s 忙等待
        conn.commit()
    ...
```

**风险**: 低。WAL 是 SQLite 标准推荐配置。后续如需彻底解决，可将 SQLite 替换为 PostgreSQL（生产部署时）。

---

### FIX-09: store 锁优化（保守方案）[REVISED]

**Bug**: E-02 — `_save()` 持有锁期间做磁盘 I/O  
**文件**: `runtime/task/store.py:31-38, 60-83`

**审阅建议**: [REVISED] 原方案锁外写盘会导致多线程写入乱序 → 磁盘回退到旧状态。**改为保守方案：保持锁内写盘，仅优化写入策略。**

```python
# 保守方案: 保持当前锁模型，仅做以下优化:
# 1. 减少 json.dump 的 indent 开销（生产环境用紧凑格式）
# 2. 合并频繁的 update_state 调用（同一秒内多次变化只写一次盘）

def _save(self):
    path = Path(self.STORE_PATH)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = str(path) + ".tmp"
    data = [t.to_dict() for t in self._tasks.values()]
    with open(tmp, "w") as f:
        json.dump(data, f, separators=(",", ":"))  # 紧凑格式，减少 I/O
    os.replace(tmp, str(path))
```

**后续可选方案**（如锁竞争成为瓶颈再实施）:
- 引入专用写线程 + 版本号队列，确保顺序落盘
- 或在 Python 3.12+ 使用 `asyncio.to_thread` + 单写者模式

**风险**: 低。当前锁模型是正确的（不会出现乱序覆盖），仅优化 I/O 量。

---

### FIX-10: e2e PID 误杀保护 [REVISED]

**Bug**: T-02 — PID 复用导致误杀  
**文件**: `tests/e2e_cli.py:91-106`

**审阅建议**: [REVISED] 不引入 `psutil` 依赖。用 `ps` 命令校验。

```python
import subprocess

def _verify_process(pid: int, expected_name: str) -> bool:
    """验证 PID 对应的进程是否匹配预期名称"""
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
        if not _verify_process(pid, name):
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
```

**风险**: 低。仅测试工具。`ps` 是 POSIX 标准命令，无需额外依赖。

---

## 第三轮：鲁棒性 + 体验（🟢 有条件的修）

### FIX-11: 重复 task 应发拒绝 ACK

**Bug**: E-07 — 重复 task_id 静默丢弃不回应  
**文件**: `runtime/task/agent.py:82-84`

```python
if self._store.exists(task_id):
    logger.info(f"Task {task_id} duplicate, sending reject ACK")
    self._reporter.send_ack(task_id, payload.get("dispatch_id", ""),
                            accepted=False, reject_reason="duplicate_task_id")
    return
```

### FIX-12: cancel 前校验 task 存在

**Bug**: E-09 — 取消未知 task 仍发 CANCELLED  
**文件**: `runtime/task/agent.py:110-114`

```python
def _handle_cancel(self, payload: dict):
    task_id = payload["task_id"]
    if not self._store.exists(task_id):
        logger.warning(f"Cancel for unknown task {task_id}, ignored")
        return
    self._executor.mark_failed(task_id, "cancelled by operator")
    self._reporter.send_status(task_id, TaskState.CANCELLED)
```

### FIX-13: API 状态码规范化

**Bug**: C-18, C-19 — 重复资源返回 400 应为 409  
**文件**: `cloud/server/routers/machines.py:39`, `cloud/server/routers/parcels.py:26`

```python
# machines.py
raise HTTPException(409, f"Machine '{body.id}' already registered")

# parcels.py
raise HTTPException(409, f"Parcel '{body.name}' already exists")
```

### FIX-14: progress 上报真实状态 [REVISED]

**Bug**: E-04 — `_compute_progress` 返回全零假数据  
**文件**: `runtime/task/executor.py:84-96`

**审阅建议**: [REVISED] 原方案用时间估算假进度比"未知"更危险。**改为显式上报"未知"**。

```python
def _compute_progress(self, task: Task) -> TaskProgress:
    """返回当前已知状态，不推测未知信息"""
    progress = TaskProgress(
        task_id=task.task_id,
        machine_id=self.machine_id,
        state=task.state,
        progress_pct=0.0,
        current_node="unknown",
    )
    try:
        buf = SharedBufferLite("runtime.control", create=False)
        seq = buf.get_sequence()
        if seq > 0:
            progress.current_node = "dispatched"
    except Exception:
        pass
    return progress
```

**后续方向**: 真实进度应来自 `runtime/monitoring/node_monitor.py` 的节点健康状态（该模块已有 PID 监控和重启追踪），通过新增一个 `node_monitor.status` shared buffer 暴露给 executor 读取。

**风险**: 低。显式上报 unknown 比伪进度更安全。

---

## 改动文件汇总（修订版）

### 边侧

| 文件 | 第一轮 | 第二轮 | 第三轮 |
|------|--------|--------|--------|
| `runtime/task/store.py` | | FIX-09 | |
| `runtime/task/executor.py` | FIX-02, FIX-04 | | FIX-14 |
| `runtime/task/agent.py` | FIX-02, FIX-03, FIX-04 | | FIX-11, FIX-12 |

### 云端

| 文件 | 第一轮 | 第二轮 | 第三轮 |
|------|--------|--------|--------|
| `cloud/server/services/mqtt_client.py` | FIX-01 | | |
| `cloud/server/services/sse_broker.py` | | FIX-07 | |
| `cloud/server/database.py` | | FIX-08 | |
| `cloud/server/app.py` | | FIX-08 | |
| `cloud/server/routers/machines.py` | | | FIX-13 |
| `cloud/server/routers/parcels.py` | | | FIX-13 |

### 前端

| 文件 | 第一轮 | 第二轮 | 第三轮 |
|------|--------|--------|--------|
| `cloud/web/src/services/api.ts` | FIX-05 | | |
| `cloud/web/src/views/JobDetailView.vue` | FIX-06 | | |

### 测试

| 文件 | 第一轮 | 第二轮 | 第三轮 |
|------|--------|--------|--------|
| `tests/e2e_cli.py` | | FIX-10 | |

---

## 修订前后对比

| 方案 | v1 风险 | v2 改动 |
|------|---------|---------|
| FIX-09 store | 🔴 写盘乱序回退 | 保持锁内写盘，仅紧凑 JSON |
| FIX-07 SSE | 🟡 跨线程 Queue 不安全 | call_soon_threadsafe + event loop |
| FIX-04 RUNNING | 🔴 实际延迟 62s | Timer(2s) 独立短周期 |
| FIX-02 buffer | 🔴 MQTT 线程阻塞 10s | 快速失败 + 工作线程重试 |
| FIX-03 异常 | 🟡 不清理本地状态 | mark_failed() 统一收口 |
| FIX-14 progress | 🟡 假进度误导 | 显式 unknown + 后续接 node_monitor |
| FIX-01 推进 | 🟢 缺幂等 | 加 step 状态守卫 |
| FIX-08 WAL | 🟢 措辞过度 | 改为"缓解" |
| FIX-10 psutil | 🟢 新依赖 | 改用 ps 命令 |

---

## 低优先级修改清单

| 编号 | 文件 | 改动 | 类型 |
|------|------|------|------|
| E-01 | store.py:28 | `_load()` 改为逐条反序列化，损坏项跳过而非全删 | 鲁棒性 |
| E-05 | executor.py:66 | `_stop_monitor` join 超时后 force-stop 线程 | 资源泄漏 |
| E-08 | agent.py:43 | `stop()` 调整顺序：先 cancel timer → set _running → loop_stop | 顺序 |
| E-11 | agent.py:25 | `start()` 中先 subscribe 再 loop_start | 顺序 |
| E-12 | reporter.py:56 | 检查 `publish()` 返回值并记录失败 | 日志 |
| E-14 | main.py:313 | `_apply_node_params` 改为 deep merge | 功能增强 |
| E-15 | main.py:304 | 加 `hasattr` 检查 + 异常明确日志 | 防御性 |
| E-16 | main.py:650 | 时间戳去重改为 `>` 或加入序列号去重 | 边界 |
| C-02 | mqtt_client.py:124 | auto-create 增加 try/except IntegrityError | 幂等 |
| C-04 | mqtt_client.py:150 | 未知 edge_task_id 加 `logger.warning` | 日志 |
| C-05 | mqtt_client.py:181 | 未知 dispatch_id 加 `logger.warning` | 日志 |
| C-06 | mqtt_client.py:187 | 旧 ACK 匹配失败加 debug 日志 | 日志 |
| C-11 | dispatcher.py:170 | `_get_or_create_splits` 无分配时加 warning | 校验 |
| C-12 | splitter.py:137 | MultiPolygon 结果显式处理 | 类型安全 |
| C-14 | events.py:13 | SSE 添加周期性 keepalive 注释帧 | 可靠性 |
| F-02 | api.ts:8 | 错误处理增加 HTTP status code 到错误消息 | 体验 |
| F-04 | machineStore.ts:21 | 添加轮询暂停/恢复机制 | 资源 |
| F-05 | jobStore.ts:46 | SSE 事件缓存队列，详情加载后回放 | 数据一致性 |
| F-06 | JobCreateView.vue:110 | 表单状态保存到 sessionStorage | 体验 |
| F-07 | JobCreateView.vue:115 | `splitCount` 变更时清理 machineAssignments | 数据一致性 |
| F-09 | MachineDashboard.vue:34 | `handleConfirm` 添加 try/catch + 错误提示 | 体验 |
| F-10 | ParcelLayer.vue:41 | `L.geoJSON` 调用包裹 try/catch | 鲁棒性 |
| F-11 | SplitPreview.vue:47 | 支持 MultiPolygon 坐标结构 | 类型安全 |
| F-12 | statusStream.ts:29 | 添加可见重连状态 + 用户提示 | 体验 |
| T-01 | e2e_cli.py:205 | start 后订阅确认 | 可靠性 |
| T-03 | e2e_cli.py:84 | `_is_running` 排除僵尸进程 | 可靠性 |

---

## 每轮预估影响

| 轮次 | 文件数 | 改动行数 | 风险 | 可单独部署 |
|------|--------|----------|------|-----------|
| 第一轮 | 4 | ~100 | 低 | FIX-01/05/06 独立; FIX-02~04 联动 |
| 第二轮 | 4 | ~60 | 中（SSE 模型变更） | FIX-08/09/10 独立; FIX-07 需回归 SSE |
| 第三轮 | 4 | ~30 | 低 | ✓ 各自独立 |
| 低优先 | 25 | ~200 | 极低 | ✓ |
