# NodeFlow 会话工作总结

日期：2026-05-29

## 1. 本轮目标

本轮围绕仿真复盘、掉头问题、机具覆盖、CLI 可调试性和后续边缘侧上车准备推进。用户明确否决了“语义健康检查插件”和“验证级别体系”两类过度抽象，因此本轮只保留可直接验证、可独立测试的工程改动。

## 2. 已完成的代码修复

### Runtime 启动顺序

- 修复 `NodeFlowRuntime.run()` 传统模式中 `self.running` 设置过晚的问题。
- `start_dataflow()` 会使用 `should_cancel=lambda: not self.running` 判断启动是否取消，因此传统 `run()` 必须先进入 running 状态。
- 补充传统启动路径单测，防止再次出现启动前即取消 dataflow 的问题。

### 机具控制与覆盖率

- 调整 `tillage_controller` 状态机优先级：
  - `final` 最高，必须升起并停 PTO。
  - 明确机具意图 `pto:on` 或 `hitch:down` 时优先进入/保持作业。
  - 明确 `pto:off` 或 `hitch:up` 时升起。
  - 没有明确意图时才回退到 zone 判定。
- 修复 emergency stop、TRANSPORT、LOWERING 状态下 `pto_rpm` 未清零的问题。
- 增加连续 work zone、机具意图覆盖 transit zone、final 覆盖作业意图的单测。

### 掉头控制

- 在 `track_controller` 中启用 `headland_turn` 专用控制分支。
- 当 `path_progress.segment_type == headland_turn` 且有 `path_heading_rad` 时，控制器不再只追目标点坐标，而是按路径切线航向闭环。
- 航向误差大时进入 `turn_align`，线速度为 0，保留完整角速度用于原地对齐。
- 航向基本对齐后进入 `headland_turn`，按低速因子和段限速前进。
- 输出 `target_mode`、`headland_turn`、`heading_error_deg` 等字段，方便可视化和黑匣子复盘确认新控制分支是否生效。

### 可视化与复盘

- `trajectory_viz` 覆盖复盘新增：
  - `active_segments`
  - `sample_count`
  - `working_sample_count`
  - `working_sample_percent`
  - `latest_active`
  - 最新机具状态、PTO、悬挂高度
- Web 面板显示覆盖率、覆盖面积、活动段数、工作采样数/总采样数和当前覆盖是否激活。
- 修复前端指标显示中 `0` 被当成 `--` 的问题，避免 0 覆盖率和无数据混淆。

### CLI 调试工具

- `health flow --json` 新增 `runtime_running` 字段。
- Runtime 未运行时新增：
  - `reason: runtime_not_running`
  - 明确说明大量 `MISSING` 只代表 dataflow 未启动，不应直接判定为图配置损坏。
- 缺失 buffer 目录时不再直接报错，而是按配置列出预期 buffer 并返回结构化 unhealthy 结果。
- CLI 文档和 `nodeflow-cli-debug` skill 同步更新。

## 3. 已完成的调查和文档

- 新增 `PROJECT_MODULE_AUDIT_REPORT_20260529.md`，汇总 CLI 之外模块的主要风险和修复顺序。
- 按用户反馈明确不推进：
  - 语义健康检查插件。
  - 验证级别体系。
- 本文档记录本轮会话的工作范围、验证结果、边缘侧准备建议和剩余边界。

## 4. 验证结果

本轮已通过以下验证：

- `tests/unit/test_cli_tools.py`
- `tests/unit/test_runtime_run.py`
- `tests/unit/test_tillage_controller.py`
- `tests/unit/test_startup_coordinator.py`
- `tests/unit/test_runtime_cli.py`
- `node-hub/trajectory_viz/test/test_replay_atom.py`
- `node-hub/track_controller/test/test_atom.py`
- `node-hub/waypoint_selector/test/test_atom.py`
- `node-hub/path_progress/test/test_atom.py`
- `node-hub/global_coverage/test/test_operation_plan.py`
- `node-hub/global_coverage/test/test_unit.py`

静态图验证结果：

- `examples/planning_simulation.yaml` 配置有效。
- 图验证有效。
- graph warning 数量为 0。
- 拓扑仍为 8 层：
  - `sim_output`
  - `rtk_filter`
  - `coord_transform`
  - `global_coverage`
  - `path_progress`
  - `waypoint_selector`
  - `tillage_controller`, `track_controller`
  - `sim_input`, `trajectory_viz`

