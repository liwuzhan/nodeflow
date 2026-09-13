from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from cloud.server.database import get_db
from cloud.server.models.coordinate_frame import CoordinateFrame
from cloud.server.schemas.coordinate_frame import CoordinateFrameResponse, CoordinateFrameUpdate


router = APIRouter(prefix="/settings", tags=["settings"])


def _response(frame: CoordinateFrame | None) -> CoordinateFrameResponse:
    if frame is None:
        return CoordinateFrameResponse(ready=False)
    return CoordinateFrameResponse(
        ready=True,
        frame_id=frame.frame_id,
        origin_source=frame.origin_source,
        ref_lon=frame.ref_lon,
        ref_lat=frame.ref_lat,
        ref_alt=frame.ref_alt,
        revision=frame.revision,
        updated_at=frame.updated_at,
    )


@router.get("/coordinate-frame", response_model=CoordinateFrameResponse)
def get_coordinate_frame(db: Session = Depends(get_db)):
    return _response(db.query(CoordinateFrame).filter(CoordinateFrame.id == "farm").first())


@router.put("/coordinate-frame", response_model=CoordinateFrameResponse)
def update_coordinate_frame(body: CoordinateFrameUpdate, db: Session = Depends(get_db)):
    frame = db.query(CoordinateFrame).filter(CoordinateFrame.id == "farm").first()
    if frame is None:
        frame = CoordinateFrame(id="farm", revision=1, **body.model_dump())
        db.add(frame)
    else:
        for key, value in body.model_dump().items():
            setattr(frame, key, value)
        frame.revision += 1
    db.commit()
    db.refresh(frame)
    return _response(frame)
