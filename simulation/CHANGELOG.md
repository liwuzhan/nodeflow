# 更新日志

## 2025-12-23 - 目录重构和坐标系整合

### ✅ 已完成

#### 1. **目录结构整理**

重新组织了 simulator 目录结构，提高可维护性：

```
simulator/
├── server.py, physics.py, sensors.py, state.py, field_generator.py  # 核心模块
├── config.yaml                                                       # 配置
├── example_usage.py                                                  # 示例
│
├── docs/          # 📚 所有文档集中在这里
│   ├── README.md, QUICKSTART.md, INTEGRATION_GUIDE.md
│   └── ...
│
├── tests/         # 🧪 所有测试集中在这里
│   ├── test_core.py, test_integration.py
│   ├── run_tests.sh
│   └── ...
│
└── utils/         # 🛠️ 工具模块
    ├── coordinates.py              # 坐标系转换
    └── random_parcel_generator.py  # 随机地块生成
```

**改进**：
- ✅ 测试文件不再散落在根目录
- ✅ 文档统一管理
- ✅ 工具模块独立

---

#### 2. **坐标系转换整合**

**新增模块**: `simulator/utils/coordinates.py`

提供笛卡尔坐标（米）↔ GPS坐标（WGS84）转换：

```python
from utils.coordinates import CoordinateConverter

converter = CoordinateConverter(ref_lon=121.5, ref_lat=31.2)

# 米 → GPS
lon, lat = converter.meter_to_gps(100, 200)

# GPS → 米
x, y = converter.gps_to_meter(121.5, 31.2)

# 批量转换边界
boundary_gps = converter.convert_boundary(boundary_meter, to_gps=True)
```

**集成到 sim_output 节点**：

现在 `sim_output` 节点自动将仿真器的笛卡尔坐标转换为 GPS 坐标：

```yaml
# node-hub/sim_output/node.yaml - 新增参数
params:
  ref_longitude: 121.5  # 参考经度
  ref_latitude: 31.2    # 参考纬度
```

**数据流**：
```
仿真器 field_generator
    ↓ [(0,0), (100,0), (100,200), (0,200)] (米)
sim_output 坐标转换
    ↓ [(121.5, 31.2), (121.501, 31.2), ...] (GPS)
global_coverage 规划器
    ↓ 路径点 [(lon, lat), ...]
velocity_controller 控制器
```

---

#### 3. **RTK GPS 增强**

**新增字段** (simulator/sensors.py):

```python
rtk_data = {
    "latitude": ...,
    "longitude": ...,
    "heading": math.degrees(state.yaw),    # ✅ 航向角 (度)
    "pitch": math.degrees(state.pitch),    # ✅ 俯仰角 (度)
    "roll": math.degrees(state.roll),      # ✅ 侧滚角 (度)
    "rtk_status": "FIXED",
    ...
}
```

模拟**双天线 RTK** 的真实输出。

---

#### 4. **sim_output 和 sim_input 节点创建**

**替代原有的 5 个碎片化节点**：

| 原方案 | 新方案 | 改进 |
|--------|--------|------|
| sim_gps, sim_imu, sim_rtk, sim_motor, sim_velocity | sim_output + sim_input | 节点数 -60% |
| 5 条 ZMQ 连接 | 2 条 ZMQ 连接 | 连接数 -60% |
| 数据不同步 | 同帧保证 | 可靠性 ↑ |
| 无地块输出 | 内置 task_request | 新增功能 |

**sim_output 输出端口**:
- `gps_fix`, `imu_data`, `rtk_fix`, `odometry` (传感器)
- `task_request` (地块+车辆配置，供规划器使用)
- `state_info` (调试)

**sim_input 输入端口**:
- `velocity_cmd` (优先级 1)
- `motor_cmd` (优先级 2)

---

#### 5. **velocity_controller 修复**

**修复坐标顺序问题**:

```python
# 修复前
lat, lon = self.path[i]  # ❌ 假设 (lat, lon)

# 修复后
lon, lat = self.path[i]  # ✅ WGS84 标准 (lon, lat)
```

global_coverage 输出的是 `[(lon, lat), ...]`（WGS84 标准格式）。

---

### 📝 配置更新

#### examples/planning_simulation.yaml

新增完整的规划闭环仿真示例：

```yaml
nodes:
  - id: sim_output      # 仿真器输出（含地块）
  - id: global_coverage # 全局路径规划
  - id: velocity_controller
  - id: sim_input       # 仿真器输入

edges:
  sim_output.task_request → global_coverage
  sim_output.rtk_fix → velocity_controller
  global_coverage.global_path → velocity_controller
  velocity_controller.velocity_cmd → sim_input
```

**完整闭环**：
```
sim_output (RTK+地块) → global_coverage (规划) → velocity_controller (控制)
                                                            ↓
                                                       sim_input
                                                            ↓
                                                        仿真器更新位置
                                                            ↑
                                                     (闭环反馈)
```

---

### 🐛 已修复问题

1. ✅ 坐标系不匹配（米 vs GPS）
2. ✅ 参数访问方式（`self.params.xxx` → `self.params.get('xxx')`）
3. ✅ velocity_controller 坐标顺序错误
4. ✅ 缺少 RTK 航向角输出
5. ✅ 缺少地块输出节点

---

### 📦 依赖更新

新增 Python 包：
- `pyzmq` (ZMQ 通信)
- `shapely` (几何运算，规划器需要)
- `pyproj` (投影转换，规划器需要)

```bash
pip3 install pyzmq shapely pyproj
```

---

### 🚀 使用方法

#### 1. 启动仿真器

```bash
python3 simulator/server.py
```

#### 2. 运行规划闭环仿真

```bash
python3 -m runtime.main examples/planning_simulation.yaml
```

#### 3. 预期结果

- ✅ sim_output 读取 100m×200m 矩形地块
- ✅ 坐标转换：米 → GPS
- ✅ global_coverage 生成全覆盖路径
- ✅ velocity_controller 跟踪路径
- ✅ sim_input 发送速度指令到仿真器
- ✅ 闭环反馈：RTK 持续输出新位置

---

### 📁 迁移后的文件位置

| 旧位置 | 新位置 |
|--------|--------|
| `simulator/test_*.py` | `simulator/tests/test_*.py` |
| `simulator/*.md` | `simulator/docs/*.md` |
| `simulator/generate_random_parcel.py` | `simulator/utils/random_parcel_generator.py` |
| (新增) | `simulator/utils/coordinates.py` |
| (新增) | `simulator/README.md` |

---

### ⚡ 性能提升

- 节点数量：5 → 2（-60%）
- ZMQ 连接：5 → 2（-60%）
- 数据同步：无保证 → 同帧保证
- 代码复用：重复逻辑 → 统一管理

---

### 🔜 未来工作

- [ ] LiDAR 扫描模拟（当前为占位）
- [ ] 完整碰撞检测（当前仅边界）
- [ ] 3D 可视化
- [ ] 多机器人支持
- [ ] 更真实的 RTK 状态转移模型

---

**更新者**: Claude Code
**日期**: 2025-12-23
