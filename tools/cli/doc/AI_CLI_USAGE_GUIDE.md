# NodeFlow AI Agent CLI 使用指南

本文档说明 AI Agent 和边缘侧 API 如何使用 NodeFlow CLI 做状态检查、任务下发和故障复盘。

## 基本约定

从项目根目录调用：

```bash
./nodeflow-cli <command> [subcommand] [options]
```

推荐所有自动化调用都使用 `--json`：

```bash
./nodeflow-cli runtime status --json
./nodeflow-cli --json runtime status
```

两种写法都有效。JSON 输出写到 `stdout`，运行日志写到 `stderr`。

## 退出码约定

| 类型 | 退出码 | 示例 |
|------|--------|------|
| 查询成功或正常空状态 | `0` | `runtime status` 返回 `not_running`，`buffer list` 返回空 |
| 命令执行失败 | `1` | runtime 未运行时执行 `start-dataflow`，节点不存在 |
| 健康检查不通过 | `2` | `health flow` 发现 `MISSING` 或 `STALE` |

API 调用建议同时判断退出码和 JSON 里的 `status` 字段。

## 命令总览

| 命令 | 用途 |
|------|------|
| `node` | 查看节点库和节点契约 |
| `buffer` | 查看共享 buffer 文件和内容 |
| `health` | 检查数据流活性和 Schema 合规性 |
| `monitor` | 周期采样 buffer 状态 |
| `runtime` | 启停 runtime 和 dataflow |
| `task` | 本地任务下发、查询和取消 |
| `logs` | 聚合节点结构化日志 |
| `simulator` | 控制外部仿真器 |

## 标准诊断流程

### 1. 判断 runtime 是否存在

```bash
./nodeflow-cli runtime status --json
```

典型结果：

```json
{"status":"not_running","pid":null}
```

`not_running` 对 `status` 命令是正常查询结果，退出码为 `0`。

### 2. 查看 buffer 面

```bash
./nodeflow-cli buffer list --json
```

关注：

- `count`: 当前 buffer 数量
- `sequence`: 是否增长
- `length`: 是否有数据
- `status`: 是否有读取错误

查看具体内容：

```bash
./nodeflow-cli buffer inspect sim_output.rtk_fix --json
```

### 3. 检查数据流活性

```bash
./nodeflow-cli health flow --config examples/planning_simulation.yaml --json
```

整体返回：

- `status: ok`: 所有预期 buffer 在采样窗口内增长
- `status: unhealthy`: 至少一个预期 buffer 为 `MISSING`、`STALE` 或 `ERROR`
- `runtime_running`: 当前 Runtime 进程是否存在
- `reason: runtime_not_running`: Runtime 未运行；此时大量 `MISSING` 通常只表示 dataflow 尚未启动，不等价于图配置损坏

单 buffer 状态：

| 状态 | 含义 |
|------|------|
| `OK` | 序列号增长 |
| `STALE` | buffer 存在但未增长 |
| `MISSING` | buffer 不存在 |
| `ERROR` | 读取失败 |

### 4. 单次采样用于复盘

```bash
./nodeflow-cli monitor --config examples/planning_simulation.yaml --iterations 1 --json
```

如果只关心部分 buffer：

```bash
./nodeflow-cli monitor --config examples/planning_simulation.yaml \
  --names sim_output.rtk_fix waypoint_selector.next_point \
  --iterations 1 --json
```

### 5. 回查日志

```bash
./nodeflow-cli logs --json --count 100
./nodeflow-cli logs --node waypoint_selector --json --count 100
./nodeflow-cli logs --level ERROR --detailed
./nodeflow-cli logs --since "5m ago" --json
```

默认日志目录为 `/tmp/nodeflow/logs`。目录不存在时返回 `empty`，退出码为 `0`。

### 6. 回查节点契约

```bash
./nodeflow-cli node list --json
./nodeflow-cli node info waypoint_selector --json
```

重点看 `ports.inputs`、`ports.outputs`、`params` 和 `entrypoints`。

## Runtime 控制

启动后台 runtime：

```bash
./nodeflow-cli runtime start examples/planning_simulation.yaml --background --json
```

启动数据流：

```bash
./nodeflow-cli runtime start-dataflow --json
```

停止数据流但保留 runtime：

```bash
./nodeflow-cli runtime stop-dataflow --json
```

重启数据流：

```bash
./nodeflow-cli runtime restart-dataflow --json
```

停止 runtime：

```bash
./nodeflow-cli runtime stop --json
```

注意：`start-dataflow`、`stop-dataflow`、`restart-dataflow` 要求 runtime 已运行。若 runtime 未运行，返回 `not_running` 且退出码为 `1`。CLI 不会创建假的 `runtime.control` 来伪装成功。

## Task 下发

```bash
./nodeflow-cli task run task.yaml --json
./nodeflow-cli task list --json
./nodeflow-cli task show <task_id> --json
./nodeflow-cli task cancel <task_id> --json
```

`task run` 会确认 runtime 进程存活。若只有旧的 `runtime.control.buf` 残留但没有 runtime 进程，返回：

```json
{
  "status": "control_unavailable",
  "message": "Runtime control buffer is not available"
}
```

同时任务状态会标记为 `failed`，便于后续 `task list` 和 `task show` 复盘。

## Simulator

```bash
./nodeflow-cli simulator refresh --json
```

无仿真器或端口不通时，命令应在约 2 秒内返回：

```json
{"status":"timeout","message":"Simulator request timed out: tcp://localhost:5555"}
```

这表示调试工具正常，问题是外部仿真器未响应。

## 常见判断

| 现象 | 判断 | 下一步 |
|------|------|--------|
| `runtime status` 为 `not_running` | runtime 未启动 | 启动 runtime 或只做静态检查 |
| `buffer list` 为 `empty` | 没有共享 buffer 文件 | 检查 runtime/dataflow 是否启动 |
| `health flow` 为 `MISSING` | 预期节点未写 buffer | 查 runtime 日志和节点启动日志 |
| `health flow` 为 `STALE` | 节点可能卡住或无输入 | 查上游 buffer 和节点日志 |
| `simulator refresh` 为 `timeout` | 仿真器没起来或端口不通 | 检查 5555 端口 |
| `task run` 为 `control_unavailable` | runtime 控制面不可用 | 先 `runtime status` |

## 结束调试后的清理检查

```bash
./nodeflow-cli runtime status --json || true
lsof -nP -iTCP:5555 -sTCP:LISTEN || true
lsof -nP -iTCP:8080 -sTCP:LISTEN || true
ps -ef | rg 'runtime.main|simulator/server.py|nodeflow-cli simulator refresh' || true
```

如果本轮启动了 runtime，结束时执行：

```bash
./nodeflow-cli runtime stop --json
```

## 相关实现和测试

| 路径 | 内容 |
|------|------|
| `nodeflow-cli` | 项目根 CLI 入口 |
| `tools/cli/core/cli.py` | 参数解析和命令路由 |
| `tools/cli/commands/` | 各子命令实现 |
| `tools/cli/utils/output.py` | JSON 和错误输出辅助 |
| `runtime/task/executor.py` | 任务下发 runtime 存活检查 |
| `tests/unit/test_cli_tools.py` | CLI 行为单元测试 |
| `tools/cli/doc/LM_DEBUG_REFERENCE.md` | 语言模型速查参考 |
