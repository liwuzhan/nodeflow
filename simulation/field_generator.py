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

    def __init__(self, base_x: float = 0.0, base_y: float = 0.0, seed: int = None):
        """
        初始化田地生成器

        Args:
            base_x: 基础X坐标（米）
            base_y: 基础Y坐标（米）
        """
        self.base_x = base_x
        self.base_y = base_y
        self._rng = random.Random(seed)

    def generate_fixed_field(self, boundary, holes=None, entry_points=None):
        """使用实测/固定轮廓，不额外随机改变地块。"""
        from shapely.geometry import Polygon
        outer = Polygon(boundary)
        if not outer.is_valid or outer.area <= 0:
            raise ValueError("field.boundary must be a valid nonzero polygon")
        holes = holes or []
        accepted = []
        for points in holes:
            hole = Polygon(points)
            if not hole.is_valid or hole.area <= 0 or not outer.contains(hole):
                raise ValueError("Every field hole must lie strictly inside the actual boundary")
            if any(hole.intersects(other) for other in accepted):
                raise ValueError("Field holes must not overlap or touch")
            accepted.append(hole)
        polygon = Polygon(boundary, holes)
        min_x, min_y, max_x, max_y = polygon.bounds
        return {
            "type": "fixed", "boundary": list(boundary), "holes": list(holes),
            "width": max_x - min_x, "length": max_y - min_y,
            "area": polygon.area, "center": (polygon.centroid.x, polygon.centroid.y),
            "obstacles": [], "entry_points": list(entry_points or [boundary[0]]),
        }

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
            "obstacles": [],
            "entry_points": [(self.base_x, self.base_y)],
            "holes": []
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
        angles = sorted([self._rng.uniform(0, 2 * math.pi) for _ in range(num_points)])

        # 生成多边形顶点
        boundary = []
        for angle in angles:
            # 随机半径（在0.7-1.3倍基础半径范围内）
            radius = self._rng.uniform(0.7, 1.3)
            radius_x = radius * width / 2
            radius_y = radius * length / 2

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
            "entry_points": [entry_point],
            "holes": []
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

        from shapely.geometry import Point, Polygon
        available = Polygon(boundary, field.get("holes", []))
        obstacles = []
        accepted = []
        for _ in range(num_obstacles):
            for attempt in range(100):
                x = self._rng.uniform(min_x, max_x)
                y = self._rng.uniform(min_y, max_y)
                circle = Point(x, y).buffer(obstacle_radius)
                if available.contains(circle) and not any(circle.intersects(p) for p in accepted):
                    obstacles.append({"type": "circle", "center": (x, y), "radius": obstacle_radius})
                    accepted.append(circle)
                    break
            else:
                raise ValueError("Unable to place requested obstacles within actual field boundary")
        field["obstacles"] = obstacles
        return field

    def generate_random_holes(self, field: Dict[str, Any], num_holes: int,
                              size_ratio: float = 0.05, segments: int = 16) -> Dict[str, Any]:
        """孔洞必须完整位于真实轮廓内；按面积比例生成，禁止互相重叠。"""
        from shapely.geometry import Polygon, Point
        boundary = field.get("boundary", [])
        if not boundary or num_holes <= 0 or size_ratio <= 0.0:
            return field
        outer = Polygon(boundary)
        if not outer.is_valid:
            raise ValueError("Invalid field polygon")
        min_x, min_y, max_x, max_y = outer.bounds
        holes = list(field.get("holes", []))
        accepted = [Polygon(points) for points in holes]
        accepted.extend(Point(item["center"]).buffer(item["radius"])
                        for item in field.get("obstacles", []) if item.get("type") == "circle")
        radius = math.sqrt(outer.area * size_ratio / math.pi)
        for _ in range(num_holes):
            for attempt in range(200):
                cx = self._rng.uniform(min_x, max_x)
                cy = self._rng.uniform(min_y, max_y)
                pts = [(cx + radius * math.cos(2 * math.pi * i / segments),
                        cy + radius * math.sin(2 * math.pi * i / segments)) for i in range(segments)]
                hole = Polygon(pts)
                if outer.contains(hole) and not any(hole.intersects(p) for p in accepted):
                    holes.append(pts)
                    accepted.append(hole)
                    break
            else:
                raise ValueError("Unable to place requested holes within actual field boundary")
        field["holes"] = holes
        field["area"] = Polygon(boundary, holes).area
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
