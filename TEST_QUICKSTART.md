# NodeFlow 自动测试快速开始 ⚡

**只需 3 步，即刻启用自动化测试！**

---

## ✅ 已配置完成

你的 NodeFlow 项目已经配置好自动测试系统，开箱即用！

**✓** Git Hook 自动测试
**✓** 手动测试脚本
**✓** GitHub Actions CI/CD
**✓** 多格式测试报告

---

## 🚀 立即使用

### 方式 1: Git 提交自动测试（推荐）

```bash
# 正常提交代码
git add .
git commit -m "your commit message"

# ✨ 自动运行测试并生成报告！
# 报告保存在: .test-reports/test-report-*.txt
```

**无需任何额外操作！** 每次 commit 后自动测试 ✅

---

### 方式 2: 手动运行测试

```bash
# 快速测试（2-3 分钟，推荐日常使用）
bash tools/run_tests.sh quick

# 完整测试（5-10 分钟，推荐提交前）
bash tools/run_tests.sh full

# Python 报告生成器（带彩色输出）
python3 tools/test_reporter.py
```

---

### 方式 3: 查看测试报告

```bash
# 查看最新的文本报告
cat .test-reports/test-report-*.txt

# 生成并查看 HTML 报告（推荐）
python3 tools/test_reporter.py --html
open .test-reports/report-*.html

# 查看 JSON 报告
python3 -m json.tool .test-reports/report-*.json
```

---

## 📊 测试内容

每次自动测试包括：

1. **✓ 代码语法检查** - 所有 Python 文件编译验证
2. **✓ Mock 节点配置** - 10 个节点配置完整性
3. **✓ 测试场景配置** - 7 个场景 YAML 有效性
4. **✓ 单元测试** - pytest 测试套件（可选）
5. **✓ 统计信息** - 代码行数、文件数等

---

## 📄 测试报告示例

```
================================================
NodeFlow 自动测试报告 - 2025-12-20 13:59:23
================================================

[1] 代码语法检查        ✓ PASS
[2] Mock 节点配置       ✓ PASS (10/10)
[3] 测试场景配置       ✓ PASS (7/7)
[4] 单元测试           ✓ PASS (4 tests)

【统计信息】
  Python 文件数: 75
  代码行数: 10,790
  YAML 配置: 32
  文档文件: 15
  Git 提交: e635d28

================================================
✓ 测试完成，报告已保存
================================================
```

---

## 🎯 典型工作流程

```
修改代码
  ↓
git add <files>
  ↓
git commit -m "message"    ← 自动测试运行
  ↓
查看报告（可选）
  cat .test-reports/test-report-*.txt
  ↓
git push                   ← GitHub Actions 自动测试
```

---

## 🔍 GitHub Actions

推送到 GitHub 后自动运行：

- **6 个测试环境** - Ubuntu/macOS × Python 3.9/3.10/3.11
- **自动 PR 评论** - 测试结果直接显示在 PR 中
- **报告下载** - 从 Actions → Artifacts 下载完整报告

---

## 📚 详细文档

需要更多信息？查看完整文档：

- **TESTING_GUIDE.md** - 完整使用指南 (6000+ 字)
- **docs/AUTO_TEST_SETUP.md** - 配置说明和验证结果

---

## ❓ 常见问题

### Q: 如何禁用自动测试？

```bash
# 跳过提交钩子（不推荐）
git commit --no-verify -m "message"
```

### Q: 如何只运行快速测试？

```bash
# 使用 quick 模式（不包含单元测试和场景测试）
bash tools/run_tests.sh quick
```

### Q: 测试报告保存在哪里？

```
.test-reports/
├── test-report-*.txt      # Git hook 生成的报告
├── report-*.json          # Python 生成的 JSON 报告
└── report-*.html          # Python 生成的 HTML 报告
```

### Q: GitHub Actions 失败了怎么办？

1. 打开 GitHub 仓库
2. 点击 "Actions" 标签
3. 点击失败的工作流
4. 查看详细日志
5. 修复问题后重新推送

---

## ⚡ 快速命令速查

```bash
# 提交代码（自动测试）
git commit -m "message"

# 手动快速测试
bash tools/run_tests.sh quick

# 生成 HTML 报告
python3 tools/test_reporter.py --html

# 查看最新报告
cat .test-reports/test-report-*.txt

# 列出所有报告
ls -lt .test-reports/
```

---

## 🎉 开始使用

现在就提交你的第一个改动，体验自动化测试！

```bash
# 示例
echo "# Test" >> README.md
git add README.md
git commit -m "test: 测试自动化测试系统"

# 观察自动测试运行...
# 报告自动生成！
```

---

**就是这么简单！** 🚀

**问题反馈**: 查看 `TESTING_GUIDE.md` 中的故障排除部分

**配置完成时间**: 2025-12-20
**测试状态**: ✅ 全部通过
