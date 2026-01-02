#!/usr/bin/env python3
import sys
import time
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, Optional, List, Tuple

# Pydantic 导入
try:
    from pydantic import BaseModel, Field
except ImportError:
    class BaseModel: pass
    def Field(*args, **kwargs): return None

project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from sdk.nodeflow_sdk import NodeFlowSDK
from atom import calculate_trajectory_metrics, generate_trajectory_image

# --- Schema Definitions ---

class TaskENU(BaseModel):
    id: str
    parcel: Dict[str, Any]
    vehicle: Dict[str, Any]
    ref_lon: float
    ref_lat: float
    timestamp: float

class GlobalPath(BaseModel):
    task_id: str
    timestamp: float
    path: List[Tuple[float, float]]
    status: str
    message: str

class PoseENU(BaseModel):
    x: float
    y: float
    theta: float
    timestamp: float
    rtk_status: Any

class TrajectoryImage(BaseModel):
    image_path: str
    timestamp: str
    update_count: int
    stats: Dict[str, Any]

# --- End Schema Definitions ---

class TrajectoryVisualizerNode:
    """轨迹可视化节点（L3层）"""

    def __init__(self, output_dir: str, update_interval: float):
        self.output_dir = Path(output_dir)
        self.update_interval = update_interval
        self.output_dir.mkdir(parents=True, exist_ok=True)

        # 当前任务数据（单帧）
        self.current_task_id: Optional[str] = None
        self.field_boundary: Optional[List[Tuple[float, float]]] = None
        self.planned_path: Optional[List[Tuple[float, float]]] = None
        self.ref_lon: Optional[float] = None
        self.ref_lat: Optional[float] = None

        # 轨迹数据（持续累积）
        self.actual_trajectory: List[Tuple[float, float]] = []
        self.actual_trajectory_with_heading: List[Tuple[float, float, float]] = []

        # 统计
        self.last_update_time = time.time()
        self.update_count = 0
        self.pose_count = 0

    def is_ready(self) -> bool:
        """检查是否有足够数据用于可视化"""
        has_boundary = self.field_boundary and len(self.field_boundary) >= 3
        has_path = self.planned_path and len(self.planned_path) >= 2
        has_trajectory = len(self.actual_trajectory) >= 2
        return has_boundary and has_path and has_trajectory

    def on_task_data(self, task_data: Dict[str, Any]):
        """处理task_enu数据"""
        if not task_data:
            return

        try:
            # task_enu用的是"id"字段（注意不是"task_id"）
            task_id = task_data.get("id")

            # 检测任务变更
            if task_id and task_id != self.current_task_id:
                print(f"[新任务] {task_id} - 清空上一个任务的轨迹")
                self.current_task_id = task_id
                self.actual_trajectory = []
                self.actual_trajectory_with_heading = []

            # 提取地块边界（ENU坐标）
            parcel = task_data.get("parcel", {})
            outer = parcel.get("outer")

            if isinstance(outer, list) and len(outer) >= 3:
                self.field_boundary = outer
                print(f"✓ 地块边界: {len(outer)}个点 (ENU坐标)")

            # 提取GPS参考点
            self.ref_lon = task_data.get("ref_lon")
            self.ref_lat = task_data.get("ref_lat")

            if self.ref_lon and self.ref_lat:
                print(f"  GPS参考点: ({self.ref_lon:.6f}°, {self.ref_lat:.6f}°)")

        except Exception as e:
            print(f"✗ 处理task_enu失败: {e}")

    def on_path_data(self, path_data: Dict[str, Any]):
        """处理global_path数据"""
        if not path_data:
            return

        try:
            task_id = path_data.get("task_id")

            # 验证task_id匹配
            if task_id and task_id != self.current_task_id:
                print(f"[警告] path数据来自不同任务 ({task_id} != {self.current_task_id})，忽略")
                return

            path = path_data.get("path")
            if isinstance(path, list) and len(path) >= 2:
                self.planned_path = path
                print(f"✓ 规划路径: {len(path)}个点 (ENU坐标)")

        except Exception as e:
            print(f"✗ 处理global_path失败: {e}")

    def on_pose_data(self, pose_data: Dict[str, Any]):
        """处理pose_enu数据（持续累积）"""
        if not pose_data:
            return

        try:
            x = pose_data.get("x")
            y = pose_data.get("y")
            theta = pose_data.get("theta", 0.0)

            if x is not None and y is not None:
                self.actual_trajectory.append((float(x), float(y)))
                self.actual_trajectory_with_heading.append((float(x), float(y), float(theta)))
                self.pose_count += 1

        except Exception as e:
            print(f"✗ 处理pose_enu失败: {e}")

    def try_generate_visualization(self) -> Optional[Tuple[str, Dict[str, Any]]]:
        """尝试生成可视化（如果数据就绪且时间到了）"""
        current_time = time.time()

        # 检查更新间隔
        if current_time - self.last_update_time < self.update_interval:
            return None

        # 检查数据是否就绪
        if not self.is_ready():
            return None

        # 生成可视化
        try:
            metrics = calculate_trajectory_metrics(
                self.planned_path,
                self.actual_trajectory,
                approach_threshold_m=5.0
            )

            # 生成图像
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            output_path = self.output_dir / f"trajectory_viz_{timestamp}.jpg"

            success = generate_trajectory_image(
                field_boundary=self.field_boundary,
                planned_path=self.planned_path,
                actual_trajectory=self.actual_trajectory,
                actual_trajectory_with_heading=self.actual_trajectory_with_heading,
                metrics=metrics,
                output_path=output_path,
                figsize=(14.0, 12.0),
                dpi=150,
                ref_lon=self.ref_lon,
                ref_lat=self.ref_lat
            )

            if success:
                self.update_count += 1
                self.last_update_time = current_time
                print(f"✓ 可视化已保存: {output_path}")
                return (str(output_path), metrics)

        except Exception as e:
            print(f"✗ 生成可视化失败: {e}")

        return None


