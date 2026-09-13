# NodeFlow 项目模块调查报告（非 CLI）

日期：2026-05-29
范围：本次只调查 CLI 之外的项目模块，包括 runtime、SDK/IPC、node-hub 节点、simulator、cloud、web-editor/backend、GUI/MCP、测试与文档。
约束：按要求未修改运行代码；本报告是本次唯一计划新增内容。

## 1. 执行摘要

当前项目已经形成了比较完整的“云端任务 - 边侧 Runtime - 仿真器 - 规划控制 - 可视化复盘”闭环骨架，但存在几个会直接影响后续验证的关键问题：

1. `runtime.main` 的传统启动路径存在高风险逻辑错误：`run()` 在 `start_dataflow()` 之后才把 `self.running` 设为 `True`，但 `start_dataflow()` 又把 `not self.running` 作为取消条件传给启动协调器。这可能导致 `python3 -m runtime.main examples/planning_simulation.yaml` 这种文档推荐方式启动时直接取消数据流。
2. `tillage_controller` 已经接入 `planning_simulation.yaml`，但状态机在进入 `LOWERING` 后，下一帧可能被“同一个 work 意图”从 `RAISING` 分支或中途转换逻辑打断。结合覆盖率只在 PTO 或悬挂下降时统计，这很可能解释“有实际轨迹但没有已覆盖面积”的现象。
3. `planning_simulation.yaml` 的静态配置、端口和拓扑是通过的，但真实闭环仍缺少端到端自动验收。现有测试覆盖了很多原子层，但没有约束“仿真器启动 + runtime 启动 + 规划 + 追踪 + 机具覆盖 + 可视化截图”这一完整链路。
4. cloud 的任务下发链路目前更像协议骨架：`download_path()` 返回空路径占位，边侧 `TaskExecutor` 只是向 `runtime.control` 写 `start_dataflow`，没有真正完成 parcel/path 下载、任务配置注入、执行完成判定。
5. Web editor/backend/GUI/MCP 仍有多套 Runtime 控制实现，并且一部分调用旧 `RuntimeManager` 或 CLI 包装。CLI 修过后，这些入口需要统一回归，否则“工具可用”会变成入口间行为不一致。

## 2. 本次验证动作

只做静态和轻量只读验证，没有启动 Runtime 或仿真器。

已执行命令：

- `./nodeflow-cli runtime status --json`：返回 `{"status":"not_running","pid":null}`。
- `./nodeflow-cli buffer list --json`：返回空 buffer 目录，`count=0`。
- `./nodeflow-cli node list --json`：扫描到 node-hub 节点 20 个。
- 静态解析 `examples/planning_simulation.yaml`：基础配置有效、图验证有效、拓扑 8 层。
- `./nodeflow-cli health flow --config examples/planning_simulation.yaml --json`：Runtime 未运行时返回 unhealthy，12 个预期 buffer 全部 `MISSING`。这不是配置错误，只说明数据流没有启动。
- `python3 -m pytest tests/unit/test_tillage_controller.py tests/unit/test_startup_coordinator.py tests/unit/test_runtime_cli.py -q`：35 passed。
- `python3 -m pytest node-hub/waypoint_selector/test/test_atom.py node-hub/track_controller/test/test_atom.py node-hub/path_progress/test/test_atom.py -q`：18 passed。
- `python3 -m pytest node-hub/trajectory_viz/test/test_replay_atom.py -q`：5 passed。

注：曾误跑 `node-hub/trajectory_viz/test_replay_atom.py`，该路径不存在，未执行任何测试；随后已用正确路径复跑。

## 3. 工作区状态说明

调查开始前工作区已存在大量未提交改动和未跟踪文件，包括：

- CLI 命令、CLI 文档和 skill 相关文件。
- `runtime/main.py`、`runtime/orchestrator/startup_coordinator.py`、`runtime/task/executor.py` 等 runtime 改动。
- `node-hub/waypoint_selector`、`trajectory_viz`、`tillage_controller`、`global_coverage` 输出路径文件等节点相关改动。
- `examples/planning_simulation.yaml`、`simulator/config.yaml`、`simulator/server.py`。
- `cloud/server/farm.db*`、`other/png/` 截图和路径输出文件。

