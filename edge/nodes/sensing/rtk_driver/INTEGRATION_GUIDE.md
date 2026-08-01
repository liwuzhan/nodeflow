# RTK驱动节点集成指南

本指南说明如何将RTK驱动节点集成到您的系统中。

## 文件结构

```
node-hub/rtk_driver/
├── node.yaml              # 节点清单和参数定义
├── run.py                 # 节点主程序
├── nmea_parser.py         # NMEA消息解析器（库）
├── device_interface.py    # 串口/网络通信接口（库）
├── test_serial.py         # 串口连接测试工具
├── README.md              # 完整文档
├── QUICKSTART.md          # 快速开始指南
└── INTEGRATION_GUIDE.md   # 本文件
```

## 模块说明

### 1. node.yaml - 节点清单

定义了RTK驱动节点的接口、参数和元数据。包含：

- **输出端口**: `rtk_fix` (sensor.rtk类型)
- **15个可配置参数**: 连接、消息、质量控制等
- **缓冲区配置**: 1MB (适合20Hz持续输出约50秒)

### 2. nmea_parser.py - NMEA消息解析库

支持的NMEA消息类型：

| 消息 | 格式 | 说明 |
|------|------|------|
| $KSXT | 集成消息 | 完整的位置、姿态、速度数据（推荐） |
| $GPGGA | 标准位置 | GPS固定数据（配合$GPRMC或$GPTHS） |
| $GPRMC | 标准推荐 | 最小定位信息 |
| $GPTHS | 标准航向 | 航向信息（双天线） |

**核心功能**：
- 校验和验证
- 坐标格式转换（NMEA -> 十进制度数）
- 时间戳解析
- 航向坐标系转换（北向 -> 数学坐标系）

### 3. device_interface.py - 通信接口库

支持三种通信方式：

| 接口 | 应用场景 | 延迟 |
|------|----------|------|
| SerialInterface | USB/UART直连（推荐） | < 10ms |
| TCPInterface | 网络连接（以太网/WiFi） | < 20ms |
| UDPInterface | 网络单向传输 | < 20ms |

**自动选择**：
```python
device = create_interface(config)  # 根据config自动选择接口
```

### 4. run.py - 节点主程序

完整的RTK驱动节点实现，包含：

- **生命周期**: setup() -> loop() -> cleanup()
- **数据处理**: 解析、验证、平滑、输出
- **错误处理**: 自动重试、日志记录
- **性能监控**: 消息计数、状态输出

## 集成步骤

### 步骤1：验证硬件连接

```bash
# 测试串口连接（最关键的一步）
cd node-hub/rtk_driver
python3 test_serial.py /dev/ttyUSB0 115200

# 应该看到原始NMEA数据和统计信息
```

### 步骤2：修改系统配置

在您的 `runtime.yaml` 中添加RTK节点：

```yaml
nodes:
  - id: rtk_gps
    package: rtk_driver
    params:
      serial_port: "/dev/ttyUSB0"      # 根据实际修改
      serial_baudrate: 115200
      nmea_message: "KSXT"
      output_frequency: 20
      min_rtk_quality: 3                # 仅固定解
      min_satellites: 10
```

### 步骤3：连接到下游节点

根据您的系统需求，将RTK输出连接到相应的处理节点：

**方案A：直接连接到坐标转换（推荐）**
```yaml
edges:
  - from: rtk_gps.rtk_fix
    to: coord_transform.rtk_fix
```

**方案B：先经过滤波器**
```yaml
edges:
  - from: rtk_gps.rtk_fix
    to: rtk_filter.rtk_fix              # 数据平滑
  - from: rtk_filter.filtered_rtk
    to: coord_transform.rtk_fix
```

**方案C：直接用于可视化调试**
```yaml
edges:
  - from: rtk_gps.rtk_fix
    to: trajectory_viz.rtk_data         # 轨迹记录
```

### 步骤4：运行和测试

```bash
# 运行完整系统
python3 -m runtime.main runtime.yaml

# 在新终端查看日志
nodeflow logs -n rtk_gps --follow

# 验证RTK状态
# 应该看到: "RTK Status: FIXED | Sats: 15 | Pos: (...) | Heading: 90.1° | Messages: 200"
```

## 常见集成场景

### 场景1：农业机器人路径规划

```yaml
nodes:
  - id: rtk_sensor
    package: rtk_driver
    params:
      serial_port: "/dev/ttyUSB0"
      output_frequency: 10              # 降低频率节省CPU
      min_rtk_quality: 2                # 允许浮点解加快启动

  - id: coord_gateway
    package: coord_transform

  - id: path_planner
    package: global_coverage

  - id: waypoint_selector
    package: waypoint_selector

  - id: controller
    package: track_controller

  - id: executor
    package: sim_input

edges:
  - from: rtk_sensor.rtk_fix
    to: coord_gateway.rtk_fix
  - from: coord_gateway.pose_enu
    to: path_planner.current_pose
  - from: path_planner.waypoints
    to: waypoint_selector.path
  - from: coord_gateway.pose_enu
    to: waypoint_selector.current_pose
  - from: waypoint_selector.next_point
    to: controller.target_point
  - from: controller.velocity_cmd
    to: executor.cmd
```

### 场景2：实时轨迹监控

