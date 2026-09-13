# NodeFlow 云端系统 Bug 审查报告

> 审查日期: 2026-04-30  
> 交叉验证: 2026-04-30 (GPT 逐项核对)  
> 范围: `runtime/task/` `cloud/server/` `cloud/web/` `tests/`  
> 原始发现 59 项 → 交叉验证后 **29 项确认成立**，3 项移除，5 项改写

---

## 验证标签说明

- ✅ **确认成立**: 代码行为与报告描述一致
- ✏️ **部分成立**: 问题存在但描述需修正（已在表述中修正）
- ⚠️ **需前提**: 需要特定部署条件才触发（已标注前提）
- ❌ **不成立**: 代码不支持该结论（已移除或降级）

---

## 1. 边侧 — `runtime/task/store.py`

**模块**: Edge / 任务持久化

| # | 行号 | 验证 | 严重度 | 问题 |
|---|------|------|--------|------|
| E-01 | 28-29 | ✅ | 🔴 严重 | `_load()` 中单个 task JSON 损坏（缺 `task_id` 触发 `KeyError`）→ 整个 `tasks.json` 被删除，所有历史任务丢失。无部分恢复、无备份。 |
| E-02 | 60-63 | ✅ | 🟡 高危 | `save()` / `update_state()` / `remove()` 在持有 `self._lock` 时调用 `_save()`（含 `json.dump` + `os.replace` 真实磁盘 I/O），阻塞所有其他线程对该 store 的读写。 |

---

## 2. 边侧 — `runtime/task/executor.py`

**模块**: Edge / 任务执行器

| # | 行号 | 验证 | 严重度 | 问题 |
|---|------|------|--------|------|
| E-03 | 31, 47 | ✏️ | 🔴 严重 | `SharedBufferLite("runtime.control", create=False)` — 若 daemon 尚未创建 buffer 文件抛 `FileNotFoundError` 且未捕获。**execute() 中任务状态先设为 READY，但 buffer 打开失败 → 写入失败 → 任务停留在 READY**，不会自动恢复。cancel() 同理。 |
| E-04 | 84-96 | ✅ | 🟡 高危 | `_compute_progress` 只构造默认 `TaskProgress(progress_pct=0, nodes_healthy=0, nodes_total=0)`，`current_node` 伪装为 `seq:N`。进度上报完全无意义。 |
| E-05 | 19, 66-69 | ✏️ | 🟢 中低 | 原 E-07/E-08 合并。`_stop_monitor()` 的 `join(timeout=2)` 超时后不强制终止线程，若旧监控线程未能在 2s 内结束，后续 `execute()` 可再启新监控线程，形成残留线程。`Event.clear()` 不会唤醒等待线程，但多次 `execute()` 的状态共享仍存在风险。 |

---

## 3. 边侧 — `runtime/task/agent.py`

**模块**: Edge / MQTT 接收协调

| # | 行号 | 验证 | 严重度 | 问题 |
|---|------|------|--------|------|
| E-06 | 103-108 | ✏️ | 🔴 严重 | `executor.execute()` 抛异常（如 E-03）后，异常被 `_on_message` 总 catch 捕获。在此之前任务已保存、ACK 已发、`DOWNLOADING` 和 `READY` 已上报。但 `RUNNING` 不会发送，任务状态停留在 READY 且无恢复机制。 |
| E-07 | 82-84 | ✅ | 🟡 高危 | 重复 task_id 时直接 `return`，不发送 ACK 也不返回拒绝原因。云端若按 ACK 超时重试，边侧持续忽略，形成死循环。 |
| E-08 | 43-48 | ✅ | 🟡 高危 | `stop()` 中 `_running=False` → `_stop_heartbeat()` → `loop_stop()` 之间有竞态窗口：心跳定时器可能在 `loop_stop()` 之后仍在 `publish()`。 |
| E-09 | 110-114 | ✅ | 🟡 高危 | 取消请求没有先校验任务是否存在，`_executor.cancel()` 尝试写 control buffer 可能失败（E-03），随后 reporter 无条件上报 CANCELLED。 |
| E-10 | 108 | ✅ | 🟡 高危 | `RUNNING` 状态由 agent 在 `executor.execute()` 返回后立即上报。daemon 真正读取 control buffer 在 `runtime.main` 的 0.5 秒轮询内，加上实际节点启动耗时，状态与真实执行并不同步。 |
| E-11 | 25-33 | ✅ | 🟢 中低 | MQTT `loop_start()` 到 `on_connect` 订阅完成前，可能收到残留 QoS 1 消息，此时 `_reporter.publish()` 在未连接状态调用，返回错误码但被忽略。 |

---

## 4. 边侧 — `runtime/task/reporter.py`

