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

    def execute(self, task: Task) -> bool:
        """返回 True 表示 buffer 写入成功，False 表示 buffer 尚不存在需重试"""
        logger.info(f"Executing task {task.task_id} (preset={task.preset_yaml})")
        self._current_task_id = task.task_id
        self.store.update_state(task.task_id, TaskState.READY)

        try:
            control_buf = SharedBufferLite("runtime.control", create=False)
        except FileNotFoundError:
            logger.warning(f"Control buffer not ready for task {task.task_id}")
            return False

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
        return True

    def cancel(self, task_id: str):
        logger.info(f"Cancelling task {task_id}")
        self._stop_monitor()
        try:
            control_buf = SharedBufferLite("runtime.control", create=False)
            control_buf.write({
                "command": "stop_dataflow",
                "task_id": task_id,
                "timestamp": time.time(),
            })
        except FileNotFoundError:
            logger.warning(f"Cannot cancel {task_id}: control buffer not found")
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
                logger.info(f"Task {task.task_id}: state={progress.state.value} "
                            f"node={progress.current_node}")
            except Exception as e:
                logger.error(f"Progress monitor error: {e}")

    def _compute_progress(self, task: Task) -> TaskProgress:
        progress = TaskProgress(
            task_id=task.task_id,
            machine_id=self.machine_id,
            state=task.state,
            progress_pct=0.0,
            current_node="unknown",
        )
        try:
            buf = SharedBufferLite("runtime.control", create=False)
            seq = buf.get_sequence()
            if seq > 0:
                progress.current_node = "dispatched"
        except Exception:
            pass
        return progress

    def mark_completed(self, task_id: str):
        self._stop_monitor()
        self._current_task_id = None
        self.store.update_state(task_id, TaskState.COMPLETED)

    def mark_failed(self, task_id: str, error: str):
        """统一失败收敛：清理执行器状态 + 标记任务失败"""
        self._stop_monitor()
        self._current_task_id = None
        self.store.update_state(task_id, TaskState.FAILED, error_message=error)
