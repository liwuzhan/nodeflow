from datetime import datetime, timezone

from sqlalchemy import Column, String, Float, DateTime

from cloud.server.database import Base


def _utcnow():
    return datetime.now(timezone.utc)


class Machine(Base):
    __tablename__ = "machines"

    id = Column(String(64), primary_key=True)
    name = Column(String(128), nullable=False)
    machine_type = Column(String(32), default="tractor")
    implement_width_m = Column(Float, default=2.0)
    status = Column(String(16), default="offline")
    last_heartbeat = Column(DateTime, nullable=True)
    current_task_id = Column(String(128), nullable=True)
    current_job_id = Column(String(128), nullable=True)
    position_lon = Column(Float, nullable=True)
    position_lat = Column(Float, nullable=True)
    cpu_pct = Column(Float, default=0.0)
    memory_mb = Column(Float, default=0.0)
    disk_free_gb = Column(Float, default=0.0)
    runtime_uptime_s = Column(Float, default=0.0)
    registered_at = Column(DateTime, default=_utcnow)
    updated_at = Column(DateTime, default=_utcnow, onupdate=_utcnow)
