# NodeFlow Bug 报告代码核对结论

> 核对日期: 2026-04-30
> 依据文档: `docs/BUG_REPORT.md`
> 核对方式: 逐项对照当前代码实现，不参考历史版本

---

## 结论摘要

本次核对结果是: `docs/BUG_REPORT.md` 的主线判断总体正确，尤其多项红色问题和核心高危问题都有明确代码依据，可以作为修复工作的输入。

但该报告并非逐条都足够精确，部分条目存在以下情况:

- 问题本体成立，但触发过程或状态描述写得过于绝对
- 报告将“理论风险”写成了“当前代码下必然发生的现状问题”
- 少数条目与代码行为不符，需改写或降级

建议将原报告作为“问题线索清单”，不要直接把所有表述原样当作事实结论。

---

## 核对标准

本文件采用以下标签:

- `确认成立`: 报告描述与当前代码行为基本一致
- `部分成立`: 问题存在，但影响范围、触发条件或细节表述不准确
- `不成立`: 当前代码不足以支持该结论
- `需前提`: 只有在额外部署条件或运行前提下才成立

---

## 一、确认成立的问题

以下问题经代码核对后，结论基本成立。

### 1. 边侧

#### E-01 `runtime/task/store.py`

`确认成立`

- `_load()` 在读取 `tasks.json` 时，若单条任务反序列化抛出 `KeyError` 或 `JSONDecodeError`，会直接 `os.remove(path)` 删除整个存储文件
- 这会导致所有历史任务记录一并丢失，而不是只跳过损坏项

代码依据:

- `runtime/task/store.py:19-29`

#### E-02 `runtime/task/store.py`

`确认成立`

- `save()`、`update_state()`、`remove()` 都在持有 `self._lock` 时调用 `_save()`
- `_save()` 内部执行 `json.dump()` 和 `os.replace()`，属于真实磁盘 I/O
- 因此写入期间会阻塞其他线程对该 store 的访问

代码依据:

- `runtime/task/store.py:31-38`
- `runtime/task/store.py:60-83`

#### E-05 `runtime/task/executor.py`

`部分成立`

- `SharedBufferLite("runtime.control", create=False)` 若控制 buffer 尚未由 daemon 创建，的确会抛异常且未捕获
- 任务会先被写成 `READY`
- 但 `RUNNING` 只有在 buffer 打开和 `write()` 成功后才会更新，因此“已标记 READY/RUNNING”这个写法不准确，应拆开描述

更准确表述:

- “buffer 不存在或写入失败会导致 `execute()` 异常退出，任务可能停留在 `READY`，不会自动恢复”

代码依据:

- `runtime/task/executor.py:26-42`

#### E-06 `runtime/task/executor.py`

`确认成立`

- `_compute_progress()` 只构造默认 `TaskProgress`
- `progress_pct`、`nodes_healthy`、`nodes_total` 没有任何真实计算逻辑
- 仅尝试读 sequence，并将 `current_node` 伪装成 `seq:N`

代码依据:

- `runtime/task/executor.py:84-96`
- `runtime/task/models.py:89-114`

#### E-10 `runtime/task/agent.py`

`部分成立`

- `executor.execute()` 失败时，异常会被 `_on_message()` 总 catch
- 在此之前任务已经保存、ACK 已发、`DOWNLOADING` 和 `READY` 状态已发
- 但 `RUNNING` 状态不会在 `execute()` 抛异常后发送，因此原报告把状态写成 “ACK 已发、READY 状态已上报、任务卡死” 更准确

代码依据:

- `runtime/task/agent.py:62-75`
- `runtime/task/agent.py:77-108`

#### E-12 `runtime/task/agent.py`

`确认成立`

- 重复 `task_id` 时直接 `return`
- 不发送 ACK，也不返回拒绝原因
- 云端若按 ACK 超时重试，边侧会持续忽略

代码依据:

- `runtime/task/agent.py:82-84`

#### E-14 `runtime/task/agent.py`

`确认成立`

