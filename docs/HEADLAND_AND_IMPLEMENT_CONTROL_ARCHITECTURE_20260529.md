# 地头掉头与机具控制架构方案

日期: 2026-05-29

## 结论

建议采用“规划给意图，运行时闭环执行”的混合架构。

不建议把全链路做成纯 G-code 式死指令，也不建议只靠实时姿态反应式判断。更合适的方式是：

- 规划节点输出带语义的作业计划：作业行、地头区、掉头段、速度上限、机具意图、提前/滞后触发距离。
- 运行时节点根据 RTK 姿态、路径跟踪状态、实际航向/曲率、机具反馈、安全互锁来执行 PTO、悬挂、分段开关、速度限制。
- 底盘控制和机具控制解耦，但共享同一份 `operation_plan`、`pose_enu` 和路径进度。

这个设计更接近实际农机自动化系统：地头边界和引导线决定在哪里转弯，转弯自动化同时协调速度和机具动作；机具控制则必须考虑执行器延迟、实际位置和安全状态。

## 调研摘要

农业覆盖路径规划通常不是单一“画一条线”问题，而是分成地头生成、作业行生成、作业行排序、地头连接路径、轨迹平滑/约束跟踪等模块。Fields2Cover 文档里也把 swath、route、headland path 分开处理，并用多个机宽作为地头空间的经验设置。

学术上，地头掉头会显式考虑车辆和机具的运动学约束、地头几何约束、不同掉头类型，例如 U-turn、bulb turn、fishtail turn，以及带拖挂机具的情况。实际系统不会把掉头当成普通折线跟踪。

商业系统也把边界/地头边界作为触发基础。John Deere AutoTrac Turn Automation 要求 field boundary、headland boundary 和 guidance track；其说明中明确提到地头边界会触发端行功能，例如速度、机具升降。显示器帮助文档也把 end turns 中的 machine/implement functions 协调、speed control、equipment control 作为功能项。

ISOBUS Task Controller 的功能划分也值得借鉴：

- TC-BAS: 任务总量/面积/用量记录。
- TC-GEO: 按地理位置记录或控制，例如处方图。
- TC-SC: 基于 GPS 和重叠率做自动分段控制。

这些都说明：规划应提供地理/作业语义，控制器按实时状态执行，而不是让单个节点完全承担所有决策。

## 当前掉头湾问题判断

这次仿真里看到的主要问题不是单一 bug，而是三层问题叠加：

1. `global_coverage` 输出的是折线点列，掉头区有 90 度和 180 度级别的硬折角，没有段语义和曲率约束。
2. `waypoint_selector` 的矩形视野算法在掉头区会频繁进入 `in_view_count` 很低或 `mode=approach` 的状态，说明目标点选择已经不稳定。
3. 原来的 `track_controller` 基本只看目标点坐标和航向误差，没有利用 `mode/in_view_count` 这类路径跟踪健康信号，也没有提前读前方转角，所以在目标点已经不稳定时仍可能输出较高线速度。

所以短期判断是：当前掉头湾最直接的问题在控制器没有“看懂”路径状态，速度没有随路径可跟踪性下降；路径没做圆角是中长期问题，但不是这次最小修复的第一刀。现在已做的低风险修复是：

- `waypoint_selector.next_point` 增加前方转角预判：`upcoming_turn_angle_deg`、`upcoming_turn_distance`。
- `track_controller.velocity_cmd` 根据 `in_view_count`、`mode`、前方转角做自适应减速。
- 在掉头前让速度主动降下来，避免用高速冲进 U 形/折返区域。

这不是最终方案。最终应让规划输出可跟踪的掉头曲线和 `headland_turn` 段，而不是让控制器长期补救折线路径。

## 常见工况解决思路

### 地头掉头

常见做法不是让普通行间跟踪器硬吃地头折线，而是显式规划掉头段：

- 地头边界先定义出来，通常由外边界等距内缩或人工/历史轨迹生成。
- 作业行和地头连接路径分开生成，地头连接可以选择 U-turn、bulb/omega、fishtail、switch-back、figure-eight 等模式。
- 掉头路径需要满足车辆最小转弯半径、最大曲率/曲率变化率、是否支持倒车、拖挂机具外摆、边界/障碍约束。
- 运行时按实时 pose 做路径进度和误差估计，必要时动态重规划或降级停车。

