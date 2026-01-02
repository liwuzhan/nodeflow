# NodeFlow AI Agent CLI 操作指南

本指南旨在指导 AI Agent 如何利用 NodeFlow CLI 工具进行系统探测、状态检查与故障调试。CLI 是你感知系统运行状态的唯一"眼睛"和"手"。

## 1. 工具调用入口

### 1.1 CLI 工具
CLI 入口文件位于：`tools/cli/core/cli.py`
所有命令建议使用 `python3 tools/cli/core/cli.py <COMMAND> [ARGS]` 格式调用。

**通用参数：**
- `--json`: 强烈建议在所有支持的命令中添加此参数，以获取易于解析的 JSON 输出。
- `--verbose`: 当遇到未知错误时使用，获取堆栈信息。

### 1.2 运行时主入口（新增）
运行时框架入口位于：`runtime/main.py`

**主要用途**：启动 NodeFlow 框架，执行数据流

```bash
# 传统单次运行
python3 -m runtime.main <config.yaml> [OPTIONS]

# 多轮循环模式（新增）
python3 -m runtime.main <config.yaml> --loop N [OPTIONS]

# 守护进程模式（新增）
python3 -m runtime.main <config.yaml> --daemon
```

**关键参数**：
- `--loop N`: 运行 N 轮启动-停止循环（0 表示无限循环）
- `--loop-interval SEC`: 循环间隔时间，默认 5 秒
- `--daemon`: 启用守护进程模式（框架持续运行，等待 CLI 命令控制）
- `--log-level {DEBUG,INFO,WARNING,ERROR}`: 日志级别
- `--duration SEC`: 自动关机时间（单次模式）
- `--no-clean-buffers`: 禁用启动前清理缓冲区

### 1.3 守护进程 CLI 控制（新增）

当框架以 `--daemon` 模式运行时，可通过 CLI 命令动态控制数据流：

```bash
# 启动框架（后台）
python3 tools/cli/core/cli.py runtime start <config.yaml> --background

# 检查框架状态
python3 tools/cli/core/cli.py runtime status

# 启动数据流
python3 tools/cli/core/cli.py runtime start-dataflow

# 停止数据流
python3 tools/cli/core/cli.py runtime stop-dataflow

# 重启数据流
python3 tools/cli/core/cli.py runtime restart-dataflow

# 停止框架
python3 tools/cli/core/cli.py runtime stop
```

**关键特性**：
- 框架和数据流可独立控制
- 支持多次启停而无需重启框架
- 通过共享缓冲区 `runtime.control` 实现进程间通信
- 后台日志输出到 `/tmp/nodeflow_runtime.log`

## 2. 核心能力与场景映射

| 场景 | 核心问题 | 推荐命令 | 关键参数 |
| :--- | :--- | :--- | :--- |
| **环境探索** | 系统里有哪些节点可用？ | `node list` | `--json` |
| **契约检查** | 这个节点的输入/输出格式是什么？ | `node info` | `<package_name>` |
| **运行时启动** | 启动框架和数据流 | `runtime.main` | `<config.yaml>` |
| **多轮测试** | 运行多个完整的启动-停止周期 | `runtime.main` | `--loop N` |
| **守护进程启动** | 启动后台框架，用 CLI 控制启停 | `runtime start` | `--background` |
| **动态控制数据流** | 在运行中启动/停止数据流（不关框架） | `runtime start-dataflow` | (无) |
| **存活检查** | 节点是否正在运行并产生数据？ | `buffer list` | (无) |
| **数据审计** | 节点输出的具体数据内容对不对？ | `buffer inspect` | `<buffer_name>` |
| **系统体检** | 整个数据流是否通畅（无阻塞）？ | `health flow` | `--config <yaml>` |
| **数据合规** | 节点输出的数据是否符合 Schema？ | `health check` | `<node_id>` |
| **实时监控** | 数据更新频率是否正常？ | `monitor` | `--names <buf>` |

