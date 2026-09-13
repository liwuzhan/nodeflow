# 坐标系约定文档

本文档定义了 NodeFlow 系统中各节点使用的坐标系约定，确保节点间数据传递的一致性。

## 1. GPS 坐标系统

### 1.1 支持的坐标系

| 坐标系 | 英文名 | 说明 | 使用场景 |
|--------|--------|------|----------|
| **WGS84** | World Geodetic System 1984 | 国际标准，GPS 原始坐标 | 默认坐标系，推荐使用 |
| GCJ02 | 火星坐标系 | 中国国测局加密坐标 | 高德/腾讯地图 |
| BD09 | 百度坐标系 | 百度在 GCJ02 基础上再加密 | 百度地图 |

### 1.2 当前系统约定

**NodeFlow 统一使用 WGS84 坐标系**

- 所有节点间传递的经纬度均为 WGS84 格式
- 如需对接国内地图 API，由调用方自行转换
- 仿真器内部使用局部笛卡尔坐标，输出时转换为 WGS84

### 1.3 在 node.yaml 中声明

```yaml
# node.yaml
metadata:
  coordinate_system: WGS84  # 可选: WGS84, GCJ02, BD09
```

---

## 2. 航向角坐标系

### 2.1 两种坐标系定义

#### 地理坐标系 (Geographic) - **推荐用于节点间传递**

| 属性 | 定义 |
|------|------|
| **0°** | 正北方向 (North) |
| **90°** | 正东方向 (East) |
| **180°** | 正南方向 (South) |
| **270°** | 正西方向 (West) |
| **正方向** | 顺时针 (Clockwise, CW) |
| **范围** | [0, 360) 度 |

```
        N (0°)
         ↑
         |
W (270°) ←---→ E (90°)
         |
         ↓
        S (180°)
```

#### 数学坐标系 (Mathematical) - 仅用于内部计算

| 属性 | 定义 |
|------|------|
| **0** | 正东方向 (+X) |
| **π/2** | 正北方向 (+Y) |
| **π** | 正西方向 (-X) |
| **-π/2** | 正南方向 (-Y) |
| **正方向** | 逆时针 (Counter-Clockwise, CCW) |
| **范围** | (-π, π] 弧度 |

```
        +Y (π/2)
         ↑
         |
-X (π) ←---→ +X (0)
         |
         ↓
        -Y (-π/2)
```

### 2.2 坐标系转换公式

```python
# 地理坐标系 → 数学坐标系
math_rad = radians(90.0 - geo_deg)

# 数学坐标系 → 地理坐标系
geo_deg = (90.0 - degrees(math_rad)) % 360.0
```

### 2.3 NodeFlow 约定

**节点间传递航向角统一使用地理坐标系（度）**

| 字段名 | 坐标系 | 单位 | 范围 | 说明 |
|--------|--------|------|------|------|
| `heading` | 地理 | 度 | [0, 360) | RTK/GPS 输出的航向角 |
| `target_bearing` | 地理 | 度 | [0, 360) | 目标方位角 |
| `heading_error` | 地理 | 度 | (-180, 180] | 航向误差，正=需CW转 |

### 2.4 SDK 工具函数

```python
from sdk.utils.geo import (
    bearing_geo,        # 计算方位角（地理坐标系，度）
    bearing_math,       # 计算方位角（数学坐标系，弧度）
    heading_geo_to_math,  # 地理→数学
    heading_math_to_geo,  # 数学→地理
    normalize_heading_deg,  # 归一化到 [0, 360)
    normalize_angle_rad,    # 归一化到 (-π, π]
)
```

---

## 3. 仿真器内部坐标系

### 3.1 局部笛卡尔坐标系

仿真器内部使用局部笛卡尔坐标系：

| 属性 | 定义 |
|------|------|
| **原点** | 参考点 (ref_lon, ref_lat) |
| **X 轴** | 东方向，单位：米 |
| **Y 轴** | 北方向，单位：米 |
| **yaw = 0** | 指向 +X（东） |
| **yaw 正方向** | CCW（逆时针） |

### 3.2 GPS 参考点配置

GPS 参考点仅需在仿真器配置中设置一次：

| 配置位置 | 参数名 | 默认值 |
|----------|--------|--------|
| `simulator/config.yaml` | `gps_ref.lon`, `gps_ref.lat` | 121.5, 31.2 |

`sim_output` 节点会通过 `get_config` API 自动从仿真器获取参考点，无需重复配置。

