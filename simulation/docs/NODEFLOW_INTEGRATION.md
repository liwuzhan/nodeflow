# 仿真器与NodeFlow集成架构

## 1. 现有节点分析

### 1.1 仿真相关节点（已存在）

#### sim_gps (传感器节点)
- **功能**: 从仿真器读取GPS数据
- **API**: `{"type": "get_sensor", "sensor": "gps"}`
- **输出**: `gps_fix` (lat, lon, alt, hdop等)
- **频率**: 可配置，默认10Hz
- **状态**: ✅ 已实现

#### sim_imu (传感器节点)
- **功能**: 从仿真器读取IMU数据
- **API**: `{"type": "get_sensor", "sensor": "imu"}`
- **输出**: `imu_data` (加速度、陀螺仪等)
- **状态**: ✅ 已实现

#### sim_motor (执行器节点)
- **功能**: 接收控制命令，发送到仿真器
- **输入**: `motor_cmd` (throttle, steering)
- **API**: `{"type": "set_actuator", "actuator": "motor", "data": {...}}`
- **频率**: 50Hz
- **状态**: ✅ 已实现

### 1.2 控制节点

#### controller (控制策略)
- **算法**: 纯追踪控制器 (Pure Pursuit)
- **输入**:
  - `gps_fix` (当前位置)
  - `global_path` (规划路径)
- **输出**: `control_cmd` (throttle, steering)
- **参数**:
  - `vehicle_type`: tracked/wheeled
  - `max_speed`: 2.0 m/s
  - `lookahead_distance`: 3.0 m
- **状态**: ✅ 已实现

### 1.3 规划节点

#### global_coverage (全局路径规划)
- **功能**: 全覆盖路径规划
- **输入**: `task_request` (包含地块和车辆配置)
- **输出**: `global_path` (WGS84经纬度路径点列表)
- **状态**: ✅ 已实现

#### farm_coverage_viz (覆盖可视化)
- **功能**: 跟踪覆盖区域并可视化
- **输入**: RTK位置数据
- **输出**: 覆盖热图、统计数据
- **状态**: 🔶 已创建但未集成

## 2. 数据流分析

### 2.1 现有数据流（油门/转向模式）

```
仿真器 (ZMQ Server :5555)
    ↓ get_sensor("gps")
sim_gps → gps_fix
    ↓
controller → control_cmd (throttle, steering)
    ↓
sim_motor → set_actuator("motor")
    ↓
仿真器 (更新位置)
```

**问题**:
- ❌ 使用throttle/steering模式，不是velocity模式
- ❌ 未利用仿真器的打滑噪声特性
- ❌ 未使用RTK GPS（只用了普通GPS）

### 2.2 农田作业理想数据流（速度控制模式）

```
仿真器 (生成田地)
    ↓ get_field()
    田地边界数据
    ↓
global_coverage (路径规划)
    ↓ global_path
controller (纯追踪)
    ↓ velocity_cmd (v, ω)
sim_velocity (新节点)
    ↓ set_actuator("velocity")
仿真器 (应用打滑噪声)
    ↓ get_sensor("rtk_gps")
sim_rtk (新节点)
    ↓ rtk_fix
controller (闭环)
```

## 3. 集成方案设计

### 3.1 需要创建的新节点

#### ✨ sim_rtk (高优先级)
**目的**: 提供RTK级别的定位数据

**配置**:
```yaml
name: sim_rtk
ports:
  outputs:
    - name: rtk_fix
      type: json
      description: RTK GPS数据 (cm级精度)
params:
  simulator_host: localhost
  simulator_port: 5555
  frequency: 20  # RTK默认20Hz
```

**输出格式**:
```json
{
  "latitude": float,
  "longitude": float,
  "altitude": float,
  "rtk_status": "FIXED|FLOAT|SINGLE|NONE",
  "solution_type": "RTK_FIXED",
  "accuracy_h": 0.02,  // 2cm
  "accuracy_v": 0.03,
  "hdop": 0.5,
  "num_satellites": 14,
  "snr_avg": 47.5,
  "age_of_diff": 0.8,
  "baseline_length": 15.2,
  "ratio": 8.5,
  "timestamp": float
}
```

#### ✨ sim_velocity (高优先级)
**目的**: 接收速度控制命令 (v, ω) 并发送到仿真器

**配置**:
```yaml
name: sim_velocity
ports:
  inputs:
    - name: velocity_cmd
      type: json
      description: 速度控制命令
params:
  simulator_host: localhost
  simulator_port: 5555
```

**输入格式**:
```json
{
  "linear_velocity": 1.0,   // m/s
  "angular_velocity": 0.1,  // rad/s
  "timestamp": float
}
```

**API调用**:
```json
{
  "type": "set_actuator",
  "actuator": "velocity",
  "data": {
    "linear_velocity": 1.0,
    "angular_velocity": 0.1
  }
}
```

#### 🔶 sim_field (中优先级)
**目的**: 从仿真器获取田地信息，作为规划输入

**配置**:
```yaml
name: sim_field
ports:
  outputs:
    - name: field_info
      type: json
```

**输出格式**:
```json
{
  "type": "rectangular",
  "boundary": [[x1, y1], [x2, y2], ...],
  "width": 100.0,
  "length": 200.0,
  "area": 20000.0,
  "obstacles": [],
  "entry_points": [[0, 0]]
}
```

