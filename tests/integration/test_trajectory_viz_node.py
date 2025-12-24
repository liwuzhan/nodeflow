"""
轨迹对比可视化节点集成测试

验证轨迹可视化节点的核心功能：
- 地块边界收集
- 规划路径收集
- 实际GPS轨迹收集
- 可视化图像生成
- 统计信息计算
"""

import os
import sys
import time
import json
import tempfile
from pathlib import Path

# 添加项目根目录到路径
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from sdk.port import OutputPort, InputPort
from sdk.shared_buffer_lite import SharedBufferLite


# ========== 轨迹可视化节点功能测试 ==========

class TestTrajectoryVizCollection:
    """轨迹数据收集测试"""

    def test_field_boundary_collection(self):
        """测试地块边界收集"""
        print("\n=== 测试地块边界收集 ===")
        SharedBufferLite.cleanup_all()

        zmq_addr = "ipc:///tmp/nodeflow/test_boundary"

        # 模拟规划器发送task_request
        output = OutputPort(name="sim_output", zmq_address=zmq_addr)
        time.sleep(0.1)

        # 地块边界数据
        task_data = {
            "field_name": "Test Field A",
            "field_boundary": [
                {"lat": 40.1230, "lon": -88.6540},
                {"lat": 40.1240, "lon": -88.6540},
                {"lat": 40.1240, "lon": -88.6550},
                {"lat": 40.1230, "lon": -88.6550}
            ]
        }

        output.send(task_data)
        time.sleep(0.1)

        # 验证接收
        input_port = InputPort(name="viz_task", zmq_address_or_source=zmq_addr)
        time.sleep(0.1)

        received = input_port.recv_latest()
        assert received is not None, "应该接收到task_request"
        assert received["field_name"] == "Test Field A", "地块名应该匹配"
        assert len(received["field_boundary"]) == 4, "应该有4个边界点"

        print("  ✓ 接收到地块边界: 4 个点")
        print(f"  ✓ 地块名: {received['field_name']}")

        output.close()
        input_port.close()
        SharedBufferLite.cleanup_all()

        print("✅ 地块边界收集测试通过")

    def test_planned_path_collection(self):
        """测试规划路径收集"""
        print("\n=== 测试规划路径收集 ===")
        SharedBufferLite.cleanup_all()

        zmq_addr = "ipc:///tmp/nodeflow/test_path"

        # 模拟规划器发送global_path
        output = OutputPort(name="global_coverage", zmq_address=zmq_addr)
        time.sleep(0.1)

        # 规划路径数据
        path_data = {
            "waypoints": [
                {"lat": 40.1230, "lon": -88.6540, "heading": 0},
                {"lat": 40.1235, "lon": -88.6540, "heading": 0},
                {"lat": 40.1240, "lon": -88.6540, "heading": 0},
                {"lat": 40.1240, "lon": -88.6545, "heading": 180},
            ],
            "total_distance": 250.0
        }

        output.send(path_data)
        time.sleep(0.1)

        # 验证接收
        input_port = InputPort(name="viz_path", zmq_address_or_source=zmq_addr)
        time.sleep(0.1)

        received = input_port.recv_latest()
        assert received is not None, "应该接收到global_path"
        assert len(received["waypoints"]) == 4, "应该有4个路径点"

        print("  ✓ 接收到规划路径: 4 个路径点")
        print(f"  ✓ 总距离: {received['total_distance']} m")

        output.close()
        input_port.close()
        SharedBufferLite.cleanup_all()

        print("✅ 规划路径收集测试通过")

    def test_gps_trajectory_collection(self):
        """测试GPS轨迹收集"""
        print("\n=== 测试GPS轨迹收集 ===")
        SharedBufferLite.cleanup_all()

        zmq_addr = "ipc:///tmp/nodeflow/test_gps"

        # 模拟GPS发送器
        output = OutputPort(name="sim_output", zmq_address=zmq_addr)
        time.sleep(0.1)

        input_port = InputPort(name="viz_gps", zmq_address_or_source=zmq_addr)
        time.sleep(0.1)

        # 发送多个GPS点
        gps_points = [
            {"latitude": 40.1230, "longitude": -88.6540, "altitude": 250.0},
            {"latitude": 40.1232, "longitude": -88.6540, "altitude": 250.1},
            {"latitude": 40.1234, "longitude": -88.6540, "altitude": 250.2},
            {"latitude": 40.1236, "longitude": -88.6540, "altitude": 250.3},
            {"latitude": 40.1238, "longitude": -88.6540, "altitude": 250.4},
        ]

        for gps_data in gps_points:
            output.send(gps_data)
            time.sleep(0.05)

        time.sleep(0.1)

        # 验证接收最后一个点
        received = input_port.recv_latest()
        assert received is not None, "应该接收到GPS数据"
        assert received["latitude"] == 40.1238, "最后一个点应该匹配"

        print(f"  ✓ 接收到 {len(gps_points)} 个GPS点")
        print(f"  ✓ 最后位置: ({received['latitude']}, {received['longitude']})")

        output.close()
        input_port.close()
        SharedBufferLite.cleanup_all()

        print("✅ GPS轨迹收集测试通过")


