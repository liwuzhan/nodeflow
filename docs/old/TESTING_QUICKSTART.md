# 节点测试快速开始（5分钟指南）

> 为你的NodeFlow节点快速添加测试的最快方式

## 1️⃣ 复制测试模板到你的节点

从项目根目录运行：

```bash
# 假设你的节点在 node-hub/my_node/
cp -r .test_template node-hub/my_node/test
```

现在你有了一个完整的测试目录结构：

```
node-hub/my_node/test/
├── __init__.py
├── conftest.py              # pytest配置（修改DEFAULT_MOCK_SDK_PARAMS）
├── data_generator.py        # 你的测试数据生成器（修改generate_sample_input()等）
├── test_unit.py             # 单元测试（修改test_basic_logic()等）
├── test_integration.py      # 集成测试（修改test_receives_input_and_sends_output()等）
└── fixtures/
    └── .gitkeep
```

## 2️⃣ 修改TODO项（按优先级）

### 优先级1：最小可运行版本

打开 `test_unit.py`，修改以下部分（15分钟）：

**步骤1**: 重命名测试类
```python
# 改这行：
class TestYourNodeLogic:
# 为这样：
class TestMyNodeLogic:
```

**步骤2**: 修改setup fixture
```python
@pytest.fixture(autouse=True)
def setup(self):
    # 修改这里：从你的run.py导入你的类
    from run import MyNodeClass  # 改成你的类名
    self.node = MyNodeClass()
```

**步骤3**: 修改test_basic_logic()
```python
def test_basic_logic(self):
    # 修改这里：调用你的节点方法
    result = self.node.process({'input': 'data'})
    assert result is not None
```

**步骤4**: 运行测试！
```bash
cd node-hub/my_node
python -m pytest test/test_unit.py::TestMyNodeLogic::test_basic_logic -v
```

✅ 如果通过，恭喜！你有了第一个测试！

### 优先级2：完整测试（再花30分钟）

1. **填充test_invalid_input()** - 测试错误输入处理
2. **填充test_edge_cases()** - 测试边界情况
3. **填充data_generator.py** - 生成真实格式的测试数据
4. 运行所有单元测试：
   ```bash
   python -m pytest test/test_unit.py -v
   ```

### 优先级3：集成测试（可选，高级用法）

打开 `test_integration.py`，修改：

1. **TestNodeWithSDK** 类 - 测试与SDK的交互
   ```python
   def test_receives_input_and_sends_output(self):
       # 使用 self.sdk (来自mock_sdk fixture)
       input_port = self.sdk.create_input_port('input')
       input_port.set_data({'task_id': '001', 'data': [...]})

       # 运行节点
       result = self.node.process(input_port)

       # 验证输出
       assert result is not None
   ```

2. 运行集成测试：
   ```bash
   python -m pytest test/test_integration.py -v
   ```

## 3️⃣ 运行所有测试

```bash
# 运行你的节点的所有测试
cd node-hub/my_node
python -m pytest test/ -v

# 运行特定测试
python -m pytest test/test_unit.py::TestMyNodeLogic::test_basic_logic -v

# 显示print输出（debug用）
python -m pytest test/ -s

# 运行并显示覆盖率
python -m pytest test/ --cov=. --cov-report=term-missing
```

---

## 🧰 使用SDK测试工具库

所有的Mock工具都在 `sdk.test_utils` 中，你的conftest.py已经自动导入了！

### 常用工具

#### 1. MockSDK（主对象）
```python
def test_something(mock_sdk):
    # mock_sdk 自动由pytest提供
    sdk = mock_sdk

    # 创建端口
    input_port = sdk.create_input_port('my_input')
    output_port = sdk.create_output_port('my_output')

    # 设置参数
    sdk.params.set('threshold', 0.5)

    # 获取参数
    threshold = sdk.params.get('threshold')
```

#### 2. Mock端口（模拟数据收发）
```python
def test_port_interaction(mock_sdk):
    port = mock_sdk.create_input_port('input')

    # 设置要接收的数据
    port.set_data({'sensor': 'gps', 'value': 123.45})

    # 接收数据（模拟）
    data = port.recv_latest()
    assert data['sensor'] == 'gps'

    # 发送数据
    port.send({'result': 'processed'})
```

