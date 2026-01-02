# Track Controller 减速优化方案

**日期**: 2025-12-30
**问题**: U形弯打转
**节点**: track_controller

---

## 一、问题分析

### 1.1 当前减速逻辑（atom.py 第66-67行）

```python
if dist < 2.0:
    v = v * (dist / 2.0)
```

**问题**：
- 路径密化后（0.5m间距），前瞻点不断更新
- 在直线段，`dist` 始终在 2-4m 之间（因为 view_distance=3.0m）
- **减速条件几乎不触发**

### 1.2 U形弯打转场景

1. **接近U形弯**：前瞻点还在直线段，dist ≈ 3m，保持高速
2. **到达U形弯顶点**：前瞻点跳到返回段，车辆已冲过去
3. **冲过后**：前瞻点在车后，开始打转

**核心问题**：track_controller 只看"到前瞻点的距离"，不知道"路径状态"

---

## 二、方案设计

### 方案1：距离梯度减速（推荐）

#### 核心思想
- **不看绝对距离**，而是看"距离变化率"
- 如果距离在缩小 → 说明在接近前瞻点 → 减速
- 如果距离保持稳定 → 说明前瞻点在更新（直线段）→ 不减速

#### 实现

```python
# atom.py 修改

# 在函数外部添加状态记录（或通过参数传入）
_last_dist = None
_last_npkt_index = None

def compute_velocity_cmd(...):
    global _last_dist, _last_npkt_index

    # ... existing code ...

    dist = math.sqrt((nx - cx)**2 + (ny - cy)**2)
    current_index = npkt.get("consumed", 0)  # 当前消费的点索引

    # 检测前瞻点是否更新
    point_updated = (_last_npkt_index is None or
                     current_index != _last_npkt_index)

    # 计算距离变化率
    if _last_dist is not None and not point_updated:
        dist_delta = dist - _last_dist
        approaching = (dist_delta < -0.1)  # 距离在减小
    else:
        approaching = False

    # 更新状态
    _last_dist = dist
    _last_npkt_index = current_index

    # 减速逻辑
    if approaching:
        # 正在接近且前瞻点未更新 → 减速
        approach_factor = max(0.3, dist / 3.0)
        v = v * approach_factor
    else:
        # 前瞻点在更新或距离稳定 → 正常速度
        pass
```

#### 问题
- **需要维护状态**，与当前无状态设计冲突
- 50Hz调用频率下，状态管理复杂

---

### 方案2：基于 waypoint_selector 输出信息减速（用户方案改进）

#### 前提
waypoint_selector 需要输出以下信息（**不控制速度，只提供信息**）：

```python
# waypoint_selector/atom.py 返回
{
    "x": float,
    "y": float,
    "final": bool,
    "consumed": int,        # 已消费点索引
    "total": int,           # 总点数
    "in_view": int,         # 当前视野内点数 ← 关键
    "mode": str             # "tracking" / "approach" / "fallback"
}
```

#### track_controller 使用信息

```python
def compute_velocity_cmd(...):
    # ... existing code ...

    # 1. 获取视野状态
    in_view = npkt.get("in_view", 10)
    mode = npkt.get("mode", "tracking")

    # 2. 基础速度计算（保持现有逻辑）
    if error_deg >= pivot_th:
        v = 0.0
    else:
        v = max_speed * abs(math.cos(error_rad))

    # 3. 距离减速（扩大触发范围）
    decel_distance = 3.0  # 从2.0扩大到3.0
    if dist < decel_distance:
        dist_factor = max(0.3, dist / decel_distance)
        v = v * dist_factor

    # 4. 视野点数减速（新增）
    if in_view <= 2:
        view_factor = 0.4  # 视野点很少，大幅减速
    elif in_view <= 5:
        view_factor = 0.7  # 视野点较少，适度减速
    else:
        view_factor = 1.0  # 正常

    v = v * view_factor

    # 5. 模式减速（保底）
    if mode == "approach":
        v = v * 0.5  # 接近模式，减速50%
    elif mode == "fallback":
        v = v * 0.3  # 回退模式，减速70%

    # 6. 角速度也适当减速
    if view_factor < 1.0 or mode != "tracking":
        w = w * max(view_factor, 0.5)

    return {"linear_velocity": v, "angular_velocity": w, "timestamp": now}
```

#### 优点
- **职责清晰**：waypoint_selector 提供信息，track_controller 做决策
- **直线段不受影响**：in_view 始终 > 5，view_factor = 1.0
- **U形弯自动减速**：in_view 降低 → view_factor 降低 → 速度降低

