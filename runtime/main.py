#!/usr/bin/env python3.12
"""
NodeFlow Runtime主入口
机器人节点化框架的启动程序
"""

import sys
import argparse
import signal
import time
import os
import atexit
import subprocess
from pathlib import Path

from runtime.config.yaml_parser import YAMLParser
from runtime.config.validator import ConfigValidator
from runtime.node_hub.node_registry import NodeRegistry
from runtime.graph.topology import TopologyAnalyzer
from runtime.graph.validator import GraphValidator
from runtime.orchestrator.node_launcher import NodeLauncher
from runtime.orchestrator.startup_coordinator import StartupCoordinator
from runtime.monitoring.node_monitor import NodeMonitor
from runtime.utils.logger import setup_logger
from runtime.utils.errors import *
from runtime.utils.constants import BUFFERS_DIR

logger = setup_logger("nodeflow")


class NodeFlowRuntime:
    """NodeFlow运行时主类"""

    def __init__(self, config_path: str, log_level: str = "INFO", duration: int = None, clean_buffers: bool = True):
        """
        初始化运行时

        参数：
        - config_path: 运行配置文件路径
        - log_level: 日志级别
        - duration: 可选，运行时长（秒），到期后自动关机
        - clean_buffers: 是否清理旧缓冲区（默认True）
        """
        self.config_path = config_path
        self.log_level = log_level
        self.duration = duration
        self.clean_buffers = clean_buffers
        self.start_time = None

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

        # 防止双重清理
        self.shutdown_complete = False

        # 设置信号处理
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)
        signal.signal(signal.SIGHUP, self._signal_handler)
        signal.signal(signal.SIGQUIT, self._signal_handler)

        # 注册紧急清理处理器
        atexit.register(self._emergency_cleanup)

    def _signal_handler(self, signum, frame):
        """
        信号处理器，支持优雅关闭

        处理的信号: SIGINT (Ctrl+C), SIGTERM, SIGHUP, SIGQUIT
        """
        signal_names = {
            signal.SIGINT: "SIGINT",
            signal.SIGTERM: "SIGTERM",
            signal.SIGHUP: "SIGHUP",
            signal.SIGQUIT: "SIGQUIT",
        }
        signal_name = signal_names.get(signum, f"signal {signum}")

        # 避免重复处理
        if not self.running:
            logger.debug(f"Received {signal_name} but already shutting down")
            return

        logger.info(f"Received {signal_name}, initiating graceful shutdown...")
        self.running = False

    def _emergency_cleanup(self):
        """
        紧急清理处理器，用于异常退出场景

        由 atexit 在 Python 退出时调用（包括未捕获异常）。
        这是一个失败保护机制，确保即使正常关闭路径未执行，
        子进程也能被终止。

        注意: 此处理器应保持静默（不抛出异常）且快速。
        """
        # 如果已完成正常关闭，跳过
        if self.shutdown_complete:
            return

        # 如果没有启动任何进程，跳过
        if not self.processes:
            return

        try:
            logger.warning("Emergency cleanup triggered - terminating child processes")

            # 终止所有子进程
            for node_id, process in list(self.processes.items()):
                try:
                    if process.poll() is None:  # 仍在运行
                        logger.warning(f"Emergency terminating node '{node_id}' (PID {process.pid})")
                        process.terminate()
                        try:
                            process.wait(timeout=2.0)  # 紧急情况下使用较短超时
                        except subprocess.TimeoutExpired:
                            process.kill()
                            process.wait(timeout=1.0)
                except (ProcessLookupError, OSError):
                    # 进程已退出，没问题
                    pass
                except Exception as e:
                    # 记录日志但不抛出异常 - atexit 处理器必须静默
                    logger.error(f"Error in emergency cleanup for '{node_id}': {e}")

            # 清理 PID 文件
            self._cleanup_pid_file()

            # 清理共享缓冲区（尽力而为）
            try:
                from shutil import rmtree
                buf_dir = Path(BUFFERS_DIR)
                if buf_dir.exists():
                    rmtree(buf_dir)
                    logger.info(f"Emergency cleanup: removed buffer directory {buf_dir}")
            except Exception as e:
                logger.warning(f"Emergency cleanup: failed to remove buffers: {e}")

            logger.info("Emergency cleanup completed")

        except Exception as e:
            # 在 atexit 处理器中永远不要抛出异常
            try:
                logger.error(f"Emergency cleanup failed: {e}")
            except:
                pass  # 此时甚至日志记录也可能失败

    def _clean_buffers(self):
        """清理共享缓冲区（写满0以重置序列号和数据）"""
        buf_dir = Path(BUFFERS_DIR)
        if not buf_dir.exists():
            logger.info("Buffer directory does not exist, skip cleaning")
            return

        buf_files = list(buf_dir.glob("*.buf"))
        if not buf_files:
            logger.info("No buffer files to clean")
            return

        cleaned_count = 0
        for buf_file in buf_files:
            try:
                # 获取文件大小
                file_size = buf_file.stat().st_size
                # 写满0
                with open(buf_file, 'wb') as f:
                    f.write(b'\x00' * file_size)
                cleaned_count += 1
            except Exception as e:
                logger.warning(f"Failed to clean buffer {buf_file.name}: {e}")

        logger.info(f"Cleaned {cleaned_count} buffer files (reset to zeros)")

    def run(self):
        """运行框架"""
        try:
            # 1. 解析配置
            logger.info("=" * 60)
            logger.info("NodeFlow Runtime Starting")
            logger.info("=" * 60)

            if self.clean_buffers:
                self._clean_buffers()

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

            # 6. 初始化通信环境（ZeroMQ/SharedBufferLite，无需SocketManager）

            # 7. 启动节点
            logger.info("=" * 60)
            logger.info("Starting Nodes")
            logger.info("=" * 60)

            self.launcher = NodeLauncher(
                self.config.node_hub_path,
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

            # 写入 PID 文件
            self.start_time = time.time()
            self._write_pid_file()

            # 9. 主循环
            logger.info("=" * 60)
            logger.info("Runtime is RUNNING")
            if self.duration:
                logger.info(f"Auto-shutdown in {self.duration}s")
            logger.info("Press Ctrl+C to stop")
            logger.info("=" * 60)

            self.running = True
            shutdown_buf = None
            try:
                from sdk.shared_buffer_lite import SharedBufferLite
                shutdown_buf = SharedBufferLite("control.shutdown_request", create=False)
                logger.info("Runtime listening on control.shutdown_request buffer")
            except Exception:
                shutdown_buf = None

            try:
                while self.running:
                    time.sleep(1)

                    # 检查定时关机
                    if self.duration and (time.time() - self.start_time) >= self.duration:
                        logger.info(f"Duration {self.duration}s reached, shutting down...")
                        self.running = False
                        break

                    if shutdown_buf is not None:
                        try:
                            data = shutdown_buf.read()
                            if data and data.get("shutdown"):
                                logger.info("External shutdown request received, initiating graceful shutdown...")
                                try:
                                    from shutil import rmtree
                                    from pathlib import Path
                                    buf_dir = Path(BUFFERS_DIR)
                                    if buf_dir.exists():
                                        rmtree(buf_dir)
                                        logger.info(f"Cleaned shared buffers at {buf_dir}")
                                except Exception as e:
                                    logger.warning(f"Failed to clean buffers: {e}")
                                self.running = False
                                break
                        except Exception:
                            pass

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

        # 通信栈不需要额外清理（ZeroMQ/SharedBufferLite）

        # 清理 PID 文件
        self._cleanup_pid_file()

        logger.info("=" * 60)
        logger.info("NodeFlow Runtime Stopped")
        logger.info("=" * 60)

        # 标记关闭完成，防止 atexit 双重清理
        self.shutdown_complete = True

        return 0

    def _write_pid_file(self):
        """写入 PID 文件"""
        try:
            pid_file = Path("/tmp/nodeflow_runtime.pid")
            with open(pid_file, 'w') as f:
                f.write(f"{os.getpid()}\n{self.start_time}")
            logger.debug(f"PID file written: {os.getpid()}")
        except Exception as e:
            logger.error(f"Failed to write PID file: {e}")

    def _cleanup_pid_file(self):
        """清理 PID 文件"""
        try:
            pid_file = Path("/tmp/nodeflow_runtime.pid")
            if pid_file.exists():
                pid_file.unlink()
                logger.debug("PID file cleaned up")
        except Exception as e:
            logger.error(f"Failed to cleanup PID file: {e}")


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
    parser.add_argument(
        '--duration',
        type=int,
        help='自动关机时间（秒），到期后自动关机'
    )
    parser.add_argument(
        '--no-clean-buffers',
        action='store_true',
        help='禁用启动前清理共享缓冲区（默认会清理）'
    )

    args = parser.parse_args()

    # 创建并运行（默认清理缓冲区，除非指定 --no-clean-buffers）
    clean_buffers = not args.no_clean_buffers
    runtime = NodeFlowRuntime(args.config, args.log_level, args.duration, clean_buffers)
    return runtime.run()


if __name__ == '__main__':
    sys.exit(main())
