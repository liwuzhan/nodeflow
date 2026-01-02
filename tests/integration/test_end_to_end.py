#!/usr/bin/env python3.12
"""
端到端集成测试
验证完整的框架流程：配置解析 -> 节点启动 -> 通信 -> 监控
"""

import sys
import os
import time
import tempfile
import threading
from pathlib import Path

# 添加项目根目录到路径
sys.path.insert(0, str(Path(__file__).parent))

from runtime.config.yaml_parser import YAMLParser
from runtime.config.validator import ConfigValidator
from runtime.node_hub.node_registry import NodeRegistry
from runtime.graph.topology import TopologyAnalyzer
from runtime.graph.validator import GraphValidator
from runtime.orchestrator.node_launcher import NodeLauncher
from runtime.orchestrator.startup_coordinator import StartupCoordinator
from runtime.monitoring.node_monitor import NodeMonitor
from runtime.utils.logger import setup_logger

logger = setup_logger("test_e2e", "INFO")


def test_complete_workflow():
    """测试完整工作流"""
    print("=" * 60)
    print("端到端集成测试")
    print("=" * 60)

    # 1. 解析配置
    print("\n[1/7] 解析运行配置...")
    parser = YAMLParser()
    config = parser.parse_runtime_config("examples/runtime.yaml")

    print(f"✓ 配置解析成功")
    print(f"  - Graph ID: {config.graph_id}")
    print(f"  - 节点数: {len(config.nodes)}")
    print(f"  - 边数: {len(config.edges)}")

    # 2. 验证配置
    print("\n[2/7] 验证配置...")
    validator = ConfigValidator()
    result = validator.validate_runtime_config(config)

    assert result.is_valid, f"配置验证失败: {result.errors}"
    print("✓ 配置验证通过")

    # 3. 加载节点库
    print("\n[3/7] 加载节点库...")
    registry = NodeRegistry("node-hub")
    registry.load_all()

    print(f"✓ 加载了{len(registry.get_all_packages())}个节点包")
    print(f"  - {', '.join(registry.get_all_packages())}")

    # 4. 验证图
    print("\n[4/7] 验证图...")
    graph_validator = GraphValidator()
    graph_result = graph_validator.validate(
        config.nodes, config.edges, registry
    )

    assert graph_result.is_valid, f"图验证失败: {graph_result.errors}"
    print("✓ 图验证通过")

    # 5. 拓扑排序
    print("\n[5/7] 拓扑排序...")
    topology = TopologyAnalyzer(config.nodes, config.edges)
    layers = topology.topological_sort()

    print(f"✓ 拓扑排序成功: {len(layers)}层")
    for i, layer in enumerate(layers):
        print(f"  - Layer {i}: {layer}")

    # 6. 启动节点
    print("\n[6/7] 启动节点...")

    with tempfile.TemporaryDirectory() as tmpdir:
        launcher = NodeLauncher("node-hub", config.edges)
        coordinator = StartupCoordinator(launcher, registry)

        nodes_dict = {n.id: n for n in config.nodes}

        try:
            processes = coordinator.startup_nodes(
                layers, nodes_dict,
                startup_timeout=5.0,
                startup_delay=0.5
            )

            print(f"✓ {len(processes)}个节点启动成功")
            for node_id, proc in processes.items():
                print(f"  - {node_id}: PID {proc.pid}")

            # 7. 验证监控
            print("\n[7/7] 验证监控系统...")

            def restart_callback(node_id):
                """重启回调"""
                node = nodes_dict[node_id]
                manifest = registry.get_manifest(node.package)
                return launcher.launch(node, manifest)

            monitor = NodeMonitor(config.restart_policy)
            monitor.start_monitoring(processes, restart_callback)

            # 等待一段时间验证监控
            time.sleep(2)

            # 获取状态
            status = monitor.get_all_status()
            print(f"✓ 监控系统运行正常")
            print(f"  - 运行中的节点: {len(monitor.get_running_nodes())}")
            for node_id in monitor.get_running_nodes():
                node_status = status[node_id]
                print(f"    - {node_id}: PID {node_status['pid']}")

            # 停止监控
            monitor.stop()

            # 关闭节点
            print("\n[关闭] 清理资源...")
            coordinator.shutdown_nodes(processes, shutdown_timeout=2.0)
            socket_manager.cleanup()

            print("✓ 清理完成")

        except Exception as e:
            print(f"✗ 测试失败: {e}")
            import traceback
            traceback.print_exc()
            raise

    print("\n" + "=" * 60)
    print("✓ 端到端测试通过！")
    print("=" * 60)


if __name__ == "__main__":
    try:
        test_complete_workflow()
        sys.exit(0)
    except Exception as e:
        print(f"测试失败: {e}")
        sys.exit(1)
