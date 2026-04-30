import uuid
from datetime import datetime, timezone

from sqlalchemy import Column, String, Integer, Float, DateTime
from sqlalchemy.dialects.sqlite import CHAR

from cloud.server.database import Base


def _uuid():
    return str(uuid.uuid4())


def _utcnow():
    return datetime.now(timezone.utc)


class EdgeTask(Base):
    __tablename__ = "edge_tasks"

    id = Column(CHAR(36), primary_key=True, default=_uuid)
    edge_task_id = Column(String(128), unique=True, nullable=False)
    job_id = Column(String(128), nullable=False, index=True)
    step_id = Column(CHAR(36), nullable=True)
    machine_id = Column(String(64), nullable=False, index=True)
    parcel_split_id = Column(CHAR(36), nullable=True)
    dispatch_id = Column(String(128), nullable=True)
    operation_type = Column(String(32), nullable=False)
    seq_index = Column(Integer, default=0)
    preset_yaml = Column(String(128), nullable=False)
    state = Column(String(16), default="pending")
    progress_pct = Column(Float, default=0.0)
    current_node = Column(String(128), nullable=True)
    attempt = Column(Integer, default=1)
    dispatched_at = Column(Float, nullable=True)
    completed_at = Column(Float, nullable=True)
    error_code = Column(String(64), nullable=True)
    error_detail = Column(String(512), nullable=True)
    created_at = Column(DateTime, default=_utcnow)
