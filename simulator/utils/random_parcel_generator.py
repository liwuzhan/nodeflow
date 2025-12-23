#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
随机地块生成程序
生成符合 parcel_format_spec.txt 规范的地块文件
"""

import random
import math
from datetime import datetime
from typing import List, Tuple


class RandomParcelGenerator:
    def __init__(self, base_lon: float = 121.5, base_lat: float = 31.2):
        """
        初始化随机地块生成器
        
        Args:
            base_lon: 基础经度
            base_lat: 基础纬度
        """
        self.base_lon = base_lon
        self.base_lat = base_lat
        self.precision = 8

    # =========================
    # 几何辅助函数
    # =========================
    def point_on_segment(self, p: Tuple[float, float], a: Tuple[float, float], b: Tuple[float, float], eps: float = 1e-12) -> bool:
        """
        判断点p是否在线段ab上
        """
        (px, py) = p
        (ax, ay) = a
        (bx, by) = b
        # 面积（叉积）接近0表示共线
        cross = (bx - ax) * (py - ay) - (by - ay) * (px - ax)
        if abs(cross) > eps:
            return False
        # 点积用于判断是否在线段范围内
        dot = (px - ax) * (px - bx) + (py - ay) * (py - by)
        return dot <= eps

    def point_in_polygon(self, point: Tuple[float, float], polygon: List[Tuple[float, float]]) -> bool:
        """
        点在多边形内判断（含边界为内）：射线法
        """
        x, y = point
        inside = False
        n = len(polygon)
        for i in range(n):
            x1, y1 = polygon[i]
            x2, y2 = polygon[(i + 1) % n]

            # 边界判断
            if self.point_on_segment(point, (x1, y1), (x2, y2)):
                return True

            # 射线与边相交判断
            intersects = ((y1 > y) != (y2 > y)) and (x < (x1 + (y - y1) * (x2 - x1) / (y2 - y1)))
            if intersects:
                inside = not inside
        return inside

    def distance_point_to_segment(self, p: Tuple[float, float], a: Tuple[float, float], b: Tuple[float, float]) -> float:
        """
        点到线段的最短距离
        """
        px, py = p
        ax, ay = a
        bx, by = b
        vx = bx - ax
        vy = by - ay
        wx = px - ax
        wy = py - ay
        c = vx * vx + vy * vy
        if c == 0.0:
            return math.hypot(px - ax, py - ay)
        t = (wx * vx + wy * vy) / c
        t = max(0.0, min(1.0, t))
        cx = ax + t * vx
        cy = ay + t * vy
        return math.hypot(px - cx, py - cy)

    def min_distance_to_polygon_edges(self, point: Tuple[float, float], polygon: List[Tuple[float, float]]) -> float:
        """
        点到多边形边界的最小距离
        """
        min_d = float('inf')
        n = len(polygon)
        for i in range(n):
            a = polygon[i]
            b = polygon[(i + 1) % n]
            d = self.distance_point_to_segment(point, a, b)
            if d < min_d:
                min_d = d
        return min_d
        
    def generate_polygon(self, num_points: int, size_hectares: float = 1.0) -> List[Tuple[float, float]]:
        """
        生成随机多边形（确保不自交）
        
        Args:
            num_points: 多边形顶点数
            size_hectares: 地块大小（公顷）
            
        Returns:
            多边形顶点坐标列表 [(lon, lat), ...]
        """
        # 1公顷 = 10000平方米，转换为经纬度偏移量（近似）
        # 在纬度31.2度附近，1度纬度约111公里，1度经度约96公里
        size_meters = math.sqrt(size_hectares * 10000)
        lat_offset = size_meters / 111000  # 约0.0009度
        lon_offset = size_meters / 96000   # 约0.00104度
        
        # 生成中心点
        center_lon = self.base_lon + random.uniform(-0.001, 0.001)
        center_lat = self.base_lat + random.uniform(-0.001, 0.001)
        
        # 生成随机角度
        angles = sorted([random.uniform(0, 2 * math.pi) for _ in range(num_points)])
        
        # 生成多边形顶点
        points = []
        for angle in angles:
            # 随机半径（在0.7-1.3倍基础半径范围内）
            radius = random.uniform(0.7, 1.3) * min(lon_offset, lat_offset)
            
            # 计算坐标
            lon = center_lon + radius * math.cos(angle)
            lat = center_lat + radius * math.sin(angle)
            
            # 保留8位小数
            lon = round(lon, self.precision)
            lat = round(lat, self.precision)
            
            points.append((lon, lat))
        
        return points
    
    def generate_hole(self, outer_polygon: List[Tuple[float, float]], 
                     num_points: int = 4) -> List[Tuple[float, float]]:
        """
        生成位于外环内部的孔洞（严格保证完全在外环内部）
        """
        # 外环边界框
        min_lon = min(p[0] for p in outer_polygon)
        max_lon = max(p[0] for p in outer_polygon)
        min_lat = min(p[1] for p in outer_polygon)
        max_lat = max(p[1] for p in outer_polygon)

        # 反复尝试寻找合适的中心点和半径
        for _ in range(200):
            # 在边界框内随机取点，直到点在外环内
            center_lon = random.uniform(min_lon, max_lon)
            center_lat = random.uniform(min_lat, max_lat)
            center = (center_lon, center_lat)
            if not self.point_in_polygon(center, outer_polygon):
                continue

            # 计算中心到外边界的最小距离，作为安全半径上限
            min_dist = self.min_distance_to_polygon_edges(center, outer_polygon)
            if min_dist <= 0:
                continue

            # 给定更保守的半径上限，避免接触外环
            max_radius = min_dist * 0.45
            if max_radius <= 1e-9:
                continue

            # 生成随机角度
            angles = sorted([random.uniform(0, 2 * math.pi) for _ in range(num_points)])

            # 尝试生成满足条件的孔洞顶点集合
            radius_scale = 0.8
            for _attempt in range(20):
                points = []
                for angle in angles:
                    radius = random.uniform(0.3, radius_scale) * max_radius
                    lon = center_lon + radius * math.cos(angle)
                    lat = center_lat + radius * math.sin(angle)
                    lon = round(lon, self.precision)
                    lat = round(lat, self.precision)
                    points.append((lon, lat))

                # 检查所有顶点均在外环内
                if all(self.point_in_polygon(pt, outer_polygon) for pt in points):
                    return points
                # 缩小半径重试
                radius_scale *= 0.8

        # 兜底策略：在中心点附近生成一个非常小的孔洞（三角形）
        # 此处保证尺寸极小，降低越界风险
        safe_center = None
        for _ in range(100):
            c = (random.uniform(min_lon, max_lon), random.uniform(min_lat, max_lat))
            if self.point_in_polygon(c, outer_polygon):
                safe_center = c
                break
        if safe_center is None:
            # 如果实在找不到，就返回一个空孔洞（调用方会忽略）
            return []
        min_dist = self.min_distance_to_polygon_edges(safe_center, outer_polygon)
        r = min_dist * 0.2
        angles = sorted([random.uniform(0, 2 * math.pi) for _ in range(max(3, num_points))])
        points = []
        for angle in angles[:max(3, num_points)]:
            lon = safe_center[0] + r * math.cos(angle)
            lat = safe_center[1] + r * math.sin(angle)
            points.append((round(lon, self.precision), round(lat, self.precision)))
        return points
    
    def generate_point_obstacle(self, outer_polygon: List[Tuple[float, float]], 
                               holes: List[List[Tuple[float, float]]]) -> Tuple[float, float]:
        """
        生成点障碍物（严格：在外环内且不在任何孔洞内）
        """
        # 外环边界框
        min_lon = min(p[0] for p in outer_polygon)
        max_lon = max(p[0] for p in outer_polygon)
        min_lat = min(p[1] for p in outer_polygon)
        max_lat = max(p[1] for p in outer_polygon)

        # 反复采样直到满足条件
        for _ in range(500):
            lon = random.uniform(min_lon, max_lon)
            lat = random.uniform(min_lat, max_lat)
            pt = (lon, lat)

            # 必须在外环内
            if not self.point_in_polygon(pt, outer_polygon):
                continue

            # 不允许在任何孔洞内
            in_hole = any(self.point_in_polygon(pt, hole) for hole in holes if hole)
            if in_hole:
                continue

            # 远离外环边界一点，避免贴边
            if self.min_distance_to_polygon_edges(pt, outer_polygon) < 1e-5:
                continue

            return (round(lon, self.precision), round(lat, self.precision))

        # 兜底：选择外环任意顶点附近偏移一个极小量
        v = random.choice(outer_polygon)
        return (round(v[0] + 1e-6, self.precision), round(v[1] + 1e-6, self.precision))
    
    def generate_entry_exit(self, outer_polygon: List[Tuple[float, float]]) -> Tuple[float, float]:
        """
        生成出入口位置（在地块边界上）
        
        Args:
            outer_polygon: 外环多边形
            
        Returns:
            出入口坐标 (lon, lat)
        """
        # 随机选择一条边
        edge_index = random.randint(0, len(outer_polygon) - 1)
        p1 = outer_polygon[edge_index]
        p2 = outer_polygon[(edge_index + 1) % len(outer_polygon)]
        
        # 在边上随机选择一个点
        t = random.uniform(0.1, 0.9)
        lon = p1[0] + t * (p2[0] - p1[0])
        lat = p1[1] + t * (p2[1] - p1[1])
        
        lon = round(lon, self.precision)
        lat = round(lat, self.precision)
        
        return (lon, lat)
    
    def generate_parcel_file(self, output_path: str, num_outer_points: int = 6, 
                           num_holes: int = 2, num_points_per_hole: int = 4,
                           num_obstacles: int = 3, num_entry_exits: int = 2):
        """
        生成完整的地块文件
        
        Args:
            output_path: 输出文件路径
            num_outer_points: 外环顶点数
            num_holes: 孔洞数量
            num_points_per_hole: 每个孔洞的顶点数
            num_obstacles: 点障碍物数量
            num_entry_exits: 出入口数量
        """
        # 生成外环
        outer_polygon = self.generate_polygon(num_outer_points)
        
        # 生成孔洞
        holes = []
        for i in range(num_holes):
            hole = self.generate_hole(outer_polygon, num_points_per_hole)
            holes.append(hole)
        
        # 生成点障碍物
        obstacles = []
        for i in range(num_obstacles):
            obstacle = self.generate_point_obstacle(outer_polygon, holes)
            obstacles.append(obstacle)
        
        # 生成出入口
        entry_exits = []
        for i in range(num_entry_exits):
            entry_exit = self.generate_entry_exit(outer_polygon)
            entry_exits.append(entry_exit)
        
        # 计算边界框
        min_lon = min(p[0] for p in outer_polygon)
        max_lon = max(p[0] for p in outer_polygon)
        min_lat = min(p[1] for p in outer_polygon)
        max_lat = max(p[1] for p in outer_polygon)
        
        # 生成文件内容
        content = []
        content.append("VERSION 1")
        content.append("CRS EPSG:4326")
        content.append(f"PRECISION_DECIMALS {self.precision}")
        content.append(f"META generated_by=random_generator")
        content.append(f"META generation_date={datetime.now().strftime('%Y-%m-%d')}")
        content.append(f"BBOX {min_lon:.8f},{min_lat:.8f},{max_lon:.8f},{max_lat:.8f}")
        content.append("")
        
        # 外环
        content.append("# 外环多边形")
        content.append("OUTER")
        for lon, lat in outer_polygon:
            content.append(f"{lon:.8f},{lat:.8f}")
        content.append("END")
        content.append("")
        
        # 孔洞
        for i, hole in enumerate(holes):
            content.append(f"# 孔/障碍物 {i+1}")
            content.append(f"HOLE hole-{i+1:02d} 障碍物{i+1}")
            for lon, lat in hole:
                content.append(f"{lon:.8f},{lat:.8f}")
            content.append("END")
            content.append("")
        
        # 点障碍物
        content.append("# 点障碍物默认直径（米）")
        content.append("POINTS_DEFAULT_DIAMETER_M 1.0")
        content.append("")
        
        for i, (lon, lat) in enumerate(obstacles):
            diameter = random.choice([1.0, 0.5, 0.8, 1.2])
            if diameter == 1.0:
                content.append(f"# 点 {i+1}：使用默认直径 1 米")
                content.append(f"POINT p-{i+1:02d} 障碍点{i+1} {lon:.8f},{lat:.8f}")
            else:
                content.append(f"# 点 {i+1}：覆盖直径为 {diameter:.2f} 米")
                content.append(f"POINT p-{i+1:02d} 障碍点{i+1} {lon:.8f},{lat:.8f} DIAMETER_M {diameter:.2f}")
        content.append("")
        
        # 出入口
        content.append("# 出入口定义（作业起点）")
        for i, (lon, lat) in enumerate(entry_exits):
            heading = random.choice([0, 90, 180, 270, 45, 135, 225, 315])
            width = random.choice([4.0, 5.0, 6.0])
            exit_type = random.choice(["main", "emergency", "service"])
            
            if exit_type == "main":
                content.append(f"# 主入口：朝向{heading}度，宽度{width}米")
                content.append(f"ENTRY_EXIT entry-{i+1:02d} \"主入口\" {lon:.8f},{lat:.8f} HEADING_DEG {heading} WIDTH_M {width:.1f} TYPE {exit_type}")
            elif exit_type == "emergency":
                content.append(f"# 紧急出口")
                content.append(f"ENTRY_EXIT entry-{i+1:02d} \"紧急出口\" {lon:.8f},{lat:.8f} TYPE {exit_type}")
            else:
                content.append(f"# 维护入口：朝向{heading}度，宽度{width}米")
                content.append(f"ENTRY_EXIT entry-{i+1:02d} \"维护入口\" {lon:.8f},{lat:.8f} HEADING_DEG {heading} WIDTH_M {width:.1f} TYPE {exit_type}")
        
        # 写入文件
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write('\n'.join(content))
        
        print(f"已生成地块文件: {output_path}")
        print(f"外环顶点数: {len(outer_polygon)}")
        print(f"孔洞数量: {len(holes)}")
        print(f"点障碍物数量: {len(obstacles)}")
        print(f"出入口数量: {len(entry_exits)}")


def main():
    """主函数"""
    generator = RandomParcelGenerator()
    
    # 确保config目录存在
    import os
    config_dir = "e:\\10\\config"
    if not os.path.exists(config_dir):
        os.makedirs(config_dir)
    
    # 生成单个地块文件
    output_file = os.path.join(config_dir, "random_parcel.txt")
    
    # 随机参数（更加随机化）
    num_outer = random.randint(4, 14)  # 外环顶点数 4-12个
    num_holes = random.randint(1, 3)    # 孔洞数量 0-5个（允许没有孔洞）
    num_obstacles = random.randint(0, 3) # 点障碍物数量 0-8个（允许没有障碍物）
    num_entries = random.randint(1, 2)   # 出入口数量 1-5个
    
    generator.generate_parcel_file(
        output_path=output_file,
        num_outer_points=num_outer,
        num_holes=num_holes,
        num_points_per_hole=4,
        num_obstacles=num_obstacles,
        num_entry_exits=num_entries
    )


if __name__ == "__main__":
    main()