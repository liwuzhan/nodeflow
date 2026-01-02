# velocity_controller - 速度控制器节点

## 概述

纯追踪控制算法，输出线速度和角速度 `(v, ω)`，专为农田作业设计。

## 功能特性

- ✅ **纯追踪算法**: 经典Pure Pursuit控制器
- ✅ **速度输出**: 直接输出 (linear_velocity, angular_velocity)
- ✅ **RTK兼容**: 支持厘米级RTK GPS输入
- ✅ **路径跟踪**: 支持多点路径跟踪
- ✅ **单点导航**: 也支持单个目标点导航
- ✅ **20Hz控制**: 适合农机的控制频率

## 控制算法

### Pure Pursuit (纯追踪)

```
1. 找到前瞻点 (lookahead point)
   - 距离当前位置 lookahead_distance 米的路径点

2. 计算期望航向
   target_bearing = atan2(dy, dx)

3. 计算航向误差
   heading_error = target_bearing - current_heading

4. 计算角速度 (P控制)
   ω = K_p * heading_error

5. 计算线速度 (根据航向误差调整)
   v = max_speed * cos(heading_error)
```

### 参数调优

| 参数 | 说明 | 建议值 | 影响 |
|------|------|--------|------|
| max_speed | 最大速度 | 1.0 m/s | 速度越大，打滑越大 |
| lookahead_distance | 前瞻距离 | 2.0 m | 太小：震荡；太大：转弯慢 |
| heading_p_gain | 航向增益 | 2.0 | 太小：响应慢；太大：震荡 |
| goal_tolerance | 到达容差 | 0.3 m | 到达判断阈值 |

## 输入数据格式

### RTK GPS (必需)

```json
{
  "latitude": 40.7128,
  "longitude": -74.0060,
  "rtk_status": "FIXED",
  "accuracy_h": 0.02
}
```

### 全局路径 (可选)

```json
{
  "path": [
    [lat1, lon1],
    [lat2, lon2],
    ...
  ]
}
```

### 目标点 (可选，用于测试)

```json
{
  "latitude": 40.7130,
  "longitude": -74.0062
}
```

## 输出数据格式

```json
{
  "linear_velocity": 0.8,        // 线速度 (m/s)
  "angular_velocity": 0.15,      // 角速度 (rad/s)
  "distance_to_goal": 5.2,       // 到目标距离 (m)
  "heading_error_deg": 8.5,      // 航向误差 (度)
  "timestamp": 123.45            // 时间戳
}
```

## 使用示例

### 1. 单点导航测试

```python
from sdk.nodeflow_sdk import NodeFlowSDK

with NodeFlowSDK() as sdk:
    # 设置目标点
    sdk.send("target_point", {
        "latitude": 40.7130,
        "longitude": -74.0062
    })

    # 控制器会自动输出速度命令
    # 直到到达目标点 (< goal_tolerance)
```

### 2. 路径跟踪

```python
# 发送路径
sdk.send("global_path", {
    "path": [
        [40.7128, -74.0060],
        [40.7129, -74.0061],
        [40.7130, -74.0062],
        # ... 更多点
    ]
})

# 控制器会跟踪整条路径
```

### 3. 完整工作流

```yaml
# workflow.yaml
nodes:
  # RTK传感器
  - name: rtk
    node: sim_rtk
    params:
      frequency: 20

  # 控制器
  - name: controller
    node: velocity_controller
    params:
      max_speed: 1.0
      lookahead_distance: 2.0
    inputs:
      rtk_fix: rtk.rtk_fix

  # 执行器
  - name: actuator
    node: sim_velocity
    inputs:
      velocity_cmd: controller.velocity_cmd
```

## 配置参数

```yaml
params:
  max_speed:
    type: float
    default: 1.0
    description: "最大线速度 (m/s)"

  min_speed:
    type: float
    default: 0.2
    description: "最小线速度 (m/s)"

  lookahead_distance:
    type: float
    default: 2.0
    description: "纯追踪前瞻距离 (米)"

  goal_tolerance:
    type: float
    default: 0.3
    description: "目标点到达容差 (米)"

  heading_p_gain:
    type: float
    default: 2.0
    description: "航向控制P增益"

  max_angular_velocity:
    type: float
    default: 1.0
    description: "最大角速度 (rad/s)"

  control_frequency:
    type: integer
    default: 20
    description: "控制循环频率 (Hz)"

  enable_control:
    type: bool
    default: true
    description: "是否启用控制输出"
```

## 性能特点

### 打滑适应

控制器输出理想速度，仿真器应用打滑：

