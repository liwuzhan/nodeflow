# 规划仿真闭环流程诊断报告

**诊断对象**: NodeFlow 规划仿真工作流 (`examples/planning_simulation.yaml`)
**涉及模块**: `node-hub`, `simulator`, `runtime`
**诊断日期**: 2025-12-26

## 1. 严重性问题 (Critical)

### 1.1 运动控制卡顿风险 (Stuttering Motion)

*   **问题描述**: 机器人运动可能出现频繁的“急停-起步”现象，导致运动不流畅。
*   **位置**: [sim_input/run.py](file:///Users/wuzhanli/Desktop/node/node-hub/sim_input/run.py)
*   **根本原因**:
    *   `sim_input` 节点采用“无新数据即停止”的激进安全策略。
    *   `recv_latest()` 仅在检测到序列号增加时返回数据，否则返回 `None`。
    *   `track_controller` 和 `sim_input` 虽同频 (50Hz) 但相位不同步。当 `sim_input` 运行稍快连续读取两次时，第二次会因无新数据而触发 `_send_velocity_command(0, 0)`。
*   **修复建议**: 引入指令超时机制（Watchdog）。仅当连续 `N` 帧（如 0.5秒）未收到新指令时才发送停机命令。

## 2. 架构缺陷 (Major)

### 2.1 硬编码依赖破坏拓扑灵活性

*   **问题描述**: 控制器节点无法通过 YAML 配置文件重定向输入源，必须修改代码才能连接不同上游。
*   **位置**: [track_controller/run.py](file:///Users/wuzhanli/Desktop/node/node-hub/track_controller/run.py)
*   **代码证据**:
    ```python
    # 错误用法：直接硬编码上游 Buffer 名称
    buf_rtk = SharedBufferLite("rtk_filter.filtered_rtk", create=False)
    ```
*   **影响**: 这违反了 NodeFlow 的“端口映射”设计原则。如果在 YAML 中将 `rtk_filter` 替换为其他滤波节点（如 `ekf_node`），`track_controller` 将因找不到 Buffer 而失效。
*   **修复建议**: 移除 `SharedBufferLite` 的直接调用，完全使用 `sdk.create_input_port("filtered_rtk")`，让 Runtime 处理连接逻辑。

## 3. 潜在逻辑错误 (Minor)

### 3.1 坐标系与航向控制风险

*   **问题描述**: 航向控制逻辑依赖于脆弱的符号取反操作，可能在坐标系定义微调后导致反向旋转。
*   **位置**: [track_controller/run.py](file:///Users/wuzhanli/Desktop/node/node-hub/track_controller/run.py)
*   **分析**:
    *   控制器计算方位角误差 `err`（通常基于地理北极顺时针）。
    *   仿真器接收角速度 `w`（通常基于数学极坐标逆时针）。
    *   当前代码通过 `w = -kp * err` 简单取反来适配，缺乏明确的坐标系转换层。

### 3.2 启动竞态条件 (Race Condition)

*   **问题描述**: 仿真器未就绪时，系统会基于错误的默认地块进行规划。
*   **位置**: [sim_output/run.py](file:///Users/wuzhanli/Desktop/node/node-hub/sim_output/run.py)
*   **流程**:
    1. `sim_output` 初始化时连接失败 → 回退到默认 100x200 矩形地块。
    2. `global_coverage` 接收默认地块 → 开始规划。
    3. `sim_output` 后续连上仿真器 → 发送真实地块。
    4. `global_coverage` 重新规划。
*   **影响**: 浪费计算资源，且日志中会包含误导性的规划信息。

## 4. 修复计划建议

建议按以下顺序实施修复：

1.  **P0**: 修复 `sim_input` 的看门狗逻辑，防止机器人运动卡顿。
2.  **P1**: 重构 `track_controller`，去除硬编码依赖，恢复架构灵活性。
3.  **P2**: 优化 `sim_output` 的启动逻辑，增加对仿真器连接的等待机制。

---
*报告生成工具: Gemini 2.0 Pro Analysis*
