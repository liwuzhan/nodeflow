#!/usr/bin/env python3
"""
测试 trajectory_loader 的原子层函数
"""

import sys
from pathlib import Path

# 添加父目录到路径
sys.path.insert(0, str(Path(__file__).parent.parent))

from edge.nodes.planning.trajectory_loader import atom


def test_wgs84_to_enu():
    """测试 WGS84 到 ENU 坐标转换"""
    print("=" * 60)
    print("测试 WGS84 → ENU 坐标转换")
    print("=" * 60)

    # 参考点（北京天安门）
    ref_lon = 116.397128
    ref_lat = 39.916527

    # 测试点（向东 100 米，向北 100 米）
    # 约 100m east = 0.00112 度经度，100m north = 0.0009 度纬度
    test_lon = ref_lon + 0.00112
    test_lat = ref_lat + 0.0009

    x, y = atom.wgs84_to_enu(test_lon, test_lat, ref_lon, ref_lat)

    print(f"参考点: ({ref_lon}, {ref_lat})")
    print(f"测试点: ({test_lon}, {test_lat})")
    print(f"ENU坐标: ({x:.2f}, {y:.2f}) 米")
    print(f"预期约: (100, 100) 米")
    print()

    # 验证精度
    assert abs(x - 100) < 5, f"X坐标误差过大: {x}"
    assert abs(y - 100) < 5, f"Y坐标误差过大: {y}"
    print("✓ 坐标转换测试通过")
    print()


def test_convert_to_enu_path():
    """测试批量坐标转换"""
    print("=" * 60)
    print("测试批量 WGS84 → ENU 转换")
    print("=" * 60)

    # 模拟轨迹点
    points = [
        {'lat': 39.916527, 'lon': 116.397128, 'alt': 50, 'heading': 90, 'timestamp': 1000},
        {'lat': 39.916627, 'lon': 116.397228, 'alt': 50, 'heading': 90, 'timestamp': 1001},
        {'lat': 39.916727, 'lon': 116.397328, 'alt': 50, 'heading': 90, 'timestamp': 1002},
    ]

    ref_lon, ref_lat = atom.compute_ref_point(points)
    print(f"自动参考点: ({ref_lon}, {ref_lat})")

    enu_path, zones = atom.convert_to_enu_path(points, ref_lon, ref_lat)
    print(f"转换得到 {len(enu_path)} 个ENU点:")
    for i, (x, y) in enumerate(enu_path):
        print(f"  点 {i}: ({x:.2f}, {y:.2f}) 米")
    print()

    # 第一个点应该在原点
    assert abs(enu_path[0][0]) < 0.1, "起点X坐标应该接近0"
    assert abs(enu_path[0][1]) < 0.1, "起点Y坐标应该接近0"
    assert zones == ["", "", ""]
    print("✓ 批量转换测试通过")
    print()


def test_compute_path_length():
    """测试路径长度计算"""
    print("=" * 60)
    print("测试路径长度计算")
    print("=" * 60)

    # 构造一个简单路径：正方形
    enu_path = [
        (0, 0),
        (10, 0),
        (10, 10),
        (0, 10),
        (0, 0),
    ]

    length = atom.compute_path_length(enu_path)
    print(f"正方形路径总长: {length:.2f} 米")
    print(f"预期: 40 米")
    print()

    assert abs(length - 40) < 0.1, f"路径长度误差过大: {length}"
    print("✓ 路径长度计算测试通过")
    print()


def test_build_global_path():
    """测试构建 global_path 消息"""
    print("=" * 60)
    print("测试 global_path 消息构建")
    print("=" * 60)

    enu_path = [(0, 0), (10, 0), (10, 10)]
    task_id = "test_task_001"

    msg = atom.build_global_path(enu_path, task_id)

    print("构建的消息:")
    print(f"  task_id: {msg['task_id']}")
    print(f"  status: {msg['status']}")
    print(f"  message: {msg['message']}")
    print(f"  path: {len(msg['path'])} 个点")
    print()

    assert msg['task_id'] == task_id
    assert msg['status'] == 'success'
    assert len(msg['path']) == 3
    print("✓ global_path 构建测试通过")
    print()


def test_build_operation_plan_from_loaded_path():
    """测试从加载路径构建 operation_plan"""
    enu_path = [(0, 0), (5, 0), (10, 0), (10, 5), (10, 10)]
    plan = atom.build_operation_plan(
        enu_path,
        "test_task_plan",
        turn_angle_threshold_deg=45.0,
        turn_zone_radius_m=1.0,
    )

    assert plan["task_id"] == "test_task_plan"
    assert len(plan["path_zones"]) == len(enu_path)
    assert plan["segments"]
    assert any(segment["type"] == "work" for segment in plan["segments"])
    assert any(segment["type"] == "headland_turn" for segment in plan["segments"])
    print("✓ operation_plan 构建测试通过")
    print()


def test_build_task_enu():
    """测试构建 task_enu 消息"""
    print("=" * 60)
    print("测试 task_enu 消息构建")
    print("=" * 60)

    ref_lon = 116.397128
    ref_lat = 39.916527
    task_id = "test_task_002"

    msg = atom.build_task_enu(ref_lon, ref_lat, task_id)

    print("构建的消息:")
    print(f"  id: {msg['id']}")
    print(f"  ref_lon: {msg['ref_lon']}")
    print(f"  ref_lat: {msg['ref_lat']}")
    print()

    assert msg['id'] == task_id
    assert msg['ref_lon'] == ref_lon
    assert msg['ref_lat'] == ref_lat
    print("✓ task_enu 构建测试通过")
    print()


def main():
    """运行所有测试"""
    print("\n" + "=" * 60)
    print("trajectory_loader atom.py 单元测试")
    print("=" * 60 + "\n")

    test_wgs84_to_enu()
    test_convert_to_enu_path()
    test_compute_path_length()
    test_build_global_path()
    test_build_operation_plan_from_loaded_path()
    test_build_task_enu()

    print("=" * 60)
    print("✅ 所有测试通过！")
    print("=" * 60)


if __name__ == "__main__":
    main()
