import uuid
from datetime import datetime, timezone

from sqlalchemy import Column, String, Integer, DateTime, ForeignKey, JSON
from sqlalchemy.dialects.sqlite import CHAR
from sqlalchemy.orm import relationship

from cloud.server.database import Base


def _uuid():
    return str(uuid.uuid4())


def _utcnow():
    return datetime.now(timezone.utc)


class Job(Base):
    __tablename__ = "jobs"

    id = Column(String(128), primary_key=True)
    name = Column(String(256), nullable=False)
    parcel_id = Column(CHAR(36), nullable=False, index=True)
    status = Column(String(16), default="draft")
    split_mode = Column(String(16), default="strip")
    split_count = Column(Integer, default=1)
    machine_assignments = Column(JSON, default=dict)
    created_at = Column(DateTime, default=_utcnow)
    updated_at = Column(DateTime, default=_utcnow, onupdate=_utcnow)

    steps = relationship("JobStep", back_populates="job", cascade="all, delete-orphan",
                         order_by="JobStep.seq_index")


class JobStep(Base):
    __tablename__ = "job_steps"

    id = Column(CHAR(36), primary_key=True, default=_uuid)
    job_id = Column(String(128), ForeignKey("jobs.id"), nullable=False, index=True)
    seq_index = Column(Integer, nullable=False)
    operation_type = Column(String(32), nullable=False)
    preset_yaml = Column(String(128), nullable=False)
    depends_on = Column(Integer, nullable=True)
    status = Column(String(16), default="pending")
    created_at = Column(DateTime, default=_utcnow)

    job = relationship("Job", back_populates="steps")
