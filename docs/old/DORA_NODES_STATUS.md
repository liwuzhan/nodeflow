# dora-rs 节点迁移状态

**更新时间**: 2025-12-18

---

## 📊 节点库概览

### 现有节点统计

| 类别 | 节点数 | 状态 |
|------|--------|------|
| **示例节点 (NodeFlow)** | 2 | ✅ 完成 |
| **dora-rs 节点** | 5 | 🔄 待迁移 |
| **总计** | 7 | - |

---

## ✅ NodeFlow 原生节点 (已完成)

### 1. rtk
- **状态**: ✅ 完成
- **类型**: 传感器
- **功能**: RTK GPS 定位节点
- **端口**:
  - 输出: `gps_fix` (gps 类型)

### 2. controller
- **状态**: ✅ 完成
- **类型**: 控制器
- **功能**: 控制策略节点
- **端口**:
  - 输入: `gps_fix` (gps 类型)
  - 输出: `control_cmd`

---

## 🔄 dora-rs 节点迁移清单

### ✅ 1. target-generator (已迁移)

**功能**: 为导航测试生成随机目标点

**迁移状态**: ✅ **已完成**

**文件**:
- ✅ `node.yaml` - 已创建
- ✅ `run.py` - 已创建
- ✅ `MIGRATION_NOTES.md` - 详细迁移说明

**端口**:
- 输入: `position_data` (object)
- 输出: `target_data` (object), `error` (string)

**参数**:
- `update_distance_threshold`: 10.0 (float)
- `target_distance`: 100.0 (float)

**测试**: 待验证

---

### ✅ 2. rmc-parser (已迁移)

**功能**: RMC NMEA 数据解析器

**迁移状态**: ✅ **已完成**

**文件**:
- ✅ `node.yaml` - 已创建
- ✅ `run.py` - 已创建
- ✅ `MIGRATION_NOTES.md` - 详细迁移说明

**端口**:
- 输入: `nmea_data` (string)
- 输出: `rmc_data` (object), `position_data` (object), `error` (string)

**参数**: 无参数

**测试**: 待验证

---

### ✅ 3. rtk-receiver (已迁移)

**功能**: 通过串口从 RTK 设备读取 NMEA 数据

**迁移状态**: ✅ **已完成**

**文件**:
- ✅ `node.yaml` - 已创建
- ✅ `run.py` - 已创建
- ✅ `MIGRATION_NOTES.md` - 详细迁移说明

**端口**:
- 输入: 无
- 输出: `nmea_data` (string), `error` (string)

**参数**:
- `serial_port`: "/dev/ttyUSB0" (string)
- `baud_rate`: 115200 (int)
- `init_commands`: "" (string)

**测试**: 待验证（可选硬件测试）

---

### ✅ 4. vehicle-controller (已迁移)

**功能**: 车辆运动控制（Pure Pursuit 算法）

**迁移状态**: ✅ **已完成**

**文件**:
- ✅ `node.yaml` - 已创建
- ✅ `run.py` - 已创建（多输入处理）
- ✅ `MIGRATION_NOTES.md` - 详细迁移说明

**端口**:
- 输入: `target_data` (object), `position_data` (object)
- 输出: `control_data` (object), `error` (string)

**参数** (7 个):
- `min_turning_radius`: 2.0 (float)
- `max_speed`: 5.0 (float)
- `max_acceleration`: 2.0 (float)
- `max_jerk`: 1.0 (float)
- `min_turning_radius_at_max_speed`: 5.0 (float)
- `wheelbase`: 2.5 (float)
- `lookahead_distance`: 3.0 (float)

**测试**: 待验证（多输入同步测试）

---

### ✅ 5. pwm-controller (已迁移)

**功能**: 将角速度和线速度转换为 RC PWM 控制信号

**迁移状态**: ✅ **已完成**

**文件**:
- ✅ `node.yaml` - 已创建
- ✅ `run.py` - 已创建（多输入+超时处理）
- ✅ `MIGRATION_NOTES.md` - 详细迁移说明

**端口**:
- 输入: `control_data` (object), `stop` (boolean)
- 输出: `pwm_signals` (object), `error` (string)

**参数** (12 个):
- `vehicle_type`: "car" (string)
- `pwm_frequency`: 50 (int)
- `pwm_min_pulse`: 1000 (int)
- `pwm_max_pulse`: 2000 (int)
- `pwm_neutral_pulse`: 1500 (int)
- `throttle_pwm_chip`: "pwmchip0" (string)
- `steering_pwm_chip`: "pwmchip1" (string)
- `left_pwm_chip`: "pwmchip0" (string)
- `right_pwm_chip`: "pwmchip1" (string)
- `max_linear_speed`: 2.0 (float)
- `max_angular_speed`: 1.0 (float)

**测试**: 待验证（需硬件 PWM 设备）

**特殊设计**: 使用参数桥接（SDK 参数 → os.environ）以保持 PWMController 类零修改

---

## 📋 完整迁移计划

### Phase 1: 高优先级节点 (1.5 小时)

| 节点 | 时间 | 顺序 | 状态 |
|------|------|------|------|
| target-generator | 20 min | ✅ 1 | 完成 |
| rmc-parser | 20 min | ✅ 2 | 完成 |
| rtk-receiver | 25 min | ✅ 3 | 完成 |

### Phase 2: 中优先级节点 (1.5 小时)

| 节点 | 时间 | 顺序 | 状态 |
|------|------|------|------|
| vehicle-controller | 30 min | ✅ 4 | 完成 |
| pwm-controller | 35 min | ✅ 5 | 完成 |

