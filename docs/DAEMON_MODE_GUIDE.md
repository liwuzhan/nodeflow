# NodeFlow 守护进程模式使用指南

## 概述

NodeFlow 框架现已支持**守护进程模式**，允许框架作为后台服务运行，通过 CLI 命令动态控制数据流的启停，而无需重启整个框架。

## 架构设计

```
┌─────────────────────────────────────────────────┐
│         守护进程（后台运行）                      │
│                                                 │
│  ┌─────────────────────────────────────┐       │
│  │  框架层（持续运行）                   │       │
│  │  - 配置管理                          │       │
│  │  - 节点库扫描                        │       │
│  │  - 拓扑分析                          │       │
│  │  - 控制缓冲区监听                     │       │
│  └─────────────────────────────────────┘       │
│           ↕ 控制命令                            │
│  ┌─────────────────────────────────────┐       │
│  │  数据流层（动态启停）                 │       │
│  │  - 启动节点进程                      │       │
│  │  - 监控运行                          │       │
│  │  - 停止节点进程                      │       │
│  └─────────────────────────────────────┘       │
└─────────────────────────────────────────────────┘
                  ↕
          CLI 命令工具
    (start-dataflow/stop-dataflow)
```

## 使用方式

### 1. 启动守护进程

启动框架作为后台服务，不立即启动数据流：

```bash
# 方式 1: 通过 runtime.main 直接启动（前台）
python3 -m runtime.main examples/planning_simulation.yaml --daemon

# 方式 2: 通过 CLI 工具启动（后台）
python3 tools/cli/core/cli.py runtime start examples/planning_simulation.yaml --background
```

**参数说明**：
- `--daemon`: 守护进程模式（等待 CLI 命令）
- `--background` / `-b`: 在后台运行（仅用于 CLI runtime start）
- `--log-level`: 日志级别（DEBUG/INFO/WARNING/ERROR）
- `--no-clean-buffers`: 禁用缓冲区清理

### 2. 检查运行状态

```bash
# 查看框架是否在运行
python3 tools/cli/core/cli.py runtime status

# JSON 格式输出
python3 tools/cli/core/cli.py runtime status --json
```

**输出示例**：
```
✓ Runtime is running
  PID: 12345
  Uptime: 0.5h
  Memory: 125.3 MB
  Started: 2025-12-28T10:30:00
```

### 3. 启动数据流

框架运行后，通过 CLI 命令启动数据流：

```bash
python3 tools/cli/core/cli.py runtime start-dataflow
```

**效果**：
- 启动所有配置的节点
- 开始数据流交互
- 启动节点监控器

### 4. 停止数据流

停止数据流但保持框架运行：

```bash
python3 tools/cli/core/cli.py runtime stop-dataflow
```

**效果**：
- 停止所有节点进程
- 清理资源
- 框架继续运行，等待下一个命令

### 5. 重启数据流

快速重启数据流（先停止再启动）：

```bash
python3 tools/cli/core/cli.py runtime restart-dataflow
```

### 6. 停止框架

停止整个框架（包括数据流）：

```bash
python3 tools/cli/core/cli.py runtime stop
```

## 完整工作流示例

### 场景 A: 日常开发调试

```bash
# 1. 启动框架（后台守护进程）
python3 tools/cli/core/cli.py runtime start examples/planning_simulation.yaml -b

# 2. 检查状态
python3 tools/cli/core/cli.py runtime status
# ✓ Runtime is running
#   PID: 12345

# 3. 启动数据流
python3 tools/cli/core/cli.py runtime start-dataflow
# ✓ Start dataflow command sent

# 4. 检查缓冲区数据
python3 tools/cli/core/cli.py buffer list

# 5. 调试完成，停止数据流
python3 tools/cli/core/cli.py runtime stop-dataflow
# ✓ Stop dataflow command sent

# 6. 修改代码...

# 7. 重新启动数据流测试
python3 tools/cli/core/cli.py runtime start-dataflow

# 8. 结束调试，停止框架
python3 tools/cli/core/cli.py runtime stop
# ✓ Runtime stopped successfully
```

### 场景 B: 长期运行服务

```bash
# 1. 启动框架（后台守护进程）
python3 tools/cli/core/cli.py runtime start production.yaml -b --log-level INFO

# 2. 启动数据流
python3 tools/cli/core/cli.py runtime start-dataflow

# ... 系统运行中 ...

# 3. 需要维护时停止数据流
python3 tools/cli/core/cli.py runtime stop-dataflow

# 4. 进行系统维护（框架继续运行）

# 5. 维护完成，重启数据流
python3 tools/cli/core/cli.py runtime start-dataflow
```

### 场景 C: 多次测试不同配置

