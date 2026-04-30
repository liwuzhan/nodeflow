import uuid
import time
import logging

from sqlalchemy.orm import Session

from cloud.server.config import settings
from cloud.server.models.job import Job, JobStep
from cloud.server.models.parcel import Parcel, ParcelSplit
from cloud.server.models.edge_task import EdgeTask
from cloud.server.services.splitter import ParcelSplitter

logger = logging.getLogger("dispatcher")


class Dispatcher:
    def __init__(self, mqtt_client):
        self.mqtt = mqtt_client
        self.splitter = ParcelSplitter()

    def dispatch_job(self, db: Session, job_id: str, http_host: str = "localhost",
                     http_port: int = 8080) -> dict:
        job = db.query(Job).filter(Job.id == job_id).first()
        if not job:
            raise ValueError(f"Job {job_id} not found")
        if job.status not in ("draft", "ready"):
            raise ValueError(f"Job {job_id} is not in dispatchable state: {job.status}")

        parcel = db.query(Parcel).filter(Parcel.id == job.parcel_id).first()
        if not parcel:
            raise ValueError(f"Parcel {job.parcel_id} not found")

        splits = self._get_or_create_splits(db, job, parcel)
        dispatched_count = 0

        for step in job.steps:
            if step.status == "completed":
                continue
            if not self._dependencies_met(db, step):
                logger.info(f"Step {step.seq_index} deps not met, skipping")
                continue

            step.status = "running"
            for split in splits:
                if not split.assigned_to:
                    logger.warning(f"Split {split.index} has no assigned machine, skipping")
                    continue

                edge_task_id = str(uuid.uuid4())
                dispatch_id = str(uuid.uuid4())

                base_url = f"http://{http_host}:{http_port}"
                parcel_url = f"{base_url}/api/v1/download/parcels/{split.id}/geojson"
                path_url = f"{base_url}/api/v1/download/paths/{edge_task_id}.bin"

                node_params = {
                    "parcel_planner": {"parcel_name": split.name.split("—")[-1].strip() if "—" in split.name else split.name},
                    "trajectory_loader": {"trajectory_file": ""},
                }

                task = EdgeTask(
                    id=str(uuid.uuid4()),
                    edge_task_id=edge_task_id,
                    job_id=job.id,
                    step_id=step.id,
                    machine_id=split.assigned_to,
                    parcel_split_id=split.id,
                    dispatch_id=dispatch_id,
                    operation_type=step.operation_type,
                    seq_index=step.seq_index,
                    preset_yaml=step.preset_yaml,
                    state="pending",
                )
                db.add(task)
                db.flush()

                payload = {
                    "type": "task_dispatch",
                    "task_id": edge_task_id,
                    "job_id": job.id,
                    "dispatch_id": dispatch_id,
                    "preset_yaml": step.preset_yaml,
                    "operation_type": step.operation_type,
                    "sequence_index": step.seq_index,
                    "machine_id": split.assigned_to,
                    "parcel_ref": split.name,
                    "parcel_url": parcel_url,
                    "path_url": path_url,
                    "node_params": node_params,
                    "timestamp": time.time(),
                }

                self.mqtt.publish(split.assigned_to, payload, qos=1)
                logger.info(f"Dispatched task {edge_task_id} → {split.assigned_to}")
                dispatched_count += 1

        job.status = "running"
        db.commit()
        return {"dispatched": dispatched_count, "job_id": job.id, "status": job.status}

    def dispatch_next_step(self, db: Session, job_id: str, http_host: str = "localhost",
                           http_port: int = 8080):
        """Try to dispatch the next pending step when dependencies are met."""
        job = db.query(Job).filter(Job.id == job_id).first()
        if not job:
            return

        for step in sorted(job.steps, key=lambda s: s.seq_index):
            if step.status in ("completed", "running"):
                continue

            if self._dependencies_met(db, step):
                self._dispatch_step(db, step, job, http_host, http_port)
                return

    def _dispatch_step(self, db: Session, step: JobStep, job: Job,
                       http_host: str, http_port: int):
        splits = db.query(ParcelSplit).filter(
            ParcelSplit.job_id == job.id
        ).order_by(ParcelSplit.index).all()

        step.status = "running"
        base_url = f"http://{http_host}:{http_port}"

        for split in splits:
            if not split.assigned_to:
                continue

            edge_task_id = str(uuid.uuid4())
            dispatch_id = str(uuid.uuid4())

            task = EdgeTask(
                id=str(uuid.uuid4()),
                edge_task_id=edge_task_id,
                job_id=job.id,
                step_id=step.id,
                machine_id=split.assigned_to,
                parcel_split_id=split.id,
                dispatch_id=dispatch_id,
                operation_type=step.operation_type,
                seq_index=step.seq_index,
                preset_yaml=step.preset_yaml,
                state="pending",
            )
            db.add(task)

            payload = {
                "type": "task_dispatch",
                "task_id": edge_task_id,
                "job_id": job.id,
                "dispatch_id": dispatch_id,
                "preset_yaml": step.preset_yaml,
                "operation_type": step.operation_type,
                "sequence_index": step.seq_index,
                "machine_id": split.assigned_to,
                "parcel_ref": split.name,
                "parcel_url": f"{base_url}/api/v1/download/parcels/{split.id}/geojson",
                "path_url": f"{base_url}/api/v1/download/paths/{edge_task_id}.bin",
                "node_params": {
                    "parcel_planner": {"parcel_name": split.name},
                    "trajectory_loader": {"trajectory_file": ""},
                },
                "timestamp": time.time(),
            }
            self.mqtt.publish(split.assigned_to, payload, qos=1)
            logger.info(f"Step {step.seq_index}: task {edge_task_id} → {split.assigned_to}")

        db.commit()

    def _get_or_create_splits(self, db: Session, job: Job, parcel: Parcel) -> list:
        existing = db.query(ParcelSplit).filter(
            ParcelSplit.job_id == job.id
        ).order_by(ParcelSplit.index).all()
        if existing:
            return existing

        assignments = job.machine_assignments or {}
        sub_parcels = self.splitter.split(
            parcel.geojson, mode=job.split_mode, count=job.split_count,
            parcel_name=parcel.name,
            machine_assignments=assignments,
        )
        for sp in sub_parcels:
            assigned = sp.assigned_machine or assignments.get(str(sp.index))
            split = ParcelSplit(
                parcel_id=parcel.id,
                job_id=job.id,
                index=sp.index,
                name=sp.name,
                geojson=sp.geojson,
                area_ha=sp.area_ha,
                assigned_to=assigned,
            )
            db.add(split)
            db.flush()
        db.commit()
        return db.query(ParcelSplit).filter(
            ParcelSplit.job_id == job.id
        ).order_by(ParcelSplit.index).all()

    def _dependencies_met(self, db: Session, step: JobStep) -> bool:
        if step.depends_on is None:
            return True
        dep_step = db.query(JobStep).filter(
            JobStep.job_id == step.job_id,
            JobStep.seq_index == step.depends_on,
        ).first()
        if dep_step is None:
            return True
        return dep_step.status == "completed"

    def retry_dispatch(self, db: Session, edge_task_id: str, http_host: str = "localhost",
                       http_port: int = 8080) -> dict:
        t = db.query(EdgeTask).filter(EdgeTask.id == edge_task_id).first()
        if not t:
            raise ValueError(f"EdgeTask {edge_task_id} not found")
        if t.state not in ("failed", "pending"):
            raise ValueError(f"Task {edge_task_id} not in retryable state: {t.state}")

        t.attempt += 1
        if t.attempt > settings.DISPATCH_MAX_RETRIES:
            t.error_detail = "DISPATCH_MAX_RETRIES_EXCEEDED"
            db.commit()
            return {"retried": False, "reason": "max retries exceeded"}

        new_dispatch_id = str(uuid.uuid4())
        t.dispatch_id = new_dispatch_id
        t.state = "pending"

        base_url = f"http://{http_host}:{http_port}"
        payload = {
            "type": "task_dispatch",
            "task_id": t.edge_task_id,
            "job_id": t.job_id,
            "dispatch_id": new_dispatch_id,
            "preset_yaml": t.preset_yaml,
            "operation_type": t.operation_type,
            "sequence_index": t.seq_index,
            "machine_id": t.machine_id,
            "parcel_url": f"{base_url}/api/v1/download/parcels/{t.parcel_split_id}/geojson",
            "path_url": f"{base_url}/api/v1/download/paths/{t.edge_task_id}.bin",
            "node_params": {
                "parcel_planner": {"parcel_name": ""},
                "trajectory_loader": {"trajectory_file": ""},
            },
            "timestamp": time.time(),
        }
        self.mqtt.publish(t.machine_id, payload, qos=1)
        db.commit()
        logger.info(f"Retry dispatch task {t.edge_task_id} (attempt {t.attempt})")
        return {"retried": True, "attempt": t.attempt}

    def cancel_job(self, db: Session, job_id: str) -> dict:
        job = db.query(Job).filter(Job.id == job_id).first()
        if not job:
            raise ValueError(f"Job {job_id} not found")

        tasks = db.query(EdgeTask).filter(
            EdgeTask.job_id == job_id,
            EdgeTask.state.in_(["pending", "downloading", "ready", "running"]),
        ).all()

        for t in tasks:
            self.mqtt.publish_cancel(t.machine_id, t.edge_task_id)
            t.state = "cancelled"
            t.completed_at = time.time()

        job.status = "cancelled"
        for step in job.steps:
            if step.status in ("pending", "running"):
                step.status = "cancelled"

        db.commit()
        return {"cancelled": len(tasks), "job_id": job_id}
