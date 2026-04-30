import logging
import time
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from cloud.server.config import settings
from cloud.server.database import get_db
from cloud.server.models.job import Job, JobStep
from cloud.server.models.parcel import ParcelSplit
from cloud.server.models.edge_task import EdgeTask
from cloud.server.schemas.job import (
    JobCreate, JobResponse, JobDetailResponse, JobStepResponse,
    EdgeTaskSummary,
)
from cloud.server.services.dispatcher import Dispatcher

logger = logging.getLogger("routers.jobs")
router = APIRouter(prefix="/jobs", tags=["jobs"])


def _build_job_id() -> str:
    import datetime
    now = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    return f"job-{now}"


def _job_to_response(job: Job) -> JobResponse:
    return JobResponse(
        id=job.id, name=job.name, parcel_id=job.parcel_id,
        status=job.status, split_mode=job.split_mode,
        split_count=job.split_count, created_at=job.created_at,
        steps=[JobStepResponse(**{c.name: getattr(s, c.name) for c in s.__table__.columns})
                for s in job.steps],
    )


def _job_to_detail(db: Session, job: Job) -> JobDetailResponse:
    splits = db.query(ParcelSplit).filter(
        ParcelSplit.job_id == job.id
    ).order_by(ParcelSplit.index).all()
    tasks = db.query(EdgeTask).filter(EdgeTask.job_id == job.id).all()
    return JobDetailResponse(
        id=job.id, name=job.name, parcel_id=job.parcel_id,
        status=job.status, split_mode=job.split_mode,
        split_count=job.split_count, created_at=job.created_at,
        steps=[JobStepResponse(**{c.name: getattr(s, c.name) for c in s.__table__.columns})
                for s in job.steps],
        splits=[{"index": s.index, "name": s.name, "area_ha": s.area_ha,
                 "assigned_to": s.assigned_to} for s in splits],
        edge_tasks=[EdgeTaskSummary(
            id=t.id, edge_task_id=t.edge_task_id, machine_id=t.machine_id,
            state=t.state, progress_pct=t.progress_pct, error_code=t.error_code,
        ) for t in tasks],
    )


@router.get("", response_model=list[JobResponse])
def list_jobs(status: str | None = None, parcel_id: str | None = None,
              db: Session = Depends(get_db)):
    q = db.query(Job)
    if status:
        q = q.filter(Job.status == status)
    if parcel_id:
        q = q.filter(Job.parcel_id == parcel_id)
    jobs = q.order_by(Job.created_at.desc()).all()
    return [_job_to_response(j) for j in jobs]


@router.post("", response_model=JobDetailResponse, status_code=201)
def create_job(body: JobCreate, request: Request, db: Session = Depends(get_db)):
    job_id = _build_job_id()
    name = body.name or f"Job-{job_id}"
    job = Job(
        id=job_id, name=name, parcel_id=body.parcel_id,
        split_mode=body.split_mode, split_count=body.split_count,
        machine_assignments=body.machine_assignments or {},
    )
    db.add(job)
    db.flush()

    for s in body.steps:
        step = JobStep(
            job_id=job.id, seq_index=s.seq_index,
            operation_type=s.operation_type, preset_yaml=s.preset_yaml,
            depends_on=s.depends_on,
        )
        db.add(step)

    db.commit()
    db.refresh(job)
    return _job_to_detail(db, job)


@router.get("/{job_id}", response_model=JobDetailResponse)
def get_job(job_id: str, db: Session = Depends(get_db)):
    job = db.query(Job).filter(Job.id == job_id).first()
    if not job:
        raise HTTPException(404, f"Job {job_id} not found")
    return _job_to_detail(db, job)


@router.delete("/{job_id}", status_code=204)
def delete_job(job_id: str, db: Session = Depends(get_db)):
    job = db.query(Job).filter(Job.id == job_id).first()
    if not job:
        raise HTTPException(404, f"Job {job_id} not found")
    if job.status == "running":
        raise HTTPException(409, "Cannot delete running job")
    db.delete(job)
    db.commit()
    return None


@router.post("/{job_id}/dispatch")
def dispatch_job(job_id: str, request: Request, db: Session = Depends(get_db)):
    job = db.query(Job).filter(Job.id == job_id).first()
    if not job:
        raise HTTPException(404, f"Job {job_id} not found")

    mqtt = request.app.state.mqtt
    dispatcher = Dispatcher(mqtt)
    result = dispatcher.dispatch_job(
        db, job_id,
        http_host="localhost",
        http_port=settings.HTTP_SERVER_PORT,
    )
    return result


@router.post("/{job_id}/cancel")
def cancel_job(job_id: str, request: Request, db: Session = Depends(get_db)):
    mqtt = request.app.state.mqtt
    dispatcher = Dispatcher(mqtt)
    return dispatcher.cancel_job(db, job_id)


@router.get("/{job_id}/tasks")
def list_job_tasks(job_id: str, db: Session = Depends(get_db)):
    tasks = db.query(EdgeTask).filter(EdgeTask.job_id == job_id).all()
    return [EdgeTaskSummary(
        id=t.id, edge_task_id=t.edge_task_id, machine_id=t.machine_id,
        state=t.state, progress_pct=t.progress_pct, error_code=t.error_code,
    ) for t in tasks]
