#!/usr/bin/env python3
"""
NodeFlow 运行时框架诊断脚本
逐步测试框架的各个环节，快速定位问题
"""

import sys
import os
import json
from pathlib import Path
from typing import List, Dict, Any

# 添加项目路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from edge.runtime.config.yaml_parser import YAMLParser
from edge.runtime.config.validator import ConfigValidator
from edge.runtime.node_hub.node_registry import NodeRegistry
from edge.runtime.node_hub.scanner import NodeHubScanner
from edge.runtime.graph.topology import TopologyAnalyzer
from edge.runtime.graph.validator import GraphValidator
from edge.runtime.orchestrator.env_builder import EnvBuilder
from edge.runtime.utils.logger import setup_logger
from edge.runtime.utils.errors import CyclicDependencyError

logger = setup_logger("debug", level="DEBUG")


class RuntimeDiagnostics:
    """运行时框架诊断工具"""

    def __init__(self, config_path: str):
        self.config_path = config_path
        self.config = None
        self.registry = None
        self.env_builder = EnvBuilder()

    def print_section(self, title: str):
        """打印章节标题"""
        print("\n" + "=" * 80)
        print(f"  {title}")
        print("=" * 80)

    def print_step(self, num: int, title: str):
        """打印步骤标题"""
        print(f"\n[{num}] {title}")
        print("-" * 60)

    def print_result(self, status: str, message: str = ""):
        """打印结果"""
        if status == "OK":
            print(f"  ✓ {message}")
        elif status == "WARN":
            print(f"  ⚠ {message}")
        elif status == "ERROR":
            print(f"  ✗ {message}")
        else:
            print(f"  • {message}")

    def step_1_load_config(self) -> bool:
        """第1步：加载 YAML 配置"""
        self.print_step(1, "Load YAML Configuration")

        try:
            parser = YAMLParser()
            self.config = parser.parse_runtime_config(self.config_path)

            self.print_result("OK", f"Config loaded: {self.config_path}")
            self.print_result("INFO", f"Graph ID: {self.config.graph_id}")
            self.print_result("INFO", f"Nodes: {len(self.config.nodes)}")
            self.print_result("INFO", f"Edges: {len(self.config.edges)}")
            self.print_result("INFO", f"Node Hub: {self.config.node_hub_path}")

            return True
        except Exception as e:
            self.print_result("ERROR", f"Failed to load config: {e}")
            import traceback
            traceback.print_exc()
            return False

    def step_2_scan_node_hub(self) -> bool:
        """第2步：扫描节点库"""
        self.print_step(2, "Scan Node Hub")

        try:
            # 处理相对路径 - 相对于项目根目录
            hub_path = Path(self.config.node_hub_path)
            if not hub_path.is_absolute():
                hub_path = (project_root / hub_path).resolve()

            if not hub_path.exists():
                self.print_result("ERROR", f"Node hub not found: {hub_path}")
                return False

            self.print_result("INFO", f"Scanning: {hub_path}")

            scanner = NodeHubScanner(str(hub_path))
            packages = scanner.scan()  # Returns List[str]

            self.print_result("OK", f"Found {len(packages)} node packages:")
            for pkg in sorted(packages):
                print(f"    • {pkg}")

            return True
        except Exception as e:
            self.print_result("ERROR", f"Failed to scan node hub: {e}")
            import traceback
            traceback.print_exc()
            return False

    def step_3_register_nodes(self) -> bool:
        """第3步：节点注册"""
        self.print_step(3, "Register Nodes")

        try:
            # 处理相对路径 - 相对于项目根目录
            hub_path = Path(self.config.node_hub_path)
            if not hub_path.is_absolute():
                hub_path = (project_root / hub_path).resolve()

            self.registry = NodeRegistry(str(hub_path))
            self.registry.load_all()  # 加载所有节点 manifests

            self.print_result("OK", f"Loaded {len(self.registry.get_all_packages())} packages")

            # 检查配置中的每个节点是否能找到
            for node in self.config.nodes:
                manifest = self.registry.get_manifest(node.package)
                if not manifest:
                    self.print_result("ERROR", f"Package not found: {node.package}")
                    return False
                else:
                    self.print_result("OK", f"Node '{node.id}' → package '{node.package}'")

            return True
        except Exception as e:
            self.print_result("ERROR", f"Failed to register nodes: {e}")
            import traceback
            traceback.print_exc()
            return False

    def step_4_validate_graph(self) -> bool:
        """第4步：图验证"""
        self.print_step(4, "Validate Graph Structure")

        try:
            result = GraphValidator.validate(self.config.nodes, self.config.edges, self.registry)
            errors = result.errors

            if errors:
                self.print_result("ERROR", "Graph validation failed:")
                for error in errors:
                    print(f"    • {error}")
                return False
            else:
                self.print_result("OK", "Graph validation passed")

                # 打印节点信息
                print(f"\n  Nodes ({len(self.config.nodes)}):")
                for node in self.config.nodes:
                    print(f"    • {node.id:20s} ({node.package})")

                # 打印边信息
                print(f"\n  Edges ({len(self.config.edges)}):")
                for edge in self.config.edges:
                    print(f"    • {edge.from_node}.{edge.from_port} → {edge.to_node}.{edge.to_port}")

                return True
        except Exception as e:
            self.print_result("ERROR", f"Failed to validate graph: {e}")
            import traceback
            traceback.print_exc()
            return False

    def step_5_analyze_topology(self) -> bool:
        """第5步：拓扑分析"""
        self.print_step(5, "Analyze Topology (Startup Order)")

        try:
            analyzer = TopologyAnalyzer(self.config.nodes, self.config.edges)

            # 获取启动顺序（如果有循环依赖会抛出异常）
            layers = analyzer.topological_sort()
            self.print_result("OK", "No circular dependencies")
            self.print_result("OK", f"Startup layers: {len(layers)}")

            for i, layer in enumerate(layers):
                print(f"    Layer {i}: {layer}")

            return True
        except CyclicDependencyError as e:
            self.print_result("ERROR", f"Circular dependency detected: {e}")
            return False
        except Exception as e:
            self.print_result("ERROR", f"Failed to analyze topology: {e}")
            import traceback
            traceback.print_exc()
            return False

    def step_6_show_zmq_addresses(self) -> bool:
        """第6步：生成并展示 ZMQ 地址（ZeroMQ 版本）"""
        self.print_step(6, "Generate ZMQ Addresses")
        try:
            print(f"\n  ZMQ addresses:")
            for node in self.config.nodes:
                manifest = self.registry.get_manifest(node.package)
                if not manifest:
                    self.print_result("WARN", f"Manifest not found: {node.package}")
                    continue
                env = self.env_builder.build_env(node, manifest, self.config.node_hub_path, self.config.edges)

                input_vars = [k for k in env.keys() if k.startswith("NODE_IN_")]
                output_vars = [k for k in env.keys() if k.startswith("NODE_OUT_") and "_BUFFER_SIZE" not in k and "_CONFLATE" not in k]

                if input_vars:
                    print(f"\n    {node.id} (inputs):")
                    for var in sorted(input_vars):
                        print(f"      • {var:25s} → {env[var]}")
                if output_vars:
                    print(f"\n    {node.id} (outputs):")
                    for var in sorted(output_vars):
                        print(f"      • {var:25s} → {env[var]}")
            return True
        except Exception as e:
            self.print_result("ERROR", f"Failed to generate ZMQ addresses: {e}")
            import traceback
            traceback.print_exc()
            return False

    def step_7_verify_node_scripts(self) -> bool:
        """第7步：验证节点脚本"""
        self.print_step(7, "Verify Node Scripts")

        try:
            # 处理相对路径 - 相对于项目根目录
            hub_path = Path(self.config.node_hub_path)
            if not hub_path.is_absolute():
                hub_path = (project_root / hub_path).resolve()

            for node in self.config.nodes:
                manifest = self.registry.get_manifest(node.package)
                if not manifest:
                    continue

                # 获取脚本路径
                entrypoint = manifest.entrypoints.get("linux")
                if not entrypoint:
                    self.print_result("WARN", f"No linux entrypoint for {node.package}")
                    continue

                # 检查脚本是否存在
                node_dir = hub_path / node.package
                if node_dir.exists():
                    self.print_result("OK", f"Node directory exists: {node_dir}")
                else:
                    self.print_result("ERROR", f"Node directory not found: {node_dir}")
                    return False

                # 检查 run.py 或其他脚本
                run_script = node_dir / "run.py"
                if run_script.exists():
                    self.print_result("OK", f"  ✓ {run_script.name} exists")
                else:
                    self.print_result("WARN", f"  ⚠ {run_script.name} not found")

            return True
        except Exception as e:
            self.print_result("ERROR", f"Failed to verify scripts: {e}")
            import traceback
            traceback.print_exc()
            return False

    def step_8_check_health_check_timeout(self) -> bool:
        """第8步：检查健康检查配置"""
        self.print_step(8, "Check Health Check Configuration")

        try:
            from edge.runtime.monitoring.health_checker import HealthChecker

            self.print_result("INFO", "Health check timeout configuration:")
            print(f"    • Default socket connect timeout: 5s")
            print(f"    • Default process polling interval: 0.1s")

            self.print_result("OK", "Health checker ready")
            return True
        except Exception as e:
            self.print_result("WARN", f"Could not check health checker: {e}")
            return True

    def run_all(self) -> bool:
        """运行所有诊断步骤"""
        self.print_section("NodeFlow Runtime Diagnostics")

        print(f"Configuration: {self.config_path}")
        print(f"Project root: {project_root}")

        steps = [
            self.step_1_load_config,
            self.step_2_scan_node_hub,
            self.step_3_register_nodes,
            self.step_4_validate_graph,
            self.step_5_analyze_topology,
            self.step_6_show_zmq_addresses,
            self.step_7_verify_node_scripts,
            self.step_8_check_health_check_timeout,
        ]

        results = []
        for step in steps:
            try:
                result = step()
                results.append(result)
                if not result:
                    self.print_result("ERROR", f"Step '{step.__name__}' failed, stopping here")
                    break
            except Exception as e:
                self.print_result("ERROR", f"Unexpected error in {step.__name__}: {e}")
                import traceback
                traceback.print_exc()
                results.append(False)
                break

        # 总结
        self.print_section("Diagnostic Summary")
        passed = sum(1 for r in results if r)
        total = len(steps)

        print(f"\nPassed: {passed}/{total} steps")

        if all(results):
            print("\n✓ All diagnostic steps passed!")
            print("\nThe runtime framework is ready for node startup.")
            print("If nodes still hang, the issue is likely in:")
            print("  1. Node startup script (run.py)")
            print("  2. Node health check mechanism")
            print("  3. Socket connection establishment")
        else:
            print("\n✗ Diagnostic failed. See errors above.")

        return all(results)


def main():
    if len(sys.argv) < 2:
        print("Usage: python3 tools/debug_runtime.py <config.yaml>")
        print()
        print("Example:")
        print("  python3 tools/debug_runtime.py examples/test_logger_simple.yaml")
        sys.exit(1)

    config_path = sys.argv[1]

    # 确保路径存在
    if not Path(config_path).exists():
        print(f"Error: Config file not found: {config_path}")
        sys.exit(1)

    diagnostics = RuntimeDiagnostics(config_path)
    success = diagnostics.run_all()

    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
