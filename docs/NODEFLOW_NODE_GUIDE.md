# NodeFlow 节点开发指南（AI 优先）

本文档放在仓库根目录，目标是：让开发者与 AI 只看这一份，就能按统一范式开发/改造节点，并能用最小上下文完成测试与调试。

相关详细文档（深入版）：

- docs/节点开发规范.md
- docs/4_LAYER_ARCHITECTURE_PRACTICE.md
- docs/NODE_TESTING_GUIDE.md
- docs/ZMQ_HYBRID_IPC_IMPLEMENTATION.md

---

## 1. 框架特点（用来指导设计决策）

### 1.1 配置驱动的 DAG 数据流

- 节点拓扑与连线由 YAML 描述（nodes/edges），代码不写“管道”
- 节点之间通过端口交换数据，跨节点协作必须通过数据契约完成

### 1.2 进程隔离 + Latest-Value 语义

- 每个节点是独立进程
- 端口默认只保留“最新值”，没有队列语义
- 这要求节点逻辑“可重复、可降级”：输入可能缺失、可能跳帧、可能只拿到最后一条

### 1.3 混合 IPC：共享缓冲区 + ZMQ 通知

- 输出端口：写入共享 buffer（持久化最新值）+ 发送 ZMQ 通知
- 输入端口：监听 ZMQ 通知 + 从共享 buffer 读取最新值
- 目标是解决分层启动与 late joiner 的数据丢失问题

### 1.4 查表式调试（Debug = Inspect Data）

- 关键定位手段不是“追代码执行流”，而是“查数据板状态”
- buffer 的存在性、序列号增长、内容摘要，是最可靠的一线事实

---

## 2. 你需要记住的边界

### 2.1 仓库关键目录

- runtime/：启动、编排、监控（生命周期）
- sdk/：节点开发 API（创建端口、收发数据、参数读取）
- node-hub/：节点包库（每个目录一个可运行节点包）
- examples/：运行场景 YAML
- tools/cli/：buffer/health/monitor 等调试工具

### 2.2 节点开发的禁止项（降低 AI 犯错概率）

- 禁止节点 A import 其它节点包的代码（包括对方的 run.py/utils）
- 禁止为了“等另一个节点启动”而阻塞等待
- 禁止把外设通信、框架 I/O、算法计算混成一坨

---

## 3. 节点包最小结构（推荐）

```text
node-hub/<your_node>/
├── node.yaml
├── run.py
├── atom.py                # 推荐：纯函数算法（可选）
├── contracts/             # 推荐：契约样例（可选）
│   ├── in_xxx.example.json
│   └── out_xxx.example.json
└── test/                  # 推荐：pytest
    ├── test_atom.py
    └── test_node.py
```

设计意图：让 AI 只读一个目录就能改对；让测试不依赖 Runtime/仿真。

---

## 4. node.yaml：把“契约”写清楚

### 4.1 最小模板

```yaml
name: your_node
version: "1.0"
description: "一句话说明节点做什么"

entrypoints:
  linux:
    kind: python
    cmd: ["python3", "run.py"]
  darwin:
    kind: python
    cmd: ["python3", "run.py"]
  windows:
    kind: python
    cmd: ["python", "run.py"]

ports:
  inputs:
    - name: input_a
      type: json
      description: |
        输入契约：字段/单位/坐标系
        example: {"x": 1.0, "y": 2.0}
  outputs:
    - name: output_b
      type: json
      description: |
        输出契约：字段/单位/枚举值
        example: {"ok": true, "state": "TRACKING"}

params:
  update_hz:
    type: float
    default: 20
    description: "主循环频率"
```

### 4.2 AI 友好的契约写法

- 固定字段名与枚举值（例如 state: WAITING_FOR_INPUT | TRACKING | TARGET_REACHED）
- 明确单位与坐标系（米/度、ENU/WGS84 等）
- 给最小可运行的 example（越短越好）

---

## 5. run.py：只做收发、参数、状态、调用算法

### 5.1 最小骨架

```python
#!/usr/bin/env python3

import sys
import time
from pathlib import Path

project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from sdk.nodeflow_sdk import NodeFlowSDK


def main():
    with NodeFlowSDK(log_level="INFO") as sdk:
        p = sdk.params
        hz = float(p.get("update_hz", 20))
        period = 1.0 / max(hz, 1e-6)

        in_a = sdk.create_input_port("input_a")
        out_b = sdk.create_output_port("output_b")

        while True:
            data = in_a.recv_latest()
            if not data:
                out_b.send({"state": "WAITING_FOR_INPUT"})
                time.sleep(period)
                continue

            result = {"state": "RUNNING"}
            out_b.send(result)
            time.sleep(period)


if __name__ == "__main__":
    main()
```

### 5.2 关键约束

- 默认非阻塞：用 recv_latest()，输入缺失就降级/跳过/输出状态
- 等待允许存在，但必须有 timeout、降级路径与可观测状态
- 节点对“启动顺序”不应有假设

---

## 6. atom.py：把算法做成纯函数（推荐）

目的：让 AI 改算法几乎不会引入框架副作用，且单测毫秒级。

要求：

- 不 import sdk.* / runtime.* / zmq / fastapi / serial 等
- 输入输出尽量是 dict/tuple/number 等简单结构

---

## 7. 测试：不启动 Runtime 也能验证

### 7.1 L4（atom）单元测试

- 针对纯函数输入输出断言
- 不依赖 SDK、不依赖系统环境

### 7.2 L3（run）MockSDK 测试

NodeFlow 提供 `sdk/test_utils`，用于隔离测试节点数据流。

示例（伪代码）：

```python
from sdk.test_utils import MockNodeFlowSDK

def test_node_dataflow():
    sdk = MockNodeFlowSDK({"update_hz": 20})
    in_a = sdk.create_input_port("input_a")
    out_b = sdk.create_output_port("output_b")

    in_a.set_data({"x": 1.0})
    assert in_a.recv_latest() == {"x": 1.0}

    out_b.send({"state": "RUNNING"})
    assert out_b.get_last_send_data()["state"] == "RUNNING"
```

---

## 8. 调试：用数据板缩短定位路径

### 8.1 CLI 查 buffer（推荐一线手段）

```bash
python3 -m tools.cli.core.cli buffer list
python3 -m tools.cli.core.cli buffer inspect sim_output.rtk_fix
python3 -m tools.cli.core.cli health --config examples/planning_simulation.yaml
python3 -m tools.cli.core.cli monitor --config examples/planning_simulation.yaml
```

### 8.2 旁路观测节点

把关键输出同时连到 logger 之类的旁路节点，用 Web 页面实时查看数据变化。

---

## 9. 改一个节点的验收清单（AI 必须满足）

- 端口名与 node.yaml 完全一致，收发 API 使用 recv_latest()/send()
- run.py 只做收发、参数、状态、调用 atom，不混入算法细节
- 算法放入 atom.py（或等价纯函数模块），无框架依赖
- 输入缺失/异常时有明确降级策略与可观测状态输出
- 至少包含一个 atom 单测与一个 MockSDK 数据流测试
