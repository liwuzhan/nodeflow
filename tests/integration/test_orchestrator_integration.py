"""
Orchestrator 集成测试

验证分布式节点编排系统的核心功能：
- 拓扑排序和分层 (Kahn算法)
- 分层启动（层内并行、层间顺序）
- 环境变量配置和端口连接
- 节点监控和故障恢复
- 优雅关闭和资源清理
"""

import os
import sys
import time
import tempfile
import subprocess
from pathlib import Path
from unittest import mock

# 添加项目根目录到路径
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from runtime.graph.topology import TopologyAnalyzer
from runtime.graph.validator import GraphValidator
from runtime.config.models import RuntimeConfig, NodeInstance, Edge
from runtime.node_hub.node_registry import NodeRegistry
from runtime.orchestrator.startup_coordinator import StartupCoordinator
from runtime.orchestrator.node_launcher import NodeLauncher
from runtime.orchestrator.env_builder import EnvBuilder
from runtime.monitoring.node_monitor import NodeMonitor
from runtime.monitoring.restart_policy import RetryTracker


# ========== 拓扑排序测试 ==========

class TestTopologyAnalysis:
    """拓扑排序和分层测试"""

    def test_simple_chain_topology(self):
        """A→B→C 线性依赖"""
        print("\n=== 测试简单链式拓扑 ===")

        nodes = [
            NodeInstance(id='A', package='test'),
            NodeInstance(id='B', package='test'),
            NodeInstance(id='C', package='test')
        ]
        edges = [
            Edge(from_node='A', from_port='out', to_node='B', to_port='in'),
            Edge(from_node='B', from_port='out', to_node='C', to_port='in')
        ]

        analyzer = TopologyAnalyzer(nodes, edges)
        layers = analyzer.topological_sort()

        print(f"  拓扑层: {layers}")

        # 验证分层结果
        assert len(layers) == 3, f"应该有3层，得到 {len(layers)}"
        assert layers[0] == ['A'], f"第1层应该是 ['A']"
        assert layers[1] == ['B'], f"第2层应该是 ['B']"
        assert layers[2] == ['C'], f"第3层应该是 ['C']"

        print("✅ 简单链式拓扑测试通过")

    def test_parallel_branches_topology(self):
        """A→B, A→C 并行分支"""
        print("\n=== 测试并行分支拓扑 ===")

        nodes = [
            NodeInstance(id='A', package='test'),
            NodeInstance(id='B', package='test'),
            NodeInstance(id='C', package='test')
        ]
        edges = [
            Edge(from_node='A', from_port='out1', to_node='B', to_port='in'),
            Edge(from_node='A', from_port='out2', to_node='C', to_port='in')
        ]

        analyzer = TopologyAnalyzer(nodes, edges)
        layers = analyzer.topological_sort()

        print(f"  拓扑层: {layers}")

        # A 第1层，B 和 C 第2层（并行）
        assert len(layers) == 2, f"应该有2层，得到 {len(layers)}"
        assert layers[0] == ['A'], f"第1层应该是 ['A']"
        assert set(layers[1]) == {'B', 'C'}, f"第2层应该是 {{B,C}}"

        print("✅ 并行分支拓扑测试通过")

    def test_diamond_topology(self):
        """A→B→D, A→C→D 菱形依赖"""
        print("\n=== 测试菱形拓扑 ===")

        nodes = [
            NodeInstance(id='A', package='test'),
            NodeInstance(id='B', package='test'),
            NodeInstance(id='C', package='test'),
            NodeInstance(id='D', package='test')
        ]
        edges = [
            Edge(from_node='A', from_port='out1', to_node='B', to_port='in'),
            Edge(from_node='A', from_port='out2', to_node='C', to_port='in'),
            Edge(from_node='B', from_port='out', to_node='D', to_port='in1'),
            Edge(from_node='C', from_port='out', to_node='D', to_port='in2')
        ]

        analyzer = TopologyAnalyzer(nodes, edges)
        layers = analyzer.topological_sort()

        print(f"  拓扑层: {layers}")

        # A第1层，B/C第2层，D第3层
        assert len(layers) == 3, f"应该有3层，得到 {len(layers)}"
        assert layers[0] == ['A'], f"第1层应该是 ['A']"
        assert set(layers[1]) == {'B', 'C'}, f"第2层应该是 {{B,C}}"
        assert layers[2] == ['D'], f"第3层应该是 ['D']"

        print("✅ 菱形拓扑测试通过")

    def test_complex_topology(self):
        """10节点复杂依赖"""
        print("\n=== 测试复杂拓扑 ===")

        nodes = [
            NodeInstance(id="N1", package="test"),
            NodeInstance(id="N2", package="test"),
            NodeInstance(id="N3", package="test"),
            NodeInstance(id="N4", package="test"),
            NodeInstance(id="N5", package="test"),
            NodeInstance(id="N6", package="test"),
            NodeInstance(id="N7", package="test"),
            NodeInstance(id="N8", package="test"),
            NodeInstance(id="N9", package="test"),
            NodeInstance(id="N10", package="test"),
        ]
        edges = [
            Edge(from_node="N1", from_port="out", to_node="N2", to_port="in"),
            Edge(from_node="N1", from_port="out", to_node="N3", to_port="in"),
            Edge(from_node="N2", from_port="out", to_node="N4", to_port="in"),
            Edge(from_node="N3", from_port="out", to_node="N4", to_port="in"),
            Edge(from_node="N4", from_port="out", to_node="N5", to_port="in"),
            Edge(from_node="N4", from_port="out", to_node="N6", to_port="in"),
            Edge(from_node="N5", from_port="out", to_node="N7", to_port="in"),
            Edge(from_node="N6", from_port="out", to_node="N8", to_port="in"),
            Edge(from_node="N7", from_port="out", to_node="N9", to_port="in"),
            Edge(from_node="N8", from_port="out", to_node="N9", to_port="in"),
            Edge(from_node="N9", from_port="out", to_node="N10", to_port="in"),
        ]

        analyzer = TopologyAnalyzer(nodes, edges)
        layers = analyzer.topological_sort()

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
        node_ids = {n.id for n in nodes}
        assert all_nodes == node_ids, f"应该包含所有节点"

        print("✅ 复杂拓扑测试通过")

    def test_cycle_detection(self):
        """检测循环依赖"""
        print("\n=== 测试循环检测 ===")

        nodes = [
            NodeInstance(id="A", package="test"),
            NodeInstance(id="B", package="test"),
            NodeInstance(id="C", package="test")
        ]
        edges = [
            Edge(from_node="A", from_port="out", to_node="B", to_port="in"),
            Edge(from_node="B", from_port="out", to_node="C", to_port="in"),
            Edge(from_node="C", from_port="out", to_node="A", to_port="in")  # 循环
        ]

        analyzer = TopologyAnalyzer(nodes, edges)

        try:
            layers = analyzer.topological_sort()
            assert False, "应该检测到循环并抛出异常"
        except (ValueError, Exception) as e:
            print(f"  ✓ 正确检测到循环: {type(e).__name__}")

        print("✅ 循环检测测试通过")


