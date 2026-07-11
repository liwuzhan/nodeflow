from fastapi import APIRouter
from cloud.server.routers.parcels import router as parcels_router
from cloud.server.routers.machines import router as machines_router
from cloud.server.routers.jobs import router as jobs_router
from cloud.server.routers.tasks import router as tasks_router
from cloud.server.routers.files import router as files_router
from cloud.server.routers.events import router as events_router
from cloud.server.routers.settings import router as settings_router

api_router = APIRouter()
api_router.include_router(parcels_router)
api_router.include_router(machines_router)
api_router.include_router(jobs_router)
api_router.include_router(tasks_router)
api_router.include_router(files_router)
api_router.include_router(events_router)
api_router.include_router(settings_router)