- 取消请求没有先校验任务是否存在
- `_executor.cancel()` 会直接尝试写 control buffer
- 随后 reporter 无条件上报 `CANCELLED`

代码依据:

- `runtime/task/agent.py:110-114`
- `runtime/task/executor.py:44-55`

#### E-15 `runtime/task/agent.py`

`确认成立`

- `RUNNING` 状态由 agent 在 `executor.execute()` 返回后立即上报
- daemon 真正读取 control buffer 发生在 `runtime.main` 的 0.5 秒轮询内
- 因此状态上报与真实执行开始并不同步

代码依据:

- `runtime/task/agent.py:103-108`
- `runtime/main.py:639-679`

#### E-16 `runtime/task/reporter.py`

`确认成立`

- `_mqtt.publish()` 返回值未检查
- 未连接、排队失败或 broker 拒绝时不会在业务层被感知

代码依据:

- `runtime/task/reporter.py:53-57`

### 2. 云端

#### C-01 `cloud/server/services/mqtt_client.py`

`确认成立`

- 收到 `task_status` 后，代码只更新 `EdgeTask`
- 没有任何逻辑在一个 step 全部完成后推进 `JobStep` 或调用 `Dispatcher.dispatch_next_step()`
- 且代码库中 `dispatch_next_step()` 只有定义，没有调用点

代码依据:

- `cloud/server/services/mqtt_client.py:150-178`
- `cloud/server/services/dispatcher.py:101-115`

#### C-04 `cloud/server/services/mqtt_client.py`

`确认成立`

- SQLite 使用 `check_same_thread=False`
- MQTT 网络线程、FastAPI 请求线程、心跳监控线程都可能访问数据库
- 当前代码没有统一串行化写入策略，确实存在 `database is locked` 风险

代码依据:

- `cloud/server/database.py:5-11`
- `cloud/server/services/mqtt_client.py`
- `cloud/server/services/heartbeat_monitor.py:31-67`

#### C-08 `cloud/server/services/dispatcher.py`

`确认成立`

- step 在分配任务前就先写成 `running`
- 若所有 split 都没有 `assigned_to`，循环里只会 `continue`
- 最后 job 仍会被写成 `running`，但实际下发数可能为 0

代码依据:

- `cloud/server/services/dispatcher.py:36-47`
- `cloud/server/services/dispatcher.py:97-99`

#### C-09 `cloud/server/services/dispatcher.py`

`确认成立`

- `_dependencies_met()` 只检查单个 `depends_on` 指向的 step 是否 `completed`
- 没有任何拓扑检测、环检测或非法依赖校验

代码依据:

- `cloud/server/services/dispatcher.py:201-210`

#### C-10 `cloud/server/services/dispatcher.py`

`确认成立`

- `attempt` 默认值是 1
- retry 时先 `t.attempt += 1`
- 再判断 `> DISPATCH_MAX_RETRIES`
- 当 `DISPATCH_MAX_RETRIES = 3` 时，实际只允许再发两次

代码依据:

- `cloud/server/models/edge_task.py:31-35`
- `cloud/server/services/dispatcher.py:220-224`
- `cloud/server/config.py:15-18`

#### C-11 `cloud/server/services/dispatcher.py`

`确认成立`

- `cancel_job()` 里先发 MQTT cancel，再修改数据库状态
- 若 `publish_cancel()` 抛异常，后续任务状态更新和 `db.commit()` 都不会执行

代码依据:

- `cloud/server/services/dispatcher.py:258-274`

#### C-15 `cloud/server/services/sse_broker.py`

`确认成立`

- `_queues` 在 `publish()` 中遍历
- `subscribe()` 的 `finally` 中直接 `remove(queue)`
- broker 本身没有锁，也没有线程边界保护
- 当前架构下 `publish()` 可能在 MQTT 线程调用，而 `subscribe()` 运行在 asyncio 主线程

代码依据:

- `cloud/server/services/sse_broker.py:9-31`
- `cloud/server/services/mqtt_client.py:170-177`

#### C-20 `cloud/server/routers/files.py`

