# 轨迹对比可视化节点（Trajectory Visualization Node）

## 快速开始

轨迹对比可视化节点实时接收农业机器人的规划路径、实际GPS轨迹和地块信息，自动生成对比可视化图像，用于评估轨迹跟踪质量和作业验收。

### 核心功能

- **实时数据融合**：并行接收地块边界、规划路径、实际轨迹三路数据
- **高质量可视化**：生成清晰的轨迹对比图（JPG/PNG 150-200 DPI）
- **精确误差分析**：计算距离误差、横向误差、覆盖率等关键指标
- **灵活参数配置**：支持自定义输出目录、图像格式、更新频率等
- **生产就绪**：100% 测试覆盖，完整的错误处理和数据验证

### 主要特性

1. **多源数据并行输入**（Late-Joiner 模式）：
   - `task_request`：规划任务（地块边界）
   - `global_path`：路径规划器输出的全覆盖路径
   - `rtk_fix`：RTK GPS 实时定位数据（实际轨迹）

2. **可视化内容**：
   - 地块边界（绿色半透明多边形）
   - 规划路径（蓝色线条 + ○ 起点 / □ 终点）
   - 实际轨迹（红色线条 + ● 起点 / ■ 终点）
   - 统计信息面板（距离、误差、覆盖率）

3. **完整的误差分析**：
   - 规划距离 vs 实际距离
   - 距离误差（百分比）
   - 平均横向误差（到规划路径的距离）
   - 最大横向误差
   - 覆盖率计算

4. **灵活的输出方式**：
   - 高分辨率JPG/PNG图像（保存到指定目录）
   - JSON 格式的统计信息输出
   - 自动时间戳命名

---

## 工作流架构

### 完整数据流

```
┌─────────────────────────────────────────────────────────────────┐
│                                                                   │
│  农业自主系统完整工作流                                           │
│  (Autonomous Agricultural System Workflow)                       │
│                                                                   │
│  ┌──────────────┐                                                │
│  │  仿真器/传感 │ (Simulator / Sensors)                           │
│  │ sim_output   │                                                │
│  └──────┬───────┘                                                │
│         │                                                         │
│    ┌────┼────┐                                                   │
│    │    │    │                                                   │
│    ▼    ▼    ▼                                                   │
│ task_  rtk_ task_                                                │
│request fix  request                                             │
│    │    │    │                                                   │
│    │    ├────┤                                                   │
│    │    │    │                                                   │
│    │    ▼    ▼                                                   │
│    │  ┌──────────────┐                                           │
│    │  │  路径规划器   │ (Path Planner)                            │
│    │  │ global_cover │                                           │
│    │  └──────┬───────┘                                           │
│    │         │                                                   │
│    │    global_path                                              │
│    │         │                                                   │
│    │         ▼                                                   │
│    │  ┌──────────────┐                                           │
│    │  │  速度控制器   │ (Velocity Controller)                     │
│    │  │     ctrl     │                                           │
│    │  └──────────────┘                                           │
│    │                                                             │
│    └────────┬──────────────────┐                                │
│             │                  │                                │
│             ▼                  ▼                                │
│        [仿真反馈]         ┌──────────────────┐                 │
│        (sim_input)        │  轨迹可视化节点   │                 │
│                           │ trajectory_viz   │◄──────┐         │
│                           └──────┬───────────┘       │         │
│                                  │                  │         │
│                            trajectory_image         │         │
│                                  │          ┌──────┼─────┐   │
│                                  ▼          │      │     │   │
│                           ┌─────────────┐  │      │     │   │
│                           │ JPG/PNG图像  │◄─┴─task_path_ │   │
│                           │ 统计信息     │   request rtk  │   │
│                           └─────────────┘        fix    │   │
│                                                        │   │
└────────────────────────────────────────────────────────┘   │
                                                              │
  并行数据流：task_request ──┐                               │
  (Parallel Data Flow)       ├──► [可视化节点] ──► 图像输出   │
                    global_path ┤                            │
                       rtk_fix ──┘                            │
```

### 节点角色

| 节点 | 功能 | 输入 | 输出 |
|------|------|------|------|
| **仿真器/传感** | 提供环境和初始数据 | 场景配置 | task_request, rtk_fix |
| **路径规划器** | 生成全覆盖农业作业路径 | task_request | global_path |
| **速度控制器** | 基于路径生成运动命令 | global_path, rtk_fix | velocity_cmd |
| **轨迹可视化** | **对比规划路径和实际轨迹** | task_request, global_path, rtk_fix | trajectory_image |

