# Runtime、SDK 与可靠性

本文说明当前 Runtime 和 SDK 的实际接口，以及节点故障时系统保存了哪些事实。节点 manifest 与源码仍是最终事实源。

## 1. 两种运行方式

### 前台单次运行

```bash
nodeflow configs/graphs/planning_simulation.yaml

# 等价形式
python3 -m edge.runtime.main configs/graphs/planning_simulation.yaml
```

该模式初始化框架后立即启动数据流，收到退出信号或 `--duration` 到期时停止。

可用参数：

```text
--log-level DEBUG|INFO|WARNING|ERROR
--duration SECONDS
--loop N
--loop-interval SECONDS
--daemon
--no-clean-buffers
```

`--loop 0` 表示无限轮次。run 目录化以后每轮本身使用新目录，`--no-clean-buffers` 主要为旧脚本保留。

### 守护模式

```bash
nodeflow-cli runtime start configs/graphs/planning_simulation.yaml --background
nodeflow-cli runtime start-dataflow
nodeflow-cli runtime status
nodeflow-cli runtime restart-dataflow
nodeflow-cli runtime stop-dataflow
nodeflow-cli runtime stop
```

`runtime start --background` 启动 `edge.runtime.main --daemon`。Daemon 初始化图和控制面，但等待显式的 `start-dataflow` 命令；因此框架进程可以跨多轮数据流保持运行。

## 2. Runtime YAML

最小图配置：

```yaml
graph_id: rtk_filter_demo
graph_version: 1
node_hub_path: ./edge/nodes

nodes:
  - id: rtk_source
    package: sensing/rtk_driver
    params:
      source_type: network

  - id: rtk_filter
    package: sensing/rtk_filter
    params:
      alpha_pos: 0.2

edges:
  - from: rtk_source.rtk_fix
    to: rtk_filter.rtk_fix

restart_policy:
  max_retries: 3
  backoff_ms: 500
```

| 字段 | 含义 |
|---|---|
| `graph_id`, `graph_version` | 图身份与版本 |
| `node_hub_path` | manifest 扫描根目录，当前默认 `./edge/nodes` |
| `nodes[].id` | 图内唯一实例 ID，也是 buffer 与日志身份的一部分 |
| `nodes[].package` | 相对 Node Hub 的包路径 |
| `nodes[].params` | 传给节点的参数；受 manifest 类型和默认值约束 |
| `nodes[].entrypoint` | 可选的实例级入口覆盖 |
| `edges[].from/to` | `节点ID.端口名` 形式的数据连接 |
| `restart_policy` | 节点退出后的最大重试次数和退避基数 |

Runtime 检查重复 ID、无效节点引用、manifest/端口存在性和图结构。端口 `type` 用于离线兼容性提示，目前类型不匹配是警告，不是强制阻断。

## 3. 节点 manifest

每个可注册节点目录必须有 `node.yaml`：

```yaml
name: example_filter
version: "1.0"
description: "示例滤波节点"

entrypoints:
  linux:
    kind: python
    cmd: ["python3", "run.py"]

ports:
  inputs:
    - name: source
      type: sensor.example
  outputs:
    - name: filtered
      type: sensor.example
      buffer_size: 1048576

params:
  alpha:
    type: float
    default: 0.2

readiness: heartbeat
input_watchdog:
  source: 1.0
```

关键约束：

- 入口按平台选择；当前主要入口为 Python 脚本。
- 输入和输出端口名在一个 manifest 内不能重复或交叉。
- `buffer_size` 默认 1 MiB；双方需要使用一致的输出 buffer 尺寸。
- `readiness` 默认 `heartbeat`；静态生产者可以选择 `first_output`。
- `input_watchdog` 只适用于应持续写入的输入。静态配置或一次性消息不应声明超时。

## 4. 使用 NodeFlowSDK 开发节点

节点不是继承某个 `Node` 基类，而是在入口脚本中创建 `NodeFlowSDK`：

```python
import time

from edge.sdk.nodeflow_sdk import NodeFlowSDK


def main() -> None:
    with NodeFlowSDK() as sdk:
        source = sdk.create_input_port("source")
        filtered = sdk.create_output_port("filtered")
        alpha = float(sdk.get_param("alpha", 0.2))
        previous = None

        while True:
            data = source.recv_latest()
            if data is not None:
                value = float(data["value"])
                previous = value if previous is None else alpha * value + (1 - alpha) * previous
                filtered.send({"value": previous, "timestamp": time.time()})
            time.sleep(0.01)


if __name__ == "__main__":
    main()
```

Runtime 通过环境变量把节点 ID、参数、端口映射、run 身份、IPC 版本和日志目录注入进程。节点不应自行拼接其他节点的 buffer 路径。

常用 API：

| API | 用途 |
|---|---|
| `get_param(key, default)` | 读取可选参数 |
| `require_param(key)` | 读取必填参数，不存在时抛错 |
| `create_input_port(name)` | 根据 Runtime 注入的连接创建输入端口 |
| `create_output_port(name, schema=None)` | 创建输出端口，可附 Pydantic schema |
| `InputPort.recv_latest()` | 读取新的最新快照；无新数据时返回空值 |
| `OutputPort.send(data)` | 写入字典或 Pydantic 模型 |
| `set_on_input_lost(name, handler)` | 覆盖输入看门狗的默认死亡行为 |
| `die(reason, code=1)` | 写出结构化遗言并硬退出整个进程 |
| `shutdown()` | 停止健康/父进程看门狗并关闭端口 |

SDK 自动发布 `<node_id>.metadata` 和 `<node_id>.health`，并写结构化节点日志。

## 5. SharedBuffer IPC

SharedBufferLite 使用 mmap 文件和 MsgPack payload。当前头部为 16 字节：

| 字段 | 大小 | 含义 |
|---|---:|---|
| sequence | 4 bytes | 写入序列号 |
| length | 4 bytes | payload 长度；写入期间使用 tombstone 状态 |
| write timestamp | 8 bytes | 单调时钟写入时间 |

主要语义：

- 单输出端写、多个输入端读；
- 新值覆盖旧值，读取端按序列号判断是否有更新；
- tombstone 协议避免读到半写 payload；
- 输入端检测 buffer 缺失、inode/尺寸变化、序列大幅回退或时间戳倒退后重开；
- Pydantic schema 校验可通过 `NODE_SCHEMA_VALIDATION=off|loose|strict` 控制。

它不是消息日志。控制算法若必须处理每一个样本，应另行使用带队列或持久化的传输机制。

## 6. 启动就绪与健康

Runtime 按拓扑层启动。每层启动后每 100 ms 检查：

- 子进程是否立即退出；若退出则本层失败并回滚；
- `heartbeat` 模式下，节点健康缓冲区是否存在且新鲜；
- `first_output` 模式下，所有输出 buffer 是否已有首个值。

每层默认最多等待 30 秒。当前实现超时后记录警告并继续启动下一层，因此“启动完成”不等于所有节点业务数据都已有效。实机流程应再执行运行态健康检查。

健康 payload 包含节点、`run_id`、`incarnation`、心跳时间，以及输入连接、最后序列和源写入年龄。常用检查：

```bash
nodeflow-cli status
nodeflow-cli health status NODE_ID
nodeflow-cli health check NODE_ID
nodeflow-cli health flow --config CONFIG.yaml
```

## 7. 崩溃、重启与断流

### 进程退出

NodeMonitor 每秒检查节点进程。退出后：

1. 抢救最多 500 字符的 stderr 尾部；
2. 增加失败计数并写事故记录；
3. 检查死亡节点的输出 buffer，损坏时改名为 `.dead.<incarnation>.buf` 留证；
4. 在重试预算内按退避时间调度重启；
5. 稳定运行 300 秒后清除该节点的旧失败计数。

重启回调本身失败也会消耗同一重试预算，不会静默放弃。

### 输入断流

InputPort 自身负责 buffer 重新打开和世代重同步。对 manifest 明确声明的持续输入，SDK 还会检查源端写入年龄：

- 有自定义 `on_input_lost` 时调用处理器，例如先把执行器置于安全值；
- 没有处理器时调用 `sdk.die()`，使故障变为可观察的进程退出；
- 处理器抛错时升级为 `die()`。

### Runtime 自身退出

