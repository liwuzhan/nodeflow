# NodeFlow 自动化测试指南

本指南说明如何设置和使用 NodeFlow 的自动化测试系统。

---

## 📋 目录

1. [快速开始](#快速开始)
2. [本地测试](#本地测试)
3. [Git Hooks](#git-hooks)
4. [GitHub Actions](#github-actions)
5. [报告查看](#报告查看)
6. [故障排除](#故障排除)

---

## 快速开始

### 安装依赖

```bash
# 安装测试依赖
pip install pytest pyyaml

# 或使用 requirements.txt
pip install -r requirements.txt
```

### 运行快速测试

```bash
# 快速测试（推荐用于日常开发）
bash tools/run_tests.sh quick

# 完整测试（包括单元测试）
bash tools/run_tests.sh full

# 运行场景测试（包括完整的框架测试）
bash tools/run_tests.sh scenario
```

---

## 本地测试

### 方法 1: 使用测试脚本

#### 快速测试 (2-3 分钟)
```bash
bash tools/run_tests.sh quick
```

**包含内容:**
- ✓ Python 语法检查
- ✓ Mock 节点配置验证
- ✓ 测试场景配置检查

**适用场景:** 日常开发、快速反馈

#### 完整测试 (5-10 分钟)
```bash
bash tools/run_tests.sh full
```

**包含内容:**
- ✓ 快速测试的所有项目
- ✓ 单元测试 (pytest)
- ✓ Scenario 1 (单节点框架测试)

**适用场景:** 提交前验证、CI/CD 流程

#### 场景测试 (10-20 分钟)
```bash
bash tools/run_tests.sh scenario
```

**包含内容:**
- ✓ 完整测试的所有项目
- ✓ 可选的完整场景测试

**适用场景:** 发布前验证、问题诊断

### 方法 2: 使用 Python 报告生成器

```bash
# 标准报告（带彩色输出）
python3 tools/test_reporter.py

# 生成 HTML 报告
python3 tools/test_reporter.py --html

# 生成总结报告
python3 tools/test_reporter.py --summary
```

**输出:**
- 📊 彩色终端报告
- 📄 JSON 格式报告
- 📋 HTML 格式报告（可在浏览器查看）

---

## Git Hooks

### 自动化提交后测试

当您执行 `git commit` 时，会自动运行测试并生成报告。

#### 工作流程

```bash
# 1. 修改代码
vim node-hub/mock_gps/run.py

# 2. 暂存更改
git add node-hub/mock_gps/run.py

# 3. 提交（自动触发测试）
git commit -m "fix: 修复 GPS 节点"

# 测试自动运行...
# ✓ 代码语法检查
# ✓ 节点配置验证
# ✓ 测试场景验证
# 📊 报告已保存
```

#### 查看测试报告

```bash
# 查看最新报告
cat .test-reports/test-report-20251220_143020.txt

# 列出所有报告
ls -lt .test-reports/test-report-*.txt | head -5
```

#### 禁用 Hook（如果需要）

```bash
# 跳过提交钩子（不推荐）
git commit --no-verify -m "message"
```

---

## GitHub Actions

### 自动 CI/CD 流程

当代码推送到 GitHub 时，自动运行测试。

#### 工作流配置

**文件:** `.github/workflows/test.yml`

**触发条件:**
- 推送到 `main` 或 `develop` 分支
- 创建 Pull Request

#### 测试矩阵

在以下配置组合上运行测试：

| 操作系统 | Python 版本 |
|--------|-----------|
| Ubuntu | 3.9, 3.10, 3.11 |
| macOS | 3.9, 3.10, 3.11 |

总共 6 个测试组合，并行执行。

#### 查看测试结果

**在 GitHub 上:**
1. 打开 Pull Request
2. 向下滚动找到 "Checks" 部分
3. 点击 "NodeFlow 自动化测试"
4. 查看详细日志

**下载报告:**
- 点击 "Artifacts" 选项卡
- 下载 `test-reports-*.zip` 文件

#### 自动 PR 评论

测试完成后，会自动在 PR 上添加评论，包括：
- 操作系统和 Python 版本
- 测试状态（通过/失败）
- 时间戳

---

## 报告查看

### 报告文件位置

```
.test-reports/
├── test-report-20251220_143020.txt     # 提交钩子生成的文本报告
├── unittest-20251220_143020.log         # 单元测试日志
├── scenario1-20251220_143020.log        # Scenario 1 测试日志
├── report-20251220_143020.json          # JSON 格式报告
└── report-20251220_143020.html          # HTML 格式报告
```

### 查看文本报告

```bash
# 最新的提交钩子报告
cat .test-reports/test-report-*.txt | tail -1

# 最新的 Scenario 1 日志
tail -50 .test-reports/scenario1-*.log
```

### 查看 HTML 报告（推荐）

```bash
# 在浏览器中打开
open .test-reports/report-*.html

# 或从命令行
python3 -m http.server 8000 -d .test-reports
# 然后访问 http://localhost:8000/report-*.html
```

### 解析 JSON 报告

```bash
# 查看 JSON 结构
python3 -m json.tool .test-reports/report-*.json

# 提取特定信息
python3 -c "
import json
with open('.test-reports/report-*.json') as f:
    data = json.load(f)
    print(f\"通过的测试: {sum(1 for t in data['tests'].values() if t['status'] == 'pass')}/3\")
    print(f\"Python 文件: {data['summary']['python_files']}\")
    print(f\"代码行数: {data['summary']['total_lines']}\")
"
```

---

## 报告说明

### 测试内容

#### 1. 代码语法检查
检查所有 Python 文件是否有语法错误

```
✓ Python 文件语法检查通过
  - 检查对象: runtime/, sdk/, node-hub/mock_*
  - 总文件数: 50+
```

#### 2. Mock 节点配置验证
验证 10 个 Mock 节点是否配置完整

```
✓ 所有 10 个 Mock 节点配置完整
  - 检查内容: node.yaml, run.py, README.md
  - 节点列表: mock_joystick, mock_gps, ... (10 个)
```

#### 3. 测试场景配置检查
验证 7 个测试场景配置文件是否有效

```
✓ 所有 7 个测试场景配置有效
  - 检查内容: YAML 语法、文件存在性
  - 场景列表: test_mock_single, test_mock_chain, ... (7 个)
```

#### 4. 单元测试
运行 pytest 单元测试

```
✓ 单元测试通过 (4/4)
  - 测试文件: tests/unit/test_yaml_parser.py
  - 测试项: 配置解析、验证等
```

#### 5. 场景测试（可选）
运行完整的框架集成测试

```
✓ Scenario 1 运行成功 (20 秒)
  - 验证内容: 节点启动、数据流、稳定性
```

### 统计信息

报告会包含项目统计：

```
Python 文件数:      50+
代码行数:          10000+
YAML 配置文件:       20+
文档文件:           15+

Git 提交:          abc1234 (用户名)
生成时间:          2025-12-20 14:30:20
```

---

## 最佳实践

### 开发流程

```
1. 修改代码
   ↓
2. 运行快速测试
   git commit  (自动运行提交钩子)
   ↓
3. 推送到 GitHub
   (自动运行 GitHub Actions)
   ↓
4. 查看 PR 测试结果
   ↓
5. 合并到主分支
```

### 推荐命令

```bash
# 日常开发（快速反馈）
bash tools/run_tests.sh quick

# 提交前（确保不出错）
bash tools/run_tests.sh full

# 发布前（完整验证）
python3 tools/test_reporter.py --html
# 然后在浏览器查看 HTML 报告

# 批量查看报告
ls -lht .test-reports/test-report-*.txt | head -10
```

---

## 故障排除

### Hook 没有运行

**问题:** 提交后没有看到测试输出

**解决:**
```bash
# 1. 检查 hook 是否可执行
ls -l .git/hooks/post-commit

# 2. 手动运行 hook
bash .git/hooks/post-commit

# 3. 如果 hook 脚本损坏，重新安装
cp tools/hooks/post-commit .git/hooks/post-commit
chmod +x .git/hooks/post-commit
```

### 测试脚本错误

**问题:** `bash: tools/run_tests.sh: Permission denied`

**解决:**
```bash
# 添加执行权限
chmod +x tools/run_tests.sh
```

### Python 模块找不到

**问题:** `ModuleNotFoundError: No module named 'yaml'`

**解决:**
```bash
# 安装缺失的包
pip install pyyaml pytest

# 或使用 requirements.txt
pip install -r requirements.txt
```

### GitHub Actions 失败

**问题:** GitHub Actions 中测试失败

**解决:**
1. 查看 "Actions" 标签页
2. 点击最新的工作流运行
3. 展开失败的任务查看详细日志
4. 根据日志修复问题
5. 推送新的提交以重新触发测试

---

## 配置说明

### Hook 脚本（.git/hooks/post-commit）

自动在每次提交后运行，执行：
- ✓ 代码编译检查
- ✓ 节点配置验证
- ✓ 测试场景检查
- ✓ 生成测试报告

### 测试脚本（tools/run_tests.sh）

手动运行的测试套件，支持三种模式：
- `quick` - 快速检查（2-3 分钟）
- `full` - 完整测试（5-10 分钟）
- `scenario` - 场景测试（10-20 分钟）

### CI/CD 工作流（.github/workflows/test.yml）

GitHub Actions 自动测试配置，在 6 个矩阵组合上运行。

---

## 进阶用法

### 生成覆盖率报告

```bash
# 安装 coverage
pip install coverage

# 运行测试并生成覆盖率
coverage run -m pytest tests/
coverage report
coverage html

# 在浏览器查看
open htmlcov/index.html
```

### 性能基准测试

```bash
# 创建性能测试脚本
python3 tools/benchmark.py

# 查看性能报告
cat .test-reports/benchmark-*.txt
```

### 自定义测试钩子

编辑 `.git/hooks/post-commit` 添加自定义检查：

```bash
# 在末尾添加
echo "运行自定义检查..."
python3 my_custom_test.py || exit 1
```

---

## 参考资源

- [pytest 文档](https://docs.pytest.org/)
- [GitHub Actions 文档](https://docs.github.com/en/actions)
- [Git Hooks 文档](https://git-scm.com/book/en/v2/Customizing-Git-Git-Hooks)

---

**最后更新:** 2025-12-20
**维护者:** NodeFlow 团队
