# NodeFlow 全仓分模块审阅汇总报告

> 审阅日期: 2026-08-03 | 审阅方式: 逐模块代码审阅 + 自写脚本关键点验证（现有测试全部通过，未重跑）| 汇总: docs/ | 各模块明细: docs/Flesh_Test/
>
> **v1**（原始全仓静态审计）: 问题按全仓全功能范围定级，P0/P1 数量偏保守场景。
> **v2**（按上机边界重新定级，2026-08-03 再评审后更新）: 以"当前仅有人监管的边侧上机实测（Linux 单实例，不启动 cloud/server、cloud/web、edge/agent、MCP、GUI/web-editor）"为边界重新评定。**整体架构通过，主链路无新增架构级 P0，可继续有人监管上机实测。**

## 零、按上机边界重新定级（v2 结论）

### 当前主链路相关（须处理）

| 新定级 | 问题 | 结论 |
|---|---|---|
| **当前 P1** | CLI 后台启动固定等待 2 秒 [runtime_cmd.py:99](tools/cli/commands/runtime_cmd.py:99) | 模型直接调用 CLI 时相关：边侧机器可能比开发机慢，出现"CLI 报告失败但 Runtime 稍后启动"→ 重复操作。改为带超时状态轮询，或样机测试重点验证。 |
| **量产前 P1** | InputPort 生产者重启后无重连与序列号重同步 [port.py:164](edge/sdk/port.py:164) | 首次正常启动不受影响；自动重启节点后可能永久断流。不阻止第一轮上机，无人值守运行前必须解决。 |
| **量产前 P1** | 节点崩溃重启路径日志句柄生命周期 [node_launcher.py:113](edge/runtime/orchestrator/node_launcher.py:113) | 问题成立（原 P0 过重）。重启策略最多重试次数限制了短期泄漏；风险主要在长期反复崩溃运行。无人值守前门禁。 |
| **仓库治理** | 高德凭据进入 Git（parcel_planner/config.json） | 已确认被 Git 跟踪且非占位符。不阻断农机运动测试；应确认密钥状态并轮换。 |

### 被高估或不属于当前边界（降级/归档）

| 原定级 | 问题 | v2 结论 |
|---|---|---|
| P0 | 云端零鉴权、DB 外键、地图页面、SSE、MQTT 调度 | 当前不启动 cloud/server、cloud/web、edge/agent → 不属于本轮边侧上机范围；启用云端无人调度时重新成为门禁。 |
| P1 | MCP 整体失效 | 模型直接使用 nodeflow-cli，MCP 不在运行链路 → 归档或明确标记为不支持。 |
| P1 | GUI、web-editor 问题 | 已归档，全部排除。 |
| P0 | farm_coverage_viz 无法运行 | 不在现有作业图中，属失效旧节点，非系统 P0。 |
| P1 | Windows/macOS 入口问题 | 实际样机按 Linux 单实例运行时不成立。 |
| P1 | bool("false")==True 参数反转 | **判定错误（已修正）**：验证的只是 Python 常识。主链路 YAML 布尔参数经 `json.dumps → json.loads` 往返后仍是真正布尔（已验证），不构成现有主链参数反转。 |
| P1 | RTK 字段双轨制（lat/lon vs latitude/longitude） | Schema 声明确属混乱，但当前主链 rtk_filter、coord_transform 已同时兼容两种命名，不导致真实 RTK 链路取零。列契约治理，非上机阻断。 |
| P1 | 仿真器零速停车 | 代码缺陷成立，但需"先 motor 模式 → 再 velocity(0,0)"才触发；当前仿真图只走 velocity 链路，不推翻已通过的 preflight，也不等同真实 PWM 停车失效。 |
| P1 | trajectory_viz 可选端口 | 主仿真图与真实 RTK 图已连接全部相关端口；主要影响 sim_arc_tracker 等其他场景。 |

### 结论

**不要求整改全部问题后再上机。** 建议：① 继续有人监管上机实测；② CLI 启动竞态纳入近期修复；③ 节点重启后的数据恢复（InputPort 重同步）与日志资源生命周期列为无人值守运行前门禁；④ 云端、MQTT、MCP 与已归档界面按启用阶段另行评审。

