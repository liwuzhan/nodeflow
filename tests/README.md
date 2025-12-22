# 测试文件组织说明

## 📁 目录结构

```
tests/
├── mcp/                    # MCP 服务相关测试（主要）
│   ├── test_mcp_functionality.py      # MCP 功能测试
│   ├── test_error_responses.py        # 错误处理测试
│   └── test_mcp_workflow.py           # AI 工作流程测试
│
├── integration/            # 集成和性能测试
│   ├── test_end_to_end.py             # 端到端集成测试
│   ├── test_300m_with_logger.py       # 长距离测试
│   ├── test_with_logger.py            # 日志集成测试
│   └── test_msgpack_performance.py    # 性能测试
│
├── legacy/                 # 历史遗留测试（存档）
│   ├── test_milestone2.py
│   ├── test_milestone3.py
│   ├── test_milestone4.py
│   ├── test_milestone5.py
│   ├── test_inputport_reconnect.py
│   └── test_manual.py
│
├── fixtures/               # 测试数据和 fixtures（预留）
├── unit/                   # 单元测试（预留）
└── README.md              # 本文件
```

## 🚀 运行测试

### 前提条件

```bash
# 确保在项目根目录
cd /Users/wuzhanli/Desktop/node

# 确保 Python 3.12 已安装
python3.12 --version
```

### MCP 服务测试（推荐）

运行单个测试：
```bash
# 功能测试
python3.12 tests/mcp/test_mcp_functionality.py

# 错误处理测试
python3.12 tests/mcp/test_error_responses.py

# 完整工作流测试
python3.12 tests/mcp/test_mcp_workflow.py
```

运行所有 MCP 测试：
```bash
python3.12 tests/mcp/test_mcp_functionality.py && \
python3.12 tests/mcp/test_error_responses.py && \
python3.12 tests/mcp/test_mcp_workflow.py
```

### 集成测试

```bash
# 端到端测试
python3.12 tests/integration/test_end_to_end.py

# 性能测试
python3.12 tests/integration/test_msgpack_performance.py

# 其他集成测试
python3.12 tests/integration/test_300m_with_logger.py
python3.12 tests/integration/test_with_logger.py
```

### 历史测试（可选）

这些是之前的 milestone 测试，保留用于参考：

```bash
python3.12 tests/legacy/test_milestone2.py
python3.12 tests/legacy/test_milestone3.py
# 等等...
```

## 📊 测试覆盖范围

| 测试文件 | 覆盖范围 | 耗时 | 状态 |
|---------|---------|------|------|
| test_mcp_functionality.py | 基础功能（5 个） | ~5s | ✅ |
| test_error_responses.py | 错误处理（7 个） | ~3s | ✅ |
| test_mcp_workflow.py | 完整工作流（5 个） | ~20s | ✅ |
| test_end_to_end.py | 端到端集成 | ~10s | ✅ |

## 🔧 路径管理

所有测试都配置了动态路径支持：

```python
sys.path.insert(0, str(Path(__file__).parent.parent.parent))
```

这意味着：
- ✅ 无需手动设置 PYTHONPATH
- ✅ 可以从项目任何位置运行
- ✅ 自动指向项目根目录
- ✅ 能正确导入 `runtime_manager`, `mcp_server` 等模块

## 💡 最佳实践

### 日常使用

快速验证 MCP 服务：
```bash
# 只需运行功能测试
python3.12 tests/mcp/test_mcp_functionality.py
```

完整验证：
```bash
# 运行所有 MCP 测试
for test in tests/mcp/test_*.py; do
    echo "Running $test..."
    python3.12 "$test" || exit 1
done
```

### 自动化脚本

创建 `run_tests.sh`：

```bash
#!/bin/bash
set -e

echo "🧪 运行 MCP 测试..."
python3.12 tests/mcp/test_mcp_functionality.py
python3.12 tests/mcp/test_error_responses.py
python3.12 tests/mcp/test_mcp_workflow.py

echo "✅ 所有测试通过！"
```

### CI/CD 集成

如果使用 GitHub Actions：

```yaml
name: Tests

on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v2
      - name: Set up Python 3.12
        uses: actions/setup-python@v2
        with:
          python-version: '3.12'
      - name: Install dependencies
        run: pip install -r requirements.txt
      - name: Run MCP tests
        run: |
          python3.12 tests/mcp/test_mcp_functionality.py
          python3.12 tests/mcp/test_error_responses.py
          python3.12 tests/mcp/test_mcp_workflow.py
```

## 📝 添加新测试

### 新增 MCP 功能测试

1. 创建文件：`tests/mcp/test_new_feature.py`
2. 添加 sys.path 配置：
   ```python
   import sys
   from pathlib import Path
   sys.path.insert(0, str(Path(__file__).parent.parent.parent))
   ```
3. 导入需要的模块并编写测试

### 新增集成测试

1. 创建文件：`tests/integration/test_new_integration.py`
2. 同样添加 sys.path 配置
3. 编写测试代码

### 新增历史/存档测试

1. 创建文件：`tests/legacy/test_archived.py`
2. 根据需要添加 sys.path 配置

## 🐛 调试技巧

### 运行单个测试函数

如果测试框架支持（如 pytest）：

```bash
python3.12 -m pytest tests/mcp/test_mcp_functionality.py::test_function_name
```

### 启用详细输出

大多数测试会打印详细信息，可以直接查看：

```bash
python3.12 tests/mcp/test_mcp_functionality.py 2>&1 | tee test_output.log
```

### 检查导入问题

如果遇到导入错误：

```bash
python3.12 -c "
import sys
from pathlib import Path
sys.path.insert(0, str(Path('tests/mcp').parent.parent.parent))
try:
    from runtime_manager import RuntimeManager
    print('✅ 导入成功')
except ImportError as e:
    print(f'❌ 导入失败: {e}')
"
```

## 📚 相关文档

- `docs/TEST_ORGANIZATION.md` - 详细的组织说明
- `docs/MCP_SERVICE_COMPLETION_REPORT.md` - MCP 服务完成报告
- `docs/MCP_DEPLOYMENT_GUIDE.md` - 部署和使用指南

## 🎯 快速参考

```bash
# 显示所有可用的测试
find tests -name "test_*.py" -type f | sort

# 运行所有测试
find tests -name "test_*.py" -type f | xargs -I {} python3.12 {}

# 只运行 MCP 测试
ls tests/mcp/test_*.py | xargs -I {} python3.12 {}

# 统计测试数量
find tests -name "test_*.py" -type f | wc -l
```

---

**最后更新**: 2025-12-22
**组织完成**: ✅
**所有测试状态**: ✅ 通过并验证
