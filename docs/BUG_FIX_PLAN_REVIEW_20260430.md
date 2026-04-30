# NodeFlow Bug 修复计划审阅意见

> 审阅日期: 2026-04-30
> 审阅对象: `docs/BUG_FIX_PLAN.md`
> 审阅目标: 检查修复方案是否可能引入新的并发、状态一致性或维护性问题

---

## 总体结论

`docs/BUG_FIX_PLAN.md` 的修复方向总体是对的，优先级排序也基本合理。

但当前方案里有几处“修法本身会制造新问题”的高风险点，尤其集中在:

- 用错误的并发模型修并发问题
- 用更假的状态去替代原本的假状态
- 在 MQTT 回调线程里引入阻塞等待
- 将内存状态与磁盘状态拆开后没有解决写入乱序

如果不先修正这些方案细节，确实存在“越修 bug 越多”的风险。

---

## 高风险问题

### 1. FIX-09 会引入磁盘状态回退

**结论**: 当前方案不建议直接实施。

`FIX-09` 提议把 `TaskStore` 改成“锁内更新内存，锁外写磁盘快照”。这个思路能减少锁内 I/O，但会引入一个新的写入乱序问题:

1. 线程 A 更新状态，生成旧快照 `snapshot_A`
2. 线程 B 紧接着更新状态，生成新快照 `snapshot_B`
3. 线程 B 先写盘成功
4. 线程 A 后写盘，把旧快照覆盖回去

这样会导致:

- 内存中的 `_tasks` 是新状态
- 磁盘上的 `tasks.json` 却回退成旧状态

这属于典型的持久化一致性 bug，比当前“锁内 I/O 阻塞”更危险，因为它会悄悄写出错误数据。

建议改法:

- 保持“单写者”语义，不要允许多个线程并行写盘
- 可选方案一: 继续在锁内写盘，先接受简单正确
- 可选方案二: 引入专用写线程 + 最新版本号/队列
- 可选方案三: 先复制数据，再在同一写锁下串行落盘，而不是完全锁外写盘

关联原文件:

- `runtime/task/store.py`

---

### 2. FIX-07 没有真正解决 SSE 跨线程问题

**结论**: 当前方案不够安全，不能只加 `threading.Lock`。

`FIX-07` 想用 `threading.Lock` 保护 `SSEBroker._queues`，这只能解决“列表遍历和删除”的并发问题，但没有解决更核心的问题:

- `publish()` 在 MQTT 线程调用
- `asyncio.Queue` 属于 asyncio 事件循环上下文
- 从别的线程直接调用 `queue.put_nowait()` 并不是可靠的跨线程投递方式

也就是说，给 `_queues` 加锁后，`list.remove()` 的崩溃风险下降了，但“跨线程直接操作 `asyncio.Queue`”这个模型问题还在。

建议改法:

- 订阅时同时记录 `queue` 所属的 event loop
- `publish()` 中用 `loop.call_soon_threadsafe(queue.put_nowait, item)` 投递
- 或改成线程安全桥接结构，再由 asyncio 侧转发

更稳妥的数据结构是:

- `self._subscribers: list[tuple[asyncio.AbstractEventLoop, asyncio.Queue]]`

关联原文件:

- `cloud/server/services/sse_broker.py`
- `cloud/server/services/mqtt_client.py`

---

### 3. FIX-04 的示例代码会把首个 `RUNNING` 延迟到约 62 秒

**结论**: 方案描述方向可以讨论，但给出的实现示例有明显逻辑错误。

计划里给的 `_monitor_loop()` 伪代码是:

```python
while not self._monitor_stop.wait(60):
    if first_report:
        time.sleep(2)
        self._reporter.send_status(task.task_id, TaskState.RUNNING)
```

这段代码的实际行为不是“2 秒后发 RUNNING”，而是:

- 先 `wait(60)`
- 60 秒后循环体才第一次执行
- 然后再 `sleep(2)`

