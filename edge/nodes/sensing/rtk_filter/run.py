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

from edge.sdk.nodeflow_sdk import NodeFlowSDK
from atom import EMAFilter

# --- Schema Definitions ---

class RTKFix(BaseModel):
    timestamp: float
    seq: int
    lat: float = Field(..., ge=-90, le=90, alias="latitude") # sim_output uses lat/lon, but filter uses latitude/longitude dict keys internally? Need to align. 
    # Checking sim_output again, it sends `rtk_data` from simulator which likely uses `latitude`/`longitude`.
    # Let's support both or align. The sim_output schema used `lat`/`lon`.
    # The `rtk_filter` code accesses `rtk.get("latitude")`.
    # This suggests `sim_output` might be sending `latitude` but defining schema as `lat`. 
    # Wait, sim_output schema for `rtk_fix` uses `lat`.
    # Let's check sim_output code `_get_sensor("rtk_gps")`. It returns whatever simulator returns.
    # Assuming simulator returns `latitude`/`longitude`.
    # Let's define schema here to match what `rtk_filter` expects and produces.
    # The `sim_output` defined schema `RTKFix` with `lat`/`lon`.
    # If `sim_output` actually sends `latitude`/`longitude` dict, then `sim_output` schema validation would fail if strict.
    # Let's assume standardization to `lat`/`lon` is desired, but for now we must match code.
    # The filter code reads `latitude`. So input must have `latitude`.
    # Let's alias fields to support both or use loose validation.
    
    # Correction: In `sim_output/run.py` schema `RTKFix` used `lat`/`lon`.
    # But `rtk_filter/run.py` uses `rtk.get("latitude")`.
    # This implies a mismatch if schema is enforced.
    # However, since `sim_output` is just passing through `_get_sensor("rtk_gps")`, likely the simulator returns `latitude`.
    # I should probably update `sim_output` schema to use `latitude` if that's what's on wire, OR update `rtk_filter` to use `lat`.
    # For this task, I will update `rtk_filter` to accept `lat` OR `latitude`.
    # Actually, `sim_output` schema defined `lat`. If `sim_output` sends `latitude`, its own validation would fail.
    # Let's stick to standardizing on `lat`/`lon` as per `sim_output` schema attempt.
    # BUT `rtk_filter` logic: `lat = rtk.get("latitude")`.
    # I will update `rtk_filter` logic to use `lat` to match the schema I just added to `sim_output`.
    
    lat: float = Field(..., ge=-90, le=90)
    lon: float = Field(..., ge=-180, le=180)
    alt: float = Field(default=0.0)
    heading: float = Field(..., ge=0, le=360)
    rtk_status: Optional[int] = None
    satellites: Optional[int] = None
    precision: Optional[float] = None

class FilteredRTK(BaseModel):
    timestamp: float
    lat: float = Field(..., ge=-90, le=90)
    lon: float = Field(..., ge=-180, le=180)
    heading: float = Field(..., ge=0, le=360)
    rtk_status: Optional[int] = None
    satellites: Optional[int] = None
    precision: Optional[float] = None
    # Original code copies input dict, so it might have seq etc.
    seq: Optional[int] = None

# --- End Schema Definitions ---

def main():
    with NodeFlowSDK(log_level="INFO") as sdk:
        alpha_pos = float(sdk.params.get("alpha_pos", 0.2))
        alpha_heading = float(sdk.params.get("alpha_heading", 0.3))
        use_imu_yaw_rate = bool(sdk.params.get("use_imu_yaw_rate", False))
        
        # Initialize L4 Atom
        filt = EMAFilter(alpha_pos, alpha_heading, use_imu_yaw_rate)
        
        in_rtk = sdk.create_input_port("rtk_fix")
        in_imu = None
        out = sdk.create_output_port("filtered_rtk", schema=FilteredRTK)
        
        while True:
            rtk = in_rtk.recv_latest()
            # Convert schema object to dict if necessary (SDK handles this for output, but for input recv_latest returns dict or object?)
            # SDK recv_latest currently returns dict (deserialized json). 
            # If we want type safety on input, we might need to parse it. 
            # But here we just use it as dict.
            
            imu = None
            
            # Pass explicit time to atom (deterministic)
            now = time.time()
            res = filt.update(rtk, imu, now)
            
            if res:
                out.send(res)
            time.sleep(0.005)  # 200Hz


if __name__ == "__main__":
    main()