## 一、审阅范围

| 模块 | 规模 | 明细报告 |
|---|---|---|
| edge/runtime 运行时核心 | 16 文件 / 3,220 行 | [01_edge_runtime.md](Flesh_Test/01_edge_runtime.md) |
| edge/sdk 节点开发 SDK | 5 文件 / 1,269 行 | [02_edge_sdk.md](Flesh_Test/02_edge_sdk.md) |
| edge/nodes 节点库 | 26 节点 / ≈18,200 行 | [03_edge_nodes.md](Flesh_Test/03_edge_nodes.md) |
| edge/agent 端侧任务代理 | 8 文件 / 1,048 行 | [04_edge_agent.md](Flesh_Test/04_edge_agent.md) |
| cloud/server 云端后端 | 42 文件 / 3,297 行 / 40 端点 | [05_cloud_server.md](Flesh_Test/05_cloud_server.md) |
| cloud/web 云端前端 | 40 文件 / 2,062 行 | [06_cloud_web.md](Flesh_Test/06_cloud_web.md) |
| tools 工具链（CLI/MCP/GUI） | 34 文件 / 6,249 行 | [07_tools.md](Flesh_Test/07_tools.md) |
| simulation + contracts | 10 文件 / 2,778 行 + 78 行 | [08_simulation_contracts.md](Flesh_Test/08_simulation_contracts.md) |
| tests 测试体系 | 92 文件 / 554 测试函数 | [09_tests.md](Flesh_Test/09_tests.md) |

验证脚本: [verify_key_issues.py](Flesh_Test/verify_key_issues.py)（16 项检查；v2 已修正 C4 推理跳跃、C13 改隔离数据库，全部检查零污染默认 farm.db）。

> 以下 v1 问题清单为原始全仓静态审计结果（全功能范围定级），供各启用阶段评审参考；当前上机阻断判定以"零、v2 重新定级"为准。

### 🔴 P0 — 致命/安全（6 项）

| # | 模块 | 问题 |
|---|---|---|
| 1 | cloud/server | **整个服务零鉴权**：AUTH_ENABLED 定义后从未引用；监听 0.0.0.0:8080；`/editor/api/runtime/start`、`/editor/api/runtime/dataflow/{action}`、`/editor/api/export/save` 为无鉴权 subprocess 端点，config_path 无路径包含校验（可 `../` 越出）。农机控制面完全裸露。 |
| 2 | cloud/server | **删除端点 FK 缺陷**（双场景实测）：全新库删除被引用 parcel/job/machine → 未捕获 IntegrityError → 500；现有 farm.db（旧 schema 无 FK）→ 删除 204 但 job 悬挂引用。 |
| 3 | edge/nodes | **farm_coverage_viz 调用不存在的 SDK 方法**：`sdk.send()/sdk.recv_latest()` 不存在于 NodeFlowSDK，启动即 AttributeError（节点不可运行）。 |
| 4 | edge/nodes | **高德地图 API 密钥硬编码并已提交 git**：parcel_planner/config.json 明文含 amap_api_key + amap_security_code。 |
| 5 | edge/runtime | **崩溃重启循环日志 handler 永久泄漏 + FD 累积**：每次"崩溃→重启"确定泄漏 FD，数百次后超 ulimit → Popen 失败、节点无法再启动。 |
| 6 | edge/runtime | **监控线程无异常保护**：`_monitor_loop` 整体无 try/except，异常时监控静默死亡，此后无重启无告警。 |

### 🟠 P1 — 高（18 项核心）

