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
    parcel = Parcel(
        name=body.name,
        geojson=body.geojson,
        vehicle_cfg=body.vehicle_cfg.model_dump(),
        ref_point=body.ref_point.model_dump(),
    )
    try:
        from shapely.geometry import shape
        geom = body.geojson.get("geometry", body.geojson)
        poly = shape({"type": geom.get("type", "Polygon"), "coordinates": geom["coordinates"]})
        parcel.area_ha = round(poly.area / 10000, 4)
    except Exception:
        parcel.area_ha = 0.0
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
        parcel.geojson = body.geojson
        try:
            from shapely.geometry import shape
            geom = body.geojson.get("geometry", body.geojson)
            poly = shape({"type": geom.get("type", "Polygon"), "coordinates": geom["coordinates"]})
            parcel.area_ha = round(poly.area / 10000, 4)
        except Exception:
            pass
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