### 轨迹可视化节点的作用

轨迹可视化节点是**平行的监控和评估单元**，它：
- 独立接收三路数据流（Late-Joiner 模式）
- 不干扰主控制流程
- 实时生成轨迹对比图
- 输出质量评估指标

---

## 使用方法

### 1. 完整工作流配置示例

```yaml
nodes:
  - id: sim_output
    package: sim_output

  - id: global_coverage
    package: global_coverage

  - id: velocity_controller
    package: velocity_controller

  - id: trajectory_viz
    package: trajectory_viz

edges:
  # 任务规划
  - from_node: sim_output
    from_port: task_request
    to_node: global_coverage
    to_port: task_request

  - from_node: sim_output
    from_port: task_request
    to_node: trajectory_viz
    to_port: task_request

  # 路径规划
  - from_node: global_coverage
    from_port: global_path
    to_node: velocity_controller
    to_port: global_path

  - from_node: global_coverage
    from_port: global_path
    to_node: trajectory_viz
    to_port: global_path

  # GPS轨迹
  - from_node: sim_output
    from_port: rtk_fix
    to_node: trajectory_viz
    to_port: rtk_fix
```

### 2. 参数配置详解

```yaml
params:
  trajectory_viz:
    # 基本配置
    output_dir: "./logs/jpg"           # 图像输出目录（推荐：./logs/jpg）
    image_format: "jpg"                 # 图像格式：jpg（较小）或 png（高质量）
    timeout: 300.0                      # 超时时间（秒），超时后自动生成最终图像

    # 更新控制
    update_interval: 5.0                # 可视化更新间隔（秒）
                                        # 设置为 0 表示仅在结束时生成
                                        # 建议：实时监控用 5-10s，验收用 0

    # 图像质量
    dpi: 150                            # 图像分辨率（DPI）
                                        # 80-100: 预览 | 150: 报告 | 200-300: 打印
    figsize_width: 14.0                 # 图像宽度（英寸）
    figsize_height: 12.0                # 图像高度（英寸）
                                        # 14x12 @ 150dpi ≈ 100-120 KB
```

### 3. 运行模式

节点支持两种运行模式：

#### 模式 1: 实时监控模式（update_interval > 0）
```yaml
params:
  trajectory_viz:
    update_interval: 5.0  # 每5秒更新一次图像
    timeout: 600.0        # 10分钟超时
```

**行为**：
- 节点持续运行，每隔 `update_interval` 秒生成一次新图像
- 用于实时监控轨迹跟踪质量
- 超时或手动中断（Ctrl+C）时生成最终图像
- 图像覆盖更新（使用最新时间戳）

#### 模式 2: 验收模式（update_interval = 0）
```yaml
params:
  trajectory_viz:
    update_interval: 0    # 不实时更新
    timeout: 600.0        # 等待作业完成
```

**行为**：
- 节点静默运行，持续收集数据
- 仅在超时或中断时生成一次最终图像
- 适用于作业完成后的验收和归档

### 4. 生成的文件

运行后会在 `output_dir` 目录下生成：

```
logs/jpg/
└── trajectory_viz_20251224_132641.jpg   # 轨迹对比可视化图像
    Size: ~100-120 KB (150 DPI, 14x12 inch)
```

**文件命名规则**：`trajectory_viz_YYYYMMDD_HHMMSS.{jpg|png}`

---

## 输入数据格式

### 1. task_request（规划任务）

**来源**: 仿真器/任务规划模块
**用途**: 获取农田地块的边界坐标
**更新频率**: 通常在作业开始时发送一次

```json
{
  "field_name": "Demo Field",
  "field_boundary": [
    {"lat": 40.1200, "lon": -88.6540},
    {"lat": 40.1400, "lon": -88.6540},
    {"lat": 40.1400, "lon": -88.6640},
    {"lat": 40.1200, "lon": -88.6640}
  ],
  "pattern": "boustrophe",        // 可选：覆盖模式
  "swath_width": 12.0             // 可选：作业幅宽（米）
}
```

