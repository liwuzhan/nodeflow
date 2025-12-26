#!/usr/bin/env python3
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
        self.path = []
        self.task_id = None
        self.index = 0

    @staticmethod
    def haversine(lat1, lon1, lat2, lon2):
        lat1, lon1, lat2, lon2 = map(math.radians, [lat1, lon1, lat2, lon2])
        dlat = lat2 - lat1
        dlon = lon2 - lon1
        a = math.sin(dlat/2)**2 + math.cos(lat1)*math.cos(lat2)*math.sin(dlon/2)**2
        return 6371000 * 2 * math.asin(math.sqrt(a))

    def set_path(self, pkt: dict):
        if not pkt or "path" not in pkt:
            return
        tid = pkt.get("task_id")
        if tid and tid == self.task_id:
            return
        coords = pkt["path"]
        self.path = [(lat, lon) for (lon, lat) in coords]
        self.task_id = tid
        self.index = 0

    def select(self, rtk: dict):
        if not self.path or not rtk:
            return None
        clat = rtk.get("latitude")
        clon = rtk.get("longitude")
        if clat is None or clon is None:
            return None

        # 只跳过当前点（如果在容差内），避免一次跳过太多点
        if self.index < len(self.path):
            lat, lon = self.path[self.index]
            d = self.haversine(clat, clon, lat, lon)
            if d < self.tol_m:
                self.index += 1

        # 到达终点
        if self.index >= len(self.path):
            return {"lat": self.path[-1][0], "lon": self.path[-1][1], "final": True}

        # 计算前瞻点
        acc = 0.0
        i = self.index
        target_lat, target_lon = self.path[i]

        while i + 1 < len(self.path) and acc < self.lookahead_m:
            a = self.path[i]
            b = self.path[i + 1]
            seg = self.haversine(a[0], a[1], b[0], b[1])
            acc += seg
            target_lat, target_lon = b
            i += 1

        is_final = (i >= len(self.path) - 1)
        return {"lat": target_lat, "lon": target_lon, "final": is_final, "index": self.index, "total": len(self.path)}


def main():
    with NodeFlowSDK(log_level="INFO") as sdk:
        lookahead = float(sdk.params.get("lookahead_distance_m", 2.0))
        tol = float(sdk.params.get("goal_tolerance_m", 0.3))
        selector = WaypointSelector(lookahead, tol)
        in_path = sdk.create_input_port("global_path")
        in_rtk = sdk.create_input_port("filtered_rtk")
        out_np = sdk.create_output_port("next_point")
        while True:
            path_pkt = in_path.recv_latest()
            if path_pkt:
                selector.set_path(path_pkt)
            rtk = in_rtk.recv_latest()
            npkt = selector.select(rtk)
            if npkt:
                out_np.send(npkt)
            time.sleep(0.02)


if __name__ == "__main__":
    main()

