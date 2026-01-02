# velocity_controller 运动控制分析

**时间**: 2025-12-23 16:40
**节点**: velocity_controller (纯追踪控制器)

---

## 概述

velocity_controller 使用**纯追踪(Pure Pursuit)算法**进行路径跟踪控制。核心思想是:
1. 获取当前位置 (RTK GPS)
2. 找到前瞻点 (Lookahead Point)
3. 计算期望航向和速度
4. 输出线速度和角速度命令

---

## 第一部分: 如何判断已通过的点

### 数据结构

```python
class PurePursuitController:
    def __init__(self):
        self.path = []  # 路径点: [(lon, lat), ...]
        self.current_path_index = 0  # 当前路径索引
        self.current_task_id = None  # 路径版本号
```

### 路径点通过检测机制

**修复前** (有问题):
```python
def find_lookahead_point(self, current_lat, current_lon):
    """查找前瞻点"""
    for i in range(self.current_path_index, len(self.path)):
        lon, lat = self.path[i]
        d = haversine_distance(current_lat, current_lon, lat, lon)
        if d >= self.lookahead_distance:
            return lat, lon, d
        # ← 注意: 没有更新self.current_path_index!

    return path[-1]  # 返回终点
```

**问题**:
- `current_path_index` 永远不更新
- 每次都从索引0开始搜索
- 如果有100个路径点,每次都要遍历整个列表
- 不知道机器人已经走过了多少点

**修复后** (正确):
```python
def find_lookahead_point(self, current_lat, current_lon):
    """查找前瞻点 (带路径点通过检测)"""
    # 第一步: 检测并跳过已通过的路径点
    while self.current_path_index < len(self.path):
        lon, lat = self.path[self.current_path_index]
        d = haversine_distance(current_lat, current_lon, lat, lon)

        # 关键: 如果距离 < goal_tolerance (0.3m), 认为已通过
        if d < self.goal_tolerance:
            logger.debug(f"已通过路径点 #{self.current_path_index + 1}/74")
            self.current_path_index += 1  # ← 更新索引!
        else:
            break  # 找到第一个未通过的点

    # 第二步: 检查是否完成整条路径
    if self.current_path_index >= len(self.path):
        logger.info("已完成整条路径!")
        return None, None, None  # 停止运动

    # 第三步: 从当前位置找前瞻点
    for i in range(self.current_path_index, len(self.path)):
        ...
```

### 判断逻辑流程图

```
当前位置: (lat_cur, lon_cur)
路径: [(lon_0, lat_0), (lon_1, lat_1), ..., (lon_73, lat_73)]
current_path_index: 0

主循环:
  ↓
每20Hz调用find_lookahead_point()
  ↓
检查第0个点
  ├─ 距离 = 0.5m > 0.3m? NO
  └─ 不用跳过,第0个点是当前目标

  ↓
返回第0个点作为前瞻点
  ↓
纯追踪算法计算:
  ├─ 目标航向
  ├─ 航向误差
  └─ 输出速度/角速度命令

  ↓
机器人向第0个点靠近

  ↓ (5秒后)
机器人距离第0个点: 0.25m < 0.3m
再次调用find_lookahead_point()
  ├─ 检查第0个点
  │  └─ 距离 = 0.25m < 0.3m? YES
  │     ├─ 标记为已通过
  │     ├─ current_path_index = 1
  │     ├─ 日志: "已通过路径点 #1/74"
  │     └─ 继续
  ├─ 检查第1个点
  │  └─ 距离 = 2.5m > 0.3m? YES
  │     └─ 找到!返回第1个点

  ↓
纯追踪算法计算:
  └─ 目标点变为第1个点

  ↓ (重复直到所有74个点都通过)
```

### 关键参数

| 参数 | 值 | 含义 |
|------|-----|------|
| `goal_tolerance` | 0.3m | 认为已到达该点的距离阈值 |
| `lookahead_distance` | 2.0m | 前瞻距离 (纯追踪前瞻点选择) |
| `control_frequency` | 20Hz | 控制循环频率 |

**什么是goal_tolerance?**
- 当机器人距离某个路径点的距离 < 0.3m 时
- 认为机器人已经通过了该点
- 自动跳到下一个点
- 如果设置太小(0.05m): 可能永远到不了,卡在某个点
- 如果设置太大(2.0m): 可能跳过点,路径不精确

