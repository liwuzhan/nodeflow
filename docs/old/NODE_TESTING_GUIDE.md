# NodeFlow 节点测试范式

## 测试结构规范

每个节点必须包含 `test/` 文件夹，结构如下：

```
node-hub/
  <node_name>/
    node.yaml               # 节点配置
    run.py                  # 节点主程序
    test/                   # 测试文件夹
      __init__.py           # Python包标识
      test_unit.py          # 单元测试（测试内部逻辑）
      test_integration.py   # 集成测试（测试与SDK交互）
      fixtures/             # 测试数据
        input_*.json        # 输入数据示例
        expected_*.json     # 期望输出示例
      conftest.py           # pytest配置（可选）
```

## 测试层级

### 1. 单元测试 (test_unit.py)

**目的**: 测试节点内部的数据处理逻辑，不依赖SDK

**适用场景**:
- 坐标转换函数
- 数据格式化函数
- 算法实现（如Pure Pursuit、覆盖规划等）
- 数学计算函数

**示例**:
```python
import pytest
from run import TrajectoryVisualizer

def test_coordinate_conversion():
    """测试坐标转换逻辑"""
    visualizer = TrajectoryVisualizer()

    # 输入: [(lon, lat), ...]
    input_coords = [(121.5, 31.2), (121.51, 31.21)]

    # 处理
    visualizer.field_boundary = [(lat, lon) for lon, lat in input_coords]

    # 验证: 应转换为 [(lat, lon), ...]
    assert visualizer.field_boundary[0] == (31.2, 121.5)
    assert visualizer.field_boundary[1] == (31.21, 121.51)

def test_distance_calculation():
    """测试距离计算准确性"""
    visualizer = TrajectoryVisualizer()

    # 两个已知距离的点
    p1 = (31.2, 121.5)
    p2 = (31.201, 121.5)  # 北移约111米

    distance = visualizer._calculate_distance(p1, p2)

    # 允许1%误差
    assert 110 <= distance <= 112
```

### 2. 集成测试 (test_integration.py)

**目的**: 测试节点与SDK的交互，验证数据流

**适用场景**:
- 端口创建和数据收发
- 参数读取
- 完整的数据处理流程
- 错误处理和边界情况

**示例**:
```python
import pytest
import json
from pathlib import Path
from unittest.mock import Mock, patch

def test_node_receives_data():
    """测试节点能正确接收和处理数据"""

    # 加载测试数据
    fixture_path = Path(__file__).parent / "fixtures" / "input_task_request.json"
    with open(fixture_path) as f:
        test_data = json.load(f)

    # 模拟SDK
    mock_sdk = Mock()
    mock_port = Mock()
    mock_port.recv_latest.return_value = test_data
    mock_sdk.create_input_port.return_value = mock_port

    # 运行节点逻辑
    with patch('run.NodeFlowSDK', return_value=mock_sdk):
        from run import TrajectoryVisualizer
        viz = TrajectoryVisualizer()

        # 处理数据
        result = viz.add_field_data(test_data)

        # 验证
        assert result is True
        assert viz.field_boundary is not None
        assert len(viz.field_boundary) == 8

def test_node_handles_invalid_data():
    """测试节点对无效数据的处理"""
    from run import TrajectoryVisualizer

    viz = TrajectoryVisualizer()

    # 测试空数据
    assert viz.add_field_data(None) is False
    assert viz.add_field_data({}) is False

    # 测试格式错误的数据
    assert viz.add_field_data({"parcel": None}) is False
    assert viz.add_field_data({"parcel": {"outer": []}}) is False
```

### 3. 端到端测试 (test_e2e.py)

**目的**: 测试节点在完整工作流中的行为

**适用场景**:
- 多节点协作场景
- 完整任务执行流程
- 性能测试

**示例**:
```python
import pytest
import subprocess
import time
from pathlib import Path

def test_trajectory_viz_workflow():
    """测试轨迹可视化完整工作流"""

    # 启动简化的测试工作流
    config_path = Path(__file__).parent / "fixtures" / "test_workflow.yaml"

    process = subprocess.Popen(
        ["python", "runtime/main.py", str(config_path)],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE
    )

    try:
        # 等待节点启动和运行
        time.sleep(10)

        # 检查输出文件是否生成
        output_dir = Path("./logs/jpg")
        jpg_files = list(output_dir.glob("trajectory_viz_*.jpg"))

        assert len(jpg_files) > 0, "未生成可视化图像"

        # 检查文件大小（确保不是空文件）
        latest_jpg = max(jpg_files, key=lambda p: p.stat().st_mtime)
        assert latest_jpg.stat().st_size > 10000, "生成的图像文件太小"

    finally:
        process.terminate()
        process.wait(timeout=5)
```

## 测试数据管理

### fixtures/ 文件夹规范

```
test/fixtures/
  input_task_request.json      # 任务请求输入示例
  input_global_path.json        # 规划路径输入示例
  input_rtk_fix.json            # RTK数据输入示例
  expected_output.json          # 期望输出示例
  test_workflow.yaml            # 测试用工作流配置
```

### 数据文件命名规范

- `input_<port_name>.json`: 输入端口的测试数据
- `expected_<port_name>.json`: 期望的输出数据
- `test_<scenario>.yaml`: 特定测试场景的配置

## 运行测试

### 单个节点测试

```bash
# 运行某个节点的所有测试
cd node-hub/<node_name>
python -m pytest test/

# 运行特定测试文件
python -m pytest test/test_unit.py

# 显示详细输出
python -m pytest test/ -v

# 显示print输出
python -m pytest test/ -s
```

