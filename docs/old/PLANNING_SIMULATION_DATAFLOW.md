# 规划闭环仿真 - 数据流文档

## 系统架构

```
┌─────────────┐
│  仿真器      │ (外部服务，localhost:5555)
│  Simulator   │
└──────┬──────┘
       │ (ZMQ REQ/REP)
       ▼
┌─────────────────────────────────────────────────────────────────┐
│                     NodeFlow Runtime                            │
│                                                                 │
│  [Layer 0]                                                      │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │ sim_output 节点                                         │   │
│  │ ├─ 输入: 无 (读取仿真器)                               │   │
│  │ ├─ 输出: task_request (1帧), rtk_fix (50Hz)          │   │
│  └─────────────────────────────────────────────────────────┘   │
│       │                          │                              │
│       ▼                          ▼                              │
│  [Layer 1]                  [继续发送RTK]                      │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │ global_coverage 节点 (规划)                            │   │
│  │ ├─ 输入: task_request (地块 + 车辆参数)               │   │
│  │ ├─ 处理: 运行往复式扫描算法                            │   │
│  │ └─ 输出: global_path (WGS84路径点列表)               │   │
│  └─────────────────────────────────────────────────────────┘   │
│       │                                                        │
│       ▼                                                        │
│  [Layer 2]                                                     │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │ velocity_controller 节点 (控制)                        │   │
│  │ ├─ 输入1: rtk_fix (50Hz 位置 + 航向)                  │   │
│  │ ├─ 输入2: global_path (路径点序列)                     │   │
│  │ ├─ 处理: 纯追踪算法 + PID控制                         │   │
│  │ └─ 输出: velocity_cmd (线速度 + 角速度)              │   │
│  └─────────────────────────────────────────────────────────┘   │
│       │                                                        │
│       ▼                                                        │
│  [Layer 3]                                                     │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │ sim_input 节点                                          │   │
│  │ ├─ 输入: velocity_cmd (速度指令)                       │   │
│  │ └─ 发送: 将命令发往仿真器                              │   │
│  └─────────────────────────────────────────────────────────┘   │
│       │                                                        │
│       └──────────► 仿真器更新机器人位置 ──┐                  │
│                                          │                   │
└──────────────────────────────────────────┼───────────────────┘
                                           │ (闭环)
                                           │
                                           ▼
                                    sim_output 持续
                                    发送新的 RTK
```

---

## 端口详细规格

### 1. sim_output 节点

**说明**: 从仿真器读取传感器数据和任务定义

#### 输出端口

##### 📤 `task_request` (规划任务)
- **类型**: `planning.task` (JSON)
- **频率**: 1次 (初始化完成后保持不变)
- **数据格式**:

```json
{
  "id": "task_1703334567",
  "parcel": {
    "outer": [
      [121.5, 31.2],           // [lon, lat] WGS84 坐标
      [121.501, 31.2],
      [121.501, 31.2004],
      [121.5, 31.2004]
    ],
    "holes": [],               // 地块内部障碍物（多边形）
    "points": [],              // 特殊关键点
    "entries": [
      {
        "point": [121.5, 31.2],
        "type": "entry"        // 可选: "entry" / "exit"
      }
    ]
  },
  "vehicle": {
    "implement_width_m": 3.0,           // 作业幅宽（米）
    "overlap_ratio": 0.1,               // 行间重叠率（0-1）
    "path_inset_m": 1.0,                // 内缩距离（米）
    "pivot_turn": true,                 // 是否支持原地转向
    "yaw_rate_max_deg_s": 60.0,         // 最大偏航率（°/s）
    "min_turn_radius_m": 2.0            // 最小转弯半径（米）
  }
}
```

**说明**:
- `parcel`: 地块信息（WGS84坐标系）
- `vehicle`: 车辆作业参数
- 只发送一次，下游节点可随时获取最新值

---

##### 📤 `rtk_fix` (定位数据)
- **类型**: `json`
- **频率**: 50 Hz (可配置)
- **数据格式**:

```json
{
  "timestamp": 1703334567.123,     // Unix时间戳（秒）
  "latitude": 31.200015,           // WGS84 纬度（度）
  "longitude": 121.500150,         // WGS84 经度（度）
  "heading": 45.5,                 // 航向角（度，北向为0，顺时针为正）
  "heading_rad": 0.794,            // 航向角（弧度）
  "pitch": 0.0,                    // 俯仰角（度，可选）
  "accuracy": 0.05,                // 定位精度（米，RTK厘米级）
  "status": "fix"                  // 定位状态: "fix" / "float" / "no_fix"
}
```

**说明**:
- RTK高精度定位（厘米级）
- 包含当前位置和航向
- 用于velocity_controller的位置更新

---

### 2. global_coverage 节点

**说明**: 根据地块和车辆参数生成全覆盖路径

#### 输入端口

##### 📥 `task_request` → 来自 sim_output
- 接收上述 `task_request` 数据格式

#### 输出端口

##### 📤 `global_path` (规划路径)
- **类型**: `planning.path` (JSON)
- **频率**: 1次 (收到新task后)
- **数据格式**:

```json
{
  "task_id": "task_1703334567",
  "timestamp": 1703334567.200,
  "path": [
    [121.5, 31.2],              // [lon, lat] 路径点 0
    [121.5, 31.2002],           // 路径点 1
    [121.5005, 31.2002],        // 路径点 2
    [121.5005, 31.2],           // 路径点 3
    [121.501, 31.2],            // 路径点 4
    ...
  ],
  "status": "success",           // "success" / "failed"
  "message": "Path found",
  "path_length": 245.67          // 路径总长度（米）
}
```