对当前履带/可原地转向仿真底盘来说，短期可以允许 `pivot`，但实机仍应把 `headland_turn` 单独限速，并避免机具在大航向误差下入土。

### 直线作业行

作业行应被标为 `work` 段，段内控制目标是稳定横向误差和稳定速度：

- 路径点不只表示几何，还应附带 `segment_id`、`zone=work`、`speed_limit_mps`、机具意图。
- 跟踪器应优先使用段速度上限，再叠加航向误差、横向误差、RTK 质量、前方曲率的实时限速。
- 机具进入作业行前要考虑动作延迟，例如提前降悬挂、延迟接 PTO。

### 地头/边界触发

成熟系统普遍把边界作为自动化触发条件，而不是只靠“到了某个路径点”：

- `headland boundary` 决定开始掉头、结束掉头、端行自动化触发位置。
- `start_turn_offset` 或等价的距离/时间偏置用于补偿机具长度和机械延迟。
- 对播种/喷药这类分段控制，需要按 GPS footprint、已覆盖区域和机械开关延迟决定 section 开关。

### 机具动作延迟

机具不是瞬时动作，计划必须表达“意图”，运行时必须做状态机：

- PTO: 先断开再升机具；接合前检查悬挂到位、速度和航向误差。
- 三点悬挂/液压: 用目标高度、动作方向、预计动作时间和反馈状态闭环。
- 播种/喷药: 用 `turn_on_time/turn_off_time` 或等价的提前距离做延迟补偿。
- 异常: RTK 失效、急停、段外作业、反馈超时都应进入安全态。

## 当前项目现状

已有能力：

- `global_coverage`: 生成覆盖路径，但目前主要输出折线路径点，没有稳定的段语义。
- `waypoint_selector`: 输出前瞻点、`mode`、`in_view_count`，现在已扩展可输出前方转角预判。
- `track_controller`: 输出底盘速度，现在已能基于视野状态和前方转角减速。
- `tillage_controller`: 已有 PTO + 三点悬挂状态机，支持 `work/transit` zone、地块边界自动检测、PTO 先断后升、紧急停止。
- `examples/tillage_operation.yaml`: 已有运动控制链 + 机具控制链的示例。

主要缺口：

- 覆盖规划没有输出正式的作业段/地头段/掉头段语义。
- `tillage_controller` 的 zone 来源偏弱：优先读 `next_point.zone`，但当前规划路径通常没有可靠 zone。
- 机具动作和速度限制没有统一计划源。例如“提前 1.5m 断 PTO”“掉头最高 0.6m/s”“进入作业行前提前降悬挂”还没有结构化表达。
- 缺少机具驱动层：现在 `tillage_cmd` 还是逻辑命令，没有明确映射到真实 PWM/继电器/CAN/ISOBUS。
- 缺少作业结果记录：实际作业覆盖、PTO 开关轨迹、悬挂状态、漏作/重叠还没有统一记录。

## 推荐数据模型

### OperationPlan

规划节点应输出 `operation_plan`，而不是只输出 `global_path`。

示例结构：

```yaml
task_id: task_001
frame: ENU
path:
  points:
    - [x, y]
  segments:
    - id: row_001
      type: work
      start_index: 0
      end_index: 240
      zone: work
      motion:
        speed_limit_mps: 1.2
        preferred_tracker: line
      implement:
        mode: tillage
        pto: on
        hitch: down
        working_depth: 1.0
        engage_offset_m: 1.0
        disengage_offset_m: 1.5
    - id: turn_001
      type: headland_turn
      start_index: 241
      end_index: 310
      zone: transit
      turn_type: u_turn
      motion:
        speed_limit_mps: 0.5
        max_curvature: 0.5
      implement:
        pto: off
        hitch: up
```

这里的字段是“意图”，不是直接执行器命令。真正执行仍由运行时状态机决定。

### ProgressState

应增加一个路径进度节点，避免每个控制器各自推断当前在哪一段。

```yaml
task_id: task_001
segment_id: row_001
segment_type: work
path_index: 128
distance_to_segment_end_m: 12.4
cross_track_error_m: 0.18
heading_error_deg: 3.2
zone: work
upcoming:
  next_segment_type: headland_turn
  distance_m: 12.4
```

这个节点可以由 `pose_enu + operation_plan` 计算，输出给底盘和机具。

### ImplementCommand

机具逻辑命令建议扩展为通用格式，不只服务旋耕。

