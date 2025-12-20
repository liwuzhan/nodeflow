# Mock Path Planner Node

## 概述

模拟路径规划算法，根据目标点请求生成导航路径，用于测试路径跟踪和导航功能。

## 功能

- 接收目标点请求
- 生成一系列航点组成的路径
- 支持多种规划算法模式
- 模拟计算延迟
- 计算路径统计信息

## 端口定义

### 输入端口

- **target** (JSON): 目标点请求
  ```json
  {
    "task_id": "task_001",
    "target_latitude": 39.9050,
    "target_longitude": 116.4080
  }
  ```

### 输出端口

- **path** (JSON): 规划路径
  ```json
  {
    "task_id": "task_001",
    "timestamp": 1703024780.5,
    "path": [[116.4074, 39.9042], [116.4076, 39.9044], ...],
    "num_waypoints": 10,
    "total_distance_meters": 150.5,
    "status": "success",
    "computation_time_ms": 25.5,
    "algorithm": "direct_line"
  }
  ```

## 参数配置

| 参数名 | 类型 | 默认值 | 说明 |
|--------|------|--------|------|
| `plan_mode` | string | `"direct_line"` | 规划算法：`direct_line`、`grid_search`、`astar` |
| `path_length` | number | `10` | 航点数量 |
| `spacing_meters` | number | `5.0` | 航点间距（米） |
| `computation_delay_ms` | number | `50` | 模拟计算延迟（毫秒） |

## 使用示例

### 示例1：直线路径规划

```yaml
nodes:
  - id: gps_0
    package: mock_gps
    params:
      mode: stationary

  - id: planner_0
    package: mock_path_planner
    params:
      plan_mode: direct_line
      path_length: 10

edges:
  - from: gps_0.gps_fix
    to: planner_0.target
  - from: planner_0.path
    to: logger_0.input1
```

### 示例2：网格搜索（绕行）

```yaml
nodes:
  - id: planner_0
    package: mock_path_planner
    params:
      plan_mode: grid_search
      path_length: 20
      computation_delay_ms: 100
```

模拟更复杂的路径规划，包含绕行逻辑。

## 规划算法

### Direct Line 模式
- 在起点和终点之间生成等间距航点
- 最简单、最快的算法
- 不考虑障碍物

### Grid Search 模式
- 模拟网格搜索，添加中间偏移点
- 模拟绕过障碍物的路径
- 路径长度略长

### A* 模式（预留）
- 未来可实现真实的A*算法
- 需要地图和障碍物信息

## 路径数据格式

航点格式：`[longitude, latitude]`（经度在前，纬度在后）

遵循GeoJSON标准格式。

### 坐标顺序说明
- **GeoJSON**: `[lon, lat]`
- **常规**: `(lat, lon)`

本节点输出采用GeoJSON格式。

## 距离计算

使用 **Haversine公式** 计算大圆距离（考虑地球曲率）：

```
d = 2R * arcsin(√[sin²(Δφ/2) + cos(φ1) * cos(φ2) * sin²(Δλ/2)])
```

其中：
- R = 6371000 m（地球半径）
- φ = 纬度（弧度）
- λ = 经度（弧度）

## 测试用途

1. **请求-响应模式**: 测试异步消息处理
2. **路径数据传输**: 验证复杂数据结构的传输
3. **计算延迟模拟**: 测试超时和性能监控
4. **路径跟踪算法**: 为控制器节点提供参考路径

## 替换为真实路径规划

要替换为真实路径规划算法：

1. 集成真实地图数据（OpenStreetMap, 栅格地图）
2. 实现障碍物检测和避让
3. 使用成熟的规划库（如ROS Navigation, OMPL）
4. 保持相同的输入输出格式

```python
# 真实路径规划集成示例
from pyastar import astar_path
import numpy as np

# 加载地图
map_data = load_map_from_file('map.png')

# A*规划
start_grid = lat_lon_to_grid(start_lat, start_lon)
goal_grid = lat_lon_to_grid(target_lat, target_lon)

path_grid = astar_path(map_data, start_grid, goal_grid)

# 转换为地理坐标
path = [grid_to_lat_lon(x, y) for x, y in path_grid]

path_data = {
    'path': [[lon, lat] for lat, lon in path],
    # ... 其他字段 ...
}
```

## 性能指标

- CPU占用：< 2%
- 内存占用：< 15 MB
- 响应延迟：50-100 ms（可配置）
- 路径质量：直线路径最优，网格搜索次优

## 依赖

- Python 3.9+
- NodeFlow SDK

## 日志输出

- **INFO**: 目标请求、路径生成完成
- **DEBUG**: 目标坐标、路径统计
- **ERROR**: 规划失败、异常
