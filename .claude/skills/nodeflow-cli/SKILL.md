---
name: nodeflow-cli
description: NodeFlow CLI 命令参考。用于调试、监控、控制 NodeFlow 运行时框架、节点库、缓冲区、日志等。
allowed-tools: Bash(python3 -m tools.cli.core.cli:*), Bash(python3 -m runtime.main:*)
---

# NodeFlow CLI 工具

CLI 入口: `python3 -m tools.cli.core.cli`

## 调试检查清单

启动框架调试时按顺序执行：

```
1. python3 -m tools.cli.core.cli runtime status     # 检查运行状态
2. python3 -m tools.cli.core.cli buffer list         # 检查缓冲区
3. python3 -m tools.cli.core.cli health check <node> # 检查节点 Schema
4. python3 -m tools.cli.core.cli logs -f             # 实时日志
```

## 命令速查

### runtime - 运行时控制
```bash
# 启动
python3 -m tools.cli.core.cli runtime start <config> -b
python3 -m tools.cli.core.cli runtime start examples/planning_simulation.yaml --background
python3 -m tools.cli.core.cli runtime start examples/tillage_operation.yaml --background

# 状态
python3 -m tools.cli.core.cli runtime status

# 数据流控制（无需重启框架）
python3 -m tools.cli.core.cli runtime start-dataflow
python3 -m tools.cli.core.cli runtime stop-dataflow
python3 -m tools.cli.core.cli runtime restart-dataflow

# 停止
python3 -m tools.cli.core.cli runtime stop
```

### logs - 日志查看
```bash
# 实时跟踪所有日志
python3 -m tools.cli.core.cli logs -f

# 过滤特定节点
python3 -m tools.cli.core.cli logs -n waypoint_selector -f

# 过滤级别
python3 -m tools.cli.core.cli logs -l ERROR

# 搜索文本
python3 -m tools.cli.core.cli logs -s "timeout"

# 指定日志目录
python3 -m tools.cli.core.cli logs --log-dir /tmp/nodeflow_logs
```

### buffer - 缓冲区诊断
```bash
# 列出所有缓冲区
python3 -m tools.cli.core.cli buffer list

# 查看缓冲区内容
python3 -m tools.cli.core.cli buffer inspect sim_output.rtk_fix
python3 -m tools.cli.core.cli buffer inspect <name> --raw
```

### health - 健康检查
```bash
# 检查节点 Schema 合规性
python3 -m tools.cli.core.cli health check <node_id> --samples 10

# 检查数据流活性
python3 -m tools.cli.core.cli health flow --config examples/planning_simulation.yaml
```

### node - 节点管理
```bash
# 列出所有节点
python3 -m tools.cli.core.cli node list

# 查看节点详情
python3 -m tools.cli.core.cli node info <package_name>
python3 -m tools.cli.core.cli node info waypoint_selector
python3 -m tools.cli.core.cli node info tillage_controller
```

### monitor - 实时监控
```bash
python3 -m tools.cli.core.cli monitor --config examples/planning_simulation.yaml --interval 1.0
```

### simulator - 仿真器控制
```bash
# 刷新地块
python3 -m tools.cli.core.cli simulator refresh
```

## 关键文件位置

| 类型 | 路径 |
|------|------|
| PID 文件 | `/tmp/nodeflow_runtime.pid` |
| 缓冲区目录 | `/tmp/nodeflow/buffers/` |
| 日志目录 | `/tmp/nodeflow_logs/` |
| 配置示例 | `examples/planning_simulation.yaml` |

## 调试常见场景

### 场景1：节点不输出数据
1. `runtime status` - 确认框架运行中
2. `buffer list` - 检查输出缓冲区是否存在
3. `buffer inspect <name>` - 查看缓冲区内容
4. `health check <node_id>` - 验证 Schema 合规
5. `logs -n <node_id> -f` - 查看节点日志

### 场景2：数据流卡住
1. `health flow --config <config>` - 检查整体数据流
2. `runtime restart-dataflow` - 重启数据流
3. `monitor --config <config>` - 实时监控各缓冲区

### 场景3：查看历史错误
```bash
python3 -m tools.cli.core.cli logs -l ERROR --detailed -c 100
```

### 场景4：旋耕作业监控
```bash
# 启动旋耕作业场景
python3 -m tools.cli.core.cli runtime start examples/tillage_operation.yaml -b

# 监控旋耕状态转换
python3 -m tools.cli.core.cli logs -n tillage_controller -f
# 预期看到: TRANSPORT → LOWERING → WORKING → RAISING → TRANSPORT

# 查看机具控制指令缓冲区
python3 -m tools.cli.core.cli buffer inspect tillage_controller.tillage_cmd
python3 -m tools.cli.core.cli buffer inspect tillage_controller.tillage_status

# 健康检查
python3 -m tools.cli.core.cli health check tillage_controller --samples 10
```

## 调用运行时框架

直接运行（非 CLI 方式）：
```bash
python3 -m runtime.main <config> --log-level INFO --daemon
```

更多参考详见 [REFERENCE.md](REFERENCE.md)
