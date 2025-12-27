#!/usr/bin/env python3
"""
路径点选择器（ENU版本）
从全局路径中选择前瞻点
"""
import sys
import time
import math
from pathlib import Path

project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from sdk.nodeflow_sdk import NodeFlowSDK


class WaypointSelector:
    def __init__(self, lookahead_m: float, tol_m: float):
        self.lookahead_m = lookahead_m
        self.tol_m = tol_m
        self.path = []  # ENU路径 [(x, y), ...]
        self.task_id = None
        self.index = 0

    @staticmethod
    def euclidean_distance(x1, y1, x2, y2):
        """欧几里得距离（米）"""
        return math.sqrt((x2 - x1)**2 + (y2 - y1)**2)

    def set_path(self, pkt: dict):
        if not pkt or "path" not in pkt:
            return
        tid = pkt.get("task_id")
        if tid and tid == self.task_id:
            return
        # ENU路径: [(x, y), ...]
        self.path = pkt["path"]
        self.task_id = tid
        self.index = 0

    def select(self, pose_enu: dict):
        """选择前瞻点（ENU坐标系）"""
        if not self.path or not pose_enu:
            return None

        cx = pose_enu.get("x")
        cy = pose_enu.get("y")
        if cx is None or cy is None:
            return None

        # 跳过已到达的点
        if self.index < len(self.path):
            x, y = self.path[self.index]
            d = self.euclidean_distance(cx, cy, x, y)
            if d < self.tol_m:
                self.index += 1

        # 到达终点
        if self.index >= len(self.path):
            final_x, final_y = self.path[-1]
            return {"x": final_x, "y": final_y, "final": True}

        # 计算前瞻点
        acc = 0.0
        i = self.index
        target_x, target_y = self.path[i]

        while i + 1 < len(self.path) and acc < self.lookahead_m:
            ax, ay = self.path[i]
            bx, by = self.path[i + 1]
            seg = self.euclidean_distance(ax, ay, bx, by)
            acc += seg
            target_x, target_y = bx, by
            i += 1

        is_final = (i >= len(self.path) - 1)
        return {
            "x": target_x,
            "y": target_y,
            "final": is_final,
            "index": self.index,
            "total": len(self.path)
        }


def main():
    with NodeFlowSDK(log_level="INFO") as sdk:
        sdk.logger.info("Waypoint Selector Node started (ENU coordinates)")

        lookahead = float(sdk.params.get("lookahead_distance_m", 2.0))
        tol = float(sdk.params.get("goal_tolerance_m", 0.3))

        sdk.logger.info(f"前瞻距离: {lookahead}m, 到达容差: {tol}m")

        selector = WaypointSelector(lookahead, tol)

        in_path = sdk.create_input_port("global_path")
        in_pose = sdk.create_input_port("pose_enu")
        out_np = sdk.create_output_port("next_point")

        while True:
            path_pkt = in_path.recv_latest()
            if path_pkt:
                selector.set_path(path_pkt)

            pose = in_pose.recv_latest()
            npkt = selector.select(pose)
            if npkt:
                out_np.send(npkt)

            time.sleep(0.02)


if __name__ == "__main__":
    main()
