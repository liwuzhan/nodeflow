#!/usr/bin/env python3
"""
弧线跟踪控制器节点 - L3层主逻辑

功能：
- 接收贝塞尔平滑路径 + ENU位姿
- Pure Pursuit 弧线跟踪算法
- 输出速度控制指令 (linear_velocity, angular_velocity)

控制频率: 200Hz
"""

import math
import sys
import time
from typing import Optional

from pydantic import BaseModel
from sdk.nodeflow_sdk import NodeFlowSDK
import atom


class VelocityCmd(BaseModel):
    linear_velocity: float
    angular_velocity: float


class ArcTrackerNode:
    """弧线跟踪控制器节点"""

    def __init__(self, sdk: NodeFlowSDK):
        self.sdk = sdk

        # 读取参数
        self.cruise_speed = float(sdk.get_param('cruise_speed', 1.0))
        self.min_speed = float(sdk.get_param('min_speed', 0.05))
        self.lookahead_base = float(sdk.get_param('lookahead_base', 1.0))
        self.lookahead_k = float(sdk.get_param('lookahead_k', 0.5))
        self.max_angular_velocity = float(sdk.get_param('max_angular_velocity', 1.5))
        pivot_deg = float(sdk.get_param('pivot_threshold_deg', 60.0))
        self.pivot_threshold_rad = math.radians(pivot_deg)
        self.curvature_decel_factor = float(sdk.get_param('curvature_decel_factor', 1.0))
        self.decel_distance = float(sdk.get_param('decel_distance', 2.0))
        self.stop_distance = float(sdk.get_param('stop_distance', 0.3))

        # 控制参数打包
        self.params = {
            'cruise_speed': self.cruise_speed,
            'min_speed': self.min_speed,
            'lookahead_base': self.lookahead_base,
            'lookahead_k': self.lookahead_k,
            'max_angular_velocity': self.max_angular_velocity,
            'pivot_threshold_rad': self.pivot_threshold_rad,
            'curvature_decel_factor': self.curvature_decel_factor,
            'decel_distance': self.decel_distance,
            'stop_distance': self.stop_distance,
        }

        # 创建端口
        self.in_bezier = sdk.create_input_port('bezier_path')
        self.in_pose = sdk.create_input_port('pose_enu')
        self.out_cmd = sdk.create_output_port('velocity_cmd', schema=VelocityCmd)

        # 状态
        self.segments = None
        self.pursuit_state = {'seg_idx': 0, 't': 0.0, 'initialized': False}
        self.last_pose = None
        self.path_task_id = None

        sdk.logger.info("=" * 60)
        sdk.logger.info("弧线跟踪控制器启动")
        sdk.logger.info(f"  巡航速度: {self.cruise_speed} m/s")
        sdk.logger.info(f"  前瞻距离: {self.lookahead_base} + {self.lookahead_k}*v")
        sdk.logger.info(f"  最大角速度: {self.max_angular_velocity} rad/s")
        sdk.logger.info(f"  原地转阈值: {pivot_deg}°")
        sdk.logger.info(f"  终点减速: {self.decel_distance}m, 停车: {self.stop_distance}m")
        sdk.logger.info("=" * 60)

    def run(self):
        """主循环: 200Hz 控制"""
        log_interval = 1.0  # 日志间隔
        last_log = 0.0
        cycle_count = 0

        try:
            while True:
                # 1. 读取贝塞尔路径（非阻塞）
                path_msg = self.in_bezier.recv_latest()
                if path_msg is not None:
                    new_task_id = path_msg.get('task_id')
                    new_segments = path_msg.get('segments', [])

                    if new_task_id != self.path_task_id and new_segments:
                        self.segments = new_segments
                        self.path_task_id = new_task_id
                        # 新路径：重置 pursuit state
                        self.pursuit_state = {
                            'seg_idx': 0, 't': 0.0, 'initialized': False
                        }
                        self.sdk.logger.info(
                            f"新路径: {len(new_segments)} 段, "
                            f"总长 {path_msg.get('total_length', 0):.1f}m"
                        )

                # 2. 读取位姿（非阻塞）
                pose_msg = self.in_pose.recv_latest()
                if pose_msg is not None:
                    self.last_pose = pose_msg

                # 3. 计算控制指令
                cmd = atom.compute_pursuit_cmd(
                    self.last_pose, self.segments,
                    self.pursuit_state, self.params
                )

                # 4. 发送速度指令
                self.out_cmd.send(cmd)

                cycle_count += 1

                # 5. 定期日志
                now = time.time()
                if now - last_log > log_interval:
                    status = cmd.get('status', 'unknown')
                    v = cmd.get('linear_velocity', 0)
                    w = cmd.get('angular_velocity', 0)
                    if self.last_pose and self.segments:
                        si = self.pursuit_state.get('seg_idx', 0)
                        t_val = self.pursuit_state.get('t', 0)
                        self.sdk.logger.debug(
                            f"[{status}] v={v:.2f} w={w:.2f} "
                            f"seg={si}/{len(self.segments)} t={t_val:.2f}"
                        )
                    elif not self.segments:
                        self.sdk.logger.debug("等待贝塞尔路径...")
                    elif not self.last_pose:
                        self.sdk.logger.debug("等待位姿数据...")
                    last_log = now

                time.sleep(0.005)  # 200Hz

        except KeyboardInterrupt:
            self.sdk.logger.info("用户中断，节点退出")
            # 发送停车指令
            self.out_cmd.send({
                'linear_velocity': 0.0,
                'angular_velocity': 0.0,
                'timestamp': time.time(),
                'status': 'stopped',
            })


def main():
    """节点主入口"""
    try:
        with NodeFlowSDK(log_level="INFO") as sdk:
            node = ArcTrackerNode(sdk)
            node.run()

    except KeyboardInterrupt:
        print("\nInterrupted by user")
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
