"""
日志工具模块
提供统一的日志配置和获取接口
"""

import logging
import sys
from typing import Optional


def setup_logger(name: str = "nodeflow", level: str = "INFO") -> logging.Logger:
    """
    设置日志记录器

    参数：
    - name: 记录器名称
    - level: 日志级别（DEBUG/INFO/WARNING/ERROR/CRITICAL）

    返回：
    - 配置好的Logger对象
    """
    logger = logging.getLogger(name)
    logger.setLevel(level.upper())

    # 如果已有处理器，直接返回
    if logger.handlers:
        return logger

    # 创建控制台处理器
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(level.upper())

    # 创建格式化器
    formatter = logging.Formatter(
        "%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )

    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    return logger


def get_logger(name: str) -> logging.Logger:
    """
    获取或创建日志记录器

    参数：
    - name: 记录器名称（通常使用模块名__name__）

    返回：
    - Logger对象
    """
    return logging.getLogger(name)


# 主框架日志记录器
logger = setup_logger("nodeflow")
