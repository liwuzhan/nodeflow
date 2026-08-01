# PWM驱动节点 - 快速开始

## 5分钟快速开始

### 前置条件

- ✅ 香橙派5 Ultra / 树莓派等Linux单板
- ✅ Python 3.8+
- ✅ wiringOP库已安装

### 1. 安装依赖

```bash
# 安装GPIO库
sudo pip3 install wiringpi-opi5

# 验证安装
python3 -c "import wiringpi; print('OK')"
```

### 2. 配置PWM引脚

```bash
# 启用PWM模式（需要先设置）
gpio mode 22 pwm    # 左轮
gpio mode 23 pwm    # 右轮

# 验证
gpio readall | grep PWM
```

### 3. 最小化配置

创建 `test_pwm.yaml`：

```yaml
nodes:
  # 速度命令输入
  - id: test_input
    package: sim_input
    params:
      default_linear_velocity: 1.0   # 前进1m/s
      default_angular_velocity: 0.0  # 直行

  # PWM输出
  - id: motor_pwm
    package: pwm_driver
    params:
      pwm_frequency: 50.0
      left_wheel_pin: 22
      right_wheel_pin: 23
      wheel_base: 0.5
      max_linear_speed: 2.0
      dry_run_mode: false

edges:
  - from: test_input.velocity_cmd
    to: motor_pwm.velocity_cmd
```

### 4. 运行

```bash
# 演习模式（先测试，不输出PWM）
sed -i 's/dry_run_mode: false/dry_run_mode: true/' test_pwm.yaml
python3 -m runtime.main test_pwm.yaml

# 确认无错误后，启用实际输出
sed -i 's/dry_run_mode: true/dry_run_mode: false/' test_pwm.yaml
python3 -m runtime.main test_pwm.yaml
```

## 常见配置

### 配置1: 简单前进

```yaml
motor_pwm:
  params:
    wheel_base: 0.5
    max_linear_speed: 2.0
    max_angular_speed: 1.0
```

PWM值计算：
- 停止: PWM=512 (中位)
- 前进1m/s: PWM≈712 (中位+400/2)
- 前进2m/s: PWM≈912 (中位+400)

### 配置2: 转向控制

```yaml
track_controller:
  params:
    heading_p_gain: 2.0        # 转向增益
    max_angular_velocity: 1.0  # 最大转速

motor_pwm:
  params:
    wheel_base: 0.5            # 履带宽度必须准确
```

示例速度命令：
```python
velocity_cmd = {
    'linear_velocity': 1.0,    # 前进1m/s
    'angular_velocity': 0.5    # 同时逆时针转，半径约2m
}
```

### 配置3: 安全配置

```yaml
motor_pwm:
  params:
    command_timeout: 0.5       # 0.5s无命令则停止
    enable_safety_check: true  # 速度限制
    min_pwm_threshold: 50      # 死区
```

## 参数调试

### 问题: 电机不转

```yaml
# 步骤1: 验证PWM值
enable_verbose_log: true
# 查看日志中PWM值是否变化

# 步骤2: 检查中位值
neutral_pwm: 512              # 通常是 pwm_range/2
# 不同驱动器可能不同，尝试 500-520

# 步骤3: 调整最大变化
max_pwm_delta: 400            # 范围 200-500
```

### 问题: 转向不准

```yaml
# 调整履带宽度
wheel_base: 0.5               # 测量实际宽度

# 调整转向增益
heading_p_gain: 2.0           # 值越大转向越敏感

# 调整最大角速度
max_angular_speed: 1.0        # 限制最大转速
```

### 问题: 速度响应慢

```yaml
# 减少滤波延迟
rtk_filter:
  params:
    alpha_pos: 0.3            # 增大系数

# 增加PWM频率（如驱动器支持）
pwm_frequency: 100.0          # 从50Hz增至100Hz
```

## 测试方案

### 方案A: 直线运动测试