**数据要求**:
- `field_name` (string): 地块名称（用于图标题）
- `field_boundary` (array): 至少 3 个顶点（闭合多边形）
- `lat`, `lon` (float): WGS84 坐标

### 2. global_path（规划路径）

**来源**: 路径规划器
**用途**: 获取规划的往复式覆盖路径
**更新频率**: 规划完成后发送一次

```json
{
  "waypoints": [
    {"lat": 40.1200, "lon": -88.6540, "heading": 0.0},
    {"lat": 40.1250, "lon": -88.6540, "heading": 0.0},
    {"lat": 40.1300, "lon": -88.6540, "heading": 0.0},
    {"lat": 40.1350, "lon": -88.6540, "heading": 0.0},
    {"lat": 40.1400, "lon": -88.6540, "heading": 0.0},
    {"lat": 40.1400, "lon": -88.6552, "heading": 90.0},
    {"lat": 40.1350, "lon": -88.6552, "heading": 180.0},
    ...
  ],
  "total_distance": 2500.0,       // 可选：路径总长（米）
  "swath_spacing": 12.0           // 可选：行间距（米）
}
```

**数据要求**:
- `waypoints` (array): 至少 2 个路径点
- 每个点包含 `lat`, `lon`，`heading` 可选
- 路径应按执行顺序排列

### 3. rtk_fix（实时GPS定位）

**来源**: RTK 定位模块/仿真器
**用途**: 获取机器人实际位置（用于轨迹记录）
**更新频率**: 持续输出（通常 10-20 Hz）

```json
{
  "latitude": 40.1234,
  "longitude": -88.6543,
  "altitude": 250.0,
  "timestamp": 1734567890.123,
  "fix_quality": 4,               // 可选：定位质量 (1-5)
  "hdop": 0.5,                    // 可选：水平精度
  "num_satellites": 12            // 可选：卫星数量
}
```

**数据要求**:
- `latitude`, `longitude` (float): WGS84 坐标（必需）
- `altitude` (float): 高度（可选）
- `timestamp` (float): Unix 时间戳（用于时间序列）
- 至少 2 个点才能绘制轨迹线

---

## 输出数据格式

### trajectory_image（可视化结果）

节点会通过 `trajectory_image` 端口输出JSON格式的统计信息：

```json
{
  "image_path": "/Users/wuzhanli/Desktop/node/logs/jpg/trajectory_viz_20251224_132641.jpg",
  "timestamp": "2025-12-24T13:26:41",
  "status": "completed",
  "trajectory_points": 30,

  "path_error": {
    "planned_distance": 6863.7,       // 规划路径总长（米）
    "actual_distance": 6566.7,        // 实际轨迹总长（米）
    "distance_error": 297.0,          // 距离误差（米）
    "distance_error_percent": 4.3,    // 距离误差百分比
    "average_lateral_error": 50.05,   // 平均横向误差（米）
    "max_lateral_error": 111.00,      // 最大横向误差（米）
    "num_points": 30                  // 轨迹点数
  },

  "coverage_metrics": {
    "coverage_rate": 95.7,            // 覆盖率（%）
    "task_duration": 150.2,           // 任务耗时（秒）
    "trajectory_points": 30
  }
}
```

**指标说明**:

| 指标 | 说明 | 单位 | 合格标准（参考） |
|------|------|------|------------------|
| `planned_distance` | 规划路径总长 | 米 | - |
| `actual_distance` | 实际行驶距离 | 米 | - |
| `distance_error_percent` | 距离误差百分比 | % | < 5-10% |
| `average_lateral_error` | 平均横向偏差 | 米 | < 0.2-0.5m（精准）<br>< 2-5m（粗放） |
| `max_lateral_error` | 最大横向偏差 | 米 | < 1-2m（精准）<br>< 10m（粗放） |
| `coverage_rate` | 路径覆盖率 | % | > 90-95% |

**注意**: 合格标准根据具体应用场景（精准播种、粗放喷洒等）而异

---

## 可视化示例

### 生成的图像效果

实际生成的轨迹对比可视化图像示例（截图来自 `logs/jpg/trajectory_viz_20251224_132641.jpg`）：

