"""
NodeFlow SDK主入口
为节点开发者提供便捷的API
"""

import os
import sys
import time
import threading
from typing import Dict, Any, Optional, Type, TYPE_CHECKING

if TYPE_CHECKING:
    try:
        from pydantic import BaseModel
    except ImportError:
        pass

from sdk.param_parser import ParamParser
from sdk.port import InputPort, OutputPort
from sdk.shared_buffer_lite import SharedBufferLite
from sdk.structured_logger import StructuredLogger

logger = None  # 框架日志（进程级）


class ParentProcessWatchdog:
    """
    父进程监控守护线程

    用于检测父进程（运行时框架）是否存活。
    当父进程被强制杀死时，节点进程会自动退出，避免孤儿进程。

    工作原理：
    - Unix/macOS: 当父进程死亡时，子进程的ppid变为1（init/launchd）
    - 定期检查ppid，如果变为1，说明父进程已死亡
    """

    def __init__(self, node_id: str, logger_instance, check_interval: float = 1.0):
        """
        初始化父进程监控

        参数：
        - node_id: 节点ID（用于日志）
        - logger_instance: 日志器实例
        - check_interval: 检查间隔（秒），默认1秒
        """
        self.node_id = node_id
        self.logger = logger_instance
        self.check_interval = check_interval
        self.running = False
        self.thread: Optional[threading.Thread] = None

        # 记录初始的父进程ID
        self.initial_ppid = os.getppid()

        self.logger.debug(
            f"ParentProcessWatchdog initialized for '{node_id}'",
            initial_ppid=self.initial_ppid,
            check_interval=check_interval
        )

    def start(self):
        """启动监控线程"""
        if self.running:
            self.logger.warning(f"ParentProcessWatchdog for '{self.node_id}' already running")
            return

        self.running = True
        self.thread = threading.Thread(
            target=self._monitor_loop,
            name=f"ParentWatchdog-{self.node_id}",
            daemon=True
        )
        self.thread.start()
        self.logger.info(f"ParentProcessWatchdog started for '{self.node_id}'")

    def stop(self):
        """停止监控线程"""
        self.running = False
        if self.thread:
            self.thread.join(timeout=2.0)
        self.logger.debug(f"ParentProcessWatchdog stopped for '{self.node_id}'")

    def _monitor_loop(self):
        """监控循环（在守护线程中运行）"""
        try:
            while self.running:
                time.sleep(self.check_interval)

                if not self.running:
                    break

                current_ppid = os.getppid()

                # 检查父进程是否死亡
                # 在Unix/macOS上，当父进程死亡时，ppid变为1（init/launchd）
                if current_ppid == 1:
                    self.logger.warning(
                        f"Node '{self.node_id}' detected parent process death",
                        old_ppid=self.initial_ppid,
                        new_ppid=current_ppid
                    )

                    # 父进程已死，节点应该退出
                    # 先触发 atexit 清理回调（包括 SDK 的 __exit__ 和资源释放）
                    # 再用 os._exit() 终止进程
                    import atexit
                    atexit._run_exitfuncs()
                    os._exit(1)

                # 如果ppid发生变化但不是1，记录警告
                elif current_ppid != self.initial_ppid:
                    self.logger.warning(
                        f"Node '{self.node_id}' ppid changed",
                        old_ppid=self.initial_ppid,
                        new_ppid=current_ppid
                    )
                    self.initial_ppid = current_ppid

        except Exception as e:
            self.logger.error(f"ParentProcessWatchdog error for '{self.node_id}'", exc_info=True)


