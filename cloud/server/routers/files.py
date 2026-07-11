import copy
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse, Response
from sqlalchemy.orm import Session

from cloud.server.database import get_db
from cloud.server.models.parcel import Parcel, ParcelSplit
from cloud.server.models.coordinate_frame import CoordinateFrame
from cloud.server.models.path_artifact import PathArtifact

router = APIRouter(prefix="/download", tags=["files"])


@router.get("/parcels/{split_id}/geojson")
def download_split_geojson(split_id: str, db: Session = Depends(get_db)):
    split = db.query(ParcelSplit).filter(ParcelSplit.id == split_id).first()
    if not split:
        raise HTTPException(404, f"Split {split_id} not found")

    base = copy.deepcopy(split.geojson)
    parent = db.query(Parcel).filter(Parcel.id == split.parcel_id).first()
    if parent:
        base["vehicle_config"] = parent.vehicle_cfg
        base["field_revision"] = parent.revision or 1
    frame = db.query(CoordinateFrame).filter(CoordinateFrame.id == "farm").first()
    if frame:
        base["coordinate_frame"] = frame.snapshot()

    return JSONResponse(content=base, media_type="application/geo+json")


@router.get("/paths/{task_id}.bin")
def download_path(task_id: str, request: Request, db: Session = Depends(get_db)):
    from cloud.server.models.edge_task import EdgeTask
    edge_task = db.query(EdgeTask).filter(EdgeTask.edge_task_id == task_id).first()
    if not edge_task:
        raise HTTPException(404, f"Task {task_id} not found")

    artifact = db.query(PathArtifact).filter(
        PathArtifact.edge_task_id == task_id,
        PathArtifact.revision == edge_task.plan_revision,
    ).first()
    if not artifact or not edge_task.plan_id or not edge_task.path_checksum:
        raise HTTPException(409, "Path artifact is not ready")
    data = artifact.payload
    headers = {
        "Accept-Ranges": "bytes",
        "X-Checksum-SHA256": artifact.checksum,
        "X-Plan-Revision": str(artifact.revision),
    }
    range_header = request.headers.get("range")
    if not range_header:
        headers["Content-Length"] = str(len(data))
        return Response(data, media_type="application/msgpack", headers=headers)

    try:
        units, requested = range_header.split("=", 1)
        if units.strip().lower() != "bytes" or "," in requested:
            raise ValueError
        start_text, end_text = requested.split("-", 1)
        if not start_text:
            length = int(end_text)
            if length <= 0:
                raise ValueError
            start = max(0, len(data) - length)
            end = len(data) - 1
        else:
            start = int(start_text)
            end = int(end_text) if end_text else len(data) - 1
        if start < 0 or start >= len(data) or end < start:
            raise ValueError
        end = min(end, len(data) - 1)
    except (ValueError, IndexError):
        return Response(status_code=416, headers={"Content-Range": f"bytes */{len(data)}"})

    content = data[start:end + 1]
    headers.update({
        "Content-Range": f"bytes {start}-{end}/{len(data)}",
        "Content-Length": str(len(content)),
    })
    return Response(content, status_code=206, media_type="application/msgpack", headers=headers)