```yaml
# simulator/config.yaml
gps_ref:
  lon: 121.5
  lat: 31.2
```

### 3.3 坐标转换函数

```python
from sdk.utils.geo import local_to_wgs84, wgs84_to_local

# 局部坐标 → WGS84
lon, lat = local_to_wgs84(x_m, y_m, ref_lon, ref_lat)

# WGS84 → 局部坐标
x_m, y_m = wgs84_to_local(lon, lat, ref_lon, ref_lat)
```

### 3.4 仿真器输出的 heading

仿真器 sensors.py 已经将内部 yaw 转换为地理坐标系 heading：

```python
# sensors.py 第 168-170 行
heading_deg = (-(math.degrees(state.yaw)) + 90.0) % 360.0
```

---

## 4. 角速度约定

### 4.1 仿真器的 angular_velocity

| 符号 | 旋转方向 |
|------|----------|
| **正值** | CCW（逆时针），yaw 增大 |
| **负值** | CW（顺时针），yaw 减小 |

### 4.2 控制器计算逻辑

```python
# track_controller 第 73-78 行

# 航向误差（地理坐标系）：正值表示需要 CW 转向
error_deg = normalize_heading_error(target_bearing_deg - current_heading_deg)

# 角速度命令（仿真器坐标系）：正值表示 CCW
# 因此需要取反
w = -kp * error_rad
```

---

## 5. 节点坐标系声明

### 5.1 在 node.yaml 中声明

每个节点应在 `node.yaml` 的 `metadata` 中声明使用的坐标系：

```yaml
# node.yaml
name: my_node
version: 1.0.0

metadata:
  coordinate_system: WGS84          # GPS 坐标系
  heading_convention: geographic    # 航向角约定: geographic | mathematical

inputs:
  - name: rtk_fix
    type: sensor.rtk
    description: "RTK 定位数据"
    data_format:
      latitude: "WGS84 纬度（度）"
      longitude: "WGS84 经度（度）"
      heading: "航向角（地理坐标系，度，北=0，CW正）"

outputs:
  - name: velocity_cmd
    type: control.velocity
    description: "速度控制命令"
    data_format:
      linear_velocity: "线速度（m/s）"
      angular_velocity: "角速度（rad/s，CCW正）"
```

### 5.2 常用数据格式

#### RTK 定位数据
```yaml
rtk_fix:
  latitude: float     # WGS84 纬度（度）
  longitude: float    # WGS84 经度（度）
  altitude: float     # 海拔高度（米）
  heading: float      # 航向角（度），地理坐标系，北=0，CW正
  rtk_status: string  # "FIXED" | "FLOAT" | "SINGLE" | "NONE"
```

#### 路径数据
```yaml
global_path:
  path: list          # [(lon, lat), ...] WGS84 经纬度序列
  task_id: string     # 任务 ID
```

#### 速度控制命令
```yaml
velocity_cmd:
  linear_velocity: float   # 线速度（m/s），正=前进
  angular_velocity: float  # 角速度（rad/s），正=CCW
  timestamp: float         # 时间戳
```

---

## 6. 最佳实践

### 6.1 新增节点时

1. 在 `node.yaml` 中声明坐标系约定
2. 使用 `sdk/utils/geo.py` 中的工具函数进行坐标转换
3. 节点间传递使用 **WGS84 + 地理坐标系航向角**
4. 内部计算可使用数学坐标系，但输出前需转换

### 6.2 调试建议

1. 检查航向角单位（度 vs 弧度）
2. 检查坐标系（地理 vs 数学）
3. 检查角速度符号（CW vs CCW）
4. 使用 `trajectory_viz` 可视化验证轨迹

### 6.3 常见错误

| 错误现象 | 可能原因 |
|----------|----------|
| 机器人反向转 | 角速度符号错误 |
| 机器人偏离 90° | 地理/数学坐标系混用 |
| 机器人旋转不停 | 航向角跨越 0°/360° 边界未正确处理 |
| 轨迹偏移 | WGS84/GCJ02 坐标系混用 |

---

## 7. 参考资料

- [WGS84 坐标系](https://en.wikipedia.org/wiki/World_Geodetic_System)
- [GCJ02 火星坐标系](https://en.wikipedia.org/wiki/Restrictions_on_geographic_data_in_China)
- [Haversine 公式](https://en.wikipedia.org/wiki/Haversine_formula)
- SDK 源码: `sdk/utils/geo.py`