本次报告没有回滚、清理或整理这些改动。后续提交前应单独分组确认哪些属于前序工作、哪些属于运行产物。

## 4. Runtime 与编排模块

### 4.1 传统启动路径可能无法启动数据流（高优先级）

证据：

- `runtime/main.py` 的 `start_dataflow()` 调用 `startup_nodes(..., should_cancel=lambda: not self.running)`。
- 同文件 `run()` 先调用 `self.start_dataflow()`，之后才设置 `self.running = True`。

影响：

- 文档中推荐的 `python3 -m runtime.main examples/planning_simulation.yaml` 可能在 `run()` 模式下启动失败或直接取消节点启动。
- CLI 的 daemon 模式可能不受同样影响，因为 `run_as_daemon()` 先设置 `self.running = True`，再等待 `start_dataflow` 命令。

建议：

- 将 `run()` 中的 `self.running = True` 前移到 `start_dataflow()` 之前。
- 或者让 `start_dataflow()` 的取消条件只在外部显式取消时生效，而不是依赖框架级 running 标志。
- 增加一个单测覆盖传统 `run()` 启动路径，至少验证 `StartupCoordinator.startup_nodes()` 会被实际调用而非立即取消。

### 4.2 Runtime 控制入口重复

现状：

- 新 CLI 走 `tools/cli/commands/runtime_cmd.py`。
- Web editor backend 通过 `python -m tools.cli.core.cli runtime ...` 调 CLI。
- MCP 和旧管理逻辑仍依赖 `runtime_manager.py`。
- GUI 也通过 CLI 包装 runtime 控制。

风险：

- CLI 修复后，MCP/RuntimeManager 仍可能保留旧行为。例如 `RuntimeManager.start_runtime()` 启动的是传统 `runtime.main`，不是 daemon 模式，且会受 4.1 影响。
- 用户从不同入口启动同一系统时，PID 文件、日志路径、控制 buffer 的语义可能不一致。

建议：

- 明确一个唯一控制面：优先使用 CLI + daemon 模式。
- MCP、GUI、backend 只包装同一组 CLI 命令，不再各自实现 runtime 生命周期。
- 将 `runtime_manager.py` 标为 legacy 或收敛为只读状态/日志工具。

### 4.3 图类型不兼容只给 warning

证据：

- `runtime/graph/validator.py` 中端口类型不兼容时调用 `result.add_warning()`，不会阻止启动。

影响：

- 对仿真调试有利，但对边缘侧实际作业不够安全。类型错连可能进入运行期才暴露，CLI/API 也难以给出“不可执行”的明确结论。

处理结论：

- 不引入“验证级别体系”。类型兼容性边界继续由现有图验证与模型/节点输出约束共同保证，避免把语言模型应负责的判断再做一层框架抽象。
- Web editor 与 runtime 的基础类型规则仍应保持一致，避免前端禁止但 runtime 放行，或反过来。

## 5. SDK 与 IPC

### 5.1 SharedBuffer + ZeroMQ 架构基本可用，但缺少运行期健康契约

现状：

- `OutputPort` 写 SharedBuffer 再发 ZMQ 通知。
- `InputPort` 可读历史数据，解决 late joiner。
- `buffer list/inspect` 已经可以作为边缘侧调试入口。

风险：

- `InputPort` 初始化只等 buffer 文件约 2 秒，之后 buffer 不存在时只记录 warning，后续不会主动重试创建/打开 buffer。
- 输出端口重启复用已有 buffer 文件，如果 size 与 manifest 变化不一致，可能保留旧尺寸。
- `health flow` 只能看 buffer 是否增长，不知道节点是否“逻辑健康”，比如控制器输出零速但仍增长。

建议：

- 给 `InputPort` 增加 lazy reconnect/reopen buffer 策略。
- buffer metadata 中增加 manifest size、schema、producer pid/start_time。
- 不增加“语义健康检查插件”。运行期语义是否异常由复盘数据、节点测试和语言模型诊断输出判断；CLI health 继续聚焦 buffer 是否存在、是否增长、基础连通性是否正常。

## 6. 规划、路径进度与追踪节点

