"""
重启策略模块
定义节点崩溃后的重启行为
"""

import time
from edge.runtime.config.models import RestartPolicy
from edge.runtime.utils.logger import get_logger

logger = get_logger(__name__)


class RetryTracker:
    """
    重试追踪器
    跟踪每个节点的重试次数和时间
    """

    def __init__(self, policy: RestartPolicy):
        """
        初始化重试追踪器

        参数：
        - policy: RestartPolicy对象
        """
        self.policy = policy
        self.retry_counts = {}  # node_id -> 重试次数
        self.last_restart_time = {}  # node_id -> 最后重启时间

    def can_retry(self, node_id: str) -> bool:
        """
        检查节点是否可以重试

        参数：
        - node_id: 节点ID

        返回：
        - True表示可以重试，False表示超过最大重试次数
        """
        retry_count = self.retry_counts.get(node_id, 0)
        return retry_count < self.policy.max_retries

    def record_failure(self, node_id: str):
        """
        记录节点失败

        参数：
        - node_id: 节点ID
        """
        current_count = self.retry_counts.get(node_id, 0)
        self.retry_counts[node_id] = current_count + 1
        self.last_restart_time[node_id] = time.time()

        logger.warning(
            f"Node '{node_id}' failed. Retry count: {self.retry_counts[node_id]}/{self.policy.max_retries}"
        )

    def reset(self, node_id: str):
        """
        重置节点的重试计数（节点正常运行时调用）

        参数：
        - node_id: 节点ID
        """
        if node_id in self.retry_counts:
            self.retry_counts[node_id] = 0
            logger.debug(f"Reset retry count for node '{node_id}'")

    def get_retry_count(self, node_id: str) -> int:
        """
        获取节点的重试次数

        参数：
        - node_id: 节点ID

        返回：
        - 重试次数
        """
        return self.retry_counts.get(node_id, 0)

    def should_wait_before_retry(self, node_id: str) -> float:
        """
        计算重试前应该等待的时间

        使用指数退避策略

        参数：
        - node_id: 节点ID

        返回：
        - 应该等待的时间（秒），0表示可以立即重试
        """
        retry_count = self.get_retry_count(node_id)
        last_time = self.last_restart_time.get(node_id, 0)

        # 计算退避时间：backoff_ms * (2 ^ retry_count)
        backoff_seconds = (self.policy.backoff_ms / 1000.0) * (2 ** retry_count)

        # 计算已经等待的时间
        elapsed = time.time() - last_time

        # 还需要等待的时间
        wait_time = max(0, backoff_seconds - elapsed)

        return wait_time

    def get_status(self, node_id: str) -> dict:
        """
        获取节点的重试状态

        参数：
        - node_id: 节点ID

        返回：
        - 状态字典
        """
        return {
            'retry_count': self.get_retry_count(node_id),
            'max_retries': self.policy.max_retries,
            'can_retry': self.can_retry(node_id),
            'last_restart_time': self.last_restart_time.get(node_id),
        }