**模块**: Edge / MQTT 状态上报

| # | 行号 | 验证 | 严重度 | 问题 |
|---|------|------|--------|------|
| E-12 | 56 | ✅ | 🟡 高危 | `_mqtt.publish()` 返回值被丢弃，MQTT 未连接/排队失败/broker 拒绝时在业务层无感知。ACK（QoS 1）丢失会导致云端误判任务未送达。 |

---

## 5. 边侧 — `runtime/main.py`

**模块**: Edge / Daemon 参数注入

| # | 行号 | 验证 | 严重度 | 问题 |
|---|------|------|--------|------|
| E-13 | 644-695 | ✏️ | 🟡 高危 | 原 E-23 改写。daemon 主循环串行处理命令，不存在 stop 中断 start 的并发。**真正问题是 control buffer 只有"最新值"语义而非命令队列** — 若写入方连续覆盖命令（如 start→cancel→start），daemon 只看到最后一个值，中间命令丢失。 |
| E-14 | 313 | ✅ | 🟡 高危 | `_apply_node_params` 使用浅合并 `dict.update()`，嵌套参数会整层覆盖而非深度合并。 |
| E-15 | 304-316 | ✅ | 🟡 高危 | 若 `NodeInstance.params` 属性缺失（类型不匹配），`_apply_node_params` 抛 `AttributeError`。异常在 daemon 循环中被静默捕获，参数注入失败但数据流照常启动。 |
| E-16 | 650 | ✅ | 🟢 中低 | `timestamp` 去重使用 `<=`，时钟精度低时相同时间戳的命令被静默丢弃。 |

---

## 6. 云端 — `cloud/server/services/mqtt_client.py`

**模块**: Cloud / MQTT 回调处理

| # | 行号 | 验证 | 严重度 | 问题 |
|---|------|------|--------|------|
| C-01 | 157-165 | ✅ | 🔴 严重 | **步骤自动推进缺失** — 收到 `task_status` 后只更新 `EdgeTask`，没有任何逻辑在一个 step 全部完成后推进 `JobStep` 或调用 `Dispatcher.dispatch_next_step()`。代码库中 `dispatch_next_step()` 只有定义，零调用点。任务链在第一步完成后永久卡住。 |
| C-02 | 124-137 | ⚠️ | 🟡 高危 | 原 C-02 改写。auto-discover 插入缺少幂等保护（如 `INSERT OR IGNORE`）。paho 同进程内单线程回调不会触发并发，但多 worker 部署或外部重复消息场景下可能触发 `IntegrityError`。 |
| C-03 | 76-203 | ✅ | 🟡 高危 | SQLite `check_same_thread=False` + MQTT 网络线程 / FastAPI 请求线程 / 心跳监控线程均可写数据库。无统一串行化策略，存在 `database is locked` 风险。 |
| C-04 | 150-179 | ✅ | 🟢 中低 | 收到未知 `edge_task_id` 的状态更新 → 静默丢弃无日志。 |
| C-05 | 181-203 | ✅ | 🟢 中低 | 收到未知 `dispatch_id` 的 ACK → 静默丢弃无日志。 |
| C-06 | 187-190 | ✅ | 🟢 中低 | 重试产生新 `dispatch_id` 后，旧 dispatch ACK 到达匹配不到任何 EdgeTask，静默丢失。 |

---

## 7. 云端 — `cloud/server/services/dispatcher.py`

**模块**: Cloud / 下发引擎

| # | 行号 | 验证 | 严重度 | 问题 |
|---|------|------|--------|------|
| C-07 | 36-47,97-99 | ✅ | 🟡 高危 | step 在分配任务前先写成 `running`。若所有 split 都没有 `assigned_to`，循环里只 `continue`，最后 job 仍被设为 `running`，但下发数为 0 — 零任务下发的死状态。 |
| C-08 | 201-210 | ✅ | 🟡 高危 | `_dependencies_met()` 只检查单个 `depends_on` 指向的 step 是否 `completed`，无拓扑检测/环检测/非法依赖校验。循环依赖导致作业永久卡死。 |
| C-09 | 220 | ✅ | 🟡 高危 | 重试次数 off-by-one：`attempt` 默认=1，retry 先 `+=1` 再判 `> MAX_RETRIES(3)`，实际只能重试 2 次。 |
| C-10 | 264 | ✅ | 🟡 高危 | `cancel_job()` 先发 MQTT cancel 再改 DB 状态。若 `publish_cancel()` 抛异常，后续 `db.commit()` 不执行，所有 task/step 取消操作全部丢失。 |
| C-11 | 170-199 | ✅ | 🟢 中低 | `machine_assignments` 缺条目时部分 split 无 `assigned_to`，被静默跳过。 |

