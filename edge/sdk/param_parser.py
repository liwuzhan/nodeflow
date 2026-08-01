"""
参数解析器模块
解析命令行传递的--params参数
"""

import argparse
import json
from typing import Dict, Any


class ParamParser:
    """参数解析器"""

    @staticmethod
    def parse() -> Dict[str, Any]:
        """
        从命令行解析--params参数

        框架通过以下方式传递参数：
        python3 run.py --params '{"key":"value"}'

        返回：
        - 参数字典
        """
        parser = argparse.ArgumentParser()
        parser.add_argument(
            '--params',
            type=str,
            default='{}',
            help='JSON-formatted parameters'
        )

        args, _ = parser.parse_known_args()

        try:
            params = json.loads(args.params)
            return params
        except json.JSONDecodeError as e:
            raise ValueError(f"Invalid JSON in --params: {e}")

    @staticmethod
    def get_param(params: Dict[str, Any], key: str, default: Any = None) -> Any:
        """
        获取参数值

        参数：
        - params: 参数字典
        - key: 参数名
        - default: 默认值（如果参数不存在）

        返回：
        - 参数值
        """
        return params.get(key, default)

    @staticmethod
    def require_param(params: Dict[str, Any], key: str) -> Any:
        """
        获取必填参数

        参数：
        - params: 参数字典
        - key: 参数名

        返回：
        - 参数值

        异常：
        - ValueError: 参数不存在
        """
        if key not in params:
            raise ValueError(f"Required parameter '{key}' not found")

        return params[key]
