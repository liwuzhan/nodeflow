# 模块审阅报告：edge/nodes（节点库）

> 审阅日期: 2026-08-03 | 审阅方式: 代码审阅 + 关键点脚本验证 | 存放: docs/Flesh_Test/（临时）
> **v2 定级注记**: 按上机边界重新评定后：P0-1（farm_coverage_viz）降为**失效旧节点**（不在现有作业图，非系统 P0）；P1-2（高德密钥）降为**仓库治理**（不阻断农机运动测试，应轮换密钥）；P1-3/4（rtk 字段双轨）降为**契约治理**（主链 rtk_filter/coord_transform 已兼容两种命名，不导致真实 RTK 取零）；P1-6（trajectory_viz 可选端口）主仿真图与真实 RTK 图已连接全部端口，不阻断；布尔参数项（原 P2）经核实为主链路 YAML→json 往返保持原生 bool，**判定不成立**，降为注释性风险。详细映射见汇总报告第零节。

## 1. 模块职责

NodeFlow 节点库：8 个分类目录、26 个已实现节点包（约 18,200 行 Python），覆盖控制、机具、I/O、定位、观测、规划、感知。

| 子目录 | 节点数 | 行数 | node.yaml | 测试 |
|---|---|---|---|---|
| control | 2 | 1,155 | 2/2 | 1 |
| implement | 1 | 570 | 1/1 | 1 |
| io | 2 | 1,015 | 2/2 | 1 |
| localization | 1 | 532 | 1/1 | 1 |
| observability | 11 | 5,094 | 11/11 | 12 |
| planning | 5 | 7,466 | 5/5 | 20 |
| sensing | 4 | 2,366 | 3/4 | 1 |
| **合计** | **26** | **≈18,200** | **25/26** | **38** |

**异常项**: `sensing/network_input/` 仅 requirements.txt（未实现）；`simulation/` 空目录；`planning/global_coverage/utils/contour_spiral.py`（1,383 行）与 `scan_utils.py`（1,374 行）为仓库最大算法文件。

## 2. 核心节点

| 节点 | 功能 |
|---|---|
| track_controller | 履带底盘 ENU 轨迹跟踪（200Hz），视野/模式/转角/横向误差/段限速五重速度因子 + ControlSafetyGuard |
| arc_tracker | 贝塞尔路径 Pure Pursuit 弧线跟踪 |
| tillage_controller | 旋耕 PTO + 三点悬挂 5 状态机（TRANSPORT/LOWERING/WORKING/RAISING） |
| waypoint_selector | 视野区域前瞻点选择 v2.0（含 path_progress 前瞻目标） |
| global_coverage | 全覆盖规划（parallel + contour_spiral G2 clothoid） |
| path_progress | 位姿投影到 operation_plan 段语义 |
| coord_transform | WGS84→ENU 网关（参考点热更新） |
| rtk_driver / rtk_filter | RTK 驱动（串口/TCP/UDP + NMEA 解析）/ EMA 平滑 |
| trajectory_viz | 实时轨迹 Web 复盘（v2.1，维护最好的节点） |
| sim_output / sim_input | 仿真器 ZMQ 对接（统一传感器输出 / 控制命令回写 + 看门狗） |

## 3. 发现的问题

### P0（致命，节点无法运行）

1. **farm_coverage_viz 调用不存在的 SDK 方法**（已验证）：`sdk.send(...)` / `sdk.recv_latest(...)` 在 NodeFlowSDK 中不存在（SDK 只有 create_input_port/create_output_port），启动即 AttributeError。`edge/nodes/observability/farm_coverage_viz/run.py:397,417,452,468-469`。

### P1（高）