**图像布局**:
```
┌─────────────────────────────────────────────────────────────────┐
│  轨迹对比可视化 - Demo Field (2025-12-24 13:26:41)               │
├─────────────────────────────────────────────────────────────────┤
│                                                                   │
│    ┌─────────────────────────────────────────────┐  图例：       │
│    │   🟢 地块边界（绿色半透明矩形）             │  ━━ 规划路径  │
│    │                                              │  ─── 实际轨迹 │
│    │         ━━━━━━━━━━━━━━━━━━━━━━               │  ○/□ 规划起/终│
│    │        ║                       ║              │  ●/■ 实际起/终│
│    │        ║  🔵 ───────────── 🟦  ║ (第1趟)      │               │
│    │        ║  🔴 ───────────── ⬛ ║              │               │
│    │        ║         │             ║              │               │
│    │        ║         ▼             ║ (转弯)       │               │
│    │        ║  🟦 ◄───────────── 🔵  ║ (第2趟)      │               │
│    │        ║  ⬛ ◄───────────── 🔴  ║              │               │
│    │        ║         │             ║              │               │
│    │        ║         ▼             ║ (转弯)       │               │
│    │        ║  🔵 ───────────── 🟦  ║ (第3趟)      │               │
│    │        ║  🔴 ───────────── ⬛ ║              │               │
│    │         ━━━━━━━━━━━━━━━━━━━━━━               │               │
│    └─────────────────────────────────────────────┘               │
│                                                                   │
│  ┌─ 轨迹统计 ────────────────────┐                                │
│  │ ─────────────────────────────│                                │
│  │ 规划距离: 6863.7 m           │                                │
│  │ 实际距离: 6566.7 m           │                                │
│  │ 距离误差: 297.0 m (4.3%)     │                                │
│  │                              │                                │
│  │ 平均横向误差: 50.05 m        │                                │
│  │ 最大横向误差: 111.00 m       │                                │
│  │                              │                                │
│  │ 轨迹点数: 30                 │                                │
│  │ 覆盖率: 95.7%                │                                │
│  │ 任务耗时: 0.0 s              │                                │
│  └──────────────────────────────┘                                │
│                                                                   │
│  X轴：经度 (°)     Y轴：纬度 (°)                                  │
└─────────────────────────────────────────────────────────────────┘
```

### 图像要素说明

| 要素 | 颜色/样式 | 说明 |
|------|----------|------|
| **地块边界** | 绿色半透明多边形 | 农田边界，填充 alpha=0.2 |
| **规划路径** | 蓝色实线（linewidth=2） | 往复式覆盖路径（Boustrophe） |
| **实际轨迹** | 红色实线（linewidth=2） | 从 RTK GPS 累积的实际轨迹 |
| **规划起点** | 蓝色圆圈 ○ (markersize=10) | 规划路径第一个点 |
| **规划终点** | 蓝色方块 □ (markersize=10) | 规划路径最后一个点 |
| **实际起点** | 红色圆圈 ● (markersize=10) | 实际轨迹第一个点 |
| **实际终点** | 红色方块 ■ (markersize=10) | 实际轨迹最后一个点 |
| **统计面板** | 米黄色圆角框 | 误差和覆盖率统计 |

### 坐标系统

- **X 轴**: 经度（Longitude, °）
- **Y 轴**: 纬度（Latitude, °）
- **坐标系**: WGS84
- **距离计算**: 经纬度转米制
  - 1° 纬度 ≈ 111,000 米
  - 1° 经度 ≈ 111,000 × cos(纬度) 米

---

## 技术实现

### 核心算法

#### 1. 地理坐标转换（Haversine 近似）

```python
# 经纬度转米
dlat = (lat2 - lat1) * 111000  # 1° 纬度 ≈ 111 km
dlon = (lon2 - lon1) * 111000 * cos(radians(avg_lat))
distance = sqrt(dlat² + dlon²)
```

#### 2. 点到线段距离（向量投影法）

```python
# 计算实际点 P 到规划路径线段 AB 的最小距离
vec_AB = B - A
vec_AP = P - A
projection = dot(vec_AP, vec_AB) / dot(vec_AB, vec_AB)
t = clamp(projection, 0, 1)
closest_point = A + t * vec_AB
lateral_distance = norm(P - closest_point)
```

#### 3. 覆盖率计算

```python
coverage_rate = (实际轨迹点数 / 预期点数) * 100%
# 预期点数基于规划距离和采样率估算
```

### 数据流处理

