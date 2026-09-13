# U形弯打转问题解决方案

**日期**: 2025-12-30
**状态**: 方案设计中

---

## 一、问题描述

### 1.1 现象
车辆在U形弯掉头后开始原地打转，无法继续跟踪下一段路径。

### 1.2 现有分析
从可视化图片观察：
- 完成度约90%时出现问题
- 车辆在U形弯顶点位置（右上角）
- 实际轨迹显示车辆冲出规划路径后开始旋转

### 1.3 根本原因分析

**当前控制逻辑**（`track_controller/atom.py`）：
```python
# 当前速度控制策略
if error_deg >= pivot_th:  # 航向误差 > 15°
    v = 0.0  # 原地转向
else:
    v = max_speed * abs(math.cos(error_rad))  # 前进
    if dist < 2.0:  # 接近目标时减速
        v = v * (dist / 2.0)
```

**问题1：U形弯的速度控制不合理**
- 接近U形弯时，前瞻点还在当前直线段上，速度保持高速
- 当前瞻点突然跳到返回段（180°航向变化），车辆已经冲过去
- 冲过去后，新前瞻点在车辆后方，导致原地打转

**问题2：减速触发太晚**
- 当前只在 `dist < 2.0` 时减速
- 路径密化后（0.5m间距），车辆总能在2m内找到新前瞻点
- 永远不会触发真正的减速

**问题3：缺乏对视野状态的感知**
- 控制器不知道"还剩多少视野内的点"
- 不知道是否即将面临急转弯

---

## 二、解决方案

### 方案A：接近前瞻点减速（用户建议）

#### 核心思想
越接近当前前瞻点，速度越慢。如果始终有新的视野点（直线段），不会真正减到很慢；如果即将到达视野边界（急转弯），自然减速等待新视野点出现。

#### 实现方式

**修改 `track_controller/atom.py`：**

```python
def compute_velocity_cmd(...):
    # ... existing code ...

    # 获取前瞻点相关信息
    in_view_count = npkt.get("in_view", 1)  # 视野内点数
    consumed = npkt.get("consumed", 0)       # 已消费点数
    total = npkt.get("total", 1)             # 总点数

    # 计算速度衰减因子
    # 方案A-1: 基于距离的平滑减速
    decel_start = 3.0  # 开始减速的距离 (米)
    decel_min = 0.3    # 最小速度比例

    if dist < decel_start:
        # 线性衰减: dist=3m -> 1.0, dist=0 -> decel_min
        dist_factor = decel_min + (1.0 - decel_min) * (dist / decel_start)
    else:
        dist_factor = 1.0

    # 方案A-2: 基于视野内点数的减速
    # 视野内点少说明即将到达转弯处
    view_factor = 1.0
    if in_view_count <= 2:
        view_factor = 0.5  # 视野点少，减速50%
    elif in_view_count <= 5:
        view_factor = 0.7  # 视野点较少，减速30%

    # 综合速度因子
    speed_factor = min(dist_factor, view_factor)

    # 应用速度因子
    v = v * speed_factor
    w = w * speed_factor  # 角速度也减慢
```

#### 配置参数
```yaml
# track_controller/node.yaml
params:
  decel_start_distance: 3.0    # 开始减速的距离 (米)
  decel_min_factor: 0.3        # 最小速度比例
  low_view_speed_factor: 0.5   # 视野点少时的速度因子
```

#### 优点
- 逻辑简单直观
- 无需修改waypoint_selector
- 直线段不受影响（总有新视野点）

#### 缺点
- 需要waypoint_selector输出in_view_count
- 可能在弯道处过度减速

---

### 方案B：视野点耗尽预警减速

#### 核心思想
waypoint_selector输出一个"视野健康度"指标，表示当前视野的充裕程度。控制器根据这个指标调整速度。

#### 实现方式

**修改 `waypoint_selector/atom.py` 输出：**

```python
def select(self, pose):
    # ... existing code ...

    # 计算视野健康度
    # = 视野内点数 / max_search_points
    # 越低说明越接近视野边界
    view_health = len(self.state.in_view_indices) / self.config.max_search_points

    return {
        "x": target_x,
        "y": target_y,
        "final": is_final,
        "consumed": first_unconsumed_idx,
        "total": len(path),
        "in_view": len(in_view_indices),
        "view_health": view_health,  # 新增：0~1之间
        "mode": mode
    }
```