---

## 8. 云端 — `cloud/server/services/splitter.py`

**模块**: Cloud / 地块分割

| # | 行号 | 验证 | 严重度 | 问题 |
|---|------|------|--------|------|
| C-12 | 137-157 | ✅ | 🟡 高危 | `_clip_strip` 交叉结果为 `MultiPolygon` 时直接返回，下游 `_to_geojson` 虽可处理 MultiPolygon，但 `fitBounds` 等处按 `Polygon` 坐标结构解析会出错。 |

---

## 9. 云端 — `cloud/server/services/sse_broker.py`

**模块**: Cloud / SSE 事件推送

| # | 行号 | 验证 | 严重度 | 问题 |
|---|------|------|--------|------|
| C-13 | 9-31 | ✅ | 🔴 严重 | `_queues` 在 `publish()`（MQTT 线程）中遍历，`subscribe()` 的 `finally` 中 `remove(queue)`（asyncio 主线程），无锁保护，存在 `list changed during iteration` 崩溃风险。 |

---

## 10. 云端 — `cloud/server/routers/events.py`

**模块**: Cloud / SSE 端点

| # | 行号 | 验证 | 严重度 | 问题 |
|---|------|------|--------|------|
| C-14 | 9-31 | ✅ | 🟡 高危 | SSE 输出仅在收到业务消息时 `yield`，无注释行/心跳帧/keepalive 机制。代理/浏览器可能在 60s 空闲后断开。 |

---

## 11. 云端 — `cloud/server/routers/files.py`

**模块**: Cloud / 文件下载

| # | 行号 | 验证 | 严重度 | 问题 |
|---|------|------|--------|------|
| C-15 | 35-41 | ✅ | 🟡 高危 | 路径下载端点当前固定返回占位 payload `{path: [], status: "pending"}`，无真实路径生成/存储/读取逻辑。 |

---

## 12. 前端 — `cloud/web/src/services/api.ts`

**模块**: Frontend / HTTP 封装

| # | 行号 | 验证 | 严重度 | 问题 |
|---|------|------|--------|------|
| F-01 | 28-30 | ✅ | 🔴 严重 | `del()` 直接调用 `fetch()`，完全不检查 `res.ok`。后端删除失败（404/500）时前端乐观移除本地数据，UI 假成功。 |
| F-02 | 8-10 | ✅ | 🟡 高危 | 非 JSON 错误响应 → `res.json()` 抛异常 → catch 提供 `{detail: res.statusText}`（可能为空），错误信息无意义。 |
| F-03 | 12-13 | ✅ | 🟡 高危 | 成功响应统一 `await res.json()`，对 204 或空 body 无兼容处理。 |

---

## 13. 前端 — `cloud/web/src/stores/machineStore.ts`

**模块**: Frontend / 机器状态

| # | 行号 | 验证 | 严重度 | 问题 |
|---|------|------|--------|------|
| F-04 | 21-29 | ✏️ | 🟢 中低 | 原 F-06 改写。`stopPolling()` 确实在 `App.vue` 卸载时调用，不会"永不清理"。但轮询是应用级常驻行为（非页面级），若应用壳长期不卸载则一直运行。 |

---

## 14. 前端 — `cloud/web/src/stores/jobStore.ts`

**模块**: Frontend / 作业状态

| # | 行号 | 验证 | 严重度 | 问题 |
|---|------|------|--------|------|
| F-05 | 47-53 | ✅ | 🟡 高危 | `currentJob` 未加载时 `updateTaskProgress()` 直接无操作。SSE `task_status` 事件先于 `fetchJobDetail` 完成到达 → 增量进度更新丢失。 |

---

## 15. 前端 — `cloud/web/src/views/JobCreateView.vue`

**模块**: Frontend / 作业创建向导

| # | 行号 | 验证 | 严重度 | 问题 |
|---|------|------|--------|------|
| F-06 | 110-123 | ✅ | 🟡 高危 | 表单状态全部保存在组件内 `reactive` 对象，无本地持久化，无路由离开守卫。导航离开后所有输入丢失。 |
| F-07 | 115-123 | ✅ | 🟡 高危 | `splitCount` 改变后，`machineAssignments` 没有同步清理。提交时直接把残留 key 发送给后端。 |

---

## 16. 前端 — `cloud/web/src/views/JobDetailView.vue`

**模块**: Frontend / 作业详情页

| # | 行号 | 验证 | 严重度 | 问题 |
|---|------|------|--------|------|
| F-08 | 77-97 | ✅ | 🔴 严重 | 页面初始化时创建轮询定时器，`handleDispatch()` 中也无条件新建定时器。**创建前没有先清理旧定时器**，多次触发导致多个轮询并行运行。 |