结果是首个 `RUNNING` 大约在 62 秒后才发送。

这会制造新问题:

- 云端长时间看不到任务启动
- 任务其实已开始，但 UI 仍停留在 `READY`
- 可能触发误判、重试或操作员二次下发

建议改法:

- 不要把“首次 RUNNING 确认”绑在 60 秒轮询上
- 单独做一个短周期确认逻辑，例如 200ms 到 500ms 的有限重试
- 如果暂时没有真实运行信号，宁可延后设计，也不要再造一层时间猜测

关联原文件:

- `runtime/task/executor.py`
- `runtime/task/agent.py`

---

### 4. FIX-02 在 MQTT 回调线程里等待 10 秒，可能阻塞整个 MQTT 客户端

**结论**: 当前修法风险偏高。

`FIX-02` 建议在 `TaskExecutor.execute()` 中循环等待 control buffer 最多 10 秒。问题在于当前调用链是:

- MQTT 收到消息
- `TaskAgent._on_message()`
- `_handle_dispatch()`
- `executor.execute()`

也就是说，这个“最多等 10 秒”的逻辑很可能运行在 paho 的网络回调线程里。

风险:

- 阻塞后续 MQTT 消息处理
- 延迟 ACK、状态上报或重连相关回调
- 当多台设备或短时间连续下发时，边侧 agent 会表现出明显卡顿

建议改法:

- 不要在 MQTT 回调线程里长时间 sleep/retry
- 更稳妥的方案是“快速失败 + 明确 FAILED 状态”
- 如果必须等待 buffer，就把执行逻辑投递到工作线程，不要阻塞 MQTT 回调线程

关联原文件:

- `runtime/task/agent.py`
- `runtime/task/executor.py`

---

### 5. FIX-03 的异常恢复不完整，会留下本地状态和心跳假忙碌

**结论**: 当前方案只修了一半。

`FIX-03` 在 `_handle_dispatch()` 里包裹 `execute()` 的 `try/except`，失败时只发送:

- `send_status(FAILED)`

但这还不够，因为 `execute()` 在异常前已经可能做过这些事:

- 设置 `self._current_task_id`
- 本地 store 写成 `READY`

如果只上报 FAILED，而不清理本地执行器状态，会出现:

- 心跳继续报 `busy`
- store 中任务仍停在 `READY`
- 云端与边侧本地状态不一致

建议改法:

- 异常路径中调用统一的失败收敛逻辑
- 至少要同时完成:
  - `store.update_state(..., FAILED)`
  - 清空 `_current_task_id`
  - 记录错误详情

更好的接口是让 `TaskExecutor` 自己提供可靠的 `mark_failed()` 收口，而不是在 agent 外层只发一条状态消息。

关联原文件:

- `runtime/task/agent.py`
- `runtime/task/executor.py`

---

### 6. FIX-14 用“估算进度”替代“未知进度”，容易把系统带偏

**结论**: 当前方案不建议上线。

`FIX-14` 提议根据:

- control buffer 的 sequence
- `started_at`
- 假设 1 小时作业时长

来推导 `progress_pct`。

这个方案的主要问题不是“不够准”，而是“会稳定地产生误导”:

- sequence 只表示 buffer 被写过，不表示作业真的在推进
- 按时间线性增长会让卡死任务看起来也在接近完成
- 任务失败前可能已经显示 80% 到 99%

这比“进度未知”更危险，因为它会误导操作员和自动化逻辑。

建议改法:

- 在拿不到真实进度前，显式上报“未知”比伪进度更安全
- 可以先只改 `current_node` 或增加 `progress_available=false`
- 真实进度应来自 daemon/monitor 的可验证运行状态，而不是时间估算

关联原文件:

- `runtime/task/executor.py`

---

## 中风险问题

### 7. FIX-01 需要补幂等保护，避免重复推进

