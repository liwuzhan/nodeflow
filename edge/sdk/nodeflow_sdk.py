"""
NodeFlow SDK主入口
为节点开发者提供便捷的API
"""

import os
import sys
import json
import time
import signal
import traceback
import threading
from typing import Dict, Any, Optional, Type, Callable, TYPE_CHECKING

if TYPE_CHECKING:
    try:
        from pydantic import BaseModel
    except ImportError:
        pass

from edge.sdk.param_parser import ParamParser
from edge.sdk.port import InputPort, OutputPort
from edge.sdk.shared_buffer_lite import SharedBufferLite, IPC_VERSION
from edge.sdk.structured_logger import StructuredLogger

logger = None  # 框架日志（进程级）

# 模块级活动 SDK 引用（die() 无 sdk 实例时用于补充端口观测）
_ACTIVE_SDK: Optional["NodeFlowSDK"] = None


def die(reason: str, code: int = 1) -> None:
    """统一"大声死"（W3-5）：结构化 stderr 遗言 → flush → 硬退出。

    - 任意线程可调用：os._exit 直接终止进程（sys.exit 在非主线程仅终止
      线程、心跳线程假存活的坑由此杜绝）
    - 遗言包含 node_id、原因、当前异常栈、关键端口观测（若 SDK 可用）
    - 退出前尽力运行已注册的 atexit 清理（端口关闭、日志落盘）
    """
    payload = {
        "event": "node_die",
        "node_id": (_ACTIVE_SDK.node_id if _ACTIVE_SDK else os.getenv("NODE_ID")),
        "reason": str(reason),
        "ts": time.time(),
    }
    if sys.exc_info()[0] is not None:
        payload["traceback"] = traceback.format_exc()
    if _ACTIVE_SDK is not None:
        payload["ports"] = {
            direction: {
                name: port.get_stats() if isinstance(port, InputPort) else {"buffer": port.buffer_name}
                for name, port in ports.items()
            }
            for direction, ports in (("inputs", _ACTIVE_SDK.inputs), ("outputs", _ACTIVE_SDK.outputs))
            if ports
        }
        payload["incarnation"] = _ACTIVE_SDK.incarnation
    try:
        sys.stderr.write(json.dumps(payload, ensure_ascii=False) + "\n")
        sys.stderr.flush()
    except Exception:
        pass
    try:
        import atexit
        atexit._run_exitfuncs()
    except Exception:
        pass
    os._exit(code)


# SIGTERM 优雅退出：Python 默认对 SIGTERM 直接终止进程，节点的 finally /
# 上下文退出都不会执行——执行器节点（如 pwm_driver）因此无法回中位，sysfs PWM
# 保持最后一个脉宽。SDK 在主线程把 SIGTERM 转为 SystemExit(143)，走正常的
# finally → __exit__ 路径；143 = 128 + SIGTERM，incident_store 仍能识别信号来源。
#
# 信号可能恰好在析构函数（如 SharedBufferLite.__del__）或弱引用回调中被处理，
# 这类上下文抛出的异常会被解释器吞掉（"Exception ignored ..."），主循环照常运行、
# 直到 5 秒后被 SIGKILL——等于回到原问题。unraisablehook 识别被吞的退出并重新投递。
SIGTERM_EXIT_CODE = 128 + signal.SIGTERM
_SIGTERM_HANDLER_INSTALLED = False
_SIGTERM_EXITING = False
_PREV_UNRAISABLE_HOOK = None


class _SigtermExit(SystemExit):
    """SIGTERM 转换出的退出；独立类型便于在 unraisablehook 中识别。"""


def _sigterm_to_system_exit(signum, frame):
    global _SIGTERM_EXITING
    if _SIGTERM_EXITING:
        # 退出已在传播：重复的 SIGTERM 不得打断 finally（例如回中位写入）。
        # 清理卡住时由 runtime 的 SIGKILL 兜底。
        return
    _SIGTERM_EXITING = True
    raise _SigtermExit(SIGTERM_EXIT_CODE)


def _sigterm_unraisable_hook(unraisable):
    global _SIGTERM_EXITING
    if isinstance(getattr(unraisable, "exc_value", None), _SigtermExit):
        # 退出被析构函数吞掉：复位并重新投递。不能在本钩子内直接 os.kill——
        # 发给自身的信号会立刻在钩子里被处理、再次被吞。改由辅助线程稍后发送，
        # 主线程在下一个字节码边界（已离开析构上下文）处理并抛出。
        _SIGTERM_EXITING = False

        def _redeliver():
            time.sleep(0.01)
            try:
                os.kill(os.getpid(), signal.SIGTERM)
            except OSError:
                pass

        threading.Thread(target=_redeliver, name="sigterm-redeliver", daemon=True).start()
        return
    (_PREV_UNRAISABLE_HOOK or sys.__unraisablehook__)(unraisable)


