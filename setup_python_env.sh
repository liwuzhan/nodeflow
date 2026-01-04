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

# 函数：检查 Python 版本是否满足要求（>= 3.10）
check_python_version() {
    local python_cmd=$1
    if ! command -v "$python_cmd" &> /dev/null; then
        return 1
    fi

    local version=$($python_cmd --version 2>&1 | awk '{print $2}')
    local major=$(echo $version | cut -d. -f1)
    local minor=$(echo $version | cut -d. -f2)

    if [ "$major" -ge 3 ] && [ "$minor" -ge 10 ]; then
        return 0
    fi
    return 1
}

# 尝试找到可用的 Python 3.10+ 版本
PYTHON_CMD=""
for cmd in python3.12 python3.11 python3.10 python3; do
    if check_python_version "$cmd"; then
        PYTHON_CMD="$cmd"
        break
    fi
done

if [ -z "$PYTHON_CMD" ]; then
    echo "❌ 未找到 Python 3.10 或更高版本"
    echo ""
    echo "请安装 Python 3.12 (推荐) 或 Python 3.10+:"
    echo "  macOS: brew install python@3.12"
    echo "  Ubuntu/Debian: sudo apt install python3.12 python3.12-venv"
    echo "  其他: 访问 https://www.python.org/downloads/"
    exit 1
fi

PYTHON_VERSION=$($PYTHON_CMD --version)
echo "✅ 找到可用版本: $PYTHON_VERSION (命令: $PYTHON_CMD)"

# 检查 pip
echo ""
echo "[2/5] 检查 pip..."
if ! $PYTHON_CMD -m pip --version &> /dev/null; then
    echo "❌ pip for $PYTHON_CMD not found"
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
        $PYTHON_CMD -m venv venv
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
    PY="./venv/bin/python"
else
    PY="$PYTHON_CMD"
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
