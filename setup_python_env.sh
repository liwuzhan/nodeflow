#!/bin/bash
# NodeFlow Python Environment Setup Script
# 配置 Python 环境以运行 NodeFlow MCP 服务和相关脚本

set -e  # 在任何错误时退出

echo "================================"
echo "NodeFlow Python 环境配置"
echo "================================"

# 检查 Python 版本
echo ""
echo "[1/5] 检查 Python 版本..."

if ! command -v python3.12 &> /dev/null; then
    echo "❌ Python 3.12 未安装"
    echo ""
    echo "请安装 Python 3.12:"
    echo "  macOS: brew install python@3.12"
    echo "  Ubuntu/Debian: sudo apt install python3.12 python3.12-venv"
    echo "  其他: 访问 https://www.python.org/downloads/"
    exit 1
fi

PYTHON_VERSION=$(python3.12 --version)
echo "✅ $PYTHON_VERSION"

# 检查 pip
echo ""
echo "[2/5] 检查 pip..."
if ! python3.12 -m pip --version &> /dev/null; then
    echo "❌ pip for Python 3.12 not found"
    exit 1
fi

echo "✅ pip 已安装"

# 创建虚拟环境（可选）
echo ""
echo "[3/5] 虚拟环境（可选）..."
if [ ! -d "venv" ]; then
    echo "是否创建虚拟环境? (y/n) [默认: n]"
    read -r create_venv
    if [ "$create_venv" = "y" ]; then
        python3.12 -m venv venv
        echo "✅ 虚拟环境已创建"
        echo ""
        echo "激活虚拟环境:"
        echo "  source venv/bin/activate"
    fi
else
    echo "ⓘ 虚拟环境已存在"
fi

# 安装依赖
echo ""
echo "[4/5] 安装依赖..."

# 确定要使用的 Python 命令
if [ -d "venv" ] && [ -z "$VIRTUAL_ENV" ]; then
    PY="./venv/bin/python3.12"
else
    PY="python3.12"
fi

echo "使用: $PY"
$PY -m pip install --upgrade pip setuptools wheel > /dev/null
$PY -m pip install -r requirements.txt

echo "✅ 依赖已安装"

# 验证关键模块
echo ""
echo "[5/5] 验证关键模块..."

modules=(
    "yaml"
    "msgpack"
    "psutil"
    "mcp"
)

for module in "${modules[@]}"; do
    if $PY -c "import $module" 2>/dev/null; then
        echo "✅ $module"
    else
        echo "⚠️  $module (未安装，某些功能可能不可用)"
    fi
done

# 总结
echo ""
echo "================================"
echo "✅ 环境配置完成"
echo "================================"
echo ""
echo "可用的命令:"
echo "  运行 MCP 服务器: $PY mcp_server.py"
echo "  测试基础功能: $PY test_mcp_functionality.py"
echo "  测试错误处理: $PY test_error_responses.py"
echo "  测试工作流: $PY test_mcp_workflow.py"
echo ""

if [ -d "venv" ]; then
    echo "如果你创建了虚拟环境，请先激活它:"
    echo "  source venv/bin/activate"
    echo ""
fi
