# Web Teleop Node

Web 远程控制节点，提供浏览器界面进行速度控制。

## 功能特性

- ✅ **Web 控制界面** - 浏览器访问，支持局域网设备
- ✅ **虚拟手柄** - 触摸屏友好的双摇杆控制
- ✅ **键盘控制** - WASD 或方向键控制
- ✅ **实时状态显示** - 显示当前命令速度和反馈速度
- ✅ **紧急停止** - 一键停止功能
- ✅ **自动超时** - 无操作超时自动停止
- ✅ **持续输出模式** - 保持最后状态持续输出

## 硬件需求

无特殊硬件需求，任何可运行 Python 的设备即可。

## 使用方法

### 1. 配置节点

```yaml
nodes:
  - id: web_teleop
    package: web_teleop
    description: "Web远程控制"
    params:
      http_port: 9873              # HTTP端口
      http_host: "0.0.0.0"         # 监听地址
      max_linear_speed: 1.0        # 最大线速度
      max_angular_speed: 1.0       # 最大角速度
      continuous_output: true      # 持续输出
      command_timeout: 5.0         # 超时时间

edges:
  # Web控制 → PWM驱动
  - from: web_teleop.velocity_cmd
    to: motor_pwm.velocity_cmd

  # PWM状态反馈 (可选)
  - from: motor_pwm.pwm_status
    to: web_teleop.feedback
```

### 2. 访问控制界面

在同一局域网的设备浏览器中访问：

```
http://<香橙派IP>:9873
```

例如：
```
http://192.168.1.100:9873
```

### 3. 控制方式

#### 虚拟手柄
- **左摇杆**: 前进/后退
- **右摇杆**: 左转/右转

#### 键盘
- `W` / `↑`: 前进
- `S` / `↓`: 后退
- `A` / `←`: 左转
- `D` / `→`: 右转
- `空格`: 紧急停止

## API 接口

### GET /api/status
获取当前状态

```json
{
  "command": {
    "linear_velocity": 0.5,
    "angular_velocity": 0.2
  },
  "feedback": {
    "linear_velocity": 0.48,
    "angular_velocity": 0.19
  },
  "limits": {
    "max_linear_speed": 1.0,
    "max_angular_speed": 1.0
  }
}
```

### POST /api/control
发送控制命令

```json
{
  "linear": 0.5,
  "angular": 0.2
}
```

### POST /api/stop
紧急停止

## 参数说明

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| http_port | int | 9873 | HTTP端口 |
| http_host | str | 0.0.0.0 | 监听地址 |
| max_linear_speed | float | 1.0 | 最大线速度 |
| max_angular_speed | float | 1.0 | 最大角速度 |
| continuous_output | bool | true | 持续输出模式 |
| output_rate | float | 10.0 | 输出频率 (Hz) |
| command_timeout | float | 5.0 | 超时时间 (秒) |

## 故障排查

### 无法访问 Web 界面

1. 检查防火墙设置
2. 确认端口未被占用: `netstat -tlnp | grep 9873`
3. 确认设备在同一局域网

### 控制无响应

1. 检查 edges 连接是否正确
2. 查看节点日志确认命令是否发送
3. 检查下游节点是否正常运行