### 全部节点测试

```bash
# 从项目根目录运行所有节点测试
python -m pytest node-hub/*/test/
```

## pytest配置 (conftest.py)

```python
import pytest
import sys
from pathlib import Path

# 添加项目根路径
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

@pytest.fixture
def fixture_dir():
    """返回测试数据目录路径"""
    return Path(__file__).parent / "fixtures"

@pytest.fixture
def load_fixture():
    """加载JSON测试数据的辅助函数"""
    import json

    def _load(filename):
        fixture_path = Path(__file__).parent / "fixtures" / filename
        with open(fixture_path) as f:
            return json.load(f)

    return _load
```

## 最佳实践

### 1. 测试独立性
- 每个测试应该独立运行
- 不依赖其他测试的执行顺序
- 使用fixture准备测试环境

### 2. 测试覆盖率
- 核心业务逻辑必须有单元测试
- 数据收发逻辑必须有集成测试
- 关键工作流必须有E2E测试

### 3. 测试数据真实性
- 使用真实场景的数据格式
- 包含边界情况和异常情况
- 数据要有代表性

### 4. 测试可维护性
- 使用清晰的测试命名
- 添加必要的注释说明
- 保持测试代码简洁

### 5. 持续集成
- 在CI/CD流程中自动运行测试
- 测试失败时阻止代码合并
- 定期检查测试覆盖率

## 常见测试模式

### 模拟SDK端口

```python
from unittest.mock import Mock

def test_with_mock_port():
    mock_port = Mock()
    mock_port.recv_latest.return_value = {"test": "data"}
    mock_port.send.return_value = None

    # 使用mock port测试
    data = mock_port.recv_latest()
    assert data["test"] == "data"
```

### 临时文件测试

```python
import tempfile
from pathlib import Path

def test_with_temp_file():
    with tempfile.TemporaryDirectory() as tmpdir:
        output_dir = Path(tmpdir)

        # 使用临时目录进行测试
        visualizer = TrajectoryVisualizer(str(output_dir))

        # 验证文件创建
        assert output_dir.exists()
```

### 参数化测试

```python
@pytest.mark.parametrize("input_data,expected", [
    ({"lat": 31.2, "lon": 121.5}, (31.2, 121.5)),
    ({"lat": 40.0, "lon": 116.0}, (40.0, 116.0)),
])
def test_multiple_coordinates(input_data, expected):
    result = process_coordinate(input_data)
    assert result == expected
```

## 测试优先级

**P0 (必须有)**:
- 核心算法的单元测试
- 数据格式转换的单元测试
- 关键工作流的集成测试

**P1 (推荐有)**:
- 错误处理的测试
- 边界情况的测试
- 性能测试

**P2 (可选)**:
- UI相关测试
- 完整E2E测试
- 压力测试

## SDK测试工具库

为了简化节点测试的开发，NodeFlow提供了可复用的SDK测试工具库（`sdk/test_utils`），包含：

### 1. Mock SDK 对象

不需要真实SDK，使用Mock对象在隔离环境中测试节点：

```python
from sdk.test_utils import MockNodeFlowSDK

def test_with_mock_sdk():
    sdk = MockNodeFlowSDK()

    # 创建模拟端口
    input_port = sdk.create_input_port('input')
    output_port = sdk.create_output_port('output')

    # 设置和获取参数
    sdk.params.set('threshold', 0.5)
    value = sdk.params.get('threshold')

    # 模拟数据收发
    input_port.set_data({'task_id': '001', 'data': [...]})
    data = input_port.recv_latest()
    output_port.send({'result': 'processed'})
```

### 2. pytest Fixtures

所有模板中的 `conftest.py` 提供了预配置的fixtures：

```python
# fixtures自动可用于所有测试

def test_with_fixtures(mock_sdk, temp_output_dir, load_fixture):
    # mock_sdk: 预初始化的MockNodeFlowSDK实例
    # temp_output_dir: 临时输出目录（自动清理）
    # load_fixture: 从fixtures/目录加载JSON数据的函数

    data = load_fixture('sample_input.json')
    output_file = temp_output_dir / 'result.txt'
    # ... 测试代码
```

### 3. 测试常量

常用的测试数据和地理坐标：

```python
from sdk.test_utils.test_constants import (
    SHANGHAI_CENTER,
    BEIJING_CENTER,
    SAMPLE_TASK_REQUEST,
    SAMPLE_GLOBAL_PATH,
)

def test_with_constants():
    # 使用预定义的上海中心坐标 (31.2304, 121.4737)
    task = SAMPLE_TASK_REQUEST.copy()
    assert task['target_location'] is not None
```

### 快速开始

请参考 [测试快速开始指南](TESTING_QUICKSTART.md) 了解如何在5分钟内为你的节点添加完整的测试框架。

### 模板使用

为新节点快速创建测试框架：

```bash
# 复制测试模板到你的节点
cp -r .test_template node-hub/<node_name>/test

# 修改模板中的TODO项
cd node-hub/<node_name>/test
# 编辑 conftest.py, data_generator.py, test_unit.py, test_integration.py

# 运行测试
cd ..
python -m pytest test/ -v
```

## 示例节点

参考以下节点的测试实现：
- `trajectory_viz/test/`: 完整的可视化节点测试实现（参考）
- `velocity_controller/test/`: 控制节点测试实现（使用新框架）
- `global_coverage/test/`: 规划节点测试实现（使用新框架）
