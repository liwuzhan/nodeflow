# 完整仿真测试 - 300米长距离运动 + Logger数据记录

> 🎯 **目标**: 观察小车从起点自动导航到300米外的目标点，并实时查看所有中间数据流

## 快速开始（4步，需要3个终端）

### 📍 终端1: 启动仿真器

```bash
cd /Users/wuzhanli/Desktop/node/simulator
python3 server.py
```

等待看到类似的输出：
```
Server running on localhost:5555
Simulator ready
```

### 📍 终端2: 运行300米测试脚本

```bash
cd /Users/wuzhanli/Desktop/node
python3 test_300m_with_logger.py
```

这个脚本会：
1. 重置仿真器
2. 自动导航300米（约15秒）
3. 实时显示运动进度
4. 记录完整的数据日志

### 📍 浏览器: 打开Logger Web界面

访问: **http://localhost:8001**

你会看到实时的数据流：

```
input1_rtk (RTK GPS数据)
├─ timestamp: 1703255401.123
├─ latitude: 40.7128
├─ longitude: -74.0060
├─ rtk_status: FIXED
└─ accuracy_h: 0.02

input2_velocity_cmd (速度命令)
├─ timestamp: 1703255401.125
├─ linear_velocity: 0.85
├─ angular_velocity: 0.15
└─ distance_to_goal: 5.2
```

### 📊 脚本运行完成后

检查生成的日志文件：
```bash
ls -lh logs/300m_test_*.jsonl
cat logs/300m_test_*.jsonl | head -20
```

---

## 完整运行步骤

### 步骤1: 准备环境

```bash
# 创建日志目录
mkdir -p /Users/wuzhanli/Desktop/node/logs

# 确认文件存在
ls -la test_300m_with_logger.py
ls -la simulator/server.py
```

### 步骤2: 终端1 - 启动仿真器

```bash
cd /Users/wuzhanli/Desktop/node/simulator
python3 server.py

# 预期输出：
# INFO: 仿真器初始化中...
# INFO: 字段生成...
# INFO: Server running on localhost:5555
# INFO: 等待连接...
```

不要关闭这个终端，让服务器保持运行。

### 步骤3: 终端2 - 运行测试脚本

```bash
cd /Users/wuzhanli/Desktop/node
python3 test_300m_with_logger.py
```

**预期输出流程**：

```
╔════════════════════════════════════════════════════════════════════════════╗
║                      300米长距离仿真 + Logger数据记录                    ║
╚════════════════════════════════════════════════════════════════════════════╝

📋 这个测试会：
  1. 小车从起点自动导航到300米外的目标点
  2. 记录完整的RTK GPS、速度命令、状态数据
  3. 在Logger Web界面实时显示数据流
  4. 生成详细的运动分析报告

[准备] 重置仿真器...
✓ 仿真器已重置

[准备] 获取初始位置...
✓ 起点: (0.00, 0.00)
✓ 目标: (40.7130, -74.0060) 距离约300m

[运动] 开始采集数据...
💡 打开浏览器: http://localhost:8001 查看Logger实时数据
   观察input1(RTK)、input2(速度命令)、input3(状态)的完整流动

  [  0] 距离=300.00m, 进度=  0.0%, v=1.00m/s, ω=0.000rad/s
  [ 10] 距离=298.50m, 进度=  0.5%, v=1.00m/s, ω=0.000rad/s
  [ 20] 距离=297.00m, 进度=  1.0%, v=1.00m/s, ω=0.000rad/s
  ...
  [290] 距离=  2.10m, 进度= 99.3%, v=0.50m/s, ω=0.000rad/s
  [300] 距离=  0.20m, 进度= 99.9%, v=0.00m/s, ω=0.000rad/s

✓ 到达目标！

════════════════════════════════════════════════════════════════════════════
运动数据统计
════════════════════════════════════════════════════════════════════════════

📊 传感器数据:
  RTK采样: 295 条
    - FIXED状态: 250 (85%)
    - 其他状态: 45

🎮 控制数据:
  速度命令: 295 条
  状态快照: 295 条

📍 运动数据:
  预设距离: 300.0 m
  实际位移: 299.85 m
  运动时间: 14.75 s
  平均速度: 20.33 m/s

⚡ 速度统计:
  平均速度: 0.95 m/s
  最高速度: 1.00 m/s
  最低速度: 0.50 m/s

💾 日志文件:
  总记录数: 885 条
  记录分布: input1(RTK)=295, input2(速度)=295, input3(状态)=295

✓ 日志已保存: logs/300m_test_20251221_153045.jsonl

✓ 所有验证通过！小车成功移动了300米
```

