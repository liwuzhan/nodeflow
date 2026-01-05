#!/usr/bin/env python3
"""
轨迹可视化 Web 版本测试脚本

测试步骤：
1. 启动 Web 服务器
2. 推送测试数据
3. 在浏览器中查看 http://localhost:5000
"""

import time
import sys
import math
from pathlib import Path

# 添加项目路径
sys.path.insert(0, str(Path(__file__).parent))

from web_server import start_web_server, update_trajectory_data

def main():
    print("=" * 70)
    print("轨迹可视化 Web 版本 - 测试脚本")
    print("=" * 70)

    # 启动 Web 服务器
    print("\n1. 启动 Web 服务器...")
    start_web_server(host='127.0.0.1', port=5000)

    # 等待服务器启动
    time.sleep(2)

    print("\n2. 推送测试数据...")

    # 模拟地块边界（矩形）
    field_boundary = [
        (0, 0),
        (100, 0),
        (100, 80),
        (0, 80)
    ]

    # 模拟规划路径（往复式3趟）
    planned_path = [
        # 第一趟（从左到右）
        (10, 10), (20, 10), (30, 10), (40, 10), (50, 10),
        (60, 10), (70, 10), (80, 10), (90, 10),
        # 转弯
        (90, 30),
        # 第二趟（从右到左）
        (90, 30), (80, 30), (70, 30), (60, 30), (50, 30),
        (40, 30), (30, 30), (20, 30), (10, 30),
        # 转弯
        (10, 50),
        # 第三趟（从左到右）
        (10, 50), (20, 50), (30, 50), (40, 50), (50, 50),
        (60, 50), (70, 50), (80, 50), (90, 50),
    ]

    # 模拟实际轨迹（带一些偏差）
    actual_trajectory = [
        # 第一趟（稍微偏离规划路径）
        (10, 11), (20, 10.5), (30, 11.5), (40, 10.2), (50, 11.8),
        (60, 10.5), (70, 11.2), (80, 10.8), (90, 11.5),
        # 转弯
        (90, 28),
        # 第二趟
        (90, 29), (80, 30.5), (70, 29.5), (60, 30.8), (50, 29.2),
        (40, 30.5), (30, 29.8), (20, 30.2), (10, 29.5),
        # 转弯
        (10, 48),
        # 第三趟
        (10, 49), (20, 50.5), (30, 49.5), (40, 50.2), (50, 49.8),
        (60, 50.5), (70, 49.2), (80, 50.8), (90, 49.5),
    ]

    # 为每个点添加航向角（模拟）
    actual_trajectory_with_heading = []
    for i, (x, y) in enumerate(actual_trajectory):
        # 简单估算航向角：根据前后点计算
        if i < len(actual_trajectory) - 1:
            next_x, next_y = actual_trajectory[i + 1]
            theta = math.atan2(next_y - y, next_x - x)
        else:
            theta = 0.0
        actual_trajectory_with_heading.append((x, y, theta))

    # 计算简单的统计指标
    metrics = {
        "planned_distance_m": 280.0,
        "actual_distance_m": 275.5,
        "distance_error_m": 4.5,
        "distance_error_percent": 1.6,
        "avg_lateral_error_m": 1.2,
        "max_lateral_error_m": 2.5,
        "trajectory_points": len(actual_trajectory)
    }

    # 推送数据到 Web 客户端
    update_trajectory_data(
        field_boundary=field_boundary,
        planned_path=planned_path,
        actual_trajectory=actual_trajectory,
        actual_trajectory_with_heading=actual_trajectory_with_heading,
        metrics=metrics
    )

    print("\n✅ 测试数据已推送")
    print("\n" + "=" * 70)
    print("🌐 请在浏览器中打开: http://localhost:5000")
    print("=" * 70)
    print("\n按 Ctrl+C 退出...")

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n\n测试结束")

if __name__ == "__main__":
    main()
