# NodeFlow 结构化日志系统使用指南

## 概述

NodeFlow 现在集成了一套完整的**结构化日志系统**，专为多进程节点框架设计：

✅ **JSON格式日志** - 机器可解析
✅ **实时控制台输出** - 人类可读
✅ **自动进程隔离** - 每个节点独立日志文件
✅ **强大的CLI工具** - 实时跟踪、过滤、聚合
✅ **零配置** - SDK自动启用，无需手动设置

## 架构

```
各节点进程
  ├─ logger.info()
  ├─ logger.debug()
  ├─ logger.error()
  └─ ... (业务逻辑)
        │
        ├─→ 控制台输出（实时，彩色）
        └─→ /tmp/nodeflow/logs/<node_id>.jsonl（JSON格式，持久化）
             │
             ├─ timestamp（ISO格式）
             ├─ timestamp_unix（纪元秒）
             ├─ node_id（节点ID）
             ├─ level（DEBUG/INFO/WARNING/ERROR/CRITICAL）
             ├─ message（日志消息）
             ├─ custom（自定义字段）
             └─ exception（异常信息）
                 │
                 └─→ nodeflow logs CLI 聚合工具
                      ├─ 实时跟踪（--follow）
                      ├─ 节点过滤（--node）
                      ├─ 级别过滤（--level）
                      ├─ 文本搜索（--search）
                      └─ 时间过滤（--since）
```

## 节点中的使用

### 基础用法

在节点代码中，日志器已经自动集成到SDK中：

```python
from nodeflow_sdk import NodeFlowSDK

def main():
    with NodeFlowSDK(log_level="INFO") as sdk:
        # sdk.logger 已经是 StructuredLogger 实例
        sdk.logger.info("节点启动")
        sdk.logger.debug("调试信息", x=10, y=20)
        sdk.logger.error("错误发生了", exc_info=True)
```

### 四个日志级别方法

```python
# DEBUG - 最低级别，仅用于调试
sdk.logger.debug("处理数据点", index=0, value=3.14)

# INFO - 通常信息
sdk.logger.info("节点初始化完成", node_name="sim_output")

# WARNING - 警告（不影响流程）
sdk.logger.warning("连接延迟过高", latency_ms=2000, threshold_ms=1000)

# ERROR - 错误（可能需要人工干预）
try:
    result = process_data(data)
except Exception as e:
    sdk.logger.error("处理失败", exc_info=True, data_size=len(data))

# CRITICAL - 严重错误（影响整个系统）
if not simulator.is_connected():
    sdk.logger.critical("仿真器离线", host="localhost", port=5555)
```

### 自定义字段

所有日志方法都支持任意的自定义字段（关键字参数）：

```python
# 简单字段
sdk.logger.info("路径规划完成",
    waypoint_count=145,
    coverage_percent=98.5)

# 复杂字段（自动转换为JSON）
sdk.logger.debug("当前状态",
    position={"x": 100.5, "y": 200.3},
    velocity=[1.0, 0.5],
    tags=["planning", "in-progress"])

# 包含异常信息
try:
    ...
except ValueError as e:
    sdk.logger.error("参数验证失败",
        exc_info=True,
        param_name="heading_angle",
        param_value=450,
        valid_range=(0, 360))
```

## CLI 日志工具

### 基本用法

```bash
# 查看最近50行日志
nodeflow logs

# 实时跟踪所有日志
nodeflow logs --follow

# 只看特定节点
nodeflow logs --node sim_output

# 只看WARNING及以上
nodeflow logs --level WARNING

# 组合过滤
nodeflow logs --node global_coverage --level ERROR --follow
```

### 详细选项

#### 1. 节点过滤 (`-n`, `--node`)

```bash
# 只看 sim_output 节点的日志
nodeflow logs --node sim_output

# 组合多个过滤（目前仅支持一个节点过滤）
nodeflow logs --node track_controller --level INFO
```

#### 2. 日志级别过滤 (`-l`, `--level`)

```bash
# 只看 INFO 及以上（包括 INFO, WARNING, ERROR, CRITICAL）
nodeflow logs --level INFO

# 只看错误
nodeflow logs --level ERROR

# 完整过滤链：track_controller 的错误
nodeflow logs --node track_controller --level ERROR
```

#### 3. 文本搜索 (`-s`, `--search`)

```bash
# 搜索包含 "error" 的日志
nodeflow logs --search error

# 搜索包含特定数据（在自定义字段中也会搜索）
nodeflow logs --search "waypoint"
```

#### 4. 时间过滤 (`--since`)

```bash
# 显示最近5分钟的日志
nodeflow logs --since "5m ago"

# 显示最近1小时的日志
nodeflow logs --since "1h ago"

# 显示最近2天的日志
nodeflow logs --since "2d ago"

# 显示特定时间之后的日志
nodeflow logs --since "2025-12-31T10:00:00"
```

#### 5. 实时跟踪 (`-f`, `--follow`)

```bash
# 像 tail -f 一样实时跟踪日志
nodeflow logs --follow

# 实时跟踪特定节点
nodeflow logs --node waypoint_selector --follow

# 实时跟踪所有警告及以上
nodeflow logs --level WARNING --follow
```

