# Mock GPS Node

## 概述

模拟GPS/RTK定位设备，生成高精度位置数据用于测试定位和导航功能。

## 功能

- 生成GPS定位数据（纬度、经度、高程）
- 支持三种模式：静止、移动、轨迹（预留）
- 模拟RTK级精度（厘米级）
- 包含速度矢量和卫星信息
- 可配置噪声水平

## 端口定义

### 输出端口

- **gps_fix** (JSON): GPS定位数据
  ```json
  {
    "timestamp": 1703024780.123,
    "seq": 1,
    "latitude": 39.9042,
    "longitude": 116.4074,
    "altitude": 50.0,
    "fix_type": "RTK",
    "num_satellites": 24,
    "horizontal_accuracy": 0.05,
    "vertical_accuracy": 0.10,
    "velocity_east": 0.5,
    "velocity_north": 1.0,
    "velocity_up": 0.0
  }
  ```

### 输入端口

无

## 参数配置

| 参数名 | 类型 | 默认值 | 说明 |
|--------|------|--------|------|
| `mode` | string | `"stationary"` | 生成模式：`stationary`（静止）、`moving`（移动）、`trajectory`（轨迹） |
| `update_rate_hz` | number | `10` | 发布频率（Hz） |
| `start_latitude` | number | `39.9042` | 起始纬度（十进制度数） |
| `start_longitude` | number | `116.4074` | 起始经度（十进制度数） |
| `start_altitude` | number | `50.0` | 起始高程（米） |
| `velocity_mps` | number | `1.0` | 移动速度（米/秒，仅moving模式） |
| `heading_deg` | number | `45.0` | 移动方向（度，0=北，90=东） |
| `accuracy_meters` | number | `0.05` | 水平精度（米） |

## 使用示例

### 示例1：静止模式（默认）

```yaml
nodes:
  - id: gps_0
    package: mock_gps
    params:
      mode: stationary
      start_latitude: 39.9042
      start_longitude: 116.4074
      accuracy_meters: 0.05
```

模拟静止的RTK基站，适合测试位置数据接收。

### 示例2：移动模式

```yaml
nodes:
  - id: gps_0
    package: mock_gps
    params:
      mode: moving
      velocity_mps: 2.0
      heading_deg: 90  # 向东移动
      update_rate_hz: 10
```

模拟以2m/s向东移动的设备，适合测试路径跟踪算法。

### 示例3：低精度GPS

```yaml
nodes:
  - id: gps_0
    package: mock_gps
    params:
      mode: stationary
      accuracy_meters: 5.0  # 普通GPS精度
```

模拟低精度GPS，适合测试容错能力。

## 数据生成逻辑

### Stationary 模式
- 位置固定在起始坐标
- 添加高斯噪声（标准差 = `accuracy_meters`）
- 速度矢量为零

### Moving 模式
- 根据速度和方向线性移动
- 使用平面坐标近似：
  - 纬度变化 ≈ `velocity_north / 111320` 度/米
  - 经度变化 ≈ `velocity_east / (111320 * cos(latitude))` 度/米
- 速度矢量反映当前运动状态

### Trajectory 模式（预留）
- 未来可加载CSV或JSON格式的轨迹文件
- 按时间戳回放预定义路径

## 坐标系统

- **纬度**: -90° (南极) 到 +90° (北极)
- **经度**: -180° (西) 到 +180° (东)
- **高程**: 相对于WGS84椭球面（米）

默认位置（北京天安门广场）：
- 纬度: 39.9042°N
- 经度: 116.4074°E

## 精度说明

| 精度级别 | accuracy_meters | 用途 |
|----------|-----------------|------|
| RTK | 0.02 - 0.05 | 高精度应用（自动驾驶、精准农业） |
| DGPS | 0.5 - 1.0 | 增强GPS |
| 标准GPS | 5.0 - 10.0 | 普通导航 |

## 测试用途

1. **位置数据接收**: 验证节点能否正确解析GPS数据
2. **坐标转换**: 测试地理坐标到平面坐标的转换
3. **路径跟踪**: 使用moving模式测试纯追踪算法
4. **精度容差**: 使用不同accuracy值测试算法鲁棒性

## 替换为真实硬件

要替换为真实GPS/RTK设备：

1. 修改 `run.py` 连接到硬件串口或网络接口
2. 解析NMEA或UBX协议数据
3. 转换为相同的JSON输出格式
4. 保持数据字段一致性

```python
# 真实硬件集成示例（使用pyserial + pynmea2）
import serial
import pynmea2

ser = serial.Serial('/dev/ttyUSB0', 115200)

while True:
    line = ser.readline().decode('ascii', errors='ignore')

    if line.startswith('$GNGGA'):  # GPS Fix Data
        msg = pynmea2.parse(line)

        gps_data = {
            'timestamp': time.time(),
            'seq': seq,
            'latitude': msg.latitude,
            'longitude': msg.longitude,
            'altitude': msg.altitude,
            'fix_type': 'RTK' if msg.gps_qual == 4 else 'GPS',
            'num_satellites': msg.num_sats,
            'horizontal_accuracy': msg.horizontal_dil,
            # ... 其他字段 ...
        }

        gps_output.send(gps_data)
        seq += 1
```

## 依赖

- Python 3.9+
- NodeFlow SDK

## 日志输出

- **INFO**: 启动信息、配置参数
- **DEBUG**: 每秒一次的位置数据样本
- **ERROR**: 异常情况

## 性能指标

- CPU占用：< 1%
- 内存占用：< 10 MB
- 位置更新稳定性：按配置频率精确输出
