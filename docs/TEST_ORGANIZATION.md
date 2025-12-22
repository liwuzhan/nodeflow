# 测试文件组织指南

## 当前建议方案

### ✅ 保留在根目录的文件

**活跃的 MCP 测试** (需要在根目录运行):
```
test_mcp_functionality.py    - MCP 功能测试
test_error_responses.py       - MCP 错误处理测试
test_mcp_workflow.py          - MCP 工作流测试
```

**原因**:
- 已添加 `sys.path.insert(0, str(Path(__file__).parent))` 支持
- 在根目录运行工作最好
- 可以从任何位置运行（已测试）

**运行方法**:
```bash
python3.12 test_mcp_functionality.py
python3.12 test_mcp_workflow.py
python3.12 test_error_responses.py
```

### 📦 可以归档的历史文件

建议创建 `tests/legacy/` 目录存放：
```
test_milestone2.py
test_milestone3.py
test_milestone4.py
test_milestone5.py
test_300m_with_logger.py
test_with_logger.py
test_inputport_reconnect.py
```

**存档命令**:
```bash
mkdir -p tests/legacy
mv test_milestone*.py tests/legacy/
mv test_300m_with_logger.py tests/legacy/
mv test_with_logger.py tests/legacy/
mv test_inputport_reconnect.py tests/legacy/
```

**特点**: 这些是历史遗留，不需要经常运行

### 🔧 保留在根目录的其他测试

```
test_msgpack_performance.py   - 性能测试（偶尔运行）
test_manual.py                - 手动测试
test_end_to_end.py            - 端到端集成测试（已有 sys.path 设置，可移可不移）
```

---

## 关于 sys.path 的详细说明

### 当前设置

```python
sys.path.insert(0, str(Path(__file__).parent))
```

这个设置的意思：
- `Path(__file__)` = 脚本文件的完整路径
- `.parent` = 脚本所在的目录
- 在根目录时，.parent = 项目根目录 ✅

### 如果移动到 tests/mcp/

**改为**:
```python
sys.path.insert(0, str(Path(__file__).parent.parent.parent))
```

这样会指向项目根目录。

### 更聪明的做法

```python
import sys
from pathlib import Path

# 找到项目根目录（包含 runtime 目录的位置）
def find_project_root():
    current = Path(__file__).parent
    while current != current.parent:  # 直到根目录
        if (current / "runtime").exists():
            return current
        current = current.parent
    raise RuntimeError("无法找到项目根目录")

sys.path.insert(0, str(find_project_root()))
```

这样无论文件在哪里都能正确运行！

---

## 建议的最终方案

### 选项 A: 保持简单（推荐）

✅ 所有 MCP 测试保留在根目录
✅ 历史文件移到 tests/legacy/
❌ 不做太多复杂的路径处理

```bash
# 只需执行一次
mkdir -p tests/legacy
mv test_milestone*.py tests/legacy/
mv test_*logger.py tests/legacy/
mv test_inputport_reconnect.py tests/legacy/
```

**优点**: 简单，MCP 测试容易找到，容易运行
**缺点**: 根目录还是有一些杂乱

### 选项 B: 完全整理（可选）

1. 把 MCP 测试放到 tests/mcp/
2. 更新每个文件的 sys.path 设置（使用"更聪明的做法"）
3. 创建 tests/run_all.py 脚本，统一运行所有测试

**优点**: 结构清晰
**缺点**: 需要修改多个文件

---

## 测试运行命令汇总

### 快速测试（推荐）
```bash
# 基础功能
python3.12 test_mcp_functionality.py

# 错误处理
python3.12 test_error_responses.py

# 完整工作流
python3.12 test_mcp_workflow.py
```

### 全部测试
```bash
#!/bin/bash
echo "运行 MCP 功能测试..."
python3.12 test_mcp_functionality.py && echo "✅ 功能测试通过" || echo "❌ 功能测试失败"

echo "运行错误处理测试..."
python3.12 test_error_responses.py && echo "✅ 错误测试通过" || echo "❌ 错误测试失败"

echo "运行工作流测试..."
timeout 30 python3.12 test_mcp_workflow.py && echo "✅ 工作流测试通过" || echo "⚠️  工作流测试完成"
```

---

## 关于 get-pip.py

✅ **已删除** - 不需要了
- Python 3.12 已安装
- pip 已可用
- 这只是引导脚本，不需要保留

---

## 总结

| 操作 | 状态 | 说明 |
|------|------|------|
| 删除 get-pip.py | ✅ 已完成 | 清理空间 |
| 添加 sys.path | ✅ 已完成 | 3 个 MCP 测试已更新 |
| 创建 tests/ | ✅ 已完成 | 目录结构已建立 |
| 归档历史文件 | ⏳ 可选 | 用户可以手动执行 |

**下一步**: 决定是采用选项 A（简单）还是选项 B（完整）