## 3. 标准作业流程 (SOP)

### SOP-0: 启动和管理运行时（新增）
当你需要启动框架、运行数据流或进行多轮测试时：

#### 场景 A: 单次运行数据流
```bash
# 启动框架，运行数据流，直到 Ctrl+C 或自动关机
python3 -m runtime.main examples/planning_simulation.yaml
```

#### 场景 B: 多轮循环测试
```bash
# 运行 3 轮完整的启动-停止周期
python3 -m runtime.main examples/planning_simulation.yaml --loop 3

# 每轮间隔 10 秒
python3 -m runtime.main examples/planning_simulation.yaml --loop 3 --loop-interval 10
```

**用途**：
- 自动化测试：验证框架在多次重启后是否稳定
- 性能评估：测量启动/停止开销
- 长期服务：保持框架运行，动态启停数据流

**每轮行为**：
```
Loop 1:
  ├─ 清理缓冲区（如果启用）
  ├─ 启动所有节点（按拓扑顺序）
  ├─ 启动监控器
  ├─ 数据流运行（可通过 Ctrl+C 中断）
  └─ 停止所有节点，清理资源

Loop 2:
  ├─ 清理缓冲区
  ├─ 重新启动所有节点
  ... (重复)
```

**关键点**：
- 框架只初始化一次（配置加载、节点扫描、拓扑分析）
- 每轮都会重新启动节点进程
- 默认清理缓冲区，使用 `--no-clean-buffers` 保留数据

#### 场景 C: 调试模式运行
```bash
# 启用详细日志
python3 -m runtime.main examples/planning_simulation.yaml --log-level DEBUG

# 自动关机（用于测试）
python3 -m runtime.main examples/planning_simulation.yaml --duration 30
```

### SOP-0.5: 守护进程模式（后台框架动态控制）

当你需要启动框架后台服务，通过 CLI 命令灵活控制数据流启停时：

#### 场景 A: 启动后台框架
```bash
# 1. 启动框架（后台运行）
python3 tools/cli/core/cli.py runtime start examples/planning_simulation.yaml --background

# 2. 检查框架运行状态
python3 tools/cli/core/cli.py runtime status
# ✓ Runtime is running
#   PID: 12345
#   Uptime: 0.1h
#   Memory: 125.3 MB
```

#### 场景 B: 动态启停数据流
```bash
# 启动数据流
python3 tools/cli/core/cli.py runtime start-dataflow
# ✓ Start dataflow command sent

# 运行数据流... （检查缓冲区状态）
python3 tools/cli/core/cli.py buffer list

# 停止数据流（框架继续运行）
python3 tools/cli/core/cli.py runtime stop-dataflow
# ✓ Stop dataflow command sent

# 修改代码、配置等...

# 重新启动数据流
python3 tools/cli/core/cli.py runtime start-dataflow
```

#### 场景 C: 多次启停循环（开发调试）
```bash
# 启动框架
python3 tools/cli/core/cli.py runtime start examples/planning_simulation.yaml -b

# 第一轮测试
python3 tools/cli/core/cli.py runtime start-dataflow
sleep 30
python3 tools/cli/core/cli.py buffer list > test1.txt
python3 tools/cli/core/cli.py runtime stop-dataflow
sleep 2

# 第二轮测试（无需重启框架）
python3 tools/cli/core/cli.py runtime start-dataflow
sleep 30
python3 tools/cli/core/cli.py buffer list > test2.txt
python3 tools/cli/core/cli.py runtime stop-dataflow

# 完成
python3 tools/cli/core/cli.py runtime stop
```

**关键优势**：
- ✓ 框架初始化一次（节省配置加载、节点扫描时间）
- ✓ 数据流可独立控制（不影响框架）
- ✓ 可快速迭代测试（无重启开销）
- ✓ 适合开发调试、长期服务、压力测试

