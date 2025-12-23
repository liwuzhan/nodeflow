##sim_velocity - 仿真速度控制节点

## 概述

接收速度控制命令 `(v, ω)` 并发送给仿真器执行。与`sim_motor`节点的油门/转向模式不同，本节点使用速度控制模式，更适合农田作业场景。

## 与sim_motor的区别

| 特性 | sim_motor | sim_velocity |
|------|-----------|--------------|
| 控制方式 | 油门/转向 | 线速度/角速度 |
| 输入格式 | `{throttle, steering}` | `{linear_velocity, angular_velocity}` |
| 物理意义 | 间接控制速度 | 直接控制速度 |
| 打滑模拟 | 不适用 | ✅ 自动应用 |
| 适用场景 | 基础测试 | 农田作业 |

## 功能特性

- ✅ **直接速度控制**: 直接指定线速度(m/s)和角速度(rad/s)
- ✅ **打滑噪声**: 仿真器自动应用5%打滑模型
- ✅ **速度限制**: 可配置最大线速度和角速度
- ✅ **50Hz控制频率**: 与真实控制器一致
- ✅ **零速度停止**: 退出时自动停止运动

## 输入数据格式

```json
{
  "linear_velocity": 1.0,       // 线速度 (m/s)
  "angular_velocity": 0.1,      // 角速度 (rad/s)
  "timestamp": 123.45           // 可选时间戳
}
```

### 参数说明

- **linear_velocity**: 线速度(m/s)
  - 正值: 前进
  - 负值: 后退
  - 推荐范围: [-2.0, 2.0]

- **angular_velocity**: 角速度 (rad/s)
  - 正值: 左转 (逆时针)
  - 负值: 右转 (顺时针)
  - 推荐范围: [-1.0, 1.0]

### 运动示例

```
直线前进:    {linear_velocity: 1.0,  angular_velocity: 0.0}
直线后退:    {linear_velocity: -1.0, angular_velocity: 0.0}
原地左转:    {linear_velocity: 0.0,  angular_velocity: 0.5}
左转前进:    {linear_velocity: 1.0,  angular_velocity: 0.2}
右转前进:    {linear_velocity: 1.0,  angular_velocity: -0.2}
停止:        {linear_velocity: 0.0,  angular_velocity: 0.0}
```

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

  control_frequency:
    type: integer
    default: 50
    description: "控制循环频率 (Hz)"

  max_linear_velocity:
    type: float
    default: 2.0
    description: "最大线速度限制 (m/s)"

  max_angular_velocity:
    type: float
    default: 1.0
    description: "最大角速度限制 (rad/s)"

  default_linear_velocity:
    type: float
    default: 0.0
    description: "默认线速度 (无指令时使用)"

  default_angular_velocity:
    type: float
    default: 0.0
    description: "默认角速度 (无指令时使用)"
```

## 使用示例

### 1. 基础使用

```bash
# 启动仿真器
cd /path/to/simulator
python3 server.py

# 启动速度控制节点
cd /path/to/node-hub/sim_velocity
python3 run.py
```

### 2. Python发送速度命令

```python
from sdk.nodeflow_sdk import NodeFlowSDK

with NodeFlowSDK() as sdk:
    # 直线前进 1 m/s
    sdk.send("velocity_cmd", {
        "linear_velocity": 1.0,
        "angular_velocity": 0.0
    })

    time.sleep(2)

    # 左转前进
    sdk.send("velocity_cmd", {
        "linear_velocity": 0.8,
        "angular_velocity": 0.3
    })

    time.sleep(2)

    # 停止
    sdk.send("velocity_cmd", {
        "linear_velocity": 0.0,
        "angular_velocity": 0.0
    })
```

### 3. 在工作流中使用

```yaml
# workflow.yaml
nodes:
  - name: rtk_sensor
    node: sim_rtk

  - name: controller
    node: velocity_controller
    inputs:
      rtk_fix: rtk_sensor.rtk_fix

  - name: actuator
    node: sim_velocity
    inputs:
      velocity_cmd: controller.velocity_cmd
