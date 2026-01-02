# NodeFlow Runtime 控制面板 - 使用指南

## 简介

这是一个简单的图形界面，用于管理 NodeFlow 数据流。无需记忆命令行参数，只需点击按钮即可控制 Runtime 和数据流的启动/停止。

![GUI Screenshot](screenshots/gui_main.png)

## 功能特性

- ✅ **配置文件选择**：从下拉列表中选择 examples 目录中的任意数据流配置
- ✅ **Runtime 控制**：一键启动/停止 NodeFlow Runtime（后台模式）
- ✅ **数据流控制**：启动/停止/重启数据流（无需重启 Runtime）
- ✅ **实时状态监控**：显示 Runtime PID、运行时间等状态信息
- ✅ **日志输出**：实时查看操作日志，便于调试
- ✅ **智能按钮状态**：根据运行状态自动启用/禁用相关按钮

## 快速开始

### 方法 1：使用启动脚本

```bash
# 进入项目目录
cd /Users/wuzhanli/Desktop/node

# 运行启动脚本
./start_gui.sh
```

### 方法 2：直接运行 Python

```bash
cd /Users/wuzhanli/Desktop/node
python3 gui_runtime_control.py
```

## 使用流程

### 1. 选择配置文件

从顶部的下拉列表中选择要运行的数据流配置文件。例如：
- `planning_simulation.yaml` - 完整的规划仿真场景
- `planning_minimal.yaml` - 最小化测试场景
- `test_logger.yaml` - 简单的日志测试

### 2. 启动 Runtime

点击 **"▶ 启动 Runtime"** 按钮：
- Runtime 会在后台启动（守护进程模式）
- 日志会显示启动结果和 PID
- 状态栏会更新为 "Runtime: 运行中"
- 数据流控制按钮会被启用

**等价的 CLI 命令**：
```bash
python3 -m tools.cli.core.cli runtime start examples/planning_simulation.yaml --background
```

### 3. 启动数据流

点击 **"▶ 启动数据流"** 按钮：
- Runtime 会启动所有配置的节点
- 数据流开始运行
- 节点间开始通信和数据处理

**等价的 CLI 命令**：
```bash
python3 -m tools.cli.core.cli runtime start-dataflow
```

### 4. 停止数据流（可选）

点击 **"⏹ 停止数据流"** 按钮：
- 所有节点会被优雅关闭
- Runtime 继续运行，可以再次启动数据流

**等价的 CLI 命令**：
```bash
python3 -m tools.cli.core.cli runtime stop-dataflow
```

### 5. 重启数据流（可选）

点击 **"🔄 重启数据流"** 按钮：
- 相当于先停止再启动数据流
- 用于快速重启节点

**等价的 CLI 命令**：
```bash
python3 -m tools.cli.core.cli runtime restart-dataflow
```

### 6. 停止 Runtime

点击 **"⏹ 停止 Runtime"** 按钮：
- Runtime 会优雅关闭
- 所有节点会被终止
- 共享缓冲区会被清理

**等价的 CLI 命令**：
```bash
python3 -m tools.cli.core.cli runtime stop
```

## 界面说明

### 配置文件选择区域

```
┌─────────────────────────────────────────┐
│ 配置文件选择                              │
│ 数据流配置: [planning_simulation.yaml ▼]│
└─────────────────────────────────────────┘
```

- 下拉列表包含 `examples/` 目录中的所有 `.yaml` 配置文件
- 选择后即可启动对应的数据流

### 控制面板区域

```
┌─────────────────────────────────────────────────────┐
│ 控制面板                                             │
│ Runtime:  [▶ 启动 Runtime]  [⏹ 停止 Runtime]       │
│ 数据流:   [▶ 启动数据流]    [⏹ 停止数据流]  [🔄 重启]│
└─────────────────────────────────────────────────────┘
```

**按钮状态说明**：

| 场景 | 启动 Runtime | 停止 Runtime | 启动数据流 | 停止数据流 | 重启数据流 |
|------|-------------|-------------|-----------|-----------|-----------|
| 初始状态 | ✅ 可用 | ❌ 禁用 | ❌ 禁用 | ❌ 禁用 | ❌ 禁用 |
| Runtime 运行中 | ❌ 禁用 | ✅ 可用 | ✅ 可用 | ✅ 可用 | ✅ 可用 |

### 运行状态区域

```
┌─────────────────────────────────────────────────────┐
│ 运行状态                                             │
│ ● Runtime: 运行中 (PID: 12345, 运行时间: 2.5h)       │
│   数据流: 已启动                                     │
└─────────────────────────────────────────────────────┘
```

- 实时显示 Runtime 状态（每 2 秒更新）
- 包含 PID 和运行时间信息
- 绿点 ● 表示正在运行

### 日志输出区域

```
┌─────────────────────────────────────────────────────┐
│ 日志输出                                             │
│ [22:30:15] 启动 Runtime: planning_simulation.yaml   │
│ [22:30:17] ✓ Runtime started in background (PID: 12│
│ [22:30:20] 启动数据流...                             │
│ [22:30:22] ✓ Start dataflow command sent            │
│                                                      │
│ [清除日志]                                           │
└─────────────────────────────────────────────────────┘
```

- 显示所有操作的日志记录
- 包含时间戳
- 可滚动查看历史日志
- 点击"清除日志"可清空

## 使用场景

### 场景 1：快速测试数据流

