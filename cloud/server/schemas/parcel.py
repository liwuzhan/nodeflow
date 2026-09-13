from __future__ import annotations
from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel, Field


class VehicleConfig(BaseModel):
    implement_width_m: float = 2.0
    overlap_ratio: float = 0.1
    path_inset_m: float = 0.5


class RefPoint(BaseModel):
    lon: float = Field(..., ge=-180.0, le=180.0)
    lat: float = Field(..., ge=-90.0, le=90.0)
    alt: Optional[float] = None
    frame_id: Optional[str] = None
    origin_source: Optional[str] = None
    revision: Optional[int] = None


class ParcelCreate(BaseModel):
    name: str = Field(..., max_length=128)
    geojson: dict
    vehicle_cfg: VehicleConfig = Field(default_factory=VehicleConfig)
    ref_point: Optional[RefPoint] = None


class ParcelUpdate(BaseModel):
    name: Optional[str] = Field(None, max_length=128)
    geojson: Optional[dict] = None
    vehicle_cfg: Optional[VehicleConfig] = None
    ref_point: Optional[RefPoint] = None


class ParcelSummary(BaseModel):
    id: str
    name: str
    area_ha: float
    created_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class ParcelResponse(BaseModel):
    id: str
    name: str
    geojson: dict
    area_ha: float
    vehicle_cfg: dict
    ref_point: dict
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class SubParcel(BaseModel):
    index: int
    name: str
    geojson: dict
    area_ha: float
    assigned_machine: Optional[str] = None


class SplitPreviewRequest(BaseModel):
    mode: str = "strip"
    count: int = 1
    angle_deg: Optional[float] = None
    machine_assignments: Optional[dict[str, str]] = None


class SplitPreviewResponse(BaseModel):
    sub_parcels: List[SubParcel]