Runtime 当前保持未运行。`health flow` 在未运行状态下返回 `unhealthy` 和退出码 2 是预期行为，JSON 中会明确给出 `runtime_running=false` 与 `reason=runtime_not_running`。

## 5. 现有节点检查结论

项目已有真机相关节点和配置：

- `rtk_driver`：支持 UM982/UMD982，串口/网络，NMEA 解析，双天线航向和天线偏移参数。
- `pwm_driver`：支持香橙派 PWM 输出，接收 `velocity_cmd`，双履带差速映射，包含 dry-run、命令超时和 emergency stop 参数。
- `planning_with_real_rtk.yaml`：真机 RTK 规划控制示例。
- `trajectory_playback.yaml`：轨迹回放控制示例。
- `web_pwm_teleop.yaml`：Web 遥控 PWM 调试示例。
- `tillage_operation.yaml`：运动控制与机具控制链路示例。

因此现有节点已经基本检查过。当前更大的风险不在节点是否存在，而在真机接入后的硬件映射、延迟、参数校准和黑匣子复盘能力。

## 6. 边缘侧硬件判断

用户确认的硬件条件：

- 边侧设备：香橙派 5 Pro。
- 底盘：履带底盘。
- 定位：UM982，田块中基本只有 RTK 可靠。
- 急停：人类 200 米内遥控切断驱动器主电源，不影响香橙派；香橙派由大充电宝隔离供电。
- 电机驱动器：支持 PWM，也支持 485。
- 机具：电液压推杆控制升降；暂无限深传感器；旋耕机驱动电机在旋耕机本体上。

判断：

- 第一阶段不需要 IMU。低价 IMU 在田块颠簸场景下容易引入额外噪声，除非 UM982 航向短时丢失或双天线航向不稳定，再考虑仅做短时补偿。
- 不建议把 485 编码器/轮速当作定位闭环依据。履带在田块中实际位移主要受打滑影响，轮端转速和对地运动关系弱。
- 485 如接入，更适合作为驱动器状态诊断：故障码、母线电压、电机电流、温度、使能状态等。
- 用户提到 485 大约 30ms 延迟，而 PWM 基本无明显链路延迟。现有控制器输出频率较高，第一阶段继续使用 PWM 更符合低延迟控制需求。
- 若未来必须用 485 控制，应在节点层显式处理延迟：降低命令频率、时间戳对齐、命令超时、状态反馈与控制反馈分离，不应简单替换 PWM 输出。

## 7. 上车前建议补充的工具

建议后续补充以下边缘侧工具：

1. `edge doctor`
   - 检查 Python/Node/Codex、依赖、串口权限、PWM sysfs、GPIO/PWM 状态、磁盘、时间同步、网络、CPU 温度。

2. `rtk probe`
   - 直接读取 UM982。
   - 输出 NMEA 类型、RTK FIX/FLOAT、卫星数、航向质量、频率。
   - 可保存原始 NMEA 日志。

3. `pwm bringup/calibrate`
   - 悬空履带测试中位、左右方向、死区、最小动作 PWM、超时回中位。
   - 以 dry-run 和低速模式优先。

4. `blackbox record`
   - 记录 `rtk_fix`、`pose_enu`、`path_progress`、`next_point`、`velocity_cmd`、`pwm_status`、`tillage_status`。
   - 这是田间问题复盘的关键工具。

5. `field replay report`
   - 从黑匣子日志生成路径图和指标。
   - 指标包括最大横向误差、掉头段状态、RTK 状态分布、PWM 输出、覆盖率。

6. 安全 bringup YAML
   - 默认 `pwm_driver.dry_run_mode=true`。
   - 低速限幅 0.1 到 0.2 m/s。
   - 先跑遥控、定位、悬空履带，再跑自动路径。

## 8. 剩余边界

不做更深工具和真机/仿真闭环验证时，目前能从代码、配置、CLI 和单节点测试中明确看到的问题已经基本处理完。剩余风险主要在：

- 真机动力响应和 PWM 映射是否匹配。
- 履带打滑导致控制参数需要田间重新调。
- UM982 双天线安装偏移、航向偏移和天线基线方向是否准确。
- RTK 丢星、FLOAT、航向质量下降时的降级策略。
- 电液压推杆没有限深传感器时，机具状态只能按指令和限位推断，无法精确知道实际入土深度。
- 485 作为控制链路时的 30ms 延迟需要单独建模和测试。

下一步优先级应是边缘侧 bringup 工具和黑匣子复盘，而不是继续增加控制算法抽象。
