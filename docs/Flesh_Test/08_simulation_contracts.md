# 模块审阅报告：simulation（仿真器）+ contracts（数据契约）

> 审阅日期: 2026-08-03 | 审阅方式: 代码审阅 + 关键点脚本验证 | 存放: docs/Flesh_Test/（临时）
> **v2 定级注记**: 按上机边界重新评定后：P1 #1（零速停车）缺陷成立但触发条件限定（需先 motor 模式再切 velocity(0,0)），当前仿真图只走 velocity 链路，不推翻已通过的 preflight，也不等同真实 PWM 停车失效 → 降为**非上机阻断**；P1 #3（RTK 概率硬编码）为配置治理。详细映射见汇总报告第零节。

## 1. 模块职责

农田仿真器：ZMQ REQ/REP 服务端 + 传感器/物理/地块模型，通过 sim_output/sim_input 节点与 NodeFlow 闭环对接。contracts/task.py 为云边共享的任务状态机契约。

| 文件 | 行数 | 职责 |
|---|---|---|
| `server.py` | 594 | ZMQ 服务端（端口 5555），仿真线程 + 请求线程，RTK 限流 |
| `physics.py` | 379 | KinematicsEngine（油门/转向 + 速度控制双模式、打滑、噪声、机具阻力） |
| `sensors.py` | 362 | GPS/RTK/IMU/里程计/LiDAR 噪声模型（RTK 四状态：FIXED 85%/FLOAT 10%/SINGLE 4%/NONE 1%） |
| `field_generator.py` | 260 | 矩形/不规则地块、障碍物、孔洞 |
| `state.py` | 176 | RobotState + StateHistory（线性插值回放） |
| `utils/coordinates.py` | 100 | 米 ↔ WGS84（与 edge 侧 geo.py 重复实现） |
| `utils/random_parcel_generator.py` | 415 | 随机地块 GeoJSON 生成（独立工具） |
| `config.yaml` | 141 | 田地/运动学/传感器/RTK/服务器配置 |
| `contracts/task.py` | 74 | TaskState 10 状态 + PlanningMode/FallbackPolicy + PROTOCOL_VERSION + `can_transition_task_state` |

**simulation 核心 10 文件 2,778 行；contracts 2 文件 78 行。**

## 2. 协议与契约

- **ZMQ 协议**: `{"type": get_sensor|set_actuator|get_state|get_field|refresh_field|reset|get_config, ...}`；get_sensor 支持 gps/rtk_gps/imu/odometry；RTK 50Hz 限流（被限返回 data:null + note）；set_actuator velocity/motor/implement。
- **坐标系**: 仿真器 yaw=0 指向 +X（东）、CCW 正（数学系）；sensors 输出 heading = (90−yaw_deg) mod 360（地理系）与 edge 侧 geo.py 一致——**坐标系本身自洽**。
- **状态机契约**: cloud 侧 mqtt_client.py:169 强制执行 `can_transition_task_state`；agent 侧 store.py 不校验（不对称，见 agent 报告 C15）。

## 3. 发现的问题

### P1（高）

| # | 位置 | 问题 |
|---|---|---|
| 1 | `physics.py:205` | **控制模式回退导致"零速命令不能停车"**：`step()` 以 `abs(v)>1e-6 or abs(w)>1e-6` 判断模式。先发过 motor 命令（throttle=0.5），再用 velocity(0,0) 停车会回退到油门模式并沿用残留 throttle → 机器人继续加速。sim_input 看门狗零速命令可能失效。**农机安全隐患**。 |
| 2 | `server.py:278` | **REQ/REP 服务端单点崩溃风险**：`recv_json(NOBLOCK)` 只捕获 zmq.Again；畸形 JSON 逃逸到外层直接 `finally: self.stop()` 关闭整个服务端；REP 未 send 则状态机卡死。 |
| 3 | `sensors.py:51,66-80` | **RTK 概率配置被硬编码、config 死键**：`rtk_failure_probability` 从未使用；0.85/0.10/0.04/0.01 硬编码；config.yaml 声明的 fixed_ratio/float_ratio/single_ratio/none_ratio 从未被读取（已验证 C10 侧证）。 |
| 4 | `state.py:46` | **sim_time 语义混乱**：初值 = time.time() 墙钟 epoch（1.7e9 量级）随后按 dt 累加；RTK 限流用墙钟 → `--no-realtime` 加速模式下语义错误。 |
| 5 | `edge/nodes/sensing/sim_output/run.py:29-70` | **sim_output schema 与真实数据契约不符**（与 nodes 报告 P1 #4 同源）：RTKFix lat/lon vs 仿真器 latitude/longitude；IMUData、Odometry 同样结构性不符。靠校验默认关闭才"恰好能跑"。 |
| 6 | `edge/agent/store.py:65-78` | edge 侧状态机无转移校验（契约不对称，详见 agent 报告 C15）。 |
| 7 | `edge/agent/agent.py:220-231` | 取消竞态覆盖终态（详见 agent 报告 P1-3）。 |

### P2（摘选）

- `state.py:138` StateHistory 用 list+pop(0) O(n) 出队（应改 deque）。
- `server.py:520-532` `_reset()` 重置到 (0,0) 而非入口位姿；不重置 RTK 计数/种子。
- sim_input 无重连机制（对比 sim_output 有 _reconnect）。
- sim_output 每帧冗余轮询 get_state（enable_state=false 时仍 20Hz 轮询）。
- 跨模块硬编码耦合：physics.py:166 `hitch_speed=1.5` 注释"与 tillage_controller 匹配"；physics.py:55 `implement_drag_full=0.3` 不可配置；server.py:413 手写 3.14159。
- `simulation/tests/test_integration.py` 与 config 直接矛盾（20Hz vs 50Hz、state["vx"] vs 嵌套结构）——见 tests 报告。

## 4. 验证记录（自写脚本实测）

| 检查项 | 结果 |
|---|---|
| C10: config.yaml rtk.frequency=50.0，test_integration.py 断言 18-22Hz | **矛盾确认**（测试必失败） |
| C12: contracts 状态机转移表正确（RUNNING→COMPLETED 合法、终态不可回退） | **通过** |
| C5: sim_output RTKFix schema（lat/lon/alt/satellites）vs 仿真器实际（latitude/longitude/num_satellites） | **矛盾确认** |

## 5. 总体评价

**优点**: 仿真器 ZMQ REQ/REP 闭环设计清晰（simulation → sim_output → 规划/控制节点 → sim_input → simulation）；RTK 四状态概率分布贴近实机；坐标系约定与 edge 侧完全对齐；任务状态机契约有显式转移表并被 cloud 侧强制。

**主要风险**: ① physics 模式回退导致零速停车失效（P1 #1，安全隐患）；② sim_output schema 假契约（校验一开全线崩溃）；③ RTK 概率硬编码与 config 声明脱节。

**建议优先修复**: P1 #1（显式记录当前模式而非按值推断）、P1 #2（REP 异常时 send 错误响应）、P1 #3（sensors 读取 config.yaml 的 ratio）、P1 #5（schema 与仿真器输出对齐）。
