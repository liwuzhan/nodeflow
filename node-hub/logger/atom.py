#!/usr/bin/env python3
"""
Logger Node - 原子层 (L4)

纯算法实现，无外部依赖，负责：
- 日志条目数据结构
- 日志缓冲区管理
- 日志格式化
"""

import json
import time
from typing import Any, Dict, List
from collections import deque


class LogEntry:
    """日志条目"""

    def __init__(
        self,
        timestamp: float,
        port: str,
        data: Any,
        level: str = "INFO",
        seq: int = 0,
        node_id: str = ""
    ):
        """
        初始化日志条目

        参数：
        - timestamp: 时间戳（Unix时间，秒）
        - port: 端口名（input1/input2/input3）
        - data: 数据内容
        - level: 日志级别（INFO/WARNING/ERROR）
        - seq: 序列号（可选）
        - node_id: 节点ID（可选）
        """
        self.timestamp = timestamp
        self.port = port
        self.data = data
        self.level = level
        self.seq = seq
        self.node_id = node_id

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        result = {
            'timestamp': self.timestamp,
            'port': self.port,
            'data': self.data,
            'level': self.level,
        }
        if self.seq > 0:
            result['seq'] = self.seq
        if self.node_id:
            result['node_id'] = self.node_id
        return result


class LogBuffer:
    """日志缓冲区（循环缓冲区）"""

    def __init__(self, max_size: int = 1000):
        """
        初始化日志缓冲区

        参数：
        - max_size: 最大缓冲区大小
        """
        self.max_size = max_size
        self.buffer: deque[LogEntry] = deque(maxlen=max_size)
        self.total_count = 0  # 总接收日志数

    def add_entry(self, entry_dict: Dict[str, Any]) -> LogEntry:
        """
        添加日志条目

        参数：
        - entry_dict: 日志条目字典

        返回：
        - LogEntry对象
        """
        log_entry = LogEntry(
            timestamp=entry_dict.get('timestamp', time.time()),
            port=entry_dict.get('port', 'unknown'),
            data=entry_dict.get('data', {}),
            level=entry_dict.get('level', 'INFO'),
            seq=entry_dict.get('seq', 0),
            node_id=entry_dict.get('node_id', '')
        )

        self.buffer.append(log_entry)
        self.total_count += 1

        return log_entry

    def get_all(self) -> List[LogEntry]:
        """
        获取所有日志条目

        返回：
        - 日志条目列表（按时间从旧到新）
        """
        return list(self.buffer)

    def get_recent(self, count: int) -> List[LogEntry]:
        """
        获取最近的 N 条日志

        参数：
        - count: 数量

        返回：
        - 日志条目列表（最新的在前）
        """
        if count >= len(self.buffer):
            return list(reversed(self.buffer))

        # 获取最后 count 个元素并反转
        recent = list(self.buffer)[-count:]
        return list(reversed(recent))

    def clear(self) -> None:
        """清空缓冲区"""
        self.buffer.clear()
        # 不重置 total_count，保留历史统计

    def size(self) -> int:
        """当前缓冲区大小"""
        return len(self.buffer)

    def get_stats(self) -> Dict[str, Any]:
        """
        获取缓冲区统计信息

        返回：
        - 统计信息字典
        """
        port_counts: Dict[str, int] = {}
        level_counts: Dict[str, int] = {}

        for entry in self.buffer:
            # 统计端口
            port_counts[entry.port] = port_counts.get(entry.port, 0) + 1
            # 统计级别
            level_counts[entry.level] = level_counts.get(entry.level, 0) + 1

        return {
            'current_size': len(self.buffer),
            'max_size': self.max_size,
            'total_count': self.total_count,
            'port_counts': port_counts,
            'level_counts': level_counts,
        }


class LogFormatter:
    """日志格式化器"""

    @staticmethod
    def format_for_json(log_entry: LogEntry) -> str:
        """
        格式化为JSON字符串（用于文件存储）

        参数：
        - log_entry: LogEntry对象

        返回：
        - JSON字符串（单行）
        """
        return json.dumps(log_entry.to_dict(), ensure_ascii=False)

    @staticmethod
    def format_for_html(log_entry: LogEntry) -> Dict[str, Any]:
        """
        格式化为HTML/WebSocket传输格式

        参数：
        - log_entry: LogEntry对象

        返回：
        - 格式化后的字典
        """
        return log_entry.to_dict()

    @staticmethod
    def format_for_console(log_entry: LogEntry) -> str:
        """
        格式化为控制台输出格式

        参数：
        - log_entry: LogEntry对象

        返回：
        - 格式化字符串
        """
        timestamp_str = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(log_entry.timestamp))
        level_str = f"[{log_entry.level:7s}]"
        port_str = f"[{log_entry.port:7s}]"

        # 简化数据显示
        data_str = str(log_entry.data)
        if len(data_str) > 100:
            data_str = data_str[:97] + "..."

        return f"{timestamp_str} {level_str} {port_str} {data_str}"
