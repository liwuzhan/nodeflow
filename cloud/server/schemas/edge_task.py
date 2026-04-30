from __future__ import annotations
from datetime import datetime
from typing import Optional
from pydantic import BaseModel


class EdgeTaskResponse(BaseModel):
    id: str
    edge_task_id: str
    job_id: str
    step_id: Optional[str] = None
    machine_id: str
    dispatch_id: Optional[str] = None
    operation_type: str
    seq_index: int
    preset_yaml: str
    state: str
    progress_pct: float
    current_node: Optional[str] = None
    attempt: int
    dispatched_at: Optional[float] = None
    completed_at: Optional[float] = None
    error_code: Optional[str] = None
    error_detail: Optional[str] = None
    created_at: Optional[datetime] = None

    model_config = {"from_attributes": True}
