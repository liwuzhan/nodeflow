# RTK驱动节点 - 快速开始指南

## 5分钟快速测试

### 第1步：连接RTK设备

```bash
# 1. 将RTK设备通过USB连接到电脑

# 2. 查找串口设备
ls -l /dev/ttyACM*

# 应该看到类似这样的输出：
# crw-rw---- 1 root dialout 188, 0 Jan 21 12:00 /dev/ttyUSB0

# 3. 给予权限（临时）
sudo chmod 666 /dev/ttyUSB0

# 或者添加用户到dialout组（永久，需重新登录）
sudo usermod -a -G dialout $USER
```

### 第2步：测试串口连接

```bash
# 查看原始NMEA数据
cat /dev/ttyUSB0

# 应该看到类似这样的输出：
# $KSXT,20231215120530.00,116.12345678,39.98765432,123.456,...*5C
# $GPGGA,120530.00,3959.25919,N,11607.40748,E,4,12,0.8,123.456,M,...*5C

# 按 Ctrl+C 停止
```

### 第3步：安装依赖

```bash
# 安装pyserial库
pip install pyserial

# 或使用项目requirements.txt
pip install -r requirements.txt
```

### 第4步：修改测试配置

```bash
# 编辑测试配置文件
nano examples/rtk_test.yaml

# 修改serial_port为你的设备路径（通常是 /dev/ttyUSB0）
# 如果使用香橙派，可能是 /dev/ttyS0 或 /dev/ttyUSB0
```

### 第5步：运行测试

```bash
# 运行RTK测试配置
python3 -m runtime.main examples/rtk_test.yaml

# 应该看到类似这样的输出：
# [INFO] RTK Driver Node initializing...
# [INFO] RTK Driver configured:
# [INFO]   Connection: Serial
# [INFO]   Serial: /dev/ttyUSB0 @ 115200 bps
# [INFO]   NMEA Message: KSXT
# [INFO]   Output Frequency: 20 Hz
# [INFO] Connecting to RTK device...
# [INFO] ✓ RTK device connected
# [INFO] RTK Status: FIXED | Sats: 15 | Pos: (39.98765432, 116.12345678) | Heading: 90.1° | Messages: 200
```

### 第6步：查看实时日志

打开新终端：

```bash
# 查看RTK节点日志
nodeflow logs -n rtk_sensor --follow

# 或查看所有节点日志
nodeflow logs --follow
```

### 第7步：查看原始NMEA数据

```bash
# 查看原始NMEA日志（如果启用了enable_raw_log）
tail -f /tmp/rtk_raw.log
```

### 第8步：查看轨迹图像

```bash
# 轨迹图像会实时更新（每5秒）
# 使用文件浏览器打开：
# /tmp/rtk_trajectory/trajectory_latest.png

# 或使用命令行查看（Linux桌面环境）
xdg-open /tmp/rtk_trajectory/trajectory_latest.png

# macOS
open /tmp/rtk_trajectory/trajectory_latest.png
```

## 验证检查清单

运行成功后，确认以下内容：

- [ ] RTK设备连接成功（日志显示 "✓ RTK device connected"）
- [ ] NMEA消息正常解析（日志显示消息类型：KSXT/GPGGA/GPRMC）
- [ ] RTK状态为FIXED（日志显示 "RTK Status: FIXED"）
- [ ] 卫星数量充足（>= 10颗）
- [ ] 坐标数据合理（经纬度在合理范围内）
- [ ] 航向数据稳定（双天线RTK）
- [ ] 轨迹图像正常生成

## 常见问题

### Q1: 串口权限错误

```
SerialException: [Errno 13] could not open port /dev/ttyUSB0: [Errno 13] Permission denied
```

**解决方案**：
```bash
sudo chmod 666 /dev/ttyUSB0
# 或永久解决
sudo usermod -a -G dialout $USER
# 注销后重新登录
```

### Q2: 找不到串口设备

```bash
# 检查USB设备
lsusb

# 查看内核消息
dmesg | grep tty

# 可能的设备名：
# /dev/ttyUSB0  (USB转串口)
# /dev/ttyACM0  (USB CDC设备)
# /dev/ttyS0    (板载串口)
```

### Q3: RTK状态一直是FLOAT

这是正常的，RTK需要时间收敛到固定解。

**原因**：
- 卫星信号不佳（室内、遮挡）
- 未接收到差分数据（基站未连接）
- 双天线基线未配置

**临时方案**（测试用）：
```yaml
# 修改 rtk_test.yaml
min_rtk_quality: 2  # 允许浮点解
min_satellites: 8   # 降低卫星要求
```

### Q4: 无NMEA数据输出

**检查RTK设备配置**：

某些RTK设备出厂时未启用NMEA输出，需要手动配置。

通过串口工具发送配置命令：
```bash
# 安装minicom
sudo apt install minicom

# 打开串口
minicom -D /dev/ttyUSB0 -b 115200

# 发送配置命令（根据设备型号）
KSXT 20           # 启用KSXT消息，20Hz
SAVECONFIG        # 保存配置

# 退出minicom: Ctrl+A, X
```

### Q5: 香橙派上找不到ttyUSB设备

```bash
# 香橙派可能使用不同的设备名
ls -l /dev/tty*

# 常见设备：
# /dev/ttyS0    - 板载串口
# /dev/ttyUSB0  - USB转串口
# /dev/ttyAMA0  - UART串口

# 检查USB设备
lsusb

# 如果没有驱动，安装USB串口驱动
sudo apt install linux-modules-extra-$(uname -r)
```

## 下一步

成功运行测试后，你可以：

1. **集成到现有系统**
   ```yaml
   # 在你的runtime.yaml中添加RTK节点
   - id: my_rtk
     package: rtk_driver
     params:
       serial_port: "/dev/ttyUSB0"
   ```

2. **连接到控制器**
   ```yaml
   edges:
     - from: my_rtk.rtk_fix
       to: coord_transform.rtk_fix
     - from: coord_transform.pose_enu
       to: track_controller.pose_enu
   ```

3. **调整参数优化性能**
   - 输出频率：根据控制器需求调整（10-50 Hz）
   - 质量要求：根据应用精度调整（FIXED/FLOAT）
   - 平滑滤波：如果数据跳变严重，启用滤波

4. **部署到香橙派**
   ```bash
   # 复制项目到香橙派
   scp -r nodeflow-enu-decoupled-v2 orangepi@192.168.1.100:~/

   # SSH登录香橙派
   ssh orangepi@192.168.1.100

   # 运行测试
   cd nodeflow-enu-decoupled-v2
   python3 -m runtime.main examples/rtk_test.yaml
   ```

## 性能调优

### 高频输出（50 Hz）

```yaml
params:
  output_frequency: 50
  serial_timeout: 0.1  # 减少超时时间
```

### 高精度模式

```yaml
params:
  min_rtk_quality: 3      # 仅固定解
  min_satellites: 12      # 增加卫星要求
  enable_smoothing: false # 不使用滤波（保持原始精度）
```

### 低延迟模式

```yaml
params:
  output_frequency: 20
  serial_timeout: 0.05   # 减少等待时间
```

## 获取帮助

- 📖 完整文档：[README.md](README.md)
- 📝 节点开发规范：[../../docs/节点开发规范.md](../../docs/节点开发规范.md)
- 🔧 SDK文档：[../../sdk/doc/SDK_GETTING_STARTED.md](../../sdk/doc/SDK_GETTING_STARTED.md)
- 🐛 问题反馈：GitHub Issues
