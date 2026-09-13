# RTK GPS定位节点

RTK GPS定位输入节点，模拟或读取RTK定位接收器数据。

## 功能

- 定期输出高精度GPS定位数据
- 支持模拟模式（用于演示和测试）
- 支持实际串口读取（生产环境）

## 端口

### 输出端口

- **gps_fix** (gps.fix): RTK GPS定位数据
  - `seq`: 数据序列号
  - `timestamp`: 时间戳
  - `latitude`: 纬度
  - `longitude`: 经度
  - `altitude`: 海拔
  - `fix_type`: 定位类型（RTK/GPS/NONE）
  - `num_satellites`: 卫星数量
  - `horizontal_accuracy`: 水平精度（米）
  - `vertical_accuracy`: 垂直精度（米）
  - `velocity_east`: 东向速度（m/s）
  - `velocity_north`: 北向速度（m/s）
  - `velocity_up`: 垂向速度（m/s）

## 参数

- **device** (string, 必填): 串口设备路径，如 `/dev/ttyUSB0`
- **baudrate** (int, 默认115200): 波特率
- **update_rate_hz** (float, 默认10.0): 数据发布频率（Hz）
- **simulation_mode** (bool, 默认true): 是否使用模拟数据

## 使用示例

### 在runtime.yaml中配置

```yaml
nodes:
  - id: rtk_main
    package: rtk
    params:
      device: "/dev/ttyUSB0"
      baudrate: 115200
      update_rate_hz: 10.0
      simulation_mode: true  # 演示模式
```

## 模拟数据

在`simulation_mode: true`时，节点生成以北京附近（39.9042°N, 116.4074°E）为基准的模拟GPS数据，包含随机漂移模拟真实场景。
