#!/usr/bin/env python3
import sys
import time
import math
from pathlib import Path

project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from sdk.nodeflow_sdk import NodeFlowSDK


class EMAFilter:
    def __init__(self, alpha_pos: float, alpha_heading: float, use_imu_yaw_rate: bool):
        self.alpha_pos = alpha_pos
        self.alpha_heading = alpha_heading
        self.use_imu_yaw_rate = use_imu_yaw_rate
        self.lat = None
        self.lon = None
        self.heading_deg = None
        self.last_time = None

    def update(self, rtk: dict, imu: dict | None):
        if not rtk:
            return None
        lat = rtk.get("latitude")
        lon = rtk.get("longitude")
        heading = rtk.get("heading")
        if lat is None or lon is None:
            return None
        now = time.time()
        if self.lat is None:
            self.lat = float(lat)
            self.lon = float(lon)
            self.heading_deg = float(heading) if heading is not None else None
            self.last_time = now
        else:
            self.lat = self.alpha_pos * float(lat) + (1 - self.alpha_pos) * self.lat
            self.lon = self.alpha_pos * float(lon) + (1 - self.alpha_pos) * self.lon
            if heading is not None:
                h = float(heading)
                if self.heading_deg is None:
                    self.heading_deg = h
                else:
                    # wrap-aware EMA
                    e = math.radians(h - self.heading_deg)
                    while e > math.pi: e -= 2 * math.pi
                    while e < -math.pi: e += 2 * math.pi
                    self.heading_deg = self.heading_deg + math.degrees(self.alpha_heading * e)
            if self.use_imu_yaw_rate and imu:
                yaw_rate = imu.get("gyro_z")
                dt = now - (self.last_time or now)
                if yaw_rate is not None and dt > 0 and self.heading_deg is not None:
                    self.heading_deg += math.degrees(float(yaw_rate) * dt)
            self.last_time = now
        out = dict(rtk)
        out["latitude"] = self.lat
        out["longitude"] = self.lon
        if self.heading_deg is not None:
            out["heading"] = (self.heading_deg % 360.0)
        out["timestamp"] = now
        return out


def main():
    with NodeFlowSDK(log_level="INFO") as sdk:
        alpha_pos = float(sdk.params.get("alpha_pos", 0.2))
        alpha_heading = float(sdk.params.get("alpha_heading", 0.3))
        use_imu_yaw_rate = bool(sdk.params.get("use_imu_yaw_rate", False))
        filt = EMAFilter(alpha_pos, alpha_heading, use_imu_yaw_rate)
        in_rtk = sdk.create_input_port("rtk_fix")
        in_imu = None
        out = sdk.create_output_port("filtered_rtk")
        while True:
            rtk = in_rtk.recv_latest()
            imu = None
            res = filt.update(rtk, imu)
            if res:
                out.send(res)
            time.sleep(0.02)


if __name__ == "__main__":
    main()