2. **高德 API 密钥硬编码并已提交 git**：`planning/parcel_planner/config.json:2-3`（amap_api_key + amap_security_code 明文入库）。
3. **rtk 字段命名双轨制导致下游取数错误**：`rtk_driver` 输出 `lat/lon`（run.py:360-369），仿真器 `sensors.py:173-174` 输出 `latitude/longitude`；`velocity_controller` 只读后者（run.py:229-230）——若其 rtk_fix 接 rtk_driver，坐标恒为 0，控制失效。
4. **sim_output schema 与实际数据不符**（已验证）：schema 声明 `lat/lon/alt/satellites/rtk_status:int`，实际发送 `latitude/longitude/altitude/num_satellites/rtk_status:"FIXED"`。开启 `NODE_SCHEMA_VALIDATION=strict` 即全部拒绝。当前靠校验默认关闭"恰好能跑"，是装饰性假契约。
5. **sim_input cleanup 空指针崩溃**：ZMQ 连接失败后 `self.socket` 为 None，`cleanup()` 直接 `.close()` 抛 AttributeError（io/sim_input/run.py:298-299）。
6. **trajectory_viz 端口"可选"声明与实现不一致**（已验证）：node.yaml 描述 operation_plan/next_point/velocity_cmd/path_progress/tillage_cmd/tillage_status 可选，但 run.py 只有 tillage_cmd/tillage_status 走 try/except（create_optional_input_port），其余 4 个无条件 create_input_port——图中未连接即启动 ValueError。
7. **e2e 引用不存在的 `simulator/server.py`**（已通过静态检查确认路径为 simulation/server.py，但 tests/e2e_test_planning_simulation.py 引用旧路径——见 tests 报告）。

### P2（中，摘选）

- **布尔参数字符串转换错误**（已验证 C4）：`bool("false")==True`，track_controller:99、tillage_controller:92,99、waypoint_selector:102、pwm_driver:52,57-58 等参数经 CLI 字符串传入时逻辑反转。
- 参数默认值与 node.yaml 漂移：track_controller `decel_start_dist` 2.0 vs 声明 3.0；waypoint_selector `progress_sync_max_cross_track_m` 6.0 vs 12.0。
- `sim_input` 使用未声明参数 `watchdog_timeout_sec`（node.yaml 未定义）。
- 调试残留：rtk_filter/run.py:21-46 大段注释思考过程；global_coverage/run.py:343 `if True:` 死条件。
- `idle_detector`/`shutdown_manager` 硬编码 `SharedBufferLite("control.shutdown_request", create=True)` 直写框架内部 buffer，create=True 截断已有数据。
- logger 节点 pickle 反序列化不安全（RCE 风险）。
- 无效 sys.path 注入（`observability/controller/run.py:14` 指向 edge/nodes 而非 edge）。
- 端口类型声明宽松：`velocity_controller.velocity_cmd` 声明 json 但下游为 control.velocity。

## 4. 端口一致性结论

**主链路一致**：sim_output/rtk_driver → coord_transform → global_coverage → waypoint_selector/path_progress → track_controller → pwm_driver/sim_input，字段与类型全部匹配（含 rtk_status 字符串 vs int 的差异已在字段层兼容）。

**风险集中**：rtk 字段命名双轨制（lat/lon vs latitude/longitude）、旧 demo 链路（controller/pwm_controller/velocity_controller）类型漂移、sim_output schema 假契约、path_progress 输出端口名 `progress_state` 与消费端 `path_progress` 不对称（P2）。

## 5. 总体评价

**优点**: L3/L4 分层贯彻良好——主链路节点（track_controller、waypoint_selector、path_progress、coord_transform、tillage_controller、arc_tracker）均将算法放入 `atom.py` 纯函数层，run.py 只做数据搬运，且核心节点几乎全部有 atom 单元测试。

**主要风险**: observability 目录质量参差（trajectory_viz 维护最好，其余多为旧 demo）；安全基线薄弱（API 密钥入库、HTTP 默认 0.0.0.0、pickle 持久化）；sensing 节点（sim_output/sim_input/rtk_driver）主循环无测试。

**建议优先修复**: P0-1（farm_coverage_viz 重写为 SDK API 或移入 archive）、P1-2（密钥移出 git）、P1-3/4（统一 rtk 字段命名 + schema 对齐实际数据）、P1-6（trajectory_viz 可选端口全部走 create_optional_input_port）。