**文件位置**：
- 后台日志：`/tmp/nodeflow_runtime.log`
- PID 文件：`/tmp/nodeflow_runtime.pid`
- 控制缓冲区：`runtime.control`（自动创建）

### SOP-1: 节点能力调研 (Discovery)
当你需要了解某个节点的功能或接口定义时：

1. **列出所有节点**：
   ```bash
   python3 tools/cli/core/cli.py node list --json
   ```
   *关注点*：找到目标节点的 `name` 和 `path`。

2. **查看节点契约**：
   ```bash
   python3 tools/cli/core/cli.py node info <package_name>
   ```
   *关注点*：
   - `Input Ports`: 需要什么数据？格式是什么？
   - `Output Ports`: 产出什么数据？
   - `Entrypoints`: 启动命令是什么（用于排查启动问题）？

### SOP-2: 运行时状态诊断 (Runtime Diagnosis)
当你被告知"系统运行不正常"或"数据没更新"时：

1. **检查是否有框架在运行**：
   ```bash
   # 查看 PID 文件
   cat /tmp/nodeflow_runtime.pid

   # 或检查进程
   ps aux | grep "python3 -m runtime.main"
   ```
   *分析逻辑*：
   - 如果没有进程 -> 框架未启动，使用 `python3 -m runtime.main` 启动。
   - 如果有进程 -> 框架正在运行，继续诊断数据流。

2. **检查缓冲区是否存在**：
   ```bash
   python3 tools/cli/core/cli.py buffer list
   ```
   *分析逻辑*：
   - 如果列表为空 -> 没有任何节点在运行。
   - 如果目标 buffer (如 `sim.pose`) 不在列表中 -> 对应节点未启动或未创建端口。
   - `seq` (序列号) 为 0 -> 节点已启动但从未发送数据。

3. **检查数据内容**：
   ```bash
   python3 tools/cli/core/cli.py buffer inspect <buffer_name>
   ```
   *分析逻辑*：
   - 检查 JSON 内容是否符合预期。
   - 如果 `len` 很小但 `seq` 在增长 -> 可能发送了空包。

4. **检查数据流健康度**：
   ```bash
   python3 tools/cli/core/cli.py health --config <runtime_config.yaml> --json
   ```
   *分析逻辑*：
   - `status: "STALE"` -> 数据不再更新（节点卡死或逻辑阻塞）。
   - `status: "MISSING"` -> 节点未启动。
   - `status: "OK"` -> 数据流正常。
   
### SOP-2.5: 数据合规性检查 (Data Compliance Check)
当你怀疑节点发送的数据格式错误、数值越界或类型不对时：

1.  **运行健康检查**：
    ```bash
    python3 tools/cli/core/cli.py health check <node_id> --samples 10
    ```

2.  **分析输出报告**：
    ```text
    Port: gps_fix (Checking...) Sampled: 10, Valid: 9 (90.0%)
      Errors:
        - -190.0 is less than the minimum of -180.0 (x1)
    ```
    *关注点*：
    *   `Valid` 比例：如果低于 100%，说明有脏数据。
    *   `Errors` 列表：具体的错误原因（如数值越界、字段缺失）。
    *   `(No Schema Defined)`：说明该端口未绑定 Pydantic Schema，无法校验。

3.  **定位问题**：
    *   如果是数值越界 -> 检查传感器或模拟逻辑。
    *   如果是类型错误 -> 检查代码中的数据构造部分。

## 4. 输出解析指南

### Buffer List 输出示例
```text
Buffers in /tmp/nodeflow/buffers (2):
--------------------------------------------------------------------------------
  sim_output.rtk_fix             size=4KB     seq=1234        len=45 bytes
  planner.cmd                    size=4KB     seq=0           len=0 bytes
```
- **解读**：
  - `sim_output.rtk_fix`: 正在正常工作 (seq=1234)。
  - `planner.cmd`: 节点可能刚启动，或者逻辑有问题，从未发过数据 (seq=0)。