**修改 `track_controller/atom.py`：**

```python
def compute_velocity_cmd(...):
    view_health = npkt.get("view_health", 1.0)

    # 视野健康度低于阈值时开始减速
    if view_health < 0.3:
        # view_health: 0.3->1.0, 0.0->0.2
        health_factor = 0.2 + 0.8 * (view_health / 0.3)
        v = v * health_factor
        w = w * health_factor
```

#### 优点
- 语义清晰：视野健康度直接反映路径状态
- 可以预见性减速

#### 缺点
- 需要同时修改两个节点
- view_health的计算可能需要调优

---

### 方案C：转弯预判减速（曲率感知）

#### 核心思想
提前分析路径曲率，在高曲率段前减速。

#### 实现方式

**在 `waypoint_selector/atom.py` 中计算曲率：**

```python
def _compute_path_curvature(self, start_idx, end_idx):
    """计算路径段的曲率"""
    path = self.state.path
    if end_idx - start_idx < 3:
        return 0.0

    # 使用三点法计算曲率
    # 曲率 = 2 * |cross(P1-P0, P2-P1)| / (|P1-P0| * |P2-P1| * |P2-P0|)
    total_curvature = 0.0
    count = 0

    for i in range(start_idx, end_idx - 2):
        p0, p1, p2 = path[i], path[i+1], path[i+2]

        v1 = (p1[0]-p0[0], p1[1]-p0[1])
        v2 = (p2[0]-p1[0], p2[1]-p1[1])

        cross = v1[0]*v2[1] - v1[1]*v2[0]
        len1 = math.sqrt(v1[0]**2 + v1[1]**2)
        len2 = math.sqrt(v2[0]**2 + v2[1]**2)
        len02 = math.sqrt((p2[0]-p0[0])**2 + (p2[1]-p0[1])**2)

        if len1 > 0 and len2 > 0 and len02 > 0:
            curvature = 2 * abs(cross) / (len1 * len2 * len02)
            total_curvature += curvature
            count += 1

    return total_curvature / count if count > 0 else 0.0
```

**输出曲率信息：**

```python
return {
    "x": target_x,
    "y": target_y,
    "curvature": upcoming_curvature,  # 新增
    ...
}
```

**控制器使用曲率减速：**

```python
curvature = npkt.get("curvature", 0.0)
curvature_threshold = 0.5  # 曲率阈值

if curvature > curvature_threshold:
    # 高曲率区域减速
    curvature_factor = curvature_threshold / curvature
    v = v * curvature_factor
```

#### 优点
- 物理意义明确
- 可以实现预判减速（提前看到后面的弯）

#### 缺点
- 计算复杂度高
- 曲率阈值需要调优
- U形弯的曲率可能不明显（直接180°折返）

---

### 方案D：模式感知减速（推荐）

#### 核心思想
利用现有的`mode`字段，当waypoint_selector处于非正常跟踪模式时减速。

#### 现有模式
```python
# waypoint_selector输出的mode：
# - "tracking": 正常跟踪（视野内有点）
# - "approach": 接近模式（视野内无点，输出第一个未消费点）
# - "fallback": 回退模式
```

#### 实现方式

**修改 `track_controller/atom.py`：**

```python
def compute_velocity_cmd(...):
    mode = npkt.get("mode", "tracking")

    # 模式减速因子
    mode_factors = {
        "tracking": 1.0,    # 正常速度
        "approach": 0.3,    # 接近模式，大幅减速
        "fallback": 0.2,    # 回退模式，更慢
    }

    mode_factor = mode_factors.get(mode, 1.0)

    v = v * mode_factor
    # 注意：角速度不一定要减，让车辆能快速转向
```

#### 优点
- 实现最简单
- 利用现有数据，无需修改waypoint_selector
- 语义清晰

#### 缺点
- 只在"已经没有视野点"时才触发，没有预判
- 但配合方案A（距离减速）可以解决这个问题

---

## 三、综合推荐方案

### 推荐：方案A + 方案D 组合

#### 设计理念
1. **距离减速**（方案A-1）：接近当前前瞻点时平滑减速
2. **视野点减速**（方案A-2）：视野内点数少时预警减速
3. **模式减速**（方案D）：进入非正常模式时保底减速