```yaml
nodes:
  - id: rtk_sensor
    package: rtk_driver
    params:
      enable_raw_log: true              # 记录原始数据用于后处理
      raw_log_path: "/data/rtk_log.txt"

  - id: trajectory_recorder
    package: trajectory_viz
    params:
      output_dir: "/data/trajectories"
      update_interval: 1.0              # 每秒更新一次

edges:
  - from: rtk_sensor.rtk_fix
    to: trajectory_recorder.pose
```

### 场景3：多传感器融合

```yaml
nodes:
  - id: rtk_sensor
    package: rtk_driver

  - id: imu_sensor
    package: imu_driver              # 需要自己实现

  - id: sensor_fusion
    package: sensor_fusion_node       # 需要自己实现
    params:
      fusion_algorithm: "EKF"

edges:
  - from: rtk_sensor.rtk_fix
    to: sensor_fusion.rtk_input
  - from: imu_sensor.imu_data
    to: sensor_fusion.imu_input
  - from: sensor_fusion.fused_state
    to: controller.state
```

## 参数调优指南

### 根据应用场景调整参数

**高精度应用（测量、制图）**
```yaml
params:
  output_frequency: 20              # 高频输出
  min_rtk_quality: 3                # 仅接受固定解
  min_satellites: 12                # 严格卫星要求
  enable_smoothing: false           # 不平滑（保持原始精度）
```

**低延迟应用（实时控制）**
```yaml
params:
  output_frequency: 50              # 最高频率
  serial_timeout: 0.05              # 减少等待时间
  enable_smoothing: false           # 不引入延迟
```

**抗干扰应用（环境恶劣）**
```yaml
params:
  output_frequency: 5               # 降低频率
  enable_smoothing: true            # 启用平滑滤波
  smoothing_alpha: 0.5              # 强滤波
  min_satellites: 15                # 严格卫星要求
```

### 性能调优检查清单

- [ ] 输出频率与控制器循环周期匹配（通常20Hz）
- [ ] 串口波特率设置正确（通常115200）
- [ ] 使用KSXT消息（相比GPGGA+GPRMC组合更高效）
- [ ] 根据GPS信号质量调整质量要求
- [ ] 对于运动平台启用平滑滤波

## 故障排查清单

### 连接问题

```bash
# 检查设备
ls -l /dev/ttyUSB*

# 测试连接
python3 test_serial.py /dev/ttyUSB0 115200

# 查看原始数据
cat /dev/ttyUSB0
```

### 数据问题

```bash
# 查看RTK状态
nodeflow logs -n rtk_gps | grep "RTK Status"

# 检查原始日志
tail -f /tmp/rtk_raw.log

# 查看消息统计
nodeflow logs -n rtk_gps | grep "Total messages"
```

### 性能问题

```bash
# 监控CPU/内存
htop  # 按P排序CPU，按M排序内存

# 查看节点延迟
nodeflow logs -n rtk_gps | grep "time"

# 检查消息处理速度
nodeflow logs -n rtk_gps | grep "messages processed"
```

## API参考

### RTK输出数据格式

```python
{
    'timestamp': float,              # Unix时间戳
    'lat': float,                    # 纬度（度）
    'lon': float,                    # 经度（度）
    'alt': float,                    # 海拔（米）
    'heading': float,                # 航向（弧度，数学坐标系）
    'rtk_status': str,               # 状态字符串: INVALID/SINGLE/FLOAT/FIXED
    'rtk_quality': int,              # 质量代码: 0/1/2/3
    'num_satellites': int,           # 卫星数量

    # 可选字段
    'ground_speed': float,           # 地面速度（m/s）
    'vel_east': float,               # 东向速度
    'vel_north': float,              # 北向速度
    'vel_up': float,                 # 天向速度
    'pitch': float,                  # 俯仰角（弧度）
    'roll': float,                   # 横滚角（弧度）
    'hdop': float,                   # 水平精度因子
    'heading_quality': int,          # 航向质量
    'num_satellites_heading': int    # 航向卫星数
}
```

### 在自定义节点中使用

```python
from edge.sdk.nodeflow_sdk import NodeFlowSDK

sdk = NodeFlowSDK()

# 创建输入端口
rtk_input = sdk.create_input_port("rtk_input")

# 在循环中读取
def on_rtk_data(data):
    lat = data['lat']
    lon = data['lon']
    rtk_status = data['rtk_status']

    if rtk_status == 'FIXED':
        # RTK固定解，使用数据
        process_gps_data(lat, lon)

rtk_input.on_data(on_rtk_data)
```

## 与不同版本NodeFlow的兼容性

本RTK驱动节点设计用于：
- **NodeFlow ENU Decoupled V2** (当前版本)
- **Python 3.12+**
- **Linux/macOS/Windows** (任何支持pyserial的平台)

## 下一步

1. ✅ **立即开始**: 参考 [QUICKSTART.md](QUICKSTART.md) 进行5分钟快速测试
2. 📖 **深入学习**: 查看 [README.md](README.md) 了解所有功能
3. 🔧 **开发自定义节点**: 基于RTK输出开发你的应用
4. 🚀 **部署到生产**: 按照本指南集成到完整系统
5. 📊 **性能优化**: 参考参数调优指南优化你的应用

## 获取支持

- 📧 问题反馈: GitHub Issues
- 💬 讨论: GitHub Discussions
- 📚 文档: [完整RTK文档](README.md)
- 🔬 源码: [node-hub/rtk_driver/](.)
