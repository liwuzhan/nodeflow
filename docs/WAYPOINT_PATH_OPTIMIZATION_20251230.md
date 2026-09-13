# 前瞻点与路径密度优化报告

**日期**: 2025-12-30
**版本**: v1.0
**状态**: ✅ 已完成

---

## 一、问题背景

### 1.1 原始问题
在 planning_simulation 测试中发现车辆在接近/到达轨迹起点时出现原地打转现象，完成度达到 76-99% 时车辆停止前进。

### 1.2 问题分析
通过可视化图片和日志分析，定位到两个核心问题：

1. **前瞻点初始消费逻辑不合理**
   - 旧逻辑：持续检测 `local_x < -0.5`（车辆后方）自动消费
   - 问题：当路径点间距大（5m）、视野深度小（1.5m）时，起点可能永远无法进入视野
   - 场景：车辆初始位置往往不在轨迹起点正上方

2. **规划路径点密度过低**
   - 问题：全覆盖规划算法直接输出几何库坐标，直线段点间距可能很大（5m+）
   - 影响：前瞻点选择器无法连续捕获视野内的点，导致跟踪失败
   - 视野参数：view_distance=3.0m, view_depth=1.5m

---

## 二、解决方案

### 2.1 前瞻点初始消费优化

#### 修改内容

**文件**: `node-hub/waypoint_selector/atom.py`

**核心改动**:
```python
# 旧逻辑（持续检测）
if local_x < -0.5:  # 在车辆后方 0.5m 以上
    passed_count += 1

# 新逻辑（初始化时一次性判定）
def _initial_consume(self, vx: float, vy: float) -> int:
    """找到前N个点中距离车辆最近的点，如果距离 < 阈值，则消费它及之前的所有点"""
    check_count = min(cfg.initial_check_points, len(path))
    # 找到最近点
    for i in range(check_count):
        dist = euclidean_distance(vx, vy, path[i][0], path[i][1])
        if dist < min_dist:
            min_dist = dist
            closest_idx = i
    # 如果最近点距离 < 阈值，消费
    if closest_idx >= 0 and min_dist < cfg.initial_consume_distance:
        return closest_idx + 1
    return 0
```

**新增配置参数**:
- `initial_check_points`: 初始化时检查的前N个点（默认10）
- `initial_consume_distance`: 距离小于此值的点视为已消费（默认2.0m）

**配置示例** (`planning_simulation.yaml`):
```yaml
- id: waypoint_selector
  params:
    initial_check_points: 50       # 覆盖更多路径点
    initial_consume_distance: 2.0  # 2米容差
```

#### 设计优势
1. **更符合实际场景**：车辆启动位置通常在轨迹附近，而非精确起点
2. **仅一次判定**：避免持续计算，性能更优
3. **可配置化**：根据实际路径间距调整参数

---

### 2.2 路径点密度配置化

#### 修改内容

**文件**: `node-hub/global_coverage/utils/planner.py`

**新增密化函数**:
```python
def densify_path(coords: List[Tuple[float, float]], spacing: float) -> List[Tuple[float, float]]:
    """
    密化路径点，确保相邻点间距不超过指定值

    算法：
    - 遍历每段路径
    - 如果段长度 > spacing，插入中间点
    - 使用线性插值保证均匀分布
    """
    for i in range(len(coords) - 1):
        seg_len = sqrt((x1-x0)^2 + (y1-y0)^2)
        if seg_len > spacing:
            num_points = ceil(seg_len / spacing) - 1
            # 线性插值
            for j in range(1, num_points + 1):
                t = j / (num_points + 1)
                result.append((x0 + t*dx, y0 + t*dy))
```

**新增配置参数** (`node.yaml`):
```yaml
params:
  path_point_spacing:
    type: number
    default: 0.5
    description: "路径点间距 (米)，用于密化路径以便控制器跟踪"
```

**配置示例** (`planning_simulation.yaml`):
```yaml
- id: global_coverage
  params:
    path_point_spacing: 0.5  # 每0.5米一个点
```

#### 效果预期
- **原始路径**: 85个点，平均间距可能 5-10m
- **密化后**: 根据总长度，预计 500-1000 个点
- **跟踪效果**: 视野深度1.5m内始终能捕获到点

---

## 三、测试验证

### 3.1 单元测试

**文件**: `node-hub/waypoint_selector/test/test_atom.py`

