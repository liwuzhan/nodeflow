import uuid
from datetime import datetime, timezone

from sqlalchemy import Column, String, Float, JSON, DateTime, ForeignKey
from sqlalchemy.dialects.sqlite import CHAR
from sqlalchemy.orm import relationship

from cloud.server.database import Base


def _uuid():
    return str(uuid.uuid4())


def _utcnow():
    return datetime.now(timezone.utc)


class Parcel(Base):
    __tablename__ = "parcels"

    id = Column(CHAR(36), primary_key=True, default=_uuid)
    name = Column(String(128), unique=True, nullable=False)
    geojson = Column(JSON, nullable=False)
    area_ha = Column(Float, default=0.0)
    vehicle_cfg = Column(JSON, default=dict)
    ref_point = Column(JSON, default=dict)
    created_at = Column(DateTime, default=_utcnow)
    updated_at = Column(DateTime, default=_utcnow, onupdate=_utcnow)

    splits = relationship("ParcelSplit", back_populates="parcel", cascade="all, delete-orphan")


class ParcelSplit(Base):
    __tablename__ = "parcel_splits"

    id = Column(CHAR(36), primary_key=True, default=_uuid)
    parcel_id = Column(CHAR(36), ForeignKey("parcels.id"), nullable=False, index=True)
    job_id = Column(String(128), nullable=True, index=True)
    index = Column(Float, nullable=False, default=0)
    name = Column(String(256))
    geojson = Column(JSON, nullable=False)
    area_ha = Column(Float, default=0.0)
    assigned_to = Column(String(64), nullable=True)
    created_at = Column(DateTime, default=_utcnow)

    parcel = relationship("Parcel", back_populates="splits")
