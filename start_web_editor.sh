#!/bin/bash
#
# NodeFlow Web Editor 一键启动脚本
# 启动前后端服务，并在浏览器中打开编辑器
#

set -e

cd "$(dirname "$0")"

echo "================================"
echo "NodeFlow Web Editor 启动脚本"
echo "================================"
echo ""

# 检查必要的工具
check_command() {
    if ! command -v $1 &> /dev/null; then
        echo "❌ 错误: $1 未安装或不在 PATH 中"
        echo "   请安装 $1 后重新运行"
        exit 1
    fi
}

echo "检查环境..."
check_command python3
check_command npm

# 检查项目结构
if [ ! -d "web-editor" ]; then
    echo "❌ 错误: 找不到 web-editor 目录"
    exit 1
fi

if [ ! -d "backend" ]; then
    echo "❌ 错误: 找不到 backend 目录"
    exit 1
fi

if [ ! -d "node-hub" ]; then
    echo "❌ 错误: 找不到 node-hub 目录"
    exit 1
fi

echo "✅ 环境检查完成"
echo ""

# 检查并安装后端依赖
echo "检查后端依赖..."
if [ -f "backend/requirements.txt" ]; then
    # 检查 fastapi 是否已安装
    if ! python3 -c "import fastapi" 2>/dev/null; then
        echo "📦 安装后端依赖 (pip3 install)..."
        pip3 install -r backend/requirements.txt
        echo "✅ 后端依赖安装完成"
    else
        echo "✅ 后端依赖已安装"
    fi
else
    echo "⚠️  未找到 backend/requirements.txt"
fi

echo ""

# 安装前端依赖（如果需要）
echo "检查前端依赖..."
if [ ! -d "web-editor/node_modules" ]; then
    echo "📦 安装前端依赖 (npm install)..."
    cd web-editor
    npm install
    cd ..
    echo "✅ 前端依赖安装完成"
else
    echo "✅ 前端依赖已安装"
fi

echo ""
echo "启动服务..."
echo "  后端服务: http://localhost:8000"
echo "  前端编辑器: http://localhost:5173"
echo ""
echo "按 Ctrl+C 停止所有服务"
echo ""

# 启动后端服务（后台运行）
echo "🚀 启动后端 API 服务..."
python3 backend/app.py &
BACKEND_PID=$!

# 给后端一点时间启动
sleep 2

# 检查后端是否成功启动
if ! kill -0 $BACKEND_PID 2>/dev/null; then
    echo "❌ 后端启动失败"
    exit 1
fi
echo "✅ 后端启动成功 (PID: $BACKEND_PID)"

# 启动前端开发服务（前台运行）
echo "🚀 启动前端开发服务..."
cd web-editor
npm run dev &
FRONTEND_PID=$!

# 给前端一点时间启动
sleep 3

# 尝试打开浏览器
echo ""
if [ "$(uname)" = "Darwin" ]; then
    # macOS
    open http://localhost:5173
elif [ "$(uname)" = "Linux" ]; then
    # Linux
    if command -v xdg-open &> /dev/null; then
        xdg-open http://localhost:5173
    fi
elif [[ "$OSTYPE" == "msys" || "$OSTYPE" == "win32" ]]; then
    # Windows
    start http://localhost:5173
fi

echo "✅ 编辑器已在浏览器中打开 (http://localhost:5173)"
echo ""

# 等待和清理
cleanup() {
    echo ""
    echo "关闭服务..."
    kill $BACKEND_PID 2>/dev/null || true
    kill $FRONTEND_PID 2>/dev/null || true
    wait $BACKEND_PID 2>/dev/null || true
    wait $FRONTEND_PID 2>/dev/null || true
    echo "✅ 所有服务已关闭"
}

trap cleanup EXIT

# 等待任何进程退出
wait