| # | 模块 | 问题 |
|---|---|---|
| 7 | cloud/server | **心跳离线检测永远失效（实测 TypeError）**：aware now − naive last_heartbeat，异常被吞 → 机器永不被标 offline、任务永不被置 communication_lost。 |
| 8 | cloud/server | **dispatch TOCTOU 竞态**：三线程并发 dispatch_queued_tasks，无原子占位 → 同一地块可能重复下发执行。 |
| 9 | cloud/server | **云规划（数秒 CPU）在 paho MQTT 回调线程同步执行**：期间 heartbeat/ACK 全部无法处理。 |
| 10 | cloud/server | MQTT 初始连接失败被静默吞掉且无重连（paho 仅首次成功后自动重连）→ broker 掉线后永久离线。 |
| 11 | cloud/server | cancel_requested 无强制终态化超时 → 任务永久卡住。 |
| 12 | cloud/web | **地图无法显示已有地块**（实测根因）：ParcelSummary 无 geojson，ParcelLayer 直接用 parcel.geojson 渲染 → 首页核心功能失效。 |
| 13 | edge/agent | **MQTT 线程被长下载阻塞 → 断连丢任务**：path 工件下载 300s 超时在 paho loop 线程内；clean_session=True 下未 ACK QoS1 消息不重投。 |
| 14 | edge/agent | **崩溃恢复缺失**：重启后遗留 RUNNING/READY 任务使机器永久 machine_busy，云边状态不一致。 |
| 15 | edge/agent | **终态覆盖竞态 + 状态机校验缺失（实测）**：cancel/完成竞态可覆盖终态；store.update_state 不调用 can_transition_task_state（cloud 侧有，不对称）。 |
| 16 | edge/agent | runtime.control 1KB 上限 vs 大 node_params → 任务直接 FAILED。 |
| 17 | edge/sdk | **InputPort 序列号陈旧永久断流**：上游 buffer 重建后 seq 归零无再同步路径。 |
| 18 | edge/sdk | **看门狗对 ppid==1 进程误杀**（launchd/init 拉起场景）。 |
| 19 | edge/nodes | **rtk 字段命名双轨制 + sim_output schema 假契约（实测）**：lat/lon vs latitude/longitude；schema 与实际数据不符，开校验即全线崩溃。 |
| 20 | edge/nodes | trajectory_viz 可选端口声明与实现不一致（实测）：4 个描述"可选"的端口无条件 create_input_port。 |
| 21 | edge/runtime | **--log-level 失效（实测 setLevel 调用=0）**；platform 硬编码 linux（darwin/macos entrypoint 无法启动）。 |
| 22 | edge/runtime | 停机期间监控线程重启竞态 → 孤儿进程；信号在初始化窗口被吞。 |
| 23 | simulation | **零速命令不能停车**：控制模式按值推断，velocity(0,0) 回退油门模式沿用残留 throttle（农机安全隐患）。 |
| 24 | tools | **MCP server 整体失效（实测）**：resolve_project_path 根算成 tools/mcp；import 链断裂；MCP 测试被排除且导入失败。 |

### 🟡 P2 — 中（摘选 20 项）

- **测试体系**: simulation 集成测试 2 处与实现矛盾（50Hz vs 断言 20Hz、state["vx"] 嵌套结构）；contracts 零直接测试；mcp/legacy 测试不在收集范围；3 处真空测试（无断言）；test_buffer_config 硬编码个人路径。
- **tests 根目录** 22 个测试游离于 pytest 之外（e2e_cli/多循环/僵尸修复），且引用已删除的 node-hub/、simulator/server.py 路径。
- **布尔参数字符串转换**：仅当参数以字符串形式入参时 `bool("false")==True` 成立；主链路 YAML→json 往返保持原生 bool，**v2 判定为非当前问题**（原表述"4 个节点受影响"过重，降为注释性风险）。
- **edge/agent**: dispatch 去重按 task_id 而非 dispatch_id；无超时机制任务无限 RUNNING；reporter 不检查 publish 返回值。
- **edge/runtime**: restart_policy off-by-one（max_retries=3 实际只重启 2 次）；_clean_buffers 清空自身 control/status 缓冲；rmtree 全局 /tmp 缓冲目录。
- **cloud/server**: SSE 无 keepalive ping、队列满静默丢；_get_or_create_splits 中途 commit 残留；migrations 无真正迁移（farm.db 旧 schema 与模型漂移即为本次实测发现）。
- **cloud/web**: SSE 重连无退避可多连接并发；JobCreate 无 try/catch 重复建单；monitor 子应用 SSE 端点不存在；Element Plus locale 空翻译。
- **tools**: tools/cli/cli 重复树 2,813 行；test_reporter 目录重组后报废；web-editor vite proxy 端口 8000 vs 8080；CLI runtime start sleep(2) 竞态误报失败。

