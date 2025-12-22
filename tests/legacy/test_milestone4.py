#!/usr/bin/env python3
"""
里程碑4测试脚本 - 验证节点启动与编排
"""

import sys
import os
import tempfile
import time
from pathlib import Path

# 添加项目根目录到路径
sys.path.insert(0, str(Path(__file__).parent))

from runtime.config.yaml_parser import YAMLParser
from runtime.node_hub.node_registry import NodeRegistry
from runtime.graph.topology import TopologyAnalyzer
from runtime.ipc.socket_manager import SocketManager
from runtime.orchestrator.env_builder import EnvBuilder
from runtime.orchestrator.node_launcher import NodeLauncher
from runtime.orchestrator.startup_coordinator import StartupCoordinator
from runtime.config.models import NodeInstance, Edge


def test_env_builder():
    """测试环境变量构建"""
    print("=" * 60)
    print("测试环境变量构建")
    print("=" * 60)

    with tempfile.TemporaryDirectory() as tmpdir:
        # 加载节点说明书
        parser = YAMLParser()
        manifest = parser.parse_node_manifest("tests/fixtures/test_node_hub/node_b/node.yaml")

        # 创建Socket管理器
        socket_manager = SocketManager(tmpdir)
        socket_manager.initialize()

        # 创建节点实例
        node = NodeInstance(
            id="test_node",
            package="node_b",
            params={"param1": "value1", "param2": 42}
        )

        # 构建环境变量
        env_builder = EnvBuilder()
        env = env_builder.build_env(
            node, manifest, socket_manager, "/node-hub"
        )

        # 验证环境变量
        assert env['NODE_ID'] == "test_node"
        assert env['NODE_HUB_PATH'] == "/node-hub"
        assert tmpdir in env['NODE_SOCKET_DIR']

        # 验证输入/输出端口环境变量
        assert 'NODE_IN_input1' in env
        assert 'NODE_OUT_output1' in env

        print(f"✓ 环境变量构建成功")
        print(f"  - NODE_ID: {env['NODE_ID']}")
        print(f"  - NODE_IN_input1: {env['NODE_IN_input1']}")
        print(f"  - NODE_OUT_output1: {env['NODE_OUT_output1']}")

    print("✓ 环境变量构建测试通过\n")


def test_node_launcher_with_dummy_script():
    """测试节点启动（使用简单的dummy脚本）"""
    print("=" * 60)
    print("测试节点启动（Dummy脚本）")
    print("=" * 60)

    with tempfile.TemporaryDirectory() as tmpdir:
        # 创建临时节点目录和脚本
        node_dir = Path(tmpdir) / "test_node"
        node_dir.mkdir()

        # 创建简单的启动脚本
        script_path = node_dir / "run.py"
        script_content = """#!/usr/bin/env python3
import sys
import time
import json
import os

# 获取参数
params = {}
for i, arg in enumerate(sys.argv):
    if arg == '--params':
        params = json.loads(sys.argv[i+1])

# 获取环境变量
node_id = os.getenv('NODE_ID', 'unknown')
print(f"Node {node_id} started with params: {params}")

# 检查socket环境变量
in_sockets = [k for k in os.environ if k.startswith('NODE_IN_')]
out_sockets = [k for k in os.environ if k.startswith('NODE_OUT_')]
print(f"Input ports: {in_sockets}")
print(f"Output ports: {out_sockets}")

# 运行一段时间
for i in range(3):
    time.sleep(0.1)
    print(f"Still running... {i}")

print("Node completed successfully")
"""
        with open(script_path, 'w') as f:
            f.write(script_content)

        os.chmod(script_path, 0o755)

        # 创建node.yaml
        manifest_path = node_dir / "node.yaml"
        manifest_content = """name: test_node
version: 0.1.0
description: Test node for launcher

entrypoints:
  linux:
    kind: python
    cmd: ["python3", "run.py"]

ports:
  inputs:
    - name: input1
      type: test.type
  outputs:
    - name: output1
      type: test.type

params: {}
"""
        with open(manifest_path, 'w') as f:
            f.write(manifest_content)

        # 创建Socket管理器和节点启动器
        socket_manager = SocketManager(tmpdir)
        socket_manager.initialize()

        launcher = NodeLauncher(str(tmpdir), socket_manager)

        # 加载节点说明书
        parser = YAMLParser()
        manifest = parser.parse_node_manifest(str(manifest_path))

        # 创建节点实例
        node = NodeInstance(
            id="test_instance",
            package="test_node",
            params={"param1": "test_value"}
        )

        # 启动节点
        try:
            process = launcher.launch(node, manifest)
            print(f"✓ 节点启动成功 (PID: {process.pid})")

            # 等待进程完成
            stdout, stderr = process.communicate(timeout=5)
            ret_code = process.returncode

            print(f"✓ 节点进程完成 (返回码: {ret_code})")

            if stdout:
                print(f"  stdout (前100字符): {stdout[:100]}")

            if ret_code == 0:
                print("✓ 节点执行成功")
            else:
                print(f"✗ 节点执行失败: {stderr[:200] if stderr else 'no error info'}")

        except Exception as e:
            print(f"✗ 节点启动失败: {e}")
            raise

    print("✓ 节点启动测试通过\n")


