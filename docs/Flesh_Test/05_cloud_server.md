# 模块审阅报告：cloud/server（云端后端）

> 审阅日期: 2026-08-03 | 审阅方式: 代码审阅 + 关键点脚本验证 | 存放: docs/Flesh_Test/（临时）
> **v2 定级注记**: 按上机边界重新评定后：本模块（含零鉴权、FK、心跳、dispatch 竞态、SSE/MQTT 系列）**不属于当前边侧上机范围**（本轮不启动 cloud/server、cloud/web、edge/agent）；启用云端无人调度时重新成为门禁。验证脚本 v2 已改为隔离临时数据库，不再触碰默认 farm.db。详细映射见汇总报告第零节。

## 1. 模块职责

云端农场管理平台 FastAPI 后端：地块管理、机器管理、作业编排（分割/下发/取消）、任务状态机、MQTT 对接、SSE 实时推送、云规划产物生成。

| 分层 | 文件数 | 行数 |
|---|---|---|
| 核心 (app/config/database/migrations) | 4 | 208 |
| models/ (9 表 ORM) | 7 | 266 |
| schemas/ (Pydantic) | 6 | 271 |
| routers/ (40 端点) | 9 | 795 |
| services/ (MQTT/分割/下发/监控) | 8 | 1,276 |
| tests/ | 8 | 481 |
| **合计** | **42** | **3,297** |

- 数据库表: parcels, parcel_splits, machines, jobs, job_steps, edge_tasks, coordinate_frames, path_artifacts, schema_migrations
- API 端点: 28 个 `/api/v1` + 12 个 `/editor`（editor 挂在根路由，无 /api/v1 前缀）

## 2. 核心服务

- **mqtt_client.py (302 行)**: 订阅 `nodeflow/+/heartbeat|status|task/ack`；心跳更新机器遥测 + 自动发现；task_status 做状态机转移校验 + 进度单调递增 + `_try_advance_step` 步骤推进；task_ack 处理 accepted/machine_busy 拒绝。
- **dispatcher.py (380 行)**: dispatch_job → `_get_or_create_splits`（ParcelSplitter）→ 依赖判断 → `_dispatch_step`（先 commit 再 MQTT publish，避免 ACK 先于落库）；cloud_preferred 降级为边缘规划；单机单任务串行。
- **heartbeat_monitor.py (70 行)**: 30s 周期，300s 超时 → 标 offline + running 任务置 communication_lost。
- **dispatch_reconciler.py (80 行)**: 2s 周期重发 pending 超时/cancel_requested/queued。
- **cloud_planner.py (122 行)**: 动态加载 global_coverage 包 → msgpack 打包 → SHA256 → PathArtifact 落库。
- **splitter.py / geo.py**: strip 分割（最小旋转矩形 + 等宽条带）+ checkerboard 网格。
- **sse_broker.py (42 行)**: threadsafe 投递（loop.call_soon_threadsafe + Lock），队列上限 256。

## 3. 发现的问题

### P0（安全 / 默认部署即高危）

1. **整个服务零鉴权**：`config.py:19` 定义 `AUTH_ENABLED` 但从未被引用；默认监听 `0.0.0.0:8080`；CORS `allow_origins=["*"] + allow_credentials=True`（非法组合）。任何局域网主机可：未认证 POST `/editor/api/runtime/start`（subprocess 执行 CLI）、`/editor/api/runtime/dataflow/{action}`、`/editor/api/export/save`（写任意文件）、`/api/v1/jobs/{id}/dispatch`（远程控制农机）。`start_runtime` 的 config_path 仅 exists() 检查，可 `../` 越出项目根（editor.py:103-114）。

### P1（功能失效 / 必然错误）