节点 SDK 默认监控父进程。父进程消失时节点会退出，减少孤儿节点。Runtime 正常停止会先清理数据流；异常退出时注册的紧急清理尽力终止仍存活的子进程组。

Runtime 停节点发送 SIGTERM（5 秒后 SIGKILL）。SDK 在主线程把 SIGTERM 转为 `SystemExit(143)`，节点的 `finally` 与上下文退出照常执行——`pwm_driver` 依此在停止时回中位；Python 默认的 SIGTERM 处理会直接终止进程、跳过这些清理，sysfs PWM 会保持最后脉宽。节点自带 SIGTERM 处理器时 SDK 不覆盖。父进程看门狗同样先走这条路径，3 秒内主线程未退出才硬退出。退出码 143 在死亡记录中仍记为 `signal: 15`。节点主循环不要用裸 `except:` 或 `except BaseException`，否则会吞掉该退出。

SIGKILL、段错误等无法执行清理的死亡，由图级 `safety_resources` 绑定兜底（`pwm_driver` 死亡后 runtime 直接写 sysfs 回中）。实车图已声明该绑定但保持 `dry_run: true`，台架确认极性与周期后再启用。

这些机制不能替代独立硬件急停和失能设计。

## 8. 死亡记录与运行现场

死亡记录不放在 `/tmp`。目录解析顺序：

1. `NODEFLOW_INCIDENT_DIR`；
2. `$XDG_STATE_HOME/nodeflow/incidents`；
3. `~/.local/state/nodeflow/incidents`；
4. 可写时的 `/var/lib/nodeflow/incidents`。

主文件为 `incidents.jsonl`，默认最多保留 1000 条且淘汰 30 天以前的记录。每条记录包含：

- 时间、`run_id`、节点、package、incarnation、重试次数；
- 退出码或 POSIX signal；
- stderr 尾部；
- 节点最后 health 中冻结的输入观测（`will`）；
- Runtime 检测时看到的输入/输出写入年龄（`witness`）；
- 被隔离的损坏 buffer 文件名。

`nodeflow-cli status` 会展示最近事故摘要。

业务数据目录默认是 `/tmp/nodeflow/runs/<run_id>/buffers`。Runtime 保留最近 5 个 run 目录；带事故的旧 run 在剪除前，会把不超过 256 KiB 的最后 payload 快照到事故目录的 `snapshots/<run_id>/`。这是有限的现场留存，不是完整时间序列。

## 9. 路径与环境变量

| 变量/路径 | 用途 |
|---|---|
| `NODEFLOW_RUNTIME_ROOT` | 覆盖运行时根目录，默认 `/tmp/nodeflow` |
| `NODEFLOW_BUFFERS_DIR` | 节点侧当前 run buffer 目录；通常由 Runtime 注入 |
| `NODEFLOW_LOG_DIR` | 节点结构化日志目录 |
| `NODEFLOW_INCIDENT_DIR` | 持久死亡记录目录 |
| `NODE_SCHEMA_VALIDATION` | 输出 schema 校验模式 |
| `/tmp/nodeflow_runtime.pid` | Runtime PID、图、run 和 buffer 目录的 JSON 元数据 |
| `/tmp/nodeflow_runtime.log` | CLI 后台启动时的 Runtime stdout/stderr |

部署到可能把 `/tmp` 映射为 tmpfs 的机器时，应明确设置 `NODEFLOW_RUNTIME_ROOT`；事故目录仍应选择可跨重启保存的磁盘位置。

## 10. 可靠性保证的边界

当前机制直接解决的是：

- 单节点崩溃的进程隔离和有限重启；
- 输入端重连与当前状态重新同步；
- Runtime/节点身份代际区分；
- 故障后能回答“谁死了、何时死、退出方式、最后看到了什么”；
- 损坏输出 buffer 的隔离和有限现场保留。

当前机制不保证：

- 节点内部状态自动恢复、事务回滚或确定性重放；
- 所有下游在上游重启期间保持业务正确；
- 网络分区下的分布式一致性；
- 错误配置、错误控制算法或传感器可信度；
- 执行器安全状态一定由软件完成。

因此，可靠性验证应同时覆盖进程死亡、数据陈旧、错误输出、Runtime 死亡、机器断电和硬件失控，而不只检查“进程能否自动拉起”。
