import logging
import threading
import time
from datetime import datetime, timezone

from cloud.server.config import settings
from cloud.server.database import SessionLocal
from cloud.server.models.machine import Machine
from cloud.server.models.edge_task import EdgeTask

logger = logging.getLogger("heartbeat_monitor")


class HeartbeatMonitor:
    def __init__(self):
        self._running = False
        self._thread: threading.Thread | None = None

    def start(self):
        self._running = True
        self._thread = threading.Thread(target=self._loop, daemon=True, name="heartbeat-monitor")
        self._thread.start()
        logger.info("Heartbeat monitor started")

    def stop(self):
        self._running = False
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=5)
        logger.info("Heartbeat monitor stopped")

    def _loop(self):
        while self._running:
            time.sleep(30)
            try:
                self._check()
            except Exception as e:
                logger.error(f"Heartbeat check error: {e}")

    def _check(self):
        db = SessionLocal()
        try:
            now = datetime.now(timezone.utc)
            machines = db.query(Machine).filter(
                Machine.status.notin_(["offline", "unregistered"])
            ).all()

            for m in machines:
                if m.last_heartbeat is None:
                    continue
                age = (now - m.last_heartbeat).total_seconds()
                if age > settings.HEARTBEAT_TIMEOUT_SECONDS:
                    logger.warning(f"Machine {m.id} offline (last heartbeat {age:.0f}s ago)")
                    m.status = "offline"
                    m.current_task_id = None
                    m.current_job_id = None

                    db.query(EdgeTask).filter(
                        EdgeTask.machine_id == m.id,
                        EdgeTask.state.in_(["pending", "downloading", "ready", "running"]),
                    ).update({
                        "state": "failed",
                        "error_code": "MACHINE_OFFLINE",
                        "error_detail": f"Machine offline for {age:.0f}s",
                        "completed_at": time.time(),
                    }, synchronize_session=False)

            db.commit()
        finally:
            db.close()
