from types import SimpleNamespace
import uuid

from cloud.server.database import SessionLocal
from cloud.server.models.edge_task import EdgeTask
from cloud.server.models.job import Job, JobStep
from cloud.server.models.parcel import Parcel, ParcelSplit
from cloud.server.models.coordinate_frame import CoordinateFrame
from cloud.server.models.machine import Machine
from cloud.server.services.dispatcher import Dispatcher
from cloud.server.services.mqtt_client import MQTTClient


FIELD_GEOJSON = {
    "type": "Feature",
    "geometry": {
        "type": "Polygon",
        "coordinates": [
            [
                [120.0, 28.9],
                [120.01, 28.9],
                [120.01, 28.91],
                [120.0, 28.91],
                [120.0, 28.9],
            ]
        ],
    },
    "properties": {},
}


class FakeMQTT:
    def __init__(self):
        self.published = []

    def publish(self, machine_id: str, payload: dict, qos: int = 1):
        self.published.append({
            "machine_id": machine_id,
            "payload": payload,
            "qos": qos,
        })
        return SimpleNamespace(mid=len(self.published), rc=0)


def _seed_job(
    steps: list[tuple[int, int | None]],
    assigned_machines: list[str | None],
) -> str:
    db = SessionLocal()
    try:
        parcel_id = str(uuid.uuid4())
        job_id = f"job-{uuid.uuid4()}"
        parcel = Parcel(id=parcel_id, name=f"field-{job_id}", geojson=FIELD_GEOJSON)
        job = Job(
            id=job_id,
            name="Progression Test",
            parcel_id=parcel_id,
            split_count=len(assigned_machines),
            machine_assignments={
                str(index): machine
                for index, machine in enumerate(assigned_machines)
                if machine
            },
        )
        db.add(parcel)
        db.flush()
        db.add_all([
            job,
            CoordinateFrame(
                id="farm", frame_id="test-base", origin_source="rtk_base_manual",
                ref_lon=120.0, ref_lat=28.9, revision=1,
            ),
        ])
        for machine_id in sorted({machine for machine in assigned_machines if machine}):
            db.add(Machine(id=machine_id, name=machine_id, status="online"))
        db.flush()

        for seq_index, depends_on in steps:
            db.add(JobStep(
                job_id=job_id,
                seq_index=seq_index,
                operation_type=f"op-{seq_index}",
                preset_yaml="tillage_operation",
                depends_on=depends_on,
            ))

        for index, machine in enumerate(assigned_machines):
            db.add(ParcelSplit(
                parcel_id=parcel_id,
                job_id=job_id,
                index=index,
                name=f"Field Section {index + 1}",
                geojson=FIELD_GEOJSON,
                area_ha=1.0,
                assigned_to=machine,
            ))

        db.commit()
        return job_id
    finally:
        db.close()


def _dispatch_job(job_id: str, mqtt: FakeMQTT):
    db = SessionLocal()
    try:
        result = Dispatcher(mqtt).dispatch_job(db, job_id)
        tasks = db.query(EdgeTask).filter(EdgeTask.job_id == job_id).all()
        return result, {task.edge_task_id: task.seq_index for task in tasks}
    finally:
        db.close()


def _status_handler(mqtt: FakeMQTT):
    handler = MQTTClient.__new__(MQTTClient)
    handler._sse = None
    handler.publish = mqtt.publish
    return handler


def _complete_task(handler, task_id: str, machine_id: str = "tractor-1"):
    handler._handle_task_status({
        "type": "task_status",
        "task_id": task_id,
        "machine_id": machine_id,
        "state": "completed",
        "progress_pct": 100,
    })


