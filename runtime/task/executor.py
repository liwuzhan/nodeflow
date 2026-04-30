import json
import time
import threading
from typing import Optional

from sdk.shared_buffer_lite import SharedBufferLite
from runtime.task.models import Task, TaskState, TaskProgress
from runtime.task.store import TaskStore
from runtime.utils.logger import setup_logger

logger = setup_logger("task_executor")


class TaskExecutor:
    def __init__(self, store: TaskStore, machine_id: str = ""):
        self.store = store
        self.machine_id = machine_id
        self._current_task_id: Optional[str] = None
        self._monitor_thread: Optional[threading.Thread] = None
        self._monitor_stop = threading.Event()

    @property
    def current_task_id(self) -> Optional[str]:
        return self._current_task_id

    def execute(self, task: Task):
        logger.info(f"Executing task {task.task_id} (preset={task.preset_yaml})")
        self._current_task_id = task.task_id
        self.store.update_state(task.task_id, TaskState.READY)

        control_buf = SharedBufferLite("runtime.control", create=False)
        payload = {
            "command": "start_dataflow",
            "task_id": task.task_id,
            "node_params": task.node_params,
            "timestamp": time.time(),
        }
        control_buf.write(payload)
        logger.info(f"Task {task.task_id} dispatched to runtime daemon")

        self.store.update_state(task.task_id, TaskState.RUNNING)
        self._start_monitor(task)

    def cancel(self, task_id: str):
        logger.info(f"Cancelling task {task_id}")
        self._stop_monitor()
        control_buf = SharedBufferLite("runtime.control", create=False)
        control_buf.write({
            "command": "stop_dataflow",
            "task_id": task_id,
            "timestamp": time.time(),
        })
        self.store.update_state(task_id, TaskState.CANCELLED)
        if self._current_task_id == task_id:
            self._current_task_id = None

    def _start_monitor(self, task: Task):
        self._monitor_stop.clear()
        self._monitor_thread = threading.Thread(
            target=self._monitor_loop,
            args=(task,),
            daemon=True,
        )
        self._monitor_thread.start()

    def _stop_monitor(self):
        self._monitor_stop.set()
        if self._monitor_thread and self._monitor_thread.is_alive():
            self._monitor_thread.join(timeout=2)

    def _monitor_loop(self, task: Task):
        interval = 60
        while not self._monitor_stop.wait(interval):
            try:
                progress = self._compute_progress(task)
                logger.info(
                    f"Task {task.task_id} progress: {progress.progress_pct:.0f}% "
                    f"node={progress.current_node} "
                    f"healthy={progress.nodes_healthy}/{progress.nodes_total}"
                )
            except Exception as e:
                logger.error(f"Progress monitor error: {e}")

    def _compute_progress(self, task: Task) -> TaskProgress:
        progress = TaskProgress(
            task_id=task.task_id,
            machine_id=self.machine_id,
            state=task.state,
        )
        try:
            buf = SharedBufferLite("runtime.control", create=False, size=4096)
            seq = buf.get_sequence()
            progress.current_node = f"seq:{seq}"
        except Exception:
            progress.current_node = "unknown"
        return progress

    def mark_completed(self, task_id: str):
        self._stop_monitor()
        self.store.update_state(task_id, TaskState.COMPLETED)
        if self._current_task_id == task_id:
            self._current_task_id = None

    def mark_failed(self, task_id: str, error: str):
        self._stop_monitor()
        self.store.update_state(task_id, TaskState.FAILED, error_message=error)
        if self._current_task_id == task_id:
            self._current_task_id = None
