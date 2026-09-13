# 父进程监控机制 (Parent Process Watchdog)

## 版本信息
- **文档版本**: 1.0
- **创建日期**: 2025-12-29
- **作者**: NodeFlow Team
- **适用版本**: NodeFlow SDK v0.2+

---

## 1. 功能概述

**父进程监控（Parent Process Watchdog）** 是 NodeFlow SDK 的内置功能，用于解决**孤儿进程（orphan process）**问题。

### 1.1 问题背景

在之前的实现中，当运行时框架（Runtime）被强制杀死时（如 `kill -9`），节点进程会变成孤儿进程继续运行：

```
Runtime (PID 1000)
    └── Node A (PID 2000)
    └── Node B (PID 3000)

[执行 kill -9 1000]

init (PID 1)
    ├── Node A (PID 2000)  ← 孤儿进程，继续运行
    └── Node B (PID 3000)  ← 孤儿进程，继续运行
```

这会导致：
- 节点进程无法被正常清理
- 占用系统资源（内存、共享缓冲区、ZMQ socket）
- 调试时需要手动查找并杀死所有节点进程

### 1.2 解决方案

SDK 自动启动一个后台守护线程，定期检测父进程（Runtime）是否存活：

- **Unix/macOS**: 当父进程死亡时，子进程的 PPID 变为 1（init/launchd）
- **检测机制**: 每 1 秒检查一次 `os.getppid()`
- **自动退出**: 检测到父进程死亡后，节点立即退出（`os._exit(1)`）

---

## 2. 工作原理

### 2.1 技术实现

```python
class ParentProcessWatchdog:
    """父进程监控守护线程"""

    def __init__(self, node_id: str, check_interval: float = 1.0):
        self.node_id = node_id
        self.check_interval = check_interval
        self.initial_ppid = os.getppid()  # 记录初始父进程ID

    def _monitor_loop(self):
        """监控循环"""
        while self.running:
            time.sleep(self.check_interval)
            current_ppid = os.getppid()

            # 检测父进程是否死亡
            if current_ppid == 1:
                logger.warning(f"Parent process death detected, exiting...")
                os._exit(1)  # 立即退出
```

### 2.2 生命周期

```
1. SDK 初始化
   └── ParentProcessWatchdog 创建
       └── 记录初始 PPID

2. SDK 启动
   └── 后台线程启动
       └── 每 1 秒检查一次 PPID

3. 父进程存活
   └── PPID = 初始值
       └── 继续运行

4. 父进程死亡
   └── PPID = 1 (init)
       └── 节点立即退出
```

### 2.3 退出方式

使用 `os._exit(1)` 而非 `sys.exit()`：

- `os._exit()`: 立即终止进程，不调用任何 cleanup handlers
- `sys.exit()`: 抛出 SystemExit 异常，可能被 try-except 捕获
- 保证节点在检测到父进程死亡后立即退出，不被延迟

---

## 3. 使用方法

### 3.1 自动启用（默认）

父进程监控在所有使用 `NodeFlowSDK` 的节点中**自动启用**：

```python
from sdk.nodeflow_sdk import NodeFlowSDK

# 自动启用父进程监控
sdk = NodeFlowSDK(log_level="INFO")

# 节点逻辑...
```

日志输出示例：

```
2025-12-29 22:28:25 - nodeflow.node - INFO - NodeFlow SDK initialized for node 'my_node'
2025-12-29 22:28:25 - nodeflow.sdk.nodeflow_sdk - INFO - ParentProcessWatchdog started for 'my_node'
2025-12-29 22:28:25 - nodeflow.node - INFO - Parent process watchdog enabled (interval=1.0s)
```

### 3.2 禁用监控（可选）

如果需要禁用父进程监控（仅用于特殊测试场景）：

#### 方法1：代码参数

```python
sdk = NodeFlowSDK(log_level="INFO", enable_parent_watchdog=False)
```

#### 方法2：环境变量

```bash
export NODE_PARENT_WATCHDOG=false
python3 my_node.py
```

支持的禁用值：`false`, `0`, `no`, `off`

### 3.3 自定义检查间隔

默认检查间隔为 1.0 秒。可通过环境变量调整：

```bash
# 设置为 0.5 秒检查一次
export NODE_WATCHDOG_INTERVAL=0.5
python3 my_node.py
```

---

## 4. 测试验证

### 4.1 端到端测试

验证父进程监控功能的完整测试流程：

```python
#!/usr/bin/env python3
"""
测试步骤：
1. 启动模拟 Runtime 进程
2. Runtime 启动 Node 子进程
3. 杀死 Runtime (SIGKILL)
4. 验证 Node 在 1-2 秒内自动退出
"""

import os
import sys
import time
import signal
import subprocess

def test_watchdog():
    # 1. 启动 Runtime
    runtime = subprocess.Popen([sys.executable, "runtime/main.py", "config.yaml"])

    # 2. 等待初始化
    time.sleep(3)

    # 3. 杀死 Runtime
    print(f"Killing Runtime {runtime.pid}...")
    os.kill(runtime.pid, signal.SIGKILL)

    # 4. 检查节点是否退出
    time.sleep(2)

    # 5. 验证没有孤儿进程
    result = subprocess.run(
        ["ps", "aux"],
        capture_output=True,
        text=True
    )

    if "nodeflow" in result.stdout:
        print("❌ FAILED: Orphan processes found")
    else:
        print("✓ PASSED: All nodes exited cleanly")

if __name__ == '__main__':
    test_watchdog()
```

