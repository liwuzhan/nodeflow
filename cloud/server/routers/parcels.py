import logging
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from cloud.server.database import get_db
from cloud.server.models.parcel import Parcel, ParcelSplit
from cloud.server.schemas.parcel import (
    ParcelCreate, ParcelUpdate, ParcelSummary, ParcelResponse,
    SplitPreviewRequest, SplitPreviewResponse, SubParcel,
)
from cloud.server.services.splitter import ParcelSplitter
from cloud.server.services.geo import area_hectares
from cloud.server.models.coordinate_frame import CoordinateFrame

logger = logging.getLogger("routers.parcels")
router = APIRouter(prefix="/parcels", tags=["parcels"])


@router.get("", response_model=list[ParcelSummary])
def list_parcels(db: Session = Depends(get_db)):
    return db.query(Parcel).order_by(Parcel.created_at.desc()).all()


@router.post("", response_model=ParcelResponse, status_code=201)
def create_parcel(body: ParcelCreate, db: Session = Depends(get_db)):
    existing = db.query(Parcel).filter(Parcel.name == body.name).first()
    if existing:
        raise HTTPException(409, f"Parcel '{body.name}' already exists")
    frame = db.query(CoordinateFrame).filter(CoordinateFrame.id == "farm").first()
    ref_point = body.ref_point.model_dump() if body.ref_point else (frame.snapshot() if frame else {})
    parcel = Parcel(
        name=body.name,
        geojson=body.geojson,
        vehicle_cfg=body.vehicle_cfg.model_dump(),
        ref_point=ref_point,
    )
    try:
        parcel.area_ha = area_hectares(body.geojson)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    db.add(parcel)
    db.commit()
    db.refresh(parcel)
    return parcel


@router.get("/{parcel_id}", response_model=ParcelResponse)
def get_parcel(parcel_id: str, db: Session = Depends(get_db)):
    parcel = db.query(Parcel).filter(Parcel.id == parcel_id).first()
    if not parcel:
        raise HTTPException(404, f"Parcel {parcel_id} not found")
    return parcel


@router.put("/{parcel_id}", response_model=ParcelResponse)
def update_parcel(parcel_id: str, body: ParcelUpdate, db: Session = Depends(get_db)):
    parcel = db.query(Parcel).filter(Parcel.id == parcel_id).first()
    if not parcel:
        raise HTTPException(404, f"Parcel {parcel_id} not found")
    if body.name is not None:
        parcel.name = body.name
    if body.geojson is not None:
        try:
            parcel.area_ha = area_hectares(body.geojson)
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc
        parcel.geojson = body.geojson
        parcel.revision = (parcel.revision or 1) + 1
    if body.vehicle_cfg is not None:
        parcel.vehicle_cfg = body.vehicle_cfg.model_dump()
    if body.ref_point is not None:
        parcel.ref_point = body.ref_point.model_dump()
    db.commit()
    db.refresh(parcel)
    return parcel


@router.delete("/{parcel_id}", status_code=204)
def delete_parcel(parcel_id: str, db: Session = Depends(get_db)):
    parcel = db.query(Parcel).filter(Parcel.id == parcel_id).first()
    if not parcel:
        raise HTTPException(404, f"Parcel {parcel_id} not found")
    db.delete(parcel)
    db.commit()
    return None


@router.post("/{parcel_id}/preview-split", response_model=SplitPreviewResponse)
def preview_split(parcel_id: str, body: SplitPreviewRequest, db: Session = Depends(get_db)):
    parcel = db.query(Parcel).filter(Parcel.id == parcel_id).first()
    if not parcel:
        raise HTTPException(404, f"Parcel {parcel_id} not found")
    splitter = ParcelSplitter()
    assignments = body.machine_assignments or {}
    sub_parcels = splitter.split(
        parcel.geojson, mode=body.mode, count=body.count,
        angle_deg=body.angle_deg, machine_assignments=assignments,
        parcel_name=parcel.name,
    )
    return SplitPreviewResponse(
        sub_parcels=[SubParcel(**sp.to_dict()) for sp in sub_parcels]
    )


@router.get("/{parcel_id}/geojson")
def get_parcel_geojson(parcel_id: str, db: Session = Depends(get_db)):
    parcel = db.query(Parcel).filter(Parcel.id == parcel_id).first()
    if not parcel:
        raise HTTPException(404, f"Parcel {parcel_id} not found")
    from fastapi.responses import JSONResponse
    return JSONResponse(content=parcel.geojson, media_type="application/geo+json")
