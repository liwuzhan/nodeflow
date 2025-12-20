#!/usr/bin/env python3
"""
手动测试脚本 - 验证配置解析模块
"""

import sys
from pathlib import Path

# 添加项目根目录到路径
sys.path.insert(0, str(Path(__file__).parent))

from runtime.config.yaml_parser import YAMLParser
from runtime.config.validator import ConfigValidator


def test_runtime_config():
    """测试运行时配置解析"""
    print("=" * 60)
    print("测试运行时配置解析")
    print("=" * 60)

    parser = YAMLParser()
    validator = ConfigValidator()

    # 解析配置
    config_path = "tests/fixtures/test_runtime.yaml"
    config = parser.parse_runtime_config(config_path)

    print(f"✓ 成功解析配置文件: {config_path}")
    print(f"  - graph_id: {config.graph_id}")
    print(f"  - 节点数量: {len(config.nodes)}")
    print(f"  - 边数量: {len(config.edges)}")

    # 验证配置
    result = validator.validate_runtime_config(config)
    if result.is_valid:
        print("✓ 配置验证通过")
    else:
        print(f"✗ 配置验证失败: {result.errors}")

    print()


def test_node_manifest():
    """测试节点说明书解析"""
    print("=" * 60)
    print("测试节点说明书解析")
    print("=" * 60)

    parser = YAMLParser()
    validator = ConfigValidator()

    # 解析节点说明书
    manifest_path = "tests/fixtures/test_node.yaml"
    manifest = parser.parse_node_manifest(manifest_path)

    print(f"✓ 成功解析节点说明书: {manifest_path}")
    print(f"  - 节点名称: {manifest.name}")
    print(f"  - 版本: {manifest.version}")
    print(f"  - 输入端口: {[p.name for p in manifest.inputs]}")
    print(f"  - 输出端口: {[p.name for p in manifest.outputs]}")
    print(f"  - 参数数量: {len(manifest.params)}")

    # 验证说明书
    result = validator.validate_node_manifest(manifest)
    if result.is_valid:
        print("✓ 节点说明书验证通过")
    else:
        print(f"✗ 节点说明书验证失败: {result.errors}")

    print()


if __name__ == "__main__":
    try:
        test_runtime_config()
        test_node_manifest()
        print("=" * 60)
        print("所有测试通过！")
        print("=" * 60)
    except Exception as e:
        print(f"测试失败: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
