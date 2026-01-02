# NodeFlow 快速环境检查

## 🚀 一键检查脚本

运行此脚本快速验证环境：

```bash
# 检查 Python 版本
python3.12 --version || echo "❌ Python 3.12 未安装"

# 检查所有依赖
python3.12 -c "
import sys
print('Python:', sys.version)
try:
    import yaml; print('✅ PyYAML')
    import msgpack; print('✅ msgpack')
    import psutil; print('✅ psutil')
    import mcp; print('✅ mcp')
    print('\n🎉 所有依赖正常！')
except ImportError as e:
    print('❌ 缺少依赖:', e)
    print('运行: pip3.12 install -r requirements.txt')
"

# 快速功能测试
python3.12 test_mcp_functionality.py && echo "✅ 功能测试通过"
```

## 📋 检查清单

### Python 环境
- [ ] Python 3.12 已安装
- [ ] pip3.12 可用
- [ ] 所有依赖已安装

### 核心文件
- [ ] `mcp_server.py` 存在且可执行
- [ ] `runtime_manager.py` 存在
- [ ] `runtime/main.py` 存在

### 测试脚本
- [ ] `test_mcp_functionality.py` 通过
- [ ] `test_error_responses.py` 通过
- [ ] `test_mcp_workflow.py` 通过

### 配置文件
- [ ] `.python-version` 存在（3.12.0）
- [ ] `.python-config.json` 存在
- [ ] `setup_python_env.sh` 可执行

## 🔧 常用命令

```bash
# 环境设置
./setup_python_env.sh

# 运行 MCP 服务器
python3.12 mcp_server.py

# 测试基础功能
python3.12 test_mcp_functionality.py

# 测试错误处理
python3.12 test_error_responses.py

# 完整工作流测试
python3.12 test_mcp_workflow.py

# 查看节点库
python3.12 -c "
from tools.cli.commands.node_cmd import scan_node_packages
packages = scan_node_packages('./node-hub')
print(f'找到 {len(packages)} 个节点包')
"
```

## ⚡ 快速诊断

如果遇到问题：

```bash
# 1. 检查 Python 路径
which python3.12

# 2. 验证依赖
python3.12 -m pip list | grep -E "(mcp|psutil|msgpack|PyYAML)"

# 3. 查看日志
ls -la /tmp/nodeflow_logs/

# 4. 检查 PID 文件
cat /tmp/nodeflow_runtime.pid 2>/dev/null || echo "运行时未启动"

# 5. 验证 MCP 服务器
python3.12 -c "from mcp_server import server; print('MCP 服务器: OK')"
```

## 📊 当前状态

运行此命令查看完整状态：

```bash
echo "=== NodeFlow 环境状态 ==="
echo ""
echo "Python:"
python3.12 --version
echo ""
echo "依赖:"
python3.12 -m pip list | grep -E "(mcp|psutil|msgpack|PyYAML)" | head -10
echo ""
echo "节点包:"
python3.12 -c "from tools.cli.commands.node_cmd import scan_node_packages; print(len(scan_node_packages('./node-hub')), '个')"
echo ""
echo "运行时:"
[ -f /tmp/nodeflow_runtime.pid ] && echo "运行中 (PID: $(head -1 /tmp/nodeflow_runtime.pid))" || echo "已停止"
echo ""
echo "日志:"
ls /tmp/nodeflow_logs/ 2>/dev/null | wc -l | xargs -I {} echo "{} 个节点日志文件"
```

---

**更新时间**: 2025-12-22
**Python 版本**: 3.12.0
**状态**: ✅ 就绪
