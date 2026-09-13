import logging
import threading
import time

from cloud.server.config import settings
from cloud.server.database import SessionLocal
from cloud.server.models.edge_task import EdgeTask
from cloud.server.services.dispatcher import Dispatcher


logger = logging.getLogger("dispatch_reconciler")


class DispatchReconciler:
    def __init__(self, mqtt_client):
        self.dispatcher = Dispatcher(mqtt_client)
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self):
        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._loop,
            daemon=True,
            name="dispatch-reconciler",
        )
        self._thread.start()

    def stop(self):
        self._stop_event.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=5)

    def _loop(self):
        while not self._stop_event.wait(2.0):
            try:
                self.reconcile_once()
            except Exception:
                logger.exception("Dispatch reconciliation failed")

    def reconcile_once(self):
        db = SessionLocal()
        try:
            cutoff = time.time() - settings.DISPATCH_ACK_TIMEOUT_SECONDS
            expired = db.query(EdgeTask).filter(
                EdgeTask.state == "pending",
                EdgeTask.last_dispatch_at.isnot(None),
                EdgeTask.last_dispatch_at <= cutoff,
            ).all()
            for task in expired:
                try:
                    self.dispatcher.retry_dispatch(db, task.id)
                except ValueError as exc:
                    logger.warning("Task %s retry stopped: %s", task.edge_task_id, exc)

            expired_cancels = db.query(EdgeTask).filter(
                EdgeTask.state == "cancel_requested",
                EdgeTask.last_dispatch_at.isnot(None),
                EdgeTask.last_dispatch_at <= cutoff,
            ).all()
            for task in expired_cancels:
                if task.attempt >= settings.DISPATCH_MAX_RETRIES:
                    task.error_code = "CANCEL_ACK_TIMEOUT"
                    task.error_detail = "Cancel requested but edge confirmation was not received"
                    continue
                self.dispatcher.mqtt.publish_cancel(task.machine_id, task.edge_task_id)
                task.attempt += 1
                task.last_dispatch_at = time.time()

            step_ids = {
                step_id for (step_id,) in db.query(EdgeTask.step_id).filter(
                    EdgeTask.state == "queued",
                    EdgeTask.step_id.isnot(None),
                ).all()
            }
            for step_id in step_ids:
                self.dispatcher.dispatch_queued_tasks(db, step_id)
            db.commit()
        finally:
            db.close()
