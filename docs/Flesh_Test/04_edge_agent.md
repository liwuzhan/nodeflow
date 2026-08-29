# 模块审阅报告：edge/agent（端侧任务代理）

> 审阅日期: 2026-08-03 | 审阅方式: 代码审阅 + 关键点脚本验证 | 存放: docs/Flesh_Test/（临时）

## 1. 模块职责

端侧任务执行代理：MQTT 订阅云端任务下发/取消 → 任务资产下载（GeoJSON parcel、云端规划路径）→ TaskExecutor 与 Runtime daemon 交互 → 状态/ACK/心跳上报。

| 文件 | 行数 | 职责 |
|---|---|---|
| `agent.py` | 247 | TaskAgent 主类：MQTT 连接/订阅、dispatch/cancel 处理、QoS1 幂等去重、心跳定时器、延迟 RUNNING 上报 |
| `executor.py` | 264 | TaskExecutor：写 `runtime.control` 与 daemon 交互、监控线程（进度/失败/完成判定）、取消 |
| `assets.py` | 181 | 任务资产下载/校验（checksum）/落盘 |
| `models.py` | 150 | Task/TaskProgress dataclass（复用 contracts.task 枚举） |
| `store.py` | 83 | JSON 文件持久化 + 线程锁 |
| `reporter.py` | 59 | MQTT 状态/ACK/心跳发布 |
| `agent_main.py` / `config.py` | 44/15 | 独立进程入口 / 环境变量 |

**合计 8 个有效文件，1,048 行。**

## 2. 核心流程

- **下发链路**: MQTT dispatch → machine_id/protocol_version 校验 → task_id 幂等去重 → busy 检查 → 构造 Task(PENDING) 落 store → 发 ACK → DOWNLOADING → assets.prepare（下载+checksum）→ READY → executor.execute（写 control buffer `{command: start_dataflow, ...}`）→ RUNNING → 监控线程判定完成/失败。
- **状态上报**: `nodeflow/{machine_id}/status|task/ack|heartbeat`，heartbeat QoS0、其余 QoS1。
- **完成判定**: `_is_safely_completed` 连续 3 次：next_point.final + pose 距离 ≤1.5m + 速度 ≤0.05 + 农具 transport/PTO off → stop_dataflow → mark_completed。

## 3. 发现的问题

### P1（高）

| # | 位置 | 问题 |
|---|---|---|
| P1-1 | `agent.py:82-95,162-180` + `assets.py:62,102` | **MQTT 网络线程被长下载阻塞 → 断连丢任务**：path 工件下载超时 300s 在 paho loop 线程内同步执行；keepalive=60s 必然超时断连；clean_session=True 下未 ACK 的 QoS1 消息不重投 → 任务静默丢失。 |
| P1-2 | `agent.py:122-127` + `store.py:44-50` | **崩溃恢复缺失**：agent 重启后 store 遗留 RUNNING/READY 任务 → `get_active()` 非空 → 新任务全部 machine_busy 拒绝；而心跳报 online，云边状态不一致。 |
| P1-3 | `executor.py:136-143,255-264` + `agent.py:220-231` | **取消/完成竞态可覆盖终态**：monitor 线程 join 仅 2s，超时后 monitor 仍可能 mark_completed/mark_failed 覆盖 CANCELLED，违反 contracts 终态不可转换。 |
| P1-4 | `executor.py:92-99` + `edge/runtime/main.py:678` | **runtime.control 1KB 上限 vs node_params**：payload 超 1016 字节 write 抛 ValueError，execute 只捕获 FileNotFoundError → 大 node_params 任务直接 FAILED。 |
| P1-5 | `agent.py:138-139` | **无效 payload 不 ACK**：非法 PlanningMode/FallbackPolicy 抛 ValueError 被 `_on_message` 吞掉 → 任务未保存、未发拒绝 ACK → 云端 QoS1 无限重投死循环。 |
| P1-6 | `store.py:19-29` | **TaskStore._load 可致 agent 启动崩溃 + 数据被删**：仅捕获 JSONDecodeError/KeyError；TaskState 非法值 ValueError、int(None) TypeError 未捕获；JSON 损坏时 os.remove 静默丢弃全部历史任务。 |
| P1-7 | `agent.py:199-218` | **`_retry_execute` 全吞异常 + 取消竞态**：retry 线程与 cancel 竞态可为已取消任务写 start_dataflow。 |
| P1-8 | `executor.py:145-184,220-240` | **任务无超时机制**：所需 buffer 长期缺失时 `_is_safely_completed` 恒 False、失败检测依赖 daemon 恰好发布 failed → 任务无限 RUNNING，机器永久不可用。 |

### P2（中，摘选）

- `_on_disconnect` 仅记日志，重连无退避、无状态补偿。
- `reporter._publish` 不检查 publish 返回值，断连期间消息静默丢失。
- `stop()` 未清理 `_running_timers`。
- `_save` 无 fsync；每次全量序列化所有任务（含完整 GeoJSON）。
- HTTP 下载无响应大小限制，全量读入内存。
- MultiPolygon 校验不一致：`_verify_field` 接受但 `_write_parcel_config` 只接受 Polygon。
- dispatch 去重按 task_id 而非 dispatch_id。
- `_runtime_process_running` PID 复用误判；`_compute_progress` 字符串浮点 int() 抛异常吞整轮进度。
- 监控线程每 1s 打开/关闭 4-5 个 buffer（fd+mmap 反复创建）。

## 4. 验证记录（自写脚本实测）

| 检查项 | 结果 |
|---|---|
| C15: `agent/store.py` 无 `can_transition_task_state` 校验（与 cloud 侧 mqtt_client.py:169 不对称） | **确认** |
| C12: contracts 状态机转移表本身正确（RUNNING→COMPLETED 合法、COMPLETED→RUNNING 与 CANCELLED→FAILED 均非法） | **通过**（契约定义对，agent 未执行） |

## 5. 总体评价

**优点**: 状态机枚举与 contracts/task.py 完全共用；QoS1 幂等去重与 busy 检查设计正确；完成判定（距离+速度+农具状态三重条件）是实机验证过的安全收敛逻辑。

**主要风险**: MQTT 线程阻塞（P1-1）、崩溃恢复缺失（P1-2）、终态覆盖竞态（P1-3）三者叠加可导致任务丢失或机器永久不可用；状态机校验缺失是根因之一（agent 与 cloud 契约不对称）。

**建议优先修复**: P1-1（下载移出 MQTT 线程或提前预下载）、P1-2（启动时对遗留活动任务收敛/置 FAILED）、P1-3/P1-5（update_state 引入 can_transition_task_state + 非法 payload 发拒绝 ACK）、P1-4（control buffer 扩容或 node_params 改引用传递）。