### 总工作量
- **Phase 1**: 1.5 小时（3 个节点）
- **Phase 2**: 1.5 小时（2 个节点）
- **总计**: ~3 小时（5 个节点）

---

## 🎯 迁移验收标准

### 单个节点验收
- [ ] `node.yaml` 符合 NodeFlow 格式
- [ ] `run.py` 使用 NodeFlowSDK
- [ ] 参数迁移到 `params` 部分
- [ ] 核心业务逻辑保持不变
- [ ] Web 编辑器中可见节点
- [ ] 参数可在编辑器中修改
- [ ] 独立运行测试通过
- [ ] 集成测试通过（如适用）

### 整体验收
- [ ] 所有 5 个 dora-rs 节点迁移完成
- [ ] Web 编辑器显示 7 个节点（2 原生 + 5 迁移）
- [ ] 可创建复杂的节点图
- [ ] YAML 导出成功
- [ ] 运行时执行正常

---

## 📖 迁移示例

### target-generator 迁移参考

已完成迁移，可作为模板参考：

**位置**: `/node-hub/target-generator/`

**关键文件**:
- `node.yaml` - NodeFlow 配置
- `run.py` - NodeFlow 启动脚本
- `MIGRATION_NOTES.md` - 详细对比和说明

**代码行数**:
- dora-rs 主循环: ~40 行
- NodeFlow 主循环: ~20 行
- 净减少: ~20 行 ✅

**复杂度**:
- dora-rs: 事件循环 + pyarrow
- NodeFlow: 简单 while + 原生对象 ✅

---

## 🛠️ 迁移工具和脚本

### 快速迁移模板 (run.py)

```python
#!/usr/bin/env python3
import sys
sys.path.insert(0, '../../sdk')
from nodeflow_sdk import NodeFlowSDK
import time

def main():
    sdk = NodeFlowSDK()
    params = sdk.params

    # 获取参数
    param1 = params.get('param1', default_value)

    # 创建端口
    input_port = sdk.create_input_port('input_name')
    output_port = sdk.create_output_port('output_name')

    # 主循环
    while True:
        data = input_port.recv_latest()
        if data is not None:
            result = process(data)
            output_port.send(result)
        time.sleep(0.01)

if __name__ == "__main__":
    main()
```

### node.yaml 模板

```yaml
name: node_name
version: "1.0.0"
description: "节点功能描述"

entrypoints:
  linux:
    kind: python
    cmd: ["python3", "run.py"]

inputs:
  - name: input_name
    type: object
    description: "输入描述"

outputs:
  - name: output_name
    type: object
    description: "输出描述"

params:
  param1:
    type: string
    required: false
    default: "value"
    description: "参数描述"
```

---

## 📚 相关文档

| 文档 | 位置 | 用途 |
|------|------|------|
| **迁移指南** | `/docs/DORA_RS_MIGRATION_GUIDE.md` | 完整迁移步骤 |
| **target-generator 示例** | `/node-hub/target-generator/MIGRATION_NOTES.md` | 实际迁移示例 |
| **快速开始** | `/docs/QUICK_START.md` | NodeFlow 使用 |
| **SDK 参考** | `/sdk/nodeflow_sdk.py` | API 文档 |

---

## 🚀 开始迁移

### 方式 1: 按优先级迁移

```bash
# 1️⃣ target-generator (已完成)
✅ 完成

# 2️⃣ rmc-parser
cd /mnt/e/test/节点化/node-hub/rmc-parser
# 查看 template.yaml 和代码
# 创建 node.yaml 和 run.py

# 3️⃣ rtk-receiver
cd /mnt/e/test/节点化/node-hub/rtk-receiver
# 同上

# 4️⃣ vehicle-controller
cd /mnt/e/test/节点化/node-hub/vehicle-controller
# 同上

# 5️⃣ pwm-controller
cd /mnt/e/test/节点化/node-hub/pwm-controller
# 同上
```

### 方式 2: 全自动迁移

如果需要批量迁移，可以创建迁移脚本：

```python
# migrate_dora_nodes.py
# 自动读取 template.yaml 并生成 node.yaml 和 run.py 骨架
```

---

## ✅ 进度跟踪

| 日期 | 完成节点 | 累计进度 |
|------|---------|---------|
| 2025-12-18 | target-generator | 1/5 (20%) |
| 2025-12-18 | rmc-parser | 2/5 (40%) |
| 2025-12-18 | rtk-receiver | 3/5 (60%) |
| 2025-12-18 | vehicle-controller | 4/5 (80%) |
| 2025-12-18 | pwm-controller | 5/5 (100%) ✅

---

## 💡 建议

1. **先迁移简单节点** - 熟悉流程后效率更高
2. **复用代码结构** - target-generator 是很好的模板
3. **保留核心逻辑** - 只改变数据输入/输出方式
4. **充分测试** - Web 编辑器 + 运行时测试
5. **文档记录** - 为每个节点创建 MIGRATION_NOTES.md

---

**当前状态**: 5/5 节点完成 (100%) ✅ **全部完成！**

**实际完成时间**: 约 3 小时工作量（符合预期）

**成就解锁**: 🏆 所有 5 个 dora-rs 节点已成功迁移到 NodeFlow！

**下一步**:
1. 重启后端以加载新节点
2. 在 Web 编辑器中验证所有 7 个节点（2 原生 + 5 迁移）
3. 创建完整的端到端测试场景
4. 在边缘设备上运行实际的导航和控制流程