class TestTrajectoryVizAnalysis:
    """轨迹分析功能测试"""

    def test_distance_calculation(self):
        """测试距离计算"""
        print("\n=== 测试距离计算 ===")

        # 添加node-hub路径
        sys.path.insert(0, str(Path(__file__).parent.parent.parent / "node-hub" / "trajectory_viz"))
        from run import TrajectoryAnalyzer, TrajectoryCollector

        # 创建收集器并添加数据
        collector = TrajectoryCollector()

        # 添加规划路径（南北向，约1000米）
        collector.planned_path = [
            (40.12, -88.654),
            (40.13, -88.654),
            (40.14, -88.654),
        ]

        # 添加实际轨迹（略有偏移）
        collector.actual_trajectory = [
            (40.12, -88.654),
            (40.125, -88.653),
            (40.13, -88.654),
            (40.135, -88.653),
            (40.14, -88.654),
        ]

        # 分析
        analyzer = TrajectoryAnalyzer(collector)
        path_len = analyzer.calculate_path_length(collector.planned_path)
        actual_len = analyzer.calculate_path_length(collector.actual_trajectory)

        print(f"  规划路径长度: {path_len:.1f} m")
        print(f"  实际轨迹长度: {actual_len:.1f} m")
        print(f"  长度差异: {abs(actual_len - path_len):.1f} m")

        assert path_len > 0, "规划路径长度应大于0"
        assert actual_len > 0, "实际轨迹长度应大于0"

        print("✅ 距离计算测试通过")

    def test_error_statistics(self):
        """测试误差统计"""
        print("\n=== 测试误差统计 ===")

        # 添加node-hub路径
        sys.path.insert(0, str(Path(__file__).parent.parent.parent / "node-hub" / "trajectory_viz"))
        from run import TrajectoryAnalyzer, TrajectoryCollector

        collector = TrajectoryCollector()

        # 规划路径：直线
        collector.planned_path = [
            (40.1200, -88.6540),
            (40.1400, -88.6540),
        ]

        # 实际轨迹：蛇形
        collector.actual_trajectory = [
            (40.1200, -88.6540),
            (40.1210, -88.6530),
            (40.1220, -88.6540),
            (40.1230, -88.6550),
            (40.1240, -88.6540),
            (40.1250, -88.6530),
            (40.1260, -88.6540),
            (40.1270, -88.6550),
            (40.1280, -88.6540),
            (40.1290, -88.6530),
            (40.1300, -88.6540),
            (40.1310, -88.6550),
            (40.1320, -88.6540),
            (40.1330, -88.6530),
            (40.1340, -88.6540),
            (40.1350, -88.6550),
            (40.1360, -88.6540),
            (40.1370, -88.6530),
            (40.1380, -88.6540),
            (40.1390, -88.6550),
            (40.1400, -88.6540),
        ]

        analyzer = TrajectoryAnalyzer(collector)
        error_stats = analyzer.calculate_path_error()

        print(f"  规划距离: {error_stats['planned_distance']:.1f} m")
        print(f"  实际距离: {error_stats['actual_distance']:.1f} m")
        print(f"  平均横向误差: {error_stats['average_lateral_error']:.3f} m")
        print(f"  最大横向误差: {error_stats['max_lateral_error']:.3f} m")

        assert error_stats['average_lateral_error'] > 0, "应该有横向误差"
        assert error_stats['max_lateral_error'] > error_stats['average_lateral_error'], "最大误差应大于平均误差"

        print("✅ 误差统计测试通过")

    def test_coverage_metrics(self):
        """测试覆盖率计算"""
        print("\n=== 测试覆盖率计算 ===")

        # 添加node-hub路径
        sys.path.insert(0, str(Path(__file__).parent.parent.parent / "node-hub" / "trajectory_viz"))
        from run import TrajectoryAnalyzer, TrajectoryCollector
        import time

        collector = TrajectoryCollector()
        collector.task_start_time = time.time() - 120  # 2分钟前启动

        collector.field_boundary = [
            (40.1200, -88.6540),
            (40.1400, -88.6540),
            (40.1400, -88.6640),
            (40.1200, -88.6640),
        ]

        collector.planned_path = [
            (40.1200, -88.6540),
            (40.1300, -88.6540),
            (40.1400, -88.6540),
        ]

        collector.actual_trajectory = [
            (40.1200, -88.6540),
            (40.1250, -88.6540),
            (40.1300, -88.6540),
            (40.1350, -88.6540),
            (40.1400, -88.6540),
        ]

        analyzer = TrajectoryAnalyzer(collector)
        coverage = analyzer.get_coverage_metrics()

        print(f"  覆盖率: {coverage['coverage_rate']:.1f}%")
        print(f"  任务耗时: {coverage['task_duration']:.1f} s")
        print(f"  轨迹点数: {coverage['trajectory_points']}")

        assert 0 <= coverage['coverage_rate'] <= 100, "覆盖率应在0-100%"
        assert coverage['task_duration'] > 0, "任务耗时应大于0"

        print("✅ 覆盖率计算测试通过")


