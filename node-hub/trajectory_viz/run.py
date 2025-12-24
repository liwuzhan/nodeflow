#!/usr/bin/env python3
"""
轨迹对比可视化节点

功能：
- 接收地块边界信息（来自规划任务）
- 接收规划器生成的全局路径
- 实时接收并累积RTK GPS定位数据（实际轨迹）
- 对比规划轨迹和实际轨迹，生成可视化图像
- 任务完成或超时后保存JPG图像到节点目录

可视化特性：
- 地块边界显示为多边形
- 规划路径显示为蓝色线条
- 实际轨迹显示为红色线条
- 起点和终点标记
- 路径误差统计信息
- 覆盖率计算
"""

import sys
import time
import json
import math
from pathlib import Path
from datetime import datetime
from typing import Optional, List, Tuple, Dict, Any
import threading

import numpy as np
import matplotlib.pyplot as plt
from matplotlib.patches import Polygon
from matplotlib.collections import LineCollection
import matplotlib.patches as mpatches

# 添加项目根路径
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from sdk.nodeflow_sdk import NodeFlowSDK
from runtime.utils.logger import get_logger

logger = get_logger(__name__)


class TrajectoryCollector:
    """轨迹数据收集器"""

    def __init__(self):
        self.field_boundary = None  # [(lat, lon), ...]
        self.planned_path = None  # [(lat, lon), ...]
        self.actual_trajectory = []  # [(lat, lon), ...] accumulated GPS points

        # 统计信息
        self.field_name = None
        self.task_start_time = None
        self.actual_start_pos = None
        self.actual_end_pos = None

    def add_field_boundary(self, task_data: Dict[str, Any]):
        """添加地块边界"""
        if not task_data:
            return

        # 从task_request中提取地块边界
        if "field_boundary" in task_data:
            boundary = task_data["field_boundary"]
            if isinstance(boundary, list) and len(boundary) > 0:
                self.field_boundary = [(p.get("lat"), p.get("lon")) for p in boundary if "lat" in p and "lon" in p]
                self.field_name = task_data.get("field_name", "Unknown Field")
                logger.info(f"记录地块边界: {len(self.field_boundary)} 个点")

    def add_planned_path(self, path_data: Dict[str, Any]):
        """添加规划路径"""
        if not path_data:
            return

        # 从global_path中提取路径点
        if "waypoints" in path_data:
            waypoints = path_data["waypoints"]
            if isinstance(waypoints, list) and len(waypoints) > 0:
                self.planned_path = [(p.get("lat"), p.get("lon")) for p in waypoints if "lat" in p and "lon" in p]
                logger.info(f"记录规划路径: {len(self.planned_path)} 个路径点")

    def add_gps_point(self, gps_data: Dict[str, Any]):
        """添加实际GPS点"""
        if not gps_data:
            return

        # 提取经纬度
        lat = gps_data.get("latitude")
        lon = gps_data.get("longitude")

        if lat is not None and lon is not None:
            point = (float(lat), float(lon))
            self.actual_trajectory.append(point)

            # 记录起点
            if self.actual_start_pos is None:
                self.actual_start_pos = point
                self.task_start_time = time.time()

            self.actual_end_pos = point

    def is_complete(self) -> bool:
        """检查数据是否充分"""
        has_boundary = self.field_boundary is not None and len(self.field_boundary) >= 3
        has_planned = self.planned_path is not None and len(self.planned_path) >= 2
        has_actual = len(self.actual_trajectory) >= 2

        return has_boundary and has_planned and has_actual


