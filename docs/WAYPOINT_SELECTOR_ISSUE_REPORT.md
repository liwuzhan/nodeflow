# Waypoint Selector 路径跟踪问题报告

**报告日期**: 2025-12-30
**问题严重性**: 高
**影响范围**: Planning Simulation 闭环测试，车辆路径跟踪

---

## 1. 问题现象

### 1.1 问题描述

在 planning_simulation 闭环测试中，车辆在完成第一段约 99% 的路径后，当**接近或到达路径起点**时，出现**持续原地打转**的异常行为，无法正常完成任务。

### 1.2 复现条件

- **配置文件**: `examples/planning_simulation.yaml`
- **路径类型**: 封闭式覆盖路径（起点 ≈ 终点）
- **触发时机**: 完成率 > 98%，距起点 < 2m
- **复现概率**: 100%（每次测试必现）

### 1.3 可视化证据

根据轨迹可视化图像序列（`trajectory_viz_20251230_021501.jpg` ~ `021551.jpg`），问题演变过程如下：

| 时间 | 完成率 | 剩余距离 | 距起点 | 路径点索引 | 车辆状态 |
|------|--------|----------|--------|------------|----------|
| 02:15:01 | 99.1% | 21.93 m | 41.53 m | 291 / 291 | 正常跟踪 |
| 02:15:11 | 98.7% | 30.61 m | 37.33 m | 387 / 387 | 正常跟踪 |
| 02:15:21 | 98.4% | 39.3 m | 33.05 m | 484 / 484 | 正常跟踪 |
| 02:15:31 | 98.0% | 48.27 m | 28.81 m | 580 / 580 | 正常跟踪 |
| **02:15:41** | **99.7%** | **7.49 m** | **1.13 m** | **85 / 677** | **到达起点** |
| **02:15:51** | **99.5%** | **11.22 m** | **1.12 m** | **181 / 773** | **开始打转** |

**关键观察**:
- 02:15:41 时，车辆已到达起点附近（距离 1.13m），完成率 99.7%
- 10秒后（02:15:51），完成率**下降**至 99.5%，剩余距离**增加**至 11.22m
- **路径点总数发生变化**（291→387→484→580→677→773），说明路径在动态更新
- 车辆轨迹显示在起点附近**原地打转**，横向偏差达到 2.5m

---

## 2. 根本原因分析

### 2.1 代码审查发现

问题定位于 `node-hub/waypoint_selector/atom.py` 的路径跟踪逻辑：

#### **缺陷 1: 路径点推进条件过于严格**

```python
# 当前实现 (atom.py:52-57)
if self.index < len(self.path):
    x, y = self.path[self.index]
    d = self.euclidean_distance(cx, cy, x, y)
    if d < self.tol_m:  # tol_m = 0.3m
        self.index += 1
```

**问题**:
- 只有车辆到达路径点 **0.3m 容差内**，才推进 index
- Coverage 路径有 **600+ 个点**，点间距约 3-5m
- 车辆实际轨迹受控制误差影响，**无法精确到达每个点**
- 如果车辆距离某个路径点 0.4m（略超容差），index 将**永久停滞**

**数据验证**:
- 02:15:41 时，index = 85，总路径点 677
- 车辆已完成 99.7% 的路径，但 index 仅推进到 12.5% (85/677)
- **index 停滞导致前瞻点计算错误**

#### **缺陷 2: 缺少封闭路径的完成判定**

```python
# 当前实现 (atom.py:59-62)
if self.index >= len(self.path):
    final_x, final_y = self.path[-1]
    return {"x": final_x, "y": final_y, "final": True}
```

**问题**:
- 完成判定**仅依赖** `self.index >= len(self.path)`
- 对于**封闭路径**（起点 = 终点），这个条件**永远无法满足**
- 即使车辆已回到起点（距离 1.13m），系统仍认为任务未完成

**理论分析**:
- Coverage 路径是封闭的（最后一个点回到起点）
- 如果 index 停滞在中间（如 85/677），车辆到达起点后：
  - 系统计算前瞻点：从 index=85 开始，向前查找 lookahead=2m 的点
  - **前瞻点可能在车辆后方或侧方**（因为路径是弯曲的）
  - Track controller 收到错误的目标点，产生错误的速度/角速度指令
  - 车辆开始打转

#### **缺陷 3: 前瞻点计算未考虑车辆航向**

```python
# 当前实现 (atom.py:81-92)
# 从 self.index 开始，累计 lookahead_m 距离
acc = 0.0
i = self.index
while i + 1 < len(self.path) and acc < self.lookahead_m:
    ax, ay = self.path[i]
    bx, by = self.path[i + 1]
    seg = self.euclidean_distance(ax, ay, bx, by)
    acc += seg
    target_x, target_y = bx, by
    i += 1
```

