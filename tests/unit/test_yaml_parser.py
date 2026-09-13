"""
YAML解析器单元测试
"""

import pytest
from pathlib import Path

from edge.runtime.config.yaml_parser import YAMLParser
from edge.runtime.config.models import RuntimeConfig, NodeManifest
from edge.runtime.utils.errors import YAMLParseError


# 获取fixtures目录路径
FIXTURES_DIR = Path(__file__).parent.parent / "fixtures"


class TestYAMLParser:
    """YAML解析器测试类"""

    def test_parse_runtime_config_success(self):
        """测试成功解析运行时配置"""
        parser = YAMLParser()
        config_path = FIXTURES_DIR / "test_runtime.yaml"

        config = parser.parse_runtime_config(str(config_path))

        # 验证基本字段
        assert isinstance(config, RuntimeConfig)
        assert config.graph_id == "test_graph"
        assert config.graph_version == 1
        assert config.node_hub_path == "./node-hub"

        # 验证节点
        assert len(config.nodes) == 2
        assert config.nodes[0].id == "node_a"
        assert config.nodes[0].package == "test_node_a"
        assert config.nodes[0].params == {"param1": "value1", "param2": 42}

        # 验证边
        assert len(config.edges) == 1
        assert config.edges[0].from_node == "node_a"
        assert config.edges[0].from_port == "output1"
        assert config.edges[0].to_node == "node_b"
        assert config.edges[0].to_port == "input1"

        # 验证重启策略
        assert config.restart_policy.max_retries == 3
        assert config.restart_policy.backoff_ms == 500

    def test_parse_runtime_config_file_not_found(self):
        """测试文件不存在的情况"""
        parser = YAMLParser()

        with pytest.raises(YAMLParseError):
            parser.parse_runtime_config("nonexistent.yaml")

    def test_parse_node_manifest_success(self):
        """测试成功解析节点说明书"""
        parser = YAMLParser()
        manifest_path = FIXTURES_DIR / "test_node.yaml"

        manifest = parser.parse_node_manifest(str(manifest_path))

        # 验证基本字段
        assert isinstance(manifest, NodeManifest)
        assert manifest.name == "test_node"
        assert manifest.version == "0.1.0"
        assert manifest.description == "Test node for unit tests"

        # 验证entrypoints
        assert "linux" in manifest.entrypoints
        assert manifest.entrypoints["linux"].kind == "python"
        assert manifest.entrypoints["linux"].cmd == ["python3", "run.py"]

        # 验证输入端口
        assert len(manifest.inputs) == 1
        assert manifest.inputs[0].name == "input1"
        assert manifest.inputs[0].type == "test.input"

        # 验证输出端口
        assert len(manifest.outputs) == 1
        assert manifest.outputs[0].name == "output1"
        assert manifest.outputs[0].type == "test.output"

        # 验证参数定义
        assert "param1" in manifest.params
        assert manifest.params["param1"].type == "string"
        assert manifest.params["param1"].required is True

        assert "param2" in manifest.params
        assert manifest.params["param2"].type == "int"
        assert manifest.params["param2"].default == 100

    def test_parse_node_manifest_file_not_found(self):
        """测试文件不存在的情况"""
        parser = YAMLParser()

        with pytest.raises(YAMLParseError):
            parser.parse_node_manifest("nonexistent.yaml")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