class TrajectoryAnalyzer:
    """轨迹分析器"""

    def __init__(self, collector: TrajectoryCollector):
        self.collector = collector

    def calculate_distance(self, p1: Tuple[float, float], p2: Tuple[float, float]) -> float:
        """计算两点间距离（简化：使用欧氏距离）"""
        dlat = (p2[0] - p1[0]) * 111000  # 1度纬度约111km
        dlon = (p2[1] - p1[1]) * 111000 * math.cos(math.radians(p1[0]))
        return math.sqrt(dlat**2 + dlon**2)

    def calculate_path_length(self, path: List[Tuple[float, float]]) -> float:
        """计算路径总长度"""
        if len(path) < 2:
            return 0.0
        total = 0.0
        for i in range(len(path) - 1):
            total += self.calculate_distance(path[i], path[i + 1])
        return total

    def calculate_path_error(self) -> Dict[str, float]:
        """计算路径误差统计"""
        if not self.collector.planned_path or not self.collector.actual_trajectory:
            return {}

        planned_len = self.calculate_path_length(self.collector.planned_path)
        actual_len = self.calculate_path_length(self.collector.actual_trajectory)

        # 计算每个实际点到规划路径的最小距离
        errors = []
        for actual_point in self.collector.actual_trajectory:
            min_distance = float('inf')
            for i in range(len(self.collector.planned_path) - 1):
                p1 = self.collector.planned_path[i]
                p2 = self.collector.planned_path[i + 1]
                # 点到线段的距离
                dist = self._point_to_segment_distance(actual_point, p1, p2)
                min_distance = min(min_distance, dist)

            if min_distance != float('inf'):
                errors.append(min_distance)

        avg_error = np.mean(errors) if errors else 0.0
        max_error = np.max(errors) if errors else 0.0

        return {
            "planned_distance": planned_len,
            "actual_distance": actual_len,
            "distance_error": abs(actual_len - planned_len),
            "distance_error_percent": abs(actual_len - planned_len) / planned_len * 100 if planned_len > 0 else 0,
            "average_lateral_error": avg_error,
            "max_lateral_error": max_error,
            "num_points": len(self.collector.actual_trajectory)
        }

    def _point_to_segment_distance(self, point: Tuple[float, float],
                                   seg_start: Tuple[float, float],
                                   seg_end: Tuple[float, float]) -> float:
        """计算点到线段的距离"""
        p = np.array(point)
        a = np.array(seg_start)
        b = np.array(seg_end)

        # 向量ab和ap
        ab = b - a
        ap = p - a

        # 参数t
        ab_squared = np.dot(ab, ab)
        if ab_squared == 0:
            return np.linalg.norm(ap)

        t = max(0, min(1, np.dot(ap, ab) / ab_squared))

        # 最近点
        closest = a + t * ab
        return np.linalg.norm(p - closest) * 111000  # 转换为米

    def get_coverage_metrics(self) -> Dict[str, Any]:
        """计算覆盖率等指标"""
        if not self.collector.field_boundary:
            return {}

        # 简化：计算实际轨迹有效率（到达的距离 / 规划距离）
        path_error = self.calculate_path_error()

        if path_error and path_error.get("planned_distance", 0) > 0:
            coverage_rate = (path_error["planned_distance"] - path_error["distance_error"]) / path_error["planned_distance"] * 100
        else:
            coverage_rate = 0.0

        return {
            "coverage_rate": max(0, coverage_rate),
            "task_duration": time.time() - self.collector.task_start_time if self.collector.task_start_time else 0,
            "trajectory_points": len(self.collector.actual_trajectory)
        }


