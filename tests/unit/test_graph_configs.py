from pathlib import Path

import pytest

from edge.runtime.config.validator import ConfigValidator
from edge.runtime.config.yaml_parser import YAMLParser
from edge.runtime.graph.validator import GraphValidator
from edge.runtime.node_hub.node_registry import NodeRegistry


PROJECT_ROOT = Path(__file__).resolve().parents[2]
GRAPH_CONFIGS = sorted(
    path
    for path in (PROJECT_ROOT / "configs" / "graphs").glob("*.yaml")
    if path.name != "tillage_task.yaml"
)


@pytest.fixture(scope="module")
def node_registry():
    registry = NodeRegistry(str(PROJECT_ROOT / "edge" / "nodes"))
    registry.load_all()
    return registry


@pytest.mark.parametrize("config_path", GRAPH_CONFIGS, ids=lambda path: path.stem)
def test_deployable_graph_config_resolves_current_node_packages(config_path, node_registry):
    config = YAMLParser().parse_runtime_config(str(config_path))

    config_result = ConfigValidator().validate_runtime_config(config)
    assert config_result.is_valid, config_result.errors
    assert Path(config.node_hub_path) == Path("edge/nodes")

    missing_packages = [
        node.package for node in config.nodes if not node_registry.has_package(node.package)
    ]
    assert missing_packages == []

    graph_result = GraphValidator().validate(config.nodes, config.edges, node_registry)
    assert graph_result.is_valid, graph_result.errors

