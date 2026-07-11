import logging
import time
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from cloud.server.config import settings
from cloud.server.database import get_db
from cloud.server.models.job import Job, JobStep
from cloud.server.models.parcel import ParcelSplit
from cloud.server.models.parcel import Parcel
from cloud.server.models.machine import Machine
from cloud.server.models.edge_task import EdgeTask
from cloud.server.schemas.job import (
    JobCreate, JobResponse, JobDetailResponse, JobStepResponse,
    EdgeTaskSummary,
)
from cloud.server.services.dispatcher import Dispatcher
from nodeflow_protocol.task import FallbackPolicy, PlanningMode

logger = logging.getLogger("routers.jobs")
router = APIRouter(prefix="/jobs", tags=["jobs"])


def _build_job_id() -> str:
    import datetime, uuid
    now = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    short = str(uuid.uuid4())[:6]
    return f"job-{now}-{short}"


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
            step_id=t.step_id, seq_index=t.seq_index, operation_type=t.operation_type,
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
    if not db.query(Parcel).filter(Parcel.id == body.parcel_id).first():
        raise HTTPException(404, f"Parcel {body.parcel_id} not found")
    if not body.steps:
        raise HTTPException(422, "Job must contain at least one step")
    sequences = [step.seq_index for step in body.steps]
    if sorted(sequences) != list(range(len(body.steps))):
        raise HTTPException(422, "Step sequence indexes must be unique and contiguous from zero")
    known_sequences = set(sequences)
    for step in body.steps:
        try:
            planning_mode = PlanningMode(step.planning_mode)
            fallback_policy = FallbackPolicy(step.fallback_policy)
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc
        if step.depends_on is not None and (
            step.depends_on not in known_sequences or step.depends_on >= step.seq_index
        ):
            raise HTTPException(422, f"Invalid dependency for step {step.seq_index}")
        if planning_mode == PlanningMode.CLOUD_PREFERRED and fallback_policy != FallbackPolicy.ALLOW_EDGE_REPLAN:
            raise HTTPException(422, "cloud_preferred requires allow_edge_replan")

    assignments = set(body.machine_assignments.values())
    for step in body.steps:
        assignments.update(step.machine_assignments.values())
    known_machines = {
        machine_id for (machine_id,) in db.query(Machine.id).filter(Machine.id.in_(assignments)).all()
    } if assignments else set()
    missing_machines = sorted(assignments - known_machines)
    if missing_machines:
        raise HTTPException(422, f"Unknown machines: {', '.join(missing_machines)}")

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
            planning_mode=PlanningMode(s.planning_mode).value,
            fallback_policy=FallbackPolicy(s.fallback_policy).value,
            operation_config=s.operation_config,
            machine_assignments=s.machine_assignments or body.machine_assignments or {},
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
    try:
        result = dispatcher.dispatch_job(db, job_id, base_url=settings.HTTP_PUBLIC_BASE_URL)
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc
    return result


@router.post("/{job_id}/cancel")
def cancel_job(job_id: str, request: Request, db: Session = Depends(get_db)):
    mqtt = request.app.state.mqtt
    dispatcher = Dispatcher(mqtt)
    try:
        return dispatcher.cancel_job(db, job_id)
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc


@router.get("/{job_id}/tasks")
def list_job_tasks(job_id: str, db: Session = Depends(get_db)):
    tasks = db.query(EdgeTask).filter(EdgeTask.job_id == job_id).all()
    return [EdgeTaskSummary(
        id=t.id, edge_task_id=t.edge_task_id, machine_id=t.machine_id,
        step_id=t.step_id, seq_index=t.seq_index, operation_type=t.operation_type,
        state=t.state, progress_pct=t.progress_pct, error_code=t.error_code,
    ) for t in tasks]