`确认成立`

- 路径下载接口当前固定返回占位 payload
- 没有任何真实路径生成、存储或读取逻辑

代码依据:

- `cloud/server/routers/files.py:28-43`

#### C-22 `cloud/server/routers/events.py`

`确认成立`

- SSE 输出仅在收到业务消息时 `yield`
- 没有注释行、心跳帧或 keepalive 机制

代码依据:

- `cloud/server/routers/events.py:13-31`

### 3. 前端

#### F-01 `cloud/web/src/services/api.ts`

`确认成立`

- `del()` 直接调用 `fetch()`
- 完全不检查 `res.ok`
- 因此后端删除失败时，调用方可能误以为成功

代码依据:

- `cloud/web/src/services/api.ts:28-30`

#### F-02 `cloud/web/src/services/api.ts`

`确认成立`

- 错误响应默认尝试 `res.json()`
- 非 JSON 时会退化成 `{ detail: res.statusText }`
- 异常信息可能较弱或为空

代码依据:

- `cloud/web/src/services/api.ts:8-10`

#### F-03 `cloud/web/src/services/api.ts`

`确认成立`

- 成功响应统一执行 `await res.json()`
- 对 204 或空 body 没有兼容处理

代码依据:

- `cloud/web/src/services/api.ts:12-13`

#### F-06 `cloud/web/src/stores/machineStore.ts`

`不按原文成立，但存在相关风险`

- store 自身实现里有 `stopPolling()`
- 且 `App.vue` 在卸载时会调用它
- 所以“永不清理”这个说法不准确
- 但由于轮询挂在应用级组件，确实会随整个 SPA 生命周期常驻

更准确表述:

- “轮询是应用级常驻行为，不是页面级行为；若未来应用壳长期不卸载，则会一直运行”

代码依据:

- `cloud/web/src/stores/machineStore.ts:21-29`
- `cloud/web/src/App.vue:39-48`

#### F-07 `cloud/web/src/stores/jobStore.ts`

`确认成立`

- `currentJob` 未加载时，`updateTaskProgress()` 直接无操作
- SSE 先到、详情后到时，增量状态会被丢弃

代码依据:

- `cloud/web/src/stores/jobStore.ts:46-54`
- `cloud/web/src/App.vue:29-31`

#### F-10 `cloud/web/src/views/JobCreateView.vue`

`确认成立`

- 表单状态全部保存在组件内 `reactive` 对象
- 没有本地持久化，也没有离开守卫

代码依据:

- `cloud/web/src/views/JobCreateView.vue:110-123`

#### F-11 `cloud/web/src/views/JobCreateView.vue`

`确认成立`

- `splitCount` 改变后，没有同步清理 `machineAssignments`
- 提交时直接把整个对象发给后端

代码依据:

- `cloud/web/src/views/JobCreateView.vue:115-123`
- `cloud/web/src/views/JobCreateView.vue:152-166`

#### F-12 `cloud/web/src/views/JobDetailView.vue`

`确认成立`

- 页面初始运行中会创建一个轮询定时器
- `handleDispatch()` 中若再次触发，也会无条件新建一个定时器
- 创建前没有先清理旧定时器

代码依据:

- `cloud/web/src/views/JobDetailView.vue:77-83`
- `cloud/web/src/views/JobDetailView.vue:90-97`

#### F-15 `cloud/web/src/views/MachineDashboard.vue`

`确认成立`

- `handleConfirm()` 没有 `try/catch`
- API 失败会向上传播成未处理 Promise

代码依据:

- `cloud/web/src/views/MachineDashboard.vue:34-36`

#### F-18 `cloud/web/src/components/map/ParcelLayer.vue`

`确认成立`

- `L.geoJSON()` 调用没有保护
- 若某一块数据损坏抛异常，会中断整个 `renderParcels()`

代码依据:

- `cloud/web/src/components/map/ParcelLayer.vue:41-58`

#### F-20 `cloud/web/src/components/map/SplitPreview.vue`

`确认成立`

