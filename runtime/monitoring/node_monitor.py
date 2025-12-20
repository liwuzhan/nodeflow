"""
节点监控器模块
监控所有节点进程的健康状态，处理崩溃和重启
"""

import subprocess
import threading
import time
from typing import Dict, Optional, Callable

from runtime.config.models import RestartPolicy as RestartPolicyConfig
from runtime.monitoring.restart_policy import RetryTracker
from runtime.utils.logger import get_logger

logger = get_logger(__name__)


class NodeMonitor:
    """节点监控器"""

    def __init__(self, restart_policy: RestartPolicyConfig):
        """
        初始化节点监控器

        参数：
        - restart_policy: RestartPolicyConfig对象
        """
        self.restart_policy = restart_policy
        self.retry_tracker = RetryTracker(restart_policy)

        self.processes: Dict[str, subprocess.Popen] = {}
        self.running = False
        self.monitor_thread: Optional[threading.Thread] = None

        # 重启回调函数（由外部提供）
        self.restart_callback: Optional[Callable] = None

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
        """监控循环（在独立线程中运行）"""
        check_interval = 1.0  # 每秒检查一次

        while self.running:
            # 检查所有进程
            crashed_nodes = []

            for node_id, process in list(self.processes.items()):
                ret_code = process.poll()

                if ret_code is not None:
                    # 进程已退出
                    crashed_nodes.append((node_id, ret_code))

            # 处理崩溃的节点
            for node_id, ret_code in crashed_nodes:
                self._handle_node_crash(node_id, ret_code)

            # 休眠
            time.sleep(check_interval)

    def _handle_node_crash(self, node_id: str, exit_code: int):
        """
        处理节点崩溃

        参数：
        - node_id: 节点ID
        - exit_code: 退出码
        """
        logger.warning(f"Node '{node_id}' crashed with exit code {exit_code}")

        # 从进程字典中移除
        if node_id in self.processes:
            process = self.processes[node_id]

            # 尝试获取输出
            try:
                stdout, stderr = process.communicate(timeout=0.1)
                if stderr:
                    logger.error(f"Node '{node_id}' stderr: {stderr[:500]}")
            except:
                pass

            del self.processes[node_id]

        # 记录失败
        self.retry_tracker.record_failure(node_id)

        # 检查是否可以重启
        if not self.retry_tracker.can_retry(node_id):
            logger.error(
                f"Node '{node_id}' exceeded max retries ({self.restart_policy.max_retries}), "
                f"giving up"
            )
            return

        # 等待退避时间
        wait_time = self.retry_tracker.should_wait_before_retry(node_id)
        if wait_time > 0:
            logger.info(f"Waiting {wait_time:.2f}s before restarting node '{node_id}'")
            time.sleep(wait_time)

        # 重启节点
        if self.restart_callback:
            try:
                logger.info(
                    f"Restarting node '{node_id}' "
                    f"(attempt {self.retry_tracker.get_retry_count(node_id)})"
                )

                # 调用重启回调
                new_process = self.restart_callback(node_id)

                if new_process:
                    self.processes[node_id] = new_process
                    logger.info(f"Node '{node_id}' restarted with PID {new_process.pid}")
                else:
                    logger.error(f"Failed to restart node '{node_id}'")

            except Exception as e:
                logger.error(f"Error restarting node '{node_id}': {e}")
        else:
            logger.warning(f"No restart callback configured, node '{node_id}' not restarted")

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
