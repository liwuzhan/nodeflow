#!/usr/bin/env python3
"""
轨迹对比可视化节点 (ENU版本)

功能：
- 接收地块信息、ENU规划路径和ENU姿态轨迹
- 生成对比可视化图像（X-Y平面，单位：米）
- 输出轨迹误差统计信息

输入端口：
  - task_request: {parcel: {outer: [(lon,lat),...], ...}, ...} (用于获取地块边界)
  - global_path: {path: [(x,y),...], task_id, ...} (ENU坐标)
  - pose_enu: {x, y, theta, ...} (ENU坐标)

输出端口：
  - trajectory_image: {image_path, timestamp, stats, ...}
"""

import sys
import os
import time
import math
from pathlib import Path
from datetime import datetime
from typing import List, Tuple, Dict, Any, Optional

import numpy as np
import matplotlib
matplotlib.use('Agg')  # Non-interactive backend
import matplotlib.pyplot as plt
from matplotlib.patches import Polygon

# 配置中文字体支持
plt.rcParams['font.sans-serif'] = ['PingFang SC', 'Arial Unicode MS', 'Heiti TC', 'STHeiti', 'SimHei']
plt.rcParams['axes.unicode_minus'] = False

# 添加项目根路径
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from sdk.nodeflow_sdk import NodeFlowSDK
from sdk.utils.geo import wgs84_to_local


def get_gps_ref() -> Tuple[float, float]:
    """获取GPS参考点（从环境变量或默认值）"""
    lon = float(os.getenv('GPS_REF_LON', '121.5'))
    lat = float(os.getenv('GPS_REF_LAT', '31.2'))
    return lon, lat


