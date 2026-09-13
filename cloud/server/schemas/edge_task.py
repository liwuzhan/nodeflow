from __future__ import annotations
from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field


class EdgeTaskResponse(BaseModel):
    id: str
    edge_task_id: str
    job_id: str
    step_id: Optional[str] = None
    machine_id: str
    dispatch_id: Optional[str] = None
    protocol_version: str = "1.0"
    planning_mode: str = "edge"
    fallback_policy: str = "deny"
    plan_id: Optional[str] = None
    plan_revision: int = 0
    field_revision: int = 1
    field_checksum: Optional[str] = None
    coordinate_frame: dict = Field(default_factory=dict)
    operation_config: dict = Field(default_factory=dict)
    operation_type: str
    seq_index: int
    preset_yaml: str
    state: str
    desired_state: str = "running"
    progress_pct: float
    current_node: Optional[str] = None
    attempt: int
    last_dispatch_at: Optional[float] = None
    dispatched_at: Optional[float] = None
    completed_at: Optional[float] = None
    error_code: Optional[str] = None
    error_detail: Optional[str] = None
    created_at: Optional[datetime] = None

    model_config = {"from_attributes": True}
