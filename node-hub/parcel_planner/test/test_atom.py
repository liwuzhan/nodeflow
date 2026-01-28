#!/usr/bin/env python3
"""
测试 atom.py 中的坐标转换和几何计算功能
"""

import pytest
import math
from atom import (
    gps_to_enu,
    enu_to_gps,
    convert_boundary_gps_to_enu,
    convert_boundary_enu_to_gps,
    calculate_polygon_area,
    calculate_perimeter,
    validate_boundary,
    meters_per_degree_lon,
)


class TestCoordinateConversion:
    """测试坐标转换功能"""

    def test_gps_to_enu_origin(self):
        """测试原点转换，应该返回 (0, 0)"""
        ref_lon, ref_lat = 121.5, 31.2
        x, y = gps_to_enu(ref_lon, ref_lat, ref_lon, ref_lat)
        assert abs(x) < 1e-6, "原点 X 坐标应该是 0"
        assert abs(y) < 1e-6, "原点 Y 坐标应该是 0"

    def test_gps_to_enu_east(self):
        """测试向东移动，X 坐标应该为正"""
        ref_lon, ref_lat = 121.5, 31.2
        x, y = gps_to_enu(121.501, 31.2, ref_lon, ref_lat)
        assert x > 0, "向东移动 X 坐标应为正"
        assert abs(y) < 1e-6, "纬度不变 Y 坐标应为 0"

    def test_gps_to_enu_north(self):
        """测试向北移动，Y 坐标应该为正"""
        ref_lon, ref_lat = 121.5, 31.2
        x, y = gps_to_enu(121.5, 31.201, ref_lon, ref_lat)
        assert abs(x) < 1e-6, "经度不变 X 坐标应为 0"
        assert y > 0, "向北移动 Y 坐标应为正"

    def test_enu_to_gps_roundtrip(self):
        """测试 GPS -> ENU -> GPS 往返转换"""
        ref_lon, ref_lat = 121.5, 31.2
        original_lon, original_lat = 121.501, 31.201

        # GPS -> ENU
        x, y = gps_to_enu(original_lon, original_lat, ref_lon, ref_lat)

        # ENU -> GPS
        result_lon, result_lat = enu_to_gps(x, y, ref_lon, ref_lat)

        assert abs(result_lon - original_lon) < 1e-9, "往返转换经度应一致"
        assert abs(result_lat - original_lat) < 1e-9, "往返转换纬度应一致"

    def test_meters_per_degree_lon(self):
        """测试经度每度对应的米数"""
        # 赤道处约 111320 米
        m_equator = meters_per_degree_lon(0)
        assert abs(m_equator - 111320) < 1

        # 北纬 60 度处约 55660 米
        m_60n = meters_per_degree_lon(60)
        assert abs(m_60n - 55660) < 100

        # 北极处约 0 米
        m_90n = meters_per_degree_lon(90)
        assert abs(m_90n) < 1


class TestBoundaryConversion:
    """测试批量边界转换"""

    def test_convert_boundary_gps_to_enu(self):
        """测试批量 GPS 转 ENU"""
        ref_lon, ref_lat = 121.5, 31.2
        boundary_gps = [
            (121.5, 31.2),
            (121.501, 31.2),
            (121.501, 31.201),
            (121.5, 31.201),
        ]

        boundary_enu = convert_boundary_gps_to_enu(boundary_gps, ref_lon, ref_lat)

        assert len(boundary_enu) == 4, "转换后点数应一致"
        assert abs(boundary_enu[0][0]) < 1e-6, "第一个点 X 应为 0"
        assert abs(boundary_enu[0][1]) < 1e-6, "第一个点 Y 应为 0"

    def test_convert_boundary_enu_to_gps(self):
        """测试批量 ENU 转 GPS"""
        ref_lon, ref_lat = 121.5, 31.2
        boundary_enu = [
            (0, 0),
            (100, 0),
            (100, 100),
            (0, 100),
        ]

        boundary_gps = convert_boundary_enu_to_gps(boundary_enu, ref_lon, ref_lat)

        assert len(boundary_gps) == 4, "转换后点数应一致"
        assert abs(boundary_gps[0][0] - ref_lon) < 1e-9, "第一个点经度应为参考点经度"
        assert abs(boundary_gps[0][1] - ref_lat) < 1e-9, "第一个点纬度应为参考点纬度"

    def test_boundary_roundtrip(self):
        """测试边界往返转换"""
        ref_lon, ref_lat = 121.5, 31.2
        original_boundary = [
            (121.5, 31.2),
            (121.501, 31.2),
            (121.501, 31.201),
        ]

        # GPS -> ENU -> GPS
        boundary_enu = convert_boundary_gps_to_enu(original_boundary, ref_lon, ref_lat)
        result_boundary = convert_boundary_enu_to_gps(boundary_enu, ref_lon, ref_lat)

        for i, (orig, result) in enumerate(zip(original_boundary, result_boundary)):
            assert abs(orig[0] - result[0]) < 1e-9, f"第 {i} 个点经度应一致"
            assert abs(orig[1] - result[1]) < 1e-9, f"第 {i} 个点纬度应一致"