#### 配置参数

```yaml
# track_controller/node.yaml
params:
  max_speed: 1.0
  min_speed: 0.0
  heading_p_gain: 2.5
  max_angular_velocity: 1.0
  pivot_threshold_deg: 15.0

  # 减速参数
  decel_distance: 3.0          # 距离减速起始点 (米)
  low_view_threshold: 5        # 视野点少阈值
  low_view_factor: 0.7         # 视野点少时速度因子
  very_low_view_threshold: 2   # 视野点很少阈值
  very_low_view_factor: 0.4    # 视野点很少时速度因子
  approach_mode_factor: 0.5    # approach 模式速度因子
  fallback_mode_factor: 0.3    # fallback 模式速度因子
```

---

### 方案3：纯距离减速（最简单）

#### 核心思想
直接扩大距离减速的触发范围，让减速更早开始。

#### 实现

```python
def compute_velocity_cmd(...):
    # ... existing code ...

    # 修改距离减速逻辑
    decel_start = 4.0   # 从 2.0 扩大到 4.0
    decel_min = 0.3     # 最小速度比例

    if dist < decel_start:
        # 线性插值：dist=4m -> 1.0, dist=0 -> 0.3
        dist_factor = decel_min + (1.0 - decel_min) * (dist / decel_start)
        v = v * dist_factor
```

#### 问题
- **直线段也会受影响**：前瞻点在3m时就开始减速
- 可能导致整体速度偏慢

---

## 三、推荐方案

### 采用：方案2（基于 waypoint_selector 信息）

#### 理由
1. **职责分明**：waypoint_selector 只提供"视野状态"，不越界
2. **自适应**：根据视野点数自动调整，不需要预知路径
3. **直线段不受影响**：视野充足时保持正常速度

#### 实施步骤

**第一步**：修改 waypoint_selector 输出（已有部分字段）
```python
# node-hub/waypoint_selector/atom.py
return {
    "x": target_x,
    "y": target_y,
    "final": is_final,
    "consumed": self.state.first_unconsumed_idx,
    "total": len(self.state.path),
    "in_view": len(self.state.in_view_indices),  # 新增
    "mode": mode
}
```

**第二步**：修改 track_controller 减速逻辑
```python
# node-hub/track_controller/atom.py
# 按照方案2的代码实现
```

**第三步**：更新配置文件
```yaml
# planning_simulation.yaml
- id: track_controller
  params:
    decel_distance: 3.0
    low_view_threshold: 5
    low_view_factor: 0.7
    very_low_view_threshold: 2
    very_low_view_factor: 0.4
```

---

## 四、效果预期

### 场景1：直线段
- `in_view` ≈ 6-10（视野充足）
- `view_factor` = 1.0
- `dist` ≈ 3.0m
- `dist_factor` ≈ 1.0
- **速度**：基本保持 max_speed

### 场景2：接近U形弯
- `in_view` 开始下降（5, 4, 3...）
- `view_factor` 降至 0.7
- **速度**：降至 max_speed * 0.7

### 场景3：U形弯顶点
- `in_view` ≈ 1-2（视野点很少）
- `view_factor` = 0.4
- 可能 `mode` = "approach"
- **速度**：降至 max_speed * 0.4 * 0.5 = max_speed * 0.2
- **给足时间**让新路径段进入视野

### 场景4：U形弯后
- 新路径段进入视野
- `in_view` 恢复到 6+
- `view_factor` 恢复到 1.0
- **速度**：恢复正常

---

## 五、关键指标监控

建议在日志中输出以下信息（调试模式）：

```python
sdk.logger.debug(
    f"[速度控制] dist={dist:.2f}m, in_view={in_view}, "
    f"mode={mode}, dist_factor={dist_factor:.2f}, "
    f"view_factor={view_factor:.2f}, v={v:.2f}m/s"
)
```

这样可以观察：
- U形弯时 in_view 如何变化
- view_factor 是否正确触发
- 速度是否合理下降

---

## 六、总结

**核心设计原则**：
- waypoint_selector：提供"我能看到多远"（in_view）
- track_controller：根据"能看到多远"决定"开多快"

**物理直觉**：
- 看得远（视野充足）→ 可以开快
- 看不远（视野受限）→ 必须慢行

这种设计**自然地**解决了U形弯问题，无需预知路径形状。