#### 速度计算公式

```python
# 1. 基础速度（现有逻辑）
if error_deg >= pivot_th:
    v_base = 0.0  # 原地转向
else:
    v_base = max_speed * abs(math.cos(error_rad))

# 2. 距离减速因子
if dist < decel_start_distance:
    dist_factor = decel_min + (1.0 - decel_min) * (dist / decel_start_distance)
else:
    dist_factor = 1.0

# 3. 视野点减速因子（需要waypoint_selector输出in_view）
in_view = npkt.get("in_view", 10)
if in_view <= 2:
    view_factor = 0.4
elif in_view <= 5:
    view_factor = 0.6
else:
    view_factor = 1.0

# 4. 模式减速因子
mode = npkt.get("mode", "tracking")
mode_factor = {"tracking": 1.0, "approach": 0.3, "fallback": 0.2}.get(mode, 1.0)

# 5. 综合速度
speed_factor = min(dist_factor, view_factor, mode_factor)
v = v_base * speed_factor

# 6. 角速度也适当减速（但保留一定转向能力）
w_factor = max(speed_factor, 0.5)  # 角速度至少保留50%
w = w_base * w_factor
```

#### 配置参数汇总

```yaml
# track_controller/node.yaml
params:
  max_speed: 1.0               # 最大线速度 (m/s)
  min_speed: 0.0               # 最小线速度 (m/s)
  heading_p_gain: 2.5          # 航向P增益
  max_angular_velocity: 1.0    # 最大角速度 (rad/s)
  pivot_threshold_deg: 15.0    # 原地转向阈值 (度)

  # 新增：减速控制参数
  decel_start_distance: 3.0    # 开始减速的距离 (米)
  decel_min_factor: 0.3        # 距离减速最小因子
  low_view_threshold: 5        # 视野点少阈值
  low_view_speed_factor: 0.6   # 视野点少时速度因子
  very_low_view_threshold: 2   # 视野点很少阈值
  very_low_view_speed_factor: 0.4  # 视野点很少时速度因子
```

---

## 四、预期效果

### 4.1 直线段
- 视野内始终有足够的点（in_view > 5）
- mode = "tracking"
- dist_factor 可能波动，但 view_factor 和 mode_factor 都是 1.0
- **结果**：基本保持正常速度

### 4.2 接近U形弯
- 视野内点数开始减少（in_view 降低）
- view_factor 开始降低
- **结果**：提前减速

### 4.3 U形弯顶点
- 视野内可能只剩1-2个点或0个点
- mode 可能变为 "approach"
- view_factor 和 mode_factor 都很低
- **结果**：大幅减速，给足时间让新路径段进入视野

### 4.4 U形弯后
- 新路径段进入视野
- in_view 恢复，mode 恢复为 "tracking"
- **结果**：速度恢复

---

## 五、实施步骤

### 第一步：修改 waypoint_selector 输出
确保输出包含 `in_view` 字段（当前视野内点数）

### 第二步：修改 track_controller/atom.py
实现综合减速逻辑

### 第三步：更新 node.yaml
添加新的配置参数

### 第四步：更新 planning_simulation.yaml
配置合适的参数值

### 第五步：测试验证
在U形弯场景中验证效果

---

## 六、其他可探索方向

### 6.1 动态前瞻距离
- 高速时前瞻距离大，低速时前瞻距离小
- 需要修改waypoint_selector的view_distance为动态值

### 6.2 路径预览窗口
- 控制器不仅看当前前瞻点，而是看未来N个点
- 可以预判转弯并提前减速

### 6.3 轨迹平滑
- 在规划阶段对U形弯做圆弧平滑
- 避免180°急转弯

---

## 七、总结

推荐采用 **方案A + 方案D 组合**：

| 触发条件 | 减速程度 | 目的 |
|---------|---------|-----|
| 距离接近前瞻点 | 渐进减速到30% | 给视野更新留时间 |
| 视野内点数少 (≤5) | 减速到60% | 预警即将转弯 |
| 视野内点数很少 (≤2) | 减速到40% | 强预警 |
| mode = approach | 减速到30% | 保底减速 |
| mode = fallback | 减速到20% | 紧急减速 |

这个方案的核心优势：**不需要预知路径形状，仅根据"还能看到多少点"来自适应调整速度**，自然地解决U形弯问题。
