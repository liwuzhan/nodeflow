#!/usr/bin/env python3
import time
from typing import Optional

# Pydantic 导入
try:
    from pydantic import BaseModel, Field
except ImportError:
    class BaseModel: pass
    def Field(*args, **kwargs): return None

from edge.sdk.nodeflow_sdk import NodeFlowSDK
if __package__:
    from .atom import EMAFilter
else:
    from atom import EMAFilter

class WireModel(BaseModel):
    # 保留采样序号、解状态以及上游时间来源等诊断字段。
    if hasattr(BaseModel, "model_validate"):
        model_config = {"extra": "allow", "populate_by_name": True}
    else:
        class Config:
            extra = "allow"
            allow_population_by_field_name = True


class RTKFix(WireModel):
    timestamp: float
    seq: Optional[int] = None
    lat: float = Field(..., ge=-90, le=90, alias="latitude")
    lon: float = Field(..., ge=-180, le=180, alias="longitude")
    heading: Optional[float] = Field(default=None, ge=0, le=360)
    heading_valid: Optional[bool] = None
    heading_mode: Optional[str] = None
    rtk_status: str | int | None = None
    timestamp_source: Optional[str] = None


class FilteredRTK(WireModel):
    timestamp: float
    lat: float = Field(..., ge=-90, le=90)
    lon: float = Field(..., ge=-180, le=180)
    heading: float = Field(..., ge=0, le=360)
    rtk_status: str | int | None = None
    satellites: Optional[int] = None
    precision: Optional[float] = None
    seq: Optional[int] = None
    heading_valid: Optional[bool] = None
    heading_mode: Optional[str] = None
    timestamp_source: Optional[str] = None


def main():
    with NodeFlowSDK(log_level="INFO") as sdk:
        alpha_pos = float(sdk.params.get("alpha_pos", 0.2))
        alpha_heading = float(sdk.params.get("alpha_heading", 0.3))
        use_imu_yaw_rate = bool(sdk.params.get("use_imu_yaw_rate", False))
        
        # 滤波仅消费新到的RTK样本。
        filt = EMAFilter(alpha_pos, alpha_heading, use_imu_yaw_rate)
        
        in_rtk = sdk.create_input_port("rtk_fix")
        out = sdk.create_output_port("filtered_rtk", schema=FilteredRTK)
        
        while True:
            rtk = in_rtk.recv_latest()
            imu = None
            
            # 只有上游没有设备时间时才使用本地时间。
            now = time.time()
            res = filt.update(rtk, imu, now)
            
            if res:
                out.send(res)
            time.sleep(0.005)  # 200Hz


if __name__ == "__main__":
    main()