```bash
# 1. 启动框架
python3 tools/cli/core/cli.py runtime start config_v1.yaml -b

# 2. 运行测试 1
python3 tools/cli/core/cli.py runtime start-dataflow
sleep 30
python3 tools/cli/core/cli.py runtime stop-dataflow

# 3. 等待系统稳定
sleep 5

# 4. 运行测试 2
python3 tools/cli/core/cli.py runtime start-dataflow
sleep 30
python3 tools/cli/core/cli.py runtime stop-dataflow

# 5. 运行测试 3
python3 tools/cli/core/cli.py runtime start-dataflow
sleep 30
python3 tools/cli/core/cli.py runtime stop-dataflow

# 6. 完成所有测试
python3 tools/cli/core/cli.py runtime stop
```

## 控制命令详解

### runtime start

**功能**：启动框架

**语法**：
```bash
python3 tools/cli/core/cli.py runtime start <config> [OPTIONS]
```

**选项**：
- `--background` / `-b`: 在后台运行
- `--log-level {DEBUG,INFO,WARNING,ERROR}`: 日志级别
- `--no-clean-buffers`: 禁用缓冲区清理
- `--json`: JSON 格式输出

**返回**：
- `status: success` - 启动成功
- `status: already_running` - 已在运行
- `status: error` - 启动失败

### runtime stop

**功能**：停止框架

**语法**：
```bash
python3 tools/cli/core/cli.py runtime stop [OPTIONS]
```

**选项**：
- `--json`: JSON 格式输出

**返回**：
- `status: success` - 停止成功
- `status: not_running` - 未在运行
- `status: error` - 停止失败

### runtime status

**功能**：检查框架状态

**语法**：
```bash
python3 tools/cli/core/cli.py runtime status [OPTIONS]
```

**选项**：
- `--json`: JSON 格式输出

**返回**：
```json
{
  "status": "running",
  "pid": 12345,
  "uptime_seconds": 3600.5,
  "memory_mb": 125.3,
  "started_at": "2025-12-28T10:30:00"
}
```

### runtime start-dataflow

**功能**：启动数据流

**前提**：框架必须已在运行（守护进程模式）

**语法**：
```bash
python3 tools/cli/core/cli.py runtime start-dataflow [OPTIONS]
```

**选项**：
- `--json`: JSON 格式输出

**通信方式**：
- 通过共享缓冲区 `runtime.control` 发送命令
- 框架监听缓冲区并响应

### runtime stop-dataflow

**功能**：停止数据流

**前提**：数据流必须正在运行

**语法**：
```bash
python3 tools/cli/core/cli.py runtime stop-dataflow [OPTIONS]
```

**选项**：
- `--json`: JSON 格式输出

### runtime restart-dataflow

**功能**：重启数据流（停止 + 启动）

**语法**：
```bash
python3 tools/cli/core/cli.py runtime restart-dataflow [OPTIONS]
```

**选项**：
- `--json`: JSON 格式输出

## 技术实现

### 控制缓冲区协议

框架和 CLI 通过共享缓冲区 `runtime.control` 通信：

**命令格式**：
```json
{
  "command": "start_dataflow|stop_dataflow|shutdown",
  "timestamp": 1735363200.123
}
```

**命令类型**：
- `start_dataflow`: 启动数据流
- `stop_dataflow`: 停止数据流
- `shutdown`: 关闭框架

**去重机制**：
- 使用 `timestamp` 字段防止重复执行同一命令
- 框架记录最后处理的命令时间戳

### PID 文件

框架在 `/tmp/nodeflow_runtime.pid` 写入进程信息：

```
<PID>
<start_time_timestamp>
```

CLI 工具通过读取此文件来检查框架状态。

### 日志文件

后台模式下，日志输出到 `/tmp/nodeflow_runtime.log`：

```bash
# 查看日志
tail -f /tmp/nodeflow_runtime.log

# 查看最近 100 行
tail -100 /tmp/nodeflow_runtime.log
```

## 故障排除

### 问题 1: CLI 命令无响应

**症状**：执行 `runtime start-dataflow` 后无反应

**诊断**：
```bash
# 检查框架是否在运行
python3 tools/cli/core/cli.py runtime status

# 检查日志
tail -50 /tmp/nodeflow_runtime.log

# 检查控制缓冲区
python3 tools/cli/core/cli.py buffer inspect runtime.control
```

**可能原因**：
- 框架未以 `--daemon` 模式启动
- 控制缓冲区未创建
- 框架进程已崩溃

**解决**：
- 确保使用 `--daemon` 或通过 CLI `runtime start --background`
- 重启框架

### 问题 2: 框架启动后立即退出

**症状**：`runtime start` 显示成功，但 `runtime status` 显示未运行

**诊断**：
```bash
# 查看日志
cat /tmp/nodeflow_runtime.log

# 检查配置文件
python3 tools/cli/core/cli.py node list
```

**可能原因**：
- 配置文件错误
- 节点库路径错误
- 初始化失败

