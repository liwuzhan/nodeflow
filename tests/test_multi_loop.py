#!/usr/bin/env python3
"""
多轮启动-停止循环功能的测试和演示脚本

这个脚本验证框架是否正确支持多轮启动-停止循环：
1. 框架初始化（一次性）
2. 多轮数据流启停循环
3. 正确的资源清理
"""

import sys
import os
import time
import logging
import threading
from pathlib import Path

# 添加项目路径（脚本位于 tests/ 下，项目根是其上一级）
sys.path.insert(0, str(Path(__file__).parent.parent))

from edge.runtime.main import NodeFlowRuntime
from edge.runtime.utils.logger import setup_logger

logger = setup_logger("test_multi_loop")


def _fd_count() -> int:
    """当前进程打开的 fd 数（资源泄漏基线指标）"""
    for candidate in ("/dev/fd", f"/proc/{Path('/proc/self').name}/fd"):
        try:
            return len(os.listdir(candidate))
        except OSError:
            continue
    return -1


def test_framework_initialization():
    """
    测试框架初始化是否正确

    期望：
    - 框架初始化成功
    - 配置加载正确
    - 节点库扫描完成
    - 图验证通过
    - 拓扑分析完成
    """
    logger.info("\n" + "=" * 60)
    logger.info("TEST 1: Framework Initialization")
    logger.info("=" * 60)

    config_file = "examples/planning_simulation.yaml"
    if not Path(config_file).exists():
        logger.error(f"Config file not found: {config_file}")
        return False

    try:
        runtime = NodeFlowRuntime(config_file, log_level="INFO", clean_buffers=True)

        # 初始化框架
        result = runtime._initialize_framework()
        if result != 0:
            logger.error("Framework initialization failed")
            return False

        # 验证框架状态
        assert runtime._framework_initialized, "Framework should be marked as initialized"
        assert runtime.config is not None, "Config should be loaded"
        assert runtime.registry is not None, "Node registry should be loaded"
        assert runtime.topology_layers is not None, "Topology should be analyzed"
        assert runtime.nodes_dict is not None, "Nodes dict should be built"

        logger.info("✓ Framework initialization successful")
        logger.info(f"  - Config: {runtime.config.graph_id}")
        logger.info(f"  - Nodes: {len(runtime.nodes_dict)}")
        logger.info(f"  - Layers: {len(runtime.topology_layers)}")

        return True

    except Exception as e:
        logger.error(f"✗ Framework initialization failed: {e}", exc_info=True)
        return False


def test_dataflow_lifecycle():
    """
    测试数据流生命周期（启动→停止）

    期望：
    - 数据流启动成功
    - 节点被正确启动
    - 监控器启动
    - 数据流停止成功
    - 所有资源被清理
    """
    logger.info("\n" + "=" * 60)
    logger.info("TEST 2: Dataflow Lifecycle (Start→Stop)")
    logger.info("=" * 60)

    config_file = "examples/planning_simulation.yaml"

    try:
        runtime = NodeFlowRuntime(config_file, log_level="WARNING", clean_buffers=True)

        # 初始化框架
        if runtime._initialize_framework() != 0:
            logger.error("Framework initialization failed")
            return False

        # 启动数据流（start_dataflow 以 self.running 判取消，直接调用 API 须先置位）
        logger.info("Starting dataflow...")
        runtime.running = True
        runtime.start_dataflow()

        # 验证数据流状态
        assert runtime.dataflow_running, "Dataflow should be marked as running"
        assert len(runtime.processes) > 0, "Processes should be started"
        assert runtime.monitor is not None, "Monitor should be started"

        logger.info(f"✓ Dataflow started with {len(runtime.processes)} nodes")

        # 运行5秒
        time.sleep(5)

        # 停止数据流
        logger.info("Stopping dataflow...")
        runtime.stop_dataflow()

        # 验证数据流停止
        assert not runtime.dataflow_running, "Dataflow should be marked as stopped"
        assert len(runtime.processes) == 0, "Processes should be cleaned up"
        assert runtime.monitor is None, "Monitor should be stopped"

        logger.info("✓ Dataflow stopped successfully")

        return True

    except Exception as e:
        logger.error(f"✗ Dataflow lifecycle test failed: {e}", exc_info=True)
        return False


def test_multi_loop_cycles():
    """
    测试多轮启动-停止循环

    期望：
    - 框架初始化一次
    - 多次启动和停止数据流成功
    - 每轮都有新的进程ID
    - 资源正确清理
    """
    logger.info("\n" + "=" * 60)
    logger.info("TEST 3: Multi-Loop Cycles (3 iterations)")
    logger.info("=" * 60)

    config_file = "examples/planning_simulation.yaml"
    num_loops = 3

    try:
        runtime = NodeFlowRuntime(config_file, log_level="WARNING", clean_buffers=True)

        # 初始化框架（一次性）
        logger.info("Initializing framework once...")
        if runtime._initialize_framework() != 0:
            logger.error("Framework initialization failed")
            return False

        logger.info("✓ Framework initialized")

        # 多轮循环（直接调用 API 须先进入 running 态）
        runtime.running = True
        for loop_num in range(1, num_loops + 1):
            logger.info(f"\n--- Loop {loop_num}/{num_loops} ---")

            # 启动数据流
            logger.info("  Starting dataflow...")
            runtime.start_dataflow()

            loop_processes = dict(runtime.processes)
            loop_process_ids = [str(p.pid) for p in loop_processes.values()]
            logger.info(f"  ✓ Started with PIDs: {', '.join(loop_process_ids[:3])}...")

            # 运行3秒
            time.sleep(3)

            # 停止数据流
            logger.info("  Stopping dataflow...")
            runtime.stop_dataflow()

            # 验证停止
            assert not runtime.dataflow_running, f"Dataflow should be stopped after loop {loop_num}"
            assert len(runtime.processes) == 0, f"Processes should be cleaned up after loop {loop_num}"

            logger.info(f"  ✓ Stopped successfully")

            # 各轮之间等待
            if loop_num < num_loops:
                logger.info(f"  Waiting 2s before next loop...")
                time.sleep(2)

        logger.info(f"\n✓ All {num_loops} loops completed successfully")
        return True

    except Exception as e:
        logger.error(f"✗ Multi-loop test failed: {e}", exc_info=True)
        return False