def install_sigterm_handler() -> bool:
    """在主线程安装 SIGTERM → SystemExit 转换；节点已自带处理器时不覆盖。"""
    global _SIGTERM_HANDLER_INSTALLED, _PREV_UNRAISABLE_HOOK
    if _SIGTERM_HANDLER_INSTALLED:
        return True
    if threading.current_thread() is not threading.main_thread():
        return False
    try:
        if signal.getsignal(signal.SIGTERM) not in (signal.SIG_DFL, None):
            return False
        signal.signal(signal.SIGTERM, _sigterm_to_system_exit)
    except (ValueError, OSError):
        return False
    _PREV_UNRAISABLE_HOOK = sys.unraisablehook
    sys.unraisablehook = _sigterm_unraisable_hook
    _SIGTERM_HANDLER_INSTALLED = True
    return True


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
        self.graceful_exit_timeout = 3.0
        self.running = False
        # 可中断的等待：stop() 立即唤醒，SDK shutdown 不必等满一个检查周期
        self._stop_event = threading.Event()
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
        self._stop_event.clear()
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
        self._stop_event.set()
        if self.thread:
            self.thread.join(timeout=2.0)
        self.logger.debug(f"ParentProcessWatchdog stopped for '{self.node_id}'")

    def _monitor_loop(self):
        """监控循环（在守护线程中运行）"""
        try:
            while self.running:
                self._stop_event.wait(self.check_interval)

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

                    # 父进程已死，节点应该退出。
                    # 优先让主线程走 SIGTERM 优雅路径（节点 finally 得以执行，
                    # 执行器回安全值）；主线程在宽限期内未退出才硬退出。
                    if _SIGTERM_HANDLER_INSTALLED:
                        try:
                            os.kill(os.getpid(), signal.SIGTERM)
                        except OSError:
                            pass
                        deadline = time.monotonic() + self.graceful_exit_timeout
                        while self.running and time.monotonic() < deadline:
                            time.sleep(0.05)
                        if not self.running:
                            return  # 主线程已进入 SDK shutdown，正常退出中
                        self.logger.warning(
                            f"Node '{self.node_id}' did not exit gracefully in "
                            f"{self.graceful_exit_timeout}s after parent death, forcing exit"
                        )

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

        # SIGTERM → SystemExit：runtime 停节点时节点 finally/清理得以执行
        install_sigterm_handler()

        # IPC 版本握手（W2-1）：launcher 注入 NODEFLOW_IPC_VERSION，
        # 不符则大声退出——杜绝旧读者把 ts 字节当 payload 的静默混读窗口。
        # env 缺失（手动启动/单测）视为兼容。
        env_ver = os.getenv('NODEFLOW_IPC_VERSION')
        if env_ver is not None:
            try:
                declared = int(env_ver)
            except ValueError:
                declared = -1
            if declared != IPC_VERSION:
                die(f"ipc_version_mismatch: declared={env_ver}, sdk={IPC_VERSION}", code=86)

        # run / 世代身份（W2-2；env 缺失时为默认值，兼容手动启动）
        self.run_id = os.getenv('NODEFLOW_RUN_ID') or ""
        try:
            self.incarnation = int(os.getenv('NODEFLOW_INCARNATION', '1'))
        except ValueError:
            self.incarnation = 1

        # 设置结构化日志（包括JSON文件 + 控制台输出）
        from edge.runtime.utils.constants import LOGS_DIR
        log_dir = os.getenv('NODEFLOW_LOG_DIR', LOGS_DIR)
        self.logger = StructuredLogger(
            node_id=self.node_id,
            log_level=log_level,
            log_dir=log_dir,
            enable_json=True,
            enable_console=True,
            run_id=self.run_id or None,
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
        self._health_stop_event = threading.Event()
        self._health_thread: Optional[threading.Thread] = None
        health_interval = float(os.getenv('NODE_HEALTH_INTERVAL', '2.0'))
        self._health_interval = max(0.5, health_interval)
        self._start_health_heartbeat()

        # 输入看门狗（W3-3，opt-in）：manifest 声明 input_watchdog 的端口
        # 断流超时 → 节点自定义回调，未注册则默认 sdk.die（P2：病了就大声死）
        self._input_watchdog_cfg: Dict[str, float] = {}
        self._on_input_lost: Dict[str, Callable] = {}
        self._input_watchdog_thread: Optional[threading.Thread] = None
        watchdog_env = os.getenv('NODEFLOW_INPUT_WATCHDOG')
        if watchdog_env:
            try:
                raw_cfg = json.loads(watchdog_env)
                self._input_watchdog_cfg = {
                    str(k): float(v) for k, v in raw_cfg.items() if v is not None
                }
            except (ValueError, TypeError):
                self.logger.warning("Invalid NODEFLOW_INPUT_WATCHDOG, ignored", value=watchdog_env)
        if self._input_watchdog_cfg:
            self._input_watchdog_thread = threading.Thread(
                target=self._input_watchdog_loop,
                name=f"input-watchdog-{self.node_id}",
                daemon=True,
            )
            self._input_watchdog_thread.start()
            self.logger.info("Input watchdog enabled", ports=self._input_watchdog_cfg)

        # 输入 anti-replay（2026-09-01 草案）：声明端口重启后不消费启动前历史命令
        self._input_anti_replay: Dict[str, str] = {}
        anti_replay_env = os.getenv('NODEFLOW_INPUT_ANTI_REPLAY')
        if anti_replay_env:
            try:
                self._input_anti_replay = {
                    str(k): str(v) for k, v in json.loads(anti_replay_env).items()
                }
            except (ValueError, TypeError):
                self.logger.warning("Invalid NODEFLOW_INPUT_ANTI_REPLAY, ignored")

        # 登记为活动 SDK（模块级 die() 由此补充端口观测）
        global _ACTIVE_SDK
        _ACTIVE_SDK = self

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

        port = InputPort(
            port_name, buffer_name,
            require_new_commit=(self._input_anti_replay.get(port_name) == "require_new_commit"),
        )
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
        报告节点健康状态到共享缓冲区（health payload v2）

        创建/写入 {node_id}.health 缓冲区，包含状态、时间戳、incarnation、
        端口连接状态与观测年龄（inputs v2: connected/last_seq_seen/source_write_age_ms）
        """
        try:
            buffer_name = f"{self.node_id}.health"

            health_data = {
                "status": "ok",
                "node_id": self.node_id,
                "timestamp": time.time(),
                "heartbeat_interval": self._health_interval,
                "incarnation": self.incarnation,
                "run_id": self.run_id,
                "inputs": {
                    port_name: {
                        "connected": port.is_connected(),
                        "last_seq_seen": port.last_sequence,
                        "source_write_age_ms": port.last_write_age_ms(),
                    }
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

    def _input_watchdog_loop(self):
        """输入看门狗（W3-3）：断言"声明了看门狗的端口上游会持续写入"。

        判定条件：端口已连接且上游写过至少一次（age 非 None），
        且写入年龄超过声明超时。只应声明在持续输出的端口上——
        静态输出端口（如任务配置下发）不适用此机制。
        """
        check_interval = min(0.05, min(self._input_watchdog_cfg.values()) / 2)
        while self._health_running:
            for port_name, timeout_s in self._input_watchdog_cfg.items():
                port = self.inputs.get(port_name)
                if port is None or not port.is_connected():
                    continue  # 未创建/未连接由重连机制负责
                age_ms = port.last_write_age_ms()
                if age_ms is None:
                    continue  # 上游从未写入（启动排序窗口），不判定
                if age_ms > timeout_s * 1000:
                    handler = self._on_input_lost.get(port_name)
                    if handler is not None:
                        try:
                            handler(port_name)
                        except Exception as e:
                            self.logger.error(
                                f"on_input_lost handler for '{port_name}' failed: {e}",
                                exc_info=True,
                            )
                            self.die(f"on_input_lost handler failed for input '{port_name}': {e}")
                            return
                    else:
                        self.die(
                            f"input '{port_name}' stale for {age_ms:.0f}ms "
                            f"(timeout {timeout_s}s, source {port.source_node}.{port.source_port})"
                        )
                        return
            time.sleep(check_interval)

    def set_on_input_lost(self, port_name: str, handler: Callable[[str], None]):
        """注册输入断流回调（覆盖默认的 sdk.die）。

        handler(port_name) 在看门狗线程中调用；抛异常则升级为 die。
        安全值输出（如执行器回中位）适合用此回调实现。
        """
        self._on_input_lost[port_name] = handler

    def die(self, reason: str, code: int = 1):
        """实例方法形态的统一大声死（见模块级 die 文档）"""
        die(reason, code=code)

    def _stop_health_heartbeat(self):
        self._health_running = False
        self._health_stop_event.set()
        if self._health_thread:
            self._health_thread.join(timeout=2.0)

    def _health_loop(self):
        while self._health_running:
            self.report_health()
            self._health_stop_event.wait(self._health_interval)

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
