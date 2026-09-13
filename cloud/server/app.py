from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from cloud.server.config import settings
from cloud.server.database import engine, Base
from cloud.server.models import (
    CoordinateFrame, EdgeTask, Job, JobStep, Machine, Parcel, ParcelSplit, PathArtifact,
)
from cloud.server.routers import api_router
from cloud.server.routers.editor import router as editor_router
from cloud.server.services.mqtt_client import MQTTClient
from cloud.server.services.heartbeat_monitor import HeartbeatMonitor
from cloud.server.services.sse_broker import SSEBroker
from cloud.server.migrations import migrate_schema
from cloud.server.services.dispatch_reconciler import DispatchReconciler


@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(bind=engine)
    migrate_schema(engine)

    sse = SSEBroker()
    app.state.sse = sse

    mqtt = MQTTClient(sse_broker=sse)
    try:
        mqtt.connect()
    except Exception:
        pass
    app.state.mqtt = mqtt

    monitor = HeartbeatMonitor()
    monitor.start()
    app.state.monitor = monitor

    reconciler = DispatchReconciler(mqtt)
    reconciler.start()
    app.state.reconciler = reconciler

    yield

    try:
        reconciler.stop()
    except Exception:
        pass
    try:
        monitor.stop()
    except Exception:
        pass
    try:
        mqtt.disconnect()
    except Exception:
        pass


def create_app() -> FastAPI:
    app = FastAPI(
        title="NodeFlow Cloud Farm Manager",
        description="农场管理云平台 API - 地块管理、作业编排、M2M 下发",
        version="1.0.0",
        lifespan=lifespan,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(api_router, prefix="/api/v1")
    app.include_router(editor_router)

    @app.get("/api/v1/health")
    def health():
        return {
            "status": "ok",
            "sse_subscribers": app.state.sse.subscriber_count,
            "mqtt_connected": app.state.mqtt.is_connected,
        }

    return app


app = create_app()