### Health Check 输出示例 (JSON)
```json
{
  "buffers": {
    "sim.pose": {
      "status": "STALE",
      "seq_start": 100,
      "seq_end": 100,
      "delta": 0
    }
  }
}
```
- **解读**：
  - `delta: 0` 表示在采样周期内序列号没有增加。
  - `status: "STALE"` 明确指出了问题：数据流停滞。

## 5. 调试思维链 (CoT) 示例

### 场景 1: 规划控制节点没反应

**用户问题**："规划控制节点好像没反应。"

**Agent 思考路径**：
1. **确认节点是否在发数据**：
   - 执行 `buffer list`。
   - *观察*：`planning.control_cmd` 是否存在？`seq` 是否在增长？
   - *分支*：
     - 不存在 -> 检查节点是否启动 (ps aux | grep planning)。
     - 存在但 seq 不动 -> 节点卡死，执行 `health` 确认。
     - 存在且 seq 增长 -> 节点在发数据，可能是数据内容不对。

2. **确认数据内容**：
   - 执行 `buffer inspect planning.control_cmd`。
   - *观察*：输出的 JSON 中 `velocity` 是不是 0？
   - *分支*：
     - 是 0 -> 逻辑层问题，检查输入数据。

3. **回溯输入数据**：
   - 规划节点的输入通常是定位数据。
   - 执行 `buffer inspect sim.pose`。
   - *观察*：定位数据是否正常？
   - *结论*：如果定位数据正常但规划输出为 0，则是规划算法逻辑 bug。

### 场景 2: 多轮测试中某轮节点启动失败

**用户问题**："为什么第 3 轮的节点启动不了？"

**Agent 思考路径**：
1. **检查前几轮是否正常**：
   ```bash
   # 检查日志中的启动信息
   python3 -m runtime.main config.yaml --loop 5 --log-level DEBUG 2>&1 | grep -E "Loop|Starting|Error"
   ```
   - *观察*：前 2 轮是否成功启动和停止？

2. **诊断第 3 轮失败原因**：
   - *可能原因 A*：缓冲区或临时文件未清理
     - 解决：增加 `--loop-interval 10` 给系统更多清理时间
   - *可能原因 B*：某个节点进程未完全退出
     - 检查：`ps aux | grep node-hub`，手动 kill 僵尸进程
   - *可能原因 C*：IPC 端口被占用
     - 检查：`lsof /tmp/nodeflow/buffers/`

3. **重新运行测试**：
   ```bash
   # 带调试信息重新运行
   python3 -m runtime.main config.yaml --loop 5 --loop-interval 10 --log-level DEBUG
   ```

### 场景 3: 长期运行框架的稳定性测试

**用户问题**："框架能稳定运行吗？需要做压力测试。"

**Agent 方案**：
```bash
# 运行 10 轮循环，每轮运行 30 秒
timeout 500 python3 -m runtime.main config.yaml --loop 10 --loop-interval 5 &
PID=$!

# 在运行时并行执行监控
while kill -0 $PID 2>/dev/null; do
  echo "=== $(date) ==="
  python3 tools/cli/core/cli.py buffer list
  python3 tools/cli/core/cli.py health --config config.yaml --json | jq .
  sleep 10
done

# 分析结果
echo "Test completed. Check logs:"
tail -100 /tmp/nodeflow_runtime.log
```

**评估标准**：
- ✓ 所有轮次都成功启停
- ✓ 缓冲区序列号正常增长（无重复或下降）
- ✓ 没有僵尸进程残留
- ✓ 内存占用稳定（不持续增长）

## 6. 常见错误处理

### 运行时相关错误

