# Waypoint Selector 视野扩宽不缩回问题 - 分析报告

## 问题描述

从轨迹对比图可以看到：
- ✅ 前面几个U形弯：红线（实际轨迹）紧跟蓝线（规划路径），贴合度好
- ❌ 后面的U形弯：红线逐渐偏离蓝线，贴合度变差

虽然所有U形弯的宽度都相同（3m），但控制精度递减。

## 根本原因分析

位置：`node-hub/waypoint_selector/atom.py` 第 330-360 行的 `_compute_in_view_points()` 方法

### 视野扩宽逻辑（现有）

```python
def _compute_in_view_points(self, vx: float, vy: float, theta: float) -> List[int]:
    # 步骤1: 用原始宽度搜索
    in_view = self._compute_in_view_points_with_width(vx, vy, theta, cfg.view_width)

    # 步骤2: 如果点数不足，扩宽视野
    if len(in_view) < cfg.min_view_points:  # min_view_points=3
        expanded_width = min(cfg.view_width * cfg.view_expand_factor, cfg.max_view_width)
        expanded_in_view = self._compute_in_view_points_with_width(
            vx, vy, theta, expanded_width
        )
        # 步骤3: 如果扩宽后有更多点，就用扩宽结果
        if len(expanded_in_view) > len(in_view):
            in_view = expanded_in_view

    return in_view
```

### 问题机制

1. **条件太宽松**：`min_view_points=3` 只需要3个点就算"足够"
2. **单向触发**：只有在 `len(in_view) < 3` 时才扩宽，但没有相反的"缩回"逻辑
3. **动态波动**：每一帧都会动态决定视野宽度

### 在U形弯上的表现

**场景**：车辆做大幅转向时

```
帧序列分析：
┌─────────────────────────────────────────┐
│ 帧 N：转弯点，路径点稀疏              │
│ → 原始宽度(4m)只找到 1-2 个点        │
│ → 触发扩宽到 8m                        │
│ → 找到 3-4 个点，使用扩宽视野          │
│ → 选择的前瞻点距路径更远               │
└─────────────────────────────────────────┘
        ↓
┌─────────────────────────────────────────┐
│ 帧 N+1, N+2, ...：继续转弯              │
│ → 扩宽视野仍有 3+ 个点                  │
│ → 条件 `len(in_view) < 3` 不满足       │
│ → 不再计算原始宽度的结果！             │
│ → 一直使用扩宽视野                      │
│ → 车辆逐帧偏离规划路径                  │
└─────────────────────────────────────────┘
```

## 配置参数分析

```yaml
view_distance: 3.0      # 视野中心距车辆 3m
view_width: 4.0         # 原始宽度
view_expand_factor: 2.0 # 扩宽倍数
max_view_width: 12.0    # 最大宽度
min_view_points: 3      # 触发扩宽的阈值
```

扩宽尺寸：4.0m → 8.0m（可能继续→12.0m）

在U形弯转弯点，扩宽视野会选择"外侧"的路径点，而不是紧跟规划路径中心。

## 修复方案

### 方案 A：增加"回弹"逻辑（推荐）

修改 `_compute_in_view_points()` 方法，使用**历史感知**：

```python
def _compute_in_view_points(self, vx: float, vy: float, theta: float) -> List[int]:
    cfg = self.config

    # 始终计算原始宽度的结果
    in_view_normal = self._compute_in_view_points_with_width(vx, vy, theta, cfg.view_width)

    # 如果原始宽度足够，直接返回（优先使用原始宽度）
    if len(in_view_normal) >= cfg.min_view_points:
        return in_view_normal

    # 只有当原始宽度不足时，才扩宽
    expanded_width = min(cfg.view_width * cfg.view_expand_factor, cfg.max_view_width)
    if expanded_width > cfg.view_width:
        expanded_in_view = self._compute_in_view_points_with_width(
            vx, vy, theta, expanded_width
        )
        if len(expanded_in_view) > len(in_view_normal):
            return expanded_in_view

    # 都不足，返回原始宽度的结果
    return in_view_normal
```

**优点**：
- ✅ 优先使用原始宽度（更紧跟路径）
- ✅ 只在必要时扩宽
- ✅ 自动"回弹"到原始宽度

### 方案 B：降低触发阈值

改变 `min_view_points` 的值：

```yaml
# 当前配置
min_view_points: 3

# 改为
min_view_points: 1  # 或 2
```

**优点**：
- ✅ 更容易满足条件，减少扩宽频率
- ⚠️ 可能在点数太少时选择误导的前瞻点

### 方案 C：添加滞后机制（Hysteresis）

记录上一帧使用的视野宽度，避免频繁切换：

```python
# 在 SelectorState 中添加
class SelectorState:
    ...
    last_view_width: float = None  # 上一帧的视野宽度

def _compute_in_view_points(self, vx, vy, theta):
    # 使用上一帧的宽度作为基准
    base_width = self.state.last_view_width or cfg.view_width

    in_view = self._compute_in_view_points_with_width(vx, vy, theta, base_width)

    # 如果不足，才扩宽
    if len(in_view) < cfg.min_view_points:
        expanded_width = min(base_width * cfg.view_expand_factor, cfg.max_view_width)
        ...

    # 记录本帧使用的宽度
    self.state.last_view_width = final_width
```

## 推荐修复

**立即执行**：方案 A（回弹逻辑）

理由：
1. 最小改动（只修改一个方法的逻辑）
2. 效果最明显（确保优先使用原始宽度）
3. 没有副作用（不改变参数，只改变决策顺序）

## 预期效果

修复后：
- ✅ 所有U形弯都能紧跟规划路径
- ✅ 在转弯点也能保持精准控制
- ✅ 实际轨迹贴合度一致（不随帧数递减）

## 验证步骤

1. 修改 `atom.py` 的 `_compute_in_view_points()` 方法
2. 重新运行 `planning_simulation.yaml`
3. 对比轨迹图：检查所有U形弯的贴合度是否均匀改善
4. 检查日志：`nodeflow logs -n waypoint_selector` 观察 `in_view_count` 的波动

