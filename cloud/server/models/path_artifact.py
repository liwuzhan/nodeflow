import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    Column, DateTime, ForeignKey, Integer, JSON, LargeBinary, String, UniqueConstraint,
)
from sqlalchemy.dialects.sqlite import CHAR

from cloud.server.database import Base


def _uuid():
    return str(uuid.uuid4())


def _utcnow():
    return datetime.now(timezone.utc)


class PathArtifact(Base):
    __tablename__ = "path_artifacts"
    __table_args__ = (
        UniqueConstraint("edge_task_id", "revision", name="uq_path_artifact_task_revision"),
    )

    id = Column(CHAR(36), primary_key=True, default=_uuid)
    edge_task_id = Column(String(128), ForeignKey("edge_tasks.edge_task_id"), nullable=False)
    revision = Column(Integer, nullable=False, default=1)
    planner_version = Column(String(64), nullable=False)
    field_checksum = Column(String(64), nullable=False)
    coordinate_frame = Column(JSON, nullable=False, default=dict)
    payload = Column(LargeBinary, nullable=False)
    checksum = Column(String(64), nullable=False)
    metrics = Column(JSON, nullable=False, default=dict)
    created_at = Column(DateTime, default=_utcnow)
