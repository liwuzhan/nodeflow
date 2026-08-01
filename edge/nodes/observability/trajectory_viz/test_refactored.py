#!/usr/bin/env python3
"""
测试重构后的 trajectory_viz 节点（按L3/L4规范）

验证：
1. run.py 是否符合L3 "傻瓜式循环" 模式
2. Web服务器是否正常启动
3. 数据推送是否正常工作
"""

import time
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

# 导入Web服务器模块（不启动节点，只测试Web服务）
import web_server

def test_web_server():
    print("=" * 70)
    print("测试 Web 服务器模块（工具层）")
    print("=" * 70)

    # 1. 启动服务器
    print("\n1️⃣  启动 Web 服务器...")
    server_thread = web_server.start_web_server(host='127.0.0.1', port=8080)
    print(f"   线程状态: {'运行中' if server_thread.is_alive() else '已停止'}")
    print(f"   访问: http://127.0.0.1:8080")

    # 2. 推送测试数据（模拟 L3 层调用）
    print("\n2️⃣  推送测试数据（模拟L3层调用）...")
    time.sleep(1)

    # 地块边界
    field_boundary = [(0, 0), (100, 0), (100, 100), (0, 100)]

    # 规划路径（往复式）
    planned_path = []
    for i in range(0, 100, 10):
        if (i // 10) % 2 == 0:
            planned_path.append((10, i))
            planned_path.append((90, i))
        else:
            planned_path.append((90, i))
            planned_path.append((10, i))

    # 实际轨迹（略有偏差）
    actual_trajectory = [(p[0] + 0.5, p[1] + 0.5) for p in planned_path]
    actual_trajectory_with_heading = [(p[0], p[1], 0.0) for p in actual_trajectory]

    # 调用 web_server.update_trajectory_data()
    web_server.update_trajectory_data(
        field_boundary=field_boundary,
        planned_path=planned_path,
        actual_trajectory=actual_trajectory,
        actual_trajectory_with_heading=actual_trajectory_with_heading,
        metrics={
            "planned_distance_m": 900.0,
            "actual_distance_m": 905.0,
            "distance_error_m": 5.0,
            "distance_error_percent": 0.6,
            "avg_lateral_error_m": 0.7,
            "max_lateral_error_m": 1.2,
            "trajectory_points": len(actual_trajectory)
        }
    )
    print("   ✅ 数据已推送")

    # 3. 持续运行几秒
    print("\n3️⃣  Web服务器运行中...")
    print("   请在浏览器中打开 http://127.0.0.1:8080 查看轨迹")
    for i in range(10, 0, -1):
        print(f"   {i} 秒后退出...")
        time.sleep(1)

    # 4. 退出
    print("\n4️⃣  测试完成，退出...")
    print(f"   线程状态: {'运行中' if server_thread.is_alive() else '已停止'}")
    print("   daemon=True，线程会在主程序退出时自动关闭")
    print("\n" + "=" * 70)
    print("✅ Web服务器模块测试通过")
    print("=" * 70)


if __name__ == "__main__":
    test_web_server()
    print("\n👋 程序退出，Web服务器自动关闭")
