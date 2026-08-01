#!/usr/bin/env python3
"""
简单测试：验证重构后的节点基本功能
"""

import time
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import web_server

def test_basic():
    print("=" * 60)
    print("测试重构后的 trajectory_viz 节点")
    print("=" * 60)

    # 1. 启动Web服务器
    print("\n✓ 启动 Web 服务器 (127.0.0.1:8080)...")
    thread = web_server.start_web_server(host='127.0.0.1', port=8080)
    time.sleep(2)  # 等待启动

    if thread.is_alive():
        print("  ✅ Web服务器运行中")
    else:
        print("  ❌ Web服务器启动失败")
        return

    # 2. 推送测试数据
    print("\n✓ 推送测试数据...")

    boundary = [(0, 0), (50, 0), (50, 50), (0, 50)]
    path = [(10, 10), (40, 10), (40, 40), (10, 40)]
    trajectory = [(10, 11), (40, 11), (40, 41), (10, 41)]
    heading = [(x, y, 0.0) for x, y in trajectory]

    web_server.update_trajectory_data(
        field_boundary=boundary,
        planned_path=path,
        actual_trajectory=trajectory,
        actual_trajectory_with_heading=heading,
        metrics={"test": "data"}
    )
    print("  ✅ 数据推送成功")

    # 3. 保持运行5秒
    print("\n✓ Web服务器运行中，请访问: http://127.0.0.1:8080")
    for i in range(5, 0, -1):
        print(f"  {i} 秒后退出...")
        time.sleep(1)

    print("\n=" * 60)
    print("✅ 测试完成")
    print("=" * 60)

if __name__ == "__main__":
    test_basic()