- **Late-Joiner 模式**: 使用 SharedBuffer + ZMQ，新订阅者可读取历史数据
- **并行接收**: 三个输入端口独立异步接收
- **累积存储**: GPS 轨迹持续累积，直到生成最终图像
- **定时触发**: `update_interval` 定时器控制图像更新频率

---

## 依赖项

### Python 依赖
```bash
pip3 install matplotlib numpy
```

- **Python**: >= 3.7
- **matplotlib**: >= 3.0（用于可视化）
- **numpy**: >= 1.18（用于数值计算）
- **NodeFlow SDK**: 最新版本（InputPort, OutputPort, SharedBuffer）

### 系统依赖
- **字体**（可选）：中文字体支持需要安装对应字体包
  - macOS: 自带中文字体但 matplotlib 默认不启用
  - Linux: `apt install fonts-noto-cjk` 或 `yum install google-noto-cjk-fonts`

---

## 注意事项与最佳实践

### ⚠️ 重要注意事项

1. **坐标系统兼容性**
   - 假设输入数据为 WGS84 经纬度坐标
   - 内部自动转换为米制距离（Haversine 近似）
   - 适用于小范围农田（< 100 km²），大范围需使用 UTM 投影

2. **数据完整性要求**
   - 地块边界：至少 **3 个顶点**（形成闭合多边形）
   - 规划路径：至少 **2 个路径点**（形成线段）
   - 实际轨迹：至少 **2 个 GPS 点**（绘制轨迹线）
   - 不满足条件时仅输出统计信息，不生成图像

3. **性能考虑**
   - `update_interval` 不宜过小（建议 >= 5 秒）
   - 大量 GPS 点（> 10,000）可能导致图像生成变慢
   - JPG 格式比 PNG 小 50-70%，但质量略低

4. **超时设置**
   - `timeout` 应略长于预期作业时长（+20-30%）
   - 超时后会自动生成最终图像并退出
   - 手动中断（Ctrl+C）同样会触发最终图像生成

5. **字体显示问题**
   - 中文标签可能显示为方框（matplotlib 默认字体不支持 CJK）
   - 不影响可视化功能（线条、统计数据正常）
   - 可通过配置 `matplotlib.rcParams['font.sans-serif']` 解决

### ✅ 最佳实践

1. **推荐参数配置**
   ```yaml
   # 实时监控
   update_interval: 10.0
   timeout: 600.0
   dpi: 100

   # 作业验收
   update_interval: 0
   timeout: 1800.0
   dpi: 150

   # 高质量报告
   image_format: "png"
   dpi: 200
   figsize_width: 16.0
   figsize_height: 14.0
   ```

2. **输出目录管理**
   - 建议使用 `logs/jpg` 或 `logs/png` 便于归档
   - 定期清理旧图像避免磁盘占用

3. **数据验证**
   - 使用端到端测试验证完整数据流
   - 检查 GPS 定位质量（`fix_quality >= 4`）
   - 确认规划路径和地块边界坐标一致性

---

## 典型应用场景

### 1. 实时轨迹质量监控

**场景**: 作业过程中实时评估控制器性能

**配置**:
```yaml
params:
  update_interval: 5.0   # 每 5 秒更新图像
  timeout: 3600.0        # 1 小时超时
  dpi: 100               # 预览质量
```

**用途**:
- 发现控制算法问题（横向误差过大）
- 检测 GPS 定位异常
- 实时调整控制参数

### 2. 作业验收与质量评估

**场景**: 作业完成后生成验收报告

**配置**:
```yaml
params:
  update_interval: 0     # 仅生成最终图像
  timeout: 7200.0        # 2 小时超时
  dpi: 150               # 报告质量
  image_format: "jpg"
```

**用途**:
- 生成作业质量报告
- 计算覆盖率和误差指标
- 归档作业记录

### 3. 控制算法对比测试

**场景**: 对比不同控制器（PID vs MPC）的实际效果

**方法**:
- 相同规划路径，不同控制器运行
- 生成多组对比图
- 对比平均横向误差和覆盖率

### 4. 故障诊断与问题定位

**场景**: 发现轨迹跟踪异常

**分析思路**:
- **大幅偏离** → 检查 GPS 定位质量、传感器校准
- **周期性震荡** → 检查控制器参数（增益过大）
- **覆盖率低** → 检查路径规划算法、转弯逻辑
- **距离误差大** → 检查速度控制、路径插值

