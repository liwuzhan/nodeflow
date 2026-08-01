"""
结构化日志系统

为NodeFlow节点提供结构化日志支持：
- JSON格式日志文件（.jsonl）
- 人类可读控制台输出
- 支持自定义字段
- 自动添加时间戳、节点ID、级别等元数据
"""

import json
import logging
import os
import sys
import traceback
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

from edge.runtime.utils.constants import LOGS_DIR


class JSONFileHandler(logging.Handler):
    """
    JSON日志文件处理器

    将日志记录写入JSONL格式文件（每行一个JSON对象）
    """

    def __init__(self, filepath: str, node_id: str):
        """
        初始化JSON文件处理器

        参数:
        - filepath: 日志文件路径
        - node_id: 节点ID
        """
        super().__init__()
        self.filepath = filepath
        self.node_id = node_id

        # 确保目录存在
        Path(filepath).parent.mkdir(parents=True, exist_ok=True)

        # 打开文件（追加模式）
        self.file = open(filepath, 'a', encoding='utf-8', buffering=1)

    def emit(self, record: logging.LogRecord) -> None:
        """
        处理一条日志记录

        参数:
        - record: 日志记录对象
        """
        try:
            # 构建JSON对象
            log_entry = {
                'timestamp': datetime.fromtimestamp(record.created).isoformat(),
                'timestamp_unix': record.created,
                'node_id': self.node_id,
                'level': record.levelname,
                'message': record.getMessage(),
                'logger': record.name,
                'module': record.module,
                'function': record.funcName,
                'line': record.lineno,
            }

            # 添加异常信息
            if record.exc_info:
                log_entry['exception'] = {
                    'type': record.exc_info[0].__name__,
                    'message': str(record.exc_info[1]),
                    'traceback': traceback.format_exception(*record.exc_info)
                }

            # 添加自定义字段（从extra参数传入）
            if hasattr(record, 'custom_fields') and record.custom_fields:
                log_entry['custom'] = record.custom_fields

            # 写入文件（每条日志一行JSON）
            self.file.write(json.dumps(log_entry, ensure_ascii=False) + '\n')

        except Exception as e:
            # 处理器内部错误不应该导致程序崩溃
            self.handleError(record)

    def close(self) -> None:
        """关闭文件"""
        if self.file:
            self.file.close()
        super().close()


class StructuredLogger:
    """
    结构化日志器

    提供双重输出：
    1. 控制台：人类可读格式
    2. JSON文件：机器可解析格式

    用法:
        logger = StructuredLogger(node_id="sim_output", log_level="INFO")
        logger.info("仿真器连接成功", host="localhost", port=5555)
        logger.error("连接失败", exc_info=True)
    """

    def __init__(
        self,
        node_id: str,
        log_level: str = "INFO",
        log_dir: str = LOGS_DIR,
        enable_json: bool = True,
        enable_console: bool = True
    ):
        """
        初始化结构化日志器

        参数:
        - node_id: 节点ID
        - log_level: 日志级别（DEBUG/INFO/WARNING/ERROR/CRITICAL）
        - log_dir: 日志目录（默认 LOGS_DIR）
        - enable_json: 是否启用JSON文件输出
        - enable_console: 是否启用控制台输出
        """
        self.node_id = node_id
        self.log_level = log_level.upper()
        self.log_dir = log_dir

        # 创建底层logger
        self._logger = logging.getLogger(f"nodeflow.node.{node_id}")
        self._logger.setLevel(self.log_level)

        # 防止重复添加处理器
        self._logger.handlers.clear()

        # 添加JSON文件处理器
        if enable_json:
            json_file = os.path.join(log_dir, f"{node_id}.jsonl")
            json_handler = JSONFileHandler(json_file, node_id)
            json_handler.setLevel(self.log_level)
            self._logger.addHandler(json_handler)

        # 添加控制台处理器
        if enable_console:
            console_handler = logging.StreamHandler(sys.stdout)
            console_handler.setLevel(self.log_level)

            # 控制台格式：简洁但信息完整
            console_formatter = logging.Formatter(
                fmt='[%(asctime)s] [%(name)s] [%(levelname)s] %(message)s',
                datefmt='%Y-%m-%d %H:%M:%S'
            )
            console_handler.setFormatter(console_formatter)
            self._logger.addHandler(console_handler)

        # 阻止日志传播到root logger（避免重复输出）
        self._logger.propagate = False

    def _log(self, level: int, msg: str, exc_info: Any = None, **kwargs) -> None:
        """
        内部日志方法

        参数:
        - level: 日志级别
        - msg: 日志消息
        - exc_info: 异常信息
        - **kwargs: 自定义字段
        """
        # 将自定义字段附加到LogRecord
        extra = {'custom_fields': kwargs} if kwargs else {}
        self._logger.log(level, msg, exc_info=exc_info, extra=extra)

    def debug(self, msg: str, **kwargs) -> None:
        """
        记录DEBUG级别日志

        参数:
        - msg: 日志消息
        - **kwargs: 自定义字段

        示例:
            logger.debug("路径点选择", waypoint_index=10, distance=5.3)
        """
        self._log(logging.DEBUG, msg, **kwargs)

    def info(self, msg: str, **kwargs) -> None:
        """
        记录INFO级别日志

        参数:
        - msg: 日志消息
        - **kwargs: 自定义字段

        示例:
            logger.info("节点启动", version="1.0")
        """
        self._log(logging.INFO, msg, **kwargs)

    def warning(self, msg: str, **kwargs) -> None:
        """
        记录WARNING级别日志

        参数:
        - msg: 日志消息
        - **kwargs: 自定义字段

        示例:
            logger.warning("连接超时", timeout_ms=2000)
        """
        self._log(logging.WARNING, msg, **kwargs)

    def error(self, msg: str, exc_info: Any = None, **kwargs) -> None:
        """
        记录ERROR级别日志

        参数:
        - msg: 日志消息
        - exc_info: 异常信息（可选，True表示捕获当前异常）
        - **kwargs: 自定义字段

        示例:
            try:
                ...
            except Exception as e:
                logger.error("处理失败", exc_info=True, data_size=1024)
        """
        self._log(logging.ERROR, msg, exc_info=exc_info, **kwargs)

    def critical(self, msg: str, exc_info: Any = None, **kwargs) -> None:
        """
        记录CRITICAL级别日志

        参数:
        - msg: 日志消息
        - exc_info: 异常信息（可选）
        - **kwargs: 自定义字段
        """
        self._log(logging.CRITICAL, msg, exc_info=exc_info, **kwargs)

    def close(self) -> None:
        """关闭所有处理器"""
        for handler in self._logger.handlers:
            handler.close()
        self._logger.handlers.clear()


def create_logger(
    node_id: str,
    log_level: str = "INFO",
    log_dir: Optional[str] = None
) -> StructuredLogger:
    """
    创建结构化日志器（便捷工厂函数）

    参数:
    - node_id: 节点ID
    - log_level: 日志级别
    - log_dir: 日志目录（可选，默认使用环境变量或 LOGS_DIR）

    返回:
    - StructuredLogger实例
    """
    if log_dir is None:
        log_dir = os.getenv('NODEFLOW_LOG_DIR', LOGS_DIR)

    return StructuredLogger(node_id=node_id, log_level=log_level, log_dir=log_dir)
