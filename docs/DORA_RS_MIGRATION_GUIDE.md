# dora-rs 节点迁移指南

**目标**: 将现有的 dora-rs 节点迁移到 NodeFlow 框架

**更新时间**: 2025-12-18

---

## 📋 概述

### 现有 dora-rs 节点清单

| 节点 | 类型 | 功能 | 输入端口 | 输出端口 |
|------|------|------|---------|---------|
| **pwm-controller** | 执行器 | PWM 信号生成 | control_data, stop | pwm_signals, error |
| **rmc-parser** | 处理器 | RMC 数据解析 | raw_nmea | parsed_rmc, error |
| **rtk-receiver** | 传感器 | RTK 数据读取 | 无 | nmea_data, error |
| **target-generator** | 规划器 | 目标轨迹生成 | global_target, state | target_trajectory, error |
| **vehicle-controller** | 控制器 | 车辆运动控制 | position, velocity, heading | control_cmd, error |

### 迁移难度评估

| 节点 | 难度 | 优先级 | 预计时间 |
|------|------|--------|---------|
| target-generator | ⭐ 简单 | 🔴 高 | 15 min |
| rmc-parser | ⭐⭐ 中等 | 🔴 高 | 20 min |
| rtk-receiver | ⭐⭐ 中等 | 🔴 高 | 25 min |
| vehicle-controller | ⭐⭐⭐ 复杂 | 🟡 中 | 30 min |
| pwm-controller | ⭐⭐⭐ 复杂 | 🟡 中 | 35 min |

---

## 🔄 迁移步骤 (通用流程)

### Step 1: 转换配置文件

**From** `template.yaml` (dora-rs):
```yaml
id: pwm-controller
name: "PWM控制器"
type: "python"
path: "pwm_controller.main:main"
inputs:
  - name: "control_data"
    type: "object"
outputs:
  - name: "pwm_signals"
    type: "object"
env:
  KEY: "value"
```

**To** `node.yaml` (NodeFlow):
```yaml
name: pwm_controller
version: "1.0.0"
description: "将角速度和线速度转换为RC PWM控制信号"

entrypoints:
  linux:
    kind: python
    cmd: ["python3", "run.py"]

inputs:
  - name: control_data
    type: object
    description: "车辆控制数据"
  - name: stop
    type: boolean
    description: "停止信号"

outputs:
  - name: pwm_signals
    type: object
    description: "PWM控制信号"
  - name: error
    type: string
    description: "错误消息"

params:
  vehicle_type:
    type: string
    required: false
    default: "car"
    description: "车辆类型: car 或 tank"
  max_linear_speed:
    type: float
    required: false
    default: 2.0
    description: "最大线速度 (m/s)"
```

### Step 2: 创建运行脚本 (`run.py`)

**移除**: dora-rs 特定的导入和 API 调用

```python
# ❌ 删除这些
import dora
node = dora.Node()
event = node.next(timeout=0.1)
node.send_output("output_name", data)
```

**添加**: NodeFlow SDK API

```python
# ✅ 替换为这些
import sys
sys.path.insert(0, '../../sdk')
from nodeflow_sdk import NodeFlowSDK

sdk = NodeFlowSDK()
params = sdk.params

input_port = sdk.create_input_port('input_name')
output_port = sdk.create_output_port('output_name')

data = input_port.recv_latest()
output_port.send(processed_data)
```

### Step 3: 重构主循环

**dora-rs 风格** (事件驱动):
```python
while True:
    event = node.next(timeout=0.1)

    if event is None:
        continue

    if event["type"] == "INPUT":
        input_id = event["id"]
        data = event["data"]
        # 处理不同的输入端口
        if input_id == "control_data":
            # ...
    elif event["type"] == "STOP":
        break
```

**NodeFlow 风格** (轮询):
```python
import time

while True:
    # 从输入端口读取最新值（非阻塞）
    control_data = input_port_1.recv_latest()
    stop_signal = input_port_2.recv_latest()

    if stop_signal:
        break

    if control_data is not None:
        # 处理数据
        result = process(control_data)
        output_port.send(result)

    time.sleep(0.01)  # 避免忙轮询
```

### Step 4: 调整环境变量

**dora-rs 配置** -> **NodeFlow 参数**

```yaml
# dora-rs template.yaml
env:
  VEHICLE_TYPE: "car"
  PWM_FREQUENCY: "50"
  MAX_LINEAR_SPEED: "2.0"
```

**转换为** NodeFlow 参数:

```yaml
# node.yaml
params:
  vehicle_type:
    type: string
    default: "car"
  pwm_frequency:
    type: int
    default: 50
  max_linear_speed:
    type: float
    default: 2.0
```

**使用方式**:
```python
# 从 SDK 参数获取
vehicle_type = sdk.params.get('vehicle_type', 'car')
pwm_frequency = sdk.params.get('pwm_frequency', 50)
max_linear_speed = sdk.params.get('max_linear_speed', 2.0)
```