**问题**:
- 前瞻点**纯粹基于路径距离**，未考虑：
  - 车辆当前航向
  - 路径点方向
  - 车辆与路径点的相对位置关系
- 当 index 停滞时，前瞻点可能指向：
  - 车辆已经驶过的点
  - 与车辆航向相反的点
  - 路径另一侧的点（对于弯曲路径）

---

## 3. 问题影响

### 3.1 功能影响

- **无法完成封闭路径任务**: 车辆在 99% 完成度时陷入死循环
- **控制指令混乱**: Track controller 收到错误的目标点，产生振荡控制
- **能耗浪费**: 车辆原地打转，消耗能量但无实际进展

### 3.2 测试影响

- Planning simulation 闭环测试**无法通过**
- 无法验证完整的路径跟踪性能
- 影响后续集成测试和现场试验

---

## 4. 当前实现的设计缺陷总结

| 缺陷类别 | 具体问题 | 后果 |
|---------|---------|------|
| **索引推进机制** | 仅依赖 0.3m 容差判定 | Index 停滞，前瞻点错误 |
| **完成判定** | 仅检查 `index >= len(path)` | 封闭路径永不完成 |
| **前瞻点选择** | 未考虑车辆航向 | 可能选择后方/侧方点 |
| **鲁棒性** | 对控制误差敏感 | 小偏差导致系统失效 |

---

## 5. 可能的解决方案

### 方案 1: 基于最近点的索引更新（简单修复）

**思路**: 动态更新 index 到车辆最近的路径点

**实现**:
```python
# 查找最近的路径点
min_dist = float('inf')
closest_idx = self.index
for i in range(self.index, len(self.path)):
    dist = self.euclidean_distance(cx, cy, self.path[i][0], self.path[i][1])
    if dist < min_dist:
        min_dist = dist
        closest_idx = i
    if dist > min_dist + 10:  # 提前退出优化
        break
self.index = closest_idx
```

**优点**: 实现简单，兼容现有架构
**缺点**: 未解决航向问题，可能在 U 型弯处失效

### 方案 2: 添加封闭路径完成检测（补丁方案）

**思路**: 检测车辆是否回到起点

**实现**:
```python
# 对于封闭路径，检测回到起点
if self.index > len(self.path) * 0.9:  # 完成 90% 以上
    start_x, start_y = self.path[0]
    dist_to_start = self.euclidean_distance(cx, cy, start_x, start_y)
    if dist_to_start < self.tol_m * 3:  # 距起点 1m 内
        return {"x": start_x, "y": start_y, "final": True}
```

**优点**: 快速修复当前问题
**缺点**: 治标不治本，不够通用

### **方案 3: 基于向量的前瞻点选择（推荐方案）** ⭐

**核心思想**: 结合车辆航向、路径方向、相对位置，选择**最优前瞻点**

**关键要素**:

1. **车辆航向向量**: `v_vehicle = (cos(θ), sin(θ))`
2. **路径方向向量**: `v_path[i] = (path[i+1] - path[i]) / |path[i+1] - path[i]|`
3. **相对位置向量**: `v_rel = (path[i] - vehicle_pos) / |path[i] - vehicle_pos|`

**选择策略**:
```python
def select_lookahead_point(vehicle_pos, vehicle_heading, path, current_index):
    """
    基于向量的前瞻点选择

    评分因子:
    1. 航向一致性: dot(v_vehicle, v_rel) -> 优先选择车辆前方的点
    2. 路径连续性: dot(v_vehicle, v_path) -> 优先选择与航向一致的路径段
    3. 距离适宜性: |lookahead - preferred_distance| -> 前瞻距离在合理范围
    """
    best_score = -inf
    best_idx = current_index

    for i in range(current_index, min(current_index + 50, len(path))):
        # 计算三个向量
        v_rel = normalize(path[i] - vehicle_pos)
        v_path = normalize(path[i+1] - path[i]) if i+1 < len(path) else v_rel
        v_vehicle = (cos(heading), sin(heading))

        # 计算评分
        forward_score = dot(v_vehicle, v_rel)  # 是否在前方
        alignment_score = dot(v_vehicle, v_path)  # 路径方向是否一致
        distance = distance(vehicle_pos, path[i])
        distance_score = -abs(distance - lookahead) / lookahead

        total_score = (
            0.5 * forward_score +      # 50% 权重：前方优先
            0.3 * alignment_score +    # 30% 权重：方向一致
            0.2 * distance_score       # 20% 权重：距离适宜
        )

        if total_score > best_score:
            best_score = total_score
            best_idx = i

    return path[best_idx]
```

