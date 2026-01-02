"""
测试数据生成器 - <your_node>节点

生成符合节点输入格式的模拟数据，用于独立测试
"""

from typing import Dict, Any, List
import random


class TestDataGenerator:
    """生成测试数据"""

    # TODO: 添加常量和参数
    # 示例：
    # DEFAULT_LAT = 31.2
    # DEFAULT_LON = 121.5

    @staticmethod
    def generate_sample_input() -> Dict[str, Any]:
        """
        生成样本输入数据

        TODO: 修改返回格式以匹配你的节点输入端口格式

        返回：
            符合节点输入格式的字典

        示例：
            {
                "task_id": "test_001",
                "data": [...]
            }
        """
        # TODO: 修改为你的数据格式
        return {
            "task_id": "test_001",
            "timestamp": "2025-12-25T00:00:00Z",
            # TODO: 添加更多字段
        }

    @staticmethod
    def generate_sample_output() -> Dict[str, Any]:
        """
        生成样本输出数据

        TODO: 修改返回格式以匹配你的节点输出端口格式

        返回：
            符合节点输出格式的字典
        """
        # TODO: 修改为你的数据格式
        return {
            "result": "success",
            "data": [],
            # TODO: 添加更多字段
        }

    # TODO: 添加更多数据生成方法
    # 示例：
    # @staticmethod
    # def generate_gps_data(count: int = 10):
    #     """生成GPS数据"""
    #     return [
    #         {
    #             "latitude": 31.2 + i * 0.001,
    #             "longitude": 121.5 + i * 0.001
    #         }
    #         for i in range(count)
    #     ]


def create_test_scenario(scenario: str = "basic") -> Dict[str, Any]:
    """
    创建完整的测试场景

    参数：
        scenario: 场景类型 ("basic", "edge_case", "error", 等)

    返回：
        包含所有测试数据的字典

    TODO: 添加不同的测试场景
    """
    gen = TestDataGenerator()

    if scenario == "basic":
        # TODO: 修改为你的基础场景
        return {
            "input": gen.generate_sample_input(),
            "expected_output": gen.generate_sample_output()
        }
    elif scenario == "edge_case":
        # TODO: 添加边界情况场景
        return {
            "input": {},  # TODO: 边界情况数据
            "expected_output": {}
        }
    else:
        raise ValueError(f"Unknown scenario: {scenario}")


if __name__ == "__main__":
    # 测试数据生成器
    import json

    print("生成测试数据...")

    for scenario in ["basic"]:  # TODO: 添加更多场景
        data = create_test_scenario(scenario)
        print(f"\n场景: {scenario}")
        print(json.dumps(data, indent=2, ensure_ascii=False))
