#!/usr/bin/env python3
"""
测试 Web 服务器的启动和关闭行为
"""

import time
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from edge.nodes.observability.trajectory_viz.web_server import start_web_server, update_trajectory_data

def test_server_lifecycle():
    print("=" * 70)
    print("测试 Web 服务器生命周期")
    print("=" * 70)

    # 1. 启动服务器
    print("\n1️⃣  启动 Web 服务器...")
    server_thread = start_web_server(host='127.0.0.1', port=8080)
    print(f"   线程状态: {'运行中' if server_thread.is_alive() else '已停止'}")
    print(f"   daemon 模式: {server_thread.daemon}")

    # 2. 推送测试数据
    print("\n2️⃣  推送测试数据...")
    time.sleep(1)
    update_trajectory_data(
        field_boundary=[(0, 0), (100, 0), (100, 100), (0, 100)],
        planned_path=[(10, 10), (50, 50), (90, 90)],
        actual_trajectory=[(10, 11), (50, 51), (90, 91)],
        actual_trajectory_with_heading=[(10, 11, 0.785), (50, 51, 0.785), (90, 91, 0.785)],  # 45度角
        metrics={"planned_distance_m": 100, "actual_distance_m": 99}
    )
    print("   ✅ 数据已推送")

    # 3. 等待几秒
    print("\n3️⃣  服务器运行中...")
    print(f"   访问: http://127.0.0.1:8080")
    for i in range(5, 0, -1):
        print(f"   {i} 秒后自动退出...")
        time.sleep(1)

    # 4. 退出（daemon 线程会自动关闭）
    print("\n4️⃣  主程序即将退出...")
    print(f"   线程状态: {'运行中' if server_thread.is_alive() else '已停止'}")
    print("   由于 daemon=True，Web 服务器线程会自动被终止")
    print("\n" + "=" * 70)
    print("✅ 测试完成")
    print("   主程序退出后，daemon 线程会被 Python 自动清理")
    print("   端口 8080 应该在几秒内释放")
    print("=" * 70)

if __name__ == "__main__":
    test_server_lifecycle()
    print("\n👋 程序已退出，Web 服务器应该已关闭")
