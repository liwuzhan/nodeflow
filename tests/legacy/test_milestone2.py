#!/usr/bin/env python3
"""
里程碑2测试脚本 - 验证节点发现与图分析
"""

import sys
from pathlib import Path

# 添加项目根目录到路径
sys.path.insert(0, str(Path(__file__).parent))

from edge.runtime.node_hub.scanner import NodeHubScanner
from edge.runtime.node_hub.node_registry import NodeRegistry
from edge.runtime.graph.topology import TopologyAnalyzer
from edge.runtime.graph.validator import GraphValidator
from edge.runtime.config.models import NodeInstance, Edge
from edge.runtime.utils.errors import CyclicDependencyError


def test_node_scanner():
    """测试节点扫描器"""
    print("=" * 60)
    print("测试节点扫描器")
    print("=" * 60)

    scanner = NodeHubScanner("tests/fixtures/test_node_hub")
    packages = scanner.scan()

    print(f"✓ 扫描到 {len(packages)} 个节点包: {packages}")

    # 验证扫描结果
    assert len(packages) == 3
    assert "node_a" in packages
    assert "node_b" in packages
    assert "node_c" in packages

    # 验证package_exists
    assert scanner.package_exists("node_a")
    assert not scanner.package_exists("nonexistent")

    print("✓ 节点扫描器测试通过\n")


def test_node_registry():
    """测试节点注册表"""
    print("=" * 60)
    print("测试节点注册表")
    print("=" * 60)

    registry = NodeRegistry("tests/fixtures/test_node_hub")
    registry.load_all()

    print(f"✓ 加载了 {len(registry.get_all_packages())} 个节点说明书")

    # 验证加载结果
    assert registry.has_package("node_a")
    assert registry.has_package("node_b")
    assert registry.has_package("node_c")

    # 获取节点说明书
    manifest_a = registry.get_manifest("node_a")
    assert manifest_a is not None
    assert manifest_a.name == "node_a"
    assert len(manifest_a.outputs) == 1
    assert len(manifest_a.inputs) == 0

    print(f"✓ node_a: {len(manifest_a.outputs)} outputs, {len(manifest_a.inputs)} inputs")

    manifest_b = registry.get_manifest("node_b")
    assert len(manifest_b.outputs) == 1
    assert len(manifest_b.inputs) == 1

    print(f"✓ node_b: {len(manifest_b.outputs)} outputs, {len(manifest_b.inputs)} inputs")

    manifest_c = registry.get_manifest("node_c")
    assert len(manifest_c.outputs) == 0
    assert len(manifest_c.inputs) == 1

    print(f"✓ node_c: {len(manifest_c.outputs)} outputs, {len(manifest_c.inputs)} inputs")

    print("✓ 节点注册表测试通过\n")

    return registry


def test_topology_simple():
    """测试拓扑排序 - 简单情况"""
    print("=" * 60)
    print("测试拓扑排序 - 简单链式依赖 (A -> B -> C)")
    print("=" * 60)

    # 创建节点实例
    nodes = [
        NodeInstance(id="inst_a", package="node_a"),
        NodeInstance(id="inst_b", package="node_b"),
        NodeInstance(id="inst_c", package="node_c"),
    ]

    # 创建边：A -> B -> C
    edges = [
        Edge(from_node="inst_a", from_port="output1", to_node="inst_b", to_port="input1"),
        Edge(from_node="inst_b", from_port="output1", to_node="inst_c", to_port="input1"),
    ]

    # 拓扑排序
    analyzer = TopologyAnalyzer(nodes, edges)
    layers = analyzer.topological_sort()

    print(f"✓ 拓扑排序结果: {layers}")

    # 验证结果
    assert len(layers) == 3
    assert layers[0] == ["inst_a"]  # A无依赖
    assert layers[1] == ["inst_b"]  # B依赖A
    assert layers[2] == ["inst_c"]  # C依赖B

    print("✓ 拓扑排序测试（简单链式）通过\n")


