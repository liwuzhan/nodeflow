# 轨迹对比可视化节点

## 功能描述

该节点用于对比农田作业的规划轨迹和实际执行轨迹，生成可视化对比图像。

### 主要特性

1. **多源数据输入**：
   - 地块边界（来自规划任务）
   - 规划全局路径（来自路径规划器）
   - 实际GPS轨迹（来自RTK定位）

2. **可视化内容**：
   - 地块边界（绿色多边形）
   - 规划路径（蓝色线条）
   - 实际轨迹（红色线条）
   - 起点/终点标记
   - 统计信息面板

3. **误差分析**：
   - 规划距离 vs 实际距离
   - 平均横向误差
   - 最大横向误差
   - 覆盖率计算

4. **输出**：
   - 高分辨率JPG/PNG图像（保存到节点目录）
   - 统计信息JSON输出

## 使用方法

### 1. 图配置示例

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

### 2. 参数配置

```yaml
params:
  trajectory_viz:
    output_dir: "./trajectory_viz"    # 输出目录
    image_format: "jpg"                # 图像格式（jpg/png）
    timeout: 300.0                     # 超时时间（秒）
    update_interval: 5.0               # 更新间隔（秒）
    dpi: 150                           # 图像DPI
    figsize_width: 12.0                # 图像宽度（英寸）
    figsize_height: 10.0               # 图像高度（英寸）
```

### 3. 运行节点

节点会持续运行，定期生成可视化图像，直到：
- 达到超时时间
- 手动中断（Ctrl+C）

最终会在节点目录下生成：
- `trajectory_viz/trajectory_viz_YYYYMMDD_HHMMSS.jpg` - 可视化图像

## 输入数据格式

### task_request
```json
{
  "field_name": "田地A",
  "field_boundary": [
    {"lat": 40.1230, "lon": -88.6540},
    {"lat": 40.1240, "lon": -88.6540},
    {"lat": 40.1240, "lon": -88.6550},
    {"lat": 40.1230, "lon": -88.6550}
  ]
}
```

### global_path
```json
{
  "waypoints": [
    {"lat": 40.1230, "lon": -88.6540, "heading": 0},
    {"lat": 40.1235, "lon": -88.6540, "heading": 0},
    {"lat": 40.1240, "lon": -88.6540, "heading": 0}
  ],
  "total_distance": 250.0
}
```

### rtk_fix
```json
{
  "latitude": 40.1234,
  "longitude": -88.6543,
  "altitude": 250.0,
  "timestamp": 1734567890.123
}
```

## 输出数据格式

### trajectory_image
```json
{
  "image_path": "/path/to/trajectory_viz_20241224_143022.jpg",
  "timestamp": "2024-12-24T14:30:22",
  "status": "completed",
  "trajectory_points": 1234,
  "path_error": {
    "planned_distance": 500.5,
    "actual_distance": 502.3,
    "distance_error": 1.8,
    "distance_error_percent": 0.36,
    "average_lateral_error": 0.12,
    "max_lateral_error": 0.45,
    "num_points": 1234
  },
  "coverage_metrics": {
    "coverage_rate": 98.2,
    "task_duration": 125.7,
    "trajectory_points": 1234
  }
}
```

## 可视化示例

生成的图像包含：

```
┌─────────────────────────────────────────────┐
│  轨迹对比可视化 - 田地A (2024-12-24 14:30)  │
├─────────────────────────────────────────────┤
│                                              │
│    ┌────────── Field Boundary ───────┐      │
│    │  ········ 规划路径 (蓝色) ······│      │
│    │  ──────── 实际轨迹 (红色) ──────│      │
│    │                                  │      │
│    │  ○ 规划起点  ● 实际起点         │      │
│    │  □ 规划终点  ■ 实际终点         │      │
│    └─────────────────────────────────┘      │
│                                              │
│  ┌─ 轨迹统计 ──────────────┐                │
│  │ 规划距离: 500.5 m        │                │
│  │ 实际距离: 502.3 m        │                │
│  │ 距离误差: 1.8 m (0.36%)  │                │
│  │ 平均横向误差: 0.12 m     │                │
│  │ 最大横向误差: 0.45 m     │                │
│  │ 轨迹点数: 1234           │                │
│  │ 覆盖率: 98.2%            │                │
│  └──────────────────────────┘                │
└─────────────────────────────────────────────┘
```

## 依赖项

- Python 3.7+
- matplotlib
- numpy
- NodeFlow SDK

## 注意事项

1. **坐标系统**：假设输入数据为WGS84经纬度，内部自动转换为米制距离
2. **数据充分性**：需要至少3个边界点、2个规划点、2个实际轨迹点才能生成可视化
3. **更新频率**：`update_interval` 控制可视化更新频率，不宜过小以避免性能问题
4. **超时设置**：`timeout` 应根据作业预期时长设置，超时后自动生成最终图像

## 典型应用场景

1. **轨迹质量评估**：实时监控轨迹跟踪质量
2. **作业验收**：作业完成后的路径对比和验收
3. **算法调优**：对比不同控制算法的实际效果
4. **故障诊断**：发现路径跟踪异常时的问题定位