class NodeFlowSDK:
    """
    NodeFlow SDK主类

    提供节点开发的核心API：
    - 参数解析
    - 端口创建
    - 数据收发
    """

    def __init__(self, log_level: str = "INFO", enable_parent_watchdog: bool = True):
        """
        初始化SDK

        自动从环境变量读取：
        - NODE_ID: 节点实例ID
        - NODE_HUB_PATH: 节点库根目录
        - NODE_SOCKET_DIR: Socket临时目录
        - NODE_IN_<PORT>: 输入端口socket路径
        - NODE_OUT_<PORT>: 输出端口socket路径
        - NODE_PARENT_WATCHDOG: 是否启用父进程监控（可选，默认true）
        - NODE_WATCHDOG_INTERVAL: 监控检查间隔（可选，默认1.0秒）
        - NODEFLOW_LOG_DIR: 日志目录（可选，默认 /tmp/nodeflow_logs）

        参数：
        - log_level: 日志级别
        - enable_parent_watchdog: 是否启用父进程监控（默认True）
        """
        # 从环境变量读取基本信息
        self.node_id = os.getenv('NODE_ID')
        self.node_hub_path = os.getenv('NODE_HUB_PATH')
        self.socket_dir = os.getenv('NODE_SOCKET_DIR')

        if not self.node_id:
            raise ValueError("NODE_ID environment variable not set")

        # 设置结构化日志（包括JSON文件 + 控制台输出）
        from runtime.utils.constants import LOGS_DIR
        log_dir = os.getenv('NODEFLOW_LOG_DIR', LOGS_DIR)
        self.logger = StructuredLogger(
            node_id=self.node_id,
            log_level=log_level,
            log_dir=log_dir,
            enable_json=True,
            enable_console=True
        )

        self.logger.info(f"NodeFlow SDK initialized for node '{self.node_id}'", log_dir=log_dir)

        # 解析命令行参数
        self.params = ParamParser.parse()
        self.logger.debug(f"Parsed parameters: {len(self.params)} params")

        # 端口字典
        self.inputs: Dict[str, InputPort] = {}
        self.outputs: Dict[str, OutputPort] = {}

        # 健康心跳 buffer（延迟创建，避免启动时无端口就写）
        self._health_buffer: Optional[SharedBufferLite] = None

        # 父进程监控（解决孤儿进程问题）
        self._parent_watchdog: Optional[ParentProcessWatchdog] = None

        # 从环境变量检查是否禁用父进程监控
        env_watchdog = os.getenv('NODE_PARENT_WATCHDOG', 'true').lower()
        watchdog_enabled = enable_parent_watchdog and env_watchdog not in ('false', '0', 'no', 'off')

        if watchdog_enabled:
            # 从环境变量读取检查间隔
            interval_str = os.getenv('NODE_WATCHDOG_INTERVAL', '1.0')
            try:
                watchdog_interval = float(interval_str)
            except ValueError:
                watchdog_interval = 1.0

            self._parent_watchdog = ParentProcessWatchdog(
                self.node_id,
                self.logger,
                check_interval=watchdog_interval
            )
            self._parent_watchdog.start()
            self.logger.info(
                f"Parent process watchdog enabled",
                interval=watchdog_interval
            )
        else:
            self.logger.info("Parent process watchdog disabled")

        # 健康心跳线程
        self._health_running = True
        self._health_thread: Optional[threading.Thread] = None
        health_interval = float(os.getenv('NODE_HEALTH_INTERVAL', '2.0'))
        self._health_interval = max(0.5, health_interval)
        self._start_health_heartbeat()

    def get_param(self, key: str, default: Any = None) -> Any:
        """
        获取参数值

        参数：
        - key: 参数名
        - default: 默认值

        返回：
        - 参数值
        """
        return self.params.get(key, default)

    def require_param(self, key: str) -> Any:
        """
        获取必填参数

        参数：
        - key: 参数名

        返回：
        - 参数值

        异常：
        - ValueError: 参数不存在
        """
        if key not in self.params:
            raise ValueError(f"Required parameter '{key}' not found")
        return self.params[key]

    def create_input_port(self, port_name: str) -> InputPort:
        """
        创建输入端口

        参数：
        - port_name: 端口名（必须与node.yaml中定义的一致）

        返回：
        - InputPort对象

        异常：
        - ValueError: 端口未配置
        """
        env_var_name = f'NODE_IN_{port_name}'
        buffer_name = os.getenv(env_var_name)

        if not buffer_name:
            raise ValueError(
                f"Input port '{port_name}' not configured. "
                f"Environment variable '{env_var_name}' not found."
            )

        port = InputPort(port_name, buffer_name)
        self.inputs[port_name] = port

        self.logger.info(f"Created input port: {port_name} (buffer={buffer_name})")
        return port

    def _publish_metadata(self):
        """
        发布节点元数据（包括Schema定义）到Shared Buffer
        """
        try:
            metadata = {
                "node_id": self.node_id,
                "ports": {}
            }

            for name, port in self.outputs.items():
                schema_json = port.get_schema_json()
                port_meta = {
                    "type": "output",
                    "schema": schema_json
                }
                metadata["ports"][name] = port_meta

            # 创建 metadata buffer
            # 命名规则: {node_id}.metadata
            buffer_name = f"{self.node_id}.metadata"
            
            # 使用较小的buffer size，元数据不会太大
            meta_buffer = SharedBufferLite(buffer_name, size=64*1024, create=True)
            meta_buffer.write(metadata)
            
            # 不需要保持buffer对象，写入后关闭即可（数据保留在共享内存文件）
            meta_buffer.close()
            
            self.logger.info(f"Published node metadata to {buffer_name}")
            
        except Exception as e:
            self.logger.warning(f"Failed to publish node metadata: {e}")

    def report_health(self):
        """
        报告节点健康状态到共享缓冲区

        创建/写入 {node_id}.health 缓冲区，包含状态、时间戳、端口连接状态
        """
        try:
            buffer_name = f"{self.node_id}.health"

            health_data = {
                "status": "ok",
                "node_id": self.node_id,
                "timestamp": time.time(),
                "heartbeat_interval": self._health_interval,
                "inputs": {
                    port_name: port.is_connected()
                    for port_name, port in self.inputs.items()
                },
                "outputs": {
                    port_name: True
                    for port_name in self.outputs
                },
            }

            # 复用以避免每 2 秒截断重建文件
            if self._health_buffer is None:
                self._health_buffer = SharedBufferLite(buffer_name, size=64*1024, create=True)
            self._health_buffer.write(health_data)

            self.logger.debug(f"Reported health to {buffer_name}")
        except Exception as e:
            self.logger.warning(f"Failed to report health: {e}")

    def create_output_port(self, port_name: str, schema: Optional[Type['BaseModel']] = None) -> OutputPort:
        """
        创建输出端口

        每次创建 OutputPort 后自动发布 metadata，保证 schema 信息尽早可用。
        """
        env_var_name = f'NODE_OUT_{port_name}'
        buffer_name = os.getenv(env_var_name)

        if not buffer_name:
            raise ValueError(
                f"Output port '{port_name}' not configured. "
                f"Environment variable '{env_var_name}' not found."
            )

        port = OutputPort(port_name, buffer_name, schema=schema)
        self.outputs[port_name] = port

        self.logger.info(f"Created output port: {port_name} (buffer={buffer_name}, schema={schema.__name__ if schema else 'None'})")
        
        self._publish_metadata()
        return port

    def get_input_port(self, port_name: str) -> Optional[InputPort]:
        """
        获取已创建的输入端口

        参数：
        - port_name: 端口名

        返回：
        - InputPort对象，如果不存在返回None
        """
        return self.inputs.get(port_name)

    def get_output_port(self, port_name: str) -> Optional[OutputPort]:
        """
        获取已创建的输出端口

        参数：
        - port_name: 端口名

        返回：
        - OutputPort对象，如果不存在返回None
        """
        return self.outputs.get(port_name)

    def is_input_port_connected(self, port_name: str) -> bool:
        """
        检查输入端口是否已连接

        参数：
        - port_name: 端口名

        返回：
        - True表示已连接，False表示未连接或端口不存在
        """
        port = self.inputs.get(port_name)
        if port is None:
            return False
        return port.is_connected()

    def get_input_port_status(self, port_name: str) -> Optional[str]:
        """
        获取输入端口的连接状态

        参数：
        - port_name: 端口名

        返回：
        - "connecting": 初始化中
        - "connected": 已连接
        - "disconnected": 已断开
        - None: 端口不存在
        """
        port = self.inputs.get(port_name)
        if port is None:
            return None
        return port.get_connection_state()

    def _start_health_heartbeat(self):
        self._health_thread = threading.Thread(
            target=self._health_loop,
            name=f"health-{self.node_id}",
            daemon=True,
        )
        self._health_thread.start()
        self.logger.debug(f"Health heartbeat started (interval={self._health_interval}s)")

    def _stop_health_heartbeat(self):
        self._health_running = False
        if self._health_thread:
            self._health_thread.join(timeout=2.0)

    def _health_loop(self):
        while self._health_running:
            self.report_health()
            time.sleep(self._health_interval)

    def shutdown(self):
        """
        清理资源

        关闭所有端口和监控线程
        """
        self.logger.info("Shutting down NodeFlow SDK")

        # 停止健康心跳
        self._stop_health_heartbeat()

        # 停止父进程监控
        if self._parent_watchdog:
            self._parent_watchdog.stop()

        for port in self.inputs.values():
            port.close()

        for port in self.outputs.values():
            port.close()

        if self._health_buffer:
            try:
                self._health_buffer.close()
            except Exception:
                pass

        self.logger.info("NodeFlow SDK shutdown complete")

    def __enter__(self):
        """上下文管理器入口"""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """上下文管理器退出"""
        self.shutdown()
        return False
