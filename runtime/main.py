#!/usr/bin/env python3
"""
NodeFlow Runtime主入口
机器人节点化框架的启动程序
"""

import sys
import argparse
import signal
import time
from pathlib import Path

from runtime.config.yaml_parser import YAMLParser
from runtime.config.validator import ConfigValidator
from runtime.node_hub.node_registry import NodeRegistry
from runtime.graph.topology import TopologyAnalyzer
from runtime.graph.validator import GraphValidator
from runtime.ipc.socket_manager import SocketManager
from runtime.orchestrator.node_launcher import NodeLauncher
from runtime.orchestrator.startup_coordinator import StartupCoordinator
from runtime.monitoring.node_monitor import NodeMonitor
from runtime.utils.logger import setup_logger
from runtime.utils.errors import *

logger = setup_logger("nodeflow")


class NodeFlowRuntime:
    """NodeFlow运行时主类"""

    def __init__(self, config_path: str, log_level: str = "INFO"):
        """
        初始化运行时

        参数：
        - config_path: 运行配置文件路径
        - log_level: 日志级别
        """
        self.config_path = config_path
        self.log_level = log_level

        # 组件
        self.config = None
        self.registry = None
        self.socket_manager = None
        self.launcher = None
        self.coordinator = None
        self.monitor = None

        # 进程字典
        self.processes = {}

        # 运行标志
        self.running = False

        # 设置信号处理
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)

    def _signal_handler(self, signum, frame):
        """信号处理函数"""
        logger.info(f"Received signal {signum}, shutting down...")
        self.running = False

    def run(self):
        """运行框架"""
        try:
            # 1. 解析配置
            logger.info("=" * 60)
            logger.info("NodeFlow Runtime Starting")
            logger.info("=" * 60)

            logger.info(f"Loading configuration from: {self.config_path}")
            parser = YAMLParser()
            self.config = parser.parse_runtime_config(self.config_path)

            logger.info(f"Graph ID: {self.config.graph_id}")
            logger.info(f"Graph Version: {self.config.graph_version}")
            logger.info(f"Node Hub Path: {self.config.node_hub_path}")

            # 2. 验证配置
            logger.info("Validating runtime configuration...")
            validator = ConfigValidator()
            result = validator.validate_runtime_config(self.config)

            if not result.is_valid:
                logger.error("Configuration validation failed:")
                for error in result.errors:
                    logger.error(f"  - {error}")
                return 1

            logger.info("Configuration validation passed")

            # 3. 加载节点库
            logger.info(f"Loading node hub from {self.config.node_hub_path}...")
            self.registry = NodeRegistry(self.config.node_hub_path)
            self.registry.load_all()

            logger.info(f"Loaded {len(self.registry.get_all_packages())} node packages:")
            for pkg in self.registry.get_all_packages():
                logger.info(f"  - {pkg}")

            # 4. 验证图
            logger.info("Validating graph...")
            graph_validator = GraphValidator()
            graph_result = graph_validator.validate(
                self.config.nodes, self.config.edges, self.registry
            )

            if not graph_result.is_valid:
                logger.error("Graph validation failed:")
                for error in graph_result.errors:
                    logger.error(f"  - {error}")
                return 1

            if graph_result.warnings:
                logger.warning("Graph validation warnings:")
                for warning in graph_result.warnings:
                    logger.warning(f"  - {warning}")

            logger.info("Graph validation passed")

            # 5. 拓扑排序
            logger.info("Analyzing topology...")
            topology = TopologyAnalyzer(self.config.nodes, self.config.edges)
            layers = topology.topological_sort()

            logger.info(f"Topology analysis complete: {len(layers)} layers")
            for i, layer in enumerate(layers):
                logger.info(f"  Layer {i}: {layer}")

            # 6. 初始化Socket管理器
            logger.info("Initializing socket manager...")
            self.socket_manager = SocketManager()
            self.socket_manager.initialize()

            # 7. 启动节点
            logger.info("=" * 60)
            logger.info("Starting Nodes")
            logger.info("=" * 60)

            self.launcher = NodeLauncher(
                self.config.node_hub_path,
                self.socket_manager,
                self.config.edges
            )

            self.coordinator = StartupCoordinator(self.launcher, self.registry)

            nodes_dict = {n.id: n for n in self.config.nodes}
            self.processes = self.coordinator.startup_nodes(layers, nodes_dict)

            logger.info("=" * 60)
            logger.info(f"All {len(self.processes)} nodes started successfully")
            logger.info("=" * 60)

            # 8. 启动监控
            logger.info("Starting node monitor...")

            # 定义重启回调
            def restart_node(node_id):
                """重启单个节点"""
                try:
                    node = nodes_dict[node_id]
                    manifest = self.registry.get_manifest(node.package)

                    if not manifest:
                        logger.error(f"Cannot restart '{node_id}': package not found")
                        return None

                    process = self.launcher.launch(node, manifest)
                    return process

                except Exception as e:
                    logger.error(f"Error restarting node '{node_id}': {e}")
                    return None

            self.monitor = NodeMonitor(self.config.restart_policy)
            self.monitor.start_monitoring(self.processes, restart_node)

            # 9. 主循环
            logger.info("=" * 60)
            logger.info("Runtime is RUNNING")
            logger.info("Press Ctrl+C to stop")
            logger.info("=" * 60)

            self.running = True

            try:
                while self.running:
                    time.sleep(1)

            except KeyboardInterrupt:
                logger.info("Received keyboard interrupt")

            # 10. 清理资源
            return self._shutdown()

        except Exception as e:
            logger.error(f"Fatal error: {e}", exc_info=True)
            return 1

    def _shutdown(self):
        """清理资源"""
        logger.info("=" * 60)
        logger.info("Shutting Down")
        logger.info("=" * 60)

        # 停止监控
        if self.monitor:
            logger.info("Stopping node monitor...")
            self.monitor.stop()

        # 关闭所有节点
        if self.coordinator and self.processes:
            logger.info("Shutting down nodes...")
            self.coordinator.shutdown_nodes(self.processes)

        # 清理Socket
        if self.socket_manager:
            logger.info("Cleaning up sockets...")
            self.socket_manager.cleanup()

        logger.info("=" * 60)
        logger.info("NodeFlow Runtime Stopped")
        logger.info("=" * 60)

        return 0


def main():
    """主函数"""
    parser = argparse.ArgumentParser(
        description="NodeFlow Runtime - 机器人节点化框架"
    )
    parser.add_argument(
        'config',
        help='运行配置文件路径（runtime.yaml）'
    )
    parser.add_argument(
        '--log-level',
        default='INFO',
        choices=['DEBUG', 'INFO', 'WARNING', 'ERROR'],
        help='日志级别（默认：INFO）'
    )

    args = parser.parse_args()

    # 创建并运行
    runtime = NodeFlowRuntime(args.config, args.log_level)
    return runtime.run()


if __name__ == '__main__':
    sys.exit(main())