### 6.1 `planning_simulation.yaml` 静态配置通过

静态验证结果：

- `config_valid=True`
- `graph_valid=True`
- 拓扑层：
  1. `sim_output`
  2. `rtk_filter`
  3. `coord_transform`
  4. `global_coverage`
  5. `path_progress`
  6. `waypoint_selector`
  7. `tillage_controller`, `track_controller`
  8. `sim_input`, `trajectory_viz`

这说明端口名和拓扑依赖层面已经能对齐。

### 6.2 掉头问题仍可能来自目标点策略与局部控制组合

已观察设计：

- `global_coverage` 已增加 `operation_plan`、`path_zones`、`segments`、限速与机具意图。
- `path_progress` 用投影进度输出段语义、横向误差、路径 heading。
- `waypoint_selector` 已支持基于 `path_progress` 的里程前瞻目标，避免纯视野窗口追旧点。
- `track_controller` 已使用路径段限速、前方转角减速、横向误差减速/恢复。

仍存在风险：

- `track_controller` 本质仍是“朝目标点转向”的 P 控制，掉头湾这种短半径、急反向、带噪声场景下，可能需要更明确的转向状态机，而不仅是目标点移动。
- `progress_target_lookahead_m=2.5` 对 3m 幅宽和 U 型弯可能偏短，容易在进入折返时目标点跳动。
- `cross_track_stop_error_m=1.5` 配合仿真噪声和掉头区几何，可能过早进入低速恢复，导致“转不过去但持续追目标”的状态。

建议：

- 下一步不要只调 waypoint_selector，应把 `path_progress.segment_type=headland_turn` 作为控制模式切换信号。
- 对 `headland_turn` 段使用单独控制器：低速、允许原地旋转、按路径切线/目标航向闭环，而不是只追坐标点。
- 在可视化中同时看 `path_index`、`segment_type`、`cross_track_error_m`、`velocity_cmd.status`，用截图定位究竟是“目标点回退”“横向误差保护”“速度过低”还是“仿真器旋转能力不足”。

## 7. 机具控制与覆盖率

### 7.1 覆盖率没有显示的主要可疑点

可视化覆盖计算位于 `trajectory_viz/atom.py`：

- 只有当 replay sample 中 `pto_on=True`，或 `hitch_height>=0.5`，或 state 属于 `working/lowering/ready_to_engage` 时，才计入覆盖。
- 覆盖面积当前是“相邻采样段矩形面积累加”，没有做重叠去重。

结合 `tillage_controller` 状态机：

- `TRANSPORT` 中如果 `should_lower=True`，会切到 `LOWERING`。
- `LOWERING` 中如果 `should_raise=True`，会切到 `RAISING`。
- `RAISING` 中如果 `should_lower=True`，会切到 `LOWERING`。

风险：

- 如果 `path_progress` 或 `next_point.zone` 在掉头/起步阶段频繁 work/transit 切换，悬挂可能一直在下降/上升边界，没有稳定进入 `WORKING`。
- 如果 `tillage_status` 没有被 trajectory_viz 收到，`make_replay_sample()` 会用 `path_progress.implement` 推断 intent；这能产生覆盖意图，但不能替代真实机具状态。若状态机输出长期 transport，覆盖率为 0 是合理结果。

建议：

- 先修正状态机的中途打断规则：刚从 `TRANSPORT -> LOWERING` 后，不应在下一帧因为同一 work 意图触发反向切换。
- 给 `tillage_controller` 增加状态转换单测，覆盖“连续 work zone 2 秒后必须进入 WORKING，PTO 必须 ON”。
- 可视化同时显示 `coverage_overlay.active_segments`，否则只有覆盖率 0 不容易判断是“无机具状态”“机具没降下”还是“采样不足”。
- 覆盖率后续应用 Shapely union 与 field polygon 裁剪，避免重叠累加导致超过真实覆盖面积。

## 8. 仿真器

### 8.1 初始点贴近入口已经有配置支持

`simulator/config.yaml` 里已有：

- `server.random_seed: 20260529`
- `initial_pose_mode: entry`
- `initial_max_distance_m: 1.0`

