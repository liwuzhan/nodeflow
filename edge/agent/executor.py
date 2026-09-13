import time
import threading
import os
import subprocess
import math
from pathlib import Path
from typing import Optional

from edge.sdk.shared_buffer_lite import SharedBufferLite
from edge.agent.models import Task, TaskState, TaskProgress
from edge.agent.store import TaskStore
from edge.runtime.utils.logger import setup_logger

logger = setup_logger("task_executor")

RUNTIME_PID_FILE = Path("/tmp/nodeflow_runtime.pid")


def _runtime_process_running() -> bool:
    if not RUNTIME_PID_FILE.exists():
        return False
    try:
        lines = RUNTIME_PID_FILE.read_text().splitlines()
        if not lines:
            return False
        pid = int(lines[0].strip())
    except (OSError, ValueError):
        return False

    try:
        os.kill(pid, 0)
    except PermissionError:
        return True
    except (ProcessLookupError, OSError):
        return False

    try:
        ps = subprocess.run(
            ["ps", "-p", str(pid), "-o", "stat="],
            capture_output=True,
            text=True,
            timeout=1,
        )
        if ps.returncode == 0 and ps.stdout.strip().startswith("Z"):
            return False
    except Exception:
        pass

    return True


class TaskExecutor:
    def __init__(self, store: TaskStore, machine_id: str = ""):
        self.store = store
        self.machine_id = machine_id
        self._current_task_id: Optional[str] = None
        self._monitor_thread: Optional[threading.Thread] = None
        self._monitor_stop = threading.Event()
        self._on_progress = None
        self._on_completed = None
        self._on_failed = None

    def set_callbacks(self, on_progress=None, on_completed=None, on_failed=None):
        self._on_progress = on_progress
        self._on_completed = on_completed
        self._on_failed = on_failed

    @property
    def current_task_id(self) -> Optional[str]:
        return self._current_task_id

    def execute(self, task: Task) -> bool:
        """返回 True 表示 buffer 写入成功，False 表示 buffer 尚不存在需重试"""
        logger.info(f"Executing task {task.task_id} (preset={task.preset_yaml})")
        self._current_task_id = task.task_id
        self.store.update_state(task.task_id, TaskState.READY)

        if not _runtime_process_running():
            logger.warning(f"Runtime not running for task {task.task_id}")
            if self._current_task_id == task.task_id:
                self._current_task_id = None
            return False

        try:
            control_buf = SharedBufferLite("runtime.control", create=False)
        except FileNotFoundError:
            logger.warning(f"Control buffer not ready for task {task.task_id}")
            if self._current_task_id == task.task_id:
                self._current_task_id = None
            return False

        payload = {
            "command": "start_dataflow",
            "task_id": task.task_id,
            "preset_yaml": task.preset_yaml,
            "node_params": task.node_params,
            "timestamp": time.time(),
        }
        control_buf.write(payload)
        control_buf.close()
        logger.info(f"Task {task.task_id} dispatched to runtime daemon")

        self.store.update_state(task.task_id, TaskState.RUNNING)
        self._start_monitor(task)
        return True

    def cancel(self, task_id: str):
        logger.info(f"Cancelling task {task_id}")
        self._stop_monitor()
        if _runtime_process_running():
            try:
                control_buf = SharedBufferLite("runtime.control", create=False)
                control_buf.write({
                    "command": "stop_dataflow",
                    "task_id": task_id,
                    "timestamp": time.time(),
                })
                control_buf.close()
            except FileNotFoundError:
                logger.warning(f"Cannot cancel {task_id}: control buffer not found")
        else:
            logger.warning(f"Cannot cancel {task_id}: runtime not running")
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
        if (
            self._monitor_thread
            and self._monitor_thread.is_alive()
            and self._monitor_thread is not threading.current_thread()
        ):
            self._monitor_thread.join(timeout=2)

    def _monitor_loop(self, task: Task):
        interval = 1.0
        report_ticks = 0
        completion_ticks = 0
        while not self._monitor_stop.wait(interval):
            try:
                progress = self._compute_progress(task)
                report_ticks += 1
                if report_ticks >= 10:
                    report_ticks = 0
                    if self._on_progress:
                        self._on_progress(progress)
                    logger.info(f"Task {task.task_id}: progress={progress.progress_pct:.1f}% "
                                f"node={progress.current_node}")

                runtime_status = self._read_buffer("runtime.status")
                stored_task = self.store.get(task.task_id)
                started_at = stored_task.started_at if stored_task else None
                if (
                    runtime_status
                    and runtime_status.get("command_status") == "failed"
                    and runtime_status.get("active_task_id", "") in ("", task.task_id)
                    and float(runtime_status.get("timestamp", 0.0) or 0.0) >= float(started_at or 0.0)
                ):
                    error = runtime_status.get("error") or "runtime command failed"
                    self.mark_failed(task.task_id, error)
                    if self._on_failed:
                        self._on_failed(task.task_id, error)
                    return

                if self._is_safely_completed():
                    completion_ticks += 1
                else:
                    completion_ticks = 0
                if completion_ticks >= 3:
                    self._stop_dataflow(task.task_id)
                    self.mark_completed(task.task_id)
                    if self._on_completed:
                        self._on_completed(task.task_id)
                    return
            except Exception as e:
                logger.error(f"Progress monitor error: {e}")

    def _compute_progress(self, task: Task) -> TaskProgress:
        stored = self.store.get(task.task_id)
        progress = TaskProgress(
            task_id=task.task_id,
            machine_id=self.machine_id,
            state=stored.state if stored else task.state,
            progress_pct=0.0,
            current_node="unknown",
        )
        next_point = self._read_buffer("waypoint_selector.next_point")
        if next_point:
            total = max(0, int(next_point.get("total", 0) or 0))
            consumed = max(0, int(next_point.get("consumed", 0) or 0))
            if total:
                progress.progress_pct = min(100.0, consumed * 100.0 / total)
            progress.current_node = "waypoint_selector"
        else:
            runtime_status = self._read_buffer("runtime.status")
            if runtime_status and runtime_status.get("dataflow_running"):
                progress.current_node = "dataflow"
        return progress

    @staticmethod
    def _read_buffer(name: str) -> dict | None:
        try:
            buf = SharedBufferLite(name, create=False)
            value = buf.read()
            buf.close()
            return value
        except Exception:
            return None

    def _is_safely_completed(self) -> bool:
        target = self._read_buffer("waypoint_selector.next_point")
        pose = self._read_buffer("coord_transform.pose_enu")
        velocity = self._read_buffer("track_controller.velocity_cmd")
        tillage = self._read_buffer("tillage_controller.tillage_status")
        if not target or not pose or not velocity or not tillage or not target.get("final"):
            return False
        distance = math.hypot(
            float(pose.get("x", 0.0)) - float(target.get("x", 0.0)),
            float(pose.get("y", 0.0)) - float(target.get("y", 0.0)),
        )
        stopped = (
            abs(float(velocity.get("linear_velocity", 0.0))) <= 0.05
            and abs(float(velocity.get("angular_velocity", 0.0))) <= 0.05
        )
        implement_safe = (
            tillage.get("state") == "transport"
            and not bool(tillage.get("pto_on", False))
            and float(tillage.get("hitch_height", 0.0)) <= 0.05
        )
        return distance <= 1.5 and stopped and implement_safe

    @staticmethod
    def _stop_dataflow(task_id: str):
        try:
            buf = SharedBufferLite("runtime.control", create=False)
            buf.write({
                "command": "stop_dataflow",
                "task_id": task_id,
                "timestamp": time.time(),
            })
            buf.close()
        except Exception as exc:
            logger.warning(f"Failed to stop completed task {task_id}: {exc}")

    def mark_completed(self, task_id: str):
        self._stop_monitor()
        self._current_task_id = None
        self.store.update_state(task_id, TaskState.COMPLETED)

    def mark_failed(self, task_id: str, error: str):
        """统一失败收敛：清理执行器状态 + 标记任务失败"""
        self._stop_monitor()
        self._current_task_id = None
        self.store.update_state(task_id, TaskState.FAILED, error_message=error)
