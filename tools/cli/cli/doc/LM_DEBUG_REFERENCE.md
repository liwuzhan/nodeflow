# NodeFlow CLI 调试参考手册

面向语言模型和边缘侧 API 调试。默认从项目根目录运行命令：

```bash
./nodeflow-cli <command> [subcommand] [options]
```

JSON 模式推荐始终开启，`--json` 可以放在顶层或子命令后：

```bash
./nodeflow-cli --json runtime status
./nodeflow-cli runtime status --json
```

## 输出契约

- JSON 数据写到 `stdout`，运行日志写到 `stderr`。程序解析时只消费 `stdout`。
- 读状态类空结果通常是正常状态，返回码为 `0`，例如 `runtime status` 的 `not_running`、`buffer list` 空目录、`logs` 空目录。
- 控制动作失败返回非零，例如无 runtime 时 `runtime start-dataflow` 返回 `1`。
- 健康检查发现不健康返回 `2`，例如 `health flow` 中 buffer 为 `MISSING` 或 `STALE`。

常见状态字段：

| 状态 | 含义 |
|------|------|
| `ok` | 命令成功，数据健康或查询成功 |
| `empty` | 查询目标为空，通常不是故障 |
| `not_running` | runtime 未运行 |
| `control_unavailable` | 控制 buffer 不可用或无接收方 |
| `timeout` | 外部服务未响应，例如仿真器 |
| `unhealthy` | 健康检查发现数据流异常 |
| `not_found` | 配置、节点、任务或 buffer 不存在 |

## 快速命令

| 问题 | 命令 |
|------|------|
| Runtime 是否运行 | `./nodeflow-cli runtime status --json` |
| 有哪些 buffer | `./nodeflow-cli buffer list --json` |
| 某个 buffer 内容 | `./nodeflow-cli buffer inspect <node.port> --json` |
| 数据流是否活跃 | `./nodeflow-cli health flow --config examples/planning_simulation.yaml --json` |
| 单次采样监控 | `./nodeflow-cli monitor --config examples/planning_simulation.yaml --iterations 1 --json` |
| 查看日志 | `./nodeflow-cli logs --json --count 50` |
| 查看节点契约 | `./nodeflow-cli node info waypoint_selector --json` |
| 刷新仿真地块 | `./nodeflow-cli simulator refresh --json` |
| 列出任务 | `./nodeflow-cli task list --json` |

## Runtime

```bash
./nodeflow-cli runtime start examples/planning_simulation.yaml --background --json
./nodeflow-cli runtime status --json
./nodeflow-cli runtime start-dataflow --json
./nodeflow-cli runtime stop-dataflow --json
./nodeflow-cli runtime restart-dataflow --json
./nodeflow-cli runtime stop --json
```

退出码语义：

| 命令 | 正常空状态 | 失败示例 |
|------|------------|----------|
| `status` | `not_running` 返回 `0` | PID 文件损坏仍应尽量结构化返回 |
| `stop` | `not_running` 返回 `0` | 进程无法停止返回 `1` |
| `start-dataflow` | 无 | runtime 未运行返回 `1` |
| `stop-dataflow` | 无 | runtime 未运行返回 `1` |
| `restart-dataflow` | 无 | runtime 未运行返回 `1` |

注意：`start-dataflow` 不会再创建假的 `runtime.control`。必须先有存活 runtime 进程和控制 buffer。

## Buffer

```bash
./nodeflow-cli buffer list --json
./nodeflow-cli buffer list --dir /tmp/nodeflow/buffers --json
./nodeflow-cli buffer inspect sim_output.rtk_fix --json
./nodeflow-cli buffer inspect sim_output.rtk_fix --raw --json
```

字段：

| 字段 | 含义 |
|------|------|
| `sequence` | 共享 buffer 序列号，增长表示有写入 |
| `length` | 当前数据长度 |
| `size_bytes` | buffer 文件大小 |
| `decoded` | MsgPack 解码后的数据 |
| `hex_preview` | `--raw` 模式的十六进制预览 |

空目录或不存在目录返回：

