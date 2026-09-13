# NodeFlow CLI 完整参考

## 命令结构

```
python3 -m tools.cli.core.cli <command> [subcommand] [options]
```

全局选项：
- `--version` - 显示版本号
- `--verbose, -v` - 显示堆栈跟踪
- `--json` - JSON 格式输出

## 1. runtime - 运行时框架控制

### start - 启动框架
```bash
python3 -m tools.cli.core.cli runtime start <config> [options]

选项:
  --background, -b      后台运行
  --log-level LEVEL     DEBUG|INFO|WARNING|ERROR (默认 INFO)
  --no-clean-buffers    禁用启动前清理缓冲区
  --json                JSON 输出
```

### status - 查看状态
```bash
python3 -m tools.cli.core.cli runtime status

输出:
  - 运行状态 (running/not_running)
  - PID
  - 内存使用
  - 启动时间
  - 运行时长
```

### start-dataflow - 启动数据流
```bash
python3 -m tools.cli.core.cli runtime start-dataflow
```
通过控制缓冲区发送启动命令，不重启框架。

### stop-dataflow - 停止数据流
```bash
python3 -m tools.cli.core.cli runtime stop-dataflow
```

### restart-dataflow - 重启数据流
```bash
python3 -m tools.cli.core.cli runtime restart-dataflow
```

### stop - 停止框架
```bash
python3 -m tools.cli.core.cli runtime stop
```
先 SIGTERM，10秒后 SIGKILL。

---

## 2. logs - 日志查看

```bash
python3 -m tools.cli.core.cli logs [config] [options]

选项:
  --log-dir DIR       日志目录 (默认 /tmp/nodeflow_logs)
  -n, --node ID       过滤特定节点 ID
  -l, --level LEVEL   DEBUG|INFO|WARNING|ERROR|CRITICAL
  -s, --search TEXT   搜索文本
  --since TIME        时间过滤 (如 "5m ago", "1h ago")
  -f, --follow        实时跟踪 (tail -f)
  --json              JSON 格式
  --detailed          详细格式 (包含自定义字段)
  -c, --count N       显示最后 N 行 (默认 50)
```

### 日志格式
```json
{
  "timestamp": "2025-01-02T10:30:45.123Z",
  "level": "INFO",
  "node_id": "waypoint_selector",
  "message": "Received 10 waypoints",
  "extra": {}
}
```

---

## 3. buffer - 缓冲区诊断

### list - 列出缓冲区
```bash
python3 -m tools.cli.core.cli buffer list --dir DIR

输出:
  - 缓冲区名称
  - 文件大小
  - 当前序列号
  - 数据长度
```

### inspect - 查看内容
```bash
python3 -m tools.cli.core.cli buffer inspect <name> [options]

选项:
  --dir DIR     缓冲区目录 (默认 /tmp/nodeflow/buffers)
  --raw         十六进制原始字节，不尝试解码
```

缓冲区命名: `sim_output.rtk_fix` 或文件名不含扩展名。

---

## 4. health - 健康检查

### check - Schema 合规性检查
```bash
python3 -m tools.cli.core.cli health check <node_id> [options]

选项:
  --samples N       采样数量 (默认 10)
  --interval SEC    采样间隔秒数 (默认 0.1)
  --json            JSON 输出
```
连接节点 Metadata Buffer，校验输出数据是否符合 Schema。

### flow - 数据流活性检查
```bash
python3 -m tools.cli.core.cli health flow --config CONFIG [options]

选项:
  --config PATH     配置文件路径 (必需)
  --interval SEC    采样间隔 (默认 1.0)
  --dir DIR         缓冲区目录
  --json            JSON 输出
```
解析配置文件，检测预期缓冲区是否存在并在时间窗口内增长。

---

## 5. node - 节点管理

### list - 列出节点
```bash
python3 -m tools.cli.core.cli node list [options]

选项:
  --hub-path PATH   节点库路径 (默认 ./node-hub)
  --sort ORDER      name|version (默认 name)
  --json            JSON 输出
```

### info - 节点详情
```bash
python3 -m tools.cli.core.cli node info <package> [options]

选项:
  --hub-path PATH   节点库路径
  --verbose         详细信息

示例:
  python3 -m tools.cli.core.cli node info waypoint_selector
  python3 -m tools.cli.core.cli node info simulation/target_generator
```

---

## 6. monitor - 实时监控

```bash
python3 -m tools.cli.core.cli monitor --config CONFIG [options]

选项:
  --names NAME [NAME ...]  要监控的缓冲区名称列表
  --interval SEC           采样间隔 (默认 1.0)
  --iterations N           迭代次数 (0 = 无限)
  --json                   JSON 事件输出

示例:
  python3 -m tools.cli.core.cli monitor --config examples/planning_simulation.yaml --names sim_output.rtk_fix sim_output.gnss_fix
```

---

## 7. simulator - 仿真器控制

### refresh - 刷新地块
```bash
python3 -m tools.cli.core.cli simulator refresh [options]

选项:
  --host HOST   仿真器主机 (默认 localhost)
  --port PORT   仿真器端口 (默认 5555)
```
请求仿真器重新生成地块并重置初始位置。

---

## 内部机制

### 运行时 PID 文件
`/tmp/nodeflow_runtime.pid` 格式：
```
<pid>
<start_time_timestamp>
```

### 控制缓冲区
名称: `runtime.control`

命令格式:
```python
{
  "command": "start_dataflow" | "stop_dataflow",
  "timestamp": <unix_timestamp>
}
```

### 信号处理
- SIGTERM (15): 优雅停止
- SIGKILL (9): 强制杀死（10秒后）

### 停止序列
1. 发送 SIGTERM
2. 等待最多 10 秒
3. 如果未退出，发送 SIGKILL
