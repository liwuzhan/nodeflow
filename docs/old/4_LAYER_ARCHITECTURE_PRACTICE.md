# NodeFlow 4层架构实践指南：打破依赖链的黑盒

## 1. 背景与痛点

在复杂的分布式机器人系统（如 NodeFlow）开发中，我们经常面临以下挑战，导致 AI 辅助编程效率低下：

1.  **依赖链模糊 (Implicit Dependencies)**：节点 A 依赖 B，B 依赖 C。当系统出现故障（如“车不走”），调试需要跨越多个进程和代码库，上下文极深，AI 容易“幻觉”。
2.  **调试困难 (Debug Hell)**：为了验证一个核心算法（如路径跟踪），必须启动仿真器、Runtime、通信层等整个笨重的环境。
3.  **状态分散 (Scattered State)**：业务逻辑与通信逻辑耦合，状态散落在各个节点的 `self.variable` 中，难以复现 Bug。

**4层架构（4-Layer Architecture）** 旨在通过极致的**解耦**和**分层**，将网状的依赖关系转化为扁平的层级关系，实现“99% 代码由 AI 生成且无 Bug，1% 核心逻辑人工把控”。

### 1.1 适用范围（对齐现状）

本指南主要约束和优化的是 NodeFlow 的“节点开发”部分，目标是让 AI 能在最小上下文下完成高质量改动：

- 本指南关注 `node-hub/<node>/` 内部的可维护性与可测试性
- 运行时启动与编排属于 `runtime/`（本指南只给出边界与接口要求）
- 数据总线与“查表式调试”在现状实现中由“共享缓冲区文件 + ZMQ 通知 + YAML 图配置”共同构成
- 节点声明文件是 `node.yaml`，拓扑与连线是 `runtime.yaml`（或 examples 下的 YAML）

相关实现与规范建议同时参考：