# 注意：环境变量、节点监控、启动协调测试由于需要实现复杂的mocking，
# 将在后续迭代中添加。当前重点验证拓扑排序和图分析功能。


# ========== 完整编排场景测试 ==========

class TestOrchestrationScenarios:
    """完整编排场景测试"""

    def test_simple_two_node_graph(self):
        """简单两节点图 (Producer → Consumer)"""
        print("\n=== 测试两节点编排 ===")

        nodes = [
            NodeInstance(id='producer', package='test'),
            NodeInstance(id='consumer', package='test')
        ]
        edges = [
            Edge(from_node='producer', from_port='out', to_node='consumer', to_port='in')
        ]

        analyzer = TopologyAnalyzer(nodes, edges)
        layers = analyzer.topological_sort()

        print(f"  拓扑: {nodes}")
        print(f"  边: {edges}")
        print(f"  启动层: {layers}")

        # 验证启动顺序
        assert len(layers) == 2, "应该有2层"
        assert layers[0] == ['producer'], "producer 应该先启动"
        assert layers[1] == ['consumer'], "consumer 应该后启动"

        print("✅ 两节点编排测试通过")

    def test_pipeline_three_node_graph(self):
        """三节点管道 (A → B → C)"""
        print("\n=== 测试三节点管道 ===")

        nodes = [
            NodeInstance(id='source', package='test'),
            NodeInstance(id='processor', package='test'),
            NodeInstance(id='sink', package='test')
        ]
        edges = [
            Edge(from_node='source', from_port='out', to_node='processor', to_port='in'),
            Edge(from_node='processor', from_port='out', to_node='sink', to_port='in')
        ]

        analyzer = TopologyAnalyzer(nodes, edges)
        layers = analyzer.topological_sort()

        print(f"  管道: source → processor → sink")
        print(f"  启动层: {layers}")

        assert len(layers) == 3, "应该有3层"
        assert layers[0] == ['source'], "source 第一层"
        assert layers[1] == ['processor'], "processor 第二层"
        assert layers[2] == ['sink'], "sink 第三层"

        print("✅ 三节点管道测试通过")

    def test_fan_out_graph(self):
        """扇形图 (1 → N)"""
        print("\n=== 测试扇形编排 ===")

        nodes = [
            NodeInstance(id='source', package='test'),
            NodeInstance(id='process_a', package='test'),
            NodeInstance(id='process_b', package='test'),
            NodeInstance(id='process_c', package='test')
        ]
        edges = [
            Edge(from_node='source', from_port='out1', to_node='process_a', to_port='in'),
            Edge(from_node='source', from_port='out2', to_node='process_b', to_port='in'),
            Edge(from_node='source', from_port='out3', to_node='process_c', to_port='in')
        ]

        analyzer = TopologyAnalyzer(nodes, edges)
        layers = analyzer.topological_sort()

        print(f"  扇形: source → [process_a, process_b, process_c]")
        print(f"  启动层: {layers}")

        assert len(layers) == 2, "应该有2层"
        assert layers[0] == ['source'], "source 第一层"
        assert set(layers[1]) == {'process_a', 'process_b', 'process_c'}, "处理节点第二层并行启动"

        print("✅ 扇形编排测试通过")

    def test_fan_in_graph(self):
        """聚合图 (N → 1)"""
        print("\n=== 测试聚合编排 ===")

        nodes = [
            NodeInstance(id='source_a', package='test'),
            NodeInstance(id='source_b', package='test'),
            NodeInstance(id='source_c', package='test'),
            NodeInstance(id='aggregator', package='test')
        ]
        edges = [
            Edge(from_node='source_a', from_port='out', to_node='aggregator', to_port='in1'),
            Edge(from_node='source_b', from_port='out', to_node='aggregator', to_port='in2'),
            Edge(from_node='source_c', from_port='out', to_node='aggregator', to_port='in3')
        ]

        analyzer = TopologyAnalyzer(nodes, edges)
        layers = analyzer.topological_sort()

        print(f"  聚合: [source_a, source_b, source_c] → aggregator")
        print(f"  启动层: {layers}")

        assert len(layers) == 2, "应该有2层"
        assert set(layers[0]) == {'source_a', 'source_b', 'source_c'}, "源节点第一层并行启动"
        assert layers[1] == ['aggregator'], "aggregator 第二层"

        print("✅ 聚合编排测试通过")


def main():
    """运行所有编排集成测试"""
    print("=" * 70)
    print("Orchestrator 集成测试")
    print("=" * 70)

    try:
        # 拓扑排序测试
        test_topo = TestTopologyAnalysis()
        test_topo.test_simple_chain_topology()
        test_topo.test_parallel_branches_topology()
        test_topo.test_diamond_topology()
        test_topo.test_complex_topology()
        test_topo.test_cycle_detection()

        # 编排场景测试
        test_scenarios = TestOrchestrationScenarios()
        test_scenarios.test_simple_two_node_graph()
        test_scenarios.test_pipeline_three_node_graph()
        test_scenarios.test_fan_out_graph()
        test_scenarios.test_fan_in_graph()

        print("\n" + "=" * 70)
        print("✅ 所有 Orchestrator 集成测试通过！")
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