```yaml
task_id: task_001
implement_type: tillage
state: working
pto:
  enabled: true
  rpm_target: 540
hitch:
  target_height: 1.0
  action: hold
sections:
  enabled: []
rate:
  target: null
safety:
  interlock_ok: true
  reason: ""
```

## 推荐节点图

### V1: 在当前架构上最小可行增强

```text
sim_output.rtk_fix
  -> rtk_filter.filtered_rtk
  -> coord_transform.pose_enu

coord_transform.task_enu
  -> global_coverage.operation_plan
  -> path_progress

global_coverage.operation_plan
  -> waypoint_selector
  -> track_controller
  -> sim_input / chassis_driver

path_progress
  -> track_controller
  -> implement_controller

coord_transform.pose_enu
  -> path_progress
  -> implement_controller

implement_controller
  -> implement_driver
  -> implement_status

implement_status + path_progress + pose_enu
  -> operation_logger / coverage_logger
```

短期可以保留 `global_path`，同时新增 `operation_plan`。`waypoint_selector` 仍可从 `operation_plan.path.points` 取点，但要透传当前段的 `zone/segment_type/speed_limit/implement intent`。

### V1.5: 保留当前节点名的兼容接法

在不大改运行时和已有示例的前提下，可以先用下面的兼容图过渡：

```text
global_coverage.global_path
  -> waypoint_selector.global_path
  -> track_controller.next_point

waypoint_selector.next_point
  -> tillage_controller.next_point

coord_transform.pose_enu
  -> waypoint_selector.pose_enu
  -> track_controller.pose_enu
  -> tillage_controller.pose_enu

coord_transform.task_enu
  -> tillage_controller.task_enu
```

这个版本依赖 `next_point.zone` 和地块边界自动检测，能跑通机具状态机，但语义仍弱。建议只作为验证 PTO/悬挂状态机的过渡方案。

### V1.6: 推荐的最小新增节点

```text
global_coverage.operation_plan
  -> path_progress.operation_plan
  -> waypoint_selector.operation_plan

coord_transform.pose_enu
  -> path_progress.pose_enu
  -> waypoint_selector.pose_enu

path_progress.progress_state
  -> track_controller.path_progress
  -> implement_controller_tillage.path_progress

waypoint_selector.next_point
  -> track_controller.next_point

implement_controller_tillage.implement_cmd
  -> implement_driver_sim / implement_driver_gpio / implement_driver_can

implement_driver_*.implement_status
  -> implement_controller_tillage.implement_feedback
  -> operation_logger
```

这里的关键变化是新增 `path_progress`。底盘和机具不再各自猜“现在在哪一段”，而是共享同一个路径进度结果。

### V2: 地头/掉头专用规划

把 `global_coverage` 拆成更清晰的阶段：

- `field_decomposer`: 地块、障碍物、地头区、作业区。
- `swath_generator`: 作业行生成。
- `route_planner`: 作业行排序。
- `headland_turn_planner`: 连接相邻作业行，生成 U-turn/bulb/fishtail/Reeds-Shepp/Bezier/NURBS 等可跟踪轨迹。
- `operation_annotator`: 给每段标注 `work/transit/headland_turn`、速度限制和机具意图。

这更接近 Fields2Cover/Fields2Benchmark 的模块化路线，也更方便以后替换算法。

## 节点职责边界

### `global_coverage`

短期继续生成 `global_path`，但新增 `operation_plan`：

- 输入: `task_enu`、车辆/机具宽度、重叠率、地头宽度、最小转弯半径。
- 输出: `operation_plan.path.points`、`segments`、`path_zones`、任务元数据。
- 不直接输出 PTO/继电器命令，只输出机具意图和触发偏置。

### `path_progress`

新增运行时节点：

- 输入: `operation_plan`、`pose_enu`。
- 输出: `segment_id`、`segment_type`、`path_index`、`distance_to_segment_end_m`、`cross_track_error_m`、`heading_error_deg`、`upcoming`。
- 负责把连续 pose 映射到计划段，统一供底盘、机具和日志使用。

### `waypoint_selector`

保留为几何前瞻点选择节点：

- 输入: `operation_plan/global_path`、`pose_enu`。
- 输出: `next_point`，包含 `index`、`mode`、`in_view_count`、前方转角预判。
- 逐步从 `global_path` 迁移到 `operation_plan.path.points`，并透传段语义。

### `track_controller`