- `fitBounds` 采集坐标时按 `Polygon` 的 `coordinates[0]` 结构处理
- 若 `geometry.type === MultiPolygon`，坐标层级不同，这里会错

代码依据:

- `cloud/web/src/components/map/SplitPreview.vue:47-60`

### 4. 测试工具

#### T-02 `tests/e2e_cli.py`

`确认成立`

- `start` 完成 agent 启动后只 sleep 2 秒
- 没有任何订阅完成确认或握手检查

代码依据:

- `tests/e2e_cli.py:188-205`

#### T-03 `tests/e2e_cli.py`

`确认成立`

- `_stop()` 仅凭 PID 文件中的数字发信号
- 不校验进程命令行、启动时间或所属程序
- PID 被系统复用时可能误杀无关进程

代码依据:

- `tests/e2e_cli.py:91-106`

---

## 二、需要改写或降级的问题

以下条目不是“完全错误”，但原报告表述不够准确，建议修订。

### E-09 `runtime/task/executor.py`

`不成立`

原报告称:

- `_monitor_stop.clear()` 会让第一次 `execute()` 的监控线程 `wait()` 被意外唤醒

问题:

- `threading.Event.clear()` 的语义是把事件重置为未置位状态
- 它不会唤醒正在 `wait()` 的线程
- 因此该条与 Python 事件语义不符

更接近真实的问题:

- 若旧监控线程没有在 `_stop_monitor()` 的 2 秒 join 内结束，后续新的监控线程可以被启动，从而形成残留线程风险

代码依据:

- `runtime/task/executor.py:57-73`

### E-23 `runtime/main.py`

`部分成立`

原报告称:

- `start_dataflow` 阻塞期间，`stop_dataflow` 可以被立即处理，导致状态不一致

问题:

- daemon 主循环是串行处理控制命令的
- `start_dataflow()` 在当前线程同步执行期间，不会并发进入下一次 `read()`
- 因此“stop 在 start 完成前立即处理”不符合当前代码执行模型

真实问题更可能是:

- control buffer 只有“最新值”语义，不是命令队列
- 如果写入方连续覆盖命令，daemon 只能在下一轮读取到最后一个可见值
- 命令存在覆盖、丢失、延迟处理和不可排队的问题

代码依据:

- `runtime/main.py:643-679`
- `sdk/shared_buffer_lite.py:93-167`

### C-02 `cloud/server/services/mqtt_client.py`

`需前提`

原报告称:

- 并发两条心跳 auto-discover 会导致重复主键错误

问题:

- 仅从当前单进程代码看，paho 回调由同一网络线程驱动，不能直接推出“同进程并发两条心跳同时插入”
- 若存在多实例部署、多 worker 或外部重复消费，则该风险成立

更准确表述:

- “auto-discover 缺少幂等插入保护；在多实例或竞争写入场景下可能触发重复插入错误”

代码依据:

- `cloud/server/services/mqtt_client.py:107-138`
- `cloud/server/app.py:21-31`

### C-03 `cloud/server/services/mqtt_client.py`

`不建议单列为 bug`

原报告称:

- `db.add()` 与 `db.commit()` 之间若失败，机器丢失

问题:

- 这是事务尚未提交前的正常行为，不是本实现独有缺陷
- 任何 ORM 写路径在 commit 前失败都会表现为数据不落库

更准确表述:

- “缺少针对 commit 失败的异常处理、补偿日志和重试策略”

代码依据:

- `cloud/server/services/mqtt_client.py:124-138`

### F-04 `cloud/web/src/services/statusStream.ts`

`部分成立`

原报告称:

- 404 后 `EventSource` 永久断开不重试

问题:

- 仅从当前包装代码不能直接证明“永久不重试”，因为原生 `EventSource` 有浏览器级自动重连语义
- 但代码确实没有提供明确的错误展示、退避策略或状态机控制

更准确表述:

- “SSE 客户端缺少可控重连与错误提示机制；连接失败时用户侧感知弱”

代码依据:

