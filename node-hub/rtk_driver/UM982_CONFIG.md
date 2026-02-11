# UM982 RTK 接收机配置指南

## 硬件架构

本系统使用 **UM982 + Air700E** 组合板：

```
UM982 (GNSS接收机)          Air700E (4G模块)           PC
  COM1  <--- UART1 --->  LuatOS ROVER App  <--- USB --->  /dev/cu.usbmodem*
                           |
                           +--- NTRIP Client (差分校正)
                           +--- GNSS 解析 (libgnss)
                           +--- 看门狗 (5秒超时)
```

- UM982 通过 UART 连接到 Air700E，**不直接暴露 USB 串口**
- Air700E 负责 4G 联网、NTRIP 差分、数据转发
- PC 通过 Air700E 的 USB 复合设备间接访问 UM982

## USB 端口映射 (macOS)

Air700E 在 USB 上创建 4 个虚拟串口：

| 端口 | 设备路径 (macOS) | 用途 |
|------|------------------|------|
| 端口1 | `/dev/cu.usbmodem*11` | AT 命令口 (未启用) |
| 端口2 | `/dev/cu.usbmodem*13` | **LuatOS Lua REPL (调试/命令口)** |
| 端口3 | `/dev/cu.usbmodem*15` | 数据转发口 (二进制观测数据) |
| 端口4 | `/dev/cu.usbmodem*17` | 诊断口 (未启用) |

> Linux 下通常映射为 `/dev/ttyUSB0` ~ `/dev/ttyUSB3`，端口顺序可能不同。

## 向 UM982 发送配置命令

由于 UM982 不直接连接 USB，需要通过 Air700E 的 **Lua REPL (端口2)** 中转：

### macOS

```bash
# 1. 配置串口波特率
stty -f /dev/cu.usbmodem0000000000013 115200

# 2. 发送命令 (通过 Lua 的 uart.write 转发到 UM982)
echo 'uart.write(1, "GPRMC 0.05\r\n")' > /dev/cu.usbmodem0000000000013
echo 'uart.write(1, "GPTHS 0.05\r\n")' > /dev/cu.usbmodem0000000000013

# 3. 查看日志 (Ctrl+C 退出)
cat /dev/cu.usbmodem0000000000013
```

### Linux

```bash
stty -F /dev/ttyUSB1 115200
echo 'uart.write(1, "GPRMC 0.05\r\n")' > /dev/ttyUSB1
echo 'uart.write(1, "GPTHS 0.05\r\n")' > /dev/ttyUSB1
```

### Python

```python
import serial, time

ser = serial.Serial('/dev/cu.usbmodem0000000000013', 115200, timeout=0.5)
time.sleep(1)

ser.write(b'uart.write(1, "GPRMC 0.05\\r\\n")\r\n')
time.sleep(0.3)
ser.write(b'uart.write(1, "GPTHS 0.05\\r\\n")\r\n')
time.sleep(0.3)

ser.close()
```

## UM982 常用命令

### NMEA 输出配置

命令格式：`<消息类型> <周期(秒)>`

| 命令 | 说明 | 输出示例 |
|------|------|---------|
| `GPRMC 0.05` | RMC 定位信息 20Hz | `$GNRMC,090845.00,A,2851.19051272,N,12000.36807251,E,0.008,58.7,100226,5.5,W,R,S*6A` |
| `GPTHS 0.05` | 航向信息 20Hz | `$GPTHS,123.45,A*XX` |
| `GPGGA 0.05` | GGA 定位信息 20Hz | `$GNGGA,090845.00,2851.190512,N,12000.368072,E,4,47,0.4,100.54,M,9.28,M,1.0,3029*XX` |
| `KSXT 0.05` | 集成定位定向 20Hz | `$KSXT,20231215120530.00,lon,lat,alt,...*XX` |

常用频率对照：

| 频率 | 周期参数 |
|------|---------|
| 1 Hz | `1` |
| 5 Hz | `0.2` |
| 10 Hz | `0.1` |
| 20 Hz | `0.05` |
| 50 Hz | `0.02` |

### 查询与管理命令

| 命令 | 说明 |
|------|------|
| `VERSION` | 查询固件版本 |
| `LOG` | 查询当前已配置的所有输出 |
| `SAVECONFIG` | 保存当前配置到 NVM (掉电不丢失) |
| `UNLOG <类型>` | 停止特定消息输出，如 `UNLOG GPRMC` |

### 20Hz GPRMC + GPTHS 典型配置

```
uart.write(1, "GPRMC 0.05\r\n")
uart.write(1, "GPTHS 0.05\r\n")
uart.write(1, "SAVECONFIG\r\n")
```