### Step 5: 处理序列化

**dora-rs** (自动处理 bytes/JSON):
```python
if isinstance(data, bytes):
    data = json.loads(data.decode('utf-8'))
```

**NodeFlow** (传递 Python 对象):
```python
# 直接传递字典/对象，SDK 会自动序列化
output_port.send({"key": "value"})

# 接收也是直接得到 Python 对象
data = input_port.recv_latest()  # 已经是字典
```

---

## 🛠️ 快速参考表

### 代码映射

| dora-rs | NodeFlow |
|---------|----------|
| `import dora` | `from nodeflow_sdk import NodeFlowSDK` |
| `node = dora.Node()` | `sdk = NodeFlowSDK()` |
| `event = node.next()` | `data = port.recv_latest()` |
| `node.send_output("name", data)` | `port.send(data)` |
| `os.getenv('KEY')` | `sdk.params.get('key')` |
| Event loop 处理 | 简单 while 循环 |

### 配置映射

| dora-rs | NodeFlow | 说明 |
|---------|----------|------|
| `template.yaml` | `node.yaml` | 配置文件名 |
| `id:` | `name:` | 节点标识 |
| `type: "python"` | `entrypoints.linux.kind: python` | 运行时类型 |
| `path: "main:func"` | `entrypoints.linux.cmd: ["python3", "run.py"]` | 启动命令 |
| `env:` | `params:` | 配置参数 |
| `inputs/outputs` | `inputs/outputs` | 端口定义 (基本相同) |

---

## 📝 迁移 Checklist

### 配置文件 (`node.yaml`)
- [ ] 重命名 `id` → `name`
- [ ] 更改 `type: "python"` → `entrypoints.linux.kind: python`
- [ ] 更改 `path` → `entrypoints.linux.cmd: ["python3", "run.py"]`
- [ ] 迁移 `env` → `params` (转换类型)
- [ ] 保留 `inputs` 和 `outputs` (基本不变)
- [ ] 添加 `version` 和 `description`

### Python 代码 (`run.py`)
- [ ] 删除 `import dora`
- [ ] 添加 `from nodeflow_sdk import NodeFlowSDK`
- [ ] 替换 `node = dora.Node()` → `sdk = NodeFlowSDK()`
- [ ] 为每个输入/输出端口创建 SDK 端口对象
- [ ] 重构主循环 (从事件驱动 → 轮询)
- [ ] 替换 `node.next()` → `port.recv_latest()`
- [ ] 替换 `node.send_output()` → `port.send()`
- [ ] 替换 `os.getenv()` → `sdk.params.get()`
- [ ] 处理序列化差异 (字典直接传递)
- [ ] 添加 `time.sleep()` 避免忙轮询

### 目录结构
- [ ] 确保 `node.yaml` 在节点目录根目录
- [ ] 确保 `run.py` 在节点目录根目录
- [ ] 保留 `pyproject.toml` (可选)
- [ ] 删除或重命名 `template.yaml` (dora-rs 配置)
- [ ] 删除或迁移 `tests/` 目录

---

## 🎯 具体迁移示例

### 示例 1: target-generator (简单节点)

**原始 dora-rs 代码结构**:
```
target-generator/
├── template.yaml          # dora-rs 配置
├── pyproject.toml
├── target_generator/
│   ├── __init__.py
│   └── main.py           # 主逻辑
└── tests/
```

**迁移后 NodeFlow 结构**:
```
target-generator/
├── node.yaml             # ✅ 新配置
├── run.py                # ✅ 新启动脚本
├── pyproject.toml        # (可选)
├── target_generator/
│   ├── __init__.py
│   └── processor.py      # 核心逻辑 (无依赖)
└── tests/
```

---

## 🔗 端口与参数对应

### RTK-Receiver 示例

**dora-rs**:
```yaml
outputs:
  - name: "nmea_data"
    type: "string"
env:
  SERIAL_PORT: "COM3"
  BAUD_RATE: "115200"
```

**NodeFlow**:
```yaml
outputs:
  - name: nmea_data
    type: string
    description: "从RTK设备接收的NMEA数据"

params:
  serial_port:
    type: string
    default: "/dev/ttyUSB0"
    description: "串口设备路径"
  baud_rate:
    type: int
    default: 115200
    description: "波特率"
```

**代码变化**:
```python
# 原始 dora-rs
port = os.getenv('SERIAL_PORT', 'COM3')
baud = os.getenv('BAUD_RATE', '115200')

# 迁移后 NodeFlow
port = sdk.params.get('serial_port', '/dev/ttyUSB0')
baud = sdk.params.get('baud_rate', 115200)
```

---

## ⚠️ 常见迁移问题

### 问题 1: 事件处理

**症状**: 多个输入端口，不知道哪个有新数据

**dora-rs 解决方案**:
```python
if event["id"] == "input_1":
    # 处理 input_1
elif event["id"] == "input_2":
    # 处理 input_2
```