class TrajectoryVisualizer:
    """轨迹可视化器"""

    def __init__(self, collector: TrajectoryCollector, output_dir: str = "./trajectory_viz"):
        self.collector = collector
        self.analyzer = TrajectoryAnalyzer(collector)
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def generate_visualization(self, figsize: Tuple[float, float] = (12, 10),
                              dpi: int = 150, format: str = "jpg") -> Optional[str]:
        """生成轨迹对比可视化图"""
        try:
            fig, ax = plt.subplots(figsize=figsize, dpi=dpi)

            # 设置标题
            title = f"轨迹对比可视化 - {self.collector.field_name or '田地'} ({datetime.now().strftime('%Y-%m-%d %H:%M:%S')})"
            ax.set_title(title, fontsize=14, fontweight='bold')

            # 1. 绘制地块边界
            if self.collector.field_boundary and len(self.collector.field_boundary) >= 3:
                boundary_array = np.array(self.collector.field_boundary)
                polygon = Polygon(boundary_array, fill=True, alpha=0.2,
                                 color='green', edgecolor='darkgreen', linewidth=2)
                ax.add_patch(polygon)
                logger.debug(f"绘制地块边界 ({len(self.collector.field_boundary)} 点)")

            # 2. 绘制规划路径
            if self.collector.planned_path and len(self.collector.planned_path) >= 2:
                planned_array = np.array(self.collector.planned_path)
                ax.plot(planned_array[:, 1], planned_array[:, 0],
                       'b-', linewidth=2, label='规划路径', alpha=0.7)

                # 标记起点
                ax.plot(planned_array[0, 1], planned_array[0, 0], 'bo',
                       markersize=10, label='规划起点')
                # 标记终点
                ax.plot(planned_array[-1, 1], planned_array[-1, 0], 'bs',
                       markersize=10, label='规划终点')

                logger.debug(f"绘制规划路径 ({len(self.collector.planned_path)} 点)")

            # 3. 绘制实际轨迹
            if self.collector.actual_trajectory and len(self.collector.actual_trajectory) >= 2:
                actual_array = np.array(self.collector.actual_trajectory)
                ax.plot(actual_array[:, 1], actual_array[:, 0],
                       'r-', linewidth=2, label='实际轨迹', alpha=0.7)

                # 标记起点
                ax.plot(actual_array[0, 1], actual_array[0, 0], 'ro',
                       markersize=10, label='实际起点')
                # 标记终点
                ax.plot(actual_array[-1, 1], actual_array[-1, 0], 'rs',
                       markersize=10, label='实际终点')

                logger.debug(f"绘制实际轨迹 ({len(self.collector.actual_trajectory)} 点)")

            # 4. 添加统计信息面板
            ax2 = fig.add_axes([0.15, 0.05, 0.3, 0.25])
            ax2.axis('off')

            path_error = self.analyzer.calculate_path_error()
            coverage = self.analyzer.get_coverage_metrics()

            stats_text = f"""轨迹统计
─────────────────
规划距离: {path_error.get('planned_distance', 0):.1f} m
实际距离: {path_error.get('actual_distance', 0):.1f} m
距离误差: {path_error.get('distance_error', 0):.1f} m ({path_error.get('distance_error_percent', 0):.1f}%)

平均横向误差: {path_error.get('average_lateral_error', 0):.2f} m
最大横向误差: {path_error.get('max_lateral_error', 0):.2f} m

轨迹点数: {path_error.get('num_points', 0)}
覆盖率: {coverage.get('coverage_rate', 0):.1f}%
任务耗时: {coverage.get('task_duration', 0):.1f} s"""

            ax2.text(0.05, 0.95, stats_text, transform=ax2.transAxes,
                    fontsize=10, verticalalignment='top', fontfamily='monospace',
                    bbox=dict(boxstyle='round', facecolor='wheat', alpha=0.5))

            # 5. 设置坐标轴标签和图例
            ax.set_xlabel('经度 (°)', fontsize=11)
            ax.set_ylabel('纬度 (°)', fontsize=11)
            ax.grid(True, alpha=0.3)
            ax.legend(loc='upper right', fontsize=10)
            ax.set_aspect('equal')

            # 6. 保存图像
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"trajectory_viz_{timestamp}.{format}"
            output_path = self.output_dir / filename

            plt.savefig(output_path, format=format, dpi=dpi, bbox_inches='tight')
            plt.close(fig)

            logger.info(f"轨迹可视化已保存: {output_path}")
            return str(output_path)

        except Exception as e:
            logger.error(f"生成轨迹可视化失败: {e}")
            import traceback
            traceback.print_exc()
            return None


