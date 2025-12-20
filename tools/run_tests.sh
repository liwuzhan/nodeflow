#!/bin/bash
# NodeFlow 测试运行器
# 用法: ./tools/run_tests.sh [quick|full|scenario]

set -e

# 颜色
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

# 项目根目录
PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${PROJECT_ROOT}"

TEST_MODE="${1:-quick}"
REPORT_DIR=".test-reports"
TIMESTAMP=$(date +"%Y%m%d_%H%M%S")

mkdir -p "${REPORT_DIR}"

echo -e "${BLUE}╔════════════════════════════════════════════════════════════╗${NC}"
echo -e "${BLUE}║          NodeFlow 自动化测试套件                          ║${NC}"
echo -e "${BLUE}╚════════════════════════════════════════════════════════════╝${NC}"
echo ""

# ============================================================================
# 测试 1: 语法检查
# ============================================================================
test_syntax() {
    echo -e "${YELLOW}[测试 1/5] 代码语法检查${NC}"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

    ERROR_COUNT=0

    # 检查 runtime
    for file in runtime/**/*.py; do
        if [ -f "$file" ]; then
            python3 -m py_compile "$file" 2>/dev/null || {
                echo -e "${RED}✗ $file 编译失败${NC}"
                ERROR_COUNT=$((ERROR_COUNT + 1))
            }
        fi
    done

    # 检查 SDK
    for file in sdk/*.py; do
        if [ -f "$file" ]; then
            python3 -m py_compile "$file" 2>/dev/null || {
                echo -e "${RED}✗ $file 编译失败${NC}"
                ERROR_COUNT=$((ERROR_COUNT + 1))
            }
        fi
    done

    # 检查 Mock 节点
    for node_dir in node-hub/mock_*; do
        if [ -d "$node_dir" ] && [ -f "$node_dir/run.py" ]; then
            python3 -m py_compile "$node_dir/run.py" 2>/dev/null || {
                echo -e "${RED}✗ $node_dir/run.py 编译失败${NC}"
                ERROR_COUNT=$((ERROR_COUNT + 1))
            }
        fi
    done

    if [ $ERROR_COUNT -eq 0 ]; then
        echo -e "${GREEN}✓ 所有 Python 文件语法检查通过${NC}"
        return 0
    else
        echo -e "${RED}✗ 发现 $ERROR_COUNT 个语法错误${NC}"
        return 1
    fi
}

# ============================================================================
# 测试 2: 节点配置验证
# ============================================================================
test_node_configs() {
    echo -e "\n${YELLOW}[测试 2/5] Mock 节点配置验证${NC}"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

    MOCK_NODES=("mock_joystick" "mock_gps" "mock_imu" "mock_path_planner"
                "mock_controller_sim" "mock_motor_controller" "mock_sensor_fusion"
                "mock_data_generator" "mock_data_validator" "mock_throughput_monitor")

    MISSING=0

    for node in "${MOCK_NODES[@]}"; do
        node_path="node-hub/${node}"

        if [ ! -d "$node_path" ]; then
            echo -e "${RED}✗ ${node} - 目录不存在${NC}"
            MISSING=$((MISSING + 1))
            continue
        fi

        # 检查必需文件
        FILES_OK=true

        if [ ! -f "$node_path/node.yaml" ]; then
            echo -e "${RED}✗ ${node} - 缺少 node.yaml${NC}"
            FILES_OK=false
        fi

        if [ ! -f "$node_path/run.py" ]; then
            echo -e "${RED}✗ ${node} - 缺少 run.py${NC}"
            FILES_OK=false
        fi

        if [ ! -f "$node_path/README.md" ]; then
            echo -e "${YELLOW}⚠ ${node} - 缺少 README.md (建议添加)${NC}"
        fi

        if [ "$FILES_OK" = true ]; then
            echo -e "${GREEN}✓ ${node}${NC}"
        else
            MISSING=$((MISSING + 1))
        fi
    done

    if [ $MISSING -eq 0 ]; then
        echo -e "${GREEN}✓ 所有 10 个 Mock 节点配置完整${NC}"
        return 0
    else
        echo -e "${RED}✗ $MISSING 个节点配置不完整${NC}"
        return 1
    fi
}

# ============================================================================
# 测试 3: 测试场景配置检查
# ============================================================================
test_scenario_configs() {
    echo -e "\n${YELLOW}[测试 3/5] 测试场景配置检查${NC}"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

    SCENARIOS=("test_mock_single" "test_mock_chain" "test_mock_multiport"
               "test_mock_processing" "test_mock_highfreq" "test_mock_errors"
               "test_mock_pipeline")

    MISSING=0

    for scenario in "${SCENARIOS[@]}"; do
        config_path="examples/${scenario}.yaml"

        if [ -f "$config_path" ]; then
            # 简单的 YAML 语法检查
            python3 -c "import yaml; yaml.safe_load(open('$config_path'))" 2>/dev/null && {
                echo -e "${GREEN}✓ ${scenario}.yaml${NC}"
            } || {
                echo -e "${RED}✗ ${scenario}.yaml - YAML 语法错误${NC}"
                MISSING=$((MISSING + 1))
            }
        else
            echo -e "${RED}✗ ${scenario}.yaml - 文件不存在${NC}"
            MISSING=$((MISSING + 1))
        fi
    done

    if [ $MISSING -eq 0 ]; then
        echo -e "${GREEN}✓ 所有 7 个测试场景配置有效${NC}"
        return 0
    else
        echo -e "${RED}✗ $MISSING 个场景配置有问题${NC}"
        return 1
    fi
}

# ============================================================================
# 测试 4: 单元测试
# ============================================================================
test_unit() {
    echo -e "\n${YELLOW}[测试 4/5] 运行单元测试${NC}"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

    if [ -d "tests/unit" ] && [ "$(ls -A tests/unit/*.py 2>/dev/null)" ]; then
        python3 -m pytest tests/unit/ -v --tb=short 2>&1 | tee "${REPORT_DIR}/unittest-${TIMESTAMP}.log"
        RESULT=${PIPESTATUS[0]}

        if [ $RESULT -eq 0 ]; then
            echo -e "${GREEN}✓ 单元测试通过${NC}"
            return 0
        else
            echo -e "${RED}✗ 单元测试失败，详细日志: ${REPORT_DIR}/unittest-${TIMESTAMP}.log${NC}"
            return 1
        fi
    else
        echo -e "${YELLOW}⊘ 没有发现单元测试文件${NC}"
        return 0
    fi
}

# ============================================================================
# 测试 5: 场景测试（可选）
# ============================================================================
test_scenarios() {
    echo -e "\n${YELLOW}[测试 5/5] 运行场景测试 (Scenario 1)${NC}"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

    if [ "$TEST_MODE" != "full" ]; then
        echo -e "${YELLOW}⊘ 跳过场景测试 (使用 './tools/run_tests.sh full' 运行)${NC}"
        return 0
    fi

    # 运行 Scenario 1 (单节点测试)
    echo "正在运行 test_mock_single.yaml (20秒)..."

    timeout 25 python3 -m runtime.main examples/test_mock_single.yaml > "${REPORT_DIR}/scenario1-${TIMESTAMP}.log" 2>&1 &
    PID=$!

    sleep 20
    kill -15 $PID 2>/dev/null || true
    wait $PID 2>/dev/null || true

    # 检查日志
    if grep -q "Runtime is RUNNING" "${REPORT_DIR}/scenario1-${TIMESTAMP}.log"; then
        echo -e "${GREEN}✓ Scenario 1 运行成功${NC}"
        return 0
    else
        echo -e "${RED}✗ Scenario 1 运行失败，详细日志: ${REPORT_DIR}/scenario1-${TIMESTAMP}.log${NC}"
        return 1
    fi
}

# ============================================================================
# 主流程
# ============================================================================

TOTAL_TESTS=0
PASSED_TESTS=0

run_test() {
    TOTAL_TESTS=$((TOTAL_TESTS + 1))
    if $1; then
        PASSED_TESTS=$((PASSED_TESTS + 1))
    fi
}

run_test test_syntax
run_test test_node_configs
run_test test_scenario_configs

if [ "$TEST_MODE" != "scenario" ]; then
    run_test test_unit
fi

if [ "$TEST_MODE" = "full" ] || [ "$TEST_MODE" = "scenario" ]; then
    run_test test_scenarios
fi

# ============================================================================
# 总结报告
# ============================================================================

echo ""
echo -e "${BLUE}╔════════════════════════════════════════════════════════════╗${NC}"
echo -e "${BLUE}║                     测试总结                               ║${NC}"
echo -e "${BLUE}╚════════════════════════════════════════════════════════════╝${NC}"
echo ""
echo "测试模式: ${TEST_MODE}"
echo "通过测试: ${PASSED_TESTS}/${TOTAL_TESTS}"
echo "测试时间: $(date '+%Y-%m-%d %H:%M:%S')"
echo "Git 提交: $(git rev-parse --short HEAD 2>/dev/null || echo 'N/A')"
echo ""

if [ $PASSED_TESTS -eq $TOTAL_TESTS ]; then
    echo -e "${GREEN}════════════════════════════════════════════════════════════${NC}"
    echo -e "${GREEN}                ✓ 所有测试通过！                           ${NC}"
    echo -e "${GREEN}════════════════════════════════════════════════════════════${NC}"
    exit 0
else
    FAILED=$((TOTAL_TESTS - PASSED_TESTS))
    echo -e "${RED}════════════════════════════════════════════════════════════${NC}"
    echo -e "${RED}                ✗ 有 ${FAILED} 个测试失败                     ${NC}"
    echo -e "${RED}════════════════════════════════════════════════════════════${NC}"
    exit 1
fi
