#!/usr/bin/env python3
import sys
import time
import math
from pathlib import Path

project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from sdk.nodeflow_sdk import NodeFlowSDK
from sdk.shared_buffer_lite import SharedBufferLite


def haversine_m(lat1, lon1, lat2, lon2):
    lat1, lon1, lat2, lon2 = map(math.radians, [lat1, lon1, lat2, lon2])
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    a = math.sin(dlat/2)**2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon/2)**2
    c = 2 * math.asin(math.sqrt(a))
    return 6371000.0 * c


class IdleDetector:
    def __init__(self, sdk: NodeFlowSDK):
        p = sdk.params
        self.window_secs = float(p.get("window_secs", 60.0))
        self.idle_radius_m = float(p.get("idle_radius_m", 1.0))
        self.sample_rate_hz = float(p.get("sample_rate_hz", 5.0))
        self.debounce_secs = float(p.get("debounce_secs", 5.0))
        self.rtk_port = sdk.create_input_port("rtk_fix")
        self.idle_event_port = sdk.create_output_port("idle_event")
        self.samples = []
        self.last_trigger_time = 0.0
        self.shutdown_buf = SharedBufferLite("control.shutdown_request", create=True)

    def update(self, rtk: dict):
        if not rtk:
            return False
        t = time.time()
        lat = rtk.get("latitude")
        lon = rtk.get("longitude")
        if lat is None or lon is None:
            return False
        self.samples.append((t, lat, lon))
        cutoff = t - self.window_secs
        while self.samples and self.samples[0][0] < cutoff:
            self.samples.pop(0)
        if len(self.samples) < 2:
            return False
        window_cov = self.samples[-1][0] - self.samples[0][0]
        if window_cov < self.window_secs:
            return False
        lats = [s[1] for s in self.samples]
        lons = [s[2] for s in self.samples]
        lat_min, lat_max = min(lats), max(lats)
        lon_min, lon_max = min(lons), max(lons)
        d1 = haversine_m(lat_min, lon_min, lat_max, lon_max)
        if d1 >= self.idle_radius_m:
            return False
        if (t - self.last_trigger_time) < self.debounce_secs:
            return False
        self.last_trigger_time = t
        return True

    def run(self):
        interval = 1.0 / max(1e-6, self.sample_rate_hz)
        try:
            while True:
                t0 = time.time()
                rtk = self.rtk_port.recv_latest()
                if self.update(rtk):
                    evt = {
                        "shutdown": True,
                        "reason": "idle",
                        "window_secs": self.window_secs,
                        "idle_radius_m": self.idle_radius_m,
                        "timestamp": time.time(),
                    }
                    self.idle_event_port.send(evt)
                    try:
                        self.shutdown_buf.write(evt)
                    except Exception:
                        pass
                dt = time.time() - t0
                if dt < interval:
                    time.sleep(interval - dt)
        except KeyboardInterrupt:
            pass
        finally:
            try:
                self.shutdown_buf.close()
            except Exception:
                pass


def main():
    with NodeFlowSDK(log_level="INFO") as sdk:
        node = IdleDetector(sdk)
        node.run()


if __name__ == "__main__":
    main()