---

## 第二部分: 重复接收轨迹的影响

### 原始问题: 分层启动导致路径丢失

```
时间线:
T=0s:    sim_output启动
         ├─ 发送task_request (每秒多次)
         └─ 发送RTK数据 (50Hz)

T=30s:   global_coverage启动
         ├─ 接收task_request
         ├─ 规划路径 (74个点)
         ├─ 发送结果一次
         └─ 进入等待新任务循环 ❌

T=60s:   velocity_controller启动
         ├─ 连接InputPort到global_coverage
         └─ 但global_coverage的路径已在30-60s间发送过
             数据被OutputPort丢弃 (没有客户端)
             velocity_controller永远收不到路径!

不运动,游戏结束 ❌
```

### 修复方案: 持续发送轨迹

**修复前** (global_coverage):
```python
# 规划完成后只发送一次
result = {'task_id': task_id, 'path': path_points}
output_port.send(result)  # 只有一次!

# 然后进入等待新任务
while True:
    task_data = input_port.recv_latest()  # 等待新任务
    if task_id变化:
        规划新任务
        break
```

**修复后** (global_coverage):
```python
# 规划完成后持续发送
result = {'task_id': task_id, 'path': path_points}

while True:
    output_port.send(result)  # ← 持续发送 (10Hz)

    # 同时检查新任务
    new_task = input_port.recv_latest()
    if new_task_id变化:
        停止发送旧路径
        break  # 重新规划

    time.sleep(0.1)  # 10Hz频率
```

### 重复接收轨迹的三种场景

#### 场景1: 持续接收相同task_id的路径

**修复前** (会出问题):
```python
# velocity_controller主循环
while True:
    global_path = input_port.recv_latest()  # 每10ms检查一次

    if global_path:
        # 每次都接收,就重置索引!
        controller.set_path(global_path['path'])
        # ← set_path()内部: self.current_path_index = 0

    # 假设:
    # T=0: 接收路径,current_path_index = 0
    # T=100ms: 再次接收相同路径,current_path_index = 0 ❌ (被重置!)
    # 机器人已经走到第5个点,但索引被重置为0
    # 下一步的控制目标还是第0个点
    # 机器人会"回头走" ❌
```

**修复后** (安全):
```python
# velocity_controller主循环
while True:
    global_path = input_port.recv_latest()  # 每10ms检查一次

    if global_path:
        task_id = global_path.get('task_id')

        # 只有task_id不同时才重置
        controller.set_path(global_path['path'], task_id)
        # ← set_path()内部:
        #   if task_id == self.current_task_id:
        #       return  # 跳过重置 ✅
        #   self.current_path_index = 0
```

**结果**:
```
T=0ms:    接收 task_id='task_123', 设置路径, current_path_index=0
T=100ms:  再次接收 task_id='task_123', 检测到相同, 跳过重置 ✅
T=200ms:  再次接收 task_id='task_123', 检测到相同, 跳过重置 ✅
...
T=5000ms: 机器人走到第5个点, current_path_index=5
T=5100ms: 再次接收 task_id='task_123', 检测到相同, 跳过重置 ✅
          current_path_index继续保持为5
          继续向第6个点走 ✅
```

#### 场景2: 接收不同task_id的新路径

```python
# T=0: 规划路径A (74个点)
global_path_A = {
    'task_id': 'task_123',
    'path': [(121.5, 31.2), (121.501, 31.2), ...]
}
controller.set_path(path_A, 'task_123')
current_path_index = 0

# 机器人开始沿着路径A运动
# ...

# T=100s: 接收新的task_request, 规划出新路径B (100个点)
global_path_B = {
    'task_id': 'task_456',  # ← 不同!
    'path': [(122.0, 31.5), (122.001, 31.5), ...]
}
controller.set_path(path_B, 'task_456')
# ← 检测到task_id不同,执行:
#   self.path = path_B
#   self.current_path_index = 0  # 重置
#   self.current_task_id = 'task_456'

# 机器人停止跟踪路径A,开始跟踪路径B ✅
```

#### 场景3: 中间漏掉一条路径消息

