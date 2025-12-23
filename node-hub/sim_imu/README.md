# sim_imu - 仿真 IMU 节点

仿真惯性测量单元 (Inertial Measurement Unit) 节点，从 NodeFlow 仿真器读取加速度、角速度和磁力计数据。

## 功能

- ✅ 从仿真器实时读取 IMU 数据
- ✅ 提供三轴加速度计数据
- ✅ 提供三轴陀螺仪数据
- ✅ 提供三轴磁力计数据
- ✅ 模拟传感器噪声

## 输出数据

**端口**: `imu_data` (JSON)

```json
{
  "accel": {
    "x": 0.12,
    "y": -0.05,
    "z": 9.81
  },
  "gyro": {
    "x": 0.001,
    "y": 0.002,
    "z": 0.15
  },
  "mag": {
    "x": -0.32,
    "y": 0.94,
    "z": 0.0
  },
  "timestamp": 1234567890.123
}
```

**字段说明**:
- `accel`: 加速度 (m/s²)
  - `x`: 前后方向
  - `y`: 左右方向
  - `z`: 上下方向（包含重力 9.81 m/s²）
- `gyro`: 角速度 (rad/s)
  - `x`: Roll（翻滚）角速度
  - `y`: Pitch（俯仰）角速度
  - `z`: Yaw（航向）角速度
- `mag`: 磁力计（归一化）
  - 指向磁北方向
- `timestamp`: 仿真时间戳

## 参数配置

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `simulator_host` | string | localhost | 仿真器服务器地址 |
| `simulator_port` | integer | 5555 | 仿真器服务器端口 |
| `frequency` | integer | 100 | 数据发布频率 (Hz) |
| `timeout` | integer | 1000 | ZMQ 请求超时 (毫秒) |

## 使用示例

### 场景配置

```yaml
nodes:
  - name: sim_imu
    package: sim_imu
    params:
      simulator_host: localhost
      simulator_port: 5555
      frequency: 100     # 100Hz IMU 更新率（常见配置）

edges: []              # 本节点为数据源，无输入边
```

### 连接到其他节点

```yaml
edges:
  - {from_node: sim_imu, from_port: imu_data, to_node: sensor_fusion, to_port: imu_in}
  - {from_node: sim_imu, from_port: imu_data, to_node: attitude_estimator, to_port: imu_input}
```

## 数据解释

### 加速度计

加速度计测量比力 (specific force)，包括：
- 线加速度
- 重力加速度

**静止状态**: `accel.z ≈ 9.81 m/s²`

**运动状态**:
- 前进加速：`accel.x > 0`
- 右转加速：`accel.y > 0`

### 陀螺仪

测量角速度，用于姿态估计：

**左转**: `gyro.z < 0`
**右转**: `gyro.z > 0`

### 磁力计

指向磁北方向，用于航向估计：

**朝北**: `mag.y ≈ 1.0, mag.x ≈ 0.0`
**朝东**: `mag.x ≈ 1.0, mag.y ≈ 0.0`

## 常见问题

### Q: IMU 数据异常抖动

**症状**: 数据突变、高频噪声

**原因**: 仿真器噪声参数设置不当

**解决**: 调整仿真器配置
```python
# simulator/sensors.py
SensorSimulator(
    imu_accel_noise=0.05,   # 降低噪声
    imu_gyro_noise=0.005    # 降低噪声
)
```

### Q: 磁力计数据恒定

**症状**: mag 值不随机器人转向变化

**原因**: 这是正常的，磁力计在世界坐标系下指向北方，机器人转向后读数应该变化

**检查**: 确保机器人在仿真中有旋转运动（yaw 角变化）

### Q: 为什么 accel.z 不是 0？

**回答**: 加速度计测量的是比力，包括重力。静止时 z 轴应该读取到 9.81 m/s²（对抗重力的支撑力）

## 性能指标

- **发布延迟**: < 1ms (本地 ZMQ)
- **数据频率**: 可达 1000 Hz
- **CPU 占用**: < 2%
- **内存占用**: 5 MB

## 典型应用

1. **姿态估计**: 使用陀螺仪积分计算航向角
2. **传感器融合**: 与 GPS 数据融合进行定位
3. **振动检测**: 监控加速度高频分量
4. **倾斜检测**: 使用加速度计检测机器人姿态

## 相关节点

- **sim_gps**: 仿真 GPS 位置数据
- **sim_motor**: 仿真电机控制执行器
- **sensor_fusion**: GPS + IMU 数据融合
- **attitude_estimator**: 姿态估计算法

## 维护者

NodeFlow 团队
