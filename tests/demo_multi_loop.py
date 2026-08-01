#!/usr/bin/env python3
"""
多轮循环功能的快速演示

这个脚本演示了如何使用新的多轮循环功能
"""

import sys
from pathlib import Path

# 添加项目路径
sys.path.insert(0, str(Path(__file__).parent))

from edge.runtime.main import NodeFlowRuntime


def demo_basic_api():
    """演示基本API用法"""
    print("\n" + "=" * 60)
    print("演示1: 底层API - 手动控制启停")
    print("=" * 60)

    config_file = "examples/planning_simulation.yaml"

    # 创建runtime实例
    runtime = NodeFlowRuntime(config_file, log_level="INFO")

    # 初始化框架（一次性）
    print("\n[1] 正在初始化框架...")
    result = runtime._initialize_framework()

    if result != 0:
        print("✗ 框架初始化失败")
        return

    print("✓ 框架初始化成功")
    print(f"  - 图ID: {runtime.config.graph_id}")
    print(f"  - 节点数: {len(runtime.nodes_dict)}")
    print(f"  - 拓扑层级: {len(runtime.topology_layers)}")

    # 模拟两轮启停（实际不运行，只展示API用法）
    print("\n[2] API用法演示（不实际运行）:")
    print("""
    # 第一轮
    runtime.start_dataflow()   # 启动数据流
    # ... 数据流运行中 ...
    runtime.stop_dataflow()    # 停止数据流

    # 第二轮
    runtime.start_dataflow()   # 再次启动
    # ... 数据流运行中 ...
    runtime.stop_dataflow()    # 再次停止
    """)

    print("✓ 演示完成")


def demo_run_with_loop():
    """演示run_with_loop()方法"""
    print("\n" + "=" * 60)
    print("演示2: run_with_loop() 方法")
    print("=" * 60)

    print("""
使用方法1 - 命令行:
  python3 -m runtime.main examples/planning_simulation.yaml --loop 3

使用方法2 - Python API:
  runtime = NodeFlowRuntime('config.yaml')
  runtime.run_with_loop(num_loops=3, loop_interval=5)

参数说明:
  - num_loops: 循环次数（None表示无限循环）
  - loop_interval: 两轮之间的等待时间（秒）
    """)


def demo_cli_usage():
    """演示CLI用法"""
    print("\n" + "=" * 60)
    print("演示3: 命令行用法")
    print("=" * 60)

    print("""
1. 传统单次运行:
   python3 -m runtime.main examples/planning_simulation.yaml

2. 运行3轮循环:
   python3 -m runtime.main examples/planning_simulation.yaml --loop 3

3. 无限循环（直到Ctrl+C）:
   python3 -m runtime.main examples/planning_simulation.yaml --loop 0

4. 自定义循环间隔（10秒）:
   python3 -m runtime.main examples/planning_simulation.yaml --loop 5 --loop-interval 10

5. 调试模式运行:
   python3 -m runtime.main examples/planning_simulation.yaml --loop 3 --log-level DEBUG
    """)


def main():
    """主函数"""
    print("\n" + "=" * 60)
    print("NodeFlow 多轮启动-停止循环功能演示")
    print("=" * 60)

    # 检查配置文件
    config_file = "examples/planning_simulation.yaml"
    if not Path(config_file).exists():
        print(f"\n✗ 配置文件不存在: {config_file}")
        print("请确保配置文件存在后再运行演示")
        return 1

    try:
        # 演示1：基本API
        demo_basic_api()

        # 演示2：run_with_loop方法
        demo_run_with_loop()

        # 演示3：CLI用法
        demo_cli_usage()

        print("\n" + "=" * 60)
        print("演示完成！")
        print("=" * 60)
        print("\n要查看完整文档，请参阅: MULTI_LOOP_GUIDE.md")
        print("要运行完整测试，请运行: python3 test_multi_loop.py")

        return 0

    except KeyboardInterrupt:
        print("\n\n演示被用户中断")
        return 1
    except Exception as e:
        print(f"\n✗ 演示过程中发生错误: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == '__main__':
    sys.exit(main())
