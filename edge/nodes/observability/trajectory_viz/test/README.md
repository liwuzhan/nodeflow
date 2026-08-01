# trajectory_viz 节点测试

本目录包含 `trajectory_viz` 节点的完整测试套件。

## 测试结构

```
test/
  ├── README.md                    # 本文件
  ├── conftest.py                  # pytest配置和fixtures
  ├── data_generator.py            # 测试数据生成器
  ├── test_unit.py                 # 单元测试（17个测试）
  ├── test_integration.py          # 集成测试（17个测试）
  └── fixtures/                    # 测试数据
      ├── scenario_basic.json      # 基础场景完整数据
      ├── scenario_irregular.json  # 不规则场景完整数据
      ├── scenario_large.json      # 大地块场景完整数据
      ├── input_*_task_request.json
      ├── input_*_global_path.json
      └── input_*_rtk_trajectory.json
```

## 运行测试

### 运行所有测试

```bash
cd /Users/wuzhanli/Desktop/node/node-hub/trajectory_viz
python3 -m pytest test/ -v
```

### 运行特定测试类型

```bash
# 只运行单元测试
python3 -m pytest test/test_unit.py -v

# 只运行集成测试
python3 -m pytest test/test_integration.py -v

# 运行特定测试类
python3 -m pytest test/test_unit.py::TestCoordinateConversion -v

# 运行特定测试函数
python3 -m pytest test/test_unit.py::TestCoordinateConversion::test_field_boundary_conversion -v
```

### 显示详细输出

```bash
# 显示print输出
python3 -m pytest test/ -s

# 显示详细错误信息
python3 -m pytest test/ -v --tb=short

# 停在第一个失败
python3 -m pytest test/ -x
```

### 使用标记运行

```bash
# 只运行单元测试（快速）
python3 -m pytest test/ -m unit

# 只运行集成测试
python3 -m pytest test/ -m integration

# 只运行可视化测试
python3 -m pytest test/ -m visualization
```

## 测试覆盖

### 单元测试 (test_unit.py)

测试节点内部逻辑，不依赖SDK或外部系统：

- **数据处理测试**: 地块数据、路径数据、GPS点添加
- **坐标转换测试**: (lon, lat) ↔ (lat, lon) 转换
- **距离计算测试**: 距离计算准确性
- **指标计算测试**: 横向误差、路径长度等统计
- **边界情况测试**: 空数据、最小数据集、大数据集

### 集成测试 (test_integration.py)

测试节点与SDK的交互和完整工作流：

- **SDK端口交互**: 端口创建、数据收发
- **节点初始化**: 参数读取、输出目录创建
- **完整工作流**: 端到端可视化流程
- **数据验证**: 无效数据处理、类型转换
- **错误处理**: 异常值处理、优雅降级
- **指标报告**: 输出格式验证
- **场景测试**: 不同场景下的节点行为

## 测试数据

### 预生成的fixture

所有测试数据在测试运行前已经生成，存储在 `fixtures/` 目录下：

- **scenario_basic.json**: 100m×200m 矩形地块，3m行距，80个路径点
- **scenario_irregular.json**: 150m半径不规则8边形地块，4m行距
- **scenario_large.json**: 300m×500m 大地块，3.5m行距

### 数据生成器

`data_generator.py` 提供了可编程的测试数据生成：

```python
from data_generator import create_test_scenario

# 生成新的测试场景
scenario = create_test_scenario("basic")

# scenario包含:
# - task_request: 地块信息
# - global_path: 规划路径
# - rtk_fixes: GPS轨迹点
# - field_boundary: 地块边界（原始格式）
# - planned_path: 规划路径（原始格式）
# - actual_trajectory: 实际轨迹（原始格式）
```

### conftest fixtures

```python
def test_example(basic_task_request, basic_global_path, basic_rtk_trajectory):
    # 直接使用预加载的测试数据
    # basic_task_request: dict
    # basic_global_path: dict
    # basic_rtk_trajectory: list[dict]
    pass

def test_example2(complete_scenario):
    # 获取完整场景数据
    # complete_scenario: dict with all data
    task = complete_scenario["task_request"]
    path = complete_scenario["global_path"]
    rtk_fixes = complete_scenario["rtk_fixes"]
    pass

def test_example3(temp_output_dir):
    # 使用临时输出目录（自动清理）
    # temp_output_dir: Path object
    pass
```

## 当前测试状态

✅ **34个测试全部通过**

- 单元测试: 17/17 通过
- 集成测试: 17/17 通过
- 测试覆盖率: 覆盖所有主要功能

⚠️ **已知警告**

- 中文字体缺失警告（不影响测试，仅影响可视化中文显示）
- matplotlib polygon color属性警告（不影响功能）

## 添加新测试

### 1. 添加单元测试

在 `test_unit.py` 中添加测试函数：

```python
def test_my_new_feature(self, complete_scenario):
    """测试新功能"""
    from run import TrajectoryVisualizer

    viz = TrajectoryVisualizer()

    # 测试逻辑
    result = viz.some_method()

    # 断言
    assert result is not None
```

### 2. 添加集成测试

在 `test_integration.py` 中添加测试函数：

```python
def test_my_integration(self, temp_output_dir, complete_scenario):
    """测试集成场景"""
    from run import TrajectoryVisualizer

    viz = TrajectoryVisualizer(output_dir=str(temp_output_dir))

    # 模拟完整工作流
    viz.add_field_data(complete_scenario["task_request"])
    viz.add_path_data(complete_scenario["global_path"])

    # 断言
    assert viz.is_ready() is True
```

### 3. 添加新的测试数据

修改 `data_generator.py` 并重新生成fixtures：

```bash
cd test
python3 data_generator.py
```

## 持续集成

建议在CI/CD流程中添加：

```yaml
# .github/workflows/test.yml
- name: Test trajectory_viz
  run: |
    cd node-hub/trajectory_viz
    python3 -m pytest test/ -v --tb=short
```

## 故障排查

### 导入错误

如果遇到 `ModuleNotFoundError: No module named 'run'`，确认：
- 从 `node-hub/trajectory_viz/` 目录运行pytest
- `conftest.py` 正确配置了 `sys.path`

### 测试数据缺失

如果 fixture 加载失败：
```bash
cd test
python3 data_generator.py  # 重新生成测试数据
```

### matplotlib 警告

中文字体警告不影响测试通过，仅影响可视化输出的中文显示。

## 最佳实践

1. **保持测试独立**: 每个测试应该能独立运行
2. **使用fixtures**: 避免在测试中硬编码数据
3. **清晰的测试名称**: 测试名称应描述测试内容
4. **添加文档字符串**: 说明测试的目的和预期行为
5. **定期运行测试**: 在修改代码后立即运行测试
