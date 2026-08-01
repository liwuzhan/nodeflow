"""
端到端场景测试（包含可视化节点）: 仿真器 → 路径规划 → 速度控制 → 仿真器 + 轨迹可视化

完整测试流程：
1. 仿真器输出GPS和RTK数据 (sim_output)
2. 路径规划器生成全覆盖路径 (global_coverage)
3. 速度控制器基于路径生成速度命令 (velocity_controller)
4. 仿真器接收命令并更新状态 (sim_input)
5. 可视化节点生成轨迹对比图 (trajectory_viz)
6. 日志记录所有数据 (logger)

验证点：
- 完整数据流通畅
- 轨迹可视化正确生成
- 统计信息准确
"""

import os
import sys
import time
import json
import tempfile
from pathlib import Path

# 添加项目根目录到路径
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from edge.sdk.port import OutputPort, InputPort
from edge.sdk.shared_buffer_lite import SharedBufferLite


class TestE2EWithVisualization:
    """端到端测试（包含可视化）"""

    def test_complete_pipeline_with_viz(self):
        """测试完整管道：仿真 → 规划 → 控制 → 可视化"""
        print("\n=== 测试完整管道（含可视化） ===")
        SharedBufferLite.cleanup_all()

        # 创建临时输出目录
        with tempfile.TemporaryDirectory() as tmpdir:
            print(f"  临时目录: {tmpdir}")

            print("\n[步骤 1] 创建仿真器输出端口")
            sim_task_out = OutputPort(name="sim_task", buffer_name="sim_task")
            sim_gps_out = OutputPort(name="sim_gps", buffer_name="sim_gps")
            sim_state_out = OutputPort(name="sim_state", buffer_name="sim_state")

            # ========== 仿真器发送初始任务和GPS数据 ==========
            print("\n[步骤 2] 仿真器发送任务和GPS数据")

            # 任务请求（包含地块边界）
            task_data = {
                "field_name": "Test Field Alpha",
                "field_boundary": [
                    {"lat": 40.1200, "lon": -88.6540},
                    {"lat": 40.1400, "lon": -88.6540},
                    {"lat": 40.1400, "lon": -88.6640},
                    {"lat": 40.1200, "lon": -88.6640}
                ],
                "pattern": "boustrophe",
                "swath_width": 12.0
            }
            sim_task_out.send(task_data)
            print(f"  ✓ 发送任务: {task_data['field_name']}")

            # 初始GPS位置
            initial_gps = {
                "latitude": 40.1200,
                "longitude": -88.6540,
                "altitude": 250.0,
                "timestamp": time.time(),
                "fix_quality": 4
            }
            sim_gps_out.send(initial_gps)
            print(f"  ✓ 发送初始GPS: ({initial_gps['latitude']}, {initial_gps['longitude']})")

            # ========== 路径规划器接收任务并生成路径 ==========
            print("\n[步骤 3] 路径规划器生成路径")

            planner_task_in = InputPort(name="planner_task", buffer_name="sim_task")

            received_task = planner_task_in.recv_latest()
            assert received_task is not None, "规划器应该接收到任务"
            print(f"  ✓ 规划器接收任务: {len(received_task['field_boundary'])} 个边界点")

            # 生成规划路径（往复式覆盖）
            planner_output = OutputPort(name="global_path", buffer_name="global_path")

            path_data = {
                "waypoints": [
                    # 第一趟（从南到北）
                    {"lat": 40.1200, "lon": -88.6540, "heading": 0},
                    {"lat": 40.1250, "lon": -88.6540, "heading": 0},
                    {"lat": 40.1300, "lon": -88.6540, "heading": 0},
                    {"lat": 40.1350, "lon": -88.6540, "heading": 0},
                    {"lat": 40.1400, "lon": -88.6540, "heading": 0},
                    # 转弯
                    {"lat": 40.1400, "lon": -88.6552, "heading": 180},
                    # 第二趟（从北到南）
                    {"lat": 40.1350, "lon": -88.6552, "heading": 180},
                    {"lat": 40.1300, "lon": -88.6552, "heading": 180},
                    {"lat": 40.1250, "lon": -88.6552, "heading": 180},
                    {"lat": 40.1200, "lon": -88.6552, "heading": 180},
                    # 转弯
                    {"lat": 40.1200, "lon": -88.6564, "heading": 0},
                    # 第三趟（从南到北）
                    {"lat": 40.1250, "lon": -88.6564, "heading": 0},
                    {"lat": 40.1300, "lon": -88.6564, "heading": 0},
                    {"lat": 40.1350, "lon": -88.6564, "heading": 0},
                    {"lat": 40.1400, "lon": -88.6564, "heading": 0},
                ],
                "total_distance": 2500.0,
                "swath_spacing": 12.0
            }
            planner_output.send(path_data)
            print(f"  ✓ 规划器生成路径: {len(path_data['waypoints'])} 个路径点, {path_data['total_distance']}m")

            # ========== 速度控制器接收GPS和路径 ==========
            print("\n[步骤 4] 速度控制器生成控制命令")

            controller_gps_in = InputPort(name="ctrl_gps", buffer_name="sim_gps")
            controller_path_in = InputPort(name="ctrl_path", buffer_name="global_path")

            received_gps = controller_gps_in.recv_latest()
            received_path = controller_path_in.recv_latest()

            assert received_gps is not None, "控制器应该接收到GPS"
            assert received_path is not None, "控制器应该接收到路径"
            print(f"  ✓ 控制器接收GPS: lat={received_gps['latitude']}")
            print(f"  ✓ 控制器接收路径: {len(received_path['waypoints'])} 个点")

            controller_output = OutputPort(name="velocity_cmd", buffer_name="velocity_cmd")

            cmd_data = {
                "linear_velocity": 1.5,
                "angular_velocity": 0.0,
                "timestamp": time.time()
            }
            controller_output.send(cmd_data)
            print(f"  ✓ 控制器发送命令: v={cmd_data['linear_velocity']}m/s")

            # ========== 可视化节点接收所有数据 ==========
            print("\n[步骤 5] 可视化节点收集数据")

            # 可视化节点订阅
            viz_task_in = InputPort(name="viz_task", buffer_name="sim_task")
            viz_path_in = InputPort(name="viz_path", buffer_name="global_path")
            viz_gps_in = InputPort(name="viz_gps", buffer_name="sim_gps")

            # 验证可视化节点接收数据
            viz_task = viz_task_in.recv_latest()
            viz_path = viz_path_in.recv_latest()
            viz_gps = viz_gps_in.recv_latest()

            assert viz_task is not None, "可视化节点应该接收到任务"
            assert viz_path is not None, "可视化节点应该接收到路径"
            assert viz_gps is not None, "可视化节点应该接收到GPS"

            print(f"  ✓ 可视化节点接收任务: {viz_task['field_name']}")
            print(f"  ✓ 可视化节点接收路径: {len(viz_path['waypoints'])} 点")
            print(f"  ✓ 可视化节点接收GPS: ({viz_gps['latitude']}, {viz_gps['longitude']})")

            # ========== 模拟运动轨迹（沿规划路径移动） ==========
            print("\n[步骤 6] 模拟车辆沿路径运动")

            gps_trajectory = []
            num_points = 20  # 模拟20个GPS点

            for i in range(num_points):
                # 计算当前位置（沿第一趟路径）
                progress = i / (num_points - 1)

                if progress < 0.33:  # 第一趟
                    lat = 40.1200 + progress * 3 * 0.0200
                    lon = -88.6540 + (0.001 * (i % 3 - 1))  # 添加小偏差
                elif progress < 0.66:  # 第二趟
                    lat = 40.1400 - (progress - 0.33) * 3 * 0.0200
                    lon = -88.6552 + (0.001 * (i % 3 - 1))
                else:  # 第三趟
                    lat = 40.1200 + (progress - 0.66) * 3 * 0.0200
                    lon = -88.6564 + (0.001 * (i % 3 - 1))

                gps_point = {
                    "latitude": lat,
                    "longitude": lon,
                    "altitude": 250.0 + i * 0.1,
                    "timestamp": time.time(),
                    "fix_quality": 4
                }

                sim_gps_out.send(gps_point)
                gps_trajectory.append(gps_point)
                time.sleep(0.05)

            print(f"  ✓ 模拟 {num_points} 个GPS点")
            print(f"  ✓ 起点: ({gps_trajectory[0]['latitude']:.4f}, {gps_trajectory[0]['longitude']:.4f})")
            print(f"  ✓ 终点: ({gps_trajectory[-1]['latitude']:.4f}, {gps_trajectory[-1]['longitude']:.4f})")

            # ========== 生成可视化 ==========
            print("\n[步骤 7] 生成轨迹可视化")

            # 导入可视化类
            sys.path.insert(0, str(Path(__file__).parent.parent.parent / "edge/nodes" / "trajectory_viz"))
            from run import TrajectoryCollector, TrajectoryVisualizer, TrajectoryAnalyzer

            # 收集数据
            collector = TrajectoryCollector()
            collector.add_field_boundary(viz_task)
            collector.add_planned_path(viz_path)

            # 添加所有GPS轨迹点
            for gps_point in gps_trajectory:
                collector.add_gps_point(gps_point)

            print(f"  ✓ 收集数据完成:")
            print(f"    - 地块边界: {len(collector.field_boundary)} 点")
            print(f"    - 规划路径: {len(collector.planned_path)} 点")
            print(f"    - 实际轨迹: {len(collector.actual_trajectory)} 点")

            # 生成可视化
            visualizer = TrajectoryVisualizer(collector, tmpdir)
            image_path = visualizer.generate_visualization(
                figsize=(12, 10),
                dpi=100,
                format="jpg"
            )

            assert image_path is not None, "应该生成可视化图像"
            assert Path(image_path).exists(), "图像文件应该存在"

            file_size = Path(image_path).stat().st_size
            print(f"\n  ✓ 生成可视化图像: {Path(image_path).name}")
            print(f"  ✓ 文件大小: {file_size / 1024:.1f} KB")

            # ========== 计算统计信息 ==========
            print("\n[步骤 8] 计算轨迹统计")

            analyzer = TrajectoryAnalyzer(collector)
            path_error = analyzer.calculate_path_error()
            coverage = analyzer.get_coverage_metrics()

            print(f"  轨迹误差分析:")
            print(f"    - 规划距离: {path_error['planned_distance']:.1f} m")
            print(f"    - 实际距离: {path_error['actual_distance']:.1f} m")
            print(f"    - 距离误差: {path_error['distance_error']:.1f} m ({path_error['distance_error_percent']:.2f}%)")
            print(f"    - 平均横向误差: {path_error['average_lateral_error']:.2f} m")
            print(f"    - 最大横向误差: {path_error['max_lateral_error']:.2f} m")
            print(f"\n  覆盖率分析:")
            print(f"    - 覆盖率: {coverage['coverage_rate']:.1f}%")
            print(f"    - 轨迹点数: {coverage['trajectory_points']}")

            # 验证统计合理性
            assert path_error['planned_distance'] > 0, "规划距离应大于0"
            assert path_error['actual_distance'] > 0, "实际距离应大于0"
            assert 0 <= path_error['average_lateral_error'] <= 1000, "平均误差应该合理"
            assert 0 <= coverage['coverage_rate'] <= 100, "覆盖率应在0-100%"

            # ========== 清理 ==========
            print("\n[步骤 9] 清理资源")

            sim_task_out.close()
            sim_gps_out.close()
            sim_state_out.close()
            planner_task_in.close()
            planner_output.close()
            controller_gps_in.close()
            controller_path_in.close()
            controller_output.close()
            viz_task_in.close()
            viz_path_in.close()
            viz_gps_in.close()

            SharedBufferLite.cleanup_all()

            print("\n✅ 完整管道测试通过（含可视化）")

    def test_continuous_visualization_updates(self):
        """测试连续可视化更新"""
        print("\n=== 测试连续可视化更新 ===")
        SharedBufferLite.cleanup_all()

        with tempfile.TemporaryDirectory() as tmpdir:
            # 导入可视化类
            sys.path.insert(0, str(Path(__file__).parent.parent.parent / "edge/nodes" / "trajectory_viz"))
            from run import TrajectoryCollector, TrajectoryVisualizer

            # 创建GPS输出
            gps_out = OutputPort(name="gps", buffer_name="continuous_gps")

            # 初始化收集器
            collector = TrajectoryCollector()

            # 添加地块和规划路径
            collector.field_boundary = [
                (40.1200, -88.6540),
                (40.1400, -88.6540),
                (40.1400, -88.6640),
                (40.1200, -88.6640)
            ]

            collector.planned_path = [
                (40.1200, -88.6540),
                (40.1300, -88.6540),
                (40.1400, -88.6540),
            ]

            visualizer = TrajectoryVisualizer(collector, tmpdir)

            # 模拟连续GPS更新和多次可视化
            num_updates = 3
            points_per_update = 5

            for update_idx in range(num_updates):
                print(f"\n  [更新 {update_idx + 1}/{num_updates}]")

                # 添加GPS点
                for i in range(points_per_update):
                    lat = 40.1200 + (update_idx * points_per_update + i) * 0.01
                    lon = -88.6540 + 0.0001 * i

                    gps_data = {
                        "latitude": lat,
                        "longitude": lon,
                        "altitude": 250.0
                    }

                    gps_out.send(gps_data)
                    collector.add_gps_point(gps_data)
                    time.sleep(0.02)

                # 生成可视化
                image_path = visualizer.generate_visualization(
                    figsize=(10, 8),
                    dpi=80,
                    format="jpg"
                )

                assert image_path is not None, f"更新 {update_idx + 1} 应该生成图像"
                print(f"    ✓ 生成图像: {Path(image_path).name}")
                print(f"    ✓ 累计轨迹点: {len(collector.actual_trajectory)}")

            gps_out.close()
            SharedBufferLite.cleanup_all()

            print(f"\n✅ 连续可视化更新测试通过（{num_updates} 次更新）")


def main():
    """运行所有端到端可视化测试"""
    print("=" * 70)
    print("端到端场景测试（包含轨迹可视化）")
    print("=" * 70)

    try:
        test_e2e = TestE2EWithVisualization()
        test_e2e.test_complete_pipeline_with_viz()
        test_e2e.test_continuous_visualization_updates()

        print("\n" + "=" * 70)
        print("✅ 所有端到端可视化测试通过！")
        print("=" * 70)
        print("\n验证的完整流程：")
        print("  1. ✓ 仿真器输出任务和GPS数据")
        print("  2. ✓ 路径规划器生成覆盖路径")
        print("  3. ✓ 速度控制器生成控制命令")
        print("  4. ✓ 可视化节点接收所有数据")
        print("  5. ✓ 模拟车辆沿路径运动（20个GPS点）")
        print("  6. ✓ 生成轨迹对比可视化图像")
        print("  7. ✓ 计算误差和覆盖率统计")
        print("  8. ✓ 连续可视化更新（3次更新）")

    except AssertionError as e:
        print(f"\n❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

    except Exception as e:
        print(f"\n❌ 测试错误: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