def test_completed_step_dispatches_dependent_step_after_all_split_tasks(client):
    mqtt = FakeMQTT()
    job_id = _seed_job(
        steps=[(0, None), (1, 0)],
        assigned_machines=["tractor-1", "tractor-2"],
    )

    result, task_seq = _dispatch_job(job_id, mqtt)

    assert result["dispatched"] == 2
    assert len(mqtt.published) == 2

    handler = _status_handler(mqtt)
    first_step_tasks = [task_id for task_id, seq in task_seq.items() if seq == 0]
    _complete_task(handler, first_step_tasks[0], machine_id="tractor-1")

    db = SessionLocal()
    try:
        step1 = db.query(JobStep).filter(
            JobStep.job_id == job_id,
            JobStep.seq_index == 1,
        ).one()
        assert step1.status == "pending"
        assert len(mqtt.published) == 2
    finally:
        db.close()

    _complete_task(handler, first_step_tasks[1], machine_id="tractor-2")

    db = SessionLocal()
    try:
        steps = {
            step.seq_index: step.status
            for step in db.query(JobStep).filter(JobStep.job_id == job_id).all()
        }
        tasks = db.query(EdgeTask).filter(EdgeTask.job_id == job_id).all()

        assert steps == {0: "completed", 1: "running"}
        assert len(tasks) == 4
        assert len(mqtt.published) == 4
        assert {event["payload"]["sequence_index"] for event in mqtt.published[2:]} == {1}
    finally:
        db.close()


def test_completing_last_step_marks_job_completed(client):
    mqtt = FakeMQTT()
    job_id = _seed_job(
        steps=[(0, None), (1, 0)],
        assigned_machines=["tractor-1"],
    )
    _, task_seq = _dispatch_job(job_id, mqtt)

    handler = _status_handler(mqtt)
    step0_task = next(task_id for task_id, seq in task_seq.items() if seq == 0)
    _complete_task(handler, step0_task)

    db = SessionLocal()
    try:
        step1_task = db.query(EdgeTask).filter(
            EdgeTask.job_id == job_id,
            EdgeTask.seq_index == 1,
        ).one()
    finally:
        db.close()

    _complete_task(handler, step1_task.edge_task_id)

    db = SessionLocal()
    try:
        job = db.query(Job).filter(Job.id == job_id).one()
        steps = db.query(JobStep).filter(JobStep.job_id == job_id).all()

        assert job.status == "completed"
        assert all(step.status == "completed" for step in steps)
        assert len(mqtt.published) == 2
    finally:
        db.close()


def test_dispatch_without_assigned_splits_does_not_mark_running(client):
    mqtt = FakeMQTT()
    job_id = _seed_job(steps=[(0, None)], assigned_machines=[None])

    result, task_seq = _dispatch_job(job_id, mqtt)

    assert result == {"dispatched": 0, "job_id": job_id, "status": "draft"}
    assert task_seq == {}
    assert mqtt.published == []

    db = SessionLocal()
    try:
        job = db.query(Job).filter(Job.id == job_id).one()
        step = db.query(JobStep).filter(JobStep.job_id == job_id).one()

        assert job.status == "draft"
        assert step.status == "pending"
    finally:
        db.close()


def test_same_machine_receives_split_tasks_sequentially(client):
    mqtt = FakeMQTT()
    job_id = _seed_job(
        steps=[(0, None)],
        assigned_machines=["tractor-1", "tractor-1"],
    )

    result, task_seq = _dispatch_job(job_id, mqtt)
    assert result["dispatched"] == 1
    assert len(task_seq) == 2
    assert len(mqtt.published) == 1

    db = SessionLocal()
    try:
        tasks = db.query(EdgeTask).filter(EdgeTask.job_id == job_id).all()
        assert sorted(task.state for task in tasks) == ["pending", "queued"]
        active = next(task for task in tasks if task.state == "pending")
    finally:
        db.close()

    _complete_task(_status_handler(mqtt), active.edge_task_id)

    db = SessionLocal()
    try:
        tasks = db.query(EdgeTask).filter(EdgeTask.job_id == job_id).all()
        assert sorted(task.state for task in tasks) == ["completed", "pending"]
        assert len(mqtt.published) == 2
    finally:
        db.close()


def test_terminal_task_state_cannot_regress(client):
    mqtt = FakeMQTT()
    job_id = _seed_job(steps=[(0, None)], assigned_machines=["tractor-1"])
    _, task_seq = _dispatch_job(job_id, mqtt)
    task_id = next(iter(task_seq))
    handler = _status_handler(mqtt)

    _complete_task(handler, task_id, machine_id="tractor-1")
    handler._handle_task_status({
        "task_id": task_id,
        "machine_id": "tractor-1",
        "state": "running",
        "progress_pct": 10,
    })

    db = SessionLocal()
    try:
        task = db.query(EdgeTask).filter(EdgeTask.edge_task_id == task_id).one()
        assert task.state == "completed"
        assert task.progress_pct == 100
    finally:
        db.close()
