# NodeFlow 多轮启动-停止循环功能指南

## 概述

NodeFlow 框架现已支持**多轮启动-停止循环**功能，允许单个框架实例在不重启的情况下多次启动和停止数据流。这对于以下场景很有用：

- **长期运行服务**：框架持续运行，支持动态启停数据流
- **自动化测试**：在同一框架实例中运行多个测试周期
- **工作流管理**：依次运行多个相互独立的任务

## 架构改动

框架现已分为两个层级：

```
┌─────────────────────────────────────┐
│     框架层（Framework）              │
│  - 信号处理（一次性）                 │
│  - 配置加载、验证（一次性）            │
│  - 节点库扫描、图验证、拓扑分析（一次性）│
└─────────────────────────────────────┘
               ↓ 初始化
┌─────────────────────────────────────┐
│     数据流层（Dataflow）             │
│  - 启动节点                          │
│  - 监控运行                          │
│  - 停止节点 ← 可重复多次！
└─────────────────────────────────────┘
```

## 使用方法

### 1. 传统单次运行模式（向后兼容）

```bash
# 启动框架，运行数据流，然后退出
python3 -m runtime.main examples/planning_simulation.yaml
```

**行为**：
1. 初始化框架
2. 启动数据流（启动所有节点）
3. 等待（直到Ctrl+C或timeout）
4. 停止数据流
5. 退出

### 2. 多轮循环模式（新功能）

#### 运行指定轮数

```bash
# 运行3轮：启动→停止→启动→停止→启动→停止
python3 -m runtime.main examples/planning_simulation.yaml --loop 3
```

**行为**：
```
Loop 1/3:
  ├─ 启动数据流 (启动所有节点)
  ├─ 运行数据流（可通过Ctrl+C中断）
  └─ 停止数据流 (关闭所有节点，清理资源)

Loop 2/3:
  ├─ 启动数据流 (重新启动所有节点)
  ├─ 运行数据流
  └─ 停止数据流

Loop 3/3:
  ├─ 启动数据流
  ├─ 运行数据流
  └─ 停止数据流

框架退出
```

#### 无限循环模式

```bash
# 运行无限轮数，直到收到Ctrl+C或系统信号
python3 -m runtime.main examples/planning_simulation.yaml --loop 0
```

#### 自定义循环间隔

```bash
# 每两轮之间等待10秒
python3 -m runtime.main examples/planning_simulation.yaml --loop 5 --loop-interval 10
```

## 命令行参数说明

| 参数 | 说明 | 默认值 |
|------|------|--------|
| `config` | 运行配置文件路径（必需） | - |
| `--loop N` | 运行N轮循环；`N=0`表示无限循环 | 无（不使用循环模式） |
| `--loop-interval SEC` | 两轮之间的等待时间（秒） | 5 |
| `--log-level` | 日志级别：DEBUG/INFO/WARNING/ERROR | INFO |
| `--duration SEC` | 自动关机时间（仅在单次运行模式下） | - |
| `--no-clean-buffers` | 禁用启动前清理共享缓冲区 | 默认清理 |

## Python API 使用

### 传统单次运行

```python
from runtime.main import NodeFlowRuntime

runtime = NodeFlowRuntime('examples/planning_simulation.yaml', log_level='INFO')
exit_code = runtime.run()
```

### 多轮循环运行

```python
from runtime.main import NodeFlowRuntime

runtime = NodeFlowRuntime('examples/planning_simulation.yaml', log_level='INFO')

# 运行3轮，每轮间隔5秒
exit_code = runtime.run_with_loop(num_loops=3, loop_interval=5)

# 无限运行，直到收到信号
# exit_code = runtime.run_with_loop(num_loops=None, loop_interval=5)
```

### 底层 API（高级用法）

```python
from runtime.main import NodeFlowRuntime

runtime = NodeFlowRuntime('examples/planning_simulation.yaml')

# 初始化框架（一次性）
if runtime._initialize_framework() != 0:
    print("Framework initialization failed")
    exit(1)

# 运行多个循环
for i in range(3):
    print(f"\n=== Loop {i+1} ===")

    try:
        # 启动数据流
        runtime.start_dataflow()

        # 运行数据流（您可以添加自定义控制逻辑）
        import time
        time.sleep(30)  # 运行30秒

    except Exception as e:
        print(f"Error in loop {i+1}: {e}")
    finally:
        # 停止数据流
        try:
            runtime.stop_dataflow()
        except:
            pass
```