### 4.2 预期行为

**正常场景**：

```
[Runtime 1000] Starting nodes...
[Node 2000] Started, parent=1000
[Node 2000] Alive, ppid=1000
[Node 2000] Alive, ppid=1000
[Runtime 1000 killed with SIGKILL]
[Node 2000] Parent process death detected (ppid=1 → init), exiting...
[Node 2000] Exit code: 1
```

**时序验证**：

| 时间 | 事件 | PPID | 状态 |
|------|------|------|------|
| T+0s | Node 启动 | 1000 | Running |
| T+2s | Runtime 被杀死 | 1000 → 1 | Parent dead |
| T+3s | Watchdog 检测到 | 1 | Detected |
| T+3s | Node 退出 | - | Exited |

---

## 5. 故障排查

### 5.1 节点没有自动退出

**症状**: 杀死 Runtime 后，节点进程仍然存活

**可能原因**：

1. **监控被禁用**

   检查日志是否包含：
   ```
   INFO - Parent process watchdog disabled
   ```

   解决方案：
   ```bash
   unset NODE_PARENT_WATCHDOG  # 清除禁用环境变量
   ```

2. **检查间隔过长**

   ```bash
   echo $NODE_WATCHDOG_INTERVAL  # 检查间隔设置
   export NODE_WATCHDOG_INTERVAL=1.0  # 设置为1秒
   ```

3. **节点代码捕获了退出**

   检查节点代码是否有：
   ```python
   try:
       # 节点逻辑
   except SystemExit:
       pass  # ❌ 不要捕获 SystemExit
   ```

### 5.2 检查运行中的节点

查看节点的父进程状态：

```bash
# 查看节点进程
ps -ef | grep nodeflow

# 输出示例：
# user  2000  1000  ... python3 my_node.py    # PPID=1000 (Runtime)
# user  3000  1000  ... python3 other_node.py # PPID=1000 (Runtime)

# 杀死 Runtime 后
ps -ef | grep nodeflow

# 预期输出：
# (无输出，所有节点已退出)

# 如果看到：
# user  2000  1  ... python3 my_node.py    # PPID=1 (orphan)
# 说明监控未生效
```

### 5.3 日志分析

**正常日志**：

```
2025-12-29 22:28:25 - nodeflow.sdk.nodeflow_sdk - INFO - ParentProcessWatchdog started for 'my_node'
2025-12-29 22:28:25 - nodeflow.node - INFO - Parent process watchdog enabled (interval=1.0s)
[... 节点正常运行 ...]
2025-12-29 22:30:15 - nodeflow.sdk.nodeflow_sdk - WARNING - Node 'my_node' detected parent process death (ppid changed from 1000 to 1). Initiating emergency shutdown...
```

**异常日志**：

```
# 监控未启动
2025-12-29 22:28:25 - nodeflow.node - INFO - Parent process watchdog disabled

# 监控启动失败
2025-12-29 22:28:25 - nodeflow.sdk.nodeflow_sdk - ERROR - ParentProcessWatchdog error for 'my_node': [error details]
```

---

## 6. 性能影响

### 6.1 资源消耗

- **CPU**: 每秒一次 `os.getppid()` 调用，开销极低（<0.01%）
- **内存**: 守护线程栈空间约 1MB（Python 默认）
- **线程数**: 每个节点增加 1 个守护线程

### 6.2 对节点性能的影响

| 指标 | 影响 | 说明 |
|------|------|------|
| 启动时间 | +10ms | 创建并启动守护线程 |
| 运行时CPU | <0.01% | 每秒一次系统调用 |
| 内存占用 | +1MB | 线程栈空间 |
| 响应延迟 | +1s | 检测到父进程死亡的延迟 |

### 6.3 调优建议

**降低检测延迟**（如果需要更快响应）：

```bash
export NODE_WATCHDOG_INTERVAL=0.5  # 500ms检查一次
```

**降低资源消耗**（如果节点数量极多）：

```bash
export NODE_WATCHDOG_INTERVAL=2.0  # 2秒检查一次
```

---

## 7. 最佳实践

### 7.1 生产环境

- ✅ **保持默认启用**: 防止孤儿进程积累
- ✅ **使用默认间隔**: 1秒平衡了响应速度和资源消耗
- ✅ **监控日志**: 检查是否有频繁的 PPID 变化警告

### 7.2 开发环境