新增测试用例 `test_initial_consume()`:
```python
# 情况1: 初始位置在起点 (最近点距离=0 < 2m，消费1点)
assert info["initial_consumed"] == 1

# 情况2: 初始位置在路径中间 (最近点是第4个，消费4点)
assert info2["initial_consumed"] == 4

# 情况3: 初始位置远离起点 (最近点距离 > 2m，不消费)
assert info3["initial_consumed"] == 0

# 情况4: 不传初始位置 (不消费)
assert info4["initial_consumed"] == 0
```

**测试结果**: ✅ 所有6个测试用例通过

---

## 四、配置文件更新

### 4.1 waypoint_selector 配置

**文件**: `node-hub/waypoint_selector/node.yaml`

```yaml
params:
  # 视野参数
  view_distance: 3.0
  view_width: 4.0
  view_depth: 1.5
  goal_tolerance: 1.5
  max_search_points: 100

  # 初始消费参数（新增）
  initial_check_points: 10
  initial_consume_distance: 2.0
```

### 4.2 global_coverage 配置

**文件**: `node-hub/global_coverage/node.yaml`

```yaml
params:
  path_point_spacing:
    type: number
    default: 0.5
    description: "路径点间距 (米)，用于密化路径以便控制器跟踪"
```

### 4.3 planning_simulation 配置

**文件**: `examples/planning_simulation.yaml`

```yaml
nodes:
  - id: global_coverage
    params:
      path_point_spacing: 0.5  # 路径点间距

  - id: waypoint_selector
    params:
      view_distance: 3.0
      view_width: 4.0
      view_depth: 1.5
      goal_tolerance: 1.5
      max_search_points: 100
      initial_check_points: 50       # 增大以覆盖更多点
      initial_consume_distance: 2.0
```

---

## 五、修改文件清单

### 5.1 核心代码
- `node-hub/waypoint_selector/atom.py` - 初始消费逻辑
- `node-hub/waypoint_selector/run.py` - 传递初始位置参数
- `node-hub/global_coverage/utils/planner.py` - 路径密化函数
- `node-hub/global_coverage/run.py` - 读取并使用密度参数

### 5.2 配置文件
- `node-hub/waypoint_selector/node.yaml` - 新增初始消费参数
- `node-hub/global_coverage/node.yaml` - 新增路径密度参数
- `examples/planning_simulation.yaml` - 更新两个节点配置

### 5.3 测试文件
- `node-hub/waypoint_selector/test/test_atom.py` - 新增初始消费测试

---

## 六、使用建议

### 6.1 参数调优指南

**路径点间距** (`path_point_spacing`):
- **低速场景** (0.5-1.0 m/s): 建议 0.3-0.5m
- **中速场景** (1.0-2.0 m/s): 建议 0.5-1.0m
- **高速场景** (>2.0 m/s): 建议 1.0-2.0m

**初始消费参数**:
- `initial_check_points`: 至少覆盖 initial_consume_distance * 5 的路径长度
- `initial_consume_distance`: 根据定位精度设置，建议 GPS精度 * 2

**视野参数关系**:
```
path_point_spacing < view_depth
```
确保视野内至少有2-3个点可选

### 6.2 性能影响

**路径点数量**:
- 原始: ~85点
- 密化后 (0.5m): ~5000点（假设总长2500m）

**内存占用**:
- 每个点 16字节（x, y 各8字节）
- 5000点 ≈ 80KB（仍在 3MB buffer 范围内）

**计算开销**:
- 密化算法: O(n), 一次性计算
- 前瞻点选择: 无额外开销（仍按 max_search_points 限制）

---

## 七、后续优化建议

1. **自适应密化**: 直线段稀疏，转弯处密集
2. **曲率感知**: 根据路径曲率动态调整点间距
3. **性能监控**: 记录实际点间距统计，用于参数调优
4. **可视化工具**: 在 trajectory_viz 中显示消费点状态

---

## 八、总结

本次优化解决了前瞻点选择器在路径起点/终点的跟踪失败问题，通过以下两方面改进：

1. ✅ **初始消费逻辑**: 从持续检测改为初始化时一次性距离判定
2. ✅ **路径点密度**: 新增可配置的密化功能，默认0.5m间距

**预期效果**:
- 车辆在任意起始位置都能正确找到前瞻点
- 轨迹跟踪更平滑，无"断点"现象
- 配置灵活，适应不同场景需求

**测试状态**: ✅ 单元测试全部通过，待集成测试验证
