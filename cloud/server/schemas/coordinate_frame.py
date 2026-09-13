from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, Field


class CoordinateFrameUpdate(BaseModel):
    frame_id: str = Field(default="farm-base", min_length=1, max_length=128)
    origin_source: Literal["rtk_base_manual", "first_fixed_position"] = "rtk_base_manual"
    ref_lon: float = Field(..., ge=-180.0, le=180.0)
    ref_lat: float = Field(..., ge=-90.0, le=90.0)
    ref_alt: Optional[float] = None


class CoordinateFrameResponse(BaseModel):
    ready: bool
    type: Literal["ENU"] = "ENU"
    frame_id: Optional[str] = None
    origin_source: Optional[str] = None
    ref_lon: Optional[float] = None
    ref_lat: Optional[float] = None
    ref_alt: Optional[float] = None
    revision: Optional[int] = None
    updated_at: Optional[datetime] = None
