# 车辆控制策略节点

车辆控制策略节点，接收GPS定位数据并生成车辆控制命令。

## 功能

- 接收高精度GPS定位数据
- 计算控制策略（速度、转向等）
- 输出标准化的车辆控制命令

## 端口

### 输入端口

- **gps_fix** (gps.fix): RTK GPS定位数据

### 输出端口

- **control_cmd** (control.cmd): 车辆控制命令
  - `timestamp`: 时间戳
  - `speed`: 目标速度（m/s）
  - `steering`: 转向角（-1.0 ~ 1.0，左负右正）
  - `throttle`: 油门（0.0 ~ 1.0）
  - `brake`: 制动（0.0 ~ 1.0）
  - `vehicle_type`: 车辆类型
  - `gps_seq`: GPS数据序列号
  - `gps_quality`: GPS质量指示
  - `status`: 控制状态

## 参数

- **vehicle_type** (string, 必填): 车辆类型
  - `tracked`: 履带车（挖掘机、推土机等）
  - `wheeled`: 轮式车（汽车、拖拉机等）
- **max_speed** (float, 默认2.0): 最大速度（m/s）
- **target_heading** (float, 默认90.0): 目标航向（度）
- **enable_control** (bool, 默认true): 是否启用控制输出

## 使用示例

### 在runtime.yaml中配置

```yaml
nodes:
  - id: controller_main
    package: controller
    params:
      vehicle_type: "tracked"
      max_speed: 2.0
      target_heading: 90.0
      enable_control: true
```

## 控制策略

### 简化的速度控制

- RTK定位：全速（max_speed）
- GPS定位：半速（max_speed * 0.5）
- 无定位：零速

### 转向控制

根据目标航向和当前航向计算转向角，范围 [-1.0, 1.0]。

## 扩展

实际生产环境中，应替换简化的控制策略为完整的：
- 路径规划模块
- 障碍物检测和避障
- 动力学模型
- PID控制器
- 安全检查机制
