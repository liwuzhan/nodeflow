# NodeFlow 仿真器

农田机器人物理仿真系统

## 📁 目录结构

```
simulator/
├── server.py              # 仿真器主服务（ZMQ服务器）
├── physics.py             # 运动学引擎（差速驱动+打滑+地形噪声）
├── sensors.py             # 传感器模拟（GPS/RTK/IMU/里程计）
├── state.py               # 机器人状态定义
├── field_generator.py     # 田地生成器（矩形/不规则）
├── config.yaml            # 配置文件
├── example_usage.py       # 使用示例
│
├── docs/                  # 📚 文档
│   ├── README.md          # 主文档
│   ├── QUICKSTART.md      # 快速启动指南
│   ├── INTEGRATION_GUIDE.md
│   ├── NODEFLOW_INTEGRATION.md
│   └── ...
│
├── tests/                 # 🧪 测试
│   ├── test_core.py       # 核心功能测试
│   ├── test_integration.py
│   ├── run_tests.sh       # 测试脚本
│   └── ...
│
└── utils/                 # 🛠️ 工具模块
    ├── coordinates.py     # 坐标系转换
    ├── random_parcel_generator.py  # 随机地块生成
    └── __init__.py
```

## 🚀 快速启动

### 1. 启动仿真器

```bash
python3 server.py
```

### 2. 使用示例

```bash
python3 example_usage.py
```

### 3. 运行测试

```bash
cd tests
bash run_tests.sh
```

## 📖 详细文档

请查看 `docs/` 目录：

- **README.md** - 完整功能说明
- **QUICKSTART.md** - 快速启动指南
- **NODEFLOW_INTEGRATION.md** - NodeFlow 集成说明

## 🔧 配置

编辑 `config.yaml` 修改仿真参数：

```yaml
# 田地配置
field:
  type: rectangular
  width: 100.0
  length: 200.0

# 运动学配置
kinematics:
  max_speed: 2.0
  slip:
    enabled: true
    ratio: 0.05
```

## 📡 API

仿真器提供 ZMQ REQ/REP 协议：

- `get_sensor` - 获取传感器数据（gps/rtk_gps/imu/odometry）
- `set_actuator` - 设置执行器（motor/velocity）
- `get_field` - 获取田地信息
- `get_state` - 获取完整状态
- `reset` - 重置仿真

详见 `docs/INTEGRATION_GUIDE.md`

## 🛠️ 工具

### 坐标转换

```python
from utils.coordinates import CoordinateConverter

converter = CoordinateConverter(ref_lon=121.5, ref_lat=31.2)
lon, lat = converter.meter_to_gps(100, 200)  # 米 → GPS
x, y = converter.gps_to_meter(121.5, 31.2)   # GPS → 米
```

### 随机地块生成

```python
from utils.random_parcel_generator import RandomParcelGenerator

generator = RandomParcelGenerator(base_lon=121.5, base_lat=31.2)
generator.generate_parcel_file("output.txt", num_outer_points=6)
```

## 📦 NodeFlow 集成

仿真器已完全集成到 NodeFlow 系统：

- **sim_output** - 仿真器输出节点（传感器+地块）
- **sim_input** - 仿真器输入节点（控制命令）

详见 `examples/planning_simulation.yaml`

## 🧪 测试

运行所有测试：

```bash
cd tests && bash run_tests.sh
```

单独测试：

```bash
python3 tests/test_core.py
python3 tests/test_integration.py
```

## 📊 性能

- 内部仿真频率: 100 Hz
- RTK GPS 输出: 20 Hz
- 普通 GPS: 无限制
- IMU: 无限制
- 实时模式 / 加速模式

## 🤝 贡献

欢迎提交 Issue 和 Pull Request
