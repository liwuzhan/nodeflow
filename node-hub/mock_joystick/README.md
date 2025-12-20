# Mock Joystick Node

## 概述

模拟手柄/遥控器输入设备，生成标准化的控制指令用于测试控制流。

## 功能

- 生成线速度和角速度控制指令
- 支持三种生成模式：固定值、正弦波、随机值
- 可配置发布频率和最大速度范围
- 模拟按钮状态

## 端口定义

### 输出端口

- **control_input** (JSON): 控制指令数据
  ```json
  {
    "timestamp": 1703024780.123,
    "seq": 1,
    "linear_velocity": 1.5,
    "angular_velocity": 0.5,
    "buttons": {"a": true, "b": false}
  }
  ```

### 输入端口

无

## 参数配置

| 参数名 | 类型 | 默认值 | 说明 |
|--------|------|--------|------|
| `mode` | string | `"sine"` | 生成模式：`constant`（固定）、`sine`（正弦波）、`random`（随机） |
| `update_rate_hz` | number | `50` | 发布频率（Hz） |
| `max_linear_velocity` | number | `2.0` | 最大线速度（m/s） |
| `max_angular_velocity` | number | `1.57` | 最大角速度（rad/s，约90度/秒） |

## 使用示例

### 示例1：正弦波模式（默认）

```yaml
nodes:
  - id: joystick_0
    package: mock_joystick
    params:
      mode: sine
      update_rate_hz: 50
      max_linear_velocity: 2.0
      max_angular_velocity: 1.57
```

生成平滑变化的控制指令，适合测试连续控制。

### 示例2：固定值模式

```yaml
nodes:
  - id: joystick_0
    package: mock_joystick
    params:
      mode: constant
      max_linear_velocity: 1.0
      max_angular_velocity: 0.5
```

输出固定的控制值（50%最大速度），适合稳态测试。

### 示例3：随机模式

```yaml
nodes:
  - id: joystick_0
    package: mock_joystick
    params:
      mode: random
      update_rate_hz: 20
```

生成随机控制值，适合压力测试和边界条件测试。

## 数据生成逻辑

### Constant 模式
- 线速度和角速度固定为 `max_value * 0.5`

### Sine 模式
- 使用正弦波函数：`value = max_value * sin(2π * t / period)`
- 周期为 10 秒
- 线速度和角速度使用不同的相位偏移

### Random 模式
- 在 `[-max_value, max_value]` 范围内均匀随机生成

## 测试用途

1. **单节点测试**: 验证节点能否正确启动和输出数据
2. **链式测试**: 作为数据源测试下游节点的数据接收
3. **频率测试**: 验证框架能否处理不同频率的数据流
4. **控制流测试**: 测试控制指令的传播和处理

## 替换为真实硬件

要替换为真实手柄设备：

1. 修改 `run.py` 中的数据生成逻辑
2. 集成 HID 库（如 `pygame` 或 `evdev`）
3. 读取真实设备的输入并映射到相同的数据格式
4. 保持输出端口格式不变，确保下游节点兼容

```python
# 真实硬件集成示例
import pygame

pygame.init()
joystick = pygame.joystick.Joystick(0)
joystick.init()

while True:
    pygame.event.pump()

    control_data = {
        'timestamp': time.time(),
        'seq': seq,
        'linear_velocity': joystick.get_axis(1) * max_linear_velocity,
        'angular_velocity': joystick.get_axis(0) * max_angular_velocity,
        'buttons': {
            'a': joystick.get_button(0),
            'b': joystick.get_button(1)
        }
    }

    control_output.send(control_data)
```

## 依赖

- Python 3.9+
- NodeFlow SDK

## 日志输出

- **INFO**: 启动信息、配置参数
- **DEBUG**: 每秒一次的控制值样本
- **ERROR**: 异常情况

## 性能指标

- CPU占用：< 1%
- 内存占用：< 10 MB
- 数据流稳定性：按配置频率精确输出