- [runtime/main.py](file:///Users/wuzhanli/Desktop/node/runtime/main.py)
- [port.py](file:///Users/wuzhanli/Desktop/node/sdk/port.py)
- [ZMQ_HYBRID_IPC_IMPLEMENTATION.md](file:///Users/wuzhanli/Desktop/node/docs/ZMQ_HYBRID_IPC_IMPLEMENTATION.md)
- [节点开发规范.md](file:///Users/wuzhanli/Desktop/node/docs/%E8%8A%82%E7%82%B9%E5%BC%80%E5%8F%91%E8%A7%84%E8%8C%83.md)

---

## 2. 核心架构定义

我们将系统自下而上划分为 4 层，每层有严格的职责边界和依赖规则。

### L4 原子层 (Atoms) —— "绝对真理"
*   **定义**：最小粒度的业务逻辑单元，通常体现为**纯函数 (Pure Functions)**。
*   **特征**：
    *   **无副作用**：输入相同，输出必然相同。
    *   **无框架依赖**：**严禁** 导入 `sdk.*`、`runtime.*`、`zmq`、`fastapi`、`serial`、ROS 等运行时/通信/外设相关代码。允许使用标准库与算法依赖（如 `math`, `numpy`）。
    *   **极简**：每个原子文件控制在 100 行以内。
*   **AI 价值**：AI 编写纯算法代码的能力极强，准确率接近 100%。
*   **文件示例**：`algorithm.py`, `pure_pursuit.py`, `geo_math.py`。

### L3 分子层 (Molecules/Nodes) —— "搬运工"
*   **定义**：独立运行的进程节点（Node）。
*   **职责**：
    *   **组装原子**：调用 L4 的函数处理业务。
    *   **数据搬运**：从 L2 读取数据，喂给 L4，将结果写回 L2。
*   **铁律**：
    *   **禁止横向代码依赖**：节点 A **不允许** `import node-hub/其它节点` 的任何代码（包括对方的 `run.py`/`utils`）。跨节点协作必须通过端口与数据契约完成。
    *   **默认非阻塞**：优先使用 `recv_latest()`，禁止“无限阻塞等待某个输入出现”。确需等待时必须有 timeout、状态输出与降级路径。
    *   **无状态（推荐）**：尽量做成无状态管道。
*   **文件示例**：`run.py` (Node Entrypoint)。

### L2 协调层 (Coordinator) —— "上帝视角"
*   **定义**：系统的控制流中心与数据总线。在现状 NodeFlow 中，它由三部分共同构成：
    *   **YAML 图配置（控制流表）**：`runtime.yaml` 中的 nodes/edges
    *   **共享缓冲区（数据板）**：每条“输出端口”对应一个 mmap buffer 文件（最新值语义）
    *   **ZMQ 通知（实时信号）**：用于触发输入端口读取最新值（避免纯轮询）
*   **职责**：
    *   **显式编排**：通过配置定义谁连接谁。
    *   **状态公示**：所有节点的数据交换都在这里透明可见。
*   **调试变革**：调试不再是追踪代码执行流，而是**查表**（检查数据板上的状态）。

### L1 入口层 (Entry) —— "启动器"
*   **定义**：系统的生命周期管理器。
*   **职责**：负责启动进程、加载配置、监控健康。
*   **文件示例**：[main.py](file:///Users/wuzhanli/Desktop/node/runtime/main.py), `runtime/orchestrator/*`。

---

## 3. 实践指南：如何落地

### 3.0 AI 优先的落地原则

- 让 AI 只阅读一个节点包目录就能完成改动（不需要理解整个系统）
- 让 AI 只靠“输入/输出契约 + 单测”就能验证正确性（不需要启动仿真/Runtime）
- 让 AI 的改动有明确边界：算法在 L4，收发在 L3，编排在 L2，生命周期在 L1

### 3.1 代码组织结构 (File Structure)

每个节点包（Node Package）内部应强制实施分层：

```text
node-hub/track_controller/
├── atom.py          # [L4] 核心算法 (纯数学，无依赖)
├── run.py           # [L3] 节点逻辑 (只负责收发数据 + 调 atom)
├── node.yaml        # [接口声明] 端口/参数/入口点（拓扑连线在 runtime.yaml）
└── test/
    ├── test_atom.py # [L4测试] 针对 atom 的单元测试 (极快)
    └── test_node.py # [L3测试] 针对 run 的集成测试 (Mock SDK)
```

如果节点的输入输出结构复杂，建议增加“契约样例”以降低 AI 误解：

```text
node-hub/track_controller/
├── contracts/
│   ├── in_pose.example.json
│   ├── in_path.example.json
│   └── out_cmd.example.json
```

### 3.2 重构步骤 (Refactoring Steps)

#### Step 1: 识别与剥离 (Extract Atoms)
检查现有的 `run.py`，寻找包含 `if-else` 复杂逻辑或数学计算的代码块。将其剪切到 `atom.py` 中，并改写为函数。

*   **Bad**: 在 `run.py` 的 loop 中写 PID 控制逻辑。
*   **Good**: `run.py` 调用 `atom.calculate_pid(target, current)`。

#### Step 2: 净化节点 (Purify Nodes)
重写 `run.py`，使其变成一个“傻瓜式”的循环：

```python
# L3 伪代码：极其简单，一眼看穿
def loop():
    # 1. Input (从 L2 获取，默认非阻塞)
    pose = input_port.recv_latest()
    target = target_port.recv_latest()
    
    # 2. Process (调用 L4)
    # 节点不负责思考，只负责传参
    cmd = atom.compute_velocity(pose, target, params)
    
    # 3. Output (写回 L2)
    output_port.send(cmd)
```

#### Step 3: 切断横向依赖 (Sever Horizontal Links)
检查代码中是否有 `time.sleep()` 等待其他节点，或者依赖特定节点启动顺序的逻辑。
*   **修正**：使用 `Latest-Value` 语义（`recv_latest()`）。如果有数据就处理，没数据就跳过或输出空/默认值，并输出明确状态。节点应假设自己是世界上唯一的进程。

“等待”允许存在，但必须显式化且可观测：

- 等待的是“数据契约满足”，不是“某个节点启动完成”
- 必须有超时与降级策略（例如输出 `WAITING_FOR_INPUT` 状态、维持上次控制指令、输出 0 指令等）

---

## 4. 如何让测试可行性变高

通过 L4/L3 分离，我们消灭了“为了测一个公式必须启动整个系统”的荒谬场景。

### 4.1 L4 测试：100% 覆盖率，零成本
由于 `atom.py` 没有依赖，我们可以直接运行 pytest。
*   **场景**：测试纯追踪算法在目标点在身后时的行为。
*   **做法**：直接构造 `(0,0)` 和 `(-1,0)` 的坐标传入函数，断言输出。
*   **速度**：毫秒级。

### 4.2 L3 测试：Mock 数据流
L3 只负责搬运，所以测试重点是**数据流通断**。
*   **做法**：使用 `sdk.test_utils.MockNodeFlowSDK` 注入假数据到 input 端口，检查 output 端口是否有数据输出。不需要关心数据的数学正确性（因为那是 L4 的事）。

参考：

- [sdk/test_utils](file:///Users/wuzhanli/Desktop/node/sdk/test_utils)
- [NODE_TESTING_GUIDE.md](file:///Users/wuzhanli/Desktop/node/docs/NODE_TESTING_GUIDE.md)

---

## 5. 如何在数据流层增加可读性

让 L2 成为真正的“指挥官”，让 AI 和人类能通过“看表”来 Debug。

### 5.1 数据总线可视化 (The "Board")
利用 NodeFlow 的“共享缓冲区文件”机制，将数据总线具象化为可检索对象。

- CLI 视角：通过 `tools/cli` 的 buffer 子命令列出 buffer、查看最新值
- Web 视角：使用类似 [logger](file:///Users/wuzhanli/Desktop/node/node-hub/logger/run.py) 这种“旁路节点”把关键数据推到 Web 页面

**故障排查流程示例**：
*   **现象**：车不动。
*   **旧模式**：看 Log -> 猜 Controller -> 猜 Planner -> 猜 GPS -> 崩溃。
*   **新模式 (查表法)**：
    1.  看 L2 总线表。
    2.  `gps_data`: ✅ (有数据)
    3.  `planned_path`: ✅ (有数据)
    4.  `control_cmd`: ❌ (无数据 / 全是 0)
    5.  **结论**：`track_controller` 节点逻辑有误，或者输入数据格式不满足 L4 要求。**定位时间：3秒。**

### 5.2 显式状态契约
在 `node.yaml` 中不仅定义端口类型，还应在端口描述中定义**状态契约与样例**。
例如，`track_controller` 可以输出一个 `status` 输出端口，payload 里包含 `state` 字段：`WAITING_FOR_INPUT` | `TRACKING` | `TARGET_REACHED`。
这样指挥官（监控系统）一眼就能看到每个分子的当前状态。

如果不希望新增端口，也至少保证每个输出 payload 中包含可读的 `status/state` 字段，且字段名与枚举值固定。

---

## 6. AI 友好的验收清单（改一个节点时必须满足）

- L4：核心算法可单测、可重复、无框架依赖
- L3：run.py 只做收发、参数读取、状态机与调用 L4
- 契约：每个输入/输出在 `node.yaml` 的 description 给出字段约定与 example
- 可观测：节点有可读状态输出（独立 status 端口或 payload 内 status 字段）
- 测试：新增/修改逻辑至少覆盖一个 L4 单测与一个 L3 MockSDK 测试


## 7. 总结

| 层级 | 关注点 | 代码量 | AI 生成难度 | Debug 难度 |
| :--- | :--- | :--- | :--- | :--- |
| **L4 原子** | 核心算法、数学 | 10% | 极低 (无依赖) | 极低 (单元测试) |
| **L3 分子** | 数据搬运、胶水 | 80% | 低 (模板化) | 低 (集成测试) |
| **L2 协调** | 数据流、状态 | 配置 | N/A | 查表即可 |
| **L1 入口** | 进程管理 | 10% | 低 | N/A |

通过实施这套架构，我们将**“调试代码”**转变成了**“调试数据”**。在数据流清晰可见的系统中，Bug 无处遁形。