`FIX-01` 的方向正确，但建议补两层保护:

- 只在 step 当前状态不是 `completed` 时才推进
- 只在“最后一个 task 刚完成”的边界点推进一次

否则一旦边侧重复发送 `completed`，或者云端收到重复状态消息，就可能重复触发下一步分发逻辑。

额外建议:

- 当前 step 的完成提交和下一步 dispatch 最好分成明确的状态流转
- 至少要保证“重复 completed 消息不会产生重复下发”

关联原文件:

- `cloud/server/services/mqtt_client.py`
- `cloud/server/services/dispatcher.py`

---

### 8. FIX-08 只能缓解 SQLite 锁冲突，不能从根上解决并发写

`FIX-08` 增加 SQLite `timeout` 和 WAL 模式是合理的，但它属于“减轻症状”，不是“彻底修复”。

这不会直接制造新 bug，但要避免过度承诺:

- WAL 不等于没有锁冲突
- timeout 不等于写入串行化
- 多线程高频写场景下，仍可能出现提交竞争

建议把该项的目标表述成:

- “降低 `database is locked` 概率”

而不是:

- “修复并发写问题”

关联原文件:

- `cloud/server/database.py`
- `cloud/server/app.py`

---

### 9. FIX-10 引入 `psutil` 依赖不够克制

`FIX-10` 的目标合理，但计划里的示例直接引入 `psutil`，会带来额外依赖管理成本。

在当前项目里，这个修复只用于测试工具，建议优先选择:

- `ps -p <pid> -o command=`
- 或现有 `subprocess`/`os` 能完成的最小方案

除非项目本来就准备增加 `psutil`，否则为了一个测试脚本引入新依赖，收益不高。

关联原文件:

- `tests/e2e_cli.py`

---

## 计划文档本身的问题

### 10. 多处 bug 编号映射错误，容易导致修错目标

`BUG_FIX_PLAN.md` 里存在多处“FIX 标题后的 bug 编号”和原报告不一致的情况，例如:

- `FIX-02` 写成 `E-03`，实际对应更接近 `E-05`
- `FIX-03` 写成 `E-06`，实际对应更接近 `E-10`
- `FIX-04` 写成 `E-10`，实际对应更接近 `E-15`
- `FIX-06` 写成 `F-08`，实际对应更接近 `F-12`
- `FIX-07` 写成 `C-13`，实际对应更接近 `C-15`
- `FIX-08` 写成 `C-03`，实际对应更接近 `C-04`
- `FIX-10` 写成 `T-02`，实际对应更接近 `T-03`
- `FIX-11` 写成 `E-07`，实际对应更接近 `E-12`
- `FIX-12` 写成 `E-09`，实际对应更接近 `E-14`
- `FIX-14` 写成 `E-04`，实际对应更接近 `E-06`

这类编号漂移本身不会改坏代码，但会显著增加实施阶段的沟通成本和误修风险。

建议先统一编号，再进入开发。

---

## 建议的调整顺序

建议保留并优先落地:

- `FIX-01`，但补幂等保护
- `FIX-05`
- `FIX-06`
- `FIX-11`
- `FIX-12`
- `FIX-13`

建议改写后再落地:

- `FIX-02`
- `FIX-03`
- `FIX-04`
- `FIX-07`
- `FIX-08`
- `FIX-10`

建议暂缓，不要按当前写法直接做:

- `FIX-09`
- `FIX-14`

---

## 一句话结论

这份修复计划可以作为施工草案，但还不能直接照着改。

最需要先修的是方案设计本身，而不是代码实现细节，尤其是:

- `FIX-09` 的锁外写盘
- `FIX-07` 的跨线程 SSE 投递
- `FIX-04` 的 62 秒假延迟
- `FIX-02` 的 MQTT 回调阻塞
- `FIX-14` 的伪进度估算

把这几项先改对，后续实施才不容易把系统修得更脆。
