import logging
import time
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from cloud.server.database import get_db
from cloud.server.models.machine import Machine
from cloud.server.schemas.machine import MachineCreate, MachineUpdate, MachineResponse

logger = logging.getLogger("routers.machines")
router = APIRouter(prefix="/machines", tags=["machines"])


def _to_response(m: Machine) -> MachineResponse:
    data = {c.name: getattr(m, c.name) for c in m.__table__.columns}
    if m.last_heartbeat:
        hb = m.last_heartbeat
        if hb.tzinfo is None:
            hb = hb.replace(tzinfo=timezone.utc)
        data["seconds_since_heartbeat"] = (
            datetime.now(timezone.utc) - hb
        ).total_seconds()
    else:
        data["seconds_since_heartbeat"] = None
    return MachineResponse(**data)


@router.get("", response_model=list[MachineResponse])
def list_machines(db: Session = Depends(get_db)):
    machines = db.query(Machine).all()
    return [_to_response(m) for m in machines]


@router.post("", response_model=MachineResponse, status_code=201)
def create_machine(body: MachineCreate, db: Session = Depends(get_db)):
    existing = db.query(Machine).filter(Machine.id == body.id).first()
    if existing:
        raise HTTPException(409, f"Machine '{body.id}' already registered")
    m = Machine(**body.model_dump())
    db.add(m)
    db.commit()
    db.refresh(m)
    return _to_response(m)


@router.get("/{machine_id}", response_model=MachineResponse)
def get_machine(machine_id: str, db: Session = Depends(get_db)):
    m = db.query(Machine).filter(Machine.id == machine_id).first()
    if not m:
        raise HTTPException(404, f"Machine {machine_id} not found")
    return _to_response(m)


@router.put("/{machine_id}", response_model=MachineResponse)
def update_machine(machine_id: str, body: MachineUpdate, db: Session = Depends(get_db)):
    m = db.query(Machine).filter(Machine.id == machine_id).first()
    if not m:
        raise HTTPException(404, f"Machine {machine_id} not found")
    for key, val in body.model_dump(exclude_unset=True).items():
        setattr(m, key, val)
    db.commit()
    db.refresh(m)
    return _to_response(m)


@router.post("/{machine_id}/confirm", response_model=MachineResponse)
def confirm_machine(machine_id: str, db: Session = Depends(get_db)):
    m = db.query(Machine).filter(Machine.id == machine_id).first()
    if not m:
        raise HTTPException(404, f"Machine {machine_id} not found")
    m.status = "online"
    db.commit()
    db.refresh(m)
    logger.info(f"Machine {machine_id} confirmed by operator")
    return _to_response(m)


@router.delete("/{machine_id}", status_code=204)
def delete_machine(machine_id: str, db: Session = Depends(get_db)):
    m = db.query(Machine).filter(Machine.id == machine_id).first()
    if not m:
        raise HTTPException(404, f"Machine {machine_id} not found")
    db.delete(m)
    db.commit()
    return None
