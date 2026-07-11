import uuid
from datetime import datetime, timezone

from sqlalchemy import Column, String, Integer, Float, DateTime, ForeignKey, JSON, UniqueConstraint
from sqlalchemy.dialects.sqlite import CHAR

from cloud.server.database import Base


def _uuid():
    return str(uuid.uuid4())


def _utcnow():
    return datetime.now(timezone.utc)


class EdgeTask(Base):
    __tablename__ = "edge_tasks"
    __table_args__ = (
        UniqueConstraint("step_id", "parcel_split_id", name="uq_edge_task_step_split"),
    )

    id = Column(CHAR(36), primary_key=True, default=_uuid)
    edge_task_id = Column(String(128), unique=True, nullable=False)
    job_id = Column(String(128), ForeignKey("jobs.id"), nullable=False, index=True)
    step_id = Column(CHAR(36), ForeignKey("job_steps.id"), nullable=True)
    machine_id = Column(String(64), ForeignKey("machines.id"), nullable=False, index=True)
    parcel_split_id = Column(CHAR(36), ForeignKey("parcel_splits.id"), nullable=True)
    dispatch_id = Column(String(128), nullable=True)
    protocol_version = Column(String(16), nullable=False, default="1.0")
    planning_mode = Column(String(24), nullable=False, default="edge")
    fallback_policy = Column(String(32), nullable=False, default="deny")
    plan_id = Column(String(128), nullable=True)
    plan_revision = Column(Integer, nullable=False, default=0)
    path_checksum = Column(String(64), nullable=True)
    field_revision = Column(Integer, nullable=False, default=1)
    field_checksum = Column(String(64), nullable=True)
    coordinate_frame = Column(JSON, nullable=False, default=dict)
    operation_config = Column(JSON, nullable=False, default=dict)
    operation_type = Column(String(32), nullable=False)
    seq_index = Column(Integer, default=0)
    preset_yaml = Column(String(128), nullable=False)
    state = Column(String(32), default="queued")
    desired_state = Column(String(32), default="running")
    progress_pct = Column(Float, default=0.0)
    current_node = Column(String(128), nullable=True)
    attempt = Column(Integer, default=1)
    last_dispatch_at = Column(Float, nullable=True)
    dispatched_at = Column(Float, nullable=True)
    completed_at = Column(Float, nullable=True)
    error_code = Column(String(64), nullable=True)
    error_detail = Column(String(512), nullable=True)
    created_at = Column(DateTime, default=_utcnow)
