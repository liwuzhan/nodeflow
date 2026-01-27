# RTK驱动节点

高精度RTK-GPS驱动节点，支持UM982/UMD982等双天线RTK设备，通过串口或网络接口读取NMEA消息并输出标准化的定位数据。

## 功能特性

- ✅ **多种连接方式**：串口、TCP、UDP
- ✅ **NMEA消息支持**：$KSXT（集成消息）、$GPGGA、$GPRMC、$GPTHS
- ✅ **高频输出**：支持 1-50 Hz 输出频率
- ✅ **RTK质量控制**：可配置最低质量要求和卫星数量
- ✅ **数据平滑**：可选的指数平滑滤波
- ✅ **原始数据记录**：支持记录原始NMEA数据用于调试
- ✅ **自动重连**：连接失败自动重试
- ✅ **校验和验证**：确保数据完整性

## 输出数据格式

**端口**: `rtk_fix` (类型: `sensor.rtk`)

```python
{
    'timestamp': 1672531200.123,      # Unix时间戳（秒）
    'lat': 39.98765432,                # 纬度（度，WGS84）
    'lon': 116.12345678,               # 经度（度，WGS84）
    'alt': 123.456,                    # 海拔高度（米，MSL）
    'heading': 1.5708,                 # 航向角（弧度，数学坐标系：东=0，CCW正）
    'rtk_status': 'FIXED',             # RTK状态字符串
    'rtk_quality': 3,                  # RTK质量（0=无效, 1=单点, 2=浮点, 3=固定）
    'num_satellites': 15,              # 定位卫星数量

    # 可选字段（取决于RTK设备和NMEA消息类型）
    'ground_speed': 1.234,             # 地面速度（m/s）
    'vel_east': 1.234,                 # 东向速度（m/s）
    'vel_north': 5.678,                # 北向速度（m/s）
    'vel_up': 0.123,                   # 天向速度（m/s）
    'pitch': 0.087,                    # 俯仰角（弧度）
    'roll': 0.052,                     # 横滚角（弧度）
    'hdop': 0.8,                       # 水平精度因子
    'heading_quality': 3,              # 航向质量（双天线RTK）
    'num_satellites_heading': 12       # 航向解算卫星数量
}
```

## 参数配置

### 串口配置（推荐）

```yaml
- id: rtk_gps
  package: rtk_driver
  params:
    # 串口连接
    serial_port: "/dev/ttyUSB0"      # 串口设备路径
    serial_baudrate: 115200          # 波特率（9600-921600）
    serial_timeout: 1.0              # 读取超时（秒）

    # NMEA消息
    nmea_message: "KSXT"             # 主要消息类型
    output_frequency: 20             # 输出频率（Hz）

    # 质量控制
    min_rtk_quality: 3               # 最低质量（3=固定解）
    min_satellites: 10               # 最少卫星数
```

### 网络配置（可选）

```yaml
- id: rtk_gps
  package: rtk_driver
  params:
    # 网络连接
    use_network: true
    network_host: "192.168.1.100"    # RTK设备IP
    network_port: 5000               # 端口号
    network_protocol: "tcp"          # tcp或udp

    # NMEA消息
    nmea_message: "KSXT"
    output_frequency: 20
```

### 完整参数列表

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `serial_port` | str | `/dev/ttyUSB0` | 串口设备路径 |
| `serial_baudrate` | int | `115200` | 波特率 |
| `serial_timeout` | float | `1.0` | 串口读取超时（秒） |
| `use_network` | bool | `false` | 是否使用网络接口 |
| `network_host` | str | `192.168.1.100` | RTK设备IP地址 |
| `network_port` | int | `5000` | 网络端口 |
| `network_protocol` | str | `tcp` | 网络协议（tcp/udp） |
| `nmea_message` | str | `KSXT` | 主要NMEA消息类型 |
| `output_frequency` | int | `20` | 输出频率（Hz） |
| `min_rtk_quality` | int | `4` | 最低RTK质量（0-3） |
| `min_satellites` | int | `10` | 最少卫星数量 |
| `enable_smoothing` | bool | `false` | 是否启用平滑滤波 |
| `smoothing_alpha` | float | `0.3` | 平滑系数（0-1） |
| `heading_source` | str | `dual_antenna` | 航向来源 |
| `enable_raw_log` | bool | `false` | 是否记录原始NMEA |
| `raw_log_path` | str | `/tmp/rtk_raw.log` | 原始日志路径 |

## 使用示例

### 1. 基础使用（串口连接）

```yaml
# runtime.yaml
nodes:
  - id: my_rtk
    package: rtk_driver
    params:
      serial_port: "/dev/ttyUSB0"
      serial_baudrate: 115200
      nmea_message: "KSXT"
      output_frequency: 20

  - id: my_controller
    package: track_controller

edges:
  - from: my_rtk.rtk_fix
    to: my_controller.rtk_input
```

### 2. 高质量RTK固定解

```yaml
nodes:
  - id: precision_rtk
    package: rtk_driver
    params:
      serial_port: "/dev/ttyUSB0"
      serial_baudrate: 115200
      nmea_message: "KSXT"
      output_frequency: 20
      min_rtk_quality: 3        # 仅输出固定解
      min_satellites: 12        # 至少12颗卫星
```

### 3. 网络连接 + 数据记录

```yaml
nodes:
  - id: network_rtk
    package: rtk_driver
    params:
      use_network: true
      network_host: "192.168.1.100"
      network_port: 5000
      network_protocol: "tcp"
      nmea_message: "KSXT"
      output_frequency: 20
      enable_raw_log: true      # 记录原始数据
      raw_log_path: "/tmp/rtk_debug.log"
```

### 4. 与坐标转换节点配合

