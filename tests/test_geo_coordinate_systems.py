#!/usr/bin/env python3
"""
测试地理坐标工具的坐标系转换
"""

import math
import sys
from pathlib import Path

# 添加项目根路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

# 从coord_transform/utils导入geo工具
sys.path.insert(0, str(project_root / 'node-hub' / 'coord_transform'))
from utils.geo import (
    bearing_geo,
    bearing_math,
    heading_geo_to_math,
    heading_math_to_geo,
    normalize_heading_deg,
    normalize_angle_rad,
)


def test_bearing_functions():
    """测试方位角计算函数"""
    print("\n=== 测试方位角计算 ===\n")

    # 测试点：起点在原点附近，目标在不同方向
    origin_lon, origin_lat = 121.5, 31.2

    test_cases = [
        # (方向, 目标lon, 目标lat, 期望地理方位角度, 容差)
        ("正北", origin_lon, origin_lat + 0.01, 0.0, 1.0),
        ("正东", origin_lon + 0.01, origin_lat, 90.0, 1.0),
        ("正南", origin_lon, origin_lat - 0.01, 180.0, 1.0),
        ("正西", origin_lon - 0.01, origin_lat, 270.0, 1.0),
        ("东北45°", origin_lon + 0.01, origin_lat + 0.01, 45.0, 5.0),   # 球面几何误差
        ("东南135°", origin_lon + 0.01, origin_lat - 0.01, 135.0, 5.0), # 球面几何误差
        ("西南225°", origin_lon - 0.01, origin_lat - 0.01, 225.0, 5.0), # 球面几何误差
        ("西北315°", origin_lon - 0.01, origin_lat + 0.01, 315.0, 5.0), # 球面几何误差
    ]

    all_passed = True
    for direction, target_lon, target_lat, expected_deg, tolerance in test_cases:
        # 地理坐标系方位角
        geo_deg = bearing_geo(origin_lon, origin_lat, target_lon, target_lat)

        # 数学坐标系方位角
        math_rad = bearing_math(origin_lon, origin_lat, target_lon, target_lat)

        # 转换验证
        geo_from_math = heading_math_to_geo(math_rad)
        math_from_geo = heading_geo_to_math(geo_deg)

        # 允许小误差（由于浮点运算和球面几何）
        error = abs(geo_deg - expected_deg)
        if error > 180:
            error = 360 - error

        passed = error < tolerance
        all_passed = all_passed and passed

        status = "✓" if passed else "✗"
        print(f"{status} {direction:10s}: geo={geo_deg:6.1f}° (期望 {expected_deg:5.1f}°, 容差±{tolerance:.0f}°), "
              f"math={math.degrees(math_rad):6.1f}° (rad), "
              f"转换一致={abs(geo_deg - geo_from_math) < 0.1}")

    return all_passed


def test_coordinate_conversion():
    """测试坐标系转换"""
    print("\n=== 测试坐标系转换 ===\n")

    test_cases = [
        # (地理坐标系度, 期望数学坐标系弧度)
        (0.0, math.pi/2),      # 北 → +Y
        (90.0, 0.0),           # 东 → +X
        (180.0, -math.pi/2),   # 南 → -Y
        (270.0, math.pi),      # 西 → -X (或 +π)
        (45.0, math.pi/4),     # 东北
        (135.0, -math.pi/4),   # 东南
    ]

    all_passed = True
    for geo_deg, expected_math_rad in test_cases:
        # 地理 → 数学
        math_rad = heading_geo_to_math(geo_deg)

        # 数学 → 地理
        geo_back = heading_math_to_geo(math_rad)

        # 验证往返转换
        tolerance = 0.01  # 弧度
        error = abs(normalize_angle_rad(math_rad - expected_math_rad))
        passed = error < tolerance and abs(geo_back - geo_deg) < 0.1

        all_passed = all_passed and passed
        status = "✓" if passed else "✗"

        print(f"{status} geo {geo_deg:5.0f}° → math {math.degrees(math_rad):6.1f}° "
              f"(期望 {math.degrees(expected_math_rad):6.1f}°), "
              f"往返 {geo_back:5.1f}°")

    return all_passed


def test_normalization():
    """测试角度归一化"""
    print("\n=== 测试角度归一化 ===\n")

    test_cases = [
        # (输入, 期望输出)
        (0.0, 0.0),
        (180.0, 180.0),
        (360.0, 0.0),
        (450.0, 90.0),
        (-90.0, 270.0),
        (-180.0, 180.0),
        (720.0, 0.0),
    ]

    all_passed = True
    for input_deg, expected_deg in test_cases:
        output_deg = normalize_heading_deg(input_deg)
        passed = abs(output_deg - expected_deg) < 0.1
        all_passed = all_passed and passed
        status = "✓" if passed else "✗"
        print(f"{status} {input_deg:6.0f}° → {output_deg:5.1f}° (期望 {expected_deg:5.1f}°)")

    return all_passed


def test_heading_error_calculation():
    """测试航向误差计算（用于控制器）"""
    print("\n=== 测试航向误差计算 ===\n")

    test_cases = [
        # (当前heading, 目标bearing, 期望误差, 说明)
        (0.0, 10.0, 10.0, "需要右转10°"),
        (350.0, 10.0, 20.0, "跨越0°边界右转20°"),
        (10.0, 350.0, -20.0, "跨越0°边界左转20°"),
        (90.0, 270.0, 180.0, "右转180°（或左转180°，等效）"),
        # 注意：180° 的归一化可能是 +180 或 -180，两者等效
    ]

    def normalize_error(error_deg):
        """归一化误差到 (-180, 180]"""
        while error_deg > 180.0:
            error_deg -= 360.0
        while error_deg <= -180.0:
            error_deg += 360.0
        return error_deg

    all_passed = True
    for current, target, expected_error, desc in test_cases:
        error = normalize_error(target - current)
        passed = abs(error - expected_error) < 0.1
        all_passed = all_passed and passed
        status = "✓" if passed else "✗"

        # 角速度符号（仿真器坐标系）
        angular_velocity_sign = "-" if error > 0 else "+"

        print(f"{status} {desc:25s}: 当前={current:5.0f}°, 目标={target:5.0f}°, "
              f"误差={error:6.1f}° (期望 {expected_error:6.1f}°), "
              f"角速度符号={angular_velocity_sign}")

    return all_passed


def main():
    """运行所有测试"""
    print("=" * 70)
    print("地理坐标系工具函数测试")
    print("=" * 70)

    results = []

    results.append(("方位角计算", test_bearing_functions()))
    results.append(("坐标系转换", test_coordinate_conversion()))
    results.append(("角度归一化", test_normalization()))
    results.append(("航向误差计算", test_heading_error_calculation()))

    print("\n" + "=" * 70)
    print("测试结果汇总")
    print("=" * 70)

    all_passed = True
    for test_name, passed in results:
        status = "✅ PASS" if passed else "❌ FAIL"
        all_passed = all_passed and passed
        print(f"{status} - {test_name}")

    print("=" * 70)

    if all_passed:
        print("\n✅ 所有测试通过！")
        return 0
    else:
        print("\n❌ 部分测试失败！")
        return 1


if __name__ == "__main__":
    sys.exit(main())