#### 6. 输出格式

```bash
# 默认格式（简洁，带彩色）
nodeflow logs

# 详细格式（包含自定义字段和异常堆栈）
nodeflow logs --detailed

# JSON格式（便于日志分析工具处理）
nodeflow logs --json

# JSON + 详细格式
nodeflow logs --detailed --json
```

#### 7. 行数控制 (`-c`, `--count`)

```bash
# 显示最后100行
nodeflow logs --count 100

# 默认显示最后50行
nodeflow logs
```

### 完整示例

#### 场景1: 调试planning_simulation场景

```bash
# 监控整个数据流
nodeflow logs examples/planning_simulation.yaml --follow

# 只看路径规划节点的问题
nodeflow logs --node global_coverage --level WARNING --follow

# 从上次失败以来的所有日志
nodeflow logs --since "30m ago" --json > debug_log.json
```

#### 场景2: 性能分析

```bash
# 查看所有节点的处理时间
nodeflow logs --search "processing_time" --detailed

# 从特定时间点开始查看
nodeflow logs --since "2025-12-31T20:00:00" --json | jq '.custom.processing_time'
```

#### 场景3: 错误排查

```bash
# 查看最近的所有错误
nodeflow logs --level ERROR --count 200

# 查看特定节点的错误（带完整堆栈）
nodeflow logs --node track_controller --level ERROR --detailed
```

## 日志文件位置

所有日志文件存储在：

```
/tmp/nodeflow/logs/
├── sim_output.jsonl
├── global_coverage.jsonl
├── track_controller.jsonl
├── waypoint_selector.jsonl
├── coord_transform.jsonl
├── rtk_filter.jsonl
├── trajectory_viz.jsonl
└── sim_input.jsonl
```

每个文件都是 JSONL 格式（每行一个JSON对象），可以直接用文本编辑器打开或用工具处理：

```bash
# 查看原始JSON
cat /tmp/nodeflow/logs/sim_output.jsonl

# 用jq过滤JSON
cat /tmp/nodeflow/logs/sim_output.jsonl | jq '.message'

# 统计各级别的日志数
cat /tmp/nodeflow/logs/*.jsonl | jq '.level' | sort | uniq -c

# 查看所有自定义字段
cat /tmp/nodeflow/logs/*.jsonl | jq '.custom'
```

## 环境变量配置

日志系统支持以下环境变量：

```bash
# 日志目录（默认 /tmp/nodeflow/logs）
export NODEFLOW_LOG_DIR=/path/to/custom/logs

# 日志级别（在SDK初始化时指定）
# 在节点代码中: NodeFlowSDK(log_level="DEBUG")
```

## 最佳实践

### 1. 关键事件记录

```python
# ✅ 好：记录关键转折点
sdk.logger.info("规划完成，开始控制",
    path_length=1000,
    estimated_time_s=300)

# ❌ 差：记录过多细节（会产生大量日志）
for i in range(1000):
    sdk.logger.debug(f"处理点 {i}")
```

### 2. 自定义字段命名

```python
# ✅ 好：使用有意义的名称
sdk.logger.debug("轨迹偏差",
    lateral_error_m=0.5,
    heading_error_rad=0.1)

# ❌ 差：使用模糊的名称
sdk.logger.debug("error", e1=0.5, e2=0.1)
```

### 3. 异常处理

```python
# ✅ 好：记录异常但继续运行
try:
    rtk_data = simulator.get_rtk()
except TimeoutError:
    sdk.logger.warning("RTK读取超时", timeout_ms=2000)
    rtk_data = last_known_rtk

# ❌ 差：异常不记录就忽略
try:
    rtk_data = simulator.get_rtk()
except:
    pass
```

### 4. 避免敏感信息

```python
# ✅ 好：只记录必要的数据
sdk.logger.info("连接成功",
    host="localhost",
    port=5555)

# ❌ 差：记录密钥或密码
sdk.logger.debug("认证信息",
    username="admin",
    password="secret123")  # 不要这样做！
```

## 故障排除

### 问题：日志文件未创建

检查日志目录权限：

```bash
# 确认目录存在且可写
ls -la /tmp/nodeflow_logs

# 如果不存在，框架会自动创建
# 如果权限有问题，修改：
chmod 755 /tmp/nodeflow_logs
```

### 问题：日志过多或过少

调整日志级别：

```python
# 在节点代码中
sdk = NodeFlowSDK(log_level="WARNING")  # 减少日志量

# 在CLI中过滤
nodeflow logs --level ERROR  # 只看错误
```

### 问题：性能影响

日志系统对性能影响很小（<1%），但如果有问题：

```python
# 减少控制台输出（只保留JSON文件）
logger = StructuredLogger(..., enable_console=False)

# 或在生产环境中改用WARNING级别
sdk = NodeFlowSDK(log_level="WARNING")
```

## 下一步

现在日志系统已经完全集成，你可以：

1. **运行planning_simulation场景**并用`nodeflow logs --follow`实时监控
2. **分析日志数据**用jq等工具处理JSON日志
3. **自定义节点日志**添加更多有意义的自定义字段

这个日志系统将大大提升调试效率！
