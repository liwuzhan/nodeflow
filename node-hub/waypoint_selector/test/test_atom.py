"""
waypoint_selector 的 L4 原子层单元测试

测试核心算法逻辑，无需 SDK，极快执行
"""

import sys
from pathlib import Path
import importlib.util

# 添加父目录到路径
node_dir = Path(__file__).parent.parent
sys.path.insert(0, str(node_dir))

spec = importlib.util.spec_from_file_location("waypoint_selector_atom", node_dir / "atom.py")
waypoint_atom = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(waypoint_atom)

WaypointSelector = waypoint_atom.WaypointSelector
ViewConfig = waypoint_atom.ViewConfig
import math


def test_basic_straight_path():
    """测试1: 基础直线路径跟踪"""
    print("\n=== 测试1: 直线路径跟踪 ===")

    # 使用较大的 initial_check_points 以覆盖整条路径
    config = ViewConfig(
        view_distance=3.0,
        view_width=4.0,
        view_depth=1.5,
        goal_tolerance=1.5,
        initial_check_points=50,  # 足够覆盖路径上的所有点
        initial_consume_distance=2.0
    )
    selector = WaypointSelector(config)

    # 创建一条从 (0,0) 到 (100,0) 的直线路径
    path = [(float(i), 0.0) for i in range(0, 101, 5)]  # 21个点，间隔5m
    path_data = {"path": path, "task_id": "test1"}

    # 测试1.1: 车辆在起点，设置路径时传递初始位置
    initial_pose = {"x": 0.0, "y": 0.0}
    info = selector.set_path(path_data, initial_pose=initial_pose)
    assert info["count"] == 21, f"路径点数错误: {info['count']}"
    print(f"✓ 路径设置成功: {info['count']} 个点, 初始消费: {info['initial_consumed']} 个")

    pose = {"x": 0.0, "y": 0.0, "theta": 0.0}  # 东向
    result = selector.select(pose)

    assert result is not None
    assert result["mode"] in ["tracking", "approach"]
    assert result["final"] == False
    print(f"✓ 起点选择: ({result['x']:.1f}, {result['y']:.1f}), 模式={result['mode']}")

    # 测试1.2: 重新设置路径，车辆在中点 (应消费前11个点: 0-50m)
    selector2 = WaypointSelector(config)
    initial_pose2 = {"x": 50.0, "y": 0.0}
    info2 = selector2.set_path(path_data, initial_pose=initial_pose2)
    print(f"  车辆在(50,0): 初始消费 {info2['initial_consumed']} 个点")

    pose = {"x": 50.0, "y": 0.0, "theta": 0.0}
    result = selector2.select(pose)

    assert result is not None
    assert result["x"] >= 50.0, f"前瞻点应该在车辆前方，实际: ({result['x']:.1f}, {result['y']:.1f})"
    print(f"✓ 中点选择: ({result['x']:.1f}, {result['y']:.1f}), 消费={result['consumed']}/{result['total']}")

    # 测试1.3: 重新设置路径，车辆到达终点附近
    selector3 = WaypointSelector(config)
    initial_pose3 = {"x": 100.0, "y": 0.0}
    selector3.set_path(path_data, initial_pose=initial_pose3)

    pose = {"x": 100.0, "y": 0.0, "theta": 0.0}
    result = selector3.select(pose)

    assert result["x"] == 100.0, "应该输出终点"
    print(f"✓ 终点选择: ({result['x']:.1f}, {result['y']:.1f}), final={result['final']}")