**优点**:
- ✅ 考虑车辆航向，避免选择后方点
- ✅ 考虑路径方向，适应弯道场景
- ✅ 自适应索引更新，无需严格容差判定
- ✅ 通用性强，适用于各种路径形状

**缺点**:
- 需要修改 Schema（添加 `theta` 字段到 `PoseENU`）
- 计算量略增（但可优化搜索范围）

### 方案 4: Pure Pursuit 算法（业界标准）

**思路**: 采用经典的 Pure Pursuit 路径跟踪算法

**核心逻辑**:
- 在路径上寻找与车辆距离为 lookahead 的点
- 使用几何关系计算曲率半径
- 直接输出角速度（bypass track_controller）

**优点**: 理论成熟，性能可靠
**缺点**: 需要重构整个跟踪节点，工作量大

---

## 6. 推荐方案与实施计划

### 6.1 短期方案（1-2 天）

**组合使用方案 1 + 方案 2**:
1. 实现基于最近点的索引更新（解决 index 停滞）
2. 添加封闭路径完成检测（解决任务无法结束）
3. 快速验证 planning_simulation 闭环测试

**预期效果**: 车辆能完成封闭路径，但可能在复杂弯道仍有振荡

### 6.2 中期方案（3-5 天）⭐ **推荐**

**实施方案 3（向量方案）**:

**实施步骤**:
1. **修改 Schema**:
   - 确保 `PoseENU` 包含 `theta` 字段
   - 验证 `coord_transform` 正确输出航向

2. **重构 waypoint_selector**:
   - 实现向量评分函数
   - 集成航向信息
   - 优化搜索范围（仅搜索前方 20-50 个点）

3. **参数调优**:
   - 前瞻距离: 2-5m（根据速度动态调整）
   - 评分权重: forward=0.5, alignment=0.3, distance=0.2
   - 完成容差: 1.5m（放宽终点判定）

4. **测试验证**:
   - Planning simulation 闭环测试
   - 不同路径类型（直线、弯道、U型弯、封闭路径）
   - 边界条件（起点附近、急转弯、路径交叉）

**预期效果**:
- ✅ 解决所有当前问题
- ✅ 提升弯道跟踪性能
- ✅ 增强系统鲁棒性

### 6.3 长期方案（1-2 周）

**考虑引入 Pure Pursuit 或 MPC**:
- 作为 waypoint_selector + track_controller 的替代方案
- 性能对比测试
- 根据实际场景选择最优方案

---

## 7. 需要讨论的问题

1. **当前 `PoseENU` Schema 是否包含 `theta` 字段？**
   - 如果没有，需要修改 `coord_transform` 节点输出
   - 影响方案 3 的实施

2. **完成任务后的期望行为？**
   - 停车？继续循环？
   - 是否需要发送任务完成信号给上游节点？

3. **前瞻距离是否需要动态调整？**
   - 根据速度调整（低速短前瞻，高速长前瞻）
   - 根据曲率调整（直道长前瞻，弯道短前瞻）

4. **是否考虑重构为 Pure Pursuit？**
   - waypoint_selector + track_controller 是否保留？
   - 或者合并为单一 path_tracker 节点？

5. **测试覆盖范围？**
   - 除了 planning_simulation，是否测试其他场景？
   - 是否需要回归测试框架？

---

## 8. 附录

### 8.1 相关文件

- 问题节点: `node-hub/waypoint_selector/atom.py`
- 依赖节点: `node-hub/track_controller/run.py`
- 测试配置: `examples/planning_simulation.yaml`
- 可视化证据: `logs/jpg/trajectory_viz_20251230_0215*.jpg`

### 8.2 日志摘要

```
# waypoint_selector 日志 (02:14:30)
[路径初始化] 路径起点: (-66.3, -129.3), 共85个点
[路径初始化] 当前位置: (-74.9, -182.0), 距起点: 53.3m

# 问题时刻无特殊日志输出（节点未检测到异常）
```

### 8.3 参数配置

```yaml
# planning_simulation.yaml
waypoint_selector:
  lookahead_distance_m: 2.0
  goal_tolerance_m: 0.3

track_controller:
  max_speed: 1.0
  heading_p_gain: 2.0
  max_angular_velocity: 1.0
  pivot_threshold_deg: 20.0
```

---

**报告人**: Claude (NodeFlow Analysis)
**审核**: 待团队讨论
**下一步**: 会议决策解决方案，制定实施计划