## NMEA 报文格式说明

### $GNRMC (推荐最小定位信息)

```
$GNRMC,090845.00,A,2851.19051272,N,12000.36807251,E,0.008,58.7,100226,5.5,W,R,S*6A
       |          | |              |                 |     |    |       |    | |
       时间UTC    状态 纬度ddmm.mmm  经度dddmm.mmm    速度  航向  日期    磁偏 模式
                  A=有效             N/S E/W          (节) (度)  ddmmyy
```

- 状态：`A` = 有效，`V` = 无效
- 纬度格式：`ddmm.mmmmm`，dd=度，mm.mmmmm=分
- 经度格式：`dddmm.mmmmm`，ddd=度，mm.mmmmm=分
- 模式指示：`R` = RTK 固定解，`F` = RTK 浮点解，`A` = 自主定位，`D` = 差分

### $GPTHS (航向信息)

```
$GPTHS,123.45,A*XX
       |      |
       航向(度) 状态
       北=0    A=有效 V=无效
       顺时针
```

- 需要**双天线**才能输出有效航向
- 单天线时输出 `$GPTHS,,V*0E`（航向为空，状态为 V）

### $GNGGA (全球定位固定数据)

```
$GNGGA,090845.00,2851.19051272,N,12000.36807251,E,4,47,0.4,100.5487,M,9.2851,M,1.0,3029*65
       |          |              |                 | |  |   |         |        差分龄期 基站ID
       时间       纬度            经度              质量 星数 HDOP 海拔(m)     大地水准面差
```

质量指示：`0`=无效, `1`=单点, `2`=差分, `4`=RTK固定, `5`=RTK浮点

## 重要注意事项

### 看门狗机制

Air700E 固件内置看门狗，**5 秒超时**，通过检测 GGA 和 RMC 报文判断设备是否正常：

- **GGA 和 RMC 必须同时存在**，缺少任一将触发看门狗重启
- 重启后 UM982 配置恢复为 Air700E 的默认启动配置

### 禁止操作

| 命令 | 后果 |
|------|------|
| `UNLOGALL` | 停掉所有输出 (含 GGA/RMC) → 触发看门狗 5 秒后重启 |
| `FRESET` | 恢复出厂设置，清除所有 NVM 配置 → 触发看门狗重启 |
| `UNLOG GPGGA` | 停掉 GGA → 触发看门狗重启 |
| `UNLOG GPRMC` | 停掉 RMC → 触发看门狗重启 |

> 只能**添加**或**修改频率**，不能停掉 GGA/RMC 输出。

### 安全操作

```bash
# 正确：添加或修改输出频率
echo 'uart.write(1, "GPRMC 0.05\r\n")' > /dev/cu.usbmodem0000000000013
echo 'uart.write(1, "GPTHS 0.05\r\n")' > /dev/cu.usbmodem0000000000013

# 正确：停掉非关键输出
echo 'uart.write(1, "UNLOG KSXT\r\n")' > /dev/cu.usbmodem0000000000013

# 错误：不要执行以下命令！
# echo 'uart.write(1, "UNLOGALL\r\n")' > ...     ← 会触发重启
# echo 'uart.write(1, "FRESET\r\n")' > ...        ← 会触发重启
# echo 'uart.write(1, "UNLOG GPGGA\r\n")' > ...   ← 会触发重启
```

## RTK 质量等级

| UM982 质量码 | GGA 质量码 | 说明 | 精度 |
|-------------|-----------|------|------|
| 0 | 0 | 无效定位 | - |
| 1 | 1 | 单点定位 | ~2m |
| 2 | 5 | RTK 浮点解 | ~0.4m |
| 3 | 4 | RTK 固定解 | ~0.02m |

## rtk_driver 节点配置示例

在 NodeFlow 的 YAML 配置中使用本驱动：

```yaml
- id: rtk_sensor
  package: rtk_driver
  params:
    serial_port: "/dev/ttyUSB0"       # Linux: 数据转发口
    serial_baudrate: 115200
    nmea_message: "GPRMC"             # 主消息类型
    output_frequency: 20              # 20Hz
    min_rtk_quality: 4                # 至少 RTK 固定解 (GGA quality=4)
    min_satellites: 10
    enable_raw_log: true              # 调试时可开启原始日志
    raw_log_path: "/tmp/rtk_raw.log"
```

## 故障排查

### 设备无输出

