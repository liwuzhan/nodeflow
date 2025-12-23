# sim_rtk - 仿真RTK GPS节点

## 概述

从仿真器读取高精度RTK GPS数据（厘米级）并发布到NodeFlow系统。

## 功能特性

- ✅ **厘米级精度**: RTK FIXED模式下达到2cm精度
- ✅ **真实RTK状态**: 模拟FIXED/FLOAT/SINGLE/NONE四种状态
- ✅ **20Hz输出频率**: 与真实RTK设备一致
- ✅ **自动频率限制处理**: 智能处理仿真器的频率限制
- ✅ **状态统计**: 定期输出RTK状态分布

## 输出数据格式

```json
{
  "latitude": 40.7128,           // 纬度 (度)
  "longitude": -74.0060,          // 经度 (度)
  "altitude": 10.0,               // 海拔 (米)
  "rtk_status": "FIXED",          // RTK状态
  "solution_type": "RTK_FIXED",   // 解算类型
  "accuracy_h": 0.02,             // 水平精度 (米) - 2cm
  "accuracy_v": 0.03,             // 竖直精度 (米) - 3cm
  "hdop": 0.5,                    // 水平精度因子
  "vdop": 0.8,                    // 竖直精度因子
  "num_satellites": 14,           // 卫星数量
  "snr_avg": 47.5,                // 平均信噪比
  "age_of_diff": 0.8,             // 差分年龄 (秒)
  "baseline_length": 15.2,        // 基线长度 (米)
  "ratio": 8.5,                   // AR比率
  "timestamp": 123.45             // 时间戳
}
```

## RTK状态说明

| 状态 | 精度 | 说明 | 占比 |
|------|------|------|------|
| FIXED | 2cm | 固定解 - 最佳状态 | ~85% |
| FLOAT | 10cm | 浮点解 - 良好状态 | ~10% |
| SINGLE | 50cm | 单点定位 - 降级状态 | ~4% |
| NONE | 5m | 无定位 - 最差状态 | ~1% |

## 配置参数

```yaml
params:
  simulator_host:
    type: string
    default: "localhost"
    description: "仿真器服务器地址"

  simulator_port:
    type: integer
    default: 5555
    description: "仿真器服务器端口"

  frequency:
    type: integer
    default: 20
    description: "RTK数据发布频率 (Hz)"

  timeout:
    type: integer
    default: 1000
    description: "ZMQ 请求超时 (毫秒)"
```

## 使用示例

### 1. 基础使用

```bash
# 启动仿真器
cd /path/to/simulator
python3 server.py

# 启动RTK节点
cd /path/to/node-hub/sim_rtk
python3 run.py
```

### 2. 在NodeFlow工作流中使用

```yaml
# workflow.yaml
nodes:
  - name: rtk_sensor
    node: sim_rtk
    params:
      frequency: 20

  - name: controller
    node: velocity_controller
    inputs:
      rtk_fix: rtk_sensor.rtk_fix
```

### 3. Python代码访问

```python
from sdk.nodeflow_sdk import NodeFlowSDK

with NodeFlowSDK() as sdk:
    rtk_data = sdk.recv("rtk_fix")
    print(f"RTK状态: {rtk_data['rtk_status']}")
    print(f"精度: {rtk_data['accuracy_h']*100:.1f} cm")
    print(f"位置: ({rtk_data['latitude']}, {rtk_data['longitude']})")
```

## 频率限制说明

仿真器默认以20Hz频率输出RTK数据，这与真实RTK设备一致。

- 如果本节点的`frequency`参数设置为20Hz或更低，将正常工作
- 如果设置为超过20Hz（如50Hz），节点会发送请求，但仿真器会返回`data: None`
- 本节点会自动处理这种情况，不会报错，只统计为"限流"

**建议**: 保持默认的20Hz，与真实RTK设备一致

## 输出示例

```
2025-12-22 14:30:01,123 [sim_rtk] INFO: === sim_rtk 节点启动 ===
2025-12-22 14:30:01,124 [sim_rtk] INFO: 仿真器地址: localhost:5555
2025-12-22 14:30:01,124 [sim_rtk] INFO: 发布频率: 20 Hz (仿真器限制: 20Hz)
2025-12-22 14:30:01,125 [sim_rtk] INFO: 已连接到仿真器: tcp://localhost:5555
2025-12-22 14:30:01,125 [sim_rtk] INFO: 开始读取 RTK GPS 数据...
2025-12-22 14:30:02,130 [sim_rtk] INFO: RTK数据: lat=40.712800, lon=-74.006000, 状态=固定解 (2cm), 精度=2.0cm | 成功: 20, 限流: 0, 失败: 0
2025-12-22 14:30:11,140 [sim_rtk] INFO: RTK状态分布 (最近10秒): FIXED=85% FLOAT=12% SINGLE=3% NONE=0%
```

## 与sim_gps的区别

| 特性 | sim_gps | sim_rtk |
|------|---------|---------|
| 精度 | 米级 (0.5m) | 厘米级 (2cm) |
| 状态 | 无状态信息 | FIXED/FLOAT/SINGLE/NONE |
| 频率 | 可配置 (默认10Hz) | 固定20Hz |
| 输出字段 | 基础GPS字段 | RTK完整字段 |
| 用途 | 基础定位 | 高精度农田作业 |

## 故障排查

### 问题1: 连接超时

```
ERROR: 仿真器请求超时
```

**解决**: 检查仿真器是否运行
```bash
ps aux | grep "python3 server.py"
```

### 问题2: 大量"限流"计数

```
INFO: 成功: 100, 限流: 400, 失败: 0
```

**解决**: 降低frequency参数到20Hz或更低

### 问题3: RTK状态一直是NONE

**解决**: 这是仿真器的随机行为，等待几秒钟应该恢复到FIXED

## 开发说明

基于sim_gps节点开发，主要区别：
- API调用改为`"sensor": "rtk_gps"`
- 输出数据增加RTK状态和精度字段
- 添加了RTK状态统计和分布显示
- 添加了频率限制的智能处理

## 版本历史

- **v1.0** (2025-12-22): 初始版本
  - RTK GPS数据读取
  - 20Hz频率限制
  - RTK状态统计

## 许可证

MIT License