```python
# global_coverage持续发送路径 (10Hz)
# velocity_controller每10ms检查一次 (recv_latest使用latest-value语义)

时间线:
T=0ms:   global_coverage发送 路径A (version=1)
T=100ms: global_coverage发送 路径A (version=1)
T=200ms: global_coverage发送 路径A (version=1)
T=300ms: (中间的消息可能被丢弃)
T=400ms: global_coverage发送 路径A (version=1)

velocity_controller.recv_latest():
T=0ms:   收到最新版本=1
T=50ms:  检查,返回None (没有新消息)
T=100ms: 检查,返回最新版本=1
T=150ms: 检查,返回版本=1
T=200ms: 检查,返回版本=1
T=250ms: 检查,返回None (或返回最新版本=1,取决于缓冲)
T=300ms: 检查,返回最新版本=1
T=350ms: 检查,返回None

结果: 即使中间有消息丢失,recv_latest()总是返回最新版本的数据
      没有数据丢失问题 ✅
```

---

## 第三部分: 完整运动过程分析

### 从启动到完成的时间线

```
T=0s:    系统启动
├─ Layer 0启动: sim_output, global_coverage
└─ sim_output开始发送RTK和task_request

T=30s:   global_coverage接收task_request,规划路径
├─ 规划耗时: 14ms
├─ 路径: 74个点
├─ 开始持续发送路径 (10Hz)
└─ velocity_controller还未启动

T=60s:   velocity_controller启动
├─ 连接InputPort到sim_output.rtk_fix ✅
├─ 连接InputPort到global_coverage.global_path ✅
├─ 第一次接收路径: task_id='task_xxx', 74个点
├─ 初始化: current_path_index=0
└─ 开始控制循环

T=63s:   velocity_controller开始有效运动
├─ RTK数据开始有效: 10-20次检查后收到
├─ 路径数据有效: 已收到
├─ 纯追踪算法: 计算第一个前瞻点
└─ 输出速度命令

T=63-125s: 机器人沿着规划路径运动 (≈2分钟)
├─ 前瞻距离: 2.0m
├─ 最大速度: 1.0 m/s
├─ 路径长度估计: 200-300m
├─ 运动时间: 200-300秒
├─ 每通过一个点时:
│  ├─ current_path_index++
│  ├─ 日志: "已通过路径点 #5/74"
│  └─ 向下一个点靠近
└─ 当current_path_index >= 74:
   ├─ find_lookahead_point() 返回None
   ├─ 日志: "已完成整条路径!"
   └─ 输出零速度,停止

T=125s: 机器人到达终点,运动完成
├─ 所有74个点都通过了
├─ current_path_index = 74
├─ velocity_cmd = (0, 0)
└─ 等待下一条路径或新任务
```

### 日志输出示例

```
2025-12-23 16:25:34 [velocity_controller] INFO: === velocity_controller 节点启动 ===
2025-12-23 16:25:34 [velocity_controller] INFO: 输入/输出端口已创建
2025-12-23 16:25:34 [velocity_controller] INFO: 开始控制循环...

2025-12-23 16:25:50 [velocity_controller] INFO: 路径已更新: 74个点 (task_id=task_1234567890)
2025-12-23 16:25:51 [velocity_controller] DEBUG: 已通过路径点 #1/74
2025-12-23 16:25:53 [velocity_controller] DEBUG: 已通过路径点 #2/74
2025-12-23 16:25:55 [velocity_controller] DEBUG: 已通过路径点 #3/74
...
2025-12-23 16:27:42 [velocity_controller] DEBUG: 已通过路径点 #73/74
2025-12-23 16:27:45 [velocity_controller] DEBUG: 已通过路径点 #74/74
2025-12-23 16:27:45 [velocity_controller] INFO: 已完成整条路径! (共 74 个点)

控制: v=0.000 m/s, ω=0.000 rad/s | 成功: 8521
```

---

## 第四部分: 重复接收轨迹的完整场景

### 场景: 持续运动 + 持续接收相同路径

