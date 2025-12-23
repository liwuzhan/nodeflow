"""
田地生成模块

用于仿真器生成虚拟农田边界
提供简化的田地边界数据供路径规划节点使用
"""

import math
import random
from typing import List, Tuple, Dict, Any


class FieldGenerator:
    """
    田地生成器

    生成简化的田地边界（矩形或不规则多边形）
    输出符合路径规划节点需求的格式
    """

    def __init__(self, base_x: float = 0.0, base_y: float = 0.0):
        """
        初始化田地生成器

        Args:
            base_x: 基础X坐标（米）
            base_y: 基础Y坐标（米）
        """
        self.base_x = base_x
        self.base_y = base_y

    def generate_rectangular_field(self, width: float, length: float) -> Dict[str, Any]:
        """
        生成矩形田地

        Args:
            width: 宽度（米）
            length: 长度（米）

        Returns:
            田地数据字典
        """
        # 矩形四个顶点（逆时针方向）
        boundary = [
            (self.base_x, self.base_y),                    # 左下
            (self.base_x + width, self.base_y),            # 右下
            (self.base_x + width, self.base_y + length),   # 右上
            (self.base_x, self.base_y + length)            # 左上
        ]

        return {
            "type": "rectangular",
            "boundary": boundary,
            "width": width,
            "length": length,
            "area": width * length,
            "center": (self.base_x + width/2, self.base_y + length/2),
            "obstacles": [],  # 暂无障碍物
            "entry_points": [(self.base_x, self.base_y)]  # 默认左下角为入口
        }

    def generate_irregular_field(self, width: float, length: float,
                                 num_points: int = 6) -> Dict[str, Any]:
        """
        生成不规则多边形田地

        Args:
            width: 大致宽度（米）
            length: 大致长度（米）
            num_points: 多边形顶点数

        Returns:
            田地数据字典
        """
        # 生成中心点
        center_x = self.base_x + width / 2
        center_y = self.base_y + length / 2

        # 生成随机角度（逆时针排序）
        angles = sorted([random.uniform(0, 2 * math.pi) for _ in range(num_points)])

        # 生成多边形顶点
        boundary = []
        for angle in angles:
            # 随机半径（在0.7-1.3倍基础半径范围内）
            radius_x = random.uniform(0.7, 1.3) * width / 2
            radius_y = random.uniform(0.7, 1.3) * length / 2

            # 计算坐标（椭圆形）
            x = center_x + radius_x * math.cos(angle)
            y = center_y + radius_y * math.sin(angle)

            boundary.append((x, y))

        # 计算实际面积（近似）
        area = self._calculate_polygon_area(boundary)

        # 找到最左下的点作为入口
        entry_point = min(boundary, key=lambda p: (p[1], p[0]))

        return {
            "type": "irregular",
            "boundary": boundary,
            "width": width,  # 近似宽度
            "length": length,  # 近似长度
            "area": area,
            "center": (center_x, center_y),
            "obstacles": [],
            "entry_points": [entry_point]
        }

    def generate_simple_obstacles(self, field: Dict[str, Any],
                                  num_obstacles: int = 3,
                                  obstacle_radius: float = 1.0) -> Dict[str, Any]:
        """
        在田地内生成简单的圆形障碍物

        Args:
            field: 田地数据
            num_obstacles: 障碍物数量
            obstacle_radius: 障碍物半径（米）

        Returns:
            更新后的田地数据
        """
        boundary = field["boundary"]

        # 计算边界框
        min_x = min(p[0] for p in boundary)
        max_x = max(p[0] for p in boundary)
        min_y = min(p[1] for p in boundary)
        max_y = max(p[1] for p in boundary)

        obstacles = []
        for _ in range(num_obstacles):
            # 随机生成障碍物中心（避开边界）
            margin = obstacle_radius * 2
            x = random.uniform(min_x + margin, max_x - margin)
            y = random.uniform(min_y + margin, max_y - margin)

            obstacles.append({
                "type": "circle",
                "center": (x, y),
                "radius": obstacle_radius
            })

        field["obstacles"] = obstacles
        return field

    def _calculate_polygon_area(self, points: List[Tuple[float, float]]) -> float:
        """
        计算多边形面积（鞋带公式）

        Args:
            points: 多边形顶点列表

        Returns:
            面积（平方米）
        """
        n = len(points)
        if n < 3:
            return 0.0

        area = 0.0
        for i in range(n):
            j = (i + 1) % n
            area += points[i][0] * points[j][1]
            area -= points[j][0] * points[i][1]

        return abs(area) / 2.0


class PredefinedFields:
    """预定义的标准田地配置"""

    @staticmethod
    def small_rectangular():
        """小型矩形田地（适合快速测试）"""
        gen = FieldGenerator(base_x=-50.0, base_y=0.0)
        return gen.generate_rectangular_field(width=100.0, length=200.0)

    @staticmethod
    def medium_rectangular():
        """中型矩形田地"""
        gen = FieldGenerator(base_x=-100.0, base_y=0.0)
        return gen.generate_rectangular_field(width=200.0, length=400.0)

    @staticmethod
    def large_rectangular():
        """大型矩形田地"""
        gen = FieldGenerator(base_x=-250.0, base_y=0.0)
        return gen.generate_rectangular_field(width=500.0, length=1000.0)

    @staticmethod
    def small_irregular():
        """小型不规则田地"""
        gen = FieldGenerator(base_x=-50.0, base_y=0.0)
        field = gen.generate_irregular_field(width=100.0, length=200.0, num_points=6)
        return gen.generate_simple_obstacles(field, num_obstacles=2, obstacle_radius=2.0)

    @staticmethod
    def medium_irregular():
        """中型不规则田地"""
        gen = FieldGenerator(base_x=-100.0, base_y=0.0)
        field = gen.generate_irregular_field(width=200.0, length=400.0, num_points=8)
        return gen.generate_simple_obstacles(field, num_obstacles=3, obstacle_radius=3.0)


def main():
    """测试田地生成"""
    import json

    print("=" * 60)
    print("田地生成测试")
    print("=" * 60)

    # 测试矩形田地
    print("\n1. 小型矩形田地:")
    field = PredefinedFields.small_rectangular()
    print(json.dumps(field, indent=2, ensure_ascii=False))

    # 测试不规则田地
    print("\n2. 小型不规则田地（带障碍物）:")
    field = PredefinedFields.small_irregular()
    print(json.dumps(field, indent=2, ensure_ascii=False))

    print("\n" + "=" * 60)


if __name__ == "__main__":
    main()