def test_view_rectangle_detection():
    """测试2: 视野矩形检测"""
    print("\n=== 测试2: 视野矩形检测 ===")

    # 测试车辆东向 (theta=0)
    vx, vy, theta = 0.0, 0.0, 0.0
    view_distance = 3.0
    view_width = 4.0
    view_depth = 1.5

    # 测试点1: 视野中心 (应该在视野内)
    px, py = 3.0, 0.0
    result = WaypointSelector.point_in_view_rectangle(
        px, py, vx, vy, theta, view_distance, view_width, view_depth
    )
    assert result == True, "视野中心应该在视野内"
    print(f"✓ 点 ({px}, {py}) 在视野内")

    # 测试点2: 视野左边界 (应该在视野内)
    px, py = 3.0, -2.0  # view_width/2 = 2.0
    result = WaypointSelector.point_in_view_rectangle(
        px, py, vx, vy, theta, view_distance, view_width, view_depth
    )
    assert result == True, "左边界应该在视野内"
    print(f"✓ 点 ({px}, {py}) 在视野内")

    # 测试点3: 视野外 (太远)
    px, py = 10.0, 0.0
    result = WaypointSelector.point_in_view_rectangle(
        px, py, vx, vy, theta, view_distance, view_width, view_depth
    )
    assert result == False, "远点应该不在视野内"
    print(f"✓ 点 ({px}, {py}) 不在视野内 (距离太远)")

    # 测试点4: 车辆后方 (应该不在视野内)
    px, py = -1.0, 0.0
    result = WaypointSelector.point_in_view_rectangle(
        px, py, vx, vy, theta, view_distance, view_width, view_depth
    )
    assert result == False, "后方点应该不在视野内"
    print(f"✓ 点 ({px}, {py}) 不在视野内 (在后方)")


def test_rotated_view():
    """测试3: 旋转视野 (北向车辆)"""
    print("\n=== 测试3: 旋转视野测试 ===")

    # 车辆北向 (theta = π/2)
    vx, vy = 0.0, 0.0
    theta = math.pi / 2  # 90度，北向

    view_distance = 3.0
    view_width = 4.0
    view_depth = 1.5

    # 测试点1: 北方 3m 处 (应该在视野内)
    px, py = 0.0, 3.0
    result = WaypointSelector.point_in_view_rectangle(
        px, py, vx, vy, theta, view_distance, view_width, view_depth
    )
    assert result == True, "北向车辆的视野中心应该在北方"
    print(f"✓ 北向车辆: 点 ({px}, {py}) 在视野内")

    # 测试点2: 东方 3m 处 (应该不在视野内)
    px, py = 3.0, 0.0
    result = WaypointSelector.point_in_view_rectangle(
        px, py, vx, vy, theta, view_distance, view_width, view_depth
    )
    assert result == False, "东方应该不在北向车辆视野内"
    print(f"✓ 北向车辆: 点 ({px}, {py}) 不在视野内")


def test_path_consumption():
    """测试4: 路径点消费逻辑"""
    print("\n=== 测试4: 路径点消费测试 ===")

    config = ViewConfig(
        view_distance=3.0,
        view_width=4.0,
        view_depth=1.5,
        goal_tolerance=1.5,
        initial_check_points=10,
        initial_consume_distance=2.0
    )

    # 创建短路径
    path = [(0.0, 0.0), (5.0, 0.0), (10.0, 0.0), (15.0, 0.0)]
    path_data = {"path": path, "task_id": "test4"}

    # 车辆从起点移动到终点，每次重新设置路径
    positions = [(0.0, 0.0), (5.0, 0.0), (10.0, 0.0), (15.0, 0.0)]
    results = []

    for px, py in positions:
        selector = WaypointSelector(config)
        initial_pose = {"x": px, "y": py}
        selector.set_path(path_data, initial_pose=initial_pose)

        pose = {"x": px, "y": py, "theta": 0.0}
        result = selector.select(pose)
        results.append(result)
        print(
            f"  位置 ({px:.1f}, {py:.1f}): "
            f"前瞻点=({result['x']:.1f}, {result['y']:.1f}), "
            f"已消费={result['consumed']}/{result['total']}, "
            f"final={result['final']}"
        )

    # 最终应该到达终点
    assert results[-1]["x"] == 15.0, "最终应该输出终点"
    assert results[-1]["final"] == True, "最终应该标记为完成"
    print(f"✓ 路径点正确消费")


