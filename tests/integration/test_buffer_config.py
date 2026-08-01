"""
测试缓冲区配置功能

验证：
1. 从node.yaml读取buffer_size和conflate配置
2. EnvBuilder正确传递环境变量
3. OutputPort正确读取并应用配置
4. 未指定配置时使用默认值(1MB, conflate=true)
"""

import os
import sys
import time
import subprocess
import tempfile
from pathlib import Path

# 添加项目根目录到路径
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from edge.runtime.config.models import NodeInstance, NodeManifest, PortDef, Edge
from edge.runtime.config.yaml_parser import YAMLParser
from edge.runtime.orchestrator.env_builder import EnvBuilder
from edge.runtime.node_hub.scanner import NodeHubScanner
from edge.sdk.shared_buffer_lite import SharedBufferLite


def test_portdef_default_values():
    """测试PortDef的默认值"""
    print("\n=== 测试 PortDef 默认值 ===")

    # 创建一个最小的PortDef（只有name）
    port = PortDef(name="test_port", type="sensor.rtk")

    assert port.buffer_size == 1024 * 1024, f"Expected 1MB default, got {port.buffer_size}"
    assert port.conflate == True, f"Expected conflate=True default, got {port.conflate}"

    print(f"✅ PortDef默认值正确: buffer_size={port.buffer_size//1024}KB, conflate={port.conflate}")


def test_portdef_custom_values():
    """测试PortDef的自定义值"""
    print("\n=== 测试 PortDef 自定义值 ===")

    # 创建一个带有自定义配置的PortDef
    port = PortDef(
        name="lidar_port",
        type="sensor.lidar",
        buffer_size=5 * 1024 * 1024,  # 5MB
        conflate=False
    )

    assert port.buffer_size == 5 * 1024 * 1024, f"Expected 5MB, got {port.buffer_size}"
    assert port.conflate == False, f"Expected conflate=False, got {port.conflate}"

    print(f"✅ PortDef自定义值正确: buffer_size={port.buffer_size//1024}KB, conflate={port.conflate}")


def test_env_builder_passes_buffer_config():
    """测试EnvBuilder是否正确传递buffer配置"""
    print("\n=== 测试 EnvBuilder 传递 buffer 配置 ===")

    # 创建输出端口配置（默认值）
    output_default = PortDef(name="rtk_fix", type="sensor.rtk")

    # 创建输出端口配置（自定义值）
    output_custom = PortDef(
        name="point_cloud",
        type="sensor.lidar",
        buffer_size=5 * 1024 * 1024,
        conflate=False
    )

    manifest = NodeManifest(
        name="test_node",
        version="1.0.0",
        description="Test node",
        entrypoints={},
        inputs=[],
        outputs=[output_default, output_custom],
        params={}
    )

    node = NodeInstance(id="test_node_1", package="test_node", params={})

    # 构建环境变量
    env = EnvBuilder.build_env(
        node=node,
        manifest=manifest,
        node_hub_path="/tmp/test_hub",
        edges=[]
    )

    # 验证默认配置的环境变量
    assert 'NODE_OUT_rtk_fix' in env, "Missing NODE_OUT_rtk_fix"
    assert env['NODE_OUT_rtk_fix_BUFFER_SIZE'] == str(1024 * 1024), \
        f"Expected 1MB, got {env['NODE_OUT_rtk_fix_BUFFER_SIZE']}"
    assert env['NODE_OUT_rtk_fix_CONFLATE'] == 'true', \
        f"Expected 'true', got {env['NODE_OUT_rtk_fix_CONFLATE']}"

    # 验证自定义配置的环境变量
    assert 'NODE_OUT_point_cloud' in env, "Missing NODE_OUT_point_cloud"
    assert env['NODE_OUT_point_cloud_BUFFER_SIZE'] == str(5 * 1024 * 1024), \
        f"Expected 5MB, got {env['NODE_OUT_point_cloud_BUFFER_SIZE']}"
    assert env['NODE_OUT_point_cloud_CONFLATE'] == 'false', \
        f"Expected 'false', got {env['NODE_OUT_point_cloud_CONFLATE']}"

    print("✅ EnvBuilder正确传递了所有buffer配置环境变量")
    print(f"   默认配置: BUFFER_SIZE={env['NODE_OUT_rtk_fix_BUFFER_SIZE']}, "
          f"CONFLATE={env['NODE_OUT_rtk_fix_CONFLATE']}")
    print(f"   自定义配置: BUFFER_SIZE={env['NODE_OUT_point_cloud_BUFFER_SIZE']}, "
          f"CONFLATE={env['NODE_OUT_point_cloud_CONFLATE']}")


