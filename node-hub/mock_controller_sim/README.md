# Mock Controller Simulator Node

## 概述

模拟自主控制算法，实现纯追踪（Pure Pursuit）转向控制，用于测试路径跟踪和自主导航系统。

## 功能

- 实现纯追踪路径跟踪算法
- 接收GPS定位数据和参考路径
- 生成速度和转向角控制指令
- 计算路径偏差（crosstrack error）
- 支持手动控制模式覆盖

## 端口定义

### 输入端口

1. **gps_fix** (JSON): 当前GPS定位数据
   ```json
   {
     "latitude": 39.9042,
     "longitude": 116.4074,
     "timestamp": 1703024780.123
   }
   ```

2. **path_reference** (JSON): 参考路径
   ```json
   {
     "path": [[116.4074, 39.9042], [116.4076, 39.9044], ...],
     "status": "success"
   }
   ```

3. **joystick_input** (JSON): 摇杆输入（可选，用于手动模式或优先级覆盖）
   ```json
   {
     "linear_velocity": 1.5,
     "angular_velocity": 0.5
   }
   ```

### 输出端口

- **control_command** (JSON): 生成的控制指令
  ```json
  {
    "timestamp": 1703024780.5,
    "seq": 1,
    "velocity": 1.5,
    "steering_angle": 0.2,
    "control_mode": "pure_pursuit",
    "crosstrack_error": 0.05
  }
  ```

## 参数配置

| 参数名 | 类型 | 默认值 | 说明 |
|--------|------|--------|------|
| `control_mode` | string | `"pure_pursuit"` | 控制模式：`pure_pursuit`、`pid`、`manual` |
| `lookahead_distance` | number | `2.0` | 前瞻距离（米） |
| `max_steering_angle` | number | `0.5` | 最大转向角（弧度） |
| `max_velocity` | number | `2.0` | 最大速度（m/s） |
| `update_rate_hz` | number | `50` | 控制更新频率（Hz） |
| `wheelbase` | number | `1.0` | 车轴距离（米） |

## 使用示例

### 示例1：标准纯追踪导航

```yaml
nodes:
  - id: gps_0
    package: mock_gps
    params:
      mode: moving
      velocity_mps: 2.0

  - id: planner_0
    package: mock_path_planner
    params:
      plan_mode: direct_line

  - id: controller_0
    package: mock_controller_sim
    params:
      control_mode: pure_pursuit
      lookahead_distance: 2.0

edges:
  - from: gps_0.gps_fix
    to: controller_0.gps_fix
  - from: planner_0.path
    to: controller_0.path_reference
  - from: controller_0.control_command
    to: motor_0.control_cmd
```

### 示例2：手动控制模式

```yaml
nodes:
  - id: joystick_0
    package: mock_joystick

  - id: controller_0
    package: mock_controller_sim
    params:
      control_mode: manual

edges:
  - from: joystick_0.control_input
    to: controller_0.joystick_input
```

## 控制算法

### Pure Pursuit 算法

**原理**: 追踪参考路径上前方一定距离的目标点

**公式**:
```
δ = atan(2L × sin(α) / d)
```

其中：
- δ: 转向角
- L: 车轴距离
- α: 目标点相对车辆朝向的角度
- d: 车辆到目标点的距离

**特点**:
- 简单高效，易于实现
- 稳定的路径跟踪性能
- 对参数变化不敏感

**参数选择**:
- 前瞻距离 `lookahead_distance`: 越大越稳定，但响应慢；越小越敏捷，但容易振荡
- 建议: `lookahead_distance = vehicle_speed × 0.5-1.0` (秒级前瞻时间)

### 其他模式（预留）

- **PID**: 传统PID控制，需要调参
- **Manual**: 直接使用摇杆输入，用于远程遥控

## 路径偏差计算

**Crosstrack Error**: 车辆当前位置到参考路径的垂直距离

- 计算方法: 找到路径上最近的点，计算距离
- 用于: 速度调节和稳定性监控
- 典型阈值:
  - < 0.1 m: 跟踪良好
  - 0.1-0.5 m: 跟踪正常
  - > 0.5 m: 偏差过大，减速并增大前瞻距离

## 坐标系统

- **纬度/经度**: 十进制度数（WGS84）
- **距离计算**: Haversine公式（考虑地球曲率）
- **转向角**: 弧度制（正数=向左，负数=向右）

## 测试用途

1. **路径跟踪验证**: 测试控制算法的准确性
2. **导航系统集成**: 验证GPS、规划器、控制器的协同工作
3. **性能评估**: 测试跟踪误差、收敛时间、稳定性
4. **鲁棒性测试**: 使用不同的GPS精度和路径进行测试

## 替换为真实控制器

要替换为真实车辆控制器：

1. 获取车辆真实参数：轴距、最大转向角、速度限制
2. 集成车辆控制接口（CAN/ROS）
3. 添加车辆反馈和状态监控
4. 保持相同的输入输出格式

```python
# 真实控制器集成示例
import rospy
from geometry_msgs.msg import Twist
from nav_msgs.msg import Path

def publish_control_command(velocity, steering_angle):
    """发布到车辆控制系统"""
    twist = Twist()
    twist.linear.x = velocity
    twist.angular.z = steering_angle
    cmd_pub.publish(twist)

# 订阅ROS消息
gps_sub = rospy.Subscriber('/gps', NavSatFix, gps_callback)
path_sub = rospy.Subscriber('/path', Path, path_callback)
```

## 性能指标

- CPU占用：2-3%
- 内存占用：15-20 MB
- 控制延迟：< 10 ms（典型50 Hz更新）
- 路径跟踪误差：< 0.2 m（在合适的前瞻距离下）

## 依赖

- Python 3.9+
- NodeFlow SDK

## 日志输出

- **INFO**: 启动配置、路径更新
- **DEBUG**: 每秒一次的控制指令和误差
- **ERROR**: 传感器失败、异常情况