| 错误 | 原因 | 解决方案 |
|-----|------|--------|
| `Error: Buffer directory not found` | 没有任何运行时环境启动过（/tmp/nodeflow/buffers 不存在） | 先启动 Runtime：`python3 -m runtime.main <config.yaml>` |
| `Error: config not found` | 运行 health/monitor 命令时路径错误 | 检查 YAML 路径是否正确 |
| `RuntimeError: Framework not initialized` | 调用 `start_dataflow()` 前未初始化框架 | 必须先调用 `_initialize_framework()` |
| `RuntimeError: Dataflow already running` | 重复启动数据流 | 先调用 `stop_dataflow()` 停止当前流 |
| `Process timeout on shutdown` | 节点停止时超时 | 增加 `--log-level DEBUG` 查看详细日志 |

### 多轮循环相关问题

| 问题 | 可能原因 | 诊断方法 |
|-----|--------|--------|
| 第二轮启动失败 | 端口被占用或缓冲区未清理 | 检查 `/tmp/nodeflow` 目录，确保第一轮完全停止 |
| 某些轮次节点未启动 | 节点文件被锁定或权限问题 | 增加 `--loop-interval` 间隔时间，或使用 `--log-level DEBUG` |
| 内存持续增长 | 前一轮资源未清理 | 确保每轮都有完整的 stop 流程，检查日志中的清理信息 |
| 循环无法中止 | 使用了 `--loop 0`（无限循环） | 按 `Ctrl+C` 中断，或检查是否真的在运行中 |

### 守护进程相关问题

| 问题 | 可能原因 | 诊断方法 |
|-----|--------|--------|
| CLI 命令无响应 | 框架未以 `--daemon` 模式启动 | 执行 `runtime status` 检查框架是否运行；检查日志 `/tmp/nodeflow_runtime.log` |
| 框架启动后立即退出 | 配置文件错误或节点库路径错误 | 查看 `/tmp/nodeflow_runtime.log` 中的错误信息；用前台模式测试配置 |
| 数据流无法停止 | 节点进程未正确响应 SIGTERM | 执行 `ps aux \| grep node-hub` 检查进程；可能需要 `runtime stop` 强制停止框架 |
| 重复启动数据流失败 | 前一次停止未完全生效 | 等待 1-2 秒后重试；或检查是否还有节点进程在运行 |
| 控制缓冲区被锁定 | 框架进程已崩溃但 PID 文件未清理 | 删除 `/tmp/nodeflow_runtime.pid`；手动清理 `/tmp/nodeflow/buffers/runtime.control` |

### 调试技巧

**启用详细日志追踪启动/停止流程**：
```bash
python3 -m runtime.main examples/planning_simulation.yaml --loop 3 --log-level DEBUG 2>&1 | tee debug.log
```

**监控每轮的缓冲区状态**：
```bash
while true; do
  echo "=== Buffer Status ==="
  python3 tools/cli/core/cli.py buffer list
  sleep 5
done
```

**检查僵尸进程**：
```bash
ps aux | grep -E "python|defunct"
lsof /tmp/nodeflow/buffers/ | head -20
```

## 7. 快速参考 (Quick Reference)

### 运行时命令速查表

| 命令 | 用途 | 示例 |
|------|------|------|
| **启动单次运行** | 启动框架和数据流，直到 Ctrl+C | `python3 -m runtime.main config.yaml` |
| **多轮循环测试** | 自动启停多个周期 | `python3 -m runtime.main config.yaml --loop 5` |
| **无限循环** | 持续运行直到信号中断 | `python3 -m runtime.main config.yaml --loop 0` |
| **自定义间隔** | 设置循环间隔时间 | `python3 -m runtime.main config.yaml --loop 3 --loop-interval 10` |
| **调试模式** | 输出详细日志 | `python3 -m runtime.main config.yaml --log-level DEBUG` |
| **自动关机** | 运行 N 秒后自动关机 | `python3 -m runtime.main config.yaml --duration 60` |
| **保留缓冲区** | 跨轮保留数据 | `python3 -m runtime.main config.yaml --loop 3 --no-clean-buffers` |

