# Mock Motor Controller

## 概述
模拟电机控制器，接收速度和转向指令并模拟执行。

## 端口
- **输入**: control_cmd (控制指令)
- **输出**: 无

## 参数
- `motor_count`: 电机数量 (default: 2)
- `response_delay_ms`: 响应延迟 (default: 100ms)
- `max_pwm`: 最大PWM值 (default: 1500)

## 用途
测试控制指令的最终执行环节