def main():
    """主函数"""
    with NodeFlowSDK() as sdk:
        print("=== 轨迹对比可视化节点启动 ===")

        # 读取参数
        output_dir = sdk.get_param("output_dir", "./trajectory_viz")
        image_format = sdk.get_param("image_format", "jpg")
        timeout = sdk.get_param("timeout", 300.0)
        update_interval = sdk.get_param("update_interval", 5.0)
        dpi = sdk.get_param("dpi", 150)
        figsize_width = sdk.get_param("figsize_width", 12.0)
        figsize_height = sdk.get_param("figsize_height", 10.0)

        print(f"输出目录: {output_dir}")
        print(f"图像格式: {image_format}")
        print(f"超时时间: {timeout}秒")
        print(f"更新间隔: {update_interval}秒")

        # 创建收集器和可视化器
        collector = TrajectoryCollector()
        visualizer = TrajectoryVisualizer(collector, output_dir)

        # 启动时间
        start_time = time.time()
        last_update_time = start_time
        visualization_count = 0

        print("开始接收轨迹数据...")

        try:
            while True:
                # 检查超时
                elapsed = time.time() - start_time
                if elapsed > timeout:
                    print(f"\n超时达到 ({timeout}秒)，生成最终可视化...")
                    break

                # 接收地块边界
                task_data = sdk.recv_latest("task_request")
                if task_data:
                    collector.add_field_boundary(task_data)

                # 接收规划路径
                path_data = sdk.recv_latest("global_path")
                if path_data:
                    collector.add_planned_path(path_data)

                # 接收GPS数据
                gps_data = sdk.recv_latest("rtk_fix")
                if gps_data:
                    collector.add_gps_point(gps_data)

                # 定期更新可视化
                current_time = time.time()
                if current_time - last_update_time >= update_interval and collector.is_complete():
                    # 生成可视化
                    image_path = visualizer.generate_visualization(
                        figsize=(figsize_width, figsize_height),
                        dpi=dpi,
                        format=image_format
                    )

                    if image_path:
                        visualization_count += 1
                        analyzer = TrajectoryAnalyzer(collector)
                        stats = analyzer.calculate_path_error()
                        coverage = analyzer.get_coverage_metrics()

                        print(f"\n[更新 #{visualization_count}] 轨迹可视化已生成")
                        print(f"  规划距离: {stats.get('planned_distance', 0):.1f}m")
                        print(f"  实际距离: {stats.get('actual_distance', 0):.1f}m")
                        print(f"  平均误差: {stats.get('average_lateral_error', 0):.2f}m")
                        print(f"  覆盖率: {coverage.get('coverage_rate', 0):.1f}%")

                        # 发送输出
                        output_data = {
                            "image_path": image_path,
                            "timestamp": datetime.now().isoformat(),
                            "trajectory_points": len(collector.actual_trajectory),
                            "path_error": stats,
                            "coverage_metrics": coverage
                        }
                        sdk.send("trajectory_image", output_data)

                    last_update_time = current_time

                # 小延迟，避免过度占用CPU
                time.sleep(0.1)

        except KeyboardInterrupt:
            print("\n收到中断信号，生成最终可视化...")

        finally:
            # 生成最终可视化
            if collector.is_complete():
                final_image_path = visualizer.generate_visualization(
                    figsize=(figsize_width, figsize_height),
                    dpi=dpi,
                    format=image_format
                )

                if final_image_path:
                    analyzer = TrajectoryAnalyzer(collector)
                    final_stats = analyzer.calculate_path_error()
                    final_coverage = analyzer.get_coverage_metrics()

                    print("\n=== 最终轨迹统计 ===")
                    print(f"地块: {collector.field_name}")
                    print(f"规划路径: {len(collector.planned_path)} 个路径点")
                    print(f"实际轨迹: {len(collector.actual_trajectory)} 个GPS点")
                    print(f"规划距离: {final_stats.get('planned_distance', 0):.1f} m")
                    print(f"实际距离: {final_stats.get('actual_distance', 0):.1f} m")
                    print(f"距离误差: {final_stats.get('distance_error', 0):.1f} m ({final_stats.get('distance_error_percent', 0):.1f}%)")
                    print(f"平均横向误差: {final_stats.get('average_lateral_error', 0):.2f} m")
                    print(f"最大横向误差: {final_stats.get('max_lateral_error', 0):.2f} m")
                    print(f"覆盖率: {final_coverage.get('coverage_rate', 0):.1f}%")
                    print(f"任务耗时: {final_coverage.get('task_duration', 0):.1f} s")
                    print(f"\n可视化图像: {final_image_path}")

                    # 发送最终输出
                    final_output = {
                        "image_path": final_image_path,
                        "timestamp": datetime.now().isoformat(),
                        "status": "completed",
                        "trajectory_points": len(collector.actual_trajectory),
                        "path_error": final_stats,
                        "coverage_metrics": final_coverage
                    }
                    sdk.send("trajectory_image", final_output)
            else:
                print("数据不充分，无法生成可视化")
                print(f"  地块边界: {collector.field_boundary is not None}")
                print(f"  规划路径: {collector.planned_path is not None}")
                print(f"  实际轨迹: {len(collector.actual_trajectory)} 点")

            print("\n=== 轨迹对比可视化节点退出 ===")


if __name__ == "__main__":
    main()