## 信号处理行为

在多轮循环模式下，信号（如Ctrl+C）的行为有所不同：

| 场景 | Ctrl+C行为 |
|------|-----------|
| 数据流运行中 | 停止当前数据流，继续下一轮（或退出如果是最后一轮） |
| 两轮之间等待中 | 立即中止，不运行后续轮数 |

示例：
```
Loop 1/3: [运行中] → 按Ctrl+C → [停止] → 继续
Loop 2/3: [运行中] → 按Ctrl+C → [停止] → 继续
Loop 3/3: [运行中] → 按Ctrl+C → [停止] → 框架退出
```

## 重要事项

### 1. 缓冲区清理

- 在每轮启动前，框架会清理共享缓冲区（默认行为）
- 如果需要保留跨轮的数据，使用`--no-clean-buffers`参数
- 缓冲区清理通过写入零字节来实现序列号重置

### 2. 节点监控和重启

- 每轮的节点监控策略独立进行
- 如果节点在运行时崩溃，会根据`restart_policy`自动重启
- 重启策略在节点启动时初始化，不跨轮继承

### 3. 文件和日志

- 每轮生成独立的日志文件
- PID文件在每轮启动时更新，停止时清理
- 建议使用不同的日志目录或时间戳以分隔各轮日志

## 故障排除

### 问题：第二轮启动失败

**原因**：端口被占用或缓冲区未正确清理

**解决**：
```bash
# 确保第一轮完全停止
# 检查是否有僵尸进程
ps aux | grep python3 | grep nodeflow

# 使用--no-clean-buffers排除缓冲区问题
python3 -m runtime.main config.yaml --loop 3 --no-clean-buffers
```

### 问题：节点在某些轮次中不启动

**原因**：节点文件被锁定或权限问题

**解决**：
```bash
# 检查日志输出
python3 -m runtime.main config.yaml --loop 3 --log-level DEBUG

# 手动检查进程
lsof /tmp/nodeflow/buffers/
```

### 问题：内存持续增长

**原因**：前一轮的资源未被正确清理

**解决**：
- 确保每轮都调用了`stop_dataflow()`
- 检查节点进程是否真的被终止（`ps aux`）
- 增加`--loop-interval`以给系统更多清理时间

## 性能考虑

- **启动开销**：每轮都需要重新启动所有节点，会有初始化延迟
- **缓冲区清理**：清理操作与缓冲区大小成正比
- **推荐配置**：
  - 对于高频循环（间隔<1秒）：使用`--no-clean-buffers`并手动管理
  - 对于低频循环（间隔>10秒）：使用默认清理策略

## 相关文件

- `runtime/main.py` - 核心框架实现
  - `NodeFlowRuntime._initialize_framework()` - 框架初始化
  - `NodeFlowRuntime.start_dataflow()` - 启动数据流
  - `NodeFlowRuntime.stop_dataflow()` - 停止数据流
  - `NodeFlowRuntime.run_with_loop()` - 多轮循环主循环

## 升级说明

### 对现有代码的影响

- ✅ **完全向后兼容**：现有的`runtime.run()`调用不受影响
- ✅ **命令行兼容**：旧的命令行用法（无`--loop`参数）仍然有效
- ⚠️ **新的异常**：`start_dataflow()`和`stop_dataflow()`可能抛出`RuntimeError`，调用代码需要处理

### 迁移建议

如果您之前有自己的多轮循环逻辑，现在可以用新的`run_with_loop()`替代：

```python
# 旧方式
for i in range(3):
    runtime = NodeFlowRuntime('config.yaml')
    runtime.run()  # 每次都重新创建框架

# 新方式
runtime = NodeFlowRuntime('config.yaml')
runtime.run_with_loop(num_loops=3)  # 共享同一个框架实例
```

## 示例配置

### 自动化测试场景

```bash
# 运行5轮测试，每轮10秒运行时间，间隔2秒
timeout 70 python3 -m runtime.main examples/planning_simulation.yaml --loop 5 --loop-interval 2
```

### 长期服务（需要外部控制）

```bash
# 保持运行，等待外部程序通过Python API控制
python3 -m runtime.main examples/planning_simulation.yaml --loop 0 --log-level INFO
```

### 性能评估

```bash
# 测试框架启停性能，运行20轮
time python3 -m runtime.main examples/planning_simulation.yaml --loop 20 --loop-interval 1 --duration 2
```

## 反馈和问题报告

如发现问题或有改进建议，请在项目GitHub上报告。