- `cloud/web/src/services/statusStream.ts:29-45`

### F-13 `cloud/web/src/views/JobDetailView.vue`

`不成立`

原报告称:

- 组件在 `<keep-alive>` 中时 `onUnmounted` 不触发

问题:

- 当前路由配置中没有看到 `<keep-alive>` 包裹 `JobDetailView`
- 该条属于“未来如果接入 keep-alive 可能出问题”的潜在风险，不应作为当前 bug 记载

代码依据:

- `cloud/web/src/views/JobDetailView.vue:86-88`
- `cloud/web/src/router/index.ts:1-39`

---

## 三、报告中值得保留的主线判断

即使部分细节需要修正，以下主线结论仍然值得保留:

- 边侧任务下发链路对 control buffer 的存在性和写入成功缺少可靠兜底
- 云端任务编排缺少完整的步骤推进闭环
- 前端对删除、重试、轮询和异常渲染的鲁棒性不足
- SSE 与数据库写路径均存在并发模型层面的风险
- E2E 工具对“进程存活”和“订阅完成”的判断过于粗糙

---

## 四、建议的报告修订方式

建议将原 `BUG_REPORT.md` 分成两层信息:

### A. 保持原优先级的问题

建议保留:

- `E-01`
- `E-05`
- `E-06`
- `E-10`
- `E-12`
- `E-14`
- `E-15`
- `E-16`
- `C-01`
- `C-04`
- `C-08`
- `C-09`
- `C-10`
- `C-11`
- `C-15`
- `C-20`
- `C-22`
- `F-01`
- `F-02`
- `F-03`
- `F-07`
- `F-10`
- `F-11`
- `F-12`
- `F-15`
- `F-18`
- `F-20`
- `T-02`
- `T-03`

### B. 需要改写的条目

建议改写:

- `E-05` 的状态描述
- `E-10` 的失败后状态描述
- `E-23` 的并发机理描述
- `C-02` 的触发前提
- `F-04` 的“永久断开”结论

### C. 建议移除或降为备注

建议移除或降级:

- `E-09`
- `C-03`
- `F-13`

---

## 五、后续建议

如果后续继续推进修复，建议按以下顺序处理:

1. 先修闭环缺失和假状态问题
   - `C-01`
   - `E-05`
   - `E-10`
   - `E-15`
   - `F-01`
   - `F-12`

2. 再修并发和一致性问题
   - `C-15`
   - `C-04`
   - `E-02`
   - `T-03`

3. 最后修鲁棒性和体验问题
   - `F-02`
   - `F-03`
   - `F-07`
   - `F-11`
   - `F-18`
   - `F-20`
   - `C-22`

---

## 附: 本次核对涉及的主要文件

- `runtime/task/store.py`
- `runtime/task/executor.py`
- `runtime/task/agent.py`
- `runtime/task/reporter.py`
- `runtime/task/config.py`
- `runtime/task/agent_main.py`
- `runtime/main.py`
- `sdk/shared_buffer_lite.py`
- `cloud/server/services/mqtt_client.py`
- `cloud/server/services/dispatcher.py`
- `cloud/server/services/sse_broker.py`
- `cloud/server/services/heartbeat_monitor.py`
- `cloud/server/routers/files.py`
- `cloud/server/routers/events.py`
- `cloud/server/routers/machines.py`
- `cloud/server/routers/parcels.py`
- `cloud/server/database.py`
- `cloud/web/src/App.vue`
- `cloud/web/src/services/api.ts`
- `cloud/web/src/services/statusStream.ts`
- `cloud/web/src/stores/machineStore.ts`
- `cloud/web/src/stores/jobStore.ts`
- `cloud/web/src/views/JobCreateView.vue`
- `cloud/web/src/views/JobDetailView.vue`
- `cloud/web/src/views/MachineDashboard.vue`
- `cloud/web/src/components/map/ParcelLayer.vue`
- `cloud/web/src/components/map/SplitPreview.vue`
- `cloud/web/src/router/index.ts`
- `tests/e2e_cli.py`
