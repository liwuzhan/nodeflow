from __future__ import annotations
from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel, Field


class JobStepCreate(BaseModel):
    operation_type: str = "tillage"
    preset_yaml: str = "planning_with_real_rtk"
    seq_index: int = 0
    depends_on: Optional[int] = None
    planning_mode: str = "edge"
    fallback_policy: str = "deny"
    operation_config: dict = Field(default_factory=dict)
    machine_assignments: dict[str, str] = Field(default_factory=dict)


class JobCreate(BaseModel):
    name: Optional[str] = None
    parcel_id: str
    split_mode: str = "strip"
    split_count: int = 1
    steps: List[JobStepCreate]
    machine_assignments: dict[str, str] = Field(default_factory=dict)


class JobStepResponse(BaseModel):
    id: str
    seq_index: int
    operation_type: str
    preset_yaml: str
    depends_on: Optional[int] = None
    planning_mode: str = "edge"
    fallback_policy: str = "deny"
    operation_config: dict = Field(default_factory=dict)
    machine_assignments: dict[str, str] = Field(default_factory=dict)
    status: str

    model_config = {"from_attributes": True}


class EdgeTaskSummary(BaseModel):
    id: str
    edge_task_id: str
    machine_id: str
    step_id: Optional[str] = None
    seq_index: int = 0
    operation_type: str = ""
    state: str
    progress_pct: float
    error_code: Optional[str] = None

    model_config = {"from_attributes": True}


class JobResponse(BaseModel):
    id: str
    name: str
    parcel_id: str
    status: str
    split_mode: str
    split_count: int
    created_at: Optional[datetime] = None
    steps: List[JobStepResponse] = []

    model_config = {"from_attributes": True}


class JobDetailResponse(JobResponse):
    splits: list = []
    edge_tasks: List[EdgeTaskSummary] = []


class JobDispatchRequest(BaseModel):
    machine_assignments: Optional[dict[str, str]] = None