#### 3. 测试数据常量
```python
from sdk.test_utils import test_constants

# 使用预定义的坐标（上海、北京等）
print(test_constants.SHANGHAI_CENTER)      # (31.2304, 121.4737)
print(test_constants.BEIJING_CENTER)       # (39.9042, 116.4074)

# 使用示例数据结构
print(test_constants.SAMPLE_TASK_REQUEST)  # 任务请求示例
```

#### 4. 临时目录和Fixtures
```python
def test_file_output(temp_output_dir):
    # temp_output_dir 是一个临时目录路径
    output_file = temp_output_dir / 'result.txt'
    output_file.write_text('hello')

    assert output_file.exists()

def test_load_data(load_fixture):
    # 从 test/fixtures/ 目录加载JSON文件
    data = load_fixture('sample_input.json')
    assert data is not None
```

---

## 📋 修改清单

使用这个清单确保你没有遗漏任何TODO：

### test_unit.py
- [ ] 重命名 `TestYourNodeLogic` → `TestMyNodeLogic`
- [ ] 修改 setup() 中的类导入
- [ ] 填充 `test_basic_logic()`
- [ ] 填充 `test_invalid_input()`
- [ ] 填充 `test_edge_cases()`

### data_generator.py
- [ ] 修改 `generate_sample_input()` 返回你的输入格式
- [ ] 修改 `generate_sample_output()` 返回你的输出格式
- [ ] 修改 `create_test_scenario()` 中的场景数据

### conftest.py
- [ ] 修改 `DEFAULT_MOCK_SDK_PARAMS` 中的参数（如果需要）
- [ ] 添加自定义fixtures（如果需要）

### test_integration.py（可选）
- [ ] 重命名 `TestNodeWithSDK` 类
- [ ] 修改 `test_receives_input_and_sends_output()`
- [ ] 修改其他集成测试

---

## ❓ 常见问题

### Q1: 我的导入失败了怎么办？
```
ImportError: cannot import name 'MyNodeClass' from 'run'
```

**答**: 检查 setup() 中的导入语句：
- 确保类名正确（区分大小写）
- 确保run.py中确实有这个类
- 确认文件路径正确（test/目录与run.py在同一父目录）

### Q2: 我不知道输入/输出数据格式
```
AttributeError: dict object has no attribute 'xxx'
```

**答**: 检查你的 `node.yaml`：
- 查看Input/Output port的type和format
- 查看其他使用同类port的节点（如trajectory_viz）
- 参考 `sdk/test_utils/test_constants.py` 中的示例数据

### Q3: 我想测试多组输入数据
使用pytest的parametrize装饰器：
```python
@pytest.mark.parametrize("input_data,expected", [
    ({"value": 1}, {"result": 10}),
    ({"value": 2}, {"result": 20}),
    ({"value": 3}, {"result": 30}),
])
def test_multiple_cases(self, input_data, expected):
    result = self.node.process(input_data)
    assert result['result'] == expected['result']
```

### Q4: 如何测试异常处理？
```python
def test_error_handling(self):
    import pytest

    # 期望节点抛出 ValueError
    with pytest.raises(ValueError):
        self.node.process(invalid_data)

    # 或期望返回错误状态
    result = self.node.process(invalid_data)
    assert result is None or result.get('error') is not None
```

### Q5: 如何查看测试覆盖率？
```bash
# 安装coverage工具
pip install coverage pytest-cov

# 运行测试并生成覆盖率报告
python -m pytest test/ --cov=. --cov-report=html

# 打开覆盖率报告
open htmlcov/index.html  # macOS
# 或 xdg-open htmlcov/index.html  # Linux
```

---

## 🔗 更多资源

- **完整测试指南**: [NODE_TESTING_GUIDE.md](NODE_TESTING_GUIDE.md)
- **参考实现**: 查看 `node-hub/trajectory_viz/test/` 获取完整示例
- **SDK工具库文档**: [SDK Test Utils](#)

---

## ✨ 下一步

1. ✅ 完成你节点的单元测试（优先级1）
2. ✅ 添加集成测试（优先级2）
3. ✅ 在提交代码前运行 `pytest test/ -v` 确保所有测试通过
4. ✅ 考虑添加测试覆盖率检查（目标：≥70%）

**祝你测试顺利！**🚀
