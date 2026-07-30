#!/usr/bin/env python3
import time
import math
from typing import Optional

# Pydantic 导入
try:
    from pydantic import BaseModel, Field
except ImportError:
    class BaseModel: pass
    def Field(*args, **kwargs): return None

from sdk.nodeflow_sdk import NodeFlowSDK
from sdk.shared_buffer_lite import SharedBufferLite
from atom import IdleDetectorLogic

# --- Schema Definitions ---

class RTKFix(BaseModel):
    timestamp: float
    lat: float = Field(..., ge=-90, le=90, alias="latitude")
    lon: float = Field(..., ge=-180, le=180, alias="longitude")
    heading: Optional[float] = None
    rtk_status: Optional[int] = None

class IdleEvent(BaseModel):
    shutdown: bool
    reason: str
    window_secs: float
    idle_radius_m: float
    timestamp: float

# --- End Schema Definitions ---

class IdleDetectorNode:
    def __init__(self, sdk: NodeFlowSDK):
        p = sdk.params
        self.window_secs = float(p.get("window_secs", 60.0))
        self.idle_radius_m = float(p.get("idle_radius_m", 1.0))
        self.sample_rate_hz = float(p.get("sample_rate_hz", 5.0))
        self.debounce_secs = float(p.get("debounce_secs", 5.0))
        
        # Initialize L4 Logic
        self.logic = IdleDetectorLogic(self.window_secs, self.idle_radius_m, self.debounce_secs)
        
        self.rtk_port = sdk.create_input_port("rtk_fix")
        self.idle_event_port = sdk.create_output_port("idle_event", schema=IdleEvent)
        
        self.shutdown_buf = SharedBufferLite("control.shutdown_request", create=True)

    def run(self):
        interval = 1.0 / max(1e-6, self.sample_rate_hz)
        try:
            while True:
                t0 = time.time()
                rtk = self.rtk_port.recv_latest()
                
                # Call L4 Logic
                is_idle = self.logic.update(rtk, t0)
                
                if is_idle:
                    evt = {
                        "shutdown": True,
                        "reason": "idle",
                        "window_secs": self.window_secs,
                        "idle_radius_m": self.idle_radius_m,
                        "timestamp": t0,
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
        node = IdleDetectorNode(sdk)
        node.run()


if __name__ == "__main__":
    main()