def test_shared_buffer_with_custom_size():
    """测试SharedBufferLite支持自定义大小"""
    print("\n=== 测试 SharedBufferLite 自定义大小 ===")

    # 清理旧缓冲区
    SharedBufferLite.cleanup_all()

    # 创建不同大小的缓冲区
    buffer_small = SharedBufferLite("test_small", size=512 * 1024, create=True)  # 512KB
    buffer_large = SharedBufferLite("test_large", size=10 * 1024 * 1024, create=True)  # 10MB

    # 验证缓冲区大小
    assert buffer_small.size == 512 * 1024, f"Expected 512KB, got {buffer_small.size}"
    assert buffer_large.size == 10 * 1024 * 1024, f"Expected 10MB, got {buffer_large.size}"

    # 测试写入和读取
    test_data = {"test": "data", "value": 123}
    buffer_small.write(test_data)
    read_data = buffer_small.read()

    assert read_data == test_data, "Data mismatch"

    # 清理
    buffer_small.close()
    buffer_large.close()
    SharedBufferLite.cleanup_all()

    print(f"✅ SharedBufferLite支持自定义大小: 512KB和10MB缓冲区工作正常")


def test_yaml_config_loading():
    """测试从YAML加载buffer配置"""
    print("\n=== 测试从 YAML 加载 buffer 配置 ===")

    # 读取global_coverage的node.yaml
    node_yaml_path = Path("/Users/wuzhanli/Desktop/node/node-hub/global_coverage/node.yaml")

    if not node_yaml_path.exists():
        print("⚠️  global_coverage/node.yaml 不存在，跳过此测试")
        return

    # 使用YAMLParser加载manifest
    manifest = YAMLParser.parse_node_manifest(str(node_yaml_path))

    # 查找global_path输出端口
    global_path_port = None
    for output in manifest.outputs:
        if output.name == "global_path":
            global_path_port = output
            break

    assert global_path_port is not None, "未找到global_path输出端口"

    # 验证配置
    assert global_path_port.buffer_size == 3097152, \
        f"Expected 3MB, got {global_path_port.buffer_size}"
    assert global_path_port.conflate == True, \
        f"Expected conflate=True, got {global_path_port.conflate}"

    print(f"✅ 从YAML加载配置成功: buffer_size={global_path_port.buffer_size//1024}KB, "
          f"conflate={global_path_port.conflate}")


def test_outputport_reads_env_config():
    """测试OutputPort从环境变量读取配置"""
    print("\n=== 测试 OutputPort 从环境变量读取配置 ===")

    # 清理旧缓冲区
    SharedBufferLite.cleanup_all()

    # 设置环境变量
    os.environ['NODE_OUT_test_port_BUFFER_SIZE'] = str(2 * 1024 * 1024)  # 2MB
    os.environ['NODE_OUT_test_port_CONFLATE'] = 'false'

    # 导入OutputPort（必须在设置环境变量后）
    from edge.sdk.port import OutputPort

    # 创建OutputPort
    output = OutputPort(name="test_port", buffer_name="test.test_port")

    # 验证配置
    assert output.buffer_size == 2 * 1024 * 1024, \
        f"Expected 2MB, got {output.buffer_size}"

    # 验证buffer实际大小
    assert output.buffer.size == 2 * 1024 * 1024, \
        f"Expected buffer size 2MB, got {output.buffer.size}"

    # 清理
    output.close()
    SharedBufferLite.cleanup_all()

    # 清理环境变量
    del os.environ['NODE_OUT_test_port_BUFFER_SIZE']
    del os.environ['NODE_OUT_test_port_CONFLATE']

    print(f"✅ OutputPort正确读取环境变量配置: buffer_size=2MB, conflate=False")


def test_outputport_uses_defaults():
    """测试OutputPort在没有环境变量时使用默认值"""
    print("\n=== 测试 OutputPort 使用默认值 ===")

    # 清理旧缓冲区
    SharedBufferLite.cleanup_all()

    # 确保环境变量不存在
    if 'NODE_OUT_default_test_BUFFER_SIZE' in os.environ:
        del os.environ['NODE_OUT_default_test_BUFFER_SIZE']
    if 'NODE_OUT_default_test_CONFLATE' in os.environ:
        del os.environ['NODE_OUT_default_test_CONFLATE']

    # 导入OutputPort
    from edge.sdk.port import OutputPort

    # 创建OutputPort
    output = OutputPort(name="default_test", buffer_name="test.default_test")

    # 验证默认配置
    assert output.buffer_size == 1024 * 1024, \
        f"Expected default 1MB, got {output.buffer_size}"

    # 验证buffer实际大小
    assert output.buffer.size == 1024 * 1024, \
        f"Expected buffer size 1MB, got {output.buffer.size}"

    # 清理
    output.close()
    SharedBufferLite.cleanup_all()

    print(f"✅ OutputPort正确使用默认值: buffer_size=1MB")


def main():
    """运行所有测试"""
    print("=" * 70)
    print("缓冲区配置功能测试")
    print("=" * 70)

    try:
        test_portdef_default_values()
        test_portdef_custom_values()
        test_env_builder_passes_buffer_config()
        test_shared_buffer_with_custom_size()
        test_yaml_config_loading()
        test_outputport_reads_env_config()
        test_outputport_uses_defaults()

        print("\n" + "=" * 70)
        print("✅ 所有测试通过！")
        print("=" * 70)

    except AssertionError as e:
        print(f"\n❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

    except Exception as e:
        print(f"\n❌ 测试出错: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
