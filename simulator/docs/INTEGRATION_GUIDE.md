# NodeFlow集成指南 - 完整仿真工作流

> 🚀 **快速开始**: 3分钟让农田仿真跑起来！

本指南介绍如何使用三个新节点构建完整的农田作业仿真系统。

## 目录

1. [快速开始](#快速开始)
2. [系统架构](#系统架构)
3. [节点详解](#节点详解)
4. [配置参考](#配置参考)
5. [完整工作流示例](#完整工作流示例)
6. [常见问题](#常见问题)
7. [故障排查](#故障排查)
8. [性能优化](#性能优化)

---

## 快速开始

### 最简单的方式：单点导航

这是最简单的仿真工作流，只需3个节点。

**步骤1**: 启动仿真器（后台）

```bash
cd /path/to/simulator
python3 server.py &
```

**步骤2**: 创建工作流文件 `quickstart.yaml`

```yaml
version: "1.0"
nodes:
  # 1. RTK GPS传感器
  - name: rtk_sensor
    node: sim_rtk
    params:
      frequency: 20

  # 2. 纯追踪速度控制器
  - name: controller
    node: velocity_controller
    params:
      max_speed: 1.0
      lookahead_distance: 2.0
      heading_p_gain: 2.0
    inputs:
      rtk_fix: rtk_sensor.rtk_fix

  # 3. 速度执行器
  - name: actuator
    node: sim_velocity
    inputs:
      velocity_cmd: controller.velocity_cmd

# 这样数据就能流动了！
```

**步骤3**: 运行工作流

```bash
nodeflow run quickstart.yaml
```

**步骤4**: 在另一个终端发送目标点（使用简单的测试脚本）

```python
#!/usr/bin/env python3
import time
from sdk.nodeflow_sdk import NodeFlowSDK

with NodeFlowSDK() as sdk:
    # 发送目标点（比当前位置北偏约50米）
    sdk.send("target_point", {
        "latitude": 40.7128 + 0.0005,  # 增加~55米
        "longitude": -74.0060
    })

    # 等待机器人到达
    time.sleep(30)
    print("✓ 导航完成")
```

**完成！** 机器人会自动导航到目标点。

---

## 系统架构

### 核心概念

```
┌─────────────────────────────────────┐
│    仿真器服务器 (ZMQ :5555)          │
│  - 田地、GPS、运动学、打滑模型      │
└─────────────┬───────────────────────┘
              │ ZMQ通信
        ┌─────┴──────┐
        ↓            ↓
    [传感器]      [执行器]
    sim_rtk   ← → sim_velocity
      ↓ rtk_fix      ↑ velocity_cmd
      └──────┬───────┘
             ↓
      velocity_controller
      (纯追踪算法)
```

### 三个关键节点

| 节点 | 类型 | 功能 | 频率 |
|------|------|------|------|
| **sim_rtk** | 传感器 | 读取RTK GPS (cm级精度) | 20Hz |
| **velocity_controller** | 控制器 | 纯追踪算法，输出(v,ω) | 20Hz |
| **sim_velocity** | 执行器 | 发送速度命令给仿真器 | 50Hz |

---

## 节点详解

### 1. sim_rtk - RTK GPS传感器

**作用**: 从仿真器读取厘米级精度的GPS定位数据

**配置参数**:

```yaml
params:
  simulator_host:
    type: string
    default: "localhost"
    description: "仿真器地址"

  simulator_port:
    type: integer
    default: 5555
    description: "仿真器端口"

  frequency:
    type: integer
    default: 20
    description: "RTK频率 (Hz) - 建议固定20Hz"

  timeout:
    type: integer
    default: 1000
    description: "请求超时时间 (ms)"
```

**输出数据** (rtk_fix):

```json
{
  "latitude": 40.7128,              // 纬度 (度)
  "longitude": -74.0060,            // 经度 (度)
  "altitude": 10.5,                 // 高度 (米)
  "rtk_status": "FIXED",            // FIXED(85%) / FLOAT(10%) / SINGLE(4%) / NONE(1%)
  "accuracy_h": 0.02,               // 水平精度 (米, 2cm)
  "accuracy_v": 0.03,               // 竖直精度 (米)
  "num_satellites": 14,             // 卫星数
  "timestamp": 1703255401.123       // 时间戳
}
```

**RTK状态说明**:

| 状态 | 精度 | 概率 | 说明 |
|------|------|------|------|
| FIXED | 2cm | 85% | 固定解，最佳精度 ✓ |
| FLOAT | 10cm | 10% | 浮点解，可用 |
| SINGLE | 50cm | 4% | 单点解，精度下降 |
| NONE | 5m | 1% | 无解，不可用 ✗ |

### 2. velocity_controller - 纯追踪控制器

**作用**: 根据当前位置和目标，计算所需的线速度和角速度

**控制算法** (Pure Pursuit):

```
1. 找到前瞻点
   - 距离当前位置 lookahead_distance 米的路径点

2. 计算期望航向
   target_bearing = atan2(Δy, Δx)

3. 计算航向误差
   heading_error = target_bearing - current_heading

4. 计算角速度 (P控制)
   ω = K_p * heading_error

5. 计算线速度 (根据转弯角度调整)
   v = max_speed * |cos(heading_error)|
```

**配置参数**:

```yaml
params:
  max_speed:
    type: float
    default: 1.0
    description: "最大线速度 (m/s) - 越大越容易打滑"

  min_speed:
    type: float
    default: 0.2
    description: "最小线速度 (m/s) - 防止过慢"

  lookahead_distance:
    type: float
    default: 2.0
    description: "前瞻距离 (米)"
    tuning: |
      - 太小 (< 1m): 震荡
      - 太大 (> 3m): 转弯慢
      - 推荐: 1.5-2.5m

  heading_p_gain:
    type: float
    default: 2.0
    description: "航向控制增益"
    tuning: |
      - 太小 (< 1): 响应慢
      - 太大 (> 4): 震荡
      - 推荐: 1.5-2.5

  goal_tolerance:
    type: float
    default: 0.3
    description: "到达目标的距离容差 (米)"

  control_frequency:
    type: integer
    default: 20
    description: "控制循环频率 (Hz)"

  enable_control:
    type: boolean
    default: true
    description: "是否启用控制输出"
```

**输入数据** (至少需要一种):

```yaml
inputs:
  rtk_fix:          # RTK GPS位置 (来自sim_rtk)
  global_path:      # 全局路径 (来自global_coverage)
  target_point:     # 单点目标 (测试用)
```

**输出数据** (velocity_cmd):

```json
{
  "linear_velocity": 0.85,           // 线速度 (m/s)
  "angular_velocity": 0.15,          // 角速度 (rad/s)
  "distance_to_goal": 5.2,           // 到目标距离 (米)
  "heading_error_deg": 8.5,          // 航向误差 (度)
  "timestamp": 1703255401.123
}
```

### 3. sim_velocity - 速度执行器

**作用**: 接收控制器输出的速度命令，发送给仿真器

**配置参数**:

```yaml
params:
  simulator_host:
    type: string
    default: "localhost"

  simulator_port:
    type: integer
    default: 5555

  control_frequency:
    type: integer
    default: 50
    description: "控制循环频率 - 与控制器频率无关"

  max_linear_velocity:
    type: float
    default: 2.0
    description: "最大线速度限制 (m/s)"

  max_angular_velocity:
    type: float
    default: 1.0
    description: "最大角速度限制 (rad/s)"
```

**打滑模型** 💡

仿真器会自动应用打滑模型：

```
指令速度: v_cmd = 1.0 m/s
           ↓ (应用5%打滑)
实际速度: v_real ≈ 0.97-0.99 m/s (1-3%损失)

关键点:
- 打滑只能降低速度，不会加速
- 速度越快打滑越大
- 每次都有新的随机噪声
- RTK反馈的是真实位置 (经过打滑后)
```

---

## 配置参考

### 单点导航配置

最简单的配置，导航到一个目标点：

```yaml
version: "1.0"

nodes:
  - name: rtk
    node: sim_rtk
    params:
      frequency: 20

  - name: controller
    node: velocity_controller
    params:
      max_speed: 1.0
      lookahead_distance: 2.0
      goal_tolerance: 0.3

  - name: actuator
    node: sim_velocity
    params:
      control_frequency: 50
```

**对应Python代码**:

```python
from sdk.nodeflow_sdk import NodeFlowSDK
import time

with NodeFlowSDK() as sdk:
    # 发送目标点
    sdk.send("target_point", {
        "latitude": 40.715,
        "longitude": -74.006
    })

    # 等待到达
    time.sleep(30)
```

### 路径跟踪配置

跟踪多个路径点：

```yaml
version: "1.0"

nodes:
  - name: rtk
    node: sim_rtk
    params:
      frequency: 20

  - name: controller
    node: velocity_controller
    params:
      max_speed: 0.8
      lookahead_distance: 2.5
      heading_p_gain: 1.8

  - name: actuator
    node: sim_velocity
    params:
      control_frequency: 50
```

**对应Python代码**:

```python
from sdk.nodeflow_sdk import NodeFlowSDK
import time

with NodeFlowSDK() as sdk:
    # 发送路径（多个点）
    sdk.send("global_path", {
        "path": [
            [40.7128, -74.0060],
            [40.7129, -74.0061],
            [40.7130, -74.0062],
            [40.7131, -74.0063],
        ]
    })

    # 等待完成
    time.sleep(60)
```

---

## 完整工作流示例

### 场景1: 简单直线导航

目标: 从起点直线前进100米

```python
#!/usr/bin/env python3
"""
简单的直线导航示例
"""
import time
from sdk.nodeflow_sdk import NodeFlowSDK

def main():
    with NodeFlowSDK() as sdk:
        print("开始直线导航...")

        # 发送目标点 (约100米北偏)
        sdk.send("target_point", {
            "latitude": 40.7128 + 0.001,  # 增加~111米
            "longitude": -74.0060
        })

        start_time = time.time()

        # 监控过程
        while time.time() - start_time < 120:  # 最多2分钟
            cmd = sdk.recv_latest("velocity_cmd")
            if cmd:
                v = cmd['linear_velocity']
                omega = cmd['angular_velocity']
                distance = cmd.get('distance_to_goal', 999)

                if distance < 0.5:  # 接近目标
                    print(f"✓ 已到达目标 (距离: {distance:.2f}m)")
                    break

                print(f"运动中: v={v:.2f}m/s, ω={omega:.3f}rad/s, "
                      f"距离={distance:.2f}m")

            time.sleep(0.1)

if __name__ == "__main__":
    main()
```

### 场景2: L形路径导航

目标: 沿L形路径行驶 (100m直线 + 100m转弯)

```python
#!/usr/bin/env python3
"""
L形路径导航示例
"""
import time
from sdk.nodeflow_sdk import NodeFlowSDK

def main():
    with NodeFlowSDK() as sdk:
        print("开始L形路径导航...")

        # 定义L形路径（5个点）
        path = [
            [40.7128, -74.0060],  # 起点
            [40.7129, -74.0060],  # 北偏1个单位
            [40.7130, -74.0060],  # 继续北偏
            [40.7130, -74.0061],  # 向东转弯
            [40.7130, -74.0062],  # 继续向东
        ]

        # 发送路径
        sdk.send("global_path", {"path": path})

        start_time = time.time()
        elapsed = 0

        # 监控
        while elapsed < 180:  # 最多3分钟
            cmd = sdk.recv_latest("velocity_cmd")
            if cmd:
                v = cmd['linear_velocity']
                omega = cmd['angular_velocity']
                distance = cmd.get('distance_to_goal', 999)

                elapsed = time.time() - start_time

                # 转弯时速度会降低 (因为cos(heading_error)变小)
                if omega > 0.2:
                    status = "转弯"
                else:
                    status = "直线"

                print(f"[{elapsed:5.1f}s] {status}: "
                      f"v={v:.2f}m/s, ω={omega:.3f}rad/s, "
                      f"距离={distance:.2f}m")

                if distance < 0.5:
                    print(f"✓ 路径完成 (总耗时: {elapsed:.1f}s)")
                    break

            time.sleep(0.5)

if __name__ == "__main__":
    main()
```

### 场景3: 带参数调优的导航

同样的路径，但调整控制参数以改变行为：

```python
#!/usr/bin/env python3
"""
参数调优示例 - 对比不同的控制参数
"""
import time
from sdk.nodeflow_sdk import NodeFlowSDK
import subprocess
import sys

def run_simulation(params_desc, velocity_cmd):
    """
    启动一个仿真，使用特定的控制参数
    """
    print(f"\n{'='*60}")
    print(f"配置: {params_desc}")
    print(f"{'='*60}")

    # 启动新的工作流进程 (假设nodeflow CLI可用)
    # 这只是示意，实际需要根据你的NodeFlow框架调整

    with NodeFlowSDK() as sdk:
        path = [
            [40.7128, -74.0060],
            [40.7130, -74.0060],
            [40.7130, -74.0062],
        ]
        sdk.send("global_path", {"path": path})

        stats = {
            "max_speed": [],
            "max_omega": [],
            "completion_time": None
        }

        start = time.time()
        while time.time() - start < 120:
            cmd = sdk.recv_latest("velocity_cmd")
            if cmd:
                stats["max_speed"].append(cmd['linear_velocity'])
                stats["max_omega"].append(abs(cmd['angular_velocity']))

                if cmd.get('distance_to_goal', 999) < 0.5:
                    stats["completion_time"] = time.time() - start
                    break
            time.sleep(0.1)

        # 统计结果
        if stats["max_speed"]:
            print(f"平均速度: {sum(stats['max_speed'])/len(stats['max_speed']):.2f} m/s")
            print(f"最大角速度: {max(stats['max_omega']):.3f} rad/s")
            if stats["completion_time"]:
                print(f"完成时间: {stats['completion_time']:.1f}s")

# 对比三种配置
configs = [
    {
        "desc": "保守配置 (低速、平缓转弯)",
        "max_speed": 0.5,
        "heading_p_gain": 1.0,
    },
    {
        "desc": "平衡配置 (中等速度、正常转弯)",
        "max_speed": 1.0,
        "heading_p_gain": 2.0,
    },
    {
        "desc": "激进配置 (高速、快速转弯)",
        "max_speed": 1.5,
        "heading_p_gain": 3.0,
    }
]

for config in configs:
    run_simulation(config["desc"], config)
```

---

## 常见问题

### Q1: 机器人转弯太慢怎么办？

**可能原因1**: `lookahead_distance` 太大

```yaml
# ❌ 太大
lookahead_distance: 4.0

# ✓ 改小一点
lookahead_distance: 2.0
```

**可能原因2**: `heading_p_gain` 太小

```yaml
# ❌ 太小 (响应慢)
heading_p_gain: 1.0

# ✓ 增加一点
heading_p_gain: 2.5
```

### Q2: 机器人震荡（来回摇晃）？

这是过度响应，需要降低增益：

```yaml
# ❌ 太大 (过度响应)
heading_p_gain: 4.0

# ✓ 降低
heading_p_gain: 2.0

# 也可以增加前瞻距离
lookahead_distance: 3.0
```

### Q3: 为什么实际速度小于指令速度？

这是**打滑模型**的正常行为！

```
指令: 1.0 m/s
实际: 0.97-0.99 m/s (3%损失，正常)

如果损失> 5% 检查:
1. max_speed是否太大
2. 地面状况 (仿真器中的friction参数)
```

### Q4: 怎样加快导航完成？

调整这两个参数：

```yaml
# 1. 增加最大速度
max_speed: 1.5  # 从1.0增加到1.5

# 2. 减小前瞻距离 (更激进)
lookahead_distance: 1.5  # 从2.0减小到1.5

# 3. 增加转向增益 (更快响应)
heading_p_gain: 3.0  # 从2.0增加到3.0
```

**警告** ⚠️ : 参数太激进会导致震荡，要平衡。

### Q5: RTK数据总是FLOAT或SINGLE状态？

这是仿真器的正常分布。可以：

1. **接受它** - 控制器能处理不完美的GPS
2. **增加天气条件** - 在仿真器中调整RTK配置
3. **改进控制算法** - 使用更鲁棒的路径跟踪

---

## 故障排查

### 问题1: 仿真器无法连接

```
Error: Failed to connect to localhost:5555
```

**解决**:

```bash
# 1. 检查仿真器是否运行
ps aux | grep server.py

# 2. 启动仿真器
cd simulator
python3 server.py

# 3. 检查端口是否被占用
lsof -i :5555
```

### 问题2: RTK数据为None（频率超限）

```python
rtk = sdk.recv_latest("rtk_fix")
if rtk is None:
    print("超过RTK频率限制 (20Hz)")
```

**解决**: 不要查询RTK频率超过20Hz

```python
# ❌ 太频繁
for i in range(100):
    rtk = sdk.recv("rtk_fix")  # 立即获取

# ✓ 正确方式
import time
while True:
    rtk = sdk.recv("rtk_fix")
    time.sleep(0.05)  # 20Hz = 50ms
```

### 问题3: 控制器输出全是0

**可能原因**: 没有目标点或路径

```python
# 检查是否发送了目标
sdk.send("target_point", {
    "latitude": 40.7130,
    "longitude": -74.0062
})
```

### 问题4: 机器人走弯路（不是直线）

**原因**: 初始方向设置

```python
# 控制器假设初始方向朝北 (current_heading = 0)
# 如果你的起点实际方向不是北方，会走弯路

# 解决: 提供更长的路径点，让控制器自动校正
path = [
    [40.7128, -74.0060],  # 起点
    [40.7128, -74.0060],  # 相同点 (控制器会直线到这)
    [40.7130, -74.0060],  # 北偏2单位
]
sdk.send("global_path", {"path": path})
```

---

## 性能优化

### 1. 频率匹配

三个节点的频率配置：

```yaml
nodes:
  - name: rtk
    node: sim_rtk
    params:
      frequency: 20        # ← RTK固定20Hz

  - name: controller
    node: velocity_controller
    params:
      control_frequency: 20  # ← 与RTK匹配

  - name: actuator
    node: sim_velocity
    params:
      control_frequency: 50  # ← 可以更高
```

**说明**:
- RTK: 20Hz (固定，无法改变)
- 控制器: 20Hz (与RTK同步)
- 执行器: 50Hz (可以更高，确保平滑)

### 2. 参数预设

根据使用场景预设参数：

```yaml
# 预设1: 高精度 (低速，平缓)
profiles:
  precision:
    max_speed: 0.5
    lookahead_distance: 2.5
    heading_p_gain: 1.5

# 预设2: 平衡 (中等)
profiles:
  balanced:
    max_speed: 1.0
    lookahead_distance: 2.0
    heading_p_gain: 2.0

# 预设3: 高效率 (高速，激进)
profiles:
  efficiency:
    max_speed: 1.5
    lookahead_distance: 1.5
    heading_p_gain: 3.0
```

### 3. 路径优化

为了更快完成：

```python
# ❌ 密集路径点 (计算量大)
path = [
    [40.7128 + i*0.0001, -74.0060]
    for i in range(1000)  # 1000个点!
]

# ✓ 稀疏路径点 (更高效)
path = [
    [40.7128 + i*0.001, -74.0060]
    for i in range(100)  # 100个点，覆盖相同距离
]
```

---

## 总结

### 关键要点

✅ **必须知道**:
1. RTK频率固定20Hz，不能改变
2. 打滑是正常的，只能降速，不能加速
3. 控制参数需要根据环境调优
4. 仿真器和节点通过ZMQ通信

✅ **最常用的配置**:
```yaml
max_speed: 1.0
lookahead_distance: 2.0
heading_p_gain: 2.0
goal_tolerance: 0.3
```

✅ **调优顺序**:
1. 先确保能到达目标
2. 然后优化转弯速度
3. 最后加快直线速度

### 下一步

- 读取各节点的单独 README.md
- 查看 NODEFLOW_INTEGRATION.md 了解架构
- 运行 test_nodeflow_integration.py 验证系统
- 尝试参数调优，找到适合你的配置

### 获取帮助

```bash
# 查看仿真器日志
tail -f simulator.log

# 启用控制器详细日志
PYTHONUNBUFFERED=1 python3 run.py 2>&1 | grep velocity_controller

# 运行集成测试
python3 test_nodeflow_integration.py
```

---

**文档版本**: v1.0
**最后更新**: 2025-12-22
**相关文件**:
- [仿真器详解](./SIMULATOR_GUIDE.md)
- [技术架构](./NODEFLOW_INTEGRATION.md)
- [节点README](../node-hub/)
