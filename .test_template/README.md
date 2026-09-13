# 节点测试模板

本目录是 NodeFlow 节点测试的标准模板。为你的节点添加测试时，请按照以下步骤操作。

## 快速开始

### 步骤1：复制模板

```bash
cp -r .test_template node-hub/<your_node>/test
cd node-hub/<your_node>/test
```

### 步骤2：按照TODO修改文件

每个文件中都有 `TODO: ...` 注释，指示需要修改的地方。

**优先级顺序**：
1. `data_generator.py` - 定义你的节点输入数据格式
2. `conftest.py` - 配置pytest和fixtures（通常不需要修改）
3. `test_unit.py` - 编写单元测试（测试纯业务逻辑）
4. `test_integration.py` - 编写集成测试（测试SDK交互）

### 步骤3：运行测试

```bash
# 运行所有测试
python3 -m pytest . -v

# 运行单元测试
python3 -m pytest test_unit.py -v

# 显示print输出
python3 -m pytest . -s

# 运行特定测试
python3 -m pytest test_unit.py::TestMyClass::test_my_function -v
```

## 文件说明

### 目录结构

```
test/
├── conftest.py              # pytest配置和fixtures
├── data_generator.py        # 生成测试数据
├── test_unit.py            # 单元测试
├── test_integration.py      # 集成测试
├── __init__.py             # Python包标识
├── README.md               # 本文件
└── fixtures/               # 测试数据存放目录
    ├── .gitkeep
    ├── sample_input.json   # TODO: 添加示例输入
    └── ...
```

### conftest.py

pytest配置文件。提供可复用的fixtures。

**需要修改**：
- `load_fixture()` - 如需自定义fixture加载逻辑

**通常不需要修改**：
- 标准fixtures（`mock_sdk`, `temp_output_dir`等）已在SDK工具库中提供

### data_generator.py

生成测试数据的工具。定义你的节点的输入输出格式。

**必需修改**：
- `TestDataGenerator` - 添加特定于你节点的数据生成方法
- 调整坐标范围、参数值等

**示例**：
```python
@staticmethod
def generate_task_data():
    """生成任务数据"""
    # TODO: 根据你的节点输入端口格式生成数据
    return {
        "task_id": "test_001",
        ...
    }
```

### test_unit.py

单元测试 - 测试你的节点的内部业务逻辑，不依赖SDK。

**必需修改**：
- `TestYourNodeLogic` - 添加测试你节点的数据处理逻辑
- 导入 `from run import YourNodeClass`
- 编写断言验证输出

**测试什么**：
- 数据转换函数
- 算法实现
- 错误处理
- 边界情况

**示例**：
```python
def test_data_processing(self):
    """测试数据处理逻辑"""
    # TODO: 修改为你的测试
    from run import MyProcessor

    processor = MyProcessor()
    result = processor.process({'input': 'data'})

    assert result is not None
    assert result['output'] == 'expected'
```

### test_integration.py

集成测试 - 测试你的节点与SDK的交互。

**必需修改**：
- `TestYourNodeIntegration` - 添加集成测试
- 模拟输入端口数据
- 验证输出端口的send调用

**测试什么**：
- 端口创建和数据收发
- 参数读取
- 完整工作流
- 错误处理

**示例**：
```python
def test_node_with_data(self, mock_sdk):
    """测试节点与SDK的交互"""
    # TODO: 修改为你的测试

    input_port = mock_sdk.create_input_port('input')
    output_port = mock_sdk.create_output_port('output')

    test_data = {'key': 'value'}
    input_port.set_data(test_data)

    # 运行你的节点逻辑
    # ...

    # 验证输出
    assert output_port.was_send_called()
```

### fixtures/

存放测试数据（JSON文件）。

**应创建**：
- `sample_input_<scenario>.json` - 输入数据示例
- `sample_output_<scenario>.json` - 期望输出示例

## 修改清单

使用此清单确保所有必需步骤都已完成：

- [ ] **data_generator.py**
  - [ ] 修改 `generate_input_data()` 或添加新方法
  - [ ] 验证数据格式与你的节点输入端口匹配
  - [ ] 添加至少3个测试场景

- [ ] **test_unit.py**
  - [ ] 导入你的节点类
  - [ ] 编写至少5个单元测试
  - [ ] 覆盖主要逻辑和边界情况

- [ ] **test_integration.py**
  - [ ] 编写至少3个集成测试
  - [ ] 验证SDK端口的正确交互
  - [ ] 测试完整工作流

- [ ] **fixtures/**
  - [ ] 添加样本输入JSON文件
  - [ ] 添加样本输出JSON文件
  - [ ] 确保文件格式与你的节点兼容

- [ ] **运行测试**
  - [ ] `pytest . -v` 所有测试通过
  - [ ] `pytest . --cov` 覆盖率≥70%
  - [ ] `pytest . -s` 检查输出是否合理

## 常见问题

### Q: 如何导入我的节点？

A: 在测试文件中使用相对导入：

```python
import sys
from pathlib import Path

# 添加父目录到路径
node_dir = Path(__file__).parent.parent
sys.path.insert(0, str(node_dir))

from run import MyNodeClass
```

### Q: 如何使用Mock SDK？

A: 导入并使用fixtures：

```python
def test_something(mock_sdk):
    # mock_sdk 是 MockNodeFlowSDK 实例
    port = mock_sdk.create_input_port('input')
    port.set_data({'test': 'data'})

    # 运行你的节点代码
    assert port.recv_latest() == {'test': 'data'}
```

### Q: 如何访问测试常量？

A: 从工具库导入：

```python
from sdk.test_utils import TEST_CONSTANTS

lat = TEST_CONSTANTS.SHANGHAI_CENTER_LAT
lon = TEST_CONSTANTS.SHANGHAI_CENTER_LON
```

### Q: 如何测试文件输出？

A: 使用 `temp_output_dir` fixture：

```python
def test_file_output(temp_output_dir):
    output_file = temp_output_dir / 'output.jpg'

    # 生成输出...

    assert output_file.exists()
    assert output_file.stat().st_size > 0
```

## 参考资源

- **完整测试指南**: [docs/NODE_TESTING_GUIDE.md](../docs/NODE_TESTING_GUIDE.md)
- **快速开始**: [docs/TESTING_QUICKSTART.md](../docs/TESTING_QUICKSTART.md)
- **参考实现**: [node-hub/trajectory_viz/test/](../node-hub/trajectory_viz/test/)
- **SDK工具库**: [sdk/test_utils/](../sdk/test_utils/)

## 获取帮助

- 查看 `trajectory_viz` 的实际测试实现作为参考
- 阅读 `docs/NODE_TESTING_GUIDE.md` 获取详细指导
- 使用 `sdk.test_utils` 中的便利函数
