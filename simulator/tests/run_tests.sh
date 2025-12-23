#!/bin/bash
# 完整的测试运行脚本

set -e  # 遇到错误立即退出

cd "$(dirname "$0")"

echo "╔════════════════════════════════════════════════════════════╗"
echo "║         仿真器测试套件                                    ║"
echo "╚════════════════════════════════════════════════════════════╝"
echo ""

# 清理可能占用的端口
echo "🧹 清理端口..."
lsof -ti:5555 2>/dev/null | xargs kill -9 2>/dev/null || true
sleep 1

# 1. 运行单元测试
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "📝 测试1: 运动噪声模型单元测试"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
python3 test_motion_noise.py
if [ $? -eq 0 ]; then
    echo "✅ 运动噪声测试通过"
else
    echo "❌ 运动噪声测试失败"
    exit 1
fi

# 2. 启动仿真器服务器
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "🚀 启动仿真器服务器"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
python3 server.py > /tmp/simulator_server.log 2>&1 &
SERVER_PID=$!
echo "服务器 PID: $SERVER_PID"

# 等待服务器启动
echo "⏳ 等待服务器启动..."
sleep 3

# 检查服务器是否在运行
if ! kill -0 $SERVER_PID 2>/dev/null; then
    echo "❌ 服务器启动失败"
    cat /tmp/simulator_server.log
    exit 1
fi
echo "✅ 服务器已启动"

# 3. 运行集成测试
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "🔗 测试2: 集成测试"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
python3 test_integration.py
INTEGRATION_RESULT=$?

# 4. 清理
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "🧹 清理资源"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
kill $SERVER_PID 2>/dev/null || true
wait $SERVER_PID 2>/dev/null || true
echo "✅ 服务器已关闭"

# 5. 总结
echo ""
echo "╔════════════════════════════════════════════════════════════╗"
echo "║                    测试总结                                ║"
echo "╚════════════════════════════════════════════════════════════╝"
if [ $INTEGRATION_RESULT -eq 0 ]; then
    echo "✅ 所有测试通过"
    exit 0
else
    echo "❌ 集成测试失败"
    echo ""
    echo "服务器日志:"
    cat /tmp/simulator_server.log
    exit 1
fi
