#!/usr/bin/env python3
"""
轨迹可视化节点 (L3层 - 数据搬运)

功能：
- 接收地块边界、规划路径、实际轨迹数据
- 计算轨迹指标（调用L4层atom）
- 启动Web服务器进行实时可视化
- 输出统计信息

职责：仅负责数据收发和调用原子函数，不包含业务逻辑
"""

import sys
import time
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, Optional, List, Tuple

# 添加 SDK 路径
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

# 添加当前目录
sys.path.insert(0, str(Path(__file__).parent))

from sdk.nodeflow_sdk import NodeFlowSDK
import atom  # L4 原子逻辑
import web_server  # Web服务器模块

# Pydantic Schema (可选)
try:
    from pydantic import BaseModel, Field

    class TrajectoryWebURL(BaseModel):
        """Web可视化输出数据格式"""
        url: str
        timestamp: str
        update_count: int
        stats: Dict[str, Any]
except ImportError:
    TrajectoryWebURL = None


def main():
    """节点主函数 (L3 - 傻瓜式循环)"""

    with NodeFlowSDK(log_level="INFO") as sdk:
        print("=" * 70)
        print("轨迹可视化节点启动 (Web 实时版本)")
        print("=" * 70)

        # 1. 读取参数
        web_host = sdk.get_param('web_host', '127.0.0.1')
        web_port = int(sdk.get_param('web_port', 8080))
        update_interval = float(sdk.get_param('update_interval', 5.0))
        timeout = float(sdk.get_param('timeout', 0.0))

        print(f"配置: host={web_host}, port={web_port}, interval={update_interval}s")

        # 2. 启动 Web 服务器 (工具层，daemon线程)
        web_server.start_web_server(host=web_host, port=web_port)
        print(f"Web服务器已启动: http://{web_host}:{web_port}")
        print()

        # 3. 创建端口
        task_port = sdk.create_input_port('task_enu')
        path_port = sdk.create_input_port('global_path')
        pose_port = sdk.create_input_port('pose_enu')
        output_port = sdk.create_output_port('web_url', schema=TrajectoryWebURL)

        print("端口已创建: task_enu, global_path, pose_enu -> web_url")
        print()

        # 4. 状态变量 (L3 职责：状态管理)
        current_task_id: Optional[str] = None
        field_boundary: Optional[List[Tuple[float, float]]] = None
        planned_path: Optional[List[Tuple[float, float]]] = None
        actual_trajectory: List[Tuple[float, float]] = []
        actual_trajectory_with_heading: List[Tuple[float, float, float]] = []

        # 统计
        update_count = 0
        pose_count = 0
        last_update_time = time.time()
        start_time = time.time()

        print("等待数据...")

        # 5. 主循环 (L3 核心职责)
        try:
            while True:
                elapsed = time.time() - start_time

                # 5a. 检查超时
                if timeout > 0 and elapsed > timeout:
                    print(f"\n[超时] 达到{timeout}秒，关闭节点")
                    break

                # 5b. 接收数据 (非阻塞，Latest-Value语义)
                task_data = task_port.recv_latest()
                path_data = path_port.recv_latest()
                pose_data = pose_port.recv_latest()

                # 5c. 处理 task_enu (地块边界)
                if task_data:
                    task_id = task_data.get("id")

                    # 任务切换：清空轨迹
                    if task_id and task_id != current_task_id:
                        print(f"[新任务] {task_id}")
                        current_task_id = task_id
                        actual_trajectory = []
                        actual_trajectory_with_heading = []

                    # 提取边界
                    parcel = task_data.get("parcel", {})
                    outer = parcel.get("outer")
                    if isinstance(outer, list) and len(outer) >= 3:
                        field_boundary = outer
                        print(f"✓ 地块边界: {len(outer)}个点")

                # 5d. 处理 global_path (规划路径)
                if path_data:
                    path = path_data.get("path")
                    if isinstance(path, list) and len(path) >= 2:
                        planned_path = path
                        print(f"✓ 规划路径: {len(path)}个点")

                # 5e. 处理 pose_enu (实际轨迹，持续累积)
                if pose_data:
                    x = pose_data.get("x")
                    y = pose_data.get("y")
                    theta = pose_data.get("theta", 0.0)

                    if x is not None and y is not None:
                        actual_trajectory.append((float(x), float(y)))
                        actual_trajectory_with_heading.append((float(x), float(y), float(theta)))
                        pose_count += 1

                # 5f. 定期推送到Web (每 update_interval 秒)
                current_time = time.time()
                should_update = current_time - last_update_time >= update_interval

                # 检查是否有足够数据
                has_boundary = field_boundary and len(field_boundary) >= 3
                has_path = planned_path and len(planned_path) >= 2
                has_trajectory = len(actual_trajectory) >= 2
                is_ready = has_boundary and has_path and has_trajectory

                if should_update and (has_boundary or has_path or len(actual_trajectory) > 0):
                    # 计算指标 (调用 L4 原子)
                    metrics = {}
                    if is_ready:
                        try:
                            metrics = atom.calculate_trajectory_metrics(
                                planned_path, actual_trajectory, approach_threshold_m=5.0
                            )
                        except Exception as e:
                            print(f"✗ 计算指标失败: {e}")

                    # 推送到 Web 客户端
                    try:
                        web_server.update_trajectory_data(
                            field_boundary=field_boundary,
                            planned_path=planned_path,
                            actual_trajectory=actual_trajectory,
                            actual_trajectory_with_heading=actual_trajectory_with_heading,
                            metrics=metrics
                        )

                        update_count += 1
                        last_update_time = current_time

                        # 输出统计信息
                        output_data = {
                            "url": f"http://{web_host}:{web_port}",
                            "timestamp": datetime.now().isoformat(),
                            "update_count": update_count,
                            "stats": metrics
                        }
                        output_port.send(output_data)

                        status = "✓ 就绪" if is_ready else "⏳ 等待数据"
                        print(f"[{status}] 轨迹点: {len(actual_trajectory)} | 更新: {update_count}次")

                    except Exception as e:
                        print(f"✗ 推送失败: {e}")

                # 5g. 休眠 (控制CPU占用)
                time.sleep(0.1)  # 10Hz

        except KeyboardInterrupt:
            print("\n[中断] 收到中断信号，关闭节点")

        except Exception as e:
            print(f"\n[错误] {e}")
            import traceback
            traceback.print_exc()

        # 6. 退出统计
        print()
        print("=" * 70)
        print(f"节点统计:")
        print(f"  接收轨迹点数: {pose_count}")
        print(f"  生成可视化次数: {update_count}")
        print(f"  最后任务ID: {current_task_id}")
        print("=" * 70)
        print("🔴 节点退出，Web 服务器将自动关闭（daemon 线程）")
        print("=" * 70)


if __name__ == "__main__":
    main()