def test_initial_consume():
    """测试5: 初始消费逻辑"""
    print("\n=== 测试5: 初始消费测试 ===")

    config = ViewConfig(
        view_distance=3.0,
        view_width=4.0,
        view_depth=1.5,
        goal_tolerance=1.5,
        initial_check_points=10,
        initial_consume_distance=2.0
    )

    # 创建短路径
    path = [(0.0, 0.0), (1.0, 0.0), (2.0, 0.0), (5.0, 0.0), (10.0, 0.0)]
    path_data = {"path": path, "task_id": "test5"}

    # 情况1: 初始位置在起点 (最近点是(0,0)，距离=0 < 2m，消费1点)
    selector1 = WaypointSelector(config)
    initial_pose = {"x": 0.0, "y": 0.0}
    info = selector1.set_path(path_data, initial_pose=initial_pose)

    assert info["initial_consumed"] == 1, f"应消费1个点(最近点)，实际消费{info['initial_consumed']}个"
    print(f"✓ 初始位置 (0, 0): 消费了 {info['initial_consumed']} 个点")

    # 情况2: 初始位置在路径中间 (最近点是(5,0)，应消费4点)
    selector2 = WaypointSelector(config)
    path_data2 = {"path": path, "task_id": "test5b"}
    initial_pose2 = {"x": 5.0, "y": 0.0}
    info2 = selector2.set_path(path_data2, initial_pose=initial_pose2)

    assert info2["initial_consumed"] == 4, f"应消费4个点，实际消费{info2['initial_consumed']}个"
    print(f"✓ 初始位置 (5, 0): 消费了 {info2['initial_consumed']} 个点")

    # 情况3: 初始位置远离起点 (最近点距离 > 2m)
    selector3 = WaypointSelector(config)
    path_data3 = {"path": path, "task_id": "test5c"}
    initial_pose3 = {"x": -10.0, "y": 0.0}  # 远离起点
    info3 = selector3.set_path(path_data3, initial_pose=initial_pose3)

    assert info3["initial_consumed"] == 0, f"不应消费任何点，实际消费{info3['initial_consumed']}个"
    print(f"✓ 初始位置 (-10, 0): 消费了 {info3['initial_consumed']} 个点")

    # 情况4: 不传初始位置 (不应消费)
    selector4 = WaypointSelector(config)
    path_data4 = {"path": path, "task_id": "test5d"}
    info4 = selector4.set_path(path_data4)  # 无 initial_pose

    assert info4["initial_consumed"] == 0, f"不应消费任何点，实际消费{info4['initial_consumed']}个"
    print(f"✓ 无初始位置: 消费了 {info4['initial_consumed']} 个点")


def test_u_turn():
    """测试6: U型弯道"""
    print("\n=== 测试6: U型弯道测试 ===")

    config = ViewConfig(
        view_distance=3.0,
        view_width=4.0,
        view_depth=1.5,
        goal_tolerance=1.5
    )
    selector = WaypointSelector(config)

    # 创建U型路径: 向东 -> 向北 -> 向西
    path = [
        (0.0, 0.0), (5.0, 0.0), (10.0, 0.0),  # 向东
        (10.0, 5.0), (10.0, 10.0),              # 向北
        (5.0, 10.0), (0.0, 10.0)                # 向西
    ]
    path_data = {"path": path, "task_id": "test5"}
    selector.set_path(path_data)

    # 模拟车辆沿路径运动
    test_poses = [
        {"x": 0.0, "y": 0.0, "theta": 0.0},          # 起点，东向
        {"x": 10.0, "y": 0.0, "theta": 0.0},         # 东段终点
        {"x": 10.0, "y": 5.0, "theta": math.pi/2},   # 转弯中，北向
        {"x": 10.0, "y": 10.0, "theta": math.pi/2},  # 北段终点
        {"x": 5.0, "y": 10.0, "theta": math.pi},     # 转弯后，西向
        {"x": 0.0, "y": 10.0, "theta": math.pi}      # 终点
    ]

    for i, pose in enumerate(test_poses):
        result = selector.select(pose)
        print(
            f"  位置{i+1} ({pose['x']:.1f}, {pose['y']:.1f}, θ={math.degrees(pose['theta']):.0f}°): "
            f"前瞻=({result['x']:.1f}, {result['y']:.1f}), "
            f"视野内={result['in_view_count']}, "
            f"模式={result['mode']}"
        )

    print(f"✓ U型弯道测试完成")