```json
{"status":"empty","count":0,"buffers":[]}
```

## Health

数据流活性：

```bash
./nodeflow-cli health flow --config examples/planning_simulation.yaml --json
```

状态判断：

顶层字段：

| 字段 | 含义 |
|------|------|
| `status` | 全部预期 buffer 增长时为 `ok`，否则为 `unhealthy` |
| `runtime_running` | Runtime 进程是否存在 |
| `reason` | 当 Runtime 未运行时为 `runtime_not_running` |

如果 `runtime_running=false` 且 `reason=runtime_not_running`，大量 `MISSING` 只说明 dataflow 没启动，不应直接判定为配置损坏。

buffer 状态：

| buffer 状态 | 含义 |
|-------------|------|
| `OK` | 采样窗口内 `sequence` 增长 |
| `STALE` | buffer 存在但未增长 |
| `MISSING` | buffer 文件不存在 |
| `ERROR` | buffer 读取失败 |

Schema 合规性：

```bash
./nodeflow-cli health check <node_id> --samples 10 --interval 0.1 --json
```

`health flow` 只要不是所有预期 buffer 都为 `OK`，整体 `status` 为 `unhealthy`，退出码为 `2`。

## Monitor

单次采样适合 API 调试：

```bash
./nodeflow-cli monitor --config examples/planning_simulation.yaml --iterations 1 --json
```

连续监控：

```bash
./nodeflow-cli monitor --config examples/planning_simulation.yaml --interval 0.5 --json
```

指定 buffer：

```bash
./nodeflow-cli monitor --config examples/planning_simulation.yaml --names sim_output.rtk_fix waypoint_selector.next_point --iterations 1 --json
```

JSON 模式是一行一个事件，适合流式消费。

## Logs

```bash
./nodeflow-cli logs --json --count 50
./nodeflow-cli logs --node waypoint_selector --json --count 100
./nodeflow-cli logs --level ERROR --detailed
./nodeflow-cli logs --since "5m ago" --json
./nodeflow-cli logs --follow --json
```

默认目录为 `/tmp/nodeflow/logs`。目录不存在时返回 `empty`，退出码为 `0`。

## Node

```bash
./nodeflow-cli node list --json
./nodeflow-cli node info waypoint_selector --json
```

`node info` 重点看：

- `ports.inputs`
- `ports.outputs`
- `params`
- `entrypoints`

节点不存在时 JSON 返回 `not_found`，退出码为 `1`。

## Simulator

```bash
./nodeflow-cli simulator refresh --json
./nodeflow-cli simulator refresh --host localhost --port 5555 --json
```

仿真器无响应时返回：

```json
{"status":"timeout","message":"Simulator request timed out: tcp://localhost:5555"}
```

该命令设置了 ZMQ 超时和 `LINGER=0`，失败时不应挂住进程。

## Task

```bash
./nodeflow-cli task list --json
./nodeflow-cli task show <task_id> --json
./nodeflow-cli task run task.yaml --json
./nodeflow-cli task cancel <task_id> --json
```

`task run` 会先写入任务存储，再尝试通过 runtime 控制 buffer 下发。若 runtime 未运行或控制 buffer 不可用，返回 `control_unavailable`，任务状态标记为 `failed`。

## 推荐诊断顺序

1. `./nodeflow-cli runtime status --json`
2. `./nodeflow-cli buffer list --json`
3. `./nodeflow-cli health flow --config <cfg> --json`
4. `./nodeflow-cli monitor --config <cfg> --iterations 1 --json`
5. 对异常节点执行 `logs --node <id> --json --count 100`
6. 对异常输出执行 `buffer inspect <node.port> --json`
7. 用 `node info <package> --json` 回查端口和参数契约

## 清理检查

调试结束后确认没有残留服务：

```bash
./nodeflow-cli runtime status --json || true
lsof -nP -iTCP:5555 -sTCP:LISTEN || true
lsof -nP -iTCP:8080 -sTCP:LISTEN || true
ps -ef | rg 'runtime.main|simulator/server.py|nodeflow-cli simulator refresh' || true
```
