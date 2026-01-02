# NodeFlow 规划仿真测试报告

**测试日期**: 2025-12-28
**测试对象**: `examples/planning_simulation.yaml`
**测试工具**: NodeFlow CLI (`tools/cli/core/cli.py`) & Runtime

---

## 1. 测试摘要

本次测试旨在验证 `planning_simulation` 数据流的正确性，并评估 CLI 工具在测试过程中的有效性。测试过程中发现了 Runtime 实现中的 Bug，导致无法完全按照《AI Agent CLI 操作指南》中的守护进程模式进行测试。通过手动启动节点和标准模式运行，验证了核心数据流逻辑的正确性。

## 2. 发现的问题 (Critical Findings)

### 2.1 守护进程模式 (Daemon Mode) 启动失败 ❌
*   **现象**: 执行 `runtime start ... --background` 后，Runtime 进程立即退出。
*   **原因**: `runtime/main.py` 在初始化 `SharedBufferLite` 时传递了错误的参数 `buffer_size`，而 `SharedBufferLite.__init__` 只接受 `size` 参数。
*   **错误日志**:
    ```
    ERROR - Failed to create control buffer: SharedBufferLite.__init__() got an unexpected keyword argument 'buffer_size'
    ```
*   **影响**: 无法使用 CLI 的 `start-dataflow` / `stop-dataflow` 动态控制功能，SOP-0.5 流程受阻。

### 2.2 部分节点在 Runtime 中启动失败 ❌
*   **现象**: 在标准模式 (`python3 -m runtime.main`) 下，`coord_transform` 和 `track_controller` 节点未能正常工作（`seq=0`，进程不存在）。
*   **原因**: 节点进程崩溃，手动调试显示 `ValueError: Input port ... not configured`。这表明 Runtime 未能正确为这些节点设置输入端口的环境变量 (`NODE_IN_<port>`)。
*   **对比**: `sim_output` 和 `rtk_filter` 能够正常启动和运行。

## 3. 数据流验证结果 (Verification Results)

尽管 Runtime 存在启动问题，通过手动设置环境变量并启动节点，验证了 L3/L4 重构后的代码逻辑是正确的。

### 3.1 节点运行状态
| 节点 | 状态 (Manual) | 说明 |
| :--- | :--- | :--- |
| **sim_output** | ✅ OK | 正常输出 `rtk_fix` (seq > 2000), `task_enu` |
| **rtk_filter** | ✅ OK | 正常接收并滤波，输出 `filtered_rtk` |
| **coord_transform** | ✅ OK (手动) | 能够接收 `task_enu` 和 `filtered_rtk`，输出 `pose_enu` |
| **waypoint_selector** | ✅ OK | 接收 `pose_enu`，输出 `next_point` (seq > 1000) |
| **track_controller** | ✅ OK (手动) | 接收 `pose_enu` 和 `next_point`，输出 `velocity_cmd` |

### 3.2 关键数据检查
*   **GPS 参考点**: `sim_output.task_enu` 正确输出了参考点 (121.500490, 31.202056)。
*   **坐标转换**: `coord_transform` 成功将 WGS84 坐标转换为 ENU 坐标，数据流未断裂。
*   **控制指令**: `track_controller` 能够根据路径生成非零的速度指令。

## 4. 建议与后续行动

1.  **修复 Runtime Bug**:
    *   修正 `runtime/main.py` 中 `SharedBufferLite` 的实例化代码，将 `buffer_size` 改为 `size`。
    *   排查 `NodeLauncher` 或 `StartupCoordinator`，确保为所有节点正确注入 `NODE_IN_` 环境变量。

2.  **完善 CLI 工具**:
    *   当前 `buffer inspect` 和 `health` 命令非常有效，帮助快速定位了断点。
    *   建议增加 `runtime logs <node_id>` 命令，以便在 Runtime 吞没子进程 stdout/stderr 时能查看节点日志。

3.  **测试策略调整**:
    *   在 Runtime 修复前，建议使用集成测试脚本（类似手动启动流程）来验证业务逻辑，而非依赖 Runtime 的自动编排。

---
**测试员**: Trae AI
**状态**: ⚠️ 数据流逻辑验证通过，Runtime 基础设施需修复