| # | 位置 | 问题 |
|---|---|---|
| 2 | `services/heartbeat_monitor.py:44-52` | **离线检测永远失效（已实测复现）**：`now` 为 aware datetime，`m.last_heartbeat` 从 SQLite 读回为 naive → `now - m.last_heartbeat` 抛 TypeError，被 `_loop` 的 except 吞掉 → 机器永不被标 offline、任务永不被置 communication_lost。 |
| 3 | `routers/parcels.py:78-85`、`jobs.py:142-151`、`machines.py:79-86` | **删除端点 FK 缺陷（两场景均实测）**：全新库上删除被引用 parcel 抛未捕获 IntegrityError → 500；现有 farm.db（旧 schema 无 FK 约束）上删除返回 204 但 job 悬挂引用。 |
| 4 | `services/dispatcher.py:182-228` | **TOCTOU 竞态 → 重复下发**：`dispatch_queued_tasks` 由 Reconciler/MQTT/API 三线程并发调用，读 queued→写 pending→publish 无原子占位 → 农机可能重复执行同一地块。 |
| 5 | `services/mqtt_client.py:236-273` | **云规划（数秒 CPU）在 paho 网络回调线程中同步执行**：期间 MQTT 无法处理 heartbeat/ACK，机器可能被误判心跳超时。 |
| 6 | `app.py:28-31` | MQTT 初始连接失败被 `except: pass` 静默吞掉，paho 仅首次连接成功后自动重连 → broker 掉线后永久离线。 |
| 7 | `dispatch_reconciler.py:56-68` | cancel_requested 超时后仅重发 cancel，无强制终态化 → 任务永远卡住。 |
| 8 | `routers/jobs.py:154-168` | `JobDispatchRequest.machine_assignments` 被忽略；job cancel 后无重新打开路径。 |
| 9 | `services/dispatcher.py:43,306` | `_get_or_create_splits` 中途 commit，后续失败时 splits 残留（半成品数据）。 |
| 10 | `services/mqtt_client.py:173-174` | `float(payload.get(...))` 无类型/范围校验（负 progress 直接入库）。 |
| 11 | `services/sse_broker.py:21` | SSE 无 keepalive ping（代理 60s 空闲断连风险）；队列满静默丢事件。 |

### P2（摘选）

- `migrations.py`：schema_migrations 永远只记 version=1，farm.db 旧 schema 与模型定义漂移（本次实测发现 jobs/parcels/edge_tasks 表无 FK 约束）——无真正迁移机制。
- `dispatcher.py:231` `split = ...one()` 未捕获 NoResultFound → 500。
- `requirements.txt` 缺 PyYAML/pytest/httpx；pyclothoids 冗余。
- `routers/parcels.py:55-75`：parcel geojson 更新后已生成 splits/edge_tasks 不失效。
- `cloud_planner.py:21-31`：动态 import 无锁无幂等。
- `routers/editor.py:125-135`：runtime status uptime/memory 恒 0（占位）。

## 4. 验证记录（自写脚本实测）

| 检查项 | 结果 |
|---|---|
| C1: heartbeat_monitor `now - m.last_heartbeat` → `TypeError: can't subtract offset-naive and offset-aware datetimes`（连真实模型验证 naive tzinfo） | **确认（P1 #2）** |
| C13: 全新隔离库删除被引用 parcel → 500 IntegrityError；现有 farm.db → 204 但 job 悬挂引用 | **双缺陷确认** |
| C14: `ParcelSummary` 不含 geojson（前端地图渲染缺陷根因，见 web 报告） | **确认** |
| 现有测试 13 个全部通过（用户已确认，未重跑） | - |

## 5. 总体评价

**优点**: 状态机契约（contracts/task.py）在 cloud 侧强制执行且正确；"先落库后发布"避免 ACK 竞态；SQLite WAL + busy_timeout 配置合理；SSE 跨线程投递模式正确；`_try_advance_step` 由 paho 单线程串行化。

**主要风险**: P0 零鉴权控制面（农机系统控制面完全裸露）必须优先修复；P1 #2（离线检测失效）与 #3（删除 FK）恰好都落在零测试区域；dispatch 竞态会导致重复作业（安全事件）。

**建议优先修复**: P0（开启 AUTH_ENABLED 或移除 editor 子进程端点 + config_path 严格校验）、P1 #2（DateTime(timezone=True) 或统一 naive/aware）、P1 #3（FK ondelete/手动级联 + 删除前引用检查）、P1 #4（`UPDATE ... WHERE state='queued'` 原子占位）。

**测试缺口**: jobs.py 全部端点、tasks.py、events.py、editor.py 全部端点、heartbeat_monitor、dispatch_reconciler 均零测试。