**NodeFlow 解决方案**:
```python
data1 = port1.recv_latest()  # 如果没有新数据则为 None
data2 = port2.recv_latest()

if data1 is not None:
    # 处理 data1
if data2 is not None:
    # 处理 data2
```

**或使用状态机**:
```python
state = {
    'data1_received': False,
    'data2_received': False
}

while True:
    d1 = port1.recv_latest()
    d2 = port2.recv_latest()

    if d1 is not None:
        state['data1_received'] = True
    if d2 is not None:
        state['data2_received'] = True

    if state['data1_received'] and state['data2_received']:
        result = process(d1, d2)
        output_port.send(result)
        state['data1_received'] = False
        state['data2_received'] = False

    time.sleep(0.01)
```

### 问题 2: 性能优化

**症状**: CPU 使用率高 (忙轮询)

**解决方案**:
```python
# ❌ 错误: 忙轮询
while True:
    data = port.recv_latest()
    if data is not None:
        output_port.send(process(data))

# ✅ 正确: 加入睡眠
import time
while True:
    data = port.recv_latest()
    if data is not None:
        output_port.send(process(data))
    time.sleep(0.01)  # 10ms 轮询周期
```

### 问题 3: 环境变量 vs 参数

**症状**: 参数在编辑器中无法修改

**原因**: 使用 `os.getenv()` 代替 `sdk.params.get()`

**解决方案**:
```python
# ❌ 环境变量无法通过编辑器修改
val = os.getenv('KEY')

# ✅ 参数可以通过编辑器修改
val = sdk.params.get('key')
```

### 问题 4: 数据序列化

**症状**: 接收到字符串而不是对象

**原因**: dora-rs 的自动 JSON 编码

**解决方案**:
```python
# NodeFlow 自动处理序列化
output_port.send({"key": "value"})  # 自动转换为 JSON

# 接收端自动解序列化
data = input_port.recv_latest()  # 自动转换为字典
print(data["key"])  # 直接访问
```

---

## 📊 迁移工作量估计

### 单个节点迁移工作

| 任务 | 时间 |
|------|------|
| 分析 dora-rs 节点结构 | 5 min |
| 编写 node.yaml | 5 min |
| 转换 Python 代码 | 10-30 min |
| 测试和调试 | 10-20 min |
| **总计** | **30-60 min** |

### 全部 5 个节点

**总工作量**: 约 2.5-5 小时

**建议计划**:
1. **优先级 1** (1 小时): target-generator + rmc-parser
2. **优先级 2** (1.5 小时): rtk-receiver + vehicle-controller
3. **优先级 3** (1 小时): pwm-controller

---

## 🚀 开始迁移

### 推荐迁移顺序

1. **target-generator** ← 最简单，作为学习示例
2. **rmc-parser** ← 中等难度，无硬件依赖
3. **rtk-receiver** ← 传感器节点，需要串口处理
4. **vehicle-controller** ← 多输入端口处理
5. **pwm-controller** ← 最复杂，硬件交互

### 验证迁移完成

```bash
# 1️⃣ 在 Web 编辑器中验证
npm run dev
# 左侧节点库应显示迁移的节点

# 2️⃣ 创建简单的连接测试
# 拖拽节点到画布
# 验证参数可编辑

# 3️⃣ 导出 YAML
# 检查配置正确性

# 4️⃣ 运行端到端测试
python3 runtime/main.py examples/test_migrated.yaml
```

---

## 📚 相关文档

- `/docs/QUICK_START.md` - 框架快速开始
- `/docs/PROJECT_PROGRESS.md` - 项目进度
- `/sdk/nodeflow_sdk.py` - SDK API 参考
- `/node-hub/rtk/run.py` - NodeFlow 示例节点
- `/node-hub/controller/run.py` - 另一个 NodeFlow 示例

---

## ❓ 常见问题

**Q: 需要修改已有的业务逻辑吗?**
A: 不需要。只需要改变数据输入/输出和配置方式，核心算法保持不变。

**Q: dora-rs 中的 callback 如何处理?**
A: NodeFlow 使用轮询模型，无需 callback。改为简单的 while 循环。

**Q: 如何处理错误?**
A: 通过错误输出端口发送错误消息（保持原有设计）。

**Q: 环境变量如何传递?**
A: 使用 `node.yaml` 中的 `params` 部分，通过 `sdk.params.get()` 访问。

**Q: 性能是否有影响?**
A: 轮询模型的延迟略高于事件驱动（通常 1-50ms），但对大多数机器人应用足够。

---

## ✅ 迁移完成标志

当以下条件满足时，迁移完成：

- ✅ node.yaml 通过 Web 编辑器验证
- ✅ 参数可在编辑器中编辑
- ✅ 节点能成功加载和启动
- ✅ 输入/输出端口正常工作
- ✅ 数据能正确流通
- ✅ 端到端测试通过
- ✅ 性能指标可接受

---

**准备好迁移了吗?** 选择 **target-generator** 开始，预计 15-20 分钟完成！
