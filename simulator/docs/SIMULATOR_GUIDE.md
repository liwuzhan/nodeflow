# NodeFlow 仿真系统使用指南

## 📋 目录

1. [快速开始](#快速开始)
2. [架构设计](#架构设计)
3. [启动流程](#启动流程)
4. [场景说明](#场景说明)
5. [自定义配置](#自定义配置)
6. [常见问题](#常见问题)

---

## 快速开始

### 最小化启动（仅 3 步）

```bash
# 1. 启动仿真器（终端 1）
python3 simulator/server.py

# 2. 运行测试场景（终端 2）
python3 -m runtime.main --config examples/test_simulation.yaml

# 3. 观察结果
# - 仿真器：显示机器人状态更新
# - 场景：显示节点启动和数据流
```

### 验证仿真运行

仿真器输出应该显示：
```
INFO: ZMQ socket bound to tcp://*:5555
INFO: Simulation thread started
INFO: Request loop started
INFO: 成功: 123, 失败: 0
```

场景输出应该显示：
```
INFO: sim_gps started
INFO: sim_imu started
INFO: sensor_fusion started
INFO: controller started
INFO: sim_motor started

INFO: GPS 数据: lat=40.712840, lon=-74.005958
INFO: IMU 数据: accel=10.12 m/s², gyro=0.15 rad/s
...
```

---

## 架构设计

### 系统组件

```
┌─────────────────────────────────────────┐
│  仿真器服务 (Simulator Server)           │
│  - 机器人状态管理 (RobotState)           │
│  - 运动学引擎 (KinematicsEngine)         │
│  - 传感器模拟 (SensorSimulator)          │
│  - ZMQ API 服务器                       │
└──────────────┬──────────────────────────┘
               │ ZMQ (TCP 5555)
    ┌──────────┼──────────┐
    ↓          ↓          ↓
 sim_gps    sim_imu    sim_motor
    ↓          ↓          ↑
    └──→ sensor_fusion ──→ controller
         ↓
    (数据融合)
```

### 数据流

```
传感器数据流（下行）:
  仿真器 → sim_gps → sensor_fusion
          sim_imu ↗          ↓
                         controller

控制指令流（上行）:
  controller → sim_motor → 仿真器
                           ↓
                      更新状态

闭环周期:
  1. 传感器读取 (10-100Hz)
  2. 数据融合 (50Hz)
  3. 控制计算 (20Hz)
  4. 电机执行 (50Hz)
  5. 返回第 1 步
```

### 时间同步

仿真系统使用**模拟时间**（非真实时间）：

```python
# 仿真器内部时间步进
self.state.sim_time += self.dt  # 每步 10ms

# 节点接收的时间戳
"timestamp": state.sim_time     # 同步到仿真时间
```

**优势**:
- ✅ 可加速（`--no-realtime` 模式）
- ✅ 精确回放和重现
- ✅ 便于调试和测试

---

## 启动流程

### 详细启动步骤

#### 步骤 1: 启动仿真器服务

```bash
python3 simulator/server.py [选项]
```

**可用选项**:
```
--port PORT      ZMQ 端口 (默认: 5555)
--dt DT          时间步长秒数 (默认: 0.01)
--no-realtime    非实时模式（加速仿真）
```

**示例**:
```bash
# 实时模式（10Hz 更新）
python3 simulator/server.py --port 5555 --dt 0.1

# 加速模式（100Hz 仿真速度）
python3 simulator/server.py --no-realtime
```

#### 步骤 2: 运行 NodeFlow 场景

```bash
python3 -m runtime.main --config examples/test_simulation.yaml
```

**预期输出顺序**:
1. 配置加载
2. 图验证
3. 拓扑排序
4. 节点启动（5 个节点）
5. 数据流开始

#### 步骤 3: 观察和调试

**监控仿真器状态**:
```bash
# 在另一个终端查看仿真器统计
watch -n 1 'tail -5 simulator.log'
```

**查看特定节点输出**:
```bash
# 仅显示 sim_gps 的输出
python3 -m runtime.main --config examples/test_simulation.yaml 2>&1 | grep sim_gps
```

---

## 场景说明

### test_simulation.yaml

完整的仿真闭环场景。

**包含节点**:
- `sim_gps`: 10Hz GPS 传感器
- `sim_imu`: 100Hz IMU 传感器
- `sensor_fusion`: 50Hz 数据融合
- `controller`: 20Hz 控制算法
- `sim_motor`: 电机执行器

**预期运行结果**:
```
第 0s: 节点启动
第 1s: 接收第一批传感器数据
第 2s: 开始输出控制指令
第 5s: 仿真器收到 50+ 条指令
第 10s+: 稳定运行，机器人在仿真中运动
```

---

## 自定义配置

### 修改场景参数

编辑 `examples/test_simulation.yaml`:

```yaml
nodes:
  - name: sim_gps
    params:
      frequency: 5      # 改为 5Hz

  - name: controller
    params:
      target_x: 20.0    # 改为 20 米
      target_y: 20.0
```

### 修改仿真器参数

编辑 `simulator/server.py`:

```python
# 修改物理参数
kinematics = KinematicsEngine(
    max_speed=5.0,          # 最大速度
    max_accel=2.0,          # 最大加速度
    max_angular_vel=2.0     # 最大角速度
)

# 修改传感器噪声
sensors = SensorSimulator(
    gps_noise_std=1.0,      # GPS 噪声
    imu_accel_noise=0.2,    # IMU 加速度噪声
    imu_gyro_noise=0.02     # IMU 陀螺仪噪声
)
```

### 创建新场景

```yaml
# examples/test_gps_only.yaml
# 仅 GPS 传感器测试

nodes:
  - name: sim_gps
    package: sim_gps

  - name: logger
    package: log           # 记录数据

edges:
  - {from_node: sim_gps, from_port: gps_fix, to_node: logger, to_port: data_in}
```

---

## 故障排除

### 问题 1: 仿真器连接失败

**症状**:
```
ZMQ Exception: Connection refused
```

**解决**:
```bash
# 1. 检查仿真器是否运行
ps aux | grep simulator

# 2. 检查端口
lsof -i :5555

# 3. 重启仿真器
pkill -f simulator
python3 simulator/server.py
```

### 问题 2: 节点无法连接仿真器

**症状**:
```
[ERROR] 仿真器请求超时
```

**原因**:
- 仿真器未运行
- 参数中的 host/port 错误
- 网络连接问题

**解决**:
```bash
# 测试连接
python3 -c "
import zmq
ctx = zmq.Context()
sock = ctx.socket(zmq.REQ)
sock.connect('tcp://localhost:5555')
sock.send_json({'type': 'get_state'})
print(sock.recv_json())
"
```

### 问题 3: 数据流无法建立

**症状**:
```
[WARNING] No data received on port
```

**原因**:
- 节点没有连接到边
- 上游节点未启动
- 数据格式不匹配

**解决**:
```bash
# 1. 检查配置
python3 -c "
import yaml
with open('examples/test_simulation.yaml') as f:
    config = yaml.safe_load(f)
    print('Edges:')
    for edge in config['edges']:
        print(f\"  {edge['from_node']}.{edge['from_port']} → {edge['to_node']}.{edge['to_port']}\")
"

# 2. 查看完整日志
python3 -m runtime.main --config examples/test_simulation.yaml --debug
```

### 问题 4: 控制指令不生效

**症状**:
```
仿真器收到指令，但机器人不动
```

**原因**:
- 控制指令为零
- 控制链断开
- 仿真器时间未推进

**解决**:
```python
# 在 controller 中添加调试输出
logger.info(f"Control command: throttle={cmd['throttle']}, steering={cmd['steering']}")

# 在仿真器中添加调试输出
logger.info(f"Received command: {data}")
```

---

## 性能优化

### 加速仿真

```bash
# 无限制加速（CPU 限制）
python3 simulator/server.py --no-realtime

# 特定速率（例如 50x）
python3 simulator/server.py --no-realtime &
python3 tools/sync_timer.py --speedup 50
```

### 降低 CPU 占用

减少频率：
```yaml
nodes:
  - name: sim_gps
    params:
      frequency: 5        # 从 10 改为 5

  - name: sim_imu
    params:
      frequency: 50       # 从 100 改为 50
```

### 并行仿真

运行多个场景（需要不同端口）：
```bash
# 终端 1: 仿真器 1
python3 simulator/server.py --port 5555

# 终端 2: 仿真器 2
python3 simulator/server.py --port 5556

# 终端 3: 场景 1（使用端口 5555）
python3 -m runtime.main --config scenario1.yaml

# 终端 4: 场景 2（使用端口 5556）
python3 -m runtime.main --config scenario2.yaml
```

---

## 高级用法

### 仿真回放

记录仿真轨迹并回放：

```python
# 在仿真器中添加
from simulator.state import StateHistory

history = StateHistory()

while running:
    self.state = self.kinematics.step(self.state)
    history.add(self.state)  # 记录每个状态

# 保存轨迹
import pickle
with open('trajectory.pkl', 'wb') as f:
    pickle.dump(history.history, f)

# 加载并回放
with open('trajectory.pkl', 'rb') as f:
    history = pickle.load(f)
    for state in history:
        print(f"Time: {state.sim_time}, Pos: ({state.x}, {state.y})")
```

### 自定义传感器

在 `simulator/sensors.py` 中添加新传感器：

```python
def get_lidar_scan(self, state: RobotState):
    """光学雷达扫描"""
    # 实现光学雷达模拟
    pass

def get_camera_image(self, state: RobotState):
    """摄像头图像"""
    # 实现摄像头模拟
    pass
```

### 多机器人仿真

为每个机器人创建独立的仿真器实例和场景。

---

## 性能基准

### 硬件要求

| 指标 | 最低 | 推荐 |
|------|------|------|
| CPU | 2 核心 | 4 核心+ |
| RAM | 1 GB | 4 GB |
| 网络 | 100 Mbps | 1 Gbps |

### 性能数据

| 场景 | CPU | 内存 | 延迟 |
|------|-----|------|------|
| 单传感器 | 5% | 50 MB | < 1ms |
| 完整闭环 | 15% | 150 MB | < 5ms |
| 加速（10x） | 80% | 300 MB | < 50ms |

---

## 相关资源

- [仿真器服务文档](../simulator/server.py)
- [传感器模拟](../simulator/sensors.py)
- [sim_gps 节点](../node-hub/sim_gps/README.md)
- [sim_imu 节点](../node-hub/sim_imu/README.md)
- [sim_motor 节点](../node-hub/sim_motor/README.md)

---

**最后更新**: 2025-12-20
**维护者**: NodeFlow 团队
