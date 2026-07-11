from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from cloud.server.config import settings
from cloud.server.database import get_db
from cloud.server.models.edge_task import EdgeTask
from cloud.server.schemas.edge_task import EdgeTaskResponse
from cloud.server.services.dispatcher import Dispatcher

router = APIRouter(prefix="/tasks", tags=["tasks"])


@router.get("/{task_id}", response_model=EdgeTaskResponse)
def get_task(task_id: str, db: Session = Depends(get_db)):
    t = db.query(EdgeTask).filter(EdgeTask.id == task_id).first()
    if not t:
        raise HTTPException(404, f"Task {task_id} not found")
    return EdgeTaskResponse(**{c.name: getattr(t, c.name) for c in t.__table__.columns})


@router.post("/{task_id}/retry")
def retry_task(task_id: str, request: Request, db: Session = Depends(get_db)):
    mqtt = request.app.state.mqtt
    dispatcher = Dispatcher(mqtt)
    try:
        return dispatcher.retry_dispatch(
            db, task_id, base_url=settings.HTTP_PUBLIC_BASE_URL,
        )
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc
