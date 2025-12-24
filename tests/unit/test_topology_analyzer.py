"""
TopologyAnalyzer 单元测试

验证拓扑排序和循环检测：
- 拓扑排序正确性（链式、并行、菱形、复杂图）
- 分层结果验证
- 循环检测
- 边缘情况处理
"""

import sys
from pathlib import Path

# 添加项目根目录到路径
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from runtime.graph.topology import TopologyAnalyzer


class TestTopologySorting:
    """拓扑排序正确性测试"""

    def test_simple_chain(self):
        """A→B→C 线性图"""
        print("\n=== 测试简单链式依赖 ===")

        analyzer = TopologyAnalyzer()

        # 构建图：A→B→C
        nodes = ['A', 'B', 'C']
        edges = [('A', 'B'), ('B', 'C')]

        layers = analyzer.topological_sort(nodes, edges)

        print(f"  拓扑层: {layers}")

        # 验证分层结果
        assert len(layers) == 3, f"应该有3层，得到 {len(layers)}"
        assert layers[0] == ['A'], f"第1层应该是 ['A']"
        assert layers[1] == ['B'], f"第2层应该是 ['B']"
        assert layers[2] == ['C'], f"第3层应该是 ['C']"

        print("✅ 简单链式依赖测试通过")

    def test_parallel_branches(self):
        """A→B, A→C 并行分支"""
        print("\n=== 测试并行分支 ===")

        analyzer = TopologyAnalyzer()

        nodes = ['A', 'B', 'C']
        edges = [('A', 'B'), ('A', 'C')]

        layers = analyzer.topological_sort(nodes, edges)

        print(f"  拓扑层: {layers}")

        # A 在第1层，B 和 C 在第2层（可以并行）
        assert len(layers) == 2, f"应该有2层，得到 {len(layers)}"
        assert layers[0] == ['A'], f"第1层应该是 ['A']"
        assert set(layers[1]) == {'B', 'C'}, f"第2层应该是 {{B,C}}"

        print("✅ 并行分支测试通过")

    def test_diamond_graph(self):
        """A→B→D, A→C→D 菱形依赖"""
        print("\n=== 测试菱形依赖 ===")

        analyzer = TopologyAnalyzer()

        nodes = ['A', 'B', 'C', 'D']
        edges = [('A', 'B'), ('A', 'C'), ('B', 'D'), ('C', 'D')]

        layers = analyzer.topological_sort(nodes, edges)

        print(f"  拓扑层: {layers}")

        # A 第1层，B/C 第2层，D 第3层
        assert len(layers) == 3, f"应该有3层，得到 {len(layers)}"
        assert layers[0] == ['A'], f"第1层应该是 ['A']"
        assert set(layers[1]) == {'B', 'C'}, f"第2层应该是 {{B,C}}"
        assert layers[2] == ['D'], f"第3层应该是 ['D']"

        print("✅ 菱形依赖测试通过")

    def test_complex_graph(self):
        """10节点复杂依赖"""
        print("\n=== 测试复杂依赖图 ===")

        analyzer = TopologyAnalyzer()

        # 构建10节点的复杂图
        nodes = ['N1', 'N2', 'N3', 'N4', 'N5', 'N6', 'N7', 'N8', 'N9', 'N10']
        edges = [
            ('N1', 'N2'), ('N1', 'N3'),
            ('N2', 'N4'), ('N3', 'N4'),
            ('N4', 'N5'), ('N4', 'N6'),
            ('N5', 'N7'), ('N6', 'N8'),
            ('N7', 'N9'), ('N8', 'N9'),
            ('N9', 'N10')
        ]

        layers = analyzer.topological_sort(nodes, edges)

        print(f"  拓扑层数: {len(layers)}")
        for i, layer in enumerate(layers):
            print(f"    第{i+1}层: {layer}")

        # 验证层数和结构
        assert len(layers) >= 5, f"应该至少有5层"
        assert layers[0] == ['N1'], f"第1层应该是 ['N1']"
        assert layers[-1] == ['N10'], f"最后一层应该是 ['N10']"

        # 验证所有节点都被包含
        all_nodes = set()
        for layer in layers:
            all_nodes.update(layer)
        assert all_nodes == set(nodes), f"应该包含所有节点"

        print("✅ 复杂依赖图测试通过")


class TestLayerOrdering:
    """分层结果验证"""

    def test_layer_ordering(self):
        """验证层级顺序正确"""
        print("\n=== 测试层级顺序 ===")

        analyzer = TopologyAnalyzer()

        nodes = ['A', 'B', 'C', 'D']
        edges = [('A', 'B'), ('B', 'C'), ('C', 'D')]

        layers = analyzer.topological_sort(nodes, edges)

        # 验证依赖都在更早的层
        for layer_idx, layer in enumerate(layers):
            for node in layer:
                # 检查该节点的所有被依赖节点是否在更早的层
                dependencies = [src for src, dst in edges if dst == node]
                for dep in dependencies:
                    # 找到依赖所在的层
                    dep_layer = None
                    for i, l in enumerate(layers):
                        if dep in l:
                            dep_layer = i
                            break
                    assert dep_layer is not None, f"依赖 {dep} 应该存在于某一层"
                    assert dep_layer < layer_idx, f"依赖 {dep} 应该在 {node} 的前面"

        print("✅ 层级顺序测试通过")

    def test_no_dependencies_in_layer(self):
        """验证同层节点无依赖关系"""
        print("\n=== 测试同层无依赖 ===")

        analyzer = TopologyAnalyzer()

        nodes = ['A', 'B', 'C', 'D', 'E']
        edges = [('A', 'B'), ('A', 'C'), ('A', 'D'), ('A', 'E')]

        layers = analyzer.topological_sort(nodes, edges)

        # 检查每一层内部是否有边
        for layer_idx, layer in enumerate(layers):
            for src, dst in edges:
                # 如果源和目标都在同一层，就有内部依赖
                if src in layer and dst in layer:
                    # B,C,D,E 都依赖于 A，不应该在同一层
                    assert False, f"同层内不应该有依赖: {src}→{dst}"

        print("✅ 同层无依赖测试通过")


class TestCycleDetection:
    """循环检测测试"""

    def test_simple_cycle_detection(self):
        """A→B→A 循环"""
        print("\n=== 测试简单循环 ===")

        analyzer = TopologyAnalyzer()

        nodes = ['A', 'B']
        edges = [('A', 'B'), ('B', 'A')]  # 循环

        try:
            layers = analyzer.topological_sort(nodes, edges)
            assert False, "应该检测到循环并抛出异常"
        except ValueError as e:
            print(f"  ✓ 正确检测到循环: {e}")

        print("✅ 简单循环检测测试通过")

    def test_self_loop(self):
        """A→A 自环"""
        print("\n=== 测试自环 ===")

        analyzer = TopologyAnalyzer()

        nodes = ['A', 'B']
        edges = [('A', 'A'), ('A', 'B')]  # A 自环

        try:
            layers = analyzer.topological_sort(nodes, edges)
            assert False, "应该检测到自环并抛出异常"
        except ValueError as e:
            print(f"  ✓ 正确检测到自环: {e}")

        print("✅ 自环检测测试通过")

    def test_deep_cycle(self):
        """A→B→C→D→B 深层循环"""
        print("\n=== 测试深层循环 ===")

        analyzer = TopologyAnalyzer()

        nodes = ['A', 'B', 'C', 'D']
        edges = [('A', 'B'), ('B', 'C'), ('C', 'D'), ('D', 'B')]  # B→C→D→B 循环

        try:
            layers = analyzer.topological_sort(nodes, edges)
            assert False, "应该检测到深层循环并抛出异常"
        except ValueError as e:
            print(f"  ✓ 正确检测到深层循环: {e}")

        print("✅ 深层循环检测测试通过")

    def test_no_cycle(self):
        """验证无环图不报错"""
        print("\n=== 测试无环验证 ===")

        analyzer = TopologyAnalyzer()

        nodes = ['A', 'B', 'C', 'D']
        edges = [('A', 'B'), ('A', 'C'), ('B', 'D'), ('C', 'D')]

        try:
            layers = analyzer.topological_sort(nodes, edges)
            print(f"  ✓ 无环图正确排序: {layers}")
        except ValueError as e:
            assert False, f"无环图不应该抛出异常: {e}"

        print("✅ 无环验证测试通过")


class TestEdgeCases:
    """边缘情况测试"""

    def test_single_node(self):
        """单节点图"""
        print("\n=== 测试单节点 ===")

        analyzer = TopologyAnalyzer()

        nodes = ['A']
        edges = []

        layers = analyzer.topological_sort(nodes, edges)

        assert len(layers) == 1, f"应该有1层"
        assert layers[0] == ['A'], f"层应该是 ['A']"

        print("✅ 单节点测试通过")

    def test_disconnected_components(self):
        """两个独立子图"""
        print("\n=== 测试独立子图 ===")

        analyzer = TopologyAnalyzer()

        # 两个独立的链：A→B 和 C→D
        nodes = ['A', 'B', 'C', 'D']
        edges = [('A', 'B'), ('C', 'D')]

        layers = analyzer.topological_sort(nodes, edges)

        print(f"  拓扑层: {layers}")

        # 应该有2层（A/C 在第1层，B/D 在第2层）
        assert len(layers) == 2, f"应该有2层，得到 {len(layers)}"
        assert set(layers[0]) == {'A', 'C'}, f"第1层应该是 {{A,C}}"
        assert set(layers[1]) == {'B', 'D'}, f"第2层应该是 {{B,D}}"

        print("✅ 独立子图测试通过")

    def test_empty_graph(self):
        """空图"""
        print("\n=== 测试空图 ===")

        analyzer = TopologyAnalyzer()

        nodes = []
        edges = []

        layers = analyzer.topological_sort(nodes, edges)

        assert len(layers) == 0, f"空图应该返回空列表，得到 {layers}"

        print("✅ 空图测试通过")


def main():
    """运行所有单元测试"""
    print("=" * 70)
    print("TopologyAnalyzer 单元测试")
    print("=" * 70)

    try:
        # 拓扑排序测试
        test_sort = TestTopologySorting()
        test_sort.test_simple_chain()
        test_sort.test_parallel_branches()
        test_sort.test_diamond_graph()
        test_sort.test_complex_graph()

        # 层级顺序测试
        test_order = TestLayerOrdering()
        test_order.test_layer_ordering()
        test_order.test_no_dependencies_in_layer()

        # 循环检测
        test_cycle = TestCycleDetection()
        test_cycle.test_simple_cycle_detection()
        test_cycle.test_self_loop()
        test_cycle.test_deep_cycle()
        test_cycle.test_no_cycle()

        # 边缘情况
        test_edge = TestEdgeCases()
        test_edge.test_single_node()
        test_edge.test_disconnected_components()
        test_edge.test_empty_graph()

        print("\n" + "=" * 70)
        print("✅ 所有 TopologyAnalyzer 单元测试通过！")
        print("=" * 70)

    except AssertionError as e:
        print(f"\n❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

    except Exception as e:
        print(f"\n❌ 测试错误: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