**关键信息**:
- `path`: **完整的路径点序列** (不是单个目标点)
- 所有路径点均为 WGS84 GPS 坐标
- 路径按执行顺序排列
- velocity_controller 会逐个跟踪这些点

---

### 3. velocity_controller 节点

**说明**: 基于当前位置和规划路径，计算实时速度指令

#### 输入端口

##### 📥 `rtk_fix` → 来自 sim_output
```json
{
  "timestamp": 1703334567.250,
  "latitude": 31.200015,
  "longitude": 121.500150,
  "heading": 45.5,
  "heading_rad": 0.794,
  ...
}
```

##### 📥 `global_path` → 来自 global_coverage
```json
{
  "task_id": "task_1703334567",
  "path": [
    [121.5, 31.2],
    [121.5, 31.2002],
    [121.5005, 31.2002],
    ...
  ],
  ...
}
```

#### 输出端口

##### 📤 `velocity_cmd` (速度控制)
- **类型**: `json`
- **频率**: 20 Hz (可配置，比RTK慢)
- **数据格式**:

```json
{
  "timestamp": 1703334567.300,
  "linear_velocity": 0.85,        // 线速度（m/s），范围 [min_speed, max_speed]
  "angular_velocity": 0.5,        // 角速度（rad/s），范围 [-max_angular, +max_angular]
  "current_target_index": 3,      // 当前追踪的路径点索引
  "distance_to_target": 2.15,     // 距离下一个路径点的距离（米）
  "heading_error": 5.2,           // 航向误差（度）
  "control_mode": "pure_pursuit",  // 控制算法
  "status": "tracking"            // 状态: "tracking" / "goal_reached" / "error"
}
```

**重要**:
- **输入是完整路径** (而不是单点)
- 纯追踪算法自动计算前瞻点
- 逐个跟踪路径点，当靠近一个点时自动过渡到下一个点
- 控制频率低于RTK输入频率（平衡算力和响应）

---

### 4. sim_input 节点

**说明**: 接收速度指令，发送给仿真器执行

#### 输入端口

##### 📥 `velocity_cmd` → 来自 velocity_controller
```json
{
  "timestamp": 1703334567.300,
  "linear_velocity": 0.85,
  "angular_velocity": 0.5,
  ...
}
```

#### 数据发送到仿真器

将velocity_cmd转换为ZMQ消息，发往仿真器:

```json
{
  "type": "set_actuator",
  "actuator": "velocity",
  "data": {
    "linear_velocity": 0.85,
    "angular_velocity": 0.5
  }
}
```

---

## 数据流时序

```
时间轴:

t=0s:     sim_output 初始化
          └─ 连接仿真器 ✓
          └─ 读取地块信息 ✓
          └─ 发送 task_request (1次) ✓

t=0.05s:  global_coverage 初始化
          └─ 接收 task_request ✓
          └─ 运行规划算法... (可能耗时 0.1-1.0s)

t=0.5-1.0s: global_coverage 完成规划
            └─ 发送 global_path ✓

t=1.0s:   velocity_controller 初始化
          └─ 等待 rtk_fix 和 global_path ✓

t≥1.0s:   CONTROL LOOP (闭环运行)

          每隔 0.02s (50Hz from sim_output):
          sim_output: 发送新的 rtk_fix
              │
              ├─→ velocity_controller 接收 rtk_fix
              │
          每隔 0.05s (20Hz control):
          velocity_controller: 计算 velocity_cmd
              │
              ├─→ sim_input 接收 velocity_cmd
              │
              └─→ sim_input 发送给仿真器
                  │
                  └─→ 仿真器更新机器人位置
                      │
                      └─→ sim_output 读取新位置 (循环)
```

---

## 关键问题回答

### Q: velocity_controller 的输入是什么？
**A**: 是**整条轨迹路径** (不是单个目标点)

- **输入**: `global_path.path` = `[[lon1, lat1], [lon2, lat2], ..., [lonN, latN]]`
- **处理**: 使用纯追踪算法自动跟踪路径点序列
- **输出**: 实时的线速度和角速度

### Q: 如何定义路径点？
**A**: 路径点格式统一为 WGS84 GPS 坐标

```python
path_point = [longitude, latitude]  # [经度, 纬度]
```

### Q: 速度控制的精度?
**A**: 分两层控制

1. **粗层** (global_coverage): 路径规划 → 离散路径点列表
2. **细层** (velocity_controller): 纯追踪算法 → 连续速度指令

### Q: 整个闭环的延迟?
**A**: 约 50-100ms

- RTK输入: 20ms (50Hz)
- velocity_controller处理: 15-20ms
- ZMQ通信: 10-15ms
- 仿真器处理: 10ms

---

## 数据验证检查表

- [ ] task_request.parcel.outer: list of [lon, lat]
- [ ] task_request.parcel.entries: list of dicts with 'point' and 'type'
- [ ] task_request.vehicle: 包含implement_width_m等参数
- [ ] global_path.path: list of [lon, lat]
- [ ] rtk_fix: 包含 latitude, longitude, heading
- [ ] velocity_cmd: 包含 linear_velocity, angular_velocity

---

## 相关文件

- 规划配置: `examples/planning_simulation.yaml`
- 节点实现:
  - `node-hub/sim_output/run.py`
  - `node-hub/global_coverage/run.py`
  - `node-hub/velocity_controller/run.py`
  - `node-hub/sim_input/run.py`