def main():
    """主函数"""
    with NodeFlowSDK(log_level="INFO") as sdk:
        print("=" * 70)
        print("轨迹对比可视化节点启动 (L3层 - 数据流管理)")
        print("=" * 70)

        # 读取参数
        output_dir = sdk.params.get("output_dir", "./logs/jpg")
        update_interval = float(sdk.params.get("update_interval", 10.0))
        timeout = float(sdk.params.get("timeout", 0.0))

        print(f"输出目录: {output_dir}")
        print(f"更新间隔: {update_interval}秒")
        if timeout > 0:
            print(f"超时: {timeout}秒")
        else:
            print(f"超时: 禁用（timeout=0.0）")

        # 创建输入输出端口
        task_port = sdk.create_input_port("task_enu")
        path_port = sdk.create_input_port("global_path")
        pose_port = sdk.create_input_port("pose_enu")
        output_port = sdk.create_output_port("trajectory_image", schema=TrajectoryImage)

        print("端口已创建: task_enu, global_path, pose_enu -> trajectory_image")
        print()

        # 创建节点实例
        node = TrajectoryVisualizerNode(output_dir, update_interval)

        start_time = time.time()
        loop_count = 0
        last_log_time = start_time

        print("等待数据...")

        try:
            while True:
                elapsed = time.time() - start_time
                loop_count += 1

                # 检查超时
                if timeout > 0 and elapsed > timeout:
                    print(f"\n[超时] 达到{timeout}秒，关闭节点")
                    break

                # 接收数据（Latest-Value语义，无阻塞）
                task_data = task_port.recv_latest()
                path_data = path_port.recv_latest()
                pose_data = pose_port.recv_latest()

                # 处理数据
                if task_data:
                    node.on_task_data(task_data)

                if path_data:
                    node.on_path_data(path_data)

                if pose_data:
                    node.on_pose_data(pose_data)

                # 定期日志
                current_time = time.time()
                if current_time - last_log_time >= 5.0:
                    ready_status = "✓ 就绪" if node.is_ready() else "⏳ 等待数据"
                    print(f"[状态] {ready_status} | 轨迹点: {len(node.actual_trajectory)} | 已更新: {node.update_count}次")
                    last_log_time = current_time

                # 尝试生成可视化
                result = node.try_generate_visualization()
                if result:
                    image_path, metrics = result
                    output_data = {
                        "image_path": image_path,
                        "timestamp": datetime.now().isoformat(),
                        "update_count": node.update_count,
                        "stats": metrics
                    }
                    output_port.send(output_data)

                # 控制CPU占用
                time.sleep(0.1)

        except KeyboardInterrupt:
            print("\n[中断] 收到中断信号，关闭节点")
        except Exception as e:
            print(f"\n[错误] {e}")
            import traceback
            traceback.print_exc()

        # 汇总统计
        print()
        print("=" * 70)
        print(f"节点统计:")
        print(f"  总循环次数: {loop_count}")
        print(f"  接收轨迹点数: {node.pose_count}")
        print(f"  生成可视化次数: {node.update_count}")
        print(f"  最后任务ID: {node.current_task_id}")
        print("=" * 70)


if __name__ == "__main__":
    main()
