import uuid
import time
import logging
import hashlib
import json

from sqlalchemy.orm import Session

from cloud.server.config import settings
from cloud.server.models.job import Job, JobStep
from cloud.server.models.parcel import Parcel, ParcelSplit
from cloud.server.models.edge_task import EdgeTask
from cloud.server.models.coordinate_frame import CoordinateFrame
from cloud.server.models.machine import Machine
from cloud.server.services.splitter import ParcelSplitter
from nodeflow_protocol.task import FallbackPolicy, PlanningMode, PROTOCOL_VERSION
from cloud.server.services.cloud_planner import CloudPathPlanner

logger = logging.getLogger("dispatcher")


class Dispatcher:
    def __init__(self, mqtt_client):
        self.mqtt = mqtt_client
        self.splitter = ParcelSplitter()
        self.cloud_planner = CloudPathPlanner()

    def dispatch_job(self, db: Session, job_id: str, base_url: str | None = None, **legacy) -> dict:
        job = db.query(Job).filter(Job.id == job_id).first()
        if not job:
            raise ValueError(f"Job {job_id} not found")
        if job.status not in ("draft", "ready"):
            raise ValueError(f"Job {job_id} is not in dispatchable state: {job.status}")

        parcel = db.query(Parcel).filter(Parcel.id == job.parcel_id).first()
        if not parcel:
            raise ValueError(f"Parcel {job.parcel_id} not found")

        frame = db.query(CoordinateFrame).filter(CoordinateFrame.id == "farm").first()
        if frame is None:
            raise ValueError("Farm coordinate frame is not configured")

        splits = self._get_or_create_splits(db, job, parcel)
        base_url = self._resolve_base_url(base_url, legacy)
        dispatched_count = 0

        for step in job.steps:
            if step.status in ("completed", "running"):
                continue
            if not self._dependencies_met(db, step):
                logger.info(f"Step {step.seq_index} deps not met, skipping")
                continue

            dispatched_count += self._dispatch_step(
                db, step, job, base_url, splits=splits, frame=frame
            )

        if dispatched_count > 0:
            job.status = "running"
        db.commit()
        return {"dispatched": dispatched_count, "job_id": job.id, "status": job.status}

    def dispatch_next_step(self, db: Session, job_id: str, base_url: str | None = None,
                           commit: bool = True, **legacy) -> dict:
        """Try to dispatch the next pending step when dependencies are met."""
        job = db.query(Job).filter(Job.id == job_id).first()
        if not job:
            return {"dispatched": 0, "job_id": job_id, "status": "not_found"}
        frame = db.query(CoordinateFrame).filter(CoordinateFrame.id == "farm").first()
        if frame is None:
            return {"dispatched": 0, "job_id": job_id, "status": "coordinate_frame_missing"}
        base_url = self._resolve_base_url(base_url, legacy)

        for step in sorted(job.steps, key=lambda s: s.seq_index):
            if step.status in ("completed", "running"):
                continue

            if self._dependencies_met(db, step):
                dispatched = self._dispatch_step(db, step, job, base_url, frame=frame)
                if dispatched > 0:
                    job.status = "running"
                if commit:
                    db.commit()
                return {
                    "dispatched": dispatched,
                    "job_id": job.id,
                    "status": job.status,
                    "step_id": step.id,
                    "step_seq": step.seq_index,
                }

        if job.steps and all(step.status == "completed" for step in job.steps):
            job.status = "completed"

        if commit:
            db.commit()
        return {"dispatched": 0, "job_id": job.id, "status": job.status}

    def _dispatch_step(self, db: Session, step: JobStep, job: Job,
                       base_url: str,
                       splits: list[ParcelSplit] | None = None,
                       frame: CoordinateFrame | None = None) -> int:
        if splits is None:
            splits = db.query(ParcelSplit).filter(
                ParcelSplit.job_id == job.id
            ).order_by(ParcelSplit.index).all()

        assignments = step.machine_assignments or job.machine_assignments or {}
        dispatchable_splits = [
            split for split in splits
            if assignments.get(str(split.index)) or split.assigned_to
        ]
        if not dispatchable_splits:
            logger.warning(
                f"Step {step.seq_index} has no assigned splits; leaving it pending"
            )
            return 0

        if frame is None:
            frame = db.query(CoordinateFrame).filter(CoordinateFrame.id == "farm").first()
        if frame is None:
            raise ValueError("Farm coordinate frame is not configured")

        parcel = db.query(Parcel).filter(Parcel.id == job.parcel_id).first()
        if parcel is None:
            raise ValueError(f"Parcel {job.parcel_id} not found")

        planning_mode = PlanningMode(step.planning_mode or PlanningMode.EDGE.value)
        fallback_policy = FallbackPolicy(step.fallback_policy or FallbackPolicy.DENY.value)

        for split in dispatchable_splits:
            existing = db.query(EdgeTask).filter(
                EdgeTask.step_id == step.id,
                EdgeTask.parcel_split_id == split.id,
            ).first()
            if existing:
                continue
            edge_task_id = str(uuid.uuid4())
            machine_id = assignments.get(str(split.index)) or split.assigned_to
            field_checksum = self._checksum(split.geojson)

            task = EdgeTask(
                id=str(uuid.uuid4()),
                edge_task_id=edge_task_id,
                job_id=job.id,
                step_id=step.id,
                machine_id=machine_id,
                parcel_split_id=split.id,
                dispatch_id=None,
                protocol_version=PROTOCOL_VERSION,
                planning_mode=planning_mode.value,
                fallback_policy=fallback_policy.value,
                field_revision=parcel.revision or 1,
                field_checksum=field_checksum,
                coordinate_frame=frame.snapshot(),
                operation_config=step.operation_config or {},
                operation_type=step.operation_type,
                seq_index=step.seq_index,
                preset_yaml=step.preset_yaml,
                state="queued",
            )
            db.add(task)
            db.flush()
            if planning_mode in (PlanningMode.CLOUD, PlanningMode.CLOUD_PREFERRED):
                try:
                    artifact = self.cloud_planner.generate(
                        task, split, frame, step.operation_config or {},
                    )
                    db.add(artifact)
                except Exception:
                    if planning_mode == PlanningMode.CLOUD:
                        raise
                    if fallback_policy != FallbackPolicy.ALLOW_EDGE_REPLAN:
                        raise
                    logger.exception("Cloud planning failed for %s; edge fallback allowed", edge_task_id)
        db.flush()
        step.status = "running"
        # Make work units visible before an edge can ACK the MQTT publish.
        db.commit()
        return self.dispatch_queued_tasks(db, step.id, base_url=base_url)

    def dispatch_queued_tasks(self, db: Session, step_id: str,
                              base_url: str | None = None) -> int:
        base_url = (base_url or settings.HTTP_PUBLIC_BASE_URL).rstrip("/")
        active_states = [
            "pending", "downloading", "ready", "running",
            "cancel_requested", "communication_lost",
        ]
        active_machines = {
            machine_id for (machine_id,) in db.query(EdgeTask.machine_id).filter(
                EdgeTask.state.in_(active_states)
            ).all()
        }
        online_machines = {
            machine_id for (machine_id,) in db.query(Machine.id).filter(
                Machine.status == "online"
            ).all()
        }
        queued = db.query(EdgeTask).filter(
            EdgeTask.step_id == step_id,
            EdgeTask.state == "queued",
        ).order_by(EdgeTask.created_at, EdgeTask.id).all()

        dispatched = 0
        for task in queued:
            if task.machine_id in active_machines or task.machine_id not in online_machines:
                continue
            payload = self._build_payload(db, task, base_url)
            task.dispatch_id = payload["dispatch_id"]
            task.state = "pending"
            task.last_dispatch_at = time.time()
            db.commit()
            try:
                result = self.mqtt.publish(task.machine_id, payload, qos=1)
            except Exception as exc:
                task.state = "queued"
                task.error_detail = f"MQTT_PUBLISH_FAILED:{exc}"
                db.commit()
                continue
            if getattr(result, "rc", 0) != 0:
                task.state = "queued"
                task.error_detail = f"MQTT_PUBLISH_FAILED:{getattr(result, 'rc', 'unknown')}"
                db.commit()
                continue
            active_machines.add(task.machine_id)
            dispatched += 1
            logger.info("Step %s: task %s -> %s", task.seq_index, task.edge_task_id, task.machine_id)
        return dispatched

    def _build_payload(self, db: Session, task: EdgeTask, base_url: str) -> dict:
        split = db.query(ParcelSplit).filter(ParcelSplit.id == task.parcel_split_id).one()
        dispatch_id = str(uuid.uuid4())
        payload = {
            "type": "task_dispatch",
            "protocol_version": task.protocol_version or PROTOCOL_VERSION,
            "task_id": task.edge_task_id,
            "job_id": task.job_id,
            "dispatch_id": dispatch_id,
            "command_id": dispatch_id,
            "preset_yaml": task.preset_yaml,
            "operation_type": task.operation_type,
            "sequence_index": task.seq_index,
            "machine_id": task.machine_id,
            "planning_mode": task.planning_mode,
            "fallback_policy": task.fallback_policy,
            "parcel_ref": split.name,
            "parcel_url": f"{base_url}/api/v1/download/parcels/{split.id}/geojson",
            "field_revision": task.field_revision,
            "field_checksum": task.field_checksum,
            "coordinate_frame": task.coordinate_frame or {},
            "operation_config": task.operation_config or {},
            "plan_id": task.plan_id,
            "plan_revision": task.plan_revision or 0,
            "path_checksum": task.path_checksum,
            "node_params": {},
            "timestamp": time.time(),
        }
        if task.planning_mode in (PlanningMode.CLOUD.value, PlanningMode.CLOUD_PREFERRED.value):
            if task.plan_id and task.path_checksum:
                payload["path_url"] = f"{base_url}/api/v1/download/paths/{task.edge_task_id}.bin"
            elif task.planning_mode == PlanningMode.CLOUD.value:
                raise ValueError(f"Cloud-planned task {task.edge_task_id} has no ready path artifact")
        return payload

    @staticmethod
    def _checksum(value: dict) -> str:
        encoded = json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()

    @staticmethod
    def _resolve_base_url(base_url: str | None, legacy: dict) -> str:
        if base_url:
            return base_url.rstrip("/")
        host = legacy.get("http_host")
        port = legacy.get("http_port")
        if host:
            return f"http://{host}:{port or settings.HTTP_SERVER_PORT}"
        return settings.HTTP_PUBLIC_BASE_URL.rstrip("/")

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
            logger.error("Step %s references missing dependency %s", step.seq_index, step.depends_on)
            return False
        return dep_step.status == "completed"

    def retry_dispatch(self, db: Session, edge_task_id: str,
                       base_url: str | None = None, **legacy) -> dict:
        t = db.query(EdgeTask).filter(EdgeTask.id == edge_task_id).first()
        if not t:
            raise ValueError(f"EdgeTask {edge_task_id} not found")
        if t.state not in ("failed", "pending"):
            raise ValueError(f"Task {edge_task_id} not in retryable state: {t.state}")

        t.attempt += 1
        if t.attempt > settings.DISPATCH_MAX_RETRIES:
            t.error_detail = "DISPATCH_MAX_RETRIES_EXCEEDED"
            t.error_code = "DISPATCH_ACK_TIMEOUT"
            t.state = "failed"
            t.completed_at = time.time()
            db.commit()
            return {"retried": False, "reason": "max retries exceeded"}

        base_url = self._resolve_base_url(base_url, legacy)
        payload = self._build_payload(db, t, base_url)
        t.dispatch_id = payload["dispatch_id"]
        t.state = "pending"
        t.last_dispatch_at = time.time()
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
            EdgeTask.state.in_(["queued", "pending", "downloading", "ready", "running",
                               "communication_lost"]),
        ).all()

        requested = 0
        for t in tasks:
            t.desired_state = "cancelled"
            if t.state == "queued":
                t.state = "cancelled"
                t.completed_at = time.time()
                continue
            self.mqtt.publish_cancel(t.machine_id, t.edge_task_id)
            t.state = "cancel_requested"
            t.attempt = 1
            t.last_dispatch_at = time.time()
            requested += 1

        job.status = "cancel_requested" if requested else "cancelled"
        for step in job.steps:
            if step.status in ("pending", "running"):
                step.status = "cancel_requested" if requested else "cancelled"

        db.commit()
        return {"cancel_requested": requested, "cancelled": len(tasks) - requested, "job_id": job_id}