1. 检查 USB 连接：`ls /dev/cu.usbmodem*` (macOS) 或 `ls /dev/ttyUSB*` (Linux)
2. 通过 Lua REPL 查看日志：`cat /dev/cu.usbmodem*13`
3. 查看 GNSS 状态：日志中出现 `I/gnss Fixed XX` 表示已定位（XX 为卫星数）
4. 查看 NTRIP 状态：日志中 `I/user.ntrip recv:` 表示正在接收差分数据

### 航向 (GPTHS) 显示无效

- `$GPTHS,,V*0E` 表示航向无效
- 确认使用双天线设备 (UMD982)，单天线 UM982 无法输出航向
- 检查两根天线间距是否足够 (建议 > 0.5m)
- 等待 RTK 固定解后航向才会有效

### 设备频繁重启

- 检查是否误发了 `UNLOGALL`、`FRESET` 或停掉了 GGA/RMC
- 设备重启后会恢复 Air700E 默认配置，需要重新发送自定义命令
- 看门狗超时为 5 秒，确保 GGA 和 RMC 不中断

## 校准流程

本系统需要校准两部分：天线安装偏移（rtk_driver）和电机/履带执行偏差（pwm_driver）。

### 校准顺序（重要）

必须按以下顺序进行，因为后续步骤依赖前序校准结果：

1. **天线位置测量** — 卷尺量，不需要开机
2. **航向偏移标定** — 需要 RTK 固定解，直线行驶法
3. **电机直线标定** — 需要开阔场地，遥控直线走
4. **旋转速率标定** — 原地旋转 360° 计时

### 步骤 1：天线位置测量

用卷尺测量定位天线（主天线）到车体几何中心的偏移：

- `antenna_offset_x`：前向偏移（米）。天线在车体前方为正值
- `antenna_offset_y`：右向偏移（米）。天线在车体右侧为正值

```yaml
# rtk_driver 参数示例
antenna_offset_x: 0.3   # 天线在车体中心前方 30cm
antenna_offset_y: 0.0   # 天线在车体中线上
```

### 步骤 2：航向偏移标定

双天线基线方向与车体前进方向不一致时需要校准（例如天线横装）。

**方法：直线行驶法**

1. 确保 RTK 固定解
2. 从 A 点直行到 B 点（距离 20m 以上）
3. 用 GPS 轨迹计算实际行驶方向（A→B 方位角）
4. 读取 RTK 输出的航向值
5. `heading_offset_deg` = RTK航向 - 实际行驶方向

```yaml
# rtk_driver 参数示例
heading_offset_deg: 90.0   # 双天线横装，基线朝右
```

> 典型值：纵装 = 0°，横装朝右 = 90°，横装朝左 = -90°

### 步骤 3：电机直线标定

补偿左右电机/履带差异导致的直线行驶跑偏。

**方法：**

1. 在开阔平坦场地，发送直线命令：`v=0.3 m/s, w=0`
2. 观察 20m 行驶后的侧偏量 d（米）
3. 估算角速度偏置：`angular_velocity_bias ≈ d × v / (L²)`，其中 L 为行驶距离
4. 车辆右偏设正值，左偏设负值

```yaml
# pwm_driver 参数示例
angular_velocity_bias: 0.01   # 补偿轻微右偏
```

如果偏差较大，也可以调整左右轮速度缩放：

```yaml
left_speed_scale: 1.0
right_speed_scale: 0.95   # 右轮偏快，缩小右轮输出
```

### 步骤 4：旋转速率标定

校正 `wheel_base` 参数使旋转角速度准确。

**方法：**

1. 发送原地旋转命令：`v=0, w=0.3 rad/s`
2. 计时完成 360° 所需时间 T（秒）
3. 理论时间：T_expected = 2π / 0.3 ≈ 20.9s
4. 校正：`wheel_base_new = wheel_base × T_expected / T`

```yaml
# pwm_driver 参数示例
wheel_base: 0.52   # 校正后的实际轮距
```

### 校准参数汇总

| 参数 | 节点 | 默认值 | 说明 |
|------|------|--------|------|
| `antenna_offset_x` | rtk_driver | 0.0 | 天线前向偏移（米） |
| `antenna_offset_y` | rtk_driver | 0.0 | 天线右向偏移（米） |
| `heading_offset_deg` | rtk_driver | 0.0 | 航向安装偏移（度） |
| `left_speed_scale` | pwm_driver | 1.0 | 左轮速度缩放 |
| `right_speed_scale` | pwm_driver | 1.0 | 右轮速度缩放 |
| `angular_velocity_bias` | pwm_driver | 0.0 | 角速度偏置（rad/s） |
| `pwm_deadzone_ns` | pwm_driver | 0 | ESC死区宽度（ns，单侧） |
