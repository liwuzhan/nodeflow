#!/bin/bash
# 测试子进程清理机制
# 验证 runtime 异常退出时，所有子节点进程都会被杀死

echo "=== 测试子进程清理机制 ==="
echo ""

# 1. 启动仿真器
echo "1. 启动仿真器..."
python3 simulator/server.py &
SIM_PID=$!
sleep 2
echo "   仿真器 PID: $SIM_PID"

# 2. 启动工作流
echo "2. 启动工作流..."
python3 -m runtime.main examples/planning_simulation.yaml &
RUNTIME_PID=$!
echo "   Runtime PID: $RUNTIME_PID"

# 3. 等待节点启动（增加等待时间）
echo "3. 等待节点启动（15秒）..."
for i in {1..15}; do
    sleep 1
    NODE_COUNT=$(ps aux | grep -E "python3.*run.py" | grep -v grep | wc -l)
    if [ "$NODE_COUNT" -gt 0 ]; then
        echo "   检测到 $NODE_COUNT 个节点进程已启动"
        break
    fi
    echo -n "."
done

echo ""
NODE_COUNT=$(ps aux | grep -E "python3.*run.py" | grep -v grep | wc -l)
if [ "$NODE_COUNT" -eq 0 ]; then
    echo "⚠️  警告：未检测到节点进程（可能启动延迟过长）"
else
    echo "✓ 当前运行的节点进程数: $NODE_COUNT"
fi

# 4. 强制杀死 runtime（模拟异常退出）
echo ""
echo "4. 强制杀死 runtime (SIGKILL)..."
kill -9 $RUNTIME_PID 2>/dev/null
sleep 2

# 5. 再次检查节点进程数量
echo "5. 检查清理后的节点进程..."
REMAINING_COUNT=$(ps aux | grep -E "python3.*run.py" | grep -v grep | wc -l)
echo "   剩余节点进程数: $REMAINING_COUNT"

# 6. 清理仿真器
kill -9 $SIM_PID 2>/dev/null

# 7. 结果判断
echo ""
if [ "$REMAINING_COUNT" -eq 0 ]; then
    echo "✅ 测试通过：所有子进程已被清理"
    echo "   (进程组杀死机制工作正常)"
    exit 0
else
    echo "❌ 测试失败：仍有 $REMAINING_COUNT 个子进程在运行"
    echo ""
    echo "僵尸进程列表："
    ps aux | grep -E "python3.*run.py" | grep -v grep
    exit 1
fi