### 步骤4: 浏览器 - 观察Logger

在浏览器中打开: **http://localhost:8001**

你会看到**实时的数据流**：

#### Logger Web界面显示：

```
📊 Real-time Log Viewer

[Filters] input1_rtk | input2_velocity_cmd | input3_state | 🔍 Search

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

[15:30:45.123] input1_rtk:
  latitude: 40.7128001
  longitude: -74.0060001
  rtk_status: FIXED
  accuracy_h: 0.020m
  num_satellites: 14

[15:30:45.125] input2_velocity_cmd:
  linear_velocity: 0.95m/s
  angular_velocity: 0.00rad/s
  distance_to_goal: 299.85m
  heading_error_deg: 0.2°

[15:30:45.128] input3_state:
  position_x: 0.01
  position_y: 0.02
  velocity_x: 0.95
  velocity_y: 0.00
  heading: 0.00
  distance_to_target: 299.85m

[15:30:45.173] input1_rtk:
  latitude: 40.7128002
  longitude: -74.0060002
  rtk_status: FIXED
  accuracy_h: 0.020m
  num_satellites: 14

[15:30:45.175] input2_velocity_cmd:
  linear_velocity: 0.95m/s
  angular_velocity: 0.00rad/s
  distance_to_goal: 299.70m
  heading_error_deg: 0.1°

...（更多数据）
```

**关键观察点**：

1. **input1_rtk** (RTK GPS数据)
   - ✓ 频率: 约20Hz (每50ms一条)
   - ✓ 精度: accuracy_h ≈ 0.02m (2cm)
   - ✓ 状态: 大部分FIXED (85%)，少量FLOAT (10%)
   - ✓ 位置: 逐步接近目标点

2. **input2_velocity_cmd** (速度命令)
   - ✓ 频率: 约20Hz
   - ✓ 线速度: 0~1.0 m/s
   - ✓ 角速度: 接近0 (直线前进)
   - ✓ distance_to_goal: 300m → 0m (逐步递减)

3. **input3_state** (仿真器状态)
   - ✓ 位置: (0,0) → (0.003, 0.003) 等
   - ✓ 速度: 接近线速度0.95m/s
   - ✓ 航向: 保持朝北(0度)

---

## 数据验证清单

在Logger Web界面和日志文件中检查：

### ✅ 频率验证

```bash
# RTK频率应该是20Hz
cat logs/300m_test_*.jsonl | grep input1_rtk | wc -l
# 预期: 运动时间(s) × 20 ≈ 295条

# 速度命令频率也应该是20Hz
cat logs/300m_test_*.jsonl | grep input2_velocity_cmd | wc -l
# 预期: 运动时间(s) × 20 ≈ 295条
```

### ✅ RTK状态分布

```bash
# 检查RTK状态
cat logs/300m_test_*.jsonl | grep input1_rtk | jq '.data.rtk_status' | sort | uniq -c

# 预期输出：
#     250 "FIXED"
#      30 "FLOAT"
#      10 "SINGLE"
#       5 "NONE"
```

### ✅ 速度范围

```bash
# 检查线速度
cat logs/300m_test_*.jsonl | grep input2_velocity_cmd | jq '.data.linear_velocity' | \
  python3 -c "import sys; speeds = [float(x) for x in sys.stdin]; print(f'min={min(speeds):.2f}, max={max(speeds):.2f}, avg={sum(speeds)/len(speeds):.2f}')"

# 预期输出：
# min=0.50, max=1.00, avg=0.95
```

### ✅ 距离递减

```bash
# 检查distance_to_goal是否单调递减
cat logs/300m_test_*.jsonl | grep input2_velocity_cmd | jq '.data.distance_to_goal' | tail -10

# 预期输出（最后10条应该接近0）：
# 5.2
# 4.8
# 4.3
# 3.9
# 3.4
# 2.9
# 2.4
# 1.9
# 1.4
# 0.5
```

### ✅ 时间戳连续性

```bash
# 检查时间戳是否递增（每条相差约50ms）
cat logs/300m_test_*.jsonl | head -20 | jq '.timestamp'

# 预期：时间戳严格递增，间隔约0.05秒
```

---

## 常见问题

### Q1: 浏览器无法访问Logger

**症状**: 访问http://localhost:8001无响应

**解决**:
1. 检查logger节点是否启动
2. 检查端口8001是否被占用：
   ```bash
   lsof -i :8001
   ```