```
控制器输出: v_cmd = 1.0 m/s
     ↓
仿真器打滑: v_real = v_cmd * (1 - 0.015) = 0.985 m/s
     ↓
RTK反馈: 真实位置
     ↓
控制器闭环: 自动补偿
```

虽然存在打滑，但闭环控制可以自动补偿。

### 速度策略

- **直线行驶**: 航向误差小 → 全速前进
- **急转弯**: 航向误差大 → 减速转向
- **到达目标**: 距离<容差 → 停止

```
v = max_speed * cos(heading_error)

heading_error = 0°   → v = max_speed * 1.0 = max_speed
heading_error = 30°  → v = max_speed * 0.87
heading_error = 60°  → v = max_speed * 0.50
heading_error = 90°  → v = max_speed * 0.0
```

## 输出示例

```
2025-12-22 15:30:01,123 [velocity_controller] INFO: === velocity_controller 节点启动 ===
2025-12-22 15:30:01,124 [velocity_controller] INFO: 控制参数:
2025-12-22 15:30:01,124 [velocity_controller] INFO:   最大速度: 1.00 m/s
2025-12-22 15:30:01,124 [velocity_controller] INFO:   最小速度: 0.20 m/s
2025-12-22 15:30:01,124 [velocity_controller] INFO:   前瞻距离: 2.00 m
2025-12-22 15:30:01,124 [velocity_controller] INFO:   航向增益: 2.00
2025-12-22 15:30:01,124 [velocity_controller] INFO:   控制频率: 20 Hz
2025-12-22 15:30:01,125 [velocity_controller] INFO: 开始控制循环...
2025-12-22 15:30:01,125 [velocity_controller] INFO: 等待RTK数据和目标点/路径...
2025-12-22 15:30:02,130 [velocity_controller] INFO: 目标点已更新: (40.713, -74.0062)
2025-12-22 15:30:03,135 [velocity_controller] INFO: 控制: v=0.856 m/s, ω=0.245 rad/s | 成功: 20
2025-12-22 15:30:15,240 [velocity_controller] INFO: 已到达目标 (距离: 0.25m)
```

## 常见问题

### Q1: 为什么机器人会震荡？

A: 可能的原因：
1. `heading_p_gain` 太大 → 降低到1.0-2.0
2. `lookahead_distance` 太小 → 增加到1.5-3.0m
3. `control_frequency` 太高 → 降低到10-20Hz

### Q2: 转弯太慢/太快？

A: 调整 `lookahead_distance`:
- 太慢：减小前瞻距离 (如1.5m)
- 太快：增大前瞻距离 (如3.0m)

### Q3: 速度总是很慢？

A: 检查：
1. `max_speed` 是否设置太小
2. 航向误差是否过大 (导致速度降低)
3. 路径是否平滑

### Q4: 如何测试控制器？

A: 使用单点导航模式：

```python
# 发送一个简单的目标点
sdk.send("target_point", {
    "latitude": current_lat + 0.0001,  # 约11米
    "longitude": current_lon
})
```

### Q5: 能否在没有路径的情况下运行？

A: 可以，使用target_point模式。但建议在实际使用中提供完整路径。

## 与传统controller的区别

| 特性 | controller | velocity_controller |
|------|-----------|---------------------|
| 输出格式 | throttle/steering | linear_vel/angular_vel |
| 物理意义 | 间接控制 | 直接控制速度 |
| 打滑模型 | 不兼容 | ✅ 完全支持 |
| 农田作业 | 不适合 | ✅ 专门设计 |
| 代码复杂度 | 复杂 | 简化 |

## 调试技巧

### 1. 启用详细日志

```python
logger.setLevel(logging.DEBUG)
```

### 2. 可视化控制过程

```python
# 记录轨迹
trajectory = []
while True:
    rtk = sdk.recv("rtk_fix")
    cmd = sdk.recv("velocity_cmd")
    trajectory.append({
        "pos": (rtk['latitude'], rtk['longitude']),
        "v": cmd['linear_velocity'],
        "omega": cmd['angular_velocity']
    })

# 绘制轨迹
import matplotlib.pyplot as plt
lats = [p['pos'][0] for p in trajectory]
lons = [p['pos'][1] for p in trajectory]
plt.plot(lons, lats)
plt.show()
```

### 3. 监控航向误差

如果航向误差持续>30°，说明控制器参数需要调整。

## 版本历史

- **v1.0** (2025-12-22): 初始版本
  - 纯追踪算法实现
  - 速度输出模式
  - RTK GPS支持

## 许可证

MIT License