只负责底盘速度，不直接管机具：

- 输入: `pose_enu`、`next_point`、`path_progress`。
- 输出: `velocity_cmd`。
- 限速来源优先级建议为：安全仲裁 > 段速度上限 > 前方转角/视野状态 > 距离目标点减速。

### `implement_controller_tillage`

从现有 `tillage_controller` 演进而来：

- 输入: `operation_plan`、`path_progress`、`pose_enu`、`implement_feedback`、`safety_state`。
- 输出: 通用 `implement_cmd`，例如 PTO、悬挂目标高度、作业状态。
- 只做机具逻辑状态机，不直接操作 GPIO/PWM/CAN。

### `implement_driver_*`

执行器适配层：

- `implement_driver_sim`: 仿真驱动，方便在 GUI 里看 PTO/hitch。
- `implement_driver_gpio`: 树莓派/工控机 GPIO、继电器、电推杆。
- `implement_driver_can`: CAN 或 ISOBUS 适配。
- 输出统一 `implement_status`，给控制器做闭环和故障判断。

## G-code 式计划 vs 反应式控制

### 纯 G-code 式

优点：

- 可复盘、可审计。
- 易于云端下发和离线检查。
- 可以提前检查作业覆盖、掉头空间和安全边界。

缺点：

- 农田实际存在滑移、RTK 抖动、执行器延迟、路径跟踪误差。
- “到点开关”在高速/延迟下容易过早或过晚。
- 机具状态无法只按计划假设，例如悬挂未到位、PTO 未反馈、急停。

### 纯反应式

优点：

- 对真实姿态和执行器状态敏感。
- 实现初期简单。

缺点：

- 没有全局意图，容易出现该作业没作业、该抬没抬、地头误作业。
- 难以提前减速和提前抬升。
- 复盘和调参困难。

### 推荐混合式

规划节点确定：

- 哪些段是作业段、地头段、掉头段、转场段。
- 每段的目标速度上限、允许转弯类型、是否可倒车。
- 每段的机具意图：PTO、悬挂、分段、变量率。
- 提前/滞后距离：例如提前 1.5m 断 PTO，进入作业行前 1.0m 降悬挂。

运行时决定：

- 根据实际 `pose_enu` 和路径进度触发状态转换。
- 根据实际掉头角度、曲率、前瞻状态和 cross-track error 限速。
- 根据执行器反馈确认 PTO/悬挂状态。
- 在异常时覆盖计划：急停、升机具、停止底盘。

## 机具控制策略

### 旋耕

推荐规则：

- 作业段: `hitch=down`, `pto=on`, 限速按土壤负载和机具能力配置。
- 地头/掉头段: 先 `pto=off`，确认断开后 `hitch=up`，底盘进入低速掉头。
- 进入下一作业行前: 根据悬挂下降时间和当前速度，提前降悬挂；降到位后延迟接合 PTO。
- 如果 `heading_error` 过大、`mode=approach`、`cross_track_error` 超限: PTO 保持 off 或降速，避免横向硬切土。

建议状态机：

```text
TRANSPORT
  -> PREPARE_LOWER    接近 work 段，且速度/航向/RTK 满足条件
  -> LOWERING         悬挂下降，PTO 保持 off
  -> READY_TO_ENGAGE  悬挂到位，等待 pto_engage_delay
  -> WORKING          PTO on，按作业速度前进
  -> DISENGAGING      接近段尾或进入 headland，PTO off
  -> RAISING          确认 PTO off 后升悬挂
  -> TRANSPORT
```

现有 `tillage_controller` 已经覆盖了 `TRANSPORT/LOWERING/WORKING/RAISING` 的核心骨架，后续主要补 `path_progress` 输入、动作提前量、反馈闭环和故障态。

### 播种/喷药

推荐采用 TC-SC 类似分段逻辑：

- 规划输出作业区和已覆盖区。
- section controller 根据 GPS footprint、重叠率、延迟补偿控制每个 section。
- 支持 `turn_on_time`、`turn_off_time` 或等价的提前距离。

### 通用安全互锁

所有机具节点都应支持：

- 急停时: PTO off、液压/电推杆进入安全位、底盘速度限为 0。
- 无 RTK fixed 或 pose 超时: 机具进入安全状态。
- 作业段外: 默认不允许 PTO on。
- 悬挂未到位: 不允许 PTO on。
- 底盘速度过高或航向误差过大: 禁止下降/接合。

