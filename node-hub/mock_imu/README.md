# Mock IMU Node

## 概述

模拟惯性测量单元（IMU），包含三轴加速度计、陀螺仪和磁力计，用于测试传感器融合和姿态估计算法。

## 功能

- 生成三轴加速度计数据（包含重力）
- 生成三轴陀螺仪数据（角速度）
- 生成三轴磁力计数据（磁场强度）
- 支持多种运动模式：静止、加速、旋转、振动
- 可配置传感器偏置和噪声
- 高频数据流（典型100 Hz）

## 端口定义

### 输出端口

- **imu_data** (JSON): IMU传感器数据
  ```json
  {
    "timestamp": 1703024780.001,
    "seq": 1,
    "accel_x": 0.1,
    "accel_y": 0.0,
    "accel_z": 9.81,
    "gyro_x": 0.0,
    "gyro_y": 0.0,
    "gyro_z": 0.05,
    "mag_x": 100,
    "mag_y": 50,
    "mag_z": 200,
    "temperature": 25.0
  }
  ```

### 输入端口

无

## 参数配置

| 参数名 | 类型 | 默认值 | 说明 |
|--------|------|--------|------|
| `mode` | string | `"stationary"` | 运动模式：`stationary`、`accelerating`、`rotating`、`vibrating` |
| `update_rate_hz` | number | `100` | 发布频率（Hz） |
| `noise_level` | number | `0.01` | 传感器噪声标准差 |
| `accel_bias_x` | number | `0.0` | 加速度计X轴偏置（m/s²） |
| `accel_bias_y` | number | `0.0` | 加速度计Y轴偏置（m/s²） |
| `accel_bias_z` | number | `0.0` | 加速度计Z轴偏置（m/s²） |
| `gyro_bias_x` | number | `0.0` | 陀螺仪X轴偏置（rad/s） |
| `gyro_bias_y` | number | `0.0` | 陀螺仪Y轴偏置（rad/s） |
| `gyro_bias_z` | number | `0.0` | 陀螺仪Z轴偏置（rad/s） |

## 使用示例

### 示例1：静止模式（默认）

```yaml
nodes:
  - id: imu_0
    package: mock_imu
    params:
      mode: stationary
      update_rate_hz: 100
      noise_level: 0.01
```

模拟静止状态，重力加速度在Z轴，适合测试传感器校准。

### 示例2：旋转运动

```yaml
nodes:
  - id: imu_0
    package: mock_imu
    params:
      mode: rotating
      update_rate_hz: 100
```

模拟旋转运动，陀螺仪输出周期性角速度，适合测试姿态估计算法。

### 示例3：带偏置的传感器

```yaml
nodes:
  - id: imu_0
    package: mock_imu
    params:
      mode: stationary
      accel_bias_z: 0.2  # 200 mg 偏置
      gyro_bias_z: 0.01  # 陀螺仪漂移
```

模拟有偏置的传感器，适合测试校准算法。

### 示例4：高频采样

```yaml
nodes:
  - id: imu_0
    package: mock_imu
    params:
      mode: accelerating
      update_rate_hz: 200  # 高频
```

模拟高频IMU数据流，适合压力测试。

## 坐标系定义

使用 **NED (North-East-Down)** 坐标系：

- **X轴**: 前进方向（North）
- **Y轴**: 右侧方向（East）
- **Z轴**: 向下方向（Down）

**重力加速度**: 在静止状态下，`accel_z ≈ +9.81 m/s²`

## 数据生成逻辑

### Stationary 模式
- 加速度计：`accel_z ≈ 9.81`, 其他轴接近0
- 陀螺仪：所有轴接近0
- 噪声：高斯噪声（标准差 = `noise_level`）

### Accelerating 模式
- 加速度计：周期性加速度变化（正弦波）
- X轴：幅度2.0 m/s²，周期5秒
- Y轴：幅度0.5 m/s²，周期7秒
- 陀螺仪：接近0

### Rotating 模式
- 加速度计：主要是重力（可能有小的离心加速度）
- 陀螺仪：周期性角速度变化
  - X轴：幅度0.3 rad/s，周期4秒
  - Y轴：幅度0.2 rad/s，周期6秒
  - Z轴：幅度0.5 rad/s，周期3秒

### Vibrating 模式
- 加速度计：高频振动（20 Hz）叠加在重力上
- 陀螺仪：接近0

## 传感器规格（模拟）

| 传感器 | 量程 | 噪声密度 | 偏置稳定性 |
|--------|------|----------|-----------|
| 加速度计 | ±16 g | 0.01 m/s²/√Hz | 0.05 m/s² |
| 陀螺仪 | ±2000 °/s | 0.001 rad/s/√Hz | 0.01 rad/s |
| 磁力计 | ±800 μT | 5 μT | 10 μT |

## 测试用途

1. **传感器融合**: 测试EKF/UKF等融合算法
2. **姿态估计**: 测试AHRS（Attitude and Heading Reference System）
3. **高频数据流**: 验证100+ Hz数据处理能力
4. **偏置补偿**: 测试传感器校准算法
5. **运动检测**: 测试运动状态识别

## 替换为真实硬件

要替换为真实IMU设备（如MPU9250, BNO055）：

1. 修改 `run.py` 连接到I2C/SPI接口
2. 使用硬件驱动库读取传感器数据
3. 转换为相同的JSON输出格式
4. 保持单位一致性（m/s², rad/s, μT）

```python
# 真实硬件集成示例（使用adafruit库）
from adafruit_mpu6050 import MPU6050
import board

i2c = board.I2C()
mpu = MPU6050(i2c)

while True:
    accel_x, accel_y, accel_z = mpu.acceleration
    gyro_x, gyro_y, gyro_z = mpu.gyro

    imu_data = {
        'timestamp': time.time(),
        'seq': seq,
        'accel_x': accel_x,
        'accel_y': accel_y,
        'accel_z': accel_z,
        'gyro_x': gyro_x,
        'gyro_y': gyro_y,
        'gyro_z': gyro_z,
        # ... 磁力计数据 ...
        'temperature': mpu.temperature
    }

    imu_output.send(imu_data)
    time.sleep(1.0 / update_rate_hz)
```

## 依赖

- Python 3.9+
- NodeFlow SDK

## 日志输出

- **INFO**: 启动信息、配置参数
- **DEBUG**: 每秒一次的IMU数据样本
- **ERROR**: 异常情况

## 性能指标

- CPU占用：< 2%
- 内存占用：< 10 MB
- 数据流稳定性：按配置频率精确输出（100 Hz = 10ms间隔）