class TestTrajectoryVizGeneration:
    """轨迹可视化生成测试"""

    def test_visualization_generation(self):
        """测试可视化图像生成"""
        print("\n=== 测试可视化图像生成 ===")

        # 添加node-hub路径
        sys.path.insert(0, str(Path(__file__).parent.parent.parent / "node-hub" / "trajectory_viz"))
        from run import TrajectoryVisualizer, TrajectoryCollector
        import tempfile

        # 创建临时目录
        with tempfile.TemporaryDirectory() as tmpdir:
            collector = TrajectoryCollector()
            collector.field_name = "Test Field"

            # 添加完整数据
            collector.field_boundary = [
                (40.1200, -88.6540),
                (40.1400, -88.6540),
                (40.1400, -88.6640),
                (40.1200, -88.6640),
            ]

            collector.planned_path = [
                (40.1200, -88.6540),
                (40.1300, -88.6540),
                (40.1400, -88.6540),
            ]

            collector.actual_trajectory = [
                (40.1200, -88.6540),
                (40.1210, -88.6541),
                (40.1220, -88.6540),
                (40.1230, -88.6540),
                (40.1240, -88.6541),
                (40.1250, -88.6540),
                (40.1260, -88.6540),
                (40.1270, -88.6541),
                (40.1280, -88.6540),
                (40.1290, -88.6540),
                (40.1300, -88.6541),
                (40.1310, -88.6540),
                (40.1320, -88.6540),
                (40.1330, -88.6541),
                (40.1340, -88.6540),
                (40.1350, -88.6540),
                (40.1360, -88.6541),
                (40.1370, -88.6540),
                (40.1380, -88.6540),
                (40.1390, -88.6541),
                (40.1400, -88.6540),
            ]

            # 生成可视化
            visualizer = TrajectoryVisualizer(collector, tmpdir)
            image_path = visualizer.generate_visualization(
                figsize=(10, 8),
                dpi=100,
                format="jpg"
            )

            assert image_path is not None, "应该生成可视化图像"
            assert Path(image_path).exists(), "图像文件应该存在"

            file_size = Path(image_path).stat().st_size
            print(f"  ✓ 生成图像: {Path(image_path).name}")
            print(f"  ✓ 文件大小: {file_size / 1024:.1f} KB")

        print("✅ 可视化图像生成测试通过")


def main():
    """运行所有轨迹可视化测试"""
    print("=" * 70)
    print("轨迹对比可视化节点集成测试")
    print("=" * 70)

    try:
        # 数据收集测试
        test_collect = TestTrajectoryVizCollection()
        test_collect.test_field_boundary_collection()
        test_collect.test_planned_path_collection()
        test_collect.test_gps_trajectory_collection()

        # 分析功能测试
        test_analysis = TestTrajectoryVizAnalysis()
        test_analysis.test_distance_calculation()
        test_analysis.test_error_statistics()
        test_analysis.test_coverage_metrics()

        # 可视化生成测试
        test_gen = TestTrajectoryVizGeneration()
        test_gen.test_visualization_generation()

        print("\n" + "=" * 70)
        print("✅ 所有轨迹可视化测试通过！")
        print("=" * 70)
        print("\n验证的功能：")
        print("  1. ✓ 地块边界数据收集")
        print("  2. ✓ 规划路径数据收集")
        print("  3. ✓ GPS轨迹数据收集")
        print("  4. ✓ 距离计算")
        print("  5. ✓ 误差统计")
        print("  6. ✓ 覆盖率计算")
        print("  7. ✓ 可视化图像生成")

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
