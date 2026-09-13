from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, Float, Integer, String

from cloud.server.database import Base


def _utcnow():
    return datetime.now(timezone.utc)


class CoordinateFrame(Base):
    __tablename__ = "coordinate_frames"

    id = Column(String(32), primary_key=True, default="farm")
    frame_id = Column(String(128), nullable=False)
    origin_source = Column(String(32), nullable=False, default="rtk_base_manual")
    ref_lon = Column(Float, nullable=False)
    ref_lat = Column(Float, nullable=False)
    ref_alt = Column(Float, nullable=True)
    revision = Column(Integer, nullable=False, default=1)
    updated_at = Column(DateTime, default=_utcnow, onupdate=_utcnow)

    def snapshot(self) -> dict:
        return {
            "type": "ENU",
            "frame_id": self.frame_id,
            "origin_source": self.origin_source,
            "ref_lon": self.ref_lon,
            "ref_lat": self.ref_lat,
            "ref_alt": self.ref_alt,
            "revision": self.revision,
        }
