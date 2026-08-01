# NodeFlow农田机器人仿真器

## 概述

基于ZMQ的2D差速驱动机器人仿真器，专门为农田作业场景设计。提供高精度RTK GPS模拟、运动学打滑噪声、田地生成等功能。

## 核心功能

### 1. 运动学模拟
- **差速驱动模型**：支持油门/转向和速度控制两种模式
- **打滑噪声**：基于速度的打滑模拟
  - 线速度只能减少（模拟履带打滑）
  - 角速度双向变化（模拟左右轮速度差异）
  - 可配置打滑比例（默认5%）
  - 可完全禁用打滑

### 2. 传感器模拟
- **RTK GPS**（厘米级精度）
  - FIXED固定解：2cm精度（85%时间）
  - FLOAT浮点解：10cm精度（10%时间）
  - SINGLE单点：50cm精度（4%时间）
  - NONE无定位：5m精度（1%时间）
  - 输出频率限制：默认20Hz（可配置）

- **普通GPS**：米级精度（向后兼容）
- **IMU**：加速度计、陀螺仪、磁力计
- **里程计**：轮式编码器数据

### 3. 田地生成
- **矩形田地**：指定宽度和长度
- **不规则田地**：随机多边形
- **障碍物**：圆形障碍物
- **入口点**：田地出入口标记

### 4. 物理引擎
- 边界碰撞检测
- 摩擦力模拟（可选）
- 实时/加速模式

## 安装依赖

```bash
pip3 install pyzmq pyyaml numpy
```

## 配置文件 (config.yaml)

```yaml
# 田地配置
field:
  type: rectangular        # rectangular | irregular
  width: 100.0            # 米
  length: 200.0           # 米
  num_points: 6           # 不规则田地顶点数
  num_obstacles: 0        # 障碍物数量

# 运动学引擎
kinematics:
  dt: 0.01                # 时间步长（秒）
  max_speed: 2.0          # 最大速度（m/s）
  max_accel: 1.0          # 最大加速度（m/s²）
  max_angular_vel: 1.0    # 最大角速度（rad/s）
  wheelbase: 0.5          # 轮距（米）

  # 打滑配置
  slip:
    enabled: true         # 启用/禁用打滑
    ratio: 0.05          # 打滑比例（5%）

# 传感器配置
sensors:
  gps_noise_std: 0.5      # GPS噪声标准差（米）
  imu_accel_noise: 0.1    # IMU加速度噪声
  imu_gyro_noise: 0.01    # IMU陀螺仪噪声

  # RTK配置
  rtk:
    frequency: 20.0       # RTK输出频率（Hz）
    fixed_ratio: 0.85     # FIXED状态比例
    float_ratio: 0.10     # FLOAT状态比例
    single_ratio: 0.04    # SINGLE状态比例
    none_ratio: 0.01      # NONE状态比例

# 服务器配置
server:
  zmq_port: 5555
  realtime: true          # 实时模式
```

## 启动仿真器

```bash
# 使用默认配置
python3 server.py

# 指定配置文件
python3 server.py --config my_config.yaml

# 指定端口和时间步长
python3 server.py --port 5556 --dt 0.02

# 禁用实时模式（加速仿真）
python3 server.py --no-realtime
```

## API接口

### ZMQ REQ/REP 协议

所有请求都是JSON格式，发送到 `tcp://localhost:5555`

### 1. 获取田地信息

**请求:**
```json
{
  "type": "get_field"
}
```

**响应:**
```json
{
  "status": "ok",
  "field": {
    "type": "rectangular",
    "boundary": [[x1, y1], [x2, y2], ...],
    "width": 100.0,
    "length": 200.0,
    "area": 20000.0,
    "center": [50.0, 100.0],
    "obstacles": [],
    "entry_points": [[0.0, 0.0]]
  },
  "sim_time": 123.45
}
```

### 2. 获取传感器数据