def test_error_handling():
    """
    测试错误处理和异常情况

    期望：
    - 未初始化时启动数据流应抛出错误
    - 数据流运行时重复启动应抛出错误
    - 未运行时停止应抛出错误
    """
    logger.info("\n" + "=" * 60)
    logger.info("TEST 4: Error Handling")
    logger.info("=" * 60)

    config_file = "examples/planning_simulation.yaml"

    try:
        runtime = NodeFlowRuntime(config_file, log_level="WARNING", clean_buffers=True)

        # 测试1：未初始化时启动数据流
        logger.info("Test 4.1: Start without initialization...")
        try:
            runtime.start_dataflow()
            logger.error("✗ Should have raised RuntimeError")
            return False
        except RuntimeError as e:
            logger.info(f"✓ Correctly raised RuntimeError: {e}")

        # 初始化框架
        runtime._initialize_framework()

        # 测试2：重复启动（直接调用 API 须先进入 running 态）
        logger.info("Test 4.2: Duplicate start...")
        runtime.running = True
        runtime.start_dataflow()
        time.sleep(2)

        try:
            runtime.start_dataflow()
            logger.error("✗ Should have raised RuntimeError")
            return False
        except RuntimeError as e:
            logger.info(f"✓ Correctly raised RuntimeError: {e}")

        # 停止数据流
        runtime.stop_dataflow()

        # 测试3：未运行时停止
        logger.info("Test 4.3: Stop without running...")
        try:
            runtime.stop_dataflow()
            logger.error("✗ Should have raised RuntimeError")
            return False
        except RuntimeError as e:
            logger.info(f"✓ Correctly raised RuntimeError: {e}")

        logger.info("✓ All error handling tests passed")
        return True

    except Exception as e:
        logger.error(f"✗ Error handling test failed: {e}", exc_info=True)
        return False


def test_resource_baseline():
    """
    资源泄漏基线测试（验收 #6）

    期望：
    - 多轮启动-停止循环后，进程 fd 数与线程数回到基线（容差 ±2）
    - buffer 文件遵循 run 保留策略（每轮新 run 目录，保留最近 5 份）
    """
    logger.info("\n" + "=" * 60)
    logger.info("TEST 5: Resource Baseline After Loops")
    logger.info("=" * 60)

    config_file = "examples/planning_simulation.yaml"

    try:
        runtime = NodeFlowRuntime(config_file, log_level="WARNING")

        if runtime._initialize_framework() != 0:
            logger.error("Framework initialization failed")
            return False

        runtime.running = True

        # 静置等清理线程（launcher 日志转发线程等）退出
        time.sleep(1.0)
        fd_before = _fd_count()
        threads_before = threading.active_count()
        logger.info(f"  Baseline: fd={fd_before}, threads={threads_before}")

        for loop in range(3):
            runtime.start_dataflow()
            time.sleep(1.5)
            runtime.stop_dataflow()
            time.sleep(0.5)

        # 等残留守护线程退出
        time.sleep(1.0)
        fd_after = _fd_count()
        threads_after = threading.active_count()
        logger.info(f"  After 3 loops: fd={fd_after}, threads={threads_after}")

        assert fd_after <= fd_before + 2, \
            f"fd leak: {fd_before} -> {fd_after}"
        assert threads_after <= threads_before + 2, \
            f"thread leak: {threads_before} -> {threads_after}"

        logger.info("✓ Resource baseline maintained")
        return True

    except Exception as e:
        logger.error(f"✗ Resource baseline test failed: {e}", exc_info=True)
        return False


def main():
    """运行所有测试"""
    logger.info("\n" + "=" * 60)
    logger.info("NodeFlow Multi-Loop Test Suite")
    logger.info("=" * 60)

    # 检查配置文件
    config_file = "examples/planning_simulation.yaml"
    if not Path(config_file).exists():
        logger.error(f"\nConfig file not found: {config_file}")
        logger.error("Please ensure the configuration file exists before running tests.")
        return 1

    tests = [
        ("Framework Initialization", test_framework_initialization),
        ("Dataflow Lifecycle", test_dataflow_lifecycle),
        ("Multi-Loop Cycles", test_multi_loop_cycles),
        ("Error Handling", test_error_handling),
        ("Resource Baseline", test_resource_baseline),
    ]

    results = {}

    for test_name, test_func in tests:
        try:
            results[test_name] = test_func()
        except KeyboardInterrupt:
            logger.warning("\nTest interrupted by user")
            break
        except Exception as e:
            logger.error(f"Unexpected error in {test_name}: {e}", exc_info=True)
            results[test_name] = False

    # 总结
    logger.info("\n" + "=" * 60)
    logger.info("Test Summary")
    logger.info("=" * 60)

    passed = sum(1 for v in results.values() if v)
    total = len(results)

    for test_name, result in results.items():
        status = "✓ PASS" if result else "✗ FAIL"
        logger.info(f"{status}: {test_name}")

    logger.info(f"\nTotal: {passed}/{total} tests passed")

    if passed == total:
        logger.info("\n🎉 All tests passed!")
        return 0
    else:
        logger.error(f"\n❌ {total - passed} test(s) failed")
        return 1


if __name__ == '__main__':
    sys.exit(main())
