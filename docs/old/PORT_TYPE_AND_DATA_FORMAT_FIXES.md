# 端口类型和数据格式对齐修复报告

**日期**: 2025-12-25
**目标**: 确保所有节点的端口类型定义和数据处理逻辑正确对齐

## 问题概述

在运行完整工作流时，系统出现3个关键的端口类型不匹配警告和多个数据格式不一致的问题。

## 发现的问题

### 1. 端口类型定义不匹配

#### 问题 1.1: velocity_controller.global_path 端口类型错误
- **位置**: `node-hub/velocity_controller/node.yaml:19`
- **问题**: 定义为 `json`，但接收 `planning.path` 类型数据
- **影响**: 产生运行时警告
- **修复**: 改为 `planning.path` ✅

#### 问题 1.2: trajectory_viz.task_request 端口类型错误
- **位置**: `node-hub/trajectory_viz/node.yaml:16`
- **问题**: 定义为 `json`，但接收 `planning.task` 类型数据
- **影响**: 产生运行时警告
- **修复**: 改为 `planning.task` ✅

#### 问题 1.3: trajectory_viz.global_path 端口类型错误
- **位置**: `node-hub/trajectory_viz/node.yaml:19`
- **问题**: 定义为 `json`，但接收 `planning.path` 类型数据
- **影响**: 产生运行时警告
- **修复**: 改为 `planning.path` ✅

### 2. 数据处理逻辑不匹配

#### 问题 2.1: trajectory_viz 获取地块边界格式错误
- **位置**: `node-hub/trajectory_viz/run.py:60-74`
- **问题**:
  - 代码期望: `task_data["field_boundary"]` (数组)
  - 实际收到: `task_data["parcel"]["outer"]` (元组数组)
- **数据格式对比**:
  ```
  代码期望:     {field_boundary: [{lat,lon}, ...]}
  实际输出:     {parcel: {outer: [(lon,lat), ...], holes: [...]}}
  ```
- **修复**: 更新逻辑以处理新的 parcel 结构
  ```python
  parcel = task_data.get("parcel")
  outer = parcel.get("outer")  # [(lon, lat), ...]
  field_boundary = [(lat, lon) for lon, lat in outer]
  ```
  ✅

#### 问题 2.2: trajectory_viz 获取规划路径格式错误
- **位置**: `node-hub/trajectory_viz/run.py:73-84`
- **问题**:
  - 代码期望: `path_data["waypoints"]` (字典数组，每个有 lat/lon)
  - 实际收到: `path_data["path"]` (元组数组)
- **数据格式对比**:
  ```
  代码期望:     {waypoints: [{lat,lon}, ...]}
  实际输出:     {path: [(lon,lat), ...], task_id, timestamp, status, ...}
  ```
- **修复**: 更新逻辑以处理 path 元组格式
  ```python
  path = path_data.get("path")  # [(lon, lat), ...]
  planned_path = [(lat, lon) for lon, lat in path]
  ```
  ✅

### 3. SDK API 调用错误

#### 问题 3.1: velocity_controller 使用过期的 SDK API
- **位置**: `node-hub/velocity_controller/run.py:303-310`
- **问题**: 使用 `sdk.get_param()` (已过期)
- **修复**: 改为 `sdk.params.get()` ✅

#### 问题 3.2: velocity_controller 使用过期的 send API
- **位置**: `node-hub/velocity_controller/run.py:413`
- **问题**: 使用 `sdk.send("velocity_cmd", ...)` (已过期)
- **修复**: 改为 `velocity_cmd_port.send(...)` ✅

## 数据流图（修复后）

```
sim_output (planning.task)
    ↓
    task_request: {id, parcel: {outer: [(lon,lat),...], ...}, vehicle: {...}}
    ↓
global_coverage (planning.task) → (planning.path)
    ↓
    global_path: {task_id, path: [(lon,lat),...], ...}
    ↓
    ├─→ velocity_controller (planning.path)
    │   └─→ controller.set_path([(lon,lat),...])
    │
    └─→ trajectory_viz (planning.path)
        └─→ planned_path = [(lat,lon),...] (转换后)

sim_output (planning.task) → trajectory_viz
    └─→ field_boundary = [(lat,lon),...] (转换后)

sim_output (json) → trajectory_viz (json)
    └─→ rtk_fix (直接使用)
```

## 修复清单

| 文件 | 行号 | 问题 | 修复 | 状态 |
|------|------|------|------|------|
| velocity_controller/node.yaml | 19 | 端口类型 | json → planning.path | ✅ |
| trajectory_viz/node.yaml | 16 | 端口类型 | json → planning.task | ✅ |
| trajectory_viz/node.yaml | 19 | 端口类型 | json → planning.path | ✅ |
| trajectory_viz/run.py | 60-74 | 地块数据处理 | 改为提取 parcel.outer | ✅ |
| trajectory_viz/run.py | 76-87 | 路径数据处理 | 改为提取 path 数组 | ✅ |
| velocity_controller/run.py | 303-310 | SDK API | sdk.get_param → sdk.params.get | ✅ |
| velocity_controller/run.py | 413 | SDK API | sdk.send → port.send | ✅ |

## 测试建议

1. **单元测试**: 验证每个节点的数据处理逻辑
   - trajectory_viz: 验证地块和路径数据解析
   - velocity_controller: 验证路径点的正确读取

2. **集成测试**: 运行完整工作流
   ```bash
   python3 simulator/server.py &
   sleep 3
   python3 -m runtime.main examples/planning_simulation.yaml
   ```

3. **验证输出**:
   - ✅ 无端口类型警告
   - ✅ trajectory_viz 生成 JPG 图像
   - ✅ 日志中显示正确的数据量

## 核心概念

### 坐标系统
- **WGS84 (GPS)**: longitude (经) 在前，latitude (纬) 在后 → `(lon, lat)`
- **数学/绘图**: latitude (纬) 在前，longitude (经) 在后 → `(lat, lon)`

### 数据格式转换
```python
# 从 global_coverage 接收的格式 (WGS84)
path = [(121.5, 31.2), ...]  # [(lon, lat), ...]

# 绘图时需要的格式
plot_data = [(31.2, 121.5), ...]  # [(lat, lon), ...]

# 转换方法
plot_data = [(lat, lon) for lon, lat in path]
```

## 后续优化建议

1. **统一数据格式定义**: 在项目范围内明确定义各数据类型的格式
2. **类型系统**: 考虑使用 TypedDict 或 Pydantic 定义数据结构，增强类型安全
3. **自动化验证**: 在运行时添加数据格式检查和日志记录
4. **文档**: 为每个节点的端口定义详细的数据格式示例

## 修改时间轴

- **2025-12-25 01:30**: 发现端口类型不匹配
- **2025-12-25 01:35**: 修复数据处理逻辑
- **2025-12-25 01:40**: 修复 SDK API 调用
- **2025-12-25 01:45**: 验证修复完成