- ✅ **启用调试日志**: `log_level="DEBUG"` 查看详细监控信息
- ✅ **测试强制退出**: 定期用 `kill -9` 测试清理是否正常
- ⚠️ **避免禁用**: 除非有特殊测试需求

### 7.3 测试环境

- ✅ **自动化测试**: 包含父进程监控的端到端测试
- ✅ **验证清理**: 每次测试后检查是否有遗留进程
- ✅ **压力测试**: 大量节点场景下验证监控性能

---

## 8. 技术细节

### 8.1 平台差异

| 平台 | 孤儿进程PPID | 监控方式 |
|------|--------------|----------|
| Linux | 1 (init/systemd) | `os.getppid() == 1` |
| macOS | 1 (launchd) | `os.getppid() == 1` |
| Windows | N/A | 不支持（需要其他实现） |

**注意**: 当前实现仅支持 Unix-like 系统（Linux/macOS）。Windows 平台需要使用其他机制（如 Job Objects）。

### 8.2 与Runtime的交互

父进程监控**完全独立**于 Runtime 的优雅关闭流程：

| 场景 | Runtime行为 | Watchdog行为 | 最终结果 |
|------|-------------|-------------|----------|
| 正常关闭 (`Ctrl+C`) | 发送SIGTERM到所有节点 | 不触发（节点正常退出） | ✓ 优雅关闭 |
| 强制杀死 (`kill -9`) | 立即终止，无法清理 | 检测到PPID=1，节点自动退出 | ✓ 紧急清理 |
| Daemon模式停止 | 发送stop_dataflow命令 | 不触发（节点被Runtime正常停止） | ✓ 正常停止 |

### 8.3 退出码

| 退出方式 | 退出码 | 含义 |
|----------|--------|------|
| 正常退出 | 0 | 节点完成任务 |
| Watchdog触发 | 1 | 父进程死亡，紧急退出 |
| 异常崩溃 | 1 | 未捕获的异常 |
| SIGTERM | -15 | Runtime发送的终止信号 |
| SIGKILL | -9 | 强制杀死 |

---

## 9. 升级指南

### 9.1 从旧版本升级

如果你的节点代码使用旧版本 SDK（无父进程监控）：

**无需修改代码** - 监控功能自动启用

```python
# 旧代码（仍然有效）
from sdk.nodeflow_sdk import NodeFlowSDK
sdk = NodeFlowSDK(log_level="INFO")
# ... 节点逻辑 ...
```

升级后：
- 自动获得父进程监控功能
- 日志中会显示 `ParentProcessWatchdog started`
- 无需改变节点逻辑或配置

### 9.2 兼容性

- **SDK版本**: v0.2+（包含监控功能）
- **Python版本**: 3.8+
- **平台**: Linux, macOS（Unix-like系统）

---

## 10. 常见问题 (FAQ)

### Q1: 监控会影响节点性能吗？

**A**: 影响极小。每秒一次 `os.getppid()` 系统调用，CPU开销 <0.01%，内存增加约1MB（线程栈）。

### Q2: 可以在Windows上使用吗？

**A**: 当前不支持。Windows 没有 PPID 机制，需要使用 Job Objects 或其他方式实现。

### Q3: 监控线程会阻塞节点吗？

**A**: 不会。监控运行在独立的守护线程中，不影响主线程的节点逻辑。

### Q4: 如果我想手动控制退出怎么办？

**A**: 可以禁用监控（`enable_parent_watchdog=False`），但不推荐。建议使用正常的信号处理机制。

### Q5: 监控失败会怎样？

**A**: 监控线程异常会被捕获并记录日志，不影响节点主逻辑。但节点可能变成孤儿进程。

### Q6: 如何验证监控是否生效？

**A**: 查看日志是否包含 `ParentProcessWatchdog started`。或运行端到端测试验证节点自动退出。

---

## 11. 参考资料

### 11.1 相关文件

- `sdk/nodeflow_sdk.py`: SDK主文件，包含 `ParentProcessWatchdog` 实现
- `runtime/main.py`: Runtime主入口，负责启动节点进程

### 11.2 相关文档

- `MULTI_LOOP_GUIDE.md`: 多轮启动-停止循环指南
- `DAEMON_MODE_GUIDE.md`: 守护进程模式指南
- `docs/NodeFlow_后续改进计划_20251228.md`: 项目改进计划

### 11.3 测试用例

手动测试参考：

```bash
# 1. 启动 Runtime
python3 -m runtime.main examples/planning_simulation.yaml --daemon &
RUNTIME_PID=$!

# 2. 等待启动
sleep 3

# 3. 查看节点进程
ps -ef | grep nodeflow

# 4. 杀死 Runtime
kill -9 $RUNTIME_PID

# 5. 等待 Watchdog 触发
sleep 2

# 6. 验证节点已退出
ps -ef | grep nodeflow
# 应该无输出
```

---

## 变更历史

| 版本 | 日期 | 变更内容 |
|------|------|----------|
| 1.0 | 2025-12-29 | 初始版本，实现父进程监控功能 |

---

**文档结束**