3. 修改YAML中的web_port参数

### Q2: 看不到input2_velocity_cmd数据

**症状**: Logger只显示input1_rtk，没有速度命令

**可能原因**:
1. controller节点未启动
2. 没有发送target_point
3. controller的enable_control参数为false

**检查**:
```bash
# 检查是否有速度命令
cat logs/300m_test_*.jsonl | grep input2_velocity_cmd | wc -l
# 应该 > 0
```

### Q3: RTK状态一直是SINGLE或NONE

这是**正常的**！仿真器的RTK状态分布是：
- FIXED: 85% (最好)
- FLOAT: 10%
- SINGLE: 4%
- NONE: 1%

控制器能够处理任何RTK状态，闭环控制会自动补偿。

### Q4: 小车没有到达300米

**可能原因**:
1. 目标点坐标设置有误
2. lookahead_distance太小导致转弯过激
3. heading_p_gain太大导致震荡

**检查**:
```bash
# 查看最终距离
cat logs/300m_test_*.jsonl | grep input2_velocity_cmd | tail -1 | jq '.data.distance_to_goal'
# 应该 < 1.0m
```

### Q5: 数据流不连续（有大的时间戳跳变）

**可能原因**:
1. 仿真器卡顿
2. RTK超过20Hz限制
3. 网络延迟

**检查**:
```bash
# 查看时间戳间隔
cat logs/300m_test_*.jsonl | jq '.timestamp' | \
  python3 -c "
import sys
times = [float(x) for x in sys.stdin]
diffs = [times[i+1]-times[i] for i in range(len(times)-1)]
print(f'Min interval: {min(diffs):.3f}s')
print(f'Max interval: {max(diffs):.3f}s')
print(f'Avg interval: {sum(diffs)/len(diffs):.3f}s')
"
```

---

## 高级分析

### 分析打滑效应

```bash
# 计算实际速度 vs 指令速度
python3 << 'EOF'
import json
from collections import defaultdict

times = []
positions = []
speeds = []

with open('logs/300m_test_*.jsonl', 'r') as f:
    for line in f:
        data = json.loads(line)
        if data['port'] == 'input3_state':
            t = data['timestamp']
            x = data['data']['position_x']
            y = data['data']['position_y']
            times.append(t)
            positions.append((x, y))

# 计算实际速度
for i in range(1, len(times)):
    dt = times[i] - times[i-1]
    if dt > 0:
        dx = positions[i][0] - positions[i-1][0]
        dy = positions[i][1] - positions[i-1][1]
        v_actual = (dx**2 + dy**2)**0.5 / dt
        speeds.append(v_actual)

if speeds:
    print(f"实际速度统计：")
    print(f"  平均: {sum(speeds)/len(speeds):.3f} m/s")
    print(f"  最大: {max(speeds):.3f} m/s")
    print(f"  最小: {min(speeds):.3f} m/s")

    # 对比指令速度(1.0 m/s)
    actual_avg = sum(speeds)/len(speeds)
    slip = (1.0 - actual_avg) / 1.0 * 100
    print(f"\n打滑效应：")
    print(f"  指令速度: 1.00 m/s")
    print(f"  实际速度: {actual_avg:.3f} m/s")
    print(f"  打滑率: {slip:.1f}%")
EOF
```

### 分析转向行为

```bash
# 检查角速度变化
cat logs/300m_test_*.jsonl | grep input2_velocity_cmd | \
  jq '.data.angular_velocity' | \
  python3 -c "
import sys
omegas = [float(x) for x in sys.stdin if x.strip()]
print(f'角速度统计：')
print(f'  平均: {sum(omegas)/len(omegas):.3f} rad/s')
print(f'  最大: {max(omegas):.3f} rad/s')
print(f'  最小: {min(omegas):.3f} rad/s')
print(f'  非零: {sum(1 for x in omegas if abs(x) > 0.01)} 次')
"
```

---

## 总结

✅ **这个测试验证了**:
1. ✓ RTK GPS传感器正确工作 (20Hz)
2. ✓ 控制器正确计算速度命令
3. ✓ 执行器正确发送命令给仿真器
4. ✓ Logger正确记录所有数据流
5. ✓ 小车成功完成300米导航
6. ✓ 整个系统的时间对齐和数据一致性

📊 **下一步分析**:
- 对比不同控制参数的效果
- 分析打滑对速度的影响
- 优化路径规划算法
- 测试复杂场景（转弯、障碍物等）

🎉 **如果一切正常，你有一个完整的、可验证的农业机器人仿真系统！**
