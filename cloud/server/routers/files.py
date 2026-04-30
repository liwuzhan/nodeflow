import hashlib
import msgpack
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import Response, JSONResponse
from sqlalchemy.orm import Session

from cloud.server.database import get_db
from cloud.server.models.parcel import Parcel, ParcelSplit

router = APIRouter(prefix="/download", tags=["files"])


@router.get("/parcels/{split_id}/geojson")
def download_split_geojson(split_id: str, db: Session = Depends(get_db)):
    split = db.query(ParcelSplit).filter(ParcelSplit.id == split_id).first()
    if not split:
        raise HTTPException(404, f"Split {split_id} not found")

    base = split.geojson
    parent = db.query(Parcel).filter(Parcel.id == split.parcel_id).first()
    if parent:
        base["vehicle_config"] = parent.vehicle_cfg
        base["ref_point"] = parent.ref_point

    return JSONResponse(content=base, media_type="application/geo+json")


@router.get("/paths/{task_id}.bin")
def download_path(task_id: str, request: Request, db: Session = Depends(get_db)):
    from cloud.server.models.edge_task import EdgeTask
    edge_task = db.query(EdgeTask).filter(EdgeTask.edge_task_id == task_id).first()
    if not edge_task:
        raise HTTPException(404, f"Task {task_id} not found")

    payload = {
        "task_id": task_id,
        "timestamp": 0.0,
        "path": [],
        "status": "pending",
        "message": "path not yet available",
    }

    data = msgpack.packb(payload)
    sha = hashlib.sha256(data).hexdigest()

    range_header = request.headers.get("range")
    if range_header:
        start, end = 0, len(data) - 1
        try:
            r = range_header.replace("bytes=", "").split("-")
            start = int(r[0]) if r[0] else 0
            end = int(r[1]) if len(r) > 1 and r[1] else len(data) - 1
        except (ValueError, IndexError):
            pass
        content = data[start:end + 1]
        return Response(
            content=content,
            status_code=206,
            media_type="application/octet-stream",
            headers={
                "Content-Range": f"bytes {start}-{end}/{len(data)}",
                "Content-Length": str(len(content)),
                "X-Checksum-SHA256": sha,
            },
        )

    return Response(
        content=data,
        media_type="application/octet-stream",
        headers={
            "Content-Length": str(len(data)),
            "X-Checksum-SHA256": sha,
        },
    )