`simulator/server.py` 会在初始化和刷新地块时把车辆放到入口点附近，并朝向田地中心。这有利于复现实验。

### 8.2 速度控制零命令会切回 throttle 模式

`simulator/physics.py` 中 `step()` 通过 `linear_velocity` 或 `angular_velocity` 是否非零判断使用速度控制，否则走 throttle 控制。

风险：

- 如果速度模式下收到 `(0, 0)`，下一步会切回 throttle 模式。当前 throttle 默认也为 0，所以一般不影响停车。
- 但如果历史 throttle/steering 曾被设置过，零速度命令不一定严格代表“速度模式停车”。

建议：

- 增加显式 `control_mode` 字段，`set_velocity_control()` 后保持 velocity mode，直到明确切换。
- `reset` 时也应调用 `_init_robot_from_config()`，否则刷新和 reset 行为不同。

### 8.3 RTK 数据契约仍有兼容痕迹

现状：

- simulator 输出 `latitude/longitude`。
- `rtk_filter` 和 `coord_transform` 同时兼容 `lat/lon` 与 `latitude/longitude`。
- `sim_output` schema 里曾定义 `lat/lon`，但实际发送可能是 simulator 原始字段。

风险：

- 在 schema validation 打开 strict 模式后，当前兼容字段可能变成失败点。

建议：

- 项目级明确标准字段：推荐内部统一 `lat/lon`，驱动层负责适配外部字段。
- 更新 schema、文档和测试，避免 loose 模式掩盖接口漂移。

## 9. 可视化与复盘

### 9.1 可视化已经具备复盘基础

现有能力：

- 地块、规划路径、实际轨迹、目标点、路径进度、速度/角速度、减速因子、机具状态、覆盖 footprint。
- replay sample 和 replay events 可用于截图复盘。

风险：

- `update_interval` 默认 5 秒，复盘截图可能错过中间状态变化。
- 覆盖率是估算值，没有去重，没有裁剪到地块边界。
- UI 面板显示的是当前最后值，不显示“最近一次状态变化时间”，难以判断数据是否 stale。

建议：

- 测试复盘时将 `update_interval` 临时降到 0.5 或 1.0 秒。
- 增加 stale 标记：比如每个输入包显示 age。
- 覆盖 overlay 加 `active_segments`、`area_estimation`、`sample_count` 到面板。

## 10. Cloud 与边侧任务链路

### 10.1 云端下发还是协议骨架

证据：

- `cloud/server/services/dispatcher.py` 生成 `parcel_url` 与 `path_url`，并通过 MQTT 下发任务。
- `cloud/server/routers/files.py` 的 `/download/paths/{task_id}.bin` 返回空路径占位：`path: []`, `status: pending`。
- 边侧 `TaskExecutor.execute()` 只向 `runtime.control` 写 `start_dataflow` 和 `node_params`，没有看到下载 path/parcel 并注入 planning 节点的完整过程。

影响：

- 云端到边侧链路目前能验证“消息到了”和“Runtime 收到启动命令”，但不能验证真实作业路径来自云端。
- 若接到边缘侧 API，调试工具需要明确标注该链路尚未实现完整数据下载与任务完成闭环。

建议：

- 补一个边侧任务 preparation 阶段：下载 parcel/path、校验 checksum、转换成 node_params 或本地任务文件。
- `download_path()` 不应长期返回空占位。短期可以返回 404/409 表示路径未生成，避免边侧误以为下载成功。
- `TaskExecutor` 需要从 `path_progress` 或任务完成事件判断 completed，而不是只把状态设为 RUNNING。

### 10.2 云端数据库与运行产物进入工作区

现状：

- `cloud/server/farm.db`、`farm.db-shm`、`farm.db-wal` 在工作区未跟踪。

建议：

- 确认 `.gitignore` 是否覆盖 SQLite 运行产物。
- 测试数据应使用临时目录或 fixture 数据库。

## 11. Web Editor / Backend / GUI / MCP

### 11.1 Web editor backend 的 Runtime 状态不完整

证据：

- `backend/app.py` 的 `/api/runtime/status` 只检查 PID 是否存在，`uptime_seconds` 和 `memory_mb` 暂时返回 0。

影响：

