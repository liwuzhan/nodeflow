"""
节点监控器模块
监控所有节点进程的健康状态，处理崩溃和重启
"""

import subprocess
import threading
import time
from typing import Dict, Optional, Callable

from edge.runtime.config.models import RestartPolicy as RestartPolicyConfig
from edge.runtime.monitoring.restart_policy import RetryTracker
from edge.runtime.utils.logger import get_logger

logger = get_logger(__name__)


class NodeMonitor:
    """节点监控器"""

    def __init__(self, restart_policy: RestartPolicyConfig, incident_recorder: Optional[Callable] = None):
        """
        初始化节点监控器

        参数：
        - restart_policy: RestartPolicyConfig对象
        - incident_recorder: 死亡记录回调 recorder(node_id, exit_code, stderr_tail, retry_count)，
          由 runtime 注入（W2-4）；None 表示不记录
        """
        self.restart_policy = restart_policy
        self.retry_tracker = RetryTracker(restart_policy)
        self.incident_recorder = incident_recorder

        self.processes: Dict[str, subprocess.Popen] = {}
        self.running = False
        self.monitor_thread: Optional[threading.Thread] = None

        # 重启回调函数（由外部提供）
        self.restart_callback: Optional[Callable] = None
        self.start_times: Dict[str, float] = {}
        self.stable_reset_seconds: float = 300.0

        # 待重启队列：{node_id: scheduled_restart_time}
        self._pending_restarts: Dict[str, float] = {}

    def start_monitoring(
        self,
        processes: Dict[str, subprocess.Popen],
        restart_callback: Optional[Callable] = None
    ):
        """
        开始监控所有节点进程

        参数：
        - processes: 节点ID -> subprocess.Popen对象的映射
        - restart_callback: 重启回调函数 callback(node_id, node_instance, manifest)
        """
        self.processes = processes
        self.restart_callback = restart_callback
        self.running = True
        now = time.time()
        for node_id in processes.keys():
            self.start_times[node_id] = now

        # 启动监控线程
        self.monitor_thread = threading.Thread(
            target=self._monitor_loop,
            daemon=True
        )
        self.monitor_thread.start()

        logger.info(f"Started monitoring {len(processes)} nodes")

    def stop(self):
        """停止监控"""
        self.running = False

        if self.monitor_thread:
            self.monitor_thread.join(timeout=5)

        logger.info("Node monitor stopped")

    def _monitor_loop(self):
        """监控循环（在独立线程中运行）

        循环体整体包异常保护：监控线程必须比被监控对象活得久，
        任何单轮未捕获异常只记日志，不允许杀死整个监控循环。
        """
        check_interval = 1.0  # 每秒检查一次

        while self.running:
            try:
                self._monitor_tick()
            except Exception:
                logger.exception("Unexpected error in monitor loop, continuing")
            time.sleep(check_interval)

    def _monitor_tick(self):
        """单轮监控：崩溃检测、退避重置、到期重启执行"""
        now = time.time()

        # 检查所有进程
        crashed_nodes = []

        for node_id, process in list(self.processes.items()):
            ret_code = process.poll()

            if ret_code is not None:
                # 进程已退出
                crashed_nodes.append((node_id, ret_code))
            else:
                started_at = self.start_times.get(node_id)
                if started_at:
                    if self.retry_tracker.get_retry_count(node_id) > 0:
                        if now - started_at >= self.stable_reset_seconds:
                            self.retry_tracker.reset(node_id)

        # 处理崩溃的节点
        for node_id, ret_code in crashed_nodes:
            self._handle_node_crash(node_id, ret_code)

        # 处理待重启队列中到时间的节点
        for node_id in list(self._pending_restarts.keys()):
            if now >= self._pending_restarts[node_id]:
                del self._pending_restarts[node_id]
                self._execute_restart(node_id)

    def _handle_node_crash(self, node_id: str, exit_code: int):
        """
        处理节点崩溃（非阻塞）

        不再在监控线程中 sleep 等待退避时间，而是将重启计划加入待重启队列，
        由监控循环在后续轮询中检查并执行。

        参数：
        - node_id: 节点ID
        - exit_code: 退出码
        """
        logger.warning(f"Node '{node_id}' crashed with exit code {exit_code}")

        # 从进程字典中移除，并抢救 stderr 遗言
        stderr_tail = ""
        if node_id in self.processes:
            process = self.processes[node_id]

            try:
                _, stderr = process.communicate(timeout=0.1)
                if stderr:
                    stderr_tail = stderr[-500:]
                    logger.error(f"Node '{node_id}' stderr: {stderr_tail}")
            except Exception:
                pass

            del self.processes[node_id]

        # 记录失败
        self.retry_tracker.record_failure(node_id)
        retry_count = self.retry_tracker.get_retry_count(node_id)

        # 死亡记录（W2-4）：监控线程是幸存目击者，在此落验尸报告
        if self.incident_recorder:
            try:
                self.incident_recorder(node_id, exit_code, stderr_tail, retry_count)
            except Exception:
                logger.exception(f"Failed to record death incident for '{node_id}'")

        # 检查是否可以重启
        if not self.retry_tracker.can_retry(node_id):
            logger.error(
                f"Node '{node_id}' exceeded max retries ({self.restart_policy.max_retries}), "
                f"giving up"
            )
            return

        # 计算重启时间并加入待重启队列（非阻塞）
        wait_time = self.retry_tracker.should_wait_before_retry(node_id)
        scheduled_time = time.time() + wait_time
        self._pending_restarts[node_id] = scheduled_time
        if wait_time > 0:
            logger.info(
                f"Scheduled restart for node '{node_id}' in {wait_time:.2f}s "
                f"(attempt {self.retry_tracker.get_retry_count(node_id)})"
            )
        else:
            logger.info(
                f"Restart for node '{node_id}' scheduled immediately "
                f"(attempt {self.retry_tracker.get_retry_count(node_id)})"
            )

    def _execute_restart(self, node_id: str):
        """
        执行节点重启

        回调抛异常或返回 None 不再静默放弃：记一次失败并按退避重新入
        待重启队列，与节点崩溃共享 max_retries 预算，耗尽后才 give up。

        参数：
        - node_id: 节点ID
        """
        if not self.restart_callback:
            logger.warning(f"No restart callback configured, node '{node_id}' not restarted")
            return

        new_process = None
        try:
            logger.info(
                f"Restarting node '{node_id}' "
                f"(attempt {self.retry_tracker.get_retry_count(node_id)})"
            )
            new_process = self.restart_callback(node_id)
        except Exception as e:
            logger.error(f"Error restarting node '{node_id}': {e}")

        if new_process:
            self.processes[node_id] = new_process
            self.start_times[node_id] = time.time()
            logger.info(f"Node '{node_id}' restarted with PID {new_process.pid}")
            return

        # 重启失败 → 记失败并按退避重新调度（与节点崩溃共享重试预算）
        logger.error(f"Failed to restart node '{node_id}'")
        self.retry_tracker.record_failure(node_id)

        if not self.retry_tracker.can_retry(node_id):
            logger.error(
                f"Node '{node_id}' exceeded max retries ({self.restart_policy.max_retries}) "
                f"on restart failures, giving up"
            )
            return

        wait_time = self.retry_tracker.should_wait_before_retry(node_id)
        self._pending_restarts[node_id] = time.time() + wait_time
        logger.info(
            f"Scheduled restart retry for node '{node_id}' in {wait_time:.2f}s "
            f"(attempt {self.retry_tracker.get_retry_count(node_id)})"
        )

    def get_running_nodes(self) -> list:
        """
        获取正在运行的节点列表

        返回：
        - 节点ID列表
        """
        return list(self.processes.keys())

    def get_node_status(self, node_id: str) -> dict:
        """
        获取节点状态

        参数：
        - node_id: 节点ID

        返回：
        - 状态字典
        """
        if node_id in self.processes:
            process = self.processes[node_id]
            ret_code = process.poll()

            status = {
                'running': ret_code is None,
                'pid': process.pid if ret_code is None else None,
                'exit_code': ret_code,
                'retry_status': self.retry_tracker.get_status(node_id),
            }
        else:
            status = {
                'running': False,
                'pid': None,
                'exit_code': None,
                'retry_status': self.retry_tracker.get_status(node_id),
            }

        return status

    def get_all_status(self) -> dict:
        """
        获取所有节点的状态

        返回：
        - 节点ID -> 状态字典的映射
        """
        status_dict = {}

        # 运行中的节点
        for node_id in self.processes.keys():
            status_dict[node_id] = self.get_node_status(node_id)

        # 已停止的节点（有重试记录）
        for node_id in self.retry_tracker.retry_counts.keys():
            if node_id not in status_dict:
                status_dict[node_id] = self.get_node_status(node_id)

        return status_dict