**请求:**
```json
{
  "type": "get_sensor",
  "sensor": "rtk_gps"  // "gps" | "rtk_gps" | "imu" | "odometry"
}
```

**响应（RTK GPS）:**
```json
{
  "status": "ok",
  "sensor": "rtk_gps",
  "data": {
    "latitude": 40.7128,
    "longitude": -74.0060,
    "altitude": 10.0,
    "rtk_status": "FIXED",
    "solution_type": "RTK_FIXED",
    "accuracy_h": 0.02,
    "accuracy_v": 0.03,
    "hdop": 0.5,
    "vdop": 0.8,
    "num_satellites": 14,
    "snr_avg": 47.5,
    "age_of_diff": 0.8,
    "baseline_length": 15.2,
    "ratio": 8.5,
    "timestamp": 123.45
  },
  "sim_time": 123.45
}
```

### 3. 设置速度控制（农田作业模式）

**请求:**
```json
{
  "type": "set_actuator",
  "actuator": "velocity",
  "data": {
    "linear_velocity": 1.0,    // m/s
    "angular_velocity": 0.1    // rad/s
  }
}
```

**响应:**
```json
{
  "status": "ok",
  "actuator": "velocity",
  "applied_at": 123.45,
  "linear_velocity": 1.0,
  "angular_velocity": 0.1
}
```

### 4. 设置油门/转向控制（传统模式）

**请求:**
```json
{
  "type": "set_actuator",
  "actuator": "motor",
  "data": {
    "throttle": 0.5,    // [-1, 1]
    "steering": 0.2     // [-1, 1]
  }
}
```

### 5. 获取状态

**请求:**
```json
{
  "type": "get_state"
}
```

**响应:**
```json
{
  "status": "ok",
  "state": {
    "x": 10.5,
    "y": 20.3,
    "z": 0.0,
    "yaw": 0.785,
    "pitch": 0.0,
    "roll": 0.0,
    "vx": 1.0,
    "vy": 0.0,
    "vz": 0.0,
    "omega_yaw": 0.1,
    "omega_pitch": 0.0,
    "omega_roll": 0.0,
    "ax": 0.05,
    "ay": 0.0,
    "az": -9.81,
    "sim_time": 123.45,
    "step_count": 12345
  },
  "stats": {
    "step_count": 12345,
    "request_count": 567,
    "sim_time": 123.45
  }
}
```

### 6. 重置仿真

**请求:**
```json
{
  "type": "reset"
}
```

**响应:**
```json
{
  "status": "ok",
  "message": "Simulation reset"
}
```

## Python客户端示例

```python
import zmq
import json

# 连接到仿真器
context = zmq.Context()
socket = context.socket(zmq.REQ)
socket.connect("tcp://localhost:5555")

# 获取田地信息
socket.send_json({"type": "get_field"})
field_response = socket.recv_json()
print(f"Field: {field_response['field']['width']}m x {field_response['field']['length']}m")

# 设置速度
socket.send_json({
    "type": "set_actuator",
    "actuator": "velocity",
    "data": {
        "linear_velocity": 1.0,
        "angular_velocity": 0.0
    }
})
control_response = socket.recv_json()

# 读取RTK GPS
socket.send_json({"type": "get_sensor", "sensor": "rtk_gps"})
rtk_response = socket.recv_json()
rtk_data = rtk_response['data']
print(f"RTK Status: {rtk_data['rtk_status']}, Accuracy: {rtk_data['accuracy_h']}m")

socket.close()
context.term()
```

## 运行测试

详细测试文档请参阅 [TESTING.md](TESTING.md)

```bash
# 方式1: 完整测试脚本（推荐）
bash run_tests.sh

# 方式2: 单独运行
# 单元测试（不需要服务器）
python3 test_motion_noise.py

# 核心功能测试（需要服务器）
python3 server.py &
sleep 2
python3 test_core.py

# 清理
pkill -f "python3 server.py"
```

