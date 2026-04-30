from __future__ import annotations
from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field


class MachineCreate(BaseModel):
    id: str = Field(..., max_length=64)
    name: str = Field(..., max_length=128)
    machine_type: str = "tractor"
    implement_width_m: float = 2.0
    position_lon: Optional[float] = None
    position_lat: Optional[float] = None


class MachineUpdate(BaseModel):
    name: Optional[str] = Field(None, max_length=128)
    machine_type: Optional[str] = None
    implement_width_m: Optional[float] = None
    position_lon: Optional[float] = None
    position_lat: Optional[float] = None


class MachineResponse(BaseModel):
    id: str
    name: str
    machine_type: str
    status: str
    last_heartbeat: Optional[datetime] = None
    current_task_id: Optional[str] = None
    current_job_id: Optional[str] = None
    position_lon: Optional[float] = None
    position_lat: Optional[float] = None
    cpu_pct: float = 0.0
    memory_mb: float = 0.0
    disk_free_gb: float = 0.0
    runtime_uptime_s: float = 0.0
    seconds_since_heartbeat: Optional[float] = None

    model_config = {"from_attributes": True}