### 守护进程 CLI 命令速查表

| 命令 | 用途 | 示例 |
|------|------|------|
| **启动守护进程** | 启动框架（后台），不启动数据流 | `python3 tools/cli/core/cli.py runtime start config.yaml --background` |
| **检查状态** | 显示框架运行状态和资源占用 | `python3 tools/cli/core/cli.py runtime status` |
| **启动数据流** | 通过控制缓冲区启动数据流 | `python3 tools/cli/core/cli.py runtime start-dataflow` |
| **停止数据流** | 停止数据流但保持框架运行 | `python3 tools/cli/core/cli.py runtime stop-dataflow` |
| **重启数据流** | 先停后启（用于快速重启） | `python3 tools/cli/core/cli.py runtime restart-dataflow` |
| **停止框架** | 完全关闭框架和所有节点 | `python3 tools/cli/core/cli.py runtime stop` |
| **JSON 输出** | 获取 JSON 格式的结果 | `python3 tools/cli/core/cli.py runtime status --json` |

### CLI 诊断命令速查表

| 命令 | 用途 |
|------|------|
| `python3 tools/cli/core/cli.py node list --json` | 列出所有可用节点 |
| `python3 tools/cli/core/cli.py node info <pkg>` | 查看节点的输入/输出端口 |
| `python3 tools/cli/core/cli.py buffer list` | 查看当前运行的缓冲区状态 |
| `python3 tools/cli/core/cli.py buffer inspect <buf>` | 查看缓冲区内容 |
| `python3 tools/cli/core/cli.py health --config <cfg>` | 检查数据流健康度 |
| `python3 tools/cli/core/cli.py monitor --config <cfg>` | 实时监控缓冲区 |

### 关键文件位置

| 文件/目录 | 说明 |
|----------|------|
| `runtime/main.py` | 运行时框架主文件 |
| `tools/cli/core/cli.py` | CLI 工具入口 |
| `tools/cli/commands/runtime_cmd.py` | 守护进程控制命令实现 |
| `/tmp/nodeflow/buffers/` | 共享缓冲区存储位置 |
| `/tmp/nodeflow_runtime.pid` | 运行时 PID 文件 |
| `/tmp/nodeflow_runtime.log` | 后台日志文件（守护进程模式） |
| `runtime.control` | 控制缓冲区（守护进程通信） |
| `MULTI_LOOP_GUIDE.md` | 多轮循环功能完整文档 |
| `DAEMON_MODE_GUIDE.md` | 守护进程模式完整文档 |
| `test_multi_loop.py` | 多轮循环测试用例 |

### 故障排除速查

| 问题 | 快速诊断命令 |
|-----|------------|
| 框架是否运行？ | `ps aux \| grep "runtime.main"` 或 `cat /tmp/nodeflow_runtime.pid` |
| 节点是否启动？ | `python3 tools/cli/core/cli.py buffer list` |
| 数据是否更新？ | `python3 tools/cli/core/cli.py health --config config.yaml --json` |
| 僵尸进程？ | `ps aux \| grep -E "defunct\|Z "` |
| 缓冲区被锁定？ | `lsof /tmp/nodeflow/buffers/` |

## 8. 新增功能说明

### v1.1: 多轮启动-停止循环功能

**功能**：在同一框架实例中支持多次启动和停止数据流，而无需重新加载配置和扫描节点库。

**架构改进**：
- 框架层（Framework Layer）：一次性初始化配置、节点库、拓扑分析
- 数据流层（Dataflow Layer）：可重复启停节点进程、监控运行

**核心优势**：
1. ✓ 减少重复初始化开销（配置加载、节点扫描只需一次）
2. ✓ 支持自动化多轮测试和性能评估
3. ✓ 保持完全向后兼容（现有单次运行方式不受影响）
4. ✓ 支持长期服务模式（框架持续运行，动态启停数据流）

