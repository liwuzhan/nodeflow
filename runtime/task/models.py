from dataclasses import dataclass, field
from typing import Optional, Dict, Any, List
from enum import Enum
import time


class TaskState(str, Enum):
    PENDING = "pending"
    DOWNLOADING = "downloading"
    READY = "ready"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class Task:
    task_id: str
    preset_yaml: str
    job_id: str = ""
    operation_type: str = ""
    sequence_index: int = 0
    machine_id: str = ""

    parcel_ref: Optional[str] = None
    parcel_data: Optional[Dict[str, Any]] = None
    parcel_url: Optional[str] = None
    path_url: Optional[str] = None

    node_params: Dict[str, Dict[str, Any]] = field(default_factory=dict)

    created_at: float = 0.0
    started_at: Optional[float] = None
    completed_at: Optional[float] = None

    state: TaskState = TaskState.PENDING
    error_message: Optional[str] = None

    def __post_init__(self):
        if self.created_at == 0.0:
            self.created_at = time.time()

    def to_dict(self) -> dict:
        return {
            "task_id": self.task_id,
            "job_id": self.job_id,
            "preset_yaml": self.preset_yaml,
            "operation_type": self.operation_type,
            "sequence_index": self.sequence_index,
            "machine_id": self.machine_id,
            "parcel_ref": self.parcel_ref,
            "parcel_data": self.parcel_data,
            "parcel_url": self.parcel_url,
            "path_url": self.path_url,
            "node_params": self.node_params,
            "created_at": self.created_at,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "state": self.state.value,
            "error_message": self.error_message,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "Task":
        state = d.get("state", "pending")
        if isinstance(state, str):
            state = TaskState(state)
        return cls(
            task_id=d["task_id"],
            job_id=d.get("job_id", ""),
            preset_yaml=d.get("preset_yaml", ""),
            operation_type=d.get("operation_type", ""),
            sequence_index=d.get("sequence_index", 0),
            machine_id=d.get("machine_id", ""),
            parcel_ref=d.get("parcel_ref"),
            parcel_data=d.get("parcel_data"),
            parcel_url=d.get("parcel_url"),
            path_url=d.get("path_url"),
            node_params=d.get("node_params", {}),
            created_at=d.get("created_at", time.time()),
            started_at=d.get("started_at"),
            completed_at=d.get("completed_at"),
            state=state,
            error_message=d.get("error_message"),
        )


@dataclass
class TaskProgress:
    task_id: str
    machine_id: str = ""
    state: TaskState = TaskState.PENDING
    progress_pct: float = 0.0
    current_node: str = ""
    nodes_healthy: int = 0
    nodes_total: int = 0
    timestamp: float = 0.0

    def __post_init__(self):
        if self.timestamp == 0.0:
            self.timestamp = time.time()

    def to_dict(self) -> dict:
        return {
            "task_id": self.task_id,
            "machine_id": self.machine_id,
            "state": self.state.value,
            "progress_pct": self.progress_pct,
            "current_node": self.current_node,
            "nodes_healthy": self.nodes_healthy,
            "nodes_total": self.nodes_total,
            "timestamp": self.timestamp,
        }