---

## 17. 前端 — `cloud/web/src/views/MachineDashboard.vue`

**模块**: Frontend / 机器监控页

| # | 行号 | 验证 | 严重度 | 问题 |
|---|------|------|--------|------|
| F-09 | 34-36 | ✅ | 🟡 高危 | `handleConfirm()` 没有 `try/catch`，API 失败会向上传播成未处理 Promise rejection。 |

---

## 18. 前端 — `cloud/web/src/components/map/ParcelLayer.vue`

**模块**: Frontend / 地块图层

| # | 行号 | 验证 | 严重度 | 问题 |
|---|------|------|--------|------|
| F-10 | 41-58 | ✅ | 🟡 高危 | `L.geoJSON()` 调用没有 try/catch 保护。若某一块数据损坏抛异常，中断整个 `renderParcels()`，所有地块渲染崩溃。 |

---

## 19. 前端 — `cloud/web/src/components/map/SplitPreview.vue`

**模块**: Frontend / 分割预览

| # | 行号 | 验证 | 严重度 | 问题 |
|---|------|------|--------|------|
| F-11 | 47-60 | ✅ | 🟡 高危 | `fitBounds` 采集坐标时按 `Polygon` 的 `coordinates[0]` 结构解析。若 `geometry.type === MultiPolygon`，坐标层级不同导致处理错误。 |

---

## 20. 前端 — `cloud/web/src/services/statusStream.ts`

**模块**: Frontend / SSE 客户端

| # | 行号 | 验证 | 严重度 | 问题 |
|---|------|------|--------|------|
| F-12 | 29-45 | ✏️ | 🟢 中低 | SSE 包装代码缺少可控重连策略、退避机制和用户侧错误提示。原生 `EventSource` 有浏览器级自动重连，但连接失败时前端无感知且无降级通知。 |

---

## 21. 集成测试 — `tests/e2e_cli.py`

**模块**: E2E / 测试工具

| # | 行号 | 验证 | 严重度 | 问题 |
|---|------|------|--------|------|
| T-01 | 269 | ✅ | 🟡 高危 | `start` 完成 agent 启动后只 sleep 2 秒，无订阅完成确认或握手检查。agent 订阅前下发的 MQTT 消息丢失。 |
| T-02 | 91-106 | ✅ | 🟡 高危 | `_stop()` 仅凭 PID 文件中的数字发信号，不校验进程命令行/启动时间/所属程序。PID 被系统复用时可能误杀无关进程。 |
| T-03 | 84 | ✅ | 🟡 高危 | `os.kill(pid, 0)` 对僵尸进程返回成功，`_is_running` 误判服务"运行中"跳过启动。 |

---

## 交叉验证结论

### 移除的条目（3 项）

| 原编号 | 原因 |
|--------|------|
| E-09 | `threading.Event.clear()` 不会唤醒等待线程，与 Python 事件语义不符 |
| C-03 | ORM 事务未提交时失败属正常行为，不是本实现独有缺陷 |
| F-13 | 当前路由无 `<keep-alive>` 包裹，该风险在当前代码中不存在 |

### 改写的条目（5 项）

| 原编号 | 修正后编号 | 改动 |
|--------|-----------|------|
| E-05 | E-03 | 状态描述修正：execute() 失败时 task 停在 READY，不会到 RUNNING |
| E-10 | E-06 | 同上，明确 RUNNING 状态不会在异常后发送 |
| E-23 | E-13 | 从"并发中断"改正确认为"buffer 覆盖丢命令" |
| C-02 | C-02 | 标注需前提：同进程单线程回调不会触发，多实例部署才存在 |
| F-06 | F-04 | 修正"永不清理"表述为"应用级常驻行为，不是页面级" |

### 最终统计

| 严重度 | 边侧 | 云端 | 前端 | 测试 | 合计 |
|--------|------|------|------|------|------|
| 🔴 严重 | 2 | 2 | 2 | 0 | **6** |
| 🟡 高危 | 7 | 7 | 7 | 3 | **24** |
| 🟢 中低 | 3 | 2 | 2 | 0 | **7** |
| **合计** | **12** | **11** | **11** | **3** | **37** |

（原 59 项 → 移除 3 项 → 合并简并 → 最终 37 项）

### GPT 建议的修复顺序

**第一轮（闭环缺失 + 假状态）**: C-01 → E-03 → E-06 → E-10 → F-01 → F-08

**第二轮（并发 + 一致性）**: C-13 → C-03 → E-02 → T-02

**第三轮（鲁棒性 + 体验）**: F-02 → F-03 → F-05 → F-07 → F-10 → F-11 → C-14