## 三、分模块结论（v1 全仓视角；v2 上机判定见第零节）

| 模块 | 总体评价 | 最优先修复 |
|---|---|---|
| edge/runtime | 分层启动与进程组终止设计良好；风险集中在崩溃重启链路 | handler 泄漏、监控线程保护（v2: 量产前门禁） |
| edge/sdk | mmap 协议自洽（实测读写+seq 正确）；InputPort 可靠性是短板 | seq 再同步、看门狗守卫（v2: 量产前门禁） |
| edge/nodes | L3/L4 分层贯彻好，主链路一致；安全基线薄弱 | SDK API 旧节点归档、密钥轮换、rtk 字段统一（v2: 密钥=仓库治理，余项契约治理） |
| edge/agent | 幂等去重与完成判定设计正确；可靠性短板集中 | MQTT 阻塞、崩溃恢复、状态机校验（v2: 云端无人调度启用时门禁） |
| cloud/server | 状态机契约与"先落库后发布"正确；安全与并发是主要风险 | 鉴权、FK、心跳、dispatch 原子化（v2: 云端启用时门禁） |
| cloud/web | 分层清晰、TS 零错误；契约使用与错误处理是短板 | ParcelSummary 补 geojson（v2: 云端启用时门禁） |
| tools | CLI 主体完整健康；8 月目录重组后系统性遗留 | **CLI runtime start 2s 竞态（v2: 当前 P1，近期修复）**；MCP 归档 |
| simulation/contracts | 闭环设计清晰、坐标系自洽；模式推断与假契约是风险 | 零速停车（v2: 触发条件限定，非上机阻断）、schema 对齐 |
| tests | L4 算法层覆盖好；真实自动化覆盖低于表象 | simulation 测试对齐、mcp 测试修复、contracts 补测试 |

## 四、跨模块根因归纳

1. **目录重组（9e7bd83）系统性遗留**: MCP 根目录/导入、test_reporter、web-editor 脚本、tests 根目录引用、install_node_deps 均指向旧路径。
2. **schema 假契约**: 节点 schema 声明与实际数据漂移（sim_output/sim_input），靠 `NODE_SCHEMA_VALIDATION` 默认关闭掩盖——建议开启 strict 作为 CI 门槛。
3. **契约不对称**: contracts/task.py 状态机在 cloud 侧强制、edge/agent 侧未强制 → 终态可被覆盖。
4. **数据库 schema 漂移**: farm.db 旧表无 FK 约束与模型定义不符，migrations.py 无真正迁移能力。
5. **线程模型隐患**: paho 回调线程（cloud 规划、agent 下载）、监控线程（runtime 重启）均无工作线程隔离。

## 五、修复路线（按 v2 边界分阶段）

**近期（上机实测期间，有人监管）**: CLI runtime start 2s 竞态改为带超时状态轮询 [runtime_cmd.py:99]；样机验证中对 Runtime 启动耗时打点，确认 sleep(2) 是否够用。

**无人值守运行前门禁**: InputPort 生产者重启后的重连 + 序列号重同步 [port.py:164]；崩溃重启路径日志句柄生命周期修复 [node_launcher.py:113]；runtime 监控线程异常保护。

**仓库治理（不阻断上机）**: 高德凭据确认状态并轮换移出 git。

**云端无人调度启用时门禁（届时重新评审）**: cloud 鉴权/editor 子进程端点/FK/心跳时间/dispatch 原子化、agent MQTT 阻塞与崩溃恢复、状态机校验、ParcelSummary geojson、SSE/MQTT 系列、MCP 启用修复。

**测试与收尾**: simulation 测试对齐 → contracts 测试 → 删除死代码/真空测试 → 补齐高价值缺口（heartbeat_monitor、dispatch_reconciler、agent、sensing 主循环）。

*各模块详细证据（含 file_path:line_number）见 docs/Flesh_Test/ 下对应报告。*