class TrajectoryVisualizer:
    """轨迹可视化器（ENU坐标系）"""

    def __init__(self, output_dir: str = "./logs/jpg"):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

        # GPS参考点（用于转换地块边界）
        self.ref_lon, self.ref_lat = get_gps_ref()

        # 数据缓存（全部使用ENU坐标）
        self.field_boundary = None  # [(x, y), ...] ENU
        self.planned_path = None    # [(x, y), ...] ENU
        self.actual_trajectory = []  # [(x, y), ...] ENU
        self.actual_trajectory_with_heading = []  # [(x, y, theta), ...] ENU + 数学坐标系角度

    def add_field_data(self, task_data: Dict[str, Any]):
        """从task_request提取地块边界并转换为ENU"""
        if not task_data:
            return False

        try:
            parcel = task_data.get("parcel")
            if not parcel:
                return False

            outer = parcel.get("outer")
            if not isinstance(outer, list) or len(outer) < 3:
                return False

            # 将WGS84转换为ENU
            enu_boundary = []
            for point in outer:
                lon, lat = point[0], point[1]
                x, y = wgs84_to_local(lon, lat, self.ref_lon, self.ref_lat)
                enu_boundary.append((x, y))

            self.field_boundary = enu_boundary
            print(f"✓ 地块边界已接收: {len(self.field_boundary)} 个点 (已转换为ENU)")
            return True
        except Exception as e:
            print(f"✗ 提取地块边界失败: {e}")
            return False

    def add_path_data(self, path_data: Dict[str, Any]):
        """从global_path提取ENU规划路径"""
        if not path_data:
            return False

        try:
            path = path_data.get("path")
            if not isinstance(path, list) or len(path) < 2:
                return False

            self.planned_path = path  # 已经是ENU坐标
            print(f"✓ 规划路径已接收: {len(self.planned_path)} 个点 (ENU坐标)")
            if self.planned_path:
                print(f"  [DEBUG] 起点: ({self.planned_path[0][0]:.2f}, {self.planned_path[0][1]:.2f})m")
                print(f"  [DEBUG] 终点: ({self.planned_path[-1][0]:.2f}, {self.planned_path[-1][1]:.2f})m")
            return True
        except Exception as e:
            print(f"✗ 提取规划路径失败: {e}")
            import traceback
            traceback.print_exc()
            return False

    def add_pose(self, pose_enu: Dict[str, Any]):
        """添加ENU姿态点到轨迹"""
        if not pose_enu:
            return

        try:
            x = pose_enu.get("x")
            y = pose_enu.get("y")
            theta = pose_enu.get("theta", 0.0)  # 航向角（弧度，数学坐标系）

            if x is not None and y is not None:
                self.actual_trajectory.append((float(x), float(y)))
                self.actual_trajectory_with_heading.append((float(x), float(y), float(theta)))
        except Exception as e:
            print(f"✗ 处理姿态数据失败: {e}")

    def is_ready(self) -> bool:
        """检查是否有足够数据用于可视化"""
        has_boundary = self.field_boundary and len(self.field_boundary) >= 3
        has_path = self.planned_path and len(self.planned_path) >= 2
        has_trajectory = len(self.actual_trajectory) >= 2

        return has_boundary and has_path and has_trajectory

    def calculate_metrics(self) -> Dict[str, Any]:
        """计算误差指标（ENU坐标系，欧几里得距离）"""
        if not self.planned_path or not self.actual_trajectory:
            return {}

        def distance(p1: Tuple, p2: Tuple) -> float:
            """欧几里得距离（米）"""
            return math.sqrt((p2[0] - p1[0])**2 + (p2[1] - p1[1])**2)

        # 计算规划路径长度
        planned_len = sum(distance(self.planned_path[i], self.planned_path[i+1])
                         for i in range(len(self.planned_path)-1))

        # 找到实际轨迹中第一个进入规划路径附近的点
        start_index = 0
        approach_threshold = 5.0  # 5米阈值
        for idx, actual_point in enumerate(self.actual_trajectory):
            dist_to_start = distance(actual_point, self.planned_path[0])
            if dist_to_start < approach_threshold:
                start_index = idx
                break

        # 使用过滤后的轨迹计算统计
        filtered_trajectory = self.actual_trajectory[start_index:]

        actual_len = sum(distance(filtered_trajectory[i], filtered_trajectory[i+1])
                        for i in range(len(filtered_trajectory)-1)) if len(filtered_trajectory) > 1 else 0

        # 计算横向误差
        lateral_errors = []
        for actual_point in filtered_trajectory:
            min_dist = float('inf')
            for i in range(len(self.planned_path)-1):
                p1 = self.planned_path[i]
                p2 = self.planned_path[i+1]

                dx = p2[0] - p1[0]
                dy = p2[1] - p1[1]

                if dx*dx + dy*dy == 0:
                    dist = distance(actual_point, p1)
                else:
                    t = max(0, min(1, ((actual_point[0] - p1[0]) * dx + (actual_point[1] - p1[1]) * dy) / (dx * dx + dy * dy)))
                    closest = (p1[0] + t * dx, p1[1] + t * dy)
                    dist = distance(actual_point, closest)

                min_dist = min(min_dist, dist)

            if min_dist != float('inf'):
                lateral_errors.append(min_dist)

        approach_distance = sum(distance(self.actual_trajectory[i], self.actual_trajectory[i+1])
                               for i in range(start_index)) if start_index > 0 else 0

        return {
            "planned_distance_m": round(planned_len, 2),
            "actual_distance_m": round(actual_len, 2),
            "approach_distance_m": round(approach_distance, 2),
            "distance_error_m": round(abs(actual_len - planned_len), 2),
            "distance_error_percent": round(abs(actual_len - planned_len) / planned_len * 100 if planned_len > 0 else 0, 1),
            "avg_lateral_error_m": round(np.mean(lateral_errors), 2) if lateral_errors else 0,
            "max_lateral_error_m": round(np.max(lateral_errors), 2) if lateral_errors else 0,
            "trajectory_points": len(filtered_trajectory),
            "total_points": len(self.actual_trajectory),
            "start_index": start_index
        }

    def generate_visualization(self, figsize: Tuple[float, float] = (14, 12),
                             dpi: int = 150) -> Optional[str]:
        """生成可视化图像（ENU坐标系，X-Y平面）"""
        if not self.is_ready():
            print(f"✗ 数据不足: 地块={bool(self.field_boundary)}, "
                  f"路径={bool(self.planned_path)}, 轨迹={len(self.actual_trajectory)}")
            return None

        try:
            fig, ax = plt.subplots(figsize=figsize, dpi=dpi)

            # 绘制地块边界
            if self.field_boundary:
                boundary_array = np.array(self.field_boundary)
                polygon = Polygon(boundary_array, fill=True, alpha=0.2,
                                color='green', edgecolor='darkgreen', linewidth=2)
                ax.add_patch(polygon)

            # 绘制规划路径
            if self.planned_path:
                planned_array = np.array(self.planned_path)
                ax.plot(planned_array[:, 0], planned_array[:, 1],
                       'b-', linewidth=2, label='规划路径', alpha=0.7)
                ax.plot(planned_array[0, 0], planned_array[0, 1], 'bo', markersize=10)
                ax.plot(planned_array[-1, 0], planned_array[-1, 1], 'bs', markersize=10)

            # 绘制实际轨迹
            if self.actual_trajectory:
                actual_array = np.array(self.actual_trajectory)
                ax.plot(actual_array[:, 0], actual_array[:, 1],
                       'r-', linewidth=2, label='实际轨迹', alpha=0.7)
                ax.plot(actual_array[0, 0], actual_array[0, 1], 'ro', markersize=10)
                ax.plot(actual_array[-1, 0], actual_array[-1, 1], 'rs', markersize=10)

                # 绘制航向角箭头（数学坐标系：东=0, CCW正）
                if self.actual_trajectory_with_heading and len(self.actual_trajectory_with_heading) >= 2:
                    heading_data = np.array(self.actual_trajectory_with_heading)
                    step = max(1, len(heading_data) // 20)

                    for idx in range(0, len(heading_data), step):
                        x, y, theta = heading_data[idx]
                        # 数学坐标系：dx = cos(theta), dy = sin(theta)
                        arrow_len = 3.0  # 箭头长度3米
                        dx = math.cos(theta) * arrow_len
                        dy = math.sin(theta) * arrow_len

                        ax.arrow(x, y, dx, dy, head_width=1.5, head_length=1.0,
                                fc='red', ec='red', alpha=0.6, linewidth=1.5)

            # 添加统计信息
            metrics = self.calculate_metrics()
            approach_info = f"接近起点: {metrics.get('approach_distance_m', 0)} m\n" if metrics.get('approach_distance_m', 0) > 0 else ""
            stats_text = f"""轨迹统计 (ENU坐标系)
────────────────
规划距离: {metrics.get('planned_distance_m', 0)} m
{approach_info}已跟踪距离: {metrics.get('actual_distance_m', 0)} m
距离误差: {metrics.get('distance_error_m', 0)} m ({metrics.get('distance_error_percent', 0)}%)

平均横向误差: {metrics.get('avg_lateral_error_m', 0)} m
最大横向误差: {metrics.get('max_lateral_error_m', 0)} m

有效轨迹点: {metrics.get('trajectory_points', 0)} / {metrics.get('total_points', 0)}"""

            ax.text(0.02, 0.98, stats_text, transform=ax.transAxes,
                   fontsize=10, verticalalignment='top', fontfamily='monospace',
                   bbox=dict(boxstyle='round', facecolor='wheat', alpha=0.8))

            # 设置坐标轴（ENU坐标系：X=东, Y=北, 单位米）
            ax.set_xlabel('X - 东向 (m)', fontsize=11)
            ax.set_ylabel('Y - 北向 (m)', fontsize=11)
            ax.set_title(f'轨迹对比 (ENU) - {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}',
                        fontsize=14, fontweight='bold')
            ax.grid(True, alpha=0.3)
            ax.legend(loc='upper right', fontsize=10)
            ax.set_aspect('equal')

            # 保存图像
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            output_path = self.output_dir / f"trajectory_viz_{timestamp}.jpg"
            plt.savefig(output_path, format='jpg', dpi=dpi, bbox_inches='tight')
            plt.close(fig)

            print(f"✓ 可视化已保存: {output_path}")
            return str(output_path), metrics

        except Exception as e:
            print(f"✗ 生成可视化失败: {e}")
            import traceback
            traceback.print_exc()
            return None


def main():
    """主函数"""
    with NodeFlowSDK() as sdk:
        print("=== 轨迹对比可视化节点启动 (ENU版本) ===")

        # 读取参数
        output_dir = sdk.params.get("output_dir", "./logs/jpg")
        timeout = float(sdk.params.get("timeout", 300.0))
        update_interval = sdk.params.get("update_interval", 10.0)
        figsize_width = sdk.params.get("figsize_width", 14.0)
        figsize_height = sdk.params.get("figsize_height", 12.0)
        dpi = sdk.params.get("dpi", 150)

        # 创建输入输出端口（ENU版本）
        task_port = sdk.create_input_port("task_request")
        path_port = sdk.create_input_port("global_path")
        pose_port = sdk.create_input_port("pose_enu")  # 改为接收ENU姿态
        output_port = sdk.create_output_port("trajectory_image")

        print(f"输出目录: {output_dir}")
        print(f"超时: {timeout}秒, 更新间隔: {update_interval}秒")

        # 创建可视化器
        visualizer = TrajectoryVisualizer(output_dir)
        print(f"GPS参考点: ({visualizer.ref_lon:.6f}, {visualizer.ref_lat:.6f})")

        start_time = time.time()
        last_update_time = start_time
        last_log_time = start_time
        update_count = 0
        pose_count = 0

        print("开始接收数据...\n")

        try:
            while True:
                elapsed = time.time() - start_time

                if timeout > 0 and elapsed > timeout:
                    print(f"\n超时达到 ({timeout}秒), 生成最终可视化...")
                    break

                # 接收数据
                task_data = task_port.recv_latest()
                path_data = path_port.recv_latest()
                pose_data = pose_port.recv_latest()

                # 处理数据
                if task_data:
                    visualizer.add_field_data(task_data)

                if path_data:
                    visualizer.add_path_data(path_data)

                if pose_data:
                    visualizer.add_pose(pose_data)
                    pose_count += 1

                # 定期生成可视化
                current_time = time.time()
                if current_time - last_update_time >= update_interval and visualizer.is_ready():
                    result = visualizer.generate_visualization(
                        figsize=(figsize_width, figsize_height),
                        dpi=dpi
                    )

                    if result:
                        image_path, metrics = result
                        update_count += 1

                        output_data = {
                            "image_path": image_path,
                            "timestamp": datetime.now().isoformat(),
                            "update_count": update_count,
                            "stats": metrics
                        }
                        output_port.send(output_data)

                    last_update_time = current_time

                # 定期打印进度
                if current_time - last_log_time >= 2.0:
                    print(f"进度: {elapsed:.1f}s, 姿态点: {pose_count}, "
                          f"可视化: {update_count}, 数据: "
                          f"地块={bool(visualizer.field_boundary)}, "
                          f"路径={bool(visualizer.planned_path)}")
                    last_log_time = current_time

                time.sleep(0.1)

        except KeyboardInterrupt:
            print("\n收到中断信号")

        finally:
            if visualizer.is_ready():
                result = visualizer.generate_visualization(
                    figsize=(figsize_width, figsize_height),
                    dpi=dpi
                )

                if result:
                    image_path, metrics = result

                    print("\n=== 最终统计 ===")
                    print(f"地块点数: {len(visualizer.field_boundary)}")
                    print(f"规划路径点: {len(visualizer.planned_path)}")
                    print(f"总轨迹点: {metrics['total_points']}")
                    print(f"有效轨迹点: {metrics['trajectory_points']}")
                    print(f"规划距离: {metrics['planned_distance_m']} m")
                    print(f"已跟踪距离: {metrics['actual_distance_m']} m")
                    print(f"距离误差: {metrics['distance_error_m']} m ({metrics['distance_error_percent']}%)")
                    print(f"平均横向误差: {metrics['avg_lateral_error_m']} m")
                    print(f"最大横向误差: {metrics['max_lateral_error_m']} m")
                    print(f"可视化图像: {image_path}")

                    final_output = {
                        "image_path": image_path,
                        "timestamp": datetime.now().isoformat(),
                        "status": "completed",
                        "final_update": True,
                        "stats": metrics
                    }
                    output_port.send(final_output)
            else:
                print("\n✗ 数据不充分, 无法生成可视化")

            print("\n=== 轨迹对比可视化节点退出 ===")


if __name__ == "__main__":
    main()