测试覆盖：
- ✅ 打滑噪声模型（6个测试）
- ✅ RTK GPS模拟（精度分布、频率限制）
- ✅ 田地生成（矩形、不规则）
- ✅ 位置积分（直线、弧线）
- ✅ API通信（全部端点）

测试通过率: **100%** (10/10)

## 使用示例

```python
# example_usage.py - 完整的覆盖作业仿真示例
python3 server.py &
python3 example_usage.py
```

该示例展示：
1. 获取田地信息
2. 生成覆盖路径
3. 使用纯追踪控制器
4. 采样RTK定位数据

更多示例见 [example_usage.py](example_usage.py)

## 项目结构

```
simulator/
├── server.py              # 仿真器服务器
├── physics.py             # 运动学引擎（带打滑模型）
├── sensors.py             # 传感器模拟（GPS/RTK/IMU）
├── field_generator.py     # 田地生成
├── state.py              # 机器人状态定义
├── config.yaml           # 配置文件
├── test_motion_noise.py  # 单元测试
├── test_core.py          # 核心功能测试
├── test_integration.py   # 集成测试
├── run_tests.sh          # 完整测试脚本
├── example_usage.py      # 使用示例
├── README.md             # 本文档
├── QUICKSTART.md         # 快速启动指南
└── TESTING.md            # 详细测试文档
```

## 架构说明

### 外部仿真器模式

仿真器作为独立服务运行在NodeFlow图之外，通过ZMQ API与节点通信。这种设计避免了DAG拓扑中的循环依赖问题。

```
┌─────────────────────────────────────────┐
│  仿真器服务器 (外部)                      │
│  - 运动学引擎                            │
│  - 传感器模拟                            │
│  - 田地环境                              │
└─────────────┬───────────────────────────┘
              │ ZMQ API
              │
┌─────────────┴───────────────────────────┐
│  NodeFlow 图                             │
│  ┌─────────┐   ┌──────────┐   ┌───────┐│
│  │ 路径规划 │→→ │ 运动控制  │→→ │ 执行器 ││
│  └─────────┘   └──────────┘   └───┬───┘│
│                                    ↓     │
│  ┌─────────┐   ┌──────────┐   ┌───────┐│
│  │ 覆盖可视 │←← │ RTK GPS  │←← │ 传感器 ││
│  └─────────┘   └──────────┘   └───────┘│
└─────────────────────────────────────────┘
```

## 设计特点

### 1. 物理真实性
- 打滑噪声基于物理原理：履带只能减速，不能加速
- RTK状态转换模拟真实GPS行为
- 速度依赖的打滑系数

### 2. 可配置性
- YAML配置文件
- 运行时参数
- 可禁用/启用各种效果

### 3. 测试友好
- 完整的单元测试
- 集成测试脚本
- 可重现的随机行为

### 4. 性能
- 实时模式：100Hz内部仿真
- 加速模式：无延迟仿真
- 传感器频率限制（RTK 20Hz）

## 常见问题

### Q: 如何调整打滑强度？
A: 在config.yaml中修改 `kinematics.slip.ratio`，范围0.0-1.0

### Q: 如何禁用打滑？
A: 设置 `kinematics.slip.enabled: false`

### Q: RTK频率能调到更高吗？
A: 可以，在config.yaml中修改 `sensors.rtk.frequency`

### Q: 如何生成更大的田地？
A: 修改 `field.width` 和 `field.length`

### Q: 仿真速度太慢怎么办？
A: 使用 `--no-realtime` 参数启动服务器

## 开发路线

- [x] 基础运动学模拟
- [x] 打滑噪声模型
- [x] RTK GPS模拟
- [x] 田地生成
- [x] 配置文件支持
- [ ] LiDAR扫描模拟
- [ ] 碰撞检测
- [ ] 3D可视化
- [ ] 多机器人支持

## 许可证

MIT License
