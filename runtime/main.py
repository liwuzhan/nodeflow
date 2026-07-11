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
import copy
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
    """NodeFlow运行时主类，支持多轮启动-停止循环"""

    def __init__(self, config_path: str, log_level: str = "INFO", duration: int = None, clean_buffers: bool = True):
        """
        初始化运行时

        参数：
        - config_path: 运行配置文件路径
        - log_level: 日志级别
        - duration: 可选，运行时长（秒），到期后自动关机（仅在run()模式下）
        - clean_buffers: 是否清理旧缓冲区（默认True）
        """
        self.config_path = config_path
        self.log_level = log_level
        self.duration = duration
        self.clean_buffers = clean_buffers
        self.start_time = None

        # 框架组件（一次性初始化）
        self.config = None
        self.registry = None
        self.topology_layers = None
        self.nodes_dict = None
        self._base_node_params = {}

        # 数据流组件（可重复初始化）
        self.socket_manager = None
        self.launcher = None
        self.coordinator = None
        self.monitor = None

        # 进程字典
        self.processes = {}

        # 运行标志
        self.running = False  # 框架级别
        self.dataflow_running = False  # 数据流级别

        # 防止双重清理
        self.shutdown_complete = False

        # 框架是否已初始化
        self._framework_initialized = False

        # 设置信号处理（只设置一次）
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)
        signal.signal(signal.SIGHUP, self._signal_handler)
        signal.signal(signal.SIGQUIT, self._signal_handler)

        # 注册紧急清理处理器（只注册一次）
        atexit.register(self._emergency_cleanup)

    def _signal_handler(self, signum, frame):
        """
        信号处理器，支持优雅关闭

        处理的信号: SIGINT (Ctrl+C), SIGTERM, SIGHUP, SIGQUIT
        支持两个级别：数据流级别（关闭数据流）和框架级别（关闭框架）
        """
        signal_names = {
            signal.SIGINT: "SIGINT",
            signal.SIGTERM: "SIGTERM",
            signal.SIGHUP: "SIGHUP",
            signal.SIGQUIT: "SIGQUIT",
        }
        signal_name = signal_names.get(signum, f"signal {signum}")

        if self.running or self.dataflow_running:
            logger.info(f"Received {signal_name}, shutting down framework...")
            self.running = False
            # stop_dataflow() must still run after the loop exits; do not clear
            # dataflow_running here or child processes will be orphaned.
        else:
            logger.debug(f"Received {signal_name} but nothing is running")

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

            # 终止所有子进程（包括其整个进程组/子进程树）
            for node_id, process in list(self.processes.items()):
                try:
                    if process.poll() is None:  # 仍在运行
                        logger.warning(f"Emergency terminating node '{node_id}' (PID {process.pid})")

                        # 先尝试杀死整个进程组（包含所有子进程）
                        try:
                            if sys.platform != "win32":
                                # Unix/macOS: 杀死整个进程组
                                # 当使用 start_new_session=True 时，process.pid 就是进程组 ID
                                os.killpg(os.getpgid(process.pid), signal.SIGKILL)
                            else:
                                # Windows: 无法杀死进程组，只能杀死主进程
                                process.kill()
                        except (OSError, ProcessLookupError):
                            # 如果进程组杀死失败，尝试杀死单个进程
                            try:
                                process.kill()
                            except ProcessLookupError:
                                pass  # 进程已退出

                        # 短暂等待进程确实退出
                        try:
                            process.wait(timeout=1.0)
                        except subprocess.TimeoutExpired:
                            logger.error(f"Node '{node_id}' did not respond to SIGKILL in emergency cleanup")

                except (ProcessLookupError, OSError):
                    # 进程已退出或进程组已不存在，没问题
                    pass
                except Exception as e:
                    # 记录日志但不抛出异常 - atexit 处理器必须静默
                    try:
                        logger.error(f"Error in emergency cleanup for '{node_id}': {e}")
                    except:
                        pass  # 日志记录失败，忽略

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

    def _initialize_framework(self):
        """
        初始化框架（一次性）

        包括：配置加载、验证、节点库扫描、图验证、拓扑分析
        返回：0成功，1失败
        """
        if self._framework_initialized:
            logger.debug("Framework already initialized, skipping...")
            return 0

        try:
            logger.info("=" * 60)
            logger.info("Initializing NodeFlow Framework")
            logger.info("=" * 60)

            # 1. 解析配置
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
            self.topology_layers = topology.topological_sort()

            logger.info(f"Topology analysis complete: {len(self.topology_layers)} layers")
            for i, layer in enumerate(self.topology_layers):
                logger.info(f"  Layer {i}: {layer}")

            # 6. 构建节点字典（用于重启回调）
            self.nodes_dict = {n.id: n for n in self.config.nodes}
            self._base_node_params = {
                node_id: copy.deepcopy(node.params)
                for node_id, node in self.nodes_dict.items()
            }

            logger.info("Framework initialization complete")
            self._framework_initialized = True
            return 0

        except Exception as e:
            logger.error(f"Framework initialization failed: {e}", exc_info=True)
            return 1

    def _apply_node_params(self, node_params: dict):
        """
        将任务参数覆盖到节点实例配置上

        node_params 格式: { "node_id": { "param_key": "value", ... } }
        参数会被合并到 NodeInstance.params，后续 _build_command 自动序列化
        """
        for node_id, params in node_params.items():
            if node_id in self.nodes_dict:
                self.nodes_dict[node_id].params.update(params)
                logger.info(f"Task params injected into node '{node_id}': {params}")
            else:
                logger.warning(f"Task params target unknown node '{node_id}', skipped")

    def _reset_node_params(self):
        for node_id, node in self.nodes_dict.items():
            node.params = copy.deepcopy(self._base_node_params.get(node_id, {}))

    def _switch_task_preset(self, preset_yaml: str) -> bool:
        if not preset_yaml:
            return True
        if Path(preset_yaml).name != preset_yaml or preset_yaml in (".", ".."):
            raise ValueError("preset_yaml must be an allowlisted example name")
        filename = preset_yaml if preset_yaml.endswith(".yaml") else f"{preset_yaml}.yaml"
        root = Path(os.getenv("NODEFLOW_ROOT", Path.cwd())).resolve()
        candidate = (root / "examples" / filename).resolve()
        examples_root = (root / "examples").resolve()
        if candidate.parent != examples_root or not candidate.is_file():
            raise ValueError(f"Unknown task preset: {preset_yaml}")
        current = Path(self.config_path).resolve()
        if current == candidate:
            return True
        if self.dataflow_running:
            raise RuntimeError("Cannot switch task preset while dataflow is running")

        logger.info("Switching task preset: %s -> %s", current.name, candidate.name)
        self.config_path = str(candidate)
        self.config = None
        self.registry = None
        self.topology_layers = None
        self.nodes_dict = None
        self._base_node_params = {}
        self._framework_initialized = False
        return self._initialize_framework() == 0

    def start_dataflow(self):
        """
        启动数据流周期

        启动所有配置的节点，开始数据流交互
        抛出：RuntimeError如果数据流已在运行或框架未初始化
        """
        if not self._framework_initialized:
            raise RuntimeError("Framework not initialized. Call _initialize_framework() first.")

        if self.dataflow_running:
            raise RuntimeError("Dataflow already running. Call stop_dataflow() first.")

        try:
            logger.info("=" * 60)
            logger.info("Starting Dataflow")
            logger.info("=" * 60)

            # 清理buffer（如果需要）
            if self.clean_buffers:
                self._clean_buffers()

            # 初始化launcher和coordinator
            self.launcher = NodeLauncher(
                self.config.node_hub_path,
                self.config.edges
            )
            self.coordinator = StartupCoordinator(self.launcher, self.registry)

            # 启动所有节点
            self.processes = self.coordinator.startup_nodes(
                self.topology_layers,
                self.nodes_dict,
                startup_timeout=2.0,  # 减少等待时间，仅用于检测启动初期崩溃
                startup_delay=1.0,
                should_cancel=lambda: not self.running,
            )

            if not self.running:
                logger.info("Dataflow startup cancelled, shutting down started nodes...")
                if self.processes:
                    self.coordinator.shutdown_nodes(self.processes)
                    self.processes = {}
                return False

            logger.info(f"All {len(self.processes)} nodes started successfully")

            # 启动监控
            logger.info("Starting node monitor...")

            def restart_node(node_id):
                """重启单个节点的回调"""
                try:
                    node = self.nodes_dict[node_id]
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

            # 写入PID文件
            self.start_time = time.time()
            self._write_pid_file()

            self.dataflow_running = True
            logger.info("Dataflow started successfully")
            logger.info("=" * 60)
            return True

        except Exception as e:
            logger.error(f"Failed to start dataflow: {e}", exc_info=True)
            # 清理部分启动的进程
            if self.processes:
                logger.info("Cleaning up partially started processes...")
                self.coordinator.shutdown_nodes(self.processes)
                self.processes = {}
            raise

    def stop_dataflow(self):
        """
        停止数据流周期

        停止所有节点，清理资源
        抛出：RuntimeError如果数据流未运行
        """
        if not self.dataflow_running:
            raise RuntimeError("Dataflow not running. Nothing to stop.")

        try:
            logger.info("=" * 60)
            logger.info("Stopping Dataflow")
            logger.info("=" * 60)

            # 停止监控
            if self.monitor:
                logger.info("Stopping node monitor...")
                self.monitor.stop()
                self.monitor = None

            # 关闭所有节点
            if self.coordinator and self.processes:
                logger.info("Shutting down nodes...")
                self.coordinator.shutdown_nodes(self.processes)
                self.processes = {}

            # 注意：不删除 PID 文件，因为在守护进程模式下 Runtime 还在运行
            # PID 文件只在 Runtime 完全退出时才删除

            self.dataflow_running = False
            logger.info("Dataflow stopped successfully")
            logger.info("=" * 60)

        except Exception as e:
            logger.error(f"Error stopping dataflow: {e}", exc_info=True)
            raise

    def run(self):
        """
        运行框架（传统模式）

        一次性启动框架、启动数据流、等待、关闭数据流、退出
        保持向后兼容性
        """
        try:
            # 初始化框架（一次性）
            result = self._initialize_framework()
            if result != 0:
                return result

            # 启动数据流。start_dataflow() 会用 self.running 判断启动是否
            # 被取消，因此传统 run() 模式必须先进入 running 状态。
            self.running = True
            started = self.start_dataflow()
            if not started:
                self.shutdown_complete = True
                return 0

            # 主循环
            logger.info("=" * 60)
            logger.info("Runtime is RUNNING")
            if self.duration:
                logger.info(f"Auto-shutdown in {self.duration}s")
            logger.info("Press Ctrl+C to stop")
            logger.info("=" * 60)

            shutdown_buf = None
            try:
                from sdk.shared_buffer_lite import SharedBufferLite
                shutdown_buf = SharedBufferLite("control.shutdown_request", create=False)
                logger.info("Runtime listening on control.shutdown_request buffer")
            except Exception:
                shutdown_buf = None

            try:
                while self.running and self.dataflow_running:
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
                                self.running = False
                                break
                        except Exception:
                            pass

            except KeyboardInterrupt:
                logger.info("Received keyboard interrupt")

            # 停止数据流
            if self.dataflow_running:
                self.stop_dataflow()

            # 标记关闭完成
            self.shutdown_complete = True
            return 0

        except Exception as e:
            logger.error(f"Fatal error: {e}", exc_info=True)
            return 1

    def run_with_loop(self, num_loops: int = None, loop_interval: int = 5):
        """
        运行框架（多轮循环模式）

        支持多轮启动-停止循环，允许在框架持续运行的情况下多次启动和停止数据流

        参数：
        - num_loops: 循环次数，None表示无限循环（直到收到关闭信号）
        - loop_interval: 两个循环之间的等待时间（秒）

        示例：
            runtime = NodeFlowRuntime('config.yaml')
            runtime.run_with_loop(num_loops=3)  # 运行3轮
        """
        try:
            # 初始化框架（一次性）
            result = self._initialize_framework()
            if result != 0:
                return result

            logger.info("=" * 60)
            logger.info("Runtime is RUNNING (Multi-loop mode)")
            logger.info(f"Number of loops: {num_loops if num_loops else 'unlimited'}")
            logger.info("Press Ctrl+C to stop")
            logger.info("=" * 60)

            self.running = True
            loop_count = 0

            try:
                while self.running:
                    loop_count += 1
                    if num_loops and loop_count > num_loops:
                        logger.info(f"Completed {num_loops} loops, shutting down...")
                        break

                    logger.info(f"\n{'='*60}")
                    logger.info(f"Loop {loop_count}/{num_loops if num_loops else '∞'}")
                    logger.info(f"{'='*60}")

                    # 启动数据流
                    try:
                        self.start_dataflow()
                    except Exception as e:
                        logger.error(f"Failed to start dataflow in loop {loop_count}: {e}")
                        if num_loops:
                            continue  # 继续下一个循环
                        else:
                            break  # 无限循环模式下出错则退出

                    # 监听控制信号（在数据流运行时）
                    try:
                        while self.running and self.dataflow_running:
                            time.sleep(1)
                            # 检查是否收到停止数据流的信号
                            # 在这里可以添加额外的控制逻辑
                    except KeyboardInterrupt:
                        logger.info("Received interrupt signal")
                        break

                    # 停止数据流
                    try:
                        self.stop_dataflow()
                    except Exception as e:
                        logger.error(f"Error stopping dataflow in loop {loop_count}: {e}")

                    # 等待下一个循环
                    if self.running and (not num_loops or loop_count < num_loops):
                        logger.info(f"Waiting {loop_interval}s before next loop...")
                        for i in range(loop_interval):
                            if not self.running:
                                break
                            time.sleep(1)

            except KeyboardInterrupt:
                logger.info("Received keyboard interrupt, shutting down...")

            # 确保数据流已停止
            if self.dataflow_running:
                try:
                    self.stop_dataflow()
                except Exception:
                    pass

            logger.info("=" * 60)
            logger.info(f"Completed {loop_count} loops")
            logger.info("=" * 60)

            # 标记关闭完成
            self.shutdown_complete = True
            return 0

        except Exception as e:
            logger.error(f"Fatal error in loop mode: {e}", exc_info=True)
            return 1

    def run_as_daemon(self):
        """
        运行框架（守护进程模式）

        初始化框架，但不自动启动数据流。
        监听控制缓冲区，等待来自 CLI 的命令。

        支持的命令：
        - start_dataflow: 启动数据流
        - stop_dataflow: 停止数据流
        - shutdown: 关闭框架
        """
        try:
            # 初始化框架（一次性）
            result = self._initialize_framework()
            if result != 0:
                return result

            logger.info("=" * 60)
            logger.info("Runtime is RUNNING (Daemon mode)")
            logger.info("Waiting for control commands from CLI")
            logger.info("=" * 60)

            self.running = True
            self.start_time = time.time()
            self._write_pid_file()

            # 创建或打开控制缓冲区
            control_buf = None
            status_buf = None
            try:
                from sdk.shared_buffer_lite import SharedBufferLite
                control_buf = SharedBufferLite("runtime.control", create=True, size=1024)
                status_buf = SharedBufferLite("runtime.status", create=True, size=4096)
                logger.info("Control buffer ready: runtime.control")
            except Exception as e:
                logger.error(f"Failed to create control buffer: {e}")
                return 1

            last_command_timestamp = 0
            active_task_id = ""

            def publish_status(command_status="idle", error=""):
                status_buf.write({
                    "runtime_running": self.running,
                    "dataflow_running": self.dataflow_running,
                    "active_task_id": active_task_id,
                    "graph_id": self.config.graph_id if self.config else "",
                    "config_path": self.config_path,
                    "command_status": command_status,
                    "error": error,
                    "timestamp": time.time(),
                })

            publish_status()

            try:
                while self.running:
                    time.sleep(0.5)

                    # 读取控制命令
                    try:
                        cmd_pkt = control_buf.read()
                        if not cmd_pkt:
                            continue

                        # 检查是否是新命令（避免重复执行）
                        timestamp = cmd_pkt.get("timestamp", 0)
                        if timestamp <= last_command_timestamp:
                            continue

                        last_command_timestamp = timestamp
                        command = cmd_pkt.get("command")

                        logger.info(f"Received command: {command}")

                        if command == "start_dataflow":
                            node_params = cmd_pkt.get("node_params", {})
                            task_id = cmd_pkt.get("task_id", "")
                            preset_yaml = cmd_pkt.get("preset_yaml", "")
                            if preset_yaml and not self._switch_task_preset(preset_yaml):
                                logger.error(f"Task {task_id} preset initialization failed")
                                publish_status("failed", "preset initialization failed")
                                continue
                            self._reset_node_params()
                            if node_params:
                                self._apply_node_params(node_params)
                            if task_id:
                                logger.info(f"Task {task_id} params applied")
                            if not self.dataflow_running:
                                try:
                                    started = self.start_dataflow()
                                    if started:
                                        active_task_id = task_id
                                        publish_status("started")
                                        logger.info("✓ Dataflow started by CLI command")
                                    else:
                                        publish_status("failed", "dataflow startup cancelled")
                                        logger.info("Dataflow startup cancelled")
                                except Exception as e:
                                    publish_status("failed", str(e))
                                    logger.error(f"Failed to start dataflow: {e}")
                            else:
                                publish_status("rejected", "dataflow already running")
                                logger.warning("Dataflow already running, ignoring start command")

                        elif command == "stop_dataflow":
                            if self.dataflow_running:
                                try:
                                    self.stop_dataflow()
                                    active_task_id = ""
                                    publish_status("stopped")
                                    logger.info("✓ Dataflow stopped by CLI command")
                                except Exception as e:
                                    publish_status("failed", str(e))
                                    logger.error(f"Failed to stop dataflow: {e}")
                            else:
                                active_task_id = ""
                                publish_status("stopped")
                                logger.warning("Dataflow not running, ignoring stop command")

                        elif command == "shutdown":
                            logger.info("Shutdown command received, exiting...")
                            self.running = False
                            break

                        else:
                            logger.warning(f"Unknown command: {command}")

                    except Exception as e:
                        publish_status("failed", str(e))
                        logger.error(f"Error processing control command: {e}")

            except KeyboardInterrupt:
                logger.info("Received keyboard interrupt, shutting down...")

            # 停止数据流（如果在运行）
            if self.dataflow_running:
                try:
                    self.stop_dataflow()
                except Exception:
                    pass

            # 清理 PID 文件
            self._cleanup_pid_file()
            if status_buf:
                publish_status("shutdown")
                status_buf.close()
            if control_buf:
                control_buf.close()

            logger.info("=" * 60)
            logger.info("Daemon mode stopped")
            logger.info("=" * 60)

            # 标记关闭完成
            self.shutdown_complete = True
            return 0

        except Exception as e:
            logger.error(f"Fatal error in daemon mode: {e}", exc_info=True)
            return 1

    def _write_pid_file(self):
        """写入 PID 文件"""
        try:
            pid_file = Path("/tmp/nodeflow_runtime.pid")
            with open(pid_file, 'w') as f:
                f.write(f"{os.getpid()}\n{self.start_time if self.start_time else time.time()}")
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
        description="NodeFlow Runtime - 机器人节点化框架，支持多轮启动-停止循环"
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
        help='自动关机时间（秒），到期后自动关机（仅在单次运行模式下）'
    )
    parser.add_argument(
        '--no-clean-buffers',
        action='store_true',
        help='禁用启动前清理共享缓冲区（默认会清理）'
    )
    parser.add_argument(
        '--loop',
        type=int,
        metavar='N',
        help='多轮循环模式：运行N轮启动-停止循环（0表示无限循环）'
    )
    parser.add_argument(
        '--loop-interval',
        type=int,
        default=5,
        help='循环间隔时间（秒），默认5秒'
    )
    parser.add_argument(
        '--daemon',
        action='store_true',
        help='守护进程模式：启动框架但不启动数据流，通过 CLI 命令控制'
    )

    args = parser.parse_args()

    # 创建并运行（默认清理缓冲区，除非指定 --no-clean-buffers）
    clean_buffers = not args.no_clean_buffers
    runtime = NodeFlowRuntime(args.config, args.log_level, args.duration, clean_buffers)

    # 守护进程模式
    if args.daemon:
        return runtime.run_as_daemon()
    # 如果指定了--loop参数，使用多轮循环模式
    elif args.loop is not None:
        num_loops = None if args.loop == 0 else args.loop
        return runtime.run_with_loop(num_loops=num_loops, loop_interval=args.loop_interval)
    else:
        # 传统单次运行模式
        return runtime.run()


if __name__ == '__main__':
    sys.exit(main())
