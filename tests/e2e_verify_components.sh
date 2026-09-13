#!/usr/bin/env bash
#
# E2E 端到端测试组件验证脚本
# 验证所有必需的节点、配置文件和脚本是否存在
#

set -e

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_ROOT"

echo "=========================================="
echo "E2E 端到端测试组件验证"
echo "=========================================="
echo ""

# 颜色定义
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

SUCCESS=0
FAILED=0

# 检查函数
check_exists() {
    local item=$1
    local label=$2

    if [ -e "$item" ]; then
        echo -e "${GREEN}✓${NC} $label: $item"
        ((SUCCESS++))
        return 0
    else
        echo -e "${RED}✗${NC} $label: $item ${RED}[不存在]${NC}"
        ((FAILED++))
        return 1
    fi
}

echo "【1/5】节点库检查"
echo "-------------------------------------------"
check_exists "node-hub/sim_output/node.yaml" "仿真器输出节点"
check_exists "node-hub/global_coverage/node.yaml" "全覆盖规划节点"
check_exists "node-hub/velocity_controller/node.yaml" "速度控制节点"
check_exists "node-hub/sim_input/node.yaml" "仿真器输入节点"
check_exists "node-hub/trajectory_viz/node.yaml" "轨迹可视化节点"
echo ""

echo "【2/5】节点实现检查"
echo "-------------------------------------------"
check_exists "node-hub/sim_output/run.py" "sim_output 实现"
check_exists "node-hub/global_coverage/run.py" "global_coverage 实现"
check_exists "node-hub/velocity_controller/run.py" "velocity_controller 实现"
check_exists "node-hub/sim_input/run.py" "sim_input 实现"
check_exists "node-hub/trajectory_viz/run.py" "trajectory_viz 实现"
echo ""

echo "【3/5】配置文件检查"
echo "-------------------------------------------"
check_exists "examples/planning_simulation.yaml" "E2E 配置文件"
check_exists "simulator/config.yaml" "仿真器配置"
check_exists "simulator/server.py" "仿真器服务器"
echo ""

echo "【4/5】测试脚本检查"
echo "-------------------------------------------"
check_exists "tests/e2e_test_planning_simulation.py" "E2E测试脚本"
check_exists "docs/E2E_TESTING_GUIDE.md" "E2E测试文档"
echo ""

echo "【5/5】运行时框架检查"
echo "-------------------------------------------"
check_exists "runtime/main.py" "运行时主程序"
check_exists "runtime/orchestrator/startup_coordinator.py" "启动协调器"
check_exists "runtime/orchestrator/node_launcher.py" "节点启动器"
check_exists "sdk/nodeflow_sdk.py" "NodeFlow SDK"
echo ""

echo "=========================================="
echo "检查结果汇总"
echo "=========================================="
echo -e "总计: $(($SUCCESS + $FAILED)) 项"
echo -e "${GREEN}通过: $SUCCESS${NC}"
echo -e "${RED}失败: $FAILED${NC}"
echo ""

if [ $FAILED -eq 0 ]; then
    echo -e "${GREEN}✓ 所有组件齐全，可以运行E2E测试！${NC}"
    echo ""
    echo "=========================================="
    echo "下一步操作"
    echo "=========================================="
    echo ""
    echo "【方法1】使用测试脚本（推荐）:"
    echo "  python3 tests/e2e_test_planning_simulation.py"
    echo ""
    echo "【方法2】手动运行:"
    echo "  # 终端1: 启动仿真器"
    echo "  python3 simulator/server.py"
    echo ""
    echo "  # 终端2: 启动运行时"
    echo "  python3 -m runtime.main examples/planning_simulation.yaml"
    echo ""
    echo "【查看文档】:"
    echo "  cat docs/E2E_TESTING_GUIDE.md"
    echo ""
    exit 0
else
    echo -e "${RED}✗ 存在缺失组件，请先补全！${NC}"
    echo ""
    exit 1
fi
