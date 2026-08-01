"""
拓扑排序模块
实现基于Kahn算法的拓扑排序，计算节点启动顺序
"""

from typing import Dict, List, Set
from collections import defaultdict

from edge.runtime.config.models import NodeInstance, Edge
from edge.runtime.utils.errors import CyclicDependencyError
from edge.runtime.utils.logger import get_logger

logger = get_logger(__name__)


class TopologyAnalyzer:
    """拓扑分析器"""

    def __init__(self, nodes: List[NodeInstance], edges: List[Edge]):
        """
        初始化拓扑分析器

        参数：
        - nodes: 节点实例列表
        - edges: 连接关系列表
        """
        self.nodes = {n.id: n for n in nodes}
        self.edges = edges
        self.graph = self._build_dependency_graph()

    def _build_dependency_graph(self) -> Dict[str, List[str]]:
        """
        构建依赖关系图（邻接表）

        依赖关系规则：
        - 如果 A.output -> B.input，则 B 依赖 A
        - 即：B 必须等 A 启动后才能启动

        返回：
        - 节点ID -> 依赖的节点ID列表的映射
        """
        graph = {node_id: [] for node_id in self.nodes}

        for edge in self.edges:
            from_node = edge.from_node
            to_node = edge.to_node

            # to_node依赖from_node
            if from_node not in graph[to_node]:
                graph[to_node].append(from_node)

        logger.debug(f"Dependency graph: {graph}")
        return graph

    def topological_sort(self) -> List[List[str]]:
        """
        拓扑排序，返回分层启动列表

        使用Kahn算法实现：
        1. 计算每个节点的入度（依赖数量）
        2. 将入度为0的节点加入队列（第一层）
        3. 处理队列中的节点，减少后继节点入度
        4. 将新的入度为0的节点加入下一层
        5. 重复直到所有节点处理完毕

        返回：
        - 分层节点列表：[[layer0_nodes], [layer1_nodes], ...]
          - layer0: 无依赖的节点，可并行启动
          - layer1: 仅依赖layer0的节点，可并行启动
          - ...

        异常：
        - CyclicDependencyError: 检测到循环依赖
        """
        # 计算每个节点的入度
        in_degree = self._calculate_in_degree()
        logger.debug(f"Initial in-degree: {in_degree}")

        # 创建逆向图（node -> 哪些节点依赖它）
        reverse_graph = self._build_reverse_graph()

        layers = []
        processed = set()

        while True:
            # 找出当前入度为0的节点（当前层）
            current_layer = [
                node_id for node_id, degree in in_degree.items()
                if degree == 0 and node_id not in processed
            ]

            if not current_layer:
                break

            logger.debug(f"Layer {len(layers)}: {current_layer}")
            layers.append(sorted(current_layer))  # 排序保证确定性

            # 标记为已处理
            for node_id in current_layer:
                processed.add(node_id)

            # 更新后继节点的入度
            for node_id in current_layer:
                # 找到所有依赖当前节点的节点
                successors = reverse_graph.get(node_id, [])
                for successor in successors:
                    if successor not in processed:
                        in_degree[successor] -= 1

        # 检查是否有循环依赖
        remaining = [node_id for node_id in in_degree if node_id not in processed]
        if remaining:
            logger.error(f"Cyclic dependency detected: {remaining}")
            raise CyclicDependencyError(remaining)

        logger.info(f"Topological sort completed: {len(layers)} layers")
        return layers

    def _calculate_in_degree(self) -> Dict[str, int]:
        """
        计算每个节点的入度（依赖数量）

        返回：
        - 节点ID -> 入度的映射
        """
        in_degree = {node_id: 0 for node_id in self.nodes}

        for node_id, dependencies in self.graph.items():
            in_degree[node_id] = len(dependencies)

        return in_degree

    def _build_reverse_graph(self) -> Dict[str, List[str]]:
        """
        构建逆向图：节点 -> 哪些节点依赖它

        返回：
        - 节点ID -> 依赖它的节点ID列表
        """
        reverse_graph = defaultdict(list)

        for node_id, dependencies in self.graph.items():
            for dep_node_id in dependencies:
                reverse_graph[dep_node_id].append(node_id)

        return dict(reverse_graph)

    def get_dependencies(self, node_id: str) -> List[str]:
        """
        获取节点的直接依赖列表

        参数：
        - node_id: 节点ID

        返回：
        - 依赖的节点ID列表
        """
        return self.graph.get(node_id, [])

    def get_dependents(self, node_id: str) -> List[str]:
        """
        获取依赖该节点的节点列表

        参数：
        - node_id: 节点ID

        返回：
        - 依赖该节点的节点ID列表
        """
        reverse_graph = self._build_reverse_graph()
        return reverse_graph.get(node_id, [])

    def is_independent(self, node_id: str) -> bool:
        """
        判断节点是否无依赖

        参数：
        - node_id: 节点ID

        返回：
        - True表示无依赖，False表示有依赖
        """
        return len(self.graph.get(node_id, [])) == 0