**解决**：
- 检查日志中的错误信息
- 验证配置文件格式
- 使用前台模式测试：`python3 -m runtime.main config.yaml --daemon`

### 问题 3: 数据流无法停止

**症状**：`runtime stop-dataflow` 后节点进程仍在运行

**诊断**：
```bash
# 检查节点进程
ps aux | grep node-hub

# 检查僵尸进程
ps aux | grep defunct
```

**可能原因**：
- 节点进程未正确响应 SIGTERM
- 进程组未正确清理

**解决**：
```bash
# 强制停止框架
python3 tools/cli/core/cli.py runtime stop

# 手动清理进程
pkill -f node-hub
```

### 问题 4: 内存持续增长

**症状**：长期运行后内存占用增加

**诊断**：
```bash
# 监控内存
watch -n 5 'python3 tools/cli/core/cli.py runtime status | grep Memory'

# 检查缓冲区
ls -lh /tmp/nodeflow/buffers/
```

**可能原因**：
- 缓冲区未清理
- 节点内存泄漏

**解决**：
- 定期重启数据流
- 检查节点代码

## 性能考虑

### 响应延迟

- **命令发送延迟**: < 10ms（缓冲区写入）
- **命令处理延迟**: ~500ms（框架轮询间隔）
- **数据流启动时间**: 1-3s（取决于节点数量）
- **数据流停止时间**: 0.5-1s（SIGTERM 超时）

### 资源占用

- **守护进程基础内存**: ~50MB（框架层）
- **数据流内存**: 取决于节点数量和类型
- **缓冲区磁盘空间**: 取决于配置（通常 <10MB）

## 最佳实践

### 1. 日志管理

```bash
# 定期轮转日志
mv /tmp/nodeflow_runtime.log /tmp/nodeflow_runtime.log.$(date +%Y%m%d)

# 限制日志大小
tail -10000 /tmp/nodeflow_runtime.log > /tmp/nodeflow_runtime.log.new
mv /tmp/nodeflow_runtime.log.new /tmp/nodeflow_runtime.log
```

### 2. 健康检查

```bash
# 定期检查框架状态
*/5 * * * * python3 tools/cli/core/cli.py runtime status --json > /var/log/nodeflow_health.json
```

### 3. 优雅重启

```bash
# 重启脚本
#!/bin/bash
python3 tools/cli/core/cli.py runtime stop-dataflow
sleep 2
python3 tools/cli/core/cli.py runtime start-dataflow
```

### 4. 监控集成

```bash
# 与 Prometheus 集成
# 定期导出指标
python3 tools/cli/core/cli.py runtime status --json | \
  jq '{uptime:.uptime_seconds, memory_mb:.memory_mb}' > /var/lib/prometheus/nodeflow_metrics.prom
```

## 与其他模式对比

| 特性 | 守护进程模式 | 单次运行 | 多轮循环 |
|-----|------------|---------|---------|
| 框架启动次数 | 1 | 1 | 1 |
| 数据流启停 | 动态（CLI控制） | 1 次 | N 次（自动） |
| 适用场景 | 生产环境、长期服务 | 测试、脚本 | 自动化测试 |
| 控制方式 | CLI 命令 | 参数 | 参数 |
| 灵活性 | 最高 | 最低 | 中等 |
| 复杂度 | 中等 | 最低 | 低 |

## 相关文档

- [多轮循环指南](MULTI_LOOP_GUIDE.md)
- [AI Agent CLI 使用指南](docs/AI_CLI_USAGE_GUIDE.md)
- [测试框架总结](docs/TESTING_FRAMEWORK_SUMMARY.md)

## 示例脚本

### 自动化测试脚本

```bash
#!/bin/bash
# test_with_daemon.sh - 使用守护进程模式进行自动化测试

set -e

CONFIG="examples/planning_simulation.yaml"
LOG_DIR="./test-logs"

echo "=== 启动守护进程 ==="
python3 tools/cli/core/cli.py runtime start $CONFIG -b --log-level DEBUG

# 等待框架初始化
sleep 3

echo "=== 检查框架状态 ==="
python3 tools/cli/core/cli.py runtime status

echo "=== 运行测试 1 ==="
python3 tools/cli/core/cli.py runtime start-dataflow
sleep 30
python3 tools/cli/core/cli.py buffer list > $LOG_DIR/test1_buffers.txt
python3 tools/cli/core/cli.py runtime stop-dataflow

echo "=== 等待清理 ==="
sleep 5

echo "=== 运行测试 2 ==="
python3 tools/cli/core/cli.py runtime start-dataflow
sleep 30
python3 tools/cli/core/cli.py buffer list > $LOG_DIR/test2_buffers.txt
python3 tools/cli/core/cli.py runtime stop-dataflow

echo "=== 停止框架 ==="
python3 tools/cli/core/cli.py runtime stop

echo "=== 测试完成 ==="
```

---

**版本**: v1.2+
**更新日期**: 2025-12-28
