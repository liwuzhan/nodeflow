# 仿真器边界问题修复报告

**日期**: 2025-12-31
**问题**: 车辆在仿真运行约10分钟后停止移动

---

## 问题现象

- 车辆在田地覆盖作业过程中突然停止前进
- 速度控制命令正常发送 (v=1.0 m/s)
- RTK 数据流正常更新

## 根因分析

通过分析仿真器日志发现：

```
03:50:50  车辆位置: x=84.36m, y=94.57m
03:51:00  车辆位置: x=85.61m, y=100.00m  ← 触碰边界
03:51:05  车辆位置: x=86.20m, y=100.00m  ← y 被限制在 100
03:51:10  车辆位置: x=86.74m, y=100.00m
```

**根因**: 仿真器物理引擎边界设置过小 (`y: [-100, 100]`)，当车辆 y 坐标达到 100m 时触发边界碰撞，`vy` 被置零，导致车辆无法继续向北移动。

## 修复方案

### 1. 扩大仿真器边界

**文件**: `simulator/config.yaml`

```yaml
# 修改前
bounds:
  x: [-100.0, 100.0]
  y: [-100.0, 100.0]

# 修改后
bounds:
  x: [-200.0, 200.0]
  y: [-200.0, 200.0]
```

### 2. 田地几何中心置于原点

**文件**: `simulator/server.py`

```python
# 修改前
self.field_generator = FieldGenerator()

# 修改后
field_config = self.config.get('field', {})
field_width = field_config.get('width', 100.0)
field_length = field_config.get('length', 200.0)
# 计算base坐标使田地几何中心在(0, 0)
base_x = -field_width / 2
base_y = -field_length / 2
self.field_generator = FieldGenerator(base_x=base_x, base_y=base_y)
```

## 修复效果

- 边界扩大到 ±200m，足够容纳 100m × 200m 的田地
- 田地几何中心位于原点 (0, 0)，车辆活动范围均匀分布在边界内
- 车辆可完成完整的田地覆盖作业而不触碰边界

## 相关文件

| 文件 | 修改内容 |
|------|----------|
| `simulator/config.yaml` | 边界从 ±100 扩大到 ±200 |
| `simulator/server.py` | 田地生成器初始化，中心置于原点 |