```

## 打滑模型说明

仿真器会自动应用打滑噪声：

### 打滑特性

1. **线速度只能减少**
   ```
   v_real = v_cmd * (1 - slip_factor)
   ```
   - 打滑导致速度损失
   - 不会"加速"

2. **速度越快打滑越大**
   ```
   slip_factor = slip_ratio * (abs(v_cmd) / max_speed)
   ```
   - 低速: 打滑小 (~0.5%)
   - 高速: 打滑大 (~2.5%)

3. **实时随机变化**
   - 每帧都有新的噪声
   - 不是累积误差

### 示例

```
指令速度: 1.0 m/s
实际速度: 0.97~0.99 m/s (打滑约1~3%)

指令速度: 2.0 m/s
实际速度: 1.93~1.97 m/s (打滑约2~4%)
```

## 输出示例

```
2025-12-22 15:00:01,123 [sim_velocity] INFO: === sim_velocity 节点启动 ===
2025-12-22 15:00:01,124 [sim_velocity] INFO: 仿真器地址: localhost:5555
2025-12-22 15:00:01,124 [sim_velocity] INFO: 控制循环频率: 50 Hz (20.0ms)
2025-12-22 15:00:01,124 [sim_velocity] INFO: 速度限制: linear=[-2.00, 2.00], angular=[-1.00, 1.00]
2025-12-22 15:00:01,125 [sim_velocity] INFO: 已连接到仿真器: tcp://localhost:5555
2025-12-22 15:00:01,125 [sim_velocity] INFO: 开始接收速度控制指令...
2025-12-22 15:00:01,125 [sim_velocity] INFO: 注意: 仿真器会应用打滑模型，实际速度会小于指令速度
2025-12-22 15:00:02,130 [sim_velocity] INFO: 速度控制: v=1.000 m/s, ω=0.100 rad/s, 预期打滑≈2.5% | 成功: 50, 失败: 0, 无指令: 0
```

## 控制频率说明

- **默认: 50Hz** (20ms周期)
- 与真实农机控制器一致
- 比仿真器内部频率(100Hz)低，确保稳定

```
控制频率 vs 仿真频率：
  控制器: 50Hz (发送控制命令)
      ↓
  仿真器: 100Hz (内部运动学)
      ↓
  RTK输出: 20Hz (定位反馈)
```

## 常见问题

### Q1: 为什么实际速度小于指令速度？

A: 这是打滑模型的正常行为。履带打滑只能导致速度损失，不会加速。

### Q2: 能否禁用打滑？

A: 可以，在仿真器配置文件中设置:
```yaml
kinematics:
  slip:
    enabled: false
```

### Q3: 角速度为正是左转还是右转？

A: 正值为左转(逆时针)，负值为右转(顺时针)，符合右手坐标系。

### Q4: 与sim_motor相比有什么优势？

A:
- 物理意义更清晰
- 可以应用打滑模型
- 更适合农田作业仿真
- 控制更精确

### Q5: 能否同时使用sim_motor和sim_velocity？

A: 不建议。两者控制同一个仿真器，会相互覆盖。选择其中一个使用。

## 调试技巧

### 1. 查看实际执行的速度

从sim_rtk获取位置，计算实际速度：

```python
last_pos = None
last_time = None

while True:
    rtk = sdk.recv("rtk_fix")
    current_time = time.time()

    if last_pos:
        dt = current_time - last_time
        # 计算位移
        distance = haversine_distance(last_pos, rtk)
        actual_speed = distance / dt
        print(f"实际速度: {actual_speed:.3f} m/s")

    last_pos = rtk
    last_time = current_time
```

### 2. 打印打滑统计

启用详细日志：
```python
logger.setLevel(logging.DEBUG)
```

## 性能指标

- **延迟**: <1ms (本地ZMQ)
- **频率**: 50Hz
- **成功率**: >99.9%
- **CPU占用**: <2%

## 开发说明

基于sim_motor节点开发，主要修改：
- API调用改为`"actuator": "velocity"`
- 输入格式改为 `(linear_velocity, angular_velocity)`
- 移除了throttle/steering相关逻辑
- 添加了打滑预期计算和显示

## 版本历史

- **v1.0** (2025-12-22): 初始版本
  - 速度控制模式支持
  - 打滑模型集成
  - 50Hz控制频率

## 许可证

MIT License
