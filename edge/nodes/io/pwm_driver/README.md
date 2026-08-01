# PWM Driver Node - 香橙派5 Ultra电机驱动

## 概述

PWM驱动节点用于香橙派5 Ultra控制双轮差速机器人的电机。节点接收速度命令（线速度+角速度），计算左右轮速度，并通过硬件PWM输出控制电机驱动器。

## 硬件配置

### 香橙派5 Ultra GPIO接口

| 功能 | GPIO引脚 | 物理引脚 | PWM通道 | wPi序号 |
|------|---------|---------|---------|---------|
| 左轮PWM | GPIO3_A5 | 33 | PWM14_M0 | 22 |
| 右轮PWM | GPIO3_B0 | 35 | PWM15_M0 | 23 |

### 接线示意

```
香橙派5 Ultra          电机驱动器
├─ 引脚33 (PWM14) ──→ 左轮PWM输入
├─ 引脚35 (PWM15) ──→ 右轮PWM输入
├─ GND ─────────────→ GND (共地)
└─ 5V (可选) ───────→ 逻辑电源
```

## 功能特性

✅ **双轮差速控制** - 支持前进/后退/转向
✅ **硬件PWM** - 50Hz PWM输出（适合伺服电机）
✅ **运动学计算** - 自动转换线速度+角速度为轮速
✅ **安全机制** - 命令超时保护、紧急停止
✅ **PWM映射** - 可配置中位值、死区、最大变化量
✅ **实时监测** - 输出PWM状态供上层监控
✅ **演习模式** - 不输出PWM，仅计算和记录

## 依赖安装

### 1. 安装 wiringOP 库

在香橙派5 Ultra上执行：

```bash
# 安装 wiringOP (香橙派官方GPIO库)
sudo pip3 install wiringpi-opi5

# 或者从源码安装（推荐）
git clone https://github.com/orangepi-xunlong/wiringOP.git
cd wiringOP
./build clean
./build
```

### 2. 启用PWM引脚

使用 `gpio` 命令设置引脚为PWM模式：

```bash
# 设置左轮PWM (wPi 22)
gpio mode 22 pwm

# 设置右轮PWM (wPi 23)
gpio mode 23 pwm

# 验证引脚状态
gpio readall
```

## 使用方法

### 配置示例

```yaml
nodes:
  - id: motor_pwm
    package: pwm_driver
    description: "电机PWM控制"
    params:
      # PWM硬件配置
      pwm_frequency: 50.0          # 50Hz PWM
      pwm_range: 1024              # 0-1023
      left_wheel_pin: 22           # wPi序号
      right_wheel_pin: 23

      # 车辆参数
      wheel_base: 0.5              # 履带宽度 0.5m
      max_linear_speed: 2.0        # 最大线速度 2m/s
      max_angular_speed: 1.0       # 最大角速度 1rad/s

      # PWM映射
      neutral_pwm: 512             # 中位值 (停止)
      max_pwm_delta: 400           # 最大变化 (±400)
      min_pwm_threshold: 50        # 死区阈值

      # 安全参数
      enable_safety_check: true
      command_timeout: 0.5         # 0.5秒超时
      emergency_stop: false

      # 调试
      enable_verbose_log: false
      dry_run_mode: false          # 实际输出PWM

edges:
  # 轨迹控制器 → PWM驱动
  - from: track_controller.velocity_cmd
    to: motor_pwm.velocity_cmd
    description: "速度命令"

  # PWM状态 → 监测 (可选)
  - from: motor_pwm.pwm_status
    to: logger.input1
    description: "PWM监测"
```

### 完整系统配置

创建 `examples/real_robot_control.yaml`：

```yaml
nodes:
  # RTK GPS
  - id: rtk_sensor
    package: rtk_driver
    params:
      serial_port: "/dev/ttyACM3"
      # ...

  # RTK 滤波
  - id: rtk_filter
    package: rtk_filter

  # 坐标转换
  - id: coord_transform
    package: coord_transform

  # 路径规划
  - id: global_coverage
    package: global_coverage

  # 前瞻点选择
  - id: waypoint_selector
    package: waypoint_selector

  # 轨迹控制
  - id: track_controller
    package: track_controller

  # PWM驱动 (新增)
  - id: motor_pwm
    package: pwm_driver
    params:
      pwm_frequency: 50.0
      left_wheel_pin: 22
      right_wheel_pin: 23
      wheel_base: 0.5
      max_linear_speed: 2.0
      max_angular_speed: 1.0

edges:
  # RTK数据流
  - from: rtk_sensor.rtk_fix
    to: rtk_filter.rtk_fix

  - from: rtk_filter.filtered_rtk
    to: coord_transform.rtk_fix

  # 路径规划流程
  - from: coord_transform.task_enu
    to: global_coverage.task_enu

  - from: global_coverage.global_path
    to: waypoint_selector.global_path

  - from: coord_transform.pose_enu
    to: waypoint_selector.pose_enu

  - from: waypoint_selector.next_point
    to: track_controller.next_point

  - from: coord_transform.pose_enu
    to: track_controller.pose_enu

  # 电机控制 (新增)
  - from: track_controller.velocity_cmd
    to: motor_pwm.velocity_cmd
    description: "速度命令 → PWM驱动"
```

## 运动学原理

### 差速驱动公式

对于双轮差速机器人：

```
v_left = v_linear - (wheel_base/2) * w_angular
v_right = v_linear + (wheel_base/2) * w_angular
```

其中：
- `v_linear`: 线速度 (m/s，正向前进)
- `w_angular`: 角速度 (rad/s，正向逆时针)
- `wheel_base`: 履带宽度 (m)