**使用场景**：
- 🔬 自动化测试：验证系统在多次重启后的稳定性
- 📊 性能评估：测量启动/停止的开销
- 🔄 轮流执行：依次运行多个独立的工作流
- 📈 压力测试：评估长期运行的资源消耗

**相关文档**：
- 完整指南：`MULTI_LOOP_GUIDE.md`
- 测试用例：`test_multi_loop.py`
- 演示脚本：`demo_multi_loop.py`

### v1.2: 守护进程模式（Daemon Mode）

**版本**：NodeFlow Runtime v1.2+

**功能**：框架作为后台服务运行，通过 CLI 命令动态控制数据流的启停。

**架构特性**：
- 框架持续运行，无需重启即可控制数据流
- 通过共享缓冲区 `runtime.control` 进行进程间通信
- 支持后台运行，日志输出到 `/tmp/nodeflow_runtime.log`
- 通过 PID 文件管理框架生命周期

**核心优势**：
1. ✓ 框架与数据流分离（独立控制）
2. ✓ CLI 命令灵活控制（无需编程接口）
3. ✓ 后台运行（适合长期服务）
4. ✓ 快速迭代测试（无框架重启开销）
5. ✓ 支持远程控制（通过 CLI）

**使用场景**：
- 🔧 开发调试：频繁启停数据流测试代码修改
- 🏭 生产环境：长期后台服务，按需启停数据流
- 🎮 手动控制：人工干预数据流的启停时机
- 🔄 动态调度：根据外部条件动态控制数据流

**CLI 命令**：
```bash
# 框架管理
runtime start <config> --background   # 启动守护进程
runtime stop                         # 停止框架
runtime status                       # 检查状态

# 数据流管理
runtime start-dataflow               # 启动数据流
runtime stop-dataflow                # 停止数据流
runtime restart-dataflow             # 重启数据流
```

**通信协议**：
- 控制缓冲区：`runtime.control`
- 命令格式：`{"command": "start_dataflow|stop_dataflow|shutdown", "timestamp": <unix_time>}`
- 去重机制：基于时间戳避免重复执行

**相关文档**：
- 完整指南：`DAEMON_MODE_GUIDE.md`
- 命令实现：`tools/cli/commands/runtime_cmd.py`

### 改进的信号处理

新增两级信号处理：
- **第一次 Ctrl+C**：停止数据流（如果在运行）
- **第二次 Ctrl+C**：关闭框架（如果在运行）

这样可以在循环过程中选择性地中断数据流而不关闭整个框架。

### API 扩展

**v1.1 新增方法**：
```python
runtime._initialize_framework()      # 初始化框架（一次性）
runtime.start_dataflow()             # 启动数据流
runtime.stop_dataflow()              # 停止数据流
runtime.run_with_loop(num_loops, loop_interval)  # 多轮循环运行
```

**v1.2 新增方法**：
```python
runtime.run_as_daemon()              # 守护进程模式运行
runtime._write_pid_file()            # 写入 PID 文件
runtime._cleanup_pid_file()          # 清理 PID 文件
```

**兼容性**：
- 现有的 `runtime.run()` 方法保持不变
- 新增的方法作为可选扩展
- 完全向后兼容，无破坏性改动

### 运行模式对比

| 特性 | 单次运行 | 多轮循环 | 守护进程 |
|-----|---------|---------|---------|
| 框架启动次数 | 1 | 1 | 1 |
| 数据流启停 | 1 次 | N 次（自动） | 动态（CLI控制） |
| 控制方式 | 参数 | 参数 | CLI 命令 |
| 适用场景 | 测试、脚本 | 自动化测试 | 生产环境、长期服务 |
| 灵活性 | 低 | 中 | 高 |
| 人工干预 | 无 | 有限（Ctrl+C） | 完全（CLI） |
