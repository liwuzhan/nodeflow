# 快速启动指南

## 第一步：启动仿真器

```bash
cd /Users/wuzhanli/Desktop/node/simulator
python3 server.py
```

输出应该如下：
```
2025-12-21 03:33:54,239 [INFO] Loading config from: config.yaml
2025-12-21 03:33:54,239 [INFO] Generating rectangular field: 100.0m x 200.0m
2025-12-21 03:33:54,240 [INFO] Starting simulator server on port 5555
2025-12-21 03:33:54,240 [INFO] ZMQ socket bound to tcp://*:5555
2025-12-21 03:33:54,240 [INFO] Simulation thread started
2025-12-21 03:33:54,240 [INFO] Request loop started
```

## 第二步：运行客户端测试

在另一个终端：

```bash
cd /Users/wuzhanli/Desktop/node/simulator

# 运行单元测试（验证打滑噪声）
python3 test_motion_noise.py

# 或者运行集成测试（需要服务器在后台运行）
# python3 test_integration.py
```

## 第三步：写客户端代码

使用Python ZMQ客户端与仿真器通信：

```python
import zmq
import json
import time

context = zmq.Context()
socket = context.socket(zmq.REQ)
socket.connect("tcp://localhost:5555")

# 获取田地信息
socket.send_json({"type": "get_field"})
field = socket.recv_json()["field"]
print(f"Farm size: {field['width']}m x {field['length']}m")

# 设置速度（带打滑）
socket.send_json({
    "type": "set_actuator",
    "actuator": "velocity",
    "data": {"linear_velocity": 1.0, "angular_velocity": 0.0}
})
socket.recv_json()

# 读取RTK GPS（20Hz限制）
for i in range(5):
    socket.send_json({"type": "get_sensor", "sensor": "rtk_gps"})
    response = socket.recv_json()
    if response["data"]:
        rtk = response["data"]
        print(f"RTK: {rtk['rtk_status']} @ ({rtk['latitude']:.6f}, {rtk['longitude']:.6f})")
    time.sleep(0.05)

socket.close()
```

## 配置调整

编辑 `config.yaml` 来自定义仿真：

### 调整打滑强度

```yaml
kinematics:
  slip:
    enabled: true
    ratio: 0.10    # 增加到10%
```

### 改变田地大小

```yaml
field:
  type: rectangular
  width: 200.0    # 200米宽
  length: 400.0   # 400米长
```

### 改变RTK频率

```yaml
sensors:
  rtk:
    frequency: 10.0  # 改为10Hz
```

## 完整的仿真工作流

1. **田地规划节点**：获取田地信息
   ```python
   socket.send_json({"type": "get_field"})
   field = socket.recv_json()["field"]
   ```

2. **路径规划节点**：基于田地生成覆盖路径
   ```python
   # 使用field的boundary生成路径
   path = plan_coverage_path(field["boundary"])
   ```

3. **运动控制节点**：输出速度命令
   ```python
   socket.send_json({
       "type": "set_actuator",
       "actuator": "velocity",
       "data": {
           "linear_velocity": linear_vel,
           "angular_velocity": angular_vel
       }
   })
   ```

4. **传感器节点**：读取RTK GPS（会自动20Hz限制）
   ```python
   socket.send_json({"type": "get_sensor", "sensor": "rtk_gps"})
   rtk_data = socket.recv_json()["data"]
   ```

5. **覆盖可视化节点**：跟踪覆盖区域
   ```python
   # 使用RTK位置计算覆盖热图
   ```

## 关键设计要点

### 打滑噪声的三个特点：

1. **只减不增**：线速度只能减少（履带打滑）
   ```
   v_actual = v_cmd * (1 - random(0, 0.05))
   ```

2. **速度相关**：速度越快打滑越大
   ```
   slip_factor = ratio * (abs(v) / max_speed)
   ```

3. **实时变化**：每帧都有新的噪声
   ```
   实时应用，不是累积的
   ```

### RTK GPS 的四个状态：

| 状态 | 精度 | 概率 | 卫星数 |
|------|------|------|--------|
| FIXED | 2cm | 85% | 12-16 |
| FLOAT | 10cm | 10% | 8-12 |
| SINGLE | 50cm | 4% | 4-8 |
| NONE | 5m | 1% | <4 |

## 调试技巧

### 禁用打滑进行测试

```yaml
kinematics:
  slip:
    enabled: false  # 禁用打滑
```

### 启用加速仿真

```bash
python3 server.py --no-realtime
```

### 检查实际输出频率

在客户端计时：
```python
import time
last_time = time.time()
for _ in range(10):
    socket.send_json({"type": "get_sensor", "sensor": "rtk_gps"})
    response = socket.recv_json()
    if response["data"]:
        now = time.time()
        print(f"Interval: {(now - last_time)*1000:.1f}ms")
        last_time = now
```

应该看到约50ms的间隔（20Hz = 1/20s = 50ms）

## 常见错误

### "Address already in use"

```bash
# 清理被占用的端口
lsof -ti:5555 | xargs kill -9
```

### RTK数据为None

这是正常的，表示触发了频率限制。客户端应该处理这种情况：
```python
if response["data"]:
    # 处理新数据
else:
    # 等待下一个周期
    pass
```

### 打滑太强或太弱

调整config.yaml中的slip.ratio参数

## 下一步

- 查看 [README.md](README.md) 了解完整API文档
- 查看 [physics.py](physics.py) 理解运动学模型
- 查看 [sensors.py](sensors.py) 理解传感器模型
- 运行 `test_motion_noise.py` 和 `test_integration.py` 理解系统行为
