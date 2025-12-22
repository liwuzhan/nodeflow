# 农田作业仿真系统设计

## 📋 目录

1. [需求分析](#需求分析)
2. [仿真环境设计](#仿真环境设计)
3. [核心模块规划](#核心模块规划)
4. [实施路线](#实施路线)
5. [验证策略](#验证策略)

---

## 需求分析

### 农田作业的特殊性

与通用机器人不同，农田作业机器人有独特的需求：

| 需求 | 特点 | 影响 |
|------|------|------|
| **GPS精度** | 需要 RTK 级别 (厘米级) | 仿真 GPS 必须支持高精度模式 |
| **路径规划** | 平行线作业 (车道线模式) | 需要轨迹生成器模块 |
| **作业执行** | 喷洒、播种、覆盖等多模式 | 需要作业状态机 |
| **地形适应** | 田地不平整，有坡度 | 需要简单的高度地图 |
| **实时性** | 田间作业不能中断 | 仿真需要高频率、低延迟 |
| **多机协作** | 多台机器同时作业 | 仿真需要支持多机场景 |

---

## 仿真环境设计

### 1. 虚拟农田模型

```python
class FarmEnvironment:
    """虚拟农田环境"""

    def __init__(self):
        # 地块信息
        self.field_width = 100.0      # 田地宽度 (米)
        self.field_length = 200.0     # 田地长度 (米)
        self.row_spacing = 0.5        # 行距 (米)，用于轨迹

        # 地形
        self.height_map = None        # 高程数据
        self.soil_type = None         # 土壤类型
        self.crop_coverage = None     # 作物覆盖图

        # 地块边界
        self.field_corners = [
            (0.0, 0.0),              # 左下
            (100.0, 0.0),            # 右下
            (100.0, 200.0),          # 右上
            (0.0, 200.0)             # 左上
        ]

        # 障碍物
        self.obstacles = []           # 树、井、田埂等

        # 环境条件
        self.weather = {
            'temperature': 25.0,      # 摄氏度
            'humidity': 60.0,         # %
            'wind_speed': 2.0,        # m/s
            'wind_direction': 0.0     # 度
        }
```

### 2. 扩展的传感器模型

**GPS 传感器升级**:
```python
class FarmGPSSensor:
    """农田 GPS 传感器（支持 RTK）"""

    def get_rtk_position(self, state):
        """RTK 定位 (厘米级精度)"""
        return {
            "latitude": state.lat,
            "longitude": state.lon,
            "altitude": state.altitude,
            "accuracy": 0.02,          # 2cm RTK 精度
            "rtk_status": "FIXED",     # RTK 固定解
            "num_satellites": 12,
            "solution_type": "RTK_FIXED"
        }
```

**新增传感器**:
```python
class FarmSensors:
    """农田特需传感器"""

    def get_row_detection(self, state):
        """行检测（视觉或激光）"""
        # 检测当前是否在田间行道上
        return {
            "on_row": True,
            "offset_from_row": 0.05,   # 距离行中线偏差 (米)
            "row_direction": state.yaw,
            "confidence": 0.95
        }

    def get_soil_moisture(self, state):
        """土壤水分传感器"""
        return {
            "moisture": 65.0,          # %
            "temperature": 22.5,       # ℃
            "location": state.get_position_2d()
        }

    def get_canopy_coverage(self, state):
        """作物冠层覆盖度（RGB 或 NIR 相机）"""
        return {
            "ndvi": 0.65,              # 植被指数
            "coverage": 75.0,          # %
            "height_estimate": 0.8     # 作物高度估计 (米)
        }

    def get_spray_control_feedback(self):
        """喷洒系统反馈"""
        return {
            "nozzle_pressure": 2.5,    # bar
            "flow_rate": 50.0,         # L/min
            "tank_level": 75.0,        # %
            "spray_status": "ACTIVE"
        }
```

### 3. 作业执行模型

```python
class FarmOperationMode:
    """农田作业模式"""

    # 作业类型
    MODE_SPRAYING = "spraying"        # 喷洒
    MODE_SEEDING = "seeding"          # 播种
    MODE_SPREADING = "spreading"      # 撒肥
    MODE_COVERAGE = "coverage"        # 覆盖
    MODE_MONITORING = "monitoring"    # 监测

    def execute_spraying(self, state):
        """喷洒作业"""
        # 喷洒宽度、流量、均匀性等
        return {
            "spray_width": 12.0,           # 米
            "application_rate": 50.0,      # L/ha
            "uniformity": 0.92,            # 0-1
            "coverage_rate": 0.95
        }

    def execute_seeding(self, state):
        """播种作业"""
        return {
            "seeding_rate": 250000,        # 粒/ha
            "seed_spacing": 0.02,          # 米
            "depth": 0.05,                 # 米
            "uniformity": 0.88
        }

    def get_operation_statistics(self):
        """作业统计"""
        return {
            "total_area": 0.0,             # 已作业面积 (ha)
            "coverage_efficiency": 0.0,    # 覆盖效率
            "overlap_percentage": 0.0,     # 重叠度
            "missed_area": 0.0             # 漏作面积
        }
```

### 4. 路径规划场景

```python
class FarmPathPlanner:
    """农田路径规划"""

    def generate_parallel_lines(self, field, row_spacing):
        """生成平行线轨迹"""
        paths = []

        # 从左到右生成平行线
        x = 0.0
        while x < field.width:
            # 一条完整的往返路径
            path = [
                (x, 0.0),                    # 起点
                (x, field.length),           # 终点
                (x + row_spacing, field.length),  # 转向
                (x + row_spacing, 0.0)       # 返回
            ]
            paths.append(path)
            x += 2 * row_spacing

        return paths

    def generate_headland_turn(self, current_pos, next_row, turn_radius):
        """田埂转向（避免重复喷洒的转向逻辑）"""
        # 光滑的曲线转向，半径可配置
        # 用于计算最优的转向轨迹
        pass

    def calculate_overlap_correction(self, position, swath_width):
        """计算重叠修正"""
        # 根据风速、漂移等因素调整喷洒宽度
        # 避免重喷或漏喷
        pass
```

---

## 核心模块规划

### 模块 1: 虚拟农田环境

**文件**: `simulator/farm_environment.py`

```python
class FarmEnvironment:
    """虚拟农田环境管理"""

    def __init__(self, width=100, length=200):
        self.width = width
        self.length = length
        self.field_boundary = self._create_boundary()
        self.worked_area = set()  # 已作业区域 (网格)
        self.time_step = 0

    def is_in_field(self, x, y):
        """检查位置是否在田地内"""
        return 0 <= x <= self.width and 0 <= y <= self.length

    def record_work(self, x, y, operation_type):
        """记录作业位置"""
        grid_cell = (int(x), int(y))
        self.worked_area.add(grid_cell)

    def get_field_coverage(self):
        """获取作业覆盖率"""
        total_cells = int(self.width * self.length)
        coverage = len(self.worked_area) / total_cells if total_cells > 0 else 0
        return coverage
```

### 模块 2: 农田传感器模拟

**文件**: `simulator/farm_sensors.py`

```python
class FarmSensorSimulator(SensorSimulator):
    """继承基础传感器，添加农田特定传感器"""

    def __init__(self, field_env):
        super().__init__()
        self.field = field_env

    def get_row_detection(self, state):
        """视觉行检测"""
        # 计算距离最近行的偏差
        nearest_row_x = round(state.x / 0.5) * 0.5
        offset = state.x - nearest_row_x
        return {
            "on_row": abs(offset) < 0.1,
            "offset": offset,
            "confidence": 0.95
        }

    def get_ndvi_data(self, state):
        """植被指数"""
        # 基于位置的模拟 NDVI 值
        # 在覆盖区域应该降低
        base_ndvi = 0.65
        if self.field.is_in_field(state.x, state.y):
            return {
                "ndvi": base_ndvi,
                "red": 0.3,
                "nir": 0.6,
                "timestamp": state.sim_time
            }
        return None
```

### 模块 3: 作业执行器

**文件**: `node-hub/farm_sprayer/run.py`

```python
class FarmSprayerNode:
    """农田喷洒执行器"""

    def __init__(self):
        self.is_spraying = False
        self.swath_width = 12.0
        self.application_rate = 50.0  # L/ha
        self.tank_level = 100.0

    def control_spray(self, command):
        """控制喷洒"""
        if command['spray_on']:
            self.is_spraying = True
            self.tank_level -= command.get('flow_rate', 0) * 0.01
        else:
            self.is_spraying = False

    def get_spray_feedback(self):
        """获取反馈"""
        return {
            "spraying": self.is_spraying,
            "tank_level": self.tank_level,
            "flow_rate": 50.0 if self.is_spraying else 0.0
        }
```

### 模块 4: 任务管理

**文件**: `node-hub/farm_task_manager/run.py`

```python
class FarmTaskManager:
    """农田作业任务管理"""

    def __init__(self, field_environment):
        self.field = field_environment
        self.current_task = None
        self.task_queue = []
        self.coverage_map = {}

    def generate_work_plan(self, field_width, field_length, swath_width):
        """生成作业计划"""
        # 平行线轨迹
        # 转向策略
        # 重叠处理
        pass

    def monitor_coverage(self, current_pos, swath_width):
        """监控覆盖进度"""
        coverage = self.field.get_field_coverage()
        missed_areas = self._identify_missed_areas()
        return {
            "coverage_percentage": coverage * 100,
            "missed_areas": missed_areas,
            "estimated_remaining_time": self._estimate_remaining_time()
        }
```

---

## 实施路线

### 第 1 阶段: 基础农田仿真 (2-3 周)

```
Week 1:
  ✓ FarmEnvironment 类
  ✓ 地块表示 (矩形、边界、障碍物)
  ✓ 覆盖率计算

Week 2:
  ✓ 农田传感器 (RTK GPS, 行检测, NDVI)
  ✓ 作业反馈模型

Week 3:
  ✓ 简单的平行线路径生成
  ✓ farm_task_manager 节点
  ✓ 集成测试
```

**验证**:
- 生成正确的作业轨迹
- 覆盖率计算准确
- 传感器数据合理

### 第 2 阶段: 执行器和控制 (2-3 周)

```
Week 4:
  ✓ farm_sprayer 节点
  ✓ farm_seeder 节点 (可选)
  ✓ 油箱管理

Week 5:
  ✓ 喷洒反馈 (流量、压力、覆盖率)
  ✓ 故障模拟 (喷嘴堵塞、阀门卡)

Week 6:
  ✓ 完整作业闭环
  ✓ 性能指标计算
```

**验证**:
- 喷洒宽度和流量正确
- 覆盖率算法准确
- 油箱耗尽处理正确

### 第 3 阶段: 高级功能 (3-4 周)

```
Week 7-8:
  ✓ 多机器人仿真
  ✓ 动态障碍物
  ✓ 天气影响 (风漂移、雨停止)

Week 9:
  ✓ 实时决策节点 (避障、路径调整)
  ✓ 数据记录和分析

Week 10:
  ✓ 可视化和监控界面
```

---

## 验证策略

### 1. 单元测试

```python
def test_farm_coverage():
    """覆盖率计算"""
    env = FarmEnvironment(100, 200)
    # 模拟作业 50 个网格
    for i in range(50):
        env.record_work(i, i, 'spraying')

    coverage = env.get_field_coverage()
    assert 0.0 <= coverage <= 1.0
    assert coverage > 0.0  # 应该有覆盖

def test_row_detection():
    """行检测精度"""
    sensors = FarmSensorSimulator(field_env)

    # 测试不同位置
    states = [
        RobotState(x=0.0, y=0.0),      # 行中心
        RobotState(x=0.05, y=0.0),     # 偏离 5cm
        RobotState(x=0.2, y=0.0),      # 偏离 20cm
    ]

    for state in states:
        data = sensors.get_row_detection(state)
        assert 'offset' in data
        assert data['offset'] == pytest.approx(state.x % 0.5)
```

### 2. 场景测试

```yaml
# examples/test_farm_spraying.yaml
# 完整的农田喷洒场景

graph_id: farm_spraying
graph_version: 1
node_hub_path: ./node-hub

nodes:
  - id: farm_gps
    package: sim_gps
    params:
      mode: rtk_fixed
      accuracy: 0.02

  - id: farm_task_manager
    package: farm_task_manager
    params:
      field_width: 100.0
      field_length: 200.0
      swath_width: 12.0

  - id: path_planner
    package: farm_path_planner
    params:
      algorithm: "parallel_lines"
      turn_strategy: "headland"

  - id: spray_controller
    package: farm_spray_controller
    params:
      max_flow_rate: 80.0
      tank_capacity: 200.0

  - id: farm_sprayer
    package: farm_sprayer
    params:
      swath_width: 12.0

edges:
  - from: farm_gps.gps_fix
    to: farm_task_manager.gps_input

  - from: farm_task_manager.target_waypoint
    to: path_planner.current_position

  - from: path_planner.next_waypoint
    to: spray_controller.target_position

  - from: spray_controller.spray_command
    to: farm_sprayer.spray_control
```

### 3. 关键指标验证

| 指标 | 目标 | 验证方法 |
|------|------|---------|
| **定位精度** | ±5cm | 比对真实 RTK 数据 |
| **覆盖均匀性** | >90% | 网格重叠分析 |
| **路径规划效率** | 转向次数最少 | 统计转向数 |
| **喷洒效果** | ±10% 偏差 | 模拟覆盖图 |
| **任务完成度** | 100% 覆盖 | 覆盖率统计 |

---

## 我的设计建议

### 1. **分层架构**

```
应用层:     农田任务规划器 → 作业执行器 → 效果评估
          (Task Manager)  (Sprayer)   (Metrics)

控制层:     路径规划 → 控制算法 → 执行器控制
          (Pathplanner) (Controller) (Actuator Cmd)

传感层:     GPS → 行检测 → 作物信息 → 执行器反馈
          (RTK)  (Vision) (NDVI)     (Feedback)

仿真层:     农田环境 ← 更新位置 ← 物理引擎
          (Field Env)  (State)    (Physics)
```

### 2. **渐进式复杂度**

**Phase 1 (最小化)**: 单行喷洒
- 直线轨迹
- 简单覆盖率计算
- 基本 GPS + 喷洒反馈

**Phase 2 (核心功能)**: 完整地块
- 平行线轨迹
- 转向逻辑
- 重叠处理
- RTK 定位

**Phase 3 (高级)**: 实际农田
- 地形适应
- 动态避障
- 多机协作
- 天气影响

### 3. **关键创新点**

```python
# 高保真覆盖率计算（不是简单的 GPS 位置求和）
class CoverageCalculator:
    def __init__(self, swath_width=12.0):
        self.swath_width = swath_width
        self.coverage_grid = {}  # (x, y) -> coverage_times

    def record_pass(self, trajectory, swath_width):
        """记录一次通过"""
        # 基于喷洒宽度生成覆盖区域
        # 处理重叠
        # 计算均匀性
        for point in trajectory:
            x, y = point
            # 生成覆盖带状区域
            for dy in range(-swath_width/2, swath_width/2):
                cell = (int(x), int(y + dy))
                self.coverage_grid[cell] = self.coverage_grid.get(cell, 0) + 1

    def get_coverage_stats(self):
        """获取覆盖统计"""
        if not self.coverage_grid:
            return {"coverage": 0.0, "uniformity": 0.0}

        total_cells = int(self.width * self.length)
        covered_cells = len(self.coverage_grid)
        coverage = covered_cells / total_cells

        # 计算均匀性（覆盖次数的标准差）
        times = list(self.coverage_grid.values())
        mean = sum(times) / len(times)
        variance = sum((t - mean) ** 2 for t in times) / len(times)
        uniformity = 1 - (variance / mean) if mean > 0 else 0

        return {
            "coverage": coverage,
            "uniformity": uniformity,
            "overlap_percentage": self._calc_overlap(),
            "missed_areas": self._find_missed_areas()
        }
```

### 4. **数据驱动的验证**

```python
# 与实际农田数据对标
class FarmSimulationValidator:
    def __init__(self):
        self.real_data = load_real_farm_data()  # 真实作业数据

    def validate_coverage(self, simulated_coverage):
        """对标真实数据"""
        real_coverage = self.real_data['coverage']
        error = abs(simulated_coverage - real_coverage) / real_coverage
        return error < 0.05  # 误差 <5%

    def validate_efficiency(self, simulated_stats, real_stats):
        """效率对标"""
        metrics = ['time', 'distance', 'fuel_consumption', 'coverage']
        for metric in metrics:
            sim_val = simulated_stats[metric]
            real_val = real_stats[metric]
            error = abs(sim_val - real_val) / real_val
            assert error < 0.1, f"{metric} 误差 {error*100:.1f}%"
```

### 5. **实用工具链**

```bash
# 1. 自动生成作业计划
python3 tools/farm_plan_generator.py \
  --field-width 100 \
  --field-length 200 \
  --swath-width 12.0 \
  --output plan.json

# 2. 模拟和验证
python3 -m runtime.main examples/test_farm_spraying.yaml

# 3. 分析覆盖率
python3 tools/analyze_coverage.py \
  --log .test-reports/farm_spraying.log \
  --output coverage_analysis.html

# 4. 对标真实数据
python3 tools/validate_farm_sim.py \
  --simulated coverage_analysis.json \
  --real real_farm_data.json
```

---

## 预期收获

完整实现后，你将获得：

1. ✅ **准确的作业仿真** - 可信度足以用于算法开发
2. ✅ **性能基准** - 了解真实系统的性能上限
3. ✅ **验证工具** - 在部署前验证算法可靠性
4. ✅ **数据积累** - 建立仿真-真实数据库
5. ✅ **快速迭代** - 算法改进不需要真实田地

---

**下一步建议**:
1. 先实现 FarmEnvironment 和基础传感器 (1 周)
2. 创建一个简单的单行喷洒场景验证  (1 周)
3. 逐步添加复杂性 (平行线、转向、多机等)
4. 与真实农田数据对标优化

你想从哪个模块开始？我可以帮你实现具体的代码。
