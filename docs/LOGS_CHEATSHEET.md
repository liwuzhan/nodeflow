# NodeFlow 日志系统快速参考

## 在节点代码中使用

```python
from nodeflow_sdk import NodeFlowSDK

with NodeFlowSDK(log_level="INFO") as sdk:
    # 基本日志
    sdk.logger.info("消息")
    sdk.logger.debug("调试", x=10, y=20)
    sdk.logger.warning("警告", threshold=100)
    sdk.logger.error("错误", exc_info=True)
    sdk.logger.critical("严重")
```

## 日志级别

| 级别 | 用途 | 示例 |
|------|------|------|
| DEBUG | 调试信息 | `sdk.logger.debug("数据点", index=0)` |
| INFO | 普通信息 | `sdk.logger.info("节点启动")` |
| WARNING | 警告 | `sdk.logger.warning("延迟高", ms=2000)` |
| ERROR | 错误 | `sdk.logger.error("失败", exc_info=True)` |
| CRITICAL | 严重 | `sdk.logger.critical("离线")` |

## CLI 快速命令

```bash
# 基础
nodeflow logs                          # 最近50行
nodeflow logs --follow                 # 实时跟踪

# 过滤
nodeflow logs --node sim_output        # 节点过滤
nodeflow logs --level ERROR            # 级别过滤
nodeflow logs --search error           # 文本搜索
nodeflow logs --since "5m ago"         # 时间过滤

# 输出
nodeflow logs --detailed               # 显示自定义字段
nodeflow logs --json                   # JSON格式
nodeflow logs --count 100              # 显示最后100行

# 组合
nodeflow logs --node track_controller --level ERROR --follow
```

## 日志文件位置

```
/tmp/nodeflow/logs/
├── sim_output.jsonl           # 仿真器输出日志
├── global_coverage.jsonl      # 路径规划日志
├── track_controller.jsonl     # 轨迹控制日志
└── ...                        # 其他节点
```

## JSON 日志格式

```json
{
  "timestamp": "2025-12-31T21:59:48.474000",
  "timestamp_unix": 1735689588.474,
  "node_id": "sim_output",
  "level": "INFO",
  "message": "仿真器连接成功",
  "logger": "nodeflow.node.sim_output",
  "module": "run",
  "function": "__init__",
  "line": 45,
  "custom": {
    "host": "localhost",
    "port": 5555
  }
}
```

## 场景速查

### 查看planning_simulation运行日志
```bash
nodeflow logs examples/planning_simulation.yaml --follow
```

### 调试特定节点
```bash
nodeflow logs --node global_coverage --level DEBUG --follow
```

### 查看所有错误
```bash
nodeflow logs --level ERROR --detailed
```

### 导出日志用于分析
```bash
nodeflow logs --json > logs.jsonl
cat logs.jsonl | jq '.custom.processing_time'
```

## 常见自定义字段示例

```python
# 坐标系统
sdk.logger.debug("位置更新",
    x=100.5, y=200.3, theta=1.57)

# 性能指标
sdk.logger.info("处理完成",
    processing_time_ms=23.4,
    waypoint_count=145)

# 状态转换
sdk.logger.info("状态切换",
    from_state="planning",
    to_state="controlling",
    reason="path_ready")

# 配置参数
sdk.logger.debug("参数设置",
    max_speed=1.0,
    heading_p_gain=2.0,
    min_turn_radius_m=2.0)
```

## 故障排查

| 问题 | 解决方案 |
|------|--------|
| 日志文件未创建 | 检查 `/tmp/nodeflow_logs/` 权限 |
| 日志过多 | 使用 `--level WARNING` 减少输出 |
| 找不到特定日志 | 用 `--search` 文本搜索或 `--json` 导出 |
| 性能受影响 | 日志对性能影响<1%，通常不是问题 |

---

**更多详情**: 见 `docs/STRUCTURED_LOGGING_GUIDE.md`
