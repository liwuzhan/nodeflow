#!/usr/bin/env python3
"""
测试实时更新功能 - 模拟连续接收 pose 数据
"""

import time
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from web_server import start_web_server, update_trajectory_data

def test_realtime_update():
    print("=" * 70)
    print("实时更新测试 - 模拟轨迹点逐个到达")
    print("=" * 70)

    # 启动 Web 服务器
    print("\n1. 启动 Web 服务器...")
    start_web_server(host='127.0.0.1', port=8080)
    time.sleep(1)

    # 设置静态数据
    field_boundary = [(0, 0), (100, 0), (100, 100), (0, 100)]
    planned_path = [(10 + i*5, 50) for i in range(18)]  # 水平直线

    print("\n2. 推送初始数据（地块和规划路径）...")
    update_trajectory_data(
        field_boundary=field_boundary,
        planned_path=planned_path,
        actual_trajectory=[(10, 50)],
        actual_trajectory_with_heading=[(10, 50, 0.0)],
        metrics={"planned_distance_m": 85.0}
    )

    print(f"\n3. 模拟轨迹点逐个到达（每 0.5 秒一个点）...")
    print(f"   🌐 在浏览器中打开: http://127.0.0.1:8080")
    print(f"   观察轨迹是否平滑实时更新\n")

    # 模拟轨迹点逐个到达
    actual_trajectory = [(10, 50)]
    actual_trajectory_with_heading = [(10, 50, 0.0)]  # (x, y, theta)

    for i in range(1, 18):
        time.sleep(0.5)  # 每 0.5 秒一个点

        # 添加新点（带一点偏差）
        x = 10 + i * 5
        y = 50 + (i % 3 - 1) * 2  # 上下波动
        theta = 0.0  # 水平向右（东向）

        actual_trajectory.append((x, y))
        actual_trajectory_with_heading.append((x, y, theta))

        # 立即推送更新
        update_trajectory_data(
            field_boundary=field_boundary,
            planned_path=planned_path,
            actual_trajectory=actual_trajectory.copy(),
            actual_trajectory_with_heading=actual_trajectory_with_heading.copy(),
            metrics={
                "planned_distance_m": 85.0,
                "actual_distance_m": i * 5,
                "trajectory_points": len(actual_trajectory)
            }
        )

        print(f"   ✓ 点 {i+1}/18: ({x:.1f}, {y:.1f})")

    print(f"\n4. 完成！轨迹包含 {len(actual_trajectory)} 个点")
    print(f"   如果看到平滑的实时更新（而非跳跃），说明功能正常 ✅")

    print("\n按 Ctrl+C 退出...")
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n\n测试结束")

if __name__ == "__main__":
    test_realtime_update()