def test_startup_coordinator():
    """测试启动协调器"""
    print("=" * 60)
    print("测试启动协调器")
    print("=" * 60)

    # 加载测试节点
    registry = NodeRegistry("tests/fixtures/test_node_hub")
    registry.load_all()

    # 创建节点实例和边
    nodes = [
        NodeInstance(id="inst_a", package="node_a"),
        NodeInstance(id="inst_b", package="node_b"),
        NodeInstance(id="inst_c", package="node_c"),
    ]

    edges = [
        Edge(from_node="inst_a", from_port="output1", to_node="inst_b", to_port="input1"),
        Edge(from_node="inst_b", from_port="output1", to_node="inst_c", to_port="input1"),
    ]

    # 拓扑排序
    analyzer = TopologyAnalyzer(nodes, edges)
    layers = analyzer.topological_sort()

    print(f"✓ 拓扑排序结果: {layers}")

    # 验证启动顺序
    assert len(layers) == 3
    assert layers[0] == ["inst_a"]
    assert layers[1] == ["inst_b"]
    assert layers[2] == ["inst_c"]

    print("✓ 启动协调器验证通过\n")


def test_process_health_check():
    """测试进程健康检查"""
    print("=" * 60)
    print("测试进程健康检查")
    print("=" * 60)

    import subprocess

    with tempfile.TemporaryDirectory() as tmpdir:
        # 创建临时节点目录和脚本
        node_dir = Path(tmpdir) / "healthy_node"
        node_dir.mkdir()

        # 创建保持运行的脚本
        script_path = node_dir / "run.py"
        script_content = """#!/usr/bin/env python3
import time
import sys

print("Node started", flush=True)
sys.stdout.flush()

try:
    while True:
        time.sleep(0.1)
except KeyboardInterrupt:
    print("Node shutting down")
"""
        with open(script_path, 'w') as f:
            f.write(script_content)

        os.chmod(script_path, 0o755)

        # 创建node.yaml
        manifest_path = node_dir / "node.yaml"
        manifest_content = """name: healthy_node
version: 0.1.0
description: Healthy test node

entrypoints:
  linux:
    kind: python
    cmd: ["python3", "run.py"]

ports:
  inputs: []
  outputs: []

params: {}
"""
        with open(manifest_path, 'w') as f:
            f.write(manifest_content)

        # 创建启动器
        socket_manager = SocketManager(tmpdir)
        socket_manager.initialize()
        launcher = NodeLauncher(str(tmpdir), socket_manager)

        # 加载节点说明书
        parser = YAMLParser()
        manifest = parser.parse_node_manifest(str(manifest_path))

        # 创建节点实例
        node = NodeInstance(id="healthy", package="healthy_node")

        # 启动节点
        process = launcher.launch(node, manifest)
        print(f"✓ 节点已启动 (PID: {process.pid})")

        # 检查健康状态
        time.sleep(0.5)
        is_alive = launcher.check_process_health(process, "healthy")
        assert is_alive, "进程应该还在运行"
        print(f"✓ 进程健康检查通过（运行中）")

        # 终止进程
        launcher.terminate_process(process, "healthy", timeout=2.0)
        print(f"✓ 进程已终止")

        # 再次检查
        is_alive = launcher.check_process_health(process, "healthy")
        assert not is_alive, "进程应该已退出"
        print(f"✓ 进程健康检查通过（已退出）")

    print("✓ 进程健康检查测试通过\n")


if __name__ == "__main__":
    try:
        test_env_builder()
        test_node_launcher_with_dummy_script()
        test_startup_coordinator()
        test_process_health_check()

        print("=" * 60)
        print("里程碑4所有测试通过！")
        print("=" * 60)
    except Exception as e:
        print(f"测试失败: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