def test_topology_parallel():
    """测试拓扑排序 - 并行情况"""
    print("=" * 60)
    print("测试拓扑排序 - 并行依赖 (A, B -> C)")
    print("=" * 60)

    # 创建节点实例
    nodes = [
        NodeInstance(id="inst_a", package="node_a"),
        NodeInstance(id="inst_a2", package="node_a"),  # 另一个A实例
        NodeInstance(id="inst_c", package="node_c"),
    ]

    # 创建边：A -> C, A2 -> C
    edges = [
        Edge(from_node="inst_a", from_port="output1", to_node="inst_c", to_port="input1"),
    ]

    # 拓扑排序
    analyzer = TopologyAnalyzer(nodes, edges)
    layers = analyzer.topological_sort()

    print(f"✓ 拓扑排序结果: {layers}")

    # 验证结果
    assert len(layers) == 2
    assert set(layers[0]) == {"inst_a", "inst_a2"}  # A和A2都无依赖，可并行
    assert layers[1] == ["inst_c"]  # C依赖A

    print("✓ 拓扑排序测试（并行启动）通过\n")


def test_topology_cyclic():
    """测试拓扑排序 - 循环依赖检测"""
    print("=" * 60)
    print("测试循环依赖检测")
    print("=" * 60)

    # 创建节点实例 - 循环依赖场景（需要特殊的端口配置）
    # 这里使用简单的方式模拟：A依赖B，B依赖A
    nodes = [
        NodeInstance(id="inst_a", package="node_b"),  # 使用node_b(有输入输出)
        NodeInstance(id="inst_b", package="node_b"),
    ]

    # 创建循环边：A -> B -> A
    edges = [
        Edge(from_node="inst_a", from_port="output1", to_node="inst_b", to_port="input1"),
        Edge(from_node="inst_b", from_port="output1", to_node="inst_a", to_port="input1"),
    ]

    # 拓扑排序应该抛出循环依赖异常
    analyzer = TopologyAnalyzer(nodes, edges)

    try:
        layers = analyzer.topological_sort()
        print("✗ 循环依赖检测失败：应该抛出异常")
        assert False, "Should detect cyclic dependency"
    except CyclicDependencyError as e:
        print(f"✓ 成功检测到循环依赖: {e.nodes}")

    print("✓ 循环依赖检测测试通过\n")


def test_graph_validation():
    """测试图验证"""
    print("=" * 60)
    print("测试图验证")
    print("=" * 60)

    registry = NodeRegistry("tests/fixtures/test_node_hub")
    registry.load_all()

    # 创建节点实例
    nodes = [
        NodeInstance(id="inst_a", package="node_a"),
        NodeInstance(id="inst_b", package="node_b"),
    ]

    # 创建边
    edges = [
        Edge(from_node="inst_a", from_port="output1", to_node="inst_b", to_port="input1"),
    ]

    # 验证图
    validator = GraphValidator()
    result = validator.validate(nodes, edges, registry)

    if result.is_valid:
        print("✓ 图验证通过")
    else:
        print(f"✗ 图验证失败: {result.errors}")

    assert result.is_valid

    # 测试非法端口
    edges_invalid = [
        Edge(from_node="inst_a", from_port="nonexistent", to_node="inst_b", to_port="input1"),
    ]

    result_invalid = validator.validate(nodes, edges_invalid, registry)
    assert not result_invalid.is_valid
    print("✓ 成功检测到非法端口")

    print("✓ 图验证测试通过\n")


if __name__ == "__main__":
    try:
        test_node_scanner()
        test_node_registry()
        test_topology_simple()
        test_topology_parallel()
        test_topology_cyclic()
        test_graph_validation()

        print("=" * 60)
        print("里程碑2所有测试通过！")
        print("=" * 60)
    except Exception as e:
        print(f"测试失败: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
