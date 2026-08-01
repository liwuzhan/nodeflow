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

    # 创建控制台处理器。CLI 的 JSON 输出依赖 stdout 保持纯净，
    # 运行日志按惯例写到 stderr。
    console_handler = logging.StreamHandler(sys.stderr)
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
    
    为了确保所有模块都继承主logger的配置，我们会将名称前缀统一为 "nodeflow."
    除非名称已经是 "nodeflow" 或以 "nodeflow." 开头。

    参数：
    - name: 记录器名称（通常使用模块名__name__）

    返回：
    - Logger对象
    """
    if name == "nodeflow" or name.startswith("nodeflow."):
        real_name = name
    else:
        # 移除可能的 runtime. 前缀以避免重复 (可选，视项目结构而定)
        # 这里简单地将所有模块作为 nodeflow 的子模块处理
        real_name = f"nodeflow.{name}"
        
    return logging.getLogger(real_name)


# 主框架日志记录器
logger = setup_logger("nodeflow")