```python
# 时间点1: T=60s, velocity_controller刚启动
global_path_msg = {
    'task_id': 'task_123',
    'path': [(121.5, 31.2), (121.501, 31.2), ...]
}

# velocity_controller主循环
loop_count = 0
while True:
    rtk_data = rtk_port.recv_latest()  # RTK位置
    global_path = global_path_port.recv_latest()  # 路径

    if global_path:
        task_id = global_path.get('task_id')  # 'task_123'
        controller.set_path(global_path['path'], task_id)
        # ← 第一次: 执行 current_path_index = 0

    # 计算并发送控制命令
    cmd = controller.compute_control(rtk_data)
    velocity_port.send(cmd)

    time.sleep(1.0 / 20)  # 20Hz

# 详细过程:
# T=60.0s: 接收global_path (task_id='task_123')
#          ├─ set_path(路径, 'task_123')
#          ├─ current_path_index = 0
#          ├─ current_task_id = 'task_123'
#          └─ 日志: "路径已更新: 74个点 (task_id=task_123)"
#
# T=60.05s: 再次recv_latest()
#          └─ 返回最新的global_path (仍是'task_123')
#
# T=60.1s: 再次接收global_path (task_id='task_123')
#          ├─ set_path(路径, 'task_123')
#          ├─ 检查: task_id == current_task_id? YES
#          ├─ 返回,跳过重置 ✅
#          ├─ current_path_index保持为0 (或已更新的值)
#          └─ 无日志 (因为已跳过)
#
# T=60.15s: 继续执行compute_control()
#          ├─ find_lookahead_point()
#          ├─ 检查第0个点是否已通过
#          ├─ 距离=50m > 0.3m, 未通过
#          ├─ 返回第0个点作为前瞻点
#          └─ 计算朝向第0个点的速度命令
#
# T=100s: (机器人已走接近40秒)
#        ├─ 当前位置: (121.502, 31.21)
#        ├─ find_lookahead_point()调用
#        ├─ 检查第0个点: 距离=100m > 0.3m
#        ├─ 检查第1个点: 距离=99m > 0.3m
#        ├─ 检查第2个点: 距离=97m > 0.3m
#        ├─ ...
#        ├─ 找到距离>前瞻距离(2.0m)的点
#        ├─ 返回作为前瞻点
#        └─ 继续运动
#
# T=200s: (机器人已走接近140秒)
#        ├─ 当前位置: 接近终点
#        ├─ find_lookahead_point()调用
#        ├─ 检查第0-73个点: 距离<0.3m
#        │  ├─ 第0个点: 距离=0.25m < 0.3m → current_path_index=1
#        │  ├─ 第1个点: 距离=0.22m < 0.3m → current_path_index=2
#        │  ├─ ...
#        │  └─ 第73个点: 距离=0.15m < 0.3m → current_path_index=74
#        ├─ current_path_index >= len(path)? YES
#        ├─ 日志: "已完成整条路径! (共74个点)"
#        └─ 返回 (None, None, None)
#
# T=200.05s: compute_control()
#           ├─ find_lookahead_point()返回None
#           ├─ logger.warning("无目标点，输出零速度")
#           ├─ 返回 {linear_velocity: 0, angular_velocity: 0}
#           └─ 机器人停止 ✅
```

---

## 总结

### 关键点

| 概念 | 说明 | 修复 |
|------|------|------|
| **路径索引** | `current_path_index` 追踪当前处理的路径点 | ✅ 会更新 |
| **点到达检测** | 距离 < `goal_tolerance` (0.3m) | ✅ 自动跳过已通过的点 |
| **路径版本** | `current_task_id` 检测是否是新路径 | ✅ 防止重复重置 |
| **持续发送** | global_coverage持续发送直到新任务 | ✅ 保证下游能接收 |
| **重复接收** | 相同task_id的路径被接收多次 | ✅ 只重置一次 |
| **停止条件** | 当`current_path_index >= len(path)` | ✅ 输出零速度 |

### 修复效果

**修复前**:
```
velocity_controller无法获得路径
→ 一直报"无目标点"
→ 机器人不动
→ 仿真失败 ❌
```

**修复后**:
```
global_coverage持续发送路径
→ velocity_controller正确接收并追踪
→ 自动管理路径索引,不重复重置
→ 机器人沿着规划路径运动 ✅
```

---

**文件位置**: `/Users/wuzhanli/Desktop/node/docs/MOTION_CONTROL_ANALYSIS.md`