class TestGeometryCalculations:
    """测试几何计算功能"""

    def test_calculate_polygon_area_square(self):
        """测试正方形面积计算"""
        # 100m x 100m 正方形
        boundary = [
            (0, 0),
            (100, 0),
            (100, 100),
            (0, 100),
        ]
        area = calculate_polygon_area(boundary)
        assert abs(area - 10000) < 1e-6, "100m x 100m 正方形面积应为 10000 m²"

    def test_calculate_polygon_area_triangle(self):
        """测试三角形面积计算"""
        # 底 100m, 高 50m 三角形
        boundary = [
            (0, 0),
            (100, 0),
            (50, 50),
        ]
        area = calculate_polygon_area(boundary)
        expected = 0.5 * 100 * 50  # 2500 m²
        assert abs(area - expected) < 1e-6, "三角形面积计算错误"

    def test_calculate_polygon_area_clockwise_counterclockwise(self):
        """测试顺时针和逆时针方向的面积计算应一致"""
        boundary_ccw = [(0, 0), (100, 0), (100, 100), (0, 100)]
        boundary_cw = [(0, 0), (0, 100), (100, 100), (100, 0)]

        area_ccw = calculate_polygon_area(boundary_ccw)
        area_cw = calculate_polygon_area(boundary_cw)

        assert abs(area_ccw - area_cw) < 1e-6, "顺时针和逆时针面积应一致"

    def test_calculate_polygon_area_empty(self):
        """测试空边界面积"""
        assert calculate_polygon_area([]) == 0.0
        assert calculate_polygon_area([(0, 0)]) == 0.0
        assert calculate_polygon_area([(0, 0), (1, 1)]) == 0.0

    def test_calculate_perimeter_square(self):
        """测试正方形周长计算"""
        boundary = [
            (0, 0),
            (100, 0),
            (100, 100),
            (0, 100),
        ]
        perimeter = calculate_perimeter(boundary)
        assert abs(perimeter - 400) < 1e-6, "100m 正方形周长应为 400m"

    def test_calculate_perimeter_triangle(self):
        """测试三角形周长计算"""
        # 3-4-5 直角三角形（放大 10 倍）
        boundary = [
            (0, 0),
            (30, 0),
            (0, 40),
        ]
        perimeter = calculate_perimeter(boundary)
        expected = 30 + 40 + 50  # 120m
        assert abs(perimeter - expected) < 1e-6, "3-4-5 三角形周长计算错误"

    def test_calculate_perimeter_empty(self):
        """测试空边界周长"""
        assert calculate_perimeter([]) == 0.0
        assert calculate_perimeter([(0, 0)]) == 0.0


class TestValidation:
    """测试验证功能"""

    def test_validate_boundary_valid(self):
        """测试有效边界"""
        boundary = [(0, 0), (1, 0), (1, 1)]
        is_valid, error = validate_boundary(boundary)
        assert is_valid, "有效边界应通过验证"
        assert error == ""

    def test_validate_boundary_empty(self):
        """测试空边界"""
        is_valid, error = validate_boundary([])
        assert not is_valid, "空边界应无效"
        assert "空" in error

    def test_validate_boundary_insufficient_points(self):
        """测试点数不足"""
        boundary = [(0, 0), (1, 1)]
        is_valid, error = validate_boundary(boundary, min_points=3)
        assert not is_valid, "点数不足应无效"
        assert "点数不足" in error

    def test_validate_boundary_invalid_format(self):
        """测试格式错误"""
        boundary = [(0, 0), (1, 0), (2,)]  # 第三个点格式错误
        is_valid, error = validate_boundary(boundary)
        assert not is_valid, "格式错误应无效"
        assert "格式错误" in error

    def test_validate_boundary_nan(self):
        """测试 NaN 值"""
        boundary = [(0, 0), (float('nan'), 0), (1, 1)]
        is_valid, error = validate_boundary(boundary)
        assert not is_valid, "包含 NaN 应无效"
        assert "NaN" in error

    def test_validate_boundary_inf(self):
        """测试无穷大值"""
        boundary = [(0, 0), (float('inf'), 0), (1, 1)]
        is_valid, error = validate_boundary(boundary)
        assert not is_valid, "包含无穷大应无效"
        assert "无穷大" in error


class TestRealWorldScenarios:
    """测试真实场景"""

    def test_shanghai_farm_field(self):
        """测试上海地区农田地块（真实场景）"""
        # 上海地区某农田（约 100m x 200m）
        ref_lon, ref_lat = 121.5, 31.2

        # GPS 边界点（使用实际测量值）
        boundary_gps = [
            (121.5, 31.2),
            (121.5009, 31.2),  # 向东约 95m
            (121.5009, 31.2018),  # 向北约 200m
            (121.5, 31.2018),
        ]

        # 转换为 ENU
        boundary_enu = convert_boundary_gps_to_enu(boundary_gps, ref_lon, ref_lat)

        # 计算面积（约 95m x 200m = 19000 m²）
        area = calculate_polygon_area(boundary_enu)
        assert 16000 < area < 18000, f"面积应接近 17000 m²，实际 {area} m²"

        # 计算周长（约 2 * (95 + 200) = 590m）
        perimeter = calculate_perimeter(boundary_enu)
        assert 560 < perimeter < 620, f"周长应接近 590m，实际 {perimeter} m"

    def test_complex_polygon_with_holes(self):
        """测试带孔洞的复杂多边形"""
        # 外边界（正方形 200m x 200m）
        outer = [
            (0, 0),
            (200, 0),
            (200, 200),
            (0, 200),
        ]

        # 内孔洞（正方形 50m x 50m，中心位置）
        hole = [
            (75, 75),
            (125, 75),
            (125, 125),
            (75, 125),
        ]

        outer_area = calculate_polygon_area(outer)
        hole_area = calculate_polygon_area(hole)
        effective_area = outer_area - hole_area

        assert abs(outer_area - 40000) < 1e-6, "外边界面积应为 40000 m²"
        assert abs(hole_area - 2500) < 1e-6, "孔洞面积应为 2500 m²"
        assert abs(effective_area - 37500) < 1e-6, "有效面积应为 37500 m²"


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
