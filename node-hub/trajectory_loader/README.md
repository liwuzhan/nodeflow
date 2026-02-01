# trajectory_loader - 轨迹加载器节点

## 功能概述

加载 `position_recorder` 节点录制的轨迹文件，转换为可执行的路径格式，用于自动导航车辆沿录制的轨迹行驶。

## 主要功能

1. **读取轨迹文件**：支持 CSV 和 JSON 格式
2. **坐标转换**：将 WGS84 坐标批量转换为 ENU 局部坐标
3. **路径输出**：输出与 `global_coverage` 兼容的 `global_path` 格式
4. **参考点传递**：输出 `task_enu` 消息，为 `coord_transform` 提供 GPS 参考点

## 输入端口

无

## 输出端口

| 端口名 | 类型 | 说明 |
|--------|------|------|
| `global_path` | planning.path | ENU坐标的路径点列表，供 waypoint_selector 使用 |
| `task_enu` | planning.task_enu | GPS参考点信息，供 coord_transform 使用 |

## 参数配置

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `trajectory_file` | string | "" | 轨迹文件完整路径（留空则自动选最新） |
| `records_dir` | string | `position_recorder/data/records` | 轨迹记录目录 |
| `ref_lon` | float | null | GPS参考点经度（留空则使用轨迹首点） |
| `ref_lat` | float | null | GPS参考点纬度（留空则使用轨迹首点） |
| `publish_interval` | float | 0.1 | 路径发布间隔（秒），建议10Hz |

## 使用场景

### 场景1：轨迹回放

录制一条轨迹后，让车辆自动沿轨迹行驶。

**数据流：**
```
[trajectory_loader] → global_path → [waypoint_selector] → [track_controller] → [pwm_driver]
       ↓
    task_enu → [coord_transform] → pose_enu
                      ↑
            [rtk_driver] → rtk_fix
```

**示例配置：** 见 `examples/trajectory_playback.yaml`

### 场景2：多条轨迹切换

录制多条不同路线，通过修改配置切换播放。

## 坐标系说明

### 输入（轨迹文件）
- **坐标系统**：WGS84（经纬度）
- **格式**：CSV 或 JSON
- **来源**：`position_recorder` 节点录制

### 输出（global_path）
- **坐标系统**：ENU 局部笛卡尔坐标
- **原点**：GPS 参考点（轨迹首点或手动指定）
- **单位**：米
- **格式**：`[(x, y), ...]` 路径点列表

## 轨迹文件格式

### CSV 格式（position_recorder 默认）

```csv
index,timestamp,datetime,lat,lon,alt,heading,rtk_status,rtk_quality,num_satellites,source
1,1234567890.123,2024-01-01T12:00:00,39.12345678,116.12345678,45.6,1.57,FIXED,4,15,manual
2,1234567891.123,2024-01-01T12:00:01,39.12345679,116.12345679,45.7,1.58,FIXED,4,15,auto
```

### JSON 格式

```json
{
  "metadata": {...},
  "summary": {...},
  "points": [
    {
      "index": 1,
      "timestamp": 1234567890.123,
      "lat": 39.12345678,
      "lon": 116.12345678,
      "alt": 45.6,
      "heading": 1.57,
      "rtk_status": "FIXED",
      ...
    }
  ]
}
```

## 典型工作流

### 步骤1：录制轨迹
```bash
# 使用 manual_trajectory_recording.yaml
python3 -m runtime.main examples/manual_trajectory_recording.yaml

# 在 Web 界面（http://localhost:8082）录制轨迹
# 轨迹保存在: node-hub/position_recorder/data/records/
```

### 步骤2：回放轨迹
```bash
# 使用 trajectory_playback.yaml
python3 -m runtime.main examples/trajectory_playback.yaml

# trajectory_loader 自动加载最新轨迹
# 车辆沿轨迹自动行驶
```

## 日志输出示例

```
============================================================
轨迹加载器节点启动
  轨迹文件: (自动选择最新)
  记录目录: /path/to/records
  参考点: (自动从轨迹首点获取)
  发布间隔: 0.1s
============================================================
加载轨迹文件: /path/to/records/record_20240101_120000.csv
读取到 150 个轨迹点
自动参考点（轨迹首点）: lon=116.12345678, lat=39.12345678
坐标转换完成: 150 个ENU路径点
  起点 ENU: (0.00, 0.00)
  终点 ENU: (52.34, 128.56)
  路径总长: 145.23 米
开始发布路径（间隔 0.1s）...
```

## 故障排查

### 问题1：找不到轨迹文件
**解决：**
- 检查 `records_dir` 是否正确
- 确认已用 `position_recorder` 录制了轨迹
- 手动指定 `trajectory_file` 绝对路径

### 问题2：坐标转换异常
**解决：**
- 检查轨迹文件中 lat, lon 字段是否有效
- 确保轨迹点在合理的经纬度范围内（-90~90, -180~180）
- 检查是否有空轨迹文件

### 问题3：车辆不按轨迹行驶
**解决：**
- 确认 GPS 参考点与录制时一致
- 检查 `waypoint_selector` 和 `track_controller` 参数配置
- 确认 RTK 定位质量为 FIXED

## 技术细节

### 坐标转换精度
- 使用球面投影近似（适用于小范围导航，< 10km）
- 纬度转换：111320 米/度
- 经度转换：111320 * cos(lat) 米/度

### 性能指标
- 轨迹加载：< 1秒（1000个点）
- 内存占用：< 10MB（1000个点）
- 发布频率：10Hz（可配置）

## 依赖关系

### 上游节点（可选）
- 无（独立数据源）

### 下游节点（典型）
- `waypoint_selector`：接收 global_path
- `coord_transform`：接收 task_enu

### 配合节点
- `rtk_driver`：提供实时定位
- `track_controller`：执行路径跟踪
- `pwm_driver`：控制电机

## 开发说明

### 文件结构
```
trajectory_loader/
├── atom.py           # L4 原子层：纯函数实现
├── run.py            # L3 主程序：NodeFlow SDK集成
├── node.yaml         # 节点配置文件
├── test/
│   └── test_atom.py  # 单元测试
└── README.md         # 本文档
```

### 单元测试
```bash
cd node-hub/trajectory_loader
python3 test/test_atom.py
```

### 扩展建议
- [ ] 添加 Web 界面选择轨迹
- [ ] 支持轨迹裁剪（起点/终点选择）
- [ ] 支持轨迹反向播放
- [ ] 支持轨迹循环播放
- [ ] 添加路径平滑算法
- [ ] 支持轨迹可视化预览