```bash
# 设置前进1m/s
# 运行30秒观察轨迹

# 预期：
# ✓ PWM左=右 (直线)
# ✓ 轨迹是直线
# ✓ 距离约30m (如果速度准确)
```

### 方案B: 原地旋转测试

```bash
# 设置线速度=0，角速度=1.0rad/s
# 运行10秒

# 预期：
# ✓ PWM差值最大 (左≠右)
# ✓ 电机声音不同
# ✓ 轨迹是圆形
```

### 方案C: 复杂运动测试

```bash
# 依次测试：
# 1. 前进 (v=1.0, w=0)
# 2. 左转 (v=1.0, w=0.5)
# 3. 停止 (v=0, w=0)
# 4. 右转 (v=1.0, w=-0.5)
# 5. 后退 (v=-1.0, w=0)
```

## 监控和调试

### 查看PWM输出

```bash
# 查看详细日志
tail -f /tmp/nodeflow_logs/motor_pwm.jsonl | grep "pwm"

# 输出示例：
# {
#   "left_pwm": 712,
#   "right_pwm": 712,
#   "linear_velocity": 1.0,
#   "angular_velocity": 0.0
# }
```

### 手动测试PWM

```bash
# 使用gpio命令手动输出
gpio pwm 22 512    # 停止
gpio pwm 22 700    # 前进
gpio pwm 22 300    # 后退
```

### 查看运动轨迹

```bash
# 轨迹图自动生成在
ls /tmp/orangepi_trajectory/

# 查看最新图像
eog /tmp/orangepi_trajectory/trajectory_latest.png
```

## 高级用法

### 自定义速度命令

```python
# 如果需要在代码中直接发送速度命令
velocity_cmd = {
    'linear_velocity': 0.5,      # m/s
    'angular_velocity': 0.2,     # rad/s
    'timestamp': time.time()
}
output_port.send(velocity_cmd)
```

### 监控PWM输出

```python
# 订阅PWM状态输出
pwm_status = pwm_status_port.recv_latest()
if pwm_status:
    print(f"L={pwm_status['left_pwm']}, R={pwm_status['right_pwm']}")
    print(f"v={pwm_status['linear_velocity']:.2f}m/s")
    print(f"w={pwm_status['angular_velocity']:.2f}rad/s")
```

### 实时参数调整

虽然目前不支持热更新，但可以：
1. 停止运行
2. 修改配置文件
3. 重新启动

## 常见参数值参考

### 小型机器人（0.5m宽）

```yaml
wheel_base: 0.5
max_linear_speed: 2.0
max_angular_speed: 1.0
neutral_pwm: 512
max_pwm_delta: 400
```

### 中型履带车（1.0m宽）

```yaml
wheel_base: 1.0
max_linear_speed: 1.0
max_angular_speed: 0.5
neutral_pwm: 512
max_pwm_delta: 350
```

### 高速移动平台（0.3m宽）

```yaml
wheel_base: 0.3
max_linear_speed: 4.0
max_angular_speed: 2.0
neutral_pwm: 512
max_pwm_delta: 450
```

## 故障排查速查表

| 症状 | 可能原因 | 解决方案 |
|------|---------|---------|
| 电机完全不转 | PWM不输出 | 检查GPIO权限、dry_run_mode |
| 电机不停 | neutral_pwm错误 | 调试neutral_pwm值 |
| 转向不准 | wheel_base错误 | 实测并更新wheel_base |
| 速度不对 | max_linear_speed错误 | 标定实际最大速度 |
| 响应缓慢 | 滤波延迟 | 减少alpha_pos系数 |
| 抖动厉害 | 控制增益太高 | 降低heading_p_gain |

## 下一步

- 📖 详细文档: [README.md](README.md)
- 🔧 完整配置: [../examples/orangepi_real_robot.yaml](../examples/orangepi_real_robot.yaml)
- 🚀 部署指南: [../../docs/ORANGEPI_DEPLOYMENT_GUIDE.md](../../docs/ORANGEPI_DEPLOYMENT_GUIDE.md)

---

**需要帮助？** 查看 README.md 的故障排查章节