---

## 快速测试

### 生成演示可视化

运行以下脚本快速测试可视化功能（无需完整工作流）：

```python
#!/usr/bin/env python3
import sys
from pathlib import Path

sys.path.insert(0, str(Path.cwd()))
sys.path.insert(0, str(Path.cwd() / "node-hub" / "trajectory_viz"))

from run import TrajectoryCollector, TrajectoryVisualizer
import numpy as np

# 创建收集器
collector = TrajectoryCollector()

# 设置地块边界
collector.field_boundary = [
    (40.1200, -88.6540),
    (40.1400, -88.6540),
    (40.1400, -88.6640),
    (40.1200, -88.6640)
]
collector.field_name = "Test Field"

# 设置规划路径（往复式3趟）
collector.planned_path = [
    (40.1200, -88.6540), (40.1250, -88.6540), (40.1300, -88.6540),
    (40.1350, -88.6540), (40.1400, -88.6540),
    (40.1400, -88.6552),
    (40.1350, -88.6552), (40.1300, -88.6552), (40.1250, -88.6552),
    (40.1200, -88.6552),
    (40.1200, -88.6564), (40.1250, -88.6564), (40.1300, -88.6564),
    (40.1350, -88.6564), (40.1400, -88.6564),
]

# 模拟实际轨迹（带偏差）
for i in range(30):
    progress = i / 29
    if progress < 0.33:
        lat = 40.1200 + progress * 3 * 0.0200
        lon = -88.6540 + 0.001 * np.sin(i * 0.5)
    elif progress < 0.66:
        lat = 40.1400 - (progress - 0.33) * 3 * 0.0200
        lon = -88.6552 + 0.001 * np.sin(i * 0.5)
    else:
        lat = 40.1200 + (progress - 0.66) * 3 * 0.0200
        lon = -88.6564 + 0.001 * np.sin(i * 0.5)
    collector.actual_trajectory.append((lat, lon))

# 生成可视化
output_dir = Path.cwd() / "logs" / "jpg"
output_dir.mkdir(parents=True, exist_ok=True)
visualizer = TrajectoryVisualizer(collector, str(output_dir))
image_path = visualizer.generate_visualization(figsize=(14, 12), dpi=150)

print(f"✅ 图像已生成: {image_path}")
print(f"   大小: {Path(image_path).stat().st_size / 1024:.1f} KB")
```

保存为 `test_viz.py` 并运行：
```bash
python3 test_viz.py
```

---

## 常见问题（FAQ）

**Q: 为什么生成的图像中中文显示为方块？**

A: matplotlib 默认字体不支持中文。不影响可视化功能（线条和数据正常）。如需显示中文，需配置中文字体。

**Q: 图像生成很慢怎么办？**

A: 降低 DPI（80-100）或减小图像尺寸（10x8）可显著提速。大量 GPS 点（> 10,000）会影响性能。

**Q: 如何验证节点正常工作？**

A: 运行端到端测试：`python3 tests/integration/test_e2e_with_viz.py`

**Q: 横向误差很大是什么原因？**

A: 可能原因：
- GPS 定位精度低（检查 `fix_quality` 和 `hdop`）
- 控制器参数未调优
- 风力等外部干扰
- 规划路径与实际场地不匹配

**Q: 覆盖率低于预期怎么办？**

A: 检查：
- 路径规划是否完整
- 是否有漏行或跳行
- 速度控制是否稳定
- 转弯逻辑是否正确

---

## 更新日志

### v1.1.0 (2025-12-24)
- 🐛 **修复**: 地块边界坐标顺序错误（导致所有点挤在一起）
- ✨ **改进**: 更新文档，添加完整工作流说明
- ✨ **改进**: 添加详细的使用示例和快速测试脚本

### v1.0.0 (2025-12-24)
- 🎉 **初始版本**: 完整的轨迹对比可视化功能
- ✅ 7 个单元测试（100% 通过）
- ✅ 2 个端到端集成测试（100% 通过）
- 📊 支持距离误差、横向误差、覆盖率计算
- 🖼️ 支持 JPG/PNG 高分辨率图像输出

---

## 贡献与支持

如有问题或建议，请提交 Issue 或 Pull Request。

**文档版本**: v1.1.0
**最后更新**: 2025-12-24
