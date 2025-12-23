# sim_motor - 仿真电机控制节点

仿真电机执行器节点，接收 NodeFlow 控制指令并将其发送给仿真器，驱动机器人运动。

## 功能

- ✅ 接收电机控制指令
- ✅ 将指令发送给仿真器
- ✅ 支持油门和转向控制
- ✅ 无指令时使用默认值
- ✅ 自动安全停止（退出时）

## 输入数据

**端口**: `motor_cmd` (JSON)

```json
{
  "throttle": 0.5,
  "steering": -0.2,
  "timestamp": 1234567890.123
}
```

**字段说明**:
- `throttle`: 油门，范围 [-1, 1]
  - `-1.0`: 全速后退
  - `0.0`: 停止
  - `1.0`: 全速前进
- `steering`: 转向，范围 [-1, 1]
  - `-1.0`: 全力左转
  - `0.0`: 直行
  - `1.0`: 全力右转
- `timestamp`: 时间戳 (可选)

## 参数配置

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `simulator_host` | string | localhost | 仿真器服务器地址 |
| `simulator_port` | integer | 5555 | 仿真器服务器端口 |
| `timeout` | integer | 1000 | ZMQ 请求超时 (毫秒) |
| `default_throttle` | float | 0.0 | 默认油门值（无指令时） |
| `default_steering` | float | 0.0 | 默认转向值（无指令时） |

## 使用示例

### 场景配置

```yaml
nodes:
  - name: sim_motor
    package: sim_motor
    params:
      simulator_host: localhost
      simulator_port: 5555
      default_throttle: 0.0
      default_steering: 0.0

edges:
  - {from_node: controller, from_port: control_cmd, to_node: sim_motor, to_port: motor_cmd}
```

### 作为控制链的最后一环

```yaml
nodes:
  - name: controller
    package: mock_controller_sim
  - name: sim_motor
    package: sim_motor

edges:
  - {from_node: controller, from_port: control_cmd, to_node: sim_motor, to_port: motor_cmd}
```

## 典型控制流程

```
传感器数据 (GPS/IMU)
        ↓
   传感器融合
        ↓
   定位算法
        ↓
   路径规划
        ↓
   控制算法 (Pure Pursuit, PID 等)
        ↓
   电机控制指令
        ↓
  [sim_motor] ← 接收指令
        ↓
   仿真器 ← 发送指令
        ↓
   机器人运动 (更新位置/速度)
        ↓
   返回到传感器 (闭环)
```

## 控制策略示例

### 1. 简单直线运动

```python
motor_cmd = {
    "throttle": 0.5,    # 50% 油门
    "steering": 0.0     # 直行
}
```

### 2. 以一定速度转圈

```python
motor_cmd = {
    "throttle": 0.5,     # 前进
    "steering": 0.3      # 右转
}
```

### 3. 原地转向

```python
motor_cmd = {
    "throttle": 0.0,     # 不前进
    "steering": 1.0      # 全力转向
}
```

### 4. 紧急停止

```python
motor_cmd = {
    "throttle": 0.0,
    "steering": 0.0
}
```

## 安全特性

1. **范围限制**: 自动将控制值限制在 [-1, 1]
2. **默认值**: 无指令时使用配置的默认值（通常为 0）
3. **安全停止**: 节点退出时自动发送停止指令

## 常见问题

### Q: 机器人无法运动

**症状**: 发送了控制指令，但仿真器中机器人位置不变

**原因**:
1. 仿真器未运行
2. 连接失败
3. 控制指令值为 0

**解决**:
```bash
# 1. 检查仿真器是否运行
python3 simulator/server.py

# 2. 检查连接
telnet localhost 5555

# 3. 检查控制指令
# 在控制节点中打印 motor_cmd 值
```

### Q: 运动方向反向

**症状**: 发送前进指令，机器人反向运动

**解决**: 反转控制指令
```python
motor_cmd = {
    "throttle": -command.throttle,
    "steering": -command.steering
}
```

### Q: 转向过度/不足

**症状**: 转向响应与预期不符

**原因**: 仿真器中电机参数设置

**解决**: 在控制算法中调整转向增益
```python
motor_cmd = {
    "throttle": throttle,
    "steering": steering * 0.5  # 减少转向
}
```

## 性能指标

- **控制延迟**: < 5ms
- **控制频率**: 50 Hz
- **更新范围**: [-1, 1]
- **精度**: 小数点后 3 位

## 相关节点

- **mock_controller_sim**: 控制算法实现
- **sim_gps**: 仿真 GPS 传感器
- **sim_imu**: 仿真 IMU 传感器
- **sensor_fusion**: 传感器数据融合

## 维护者

NodeFlow 团队