```
1. 选择 planning_simulation.yaml
2. 点击 [▶ 启动 Runtime]
3. 点击 [▶ 启动数据流]
4. 观察日志输出
5. 点击 [⏹ 停止 Runtime]
```

### 场景 2：多次运行同一配置

```
1. 选择 test_logger.yaml
2. 点击 [▶ 启动 Runtime]
3. 点击 [▶ 启动数据流]
4. 测试完成后，点击 [⏹ 停止数据流]
5. 修改代码...
6. 点击 [▶ 启动数据流] （无需重启 Runtime）
7. 重复步骤 4-6
```

### 场景 3：测试多个配置

```
1. 选择 planning_minimal.yaml
2. 点击 [▶ 启动 Runtime]
3. 点击 [▶ 启动数据流]
4. 点击 [⏹ 停止 Runtime]
5. 选择 planning_simulation.yaml
6. 点击 [▶ 启动 Runtime]
7. 点击 [▶ 启动数据流]
```

## 常见问题

### Q1: 点击"启动 Runtime"后没有反应？

**A**: 检查：
1. 日志输出是否显示错误信息
2. 配置文件路径是否正确
3. Python 环境是否正确（需要 Python 3.8+）
4. 是否有其他 Runtime 实例正在运行（检查 `/tmp/nodeflow_runtime.pid`）

### Q2: 数据流按钮一直是禁用状态？

**A**: 说明 Runtime 未成功启动。检查：
1. 日志中是否有错误信息
2. 运行 `ps aux | grep nodeflow` 查看进程是否存在
3. 运行 CLI 命令手动测试：`python3 -m tools.cli.core.cli runtime status`

### Q3: 如何查看节点的详细日志？

**A**: GUI 只显示控制操作的日志。节点日志位于：
```bash
# Runtime 主日志
/tmp/nodeflow_runtime.log

# 各节点日志
/tmp/nodeflow_logs/*.log
```

### Q4: 关闭 GUI 窗口会停止 Runtime 吗？

**A**: 不会。Runtime 在后台运行，关闭 GUI 不影响 Runtime。如需停止，请：
1. 在关闭前点击"停止 Runtime"按钮，或
2. 使用 CLI 命令：`python3 -m tools.cli.core.cli runtime stop`

### Q5: 状态显示不准确怎么办？

**A**: 状态每 2 秒自动更新。如果仍然不准确：
1. 关闭并重新打开 GUI
2. 使用 CLI 查看准确状态：`python3 -m tools.cli.core.cli runtime status`

## 技术细节

### 架构

```
GUI (tkinter)
    ↓ 调用
tools/cli/commands/runtime_cmd.py
    ↓ 控制
Runtime (后台守护进程)
    ↓ 管理
Nodes (各个节点进程)
```

### 文件说明

- `gui_runtime_control.py`: GUI 主程序
- `start_gui.sh`: 快速启动脚本
- `tools/cli/commands/runtime_cmd.py`: CLI 命令实现（被 GUI 调用）

### 依赖

- **Python 3.8+**: 基础运行环境
- **tkinter**: GUI 库（Python 内置，无需安装）
- **threading**: 后台任务（Python 内置）

### 性能

- **启动时间**: < 1 秒
- **内存占用**: ~20 MB
- **CPU 占用**: ~0.1%（后台监控）
- **状态更新频率**: 每 2 秒

## 进阶用法

### 自定义配置目录

编辑 `gui_runtime_control.py`，修改：

```python
# 默认
self.examples_dir = project_root / "examples"

# 修改为自定义目录
self.examples_dir = Path("/path/to/your/configs")
```

### 修改状态更新频率

编辑 `gui_runtime_control.py`，修改：

```python
# 默认 2 秒
time.sleep(2)

# 修改为 1 秒
time.sleep(1)
```

### 添加更多控制按钮

参考现有按钮的实现，添加自定义功能按钮。例如，添加"查看日志"按钮打开日志文件：

```python
def open_logs(self):
    """打开日志目录"""
    import subprocess
    subprocess.run(["open", "/tmp/nodeflow_logs/"])
```

## 故障排查

### 无法启动 GUI

```bash
# 检查 Python 版本
python3 --version  # 需要 3.8+

# 检查 tkinter 是否可用
python3 -c "import tkinter; print('OK')"

# 检查语法错误
python3 -m py_compile gui_runtime_control.py
```

### Runtime 启动失败

```bash
# 查看详细错误
cat /tmp/nodeflow_runtime.log

# 检查端口占用
lsof -i :5555  # 仿真器端口

# 检查共享缓冲区
ls -lh /tmp/nodeflow/buffers/
```

### 节点异常

```bash
# 查看所有节点日志
tail -f /tmp/nodeflow_logs/*.log

# 检查进程
ps aux | grep nodeflow

# 清理遗留进程
pkill -f nodeflow
```

## 相关文档

- [DAEMON_MODE_GUIDE.md](DAEMON_MODE_GUIDE.md) - 守护进程模式详细说明
- [MULTI_LOOP_GUIDE.md](MULTI_LOOP_GUIDE.md) - 多轮循环模式说明
- [PARENT_PROCESS_WATCHDOG.md](docs/PARENT_PROCESS_WATCHDOG.md) - 父进程监控机制
- [README.md](README.md) - 项目总览

## 反馈与贡献

如有问题或建议，请通过以下方式反馈：
- 创建 GitHub Issue
- 提交 Pull Request
- 联系项目维护者

---

**版本**: 1.0
**更新日期**: 2025-12-29
**作者**: NodeFlow Team