def test_upcoming_turn_preview():
    """测试7: 前方急转弯预判"""
    print("\n=== 测试7: 前方急转弯预判 ===")

    config = ViewConfig(
        view_distance=2.0,
        view_width=4.0,
        view_depth=1.5,
        turn_preview_distance=8.0
    )
    selector = WaypointSelector(config)

    path = [
        (0.0, 0.0), (1.0, 0.0), (2.0, 0.0), (3.0, 0.0),
        (3.0, 1.0), (3.0, 2.0), (3.0, 3.0),
    ]
    selector.set_path({"path": path, "task_id": "turn_preview"})

    result = selector.select({"x": 0.0, "y": 0.0, "theta": 0.0})

    assert result["upcoming_turn_angle_deg"] >= 80.0
    assert result["upcoming_turn_distance"] > 0.0
    print(
        f"✓ 预判转角: {result['upcoming_turn_angle_deg']:.1f}°, "
        f"距离={result['upcoming_turn_distance']:.1f}m"
    )


def test_sync_progress_advances_consumed_index():
    """测试8: 外部路径进度可以纠正落后的已消费索引"""
    print("\n=== 测试8: 路径进度同步 ===")

    selector = WaypointSelector(ViewConfig())
    path = [(float(i), 0.0) for i in range(10)]
    selector.set_path({"path": path, "task_id": "progress_task"})

    synced = selector.sync_progress({
        "task_id": "progress_task",
        "path_index": 5,
        "segment_fraction": 0.4,
        "cross_track_error_m": 0.2,
    })
    assert selector.state.first_unconsumed_idx == 6
    result = selector.select({"x": 5.2, "y": 0.0, "theta": 0.0})

    assert synced is True
    assert result["consumed"] >= 6
    assert result["index"] >= 6
    print(f"✓ 同步后已消费索引: {result['consumed']}")


def test_sync_progress_ignores_backward_or_untrusted_updates():
    """测试9: 外部路径进度只允许可信的单调前进修正"""
    print("\n=== 测试9: 路径进度同步保护 ===")

    selector = WaypointSelector(ViewConfig(progress_sync_max_cross_track_m=2.0))
    path = [(float(i), 0.0) for i in range(10)]
    selector.set_path({"path": path, "task_id": "progress_guard"})

    assert selector.sync_progress({
        "task_id": "progress_guard",
        "path_index": 4,
        "segment_fraction": 0.5,
        "cross_track_error_m": 0.1,
    })
    assert selector.state.first_unconsumed_idx == 5

    assert not selector.sync_progress({
        "task_id": "progress_guard",
        "path_index": 2,
        "segment_fraction": 0.5,
        "cross_track_error_m": 0.1,
    })
    assert selector.state.first_unconsumed_idx == 5

    assert not selector.sync_progress({
        "task_id": "progress_guard",
        "path_index": 8,
        "segment_fraction": 0.5,
        "cross_track_error_m": 3.0,
    })
    assert selector.state.first_unconsumed_idx == 5
    print("✓ 单调前进和横向误差保护通过")


def run_all_tests():
    """运行所有测试"""
    print("=" * 60)
    print("waypoint_selector L4 原子层单元测试")
    print("=" * 60)

    try:
        test_basic_straight_path()
        test_view_rectangle_detection()
        test_rotated_view()
        test_path_consumption()
        test_initial_consume()
        test_u_turn()
        test_upcoming_turn_preview()
        test_sync_progress_advances_consumed_index()
        test_sync_progress_ignores_backward_or_untrusted_updates()

        print("\n" + "=" * 60)
        print("✅ 所有测试通过!")
        print("=" * 60)
        return True

    except AssertionError as e:
        print(f"\n❌ 测试失败: {e}")
        return False
    except Exception as e:
        print(f"\n❌ 异常: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1)