```yaml
nodes:
  - id: rtk_sensor
    package: rtk_driver
    params:
      serial_port: "/dev/ttyUSB0"
      nmea_message: "KSXT"
      output_frequency: 20

  - id: coord_gateway
    package: coord_transform

  - id: path_follower
    package: track_controller

edges:
  # RTK原始数据 -> 坐标转换
  - from: rtk_sensor.rtk_fix
    to: coord_gateway.rtk_fix

  # 转换后的ENU坐标 -> 控制器
  - from: coord_gateway.pose_enu
    to: path_follower.pose_enu
```

## 支持的NMEA消息

### $KSXT（推荐）

集成消息，包含完整的定位、姿态、速度信息，适合双天线RTK。

**优点**：
- 一条消息包含所有数据
- 高精度时间戳（yyyymmddhhmmss.ss）
- 包含NEU坐标和速度
- 双天线航向信息

**示例**：
```
$KSXT,20231215120530.00,116.12345678,39.98765432,123.456,
1.234,5.678,90.123,1.234,0.567,3,3,12,10,
1234.567,5678.901,23.456,0.123,0.456,0.789*5C
```

### $GPGGA + $GPRMC

标准NMEA组合，适合单天线GPS。

**优点**：
- 标准协议，兼容性好
- 广泛支持

**缺点**：
- 需要两条消息合成
- 航向依赖速度推算

### $GPGGA + $GPTHS

位置 + 独立航向，适合双天线RTK。

**优点**：
- 独立的高精度航向

## 硬件连接

### USB转串口（Linux）

```bash
# 查看串口设备
ls -l /dev/ttyUSB* /dev/ttyACM*

# 检查设备权限
sudo chmod 666 /dev/ttyUSB0

# 或添加用户到dialout组（推荐）
sudo usermod -a -G dialout $USER
# 注销后重新登录生效
```

### USB转串口（香橙派）

```bash
# 香橙派通常识别为ttyUSB0或ttyS0
ls -l /dev/tty*

# 测试串口数据
cat /dev/ttyUSB0

# 如果看到NMEA消息输出，说明连接正常
```

### 网络连接（以太网）

```bash
# 配置RTK设备IP（通过Web界面或串口配置）
# 确保设备和主机在同一网段

# 测试连接
ping 192.168.1.100

# 测试TCP端口
telnet 192.168.1.100 5000
```

## 故障排查

### 1. 无法打开串口

**问题**：`SerialException: Could not open port /dev/ttyUSB0`

**解决**：
```bash
# 检查设备是否存在
ls -l /dev/ttyUSB*

# 检查权限
sudo chmod 666 /dev/ttyUSB0

# 或添加到dialout组
sudo usermod -a -G dialout $USER
```

### 2. 无RTK数据输出

**问题**：节点运行但没有数据输出

**检查**：
```bash
# 查看节点日志
nodeflow logs -n rtk_driver

# 检查原始数据（启用raw_log）
tail -f /tmp/rtk_raw.log

# 确认RTK设备输出
cat /dev/ttyUSB0
```

**可能原因**：
- RTK设备未配置输出NMEA消息
- 波特率不匹配
- RTK未获得固定解（质量不满足要求）
- 卫星数量不足

### 3. RTK质量一直是FLOAT或SINGLE

**问题**：无法获得固定解（FIXED）

**检查**：
- 基站差分数据是否正常接收
- 天线位置是否有遮挡
- 双天线基线长度是否正确
- 等待时间是否足够（冷启动需5-10分钟）

**临时方案**：
```yaml
# 降低质量要求用于测试
min_rtk_quality: 2  # 允许浮点解
min_satellites: 8   # 降低卫星要求
```

### 4. 航向数据不稳定

**问题**：航向角跳变或不准确

**检查**：
- 确认使用双天线RTK（单天线无法提供稳定航向）
- 检查 `heading_quality` 字段
- 确认天线基线方向正确

**解决**：
```yaml
# 启用平滑滤波
enable_smoothing: true
smoothing_alpha: 0.3  # 增大平滑强度
```

### 5. 网络连接失败

**问题**：`Network connection failed`

**检查**：
```bash
# 测试网络连通性
ping <RTK设备IP>

# 测试端口
telnet <RTK设备IP> <端口>

# 检查防火墙
sudo ufw status
```

## 性能指标

| 指标 | 值 |
|------|-----|
| 最大输出频率 | 50 Hz |
| 串口延迟 | < 10 ms |
| 网络延迟 | < 20 ms |
| CPU占用 | < 5% |
| 内存占用 | < 50 MB |
| 定位精度 | 1-2 cm (RTK固定解) |
| 航向精度 | < 0.1° (双天线) |

## 坐标系说明

### 输出坐标系

- **位置**: WGS84经纬度（度）+ MSL海拔高度（米）
- **航向**: 数学坐标系（东=0°，逆时针为正），单位：弧度
- **速度**: ENU坐标系（东-北-天），单位：m/s

### 与其他节点配合

```
RTK Driver (WGS84) → coord_transform (转换) → 下游节点 (ENU)
```

下游节点（如 `track_controller`）使用 ENU 局部坐标系，需要通过 `coord_transform` 网关转换。

## 依赖

- Python 3.12+
- pyserial (串口通信)
- NodeFlow SDK

安装依赖：
```bash
pip install pyserial
```

## 相关文档

- [NodeFlow SDK 文档](../../sdk/doc/SDK_GETTING_STARTED.md)
- [坐标转换节点](../coord_transform/README.md)
- [RTK设备用户手册](https://www.unicorecomm.com/)

## 开发者

如需修改或扩展功能，参考：

- `nmea_parser.py` - NMEA消息解析逻辑
- `device_interface.py` - 通信接口实现
- `run.py` - 主节点逻辑

## 许可证

GPLv3