### PWM映射

轮速到PWM的映射关系：

```
PWM = neutral + (speed / max_speed) * max_delta
```

示例（neutral=512，max_delta=400）：
- `speed = 0 m/s` → PWM = 512（停止）
- `speed = 2 m/s` → PWM = 912（全速前进）
- `speed = -2 m/s` → PWM = 112（全速后退）

## 参数说明

### PWM硬件配置

| 参数 | 类型 | 默认值 | 说明 |
|-----|------|--------|------|
| pwm_frequency | float | 50.0 | PWM频率 (Hz) |
| pwm_range | int | 1024 | PWM范围 (0-1023) |
| left_wheel_pin | int | 22 | 左轮引脚 (wPi) |
| right_wheel_pin | int | 23 | 右轮引脚 (wPi) |

### 车辆参数

| 参数 | 类型 | 默认值 | 说明 |
|-----|------|--------|------|
| wheel_base | float | 0.5 | 履带宽度 (m) |
| max_linear_speed | float | 2.0 | 最大线速度 (m/s) |
| max_angular_speed | float | 1.0 | 最大角速度 (rad/s) |

### PWM映射参数

| 参数 | 类型 | 默认值 | 说明 |
|-----|------|--------|------|
| neutral_pwm | int | 512 | 中位PWM值 |
| max_pwm_delta | int | 400 | 最大PWM变化量 |
| min_pwm_threshold | int | 50 | 最小PWM阈值（死区） |

### 安全参数

| 参数 | 类型 | 默认值 | 说明 |
|-----|------|--------|------|
| enable_safety_check | bool | true | 启用速度限制 |
| emergency_stop | bool | false | 紧急停止标志 |
| command_timeout | float | 0.5 | 命令超时 (s) |

### 调试参数

| 参数 | 类型 | 默认值 | 说明 |
|-----|------|--------|------|
| enable_verbose_log | bool | false | 详细日志 |
| dry_run_mode | bool | false | 演习模式（不输出PWM） |

## 测试方法

### 1. 演习模式测试（PC上）

在开发PC上测试（不需要实际硬件）：

```yaml
params:
  dry_run_mode: true          # 演习模式
  enable_verbose_log: true    # 详细日志
```

运行：
```bash
python3 -m runtime.main examples/pwm_test.yaml
```

### 2. 硬件测试（香橙派）

创建简单测试配置 `examples/pwm_hardware_test.yaml`：

```yaml
nodes:
  - id: test_input
    package: sim_input
    params:
      default_linear_velocity: 0.5   # 0.5 m/s
      default_angular_velocity: 0.0  # 直行

  - id: motor_pwm
    package: pwm_driver
    params:
      dry_run_mode: false
      enable_verbose_log: true

edges:
  - from: test_input.velocity_cmd
    to: motor_pwm.velocity_cmd
```

运行：
```bash
# 在香橙派上
python3 -m runtime.main examples/pwm_hardware_test.yaml
```

### 3. 单元测试

测试PWM计算逻辑：

```bash
cd node-hub/pwm_driver
python3 -m pytest test_atom.py -v
```

## 故障排查

### 问题1: wiringOP未找到

```
ModuleNotFoundError: No module named 'wiringpi'
```

**解决方案**：
```bash
sudo pip3 install wiringpi-opi5
```

### 问题2: GPIO初始化失败

```
ERROR: Failed to initialize wiringOP
```

**解决方案**：
```bash
# 检查权限
sudo usermod -aG gpio $USER
newgrp gpio

# 或使用sudo运行
sudo python3 -m runtime.main config.yaml
```

### 问题3: PWM引脚未配置

```
WARNING: GPIO not available, PWM not written
```

**解决方案**：
```bash
# 设置PWM模式
gpio mode 22 pwm
gpio mode 23 pwm

# 验证
gpio readall | grep -E "22|23"
```

### 问题4: 电机不转

**检查清单**：
1. ✅ PWM引脚连接正确
2. ✅ 电机驱动器供电正常
3. ✅ 共地连接
4. ✅ PWM频率匹配驱动器要求
5. ✅ 中位PWM值正确（通常50%）
6. ✅ 速度命令非零

### 问题5: 命令超时

```
WARNING: Command timeout (0.5s), motors stopped
```

**原因**：速度命令端口未接收到数据

**解决方案**：
- 检查数据连接配置
- 确认上游节点正常运行
- 增加 `command_timeout` 参数

## 高级功能

### 自定义PWM映射

不同电机驱动器可能需要不同的PWM范围：

```yaml
params:
  # 例如：驱动器要求 1000-2000us (50Hz)
  pwm_range: 20000        # 20ms = 50Hz
  neutral_pwm: 15000      # 1.5ms
  max_pwm_delta: 5000     # ±0.5ms
```

### 非对称速度限制

如果左右轮最大速度不同：

```yaml
# 目前不支持，需修改 atom.py 添加独立轮速限制
```

### 自适应死区

根据负载自动调整死区：

```yaml
# 目前不支持，可在atom.py中添加
```

## 性能指标

- **更新频率**: 100Hz (10ms周期)
- **PWM频率**: 50Hz (可配置)
- **延迟**: < 20ms (从命令到PWM输出)
- **精度**: ±1 PWM单位 (0.1% @ 1024范围)

## 相关文档

- [NodeFlow SDK文档](../../sdk/doc/)
- [香橙派5 Ultra官方文档](http://www.orangepi.cn/)
- [wiringOP库文档](https://github.com/orangepi-xunlong/wiringOP)
- [差速驱动运动学](https://en.wikipedia.org/wiki/Differential_wheeled_robot)

## 许可证

MIT License