### 3.2 需要修改的现有节点

#### controller 节点适配

**问题**: 当前输出throttle/steering，需要支持输出velocity

**方案1**: 修改现有controller节点
- 添加参数 `output_mode: "throttle_steering" | "velocity"`
- 根据模式输出不同格式

**方案2**: 创建新的velocity_controller节点
- 专门为农田作业设计
- 输出 (v, ω) 格式

**推荐**: 方案2 - 保持现有节点不变，创建专用节点

#### global_coverage 节点适配

**问题**: 输入格式是task_request，需要从sim_field获取田地

**方案**: 创建适配器节点 `field_to_task`
- 输入: sim_field的field_info
- 输出: global_coverage需要的task_request格式

## 4. 完整仿真工作流

### 4.1 节点图

```
┌─────────────────────────────────────────────────────┐
│                  仿真器服务器                        │
│           (ZMQ :5555, 独立进程)                     │
│  - 田地生成                                         │
│  - 运动学引擎 (带打滑)                              │
│  - RTK GPS模拟                                      │
└─────────────────────────────────────────────────────┘
         ↑ ZMQ API                    ↓ ZMQ API
         │                            │
┌────────┴────────┐         ┌────────┴────────┐
│   sim_velocity  │         │    sim_rtk      │
│  (执行器节点)    │         │  (传感器节点)    │
└────────┬────────┘         └────────┬────────┘
         ↑                            ↓
         │velocity_cmd                │rtk_fix
         │                            │
┌────────┴──────────────────┬─────────┘
│  velocity_controller      │
│   (纯追踪 v,ω版本)        │
└────────┬──────────────────┘
         ↑ global_path
         │
┌────────┴────────┐
│ global_coverage │
│   (路径规划)     │
└────────┬────────┘
         ↑ task_request
         │
┌────────┴────────┐
│  field_to_task  │
│   (格式转换)     │
└────────┬────────┘
         ↑ field_info
         │
┌────────┴────────┐
│   sim_field     │
│  (田地数据)      │
└─────────────────┘
```

### 4.2 数据流详细说明

**步骤1**: 田地生成
```
sim_field → get_field() → field_info
```

**步骤2**: 格式转换
```
field_to_task: field_info → task_request
```

**步骤3**: 路径规划
```
global_coverage: task_request → global_path
```

**步骤4**: 速度控制
```
velocity_controller: (global_path, rtk_fix) → velocity_cmd
```

**步骤5**: 执行控制
```
sim_velocity: velocity_cmd → set_actuator("velocity")
```

**步骤6**: 状态反馈
```
sim_rtk: get_sensor("rtk_gps") → rtk_fix
```

**步骤7**: 覆盖可视化 (可选)
```
farm_coverage_viz: rtk_fix → coverage_map
```

## 5. 实施优先级

### Phase 1: 核心节点 (今天完成)

1. ✨ **sim_rtk** - RTK GPS节点
   - 复用sim_gps的架构
   - 修改API调用为"rtk_gps"
   - 输出RTK状态和精度信息

2. ✨ **sim_velocity** - 速度控制节点
   - 复用sim_motor的架构
   - 修改API调用为"velocity"
   - 输入格式改为 (v, ω)

3. ✨ **velocity_controller** - 速度控制器
   - 基于现有controller
   - 输出改为 (linear_velocity, angular_velocity)

### Phase 2: 辅助节点 (后续)

4. 🔶 **sim_field** - 田地数据节点
5. 🔶 **field_to_task** - 格式转换节点

### Phase 3: 集成测试

6. ✅ 完整工作流测试
7. ✅ 打滑效果验证
8. ✅ 覆盖率对比测试

## 6. 兼容性考虑

### 6.1 向后兼容

- 保留sim_gps、sim_motor等现有节点
- 新节点作为补充，不替换
- 用户可以选择使用普通GPS或RTK GPS
- 用户可以选择throttle/steering或velocity控制

### 6.2 配置统一

所有sim_*节点使用相同的参数格式：
```yaml
params:
  simulator_host:
    type: string
    default: "localhost"
  simulator_port:
    type: integer
    default: 5555
  frequency:  # 仅传感器节点
    type: integer
    default: 10
  timeout:
    type: integer
    default: 1000
```

## 7. 测试场景

### 场景1: 基础仿真 (使用现有节点)
```
sim_gps → controller → sim_motor
```
**目的**: 验证基础连接

### 场景2: RTK仿真 (新节点)
```
sim_rtk → velocity_controller → sim_velocity
```
**目的**: 验证新节点工作

### 场景3: 完整农田作业
```
sim_field → field_to_task → global_coverage →
velocity_controller → sim_velocity
                ↓
            sim_rtk ← (闭环反馈)
```
**目的**: 端到端验证

### 场景4: 打滑效果测试
- 不同速度 (0.5, 1.0, 1.5, 2.0 m/s)
- 观察覆盖率变化
- 验证控制算法鲁棒性

## 8. 下一步行动

✅ **立即执行**:
1. 创建sim_rtk节点
2. 创建sim_velocity节点
3. 创建velocity_controller节点
4. 编写测试工作流

🔶 **后续考虑**:
5. sim_field节点
6. 可视化增强
7. 性能优化

---

**文档版本**: v1.0
**最后更新**: 2025-12-22
**状态**: ✅ 分析完成，准备实施