## 下一步实现建议

### 第一阶段: 结构化 plan 和 progress

1. 在 `global_coverage` 输出中新增 `segments` 和 `path_zones`，先不移除 `global_path`。
2. 新增 `path_progress` 节点，统一输出当前段、路径索引、到段尾距离、横向误差、航向误差。
3. 把 `waypoint_selector` 改成从路径索引映射 segment，输出 `zone/segment_type/speed_limit/implement_intent`。
4. 让 `track_controller` 使用 segment speed limit，并保留当前前方转角/视野状态减速。
5. 让 `tillage_controller` 优先使用 `path_progress.segment_type`，其次使用 RTK 边界自动检测。

### 第二阶段: 机具驱动层

新增：

- `implement_driver_pwm`: PWM/继电器/电推杆驱动。
- `implement_driver_can`: 后续 CAN/ISOBUS 适配。
- `implement_feedback`: 采集 PTO、悬挂、电流、限位开关。
- `implement_safety_supervisor`: 跨底盘和机具的安全仲裁。

### 第三阶段: 地头掉头规划

新增或重构：

- `headland_generator`: 生成地头缓冲区。
- `headland_turn_planner`: 按车辆/机具约束生成掉头曲线。
- `operation_annotator`: 统一标注作业段和机具动作。

短期可以先做折线圆角/Bezier 过渡；长期应把车辆最小转弯半径、履带原地转能力、机具外摆包络、障碍物和边界都纳入约束。

## 对当前代码的具体建议

1. 保留 `tillage_controller`，但把它升级为 `implement_controller_tillage`，输入从 `next_point + task_enu` 扩展为 `operation_plan + path_progress + pose_enu + implement_feedback`。
2. 新增通用 `implement_driver`，不要让 `tillage_controller` 直接关心 PWM、继电器或 CAN 细节。
3. `global_coverage` 不只输出点列；至少输出 `path_zones` 和 `segments`。
4. 当前掉头减速逻辑继续放在 `track_controller`，但速度上限应逐步来自 `operation_plan.segment.motion.speed_limit_mps`。
5. `trajectory_viz` 应显示 segment 类型、机具状态、PTO/hitch 轨迹，这对实机调试很重要。

## 实施优先级

建议按风险从低到高做：

1. 保留现有折线路径，先落地 `operation_plan.segments/path_zones` 和 `path_progress`，让机具控制有可靠语义来源。
2. 把 `tillage_operation.yaml` 改成 `path_progress -> tillage_controller` 的链路，验证 PTO/hitch 触发时机。
3. 可视化增加 segment、headland、PTO、hitch、速度限制轨迹。
4. 再做掉头路径圆角/连续曲率，优先在 `headland_turn_planner` 内实现，不要散落到 `waypoint_selector` 或 `track_controller`。
5. 最后接真实驱动层和安全仲裁，实机前必须有急停、RTK 超时、反馈超时和段外禁止作业。

## 参考资料

- John Deere AutoTrac Turn Automation: field/headland boundary 是自动掉头基础，地头边界也作为速度和机具升降等端行功能触发。
  https://www.deere.com/en/technology-products/precision-ag-technology/guidance/auto-trac-turn-automation/
- John Deere display help: AutoTrac Turn Automation coordinates machine and implement functions during end turns，并包含 speed control、equipment control 设置。
  https://displaysimulator.deere.com/onscreen_help/S7combine/current/en/autotrac_turn_automation/autotrac_turn_automation.htm
- Fields2Cover route planning 文档: 把 swath、route、headland path 分开处理，示例中使用机宽倍数生成地头空间。
  https://fields2cover.github.io/source/tutorials/route_planning.html
- Headland turning optimisation for agricultural vehicles and those with towed implements: 地头掉头优化需考虑车辆/机具运动学、地形和地头几何约束，可生成 bulb/fishtail/拖挂场景轨迹。
  https://www.sciencedirect.com/science/article/pii/S2666154319300092
- Fields2Benchmark: 将农业覆盖路径规划拆成 field decomposition、headland generation、swath generation、route planning、path planning 等可替换模块。
  https://www.sciencedirect.com/science/article/pii/S2772375525003880
- AEF ISOBUS Task Controller 功能说明: TC-BAS、TC-GEO、TC-SC 分别对应任务记录、地理位置控制/记录、分段控制。
  https://www.aef-online.org/aef-tour-it/