- 前端看到 running 但无法判断 runtime 是否真实健康，也无法区分 daemon 空转与 dataflow running。

建议：

- backend 直接调用 `./nodeflow-cli runtime status --json`。
- 状态结构里区分 `runtime_status` 与 `dataflow_status`，并暴露 active node 数量、最近错误日志。

### 11.2 MCP 的运行时入口仍可能走旧路径

证据：

- `mcp_server.py` 中 `run-runtime` 使用 `runtime_manager.start_runtime()`。
- `runtime_manager.py` 启动命令是 `python3 -m runtime.main <yaml>`，没有 `--daemon`。

影响：

- MCP 工具和 CLI 工具可能对同一项目给出不同结果。

建议：

- MCP 的运行/停止/状态查询统一委托 CLI。
- `nodeflow/edit-yaml` 这种会写文件的 MCP 工具应默认生成备份，且与当前“不要修改模块”的工作模式区分清楚。

## 12. 测试体系

现有优点：

- 关键原子层有测试：waypoint、track、path_progress、tillage、trajectory_viz replay。
- CLI 与启动协调器已有局部测试。
- IPC 层有 SharedBuffer/Port 测试。

主要缺口：

- 没有覆盖传统 `NodeFlowRuntime.run()` 的启动顺序 bug。
- 没有完整 `planning_simulation.yaml` 端到端自动测试，包括仿真器进程、runtime daemon、dataflow、截图和覆盖率断言。
- 云端任务链路没有“云端 dispatch -> MQTT -> edge agent -> runtime -> status report”的集成验收。
- 测试中仍有旧命名和旧节点痕迹，如 `velocity_controller`，与当前 `track_controller` 并存，容易误导。

建议补充的高价值测试：

1. Runtime 传统启动冒烟测试：mock `StartupCoordinator`，断言不会被 `should_cancel` 立即取消。
2. Planning simulation 60 秒验收：启动 simulator + runtime daemon + dataflow，断言关键 buffer 均增长。
3. 掉头段验收：固定 random seed，采集 `cross_track_error_m`、`path_index`、`velocity_cmd.status`，对最大偏差和进度单调性设阈值。
4. 机具覆盖验收：在 work 段运行至少 N 秒后，断言 `tillage_status.state == working` 曾出现，`coverage_overlay.active_segments > 0`，`coverage_rate_percent > 0`。
5. Cloud dispatch 契约测试：空路径下载应明确失败或 pending，不允许被边侧当作可执行路径。

## 13. 建议修复顺序

第一阶段：先保证验证工具可信

1. 修复 runtime 传统启动顺序或明确废弃传统 run，只保留 daemon + CLI。
2. 统一 GUI/backend/MCP Runtime 控制入口到 CLI。
3. 给 health 增加“runtime 未运行”的清晰提示，避免把 `MISSING` 全量输出误解为配置坏。

第二阶段：修复复盘与机具覆盖

1. 调整 `tillage_controller` 状态机，确保连续 work zone 会稳定进入 WORKING。
2. 可视化面板补 `active_segments`、输入 age、覆盖估算说明。
3. 覆盖率改用 Shapely union + field clip。

第三阶段：掉头控制闭环

1. 基于 `operation_plan.segment_type=headland_turn` 切换掉头控制模式。
2. 在 headland_turn 中控制目标航向、角速度上限和速度 profile，不只追下一个点。
3. 建立固定 seed 的掉头回归测试。

第四阶段：云边任务闭环

1. 实现边侧下载与校验 parcel/path。
2. `TaskExecutor` 监听真实进度与完成条件。
3. 云端 `download_path` 不再返回空路径占位，或者显式返回 pending 错误。

## 14. 结论

当前项目不是“只有 CLI 有问题”。CLI 暴露了调试入口不稳定的问题，但更深层的风险在于 Runtime 控制入口分裂、传统启动路径疑似失效、机具状态机与覆盖率复盘之间缺少端到端约束、云边任务链路仍未闭合。

建议下一步先修 Runtime 启动与机具覆盖两处，因为它们直接影响后续仿真截图和掉头问题定位。等这两处稳定后，再继续优化掉头控制策略和云端任务执行闭环。
