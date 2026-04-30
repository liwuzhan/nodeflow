import json
import os
import time
import threading
from pathlib import Path
from typing import Optional, List

from runtime.task.models import Task, TaskState


class TaskStore:
    STORE_PATH = "/tmp/nodeflow/tasks.json"

    def __init__(self):
        self._lock = threading.Lock()
        self._tasks: dict[str, Task] = {}
        self._load()

    def _load(self):
        path = Path(self.STORE_PATH)
        if path.exists():
            try:
                with open(path, "r") as f:
                    raw = json.load(f)
                for item in raw:
                    task = Task.from_dict(item)
                    self._tasks[task.task_id] = task
            except (json.JSONDecodeError, KeyError):
                os.remove(path)

    def _save(self):
        path = Path(self.STORE_PATH)
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = str(path) + ".tmp"
        data = [t.to_dict() for t in self._tasks.values()]
        with open(tmp, "w") as f:
            json.dump(data, f, indent=2)
        os.replace(tmp, str(path))

    def get_all(self) -> List[Task]:
        with self._lock:
            return list(self._tasks.values())

    def get_active(self) -> List[Task]:
        with self._lock:
            return [
                t for t in self._tasks.values()
                if t.state in (TaskState.PENDING, TaskState.DOWNLOADING,
                               TaskState.READY, TaskState.RUNNING)
            ]

    def get(self, task_id: str) -> Optional[Task]:
        with self._lock:
            return self._tasks.get(task_id)

    def exists(self, task_id: str) -> bool:
        with self._lock:
            return task_id in self._tasks

    def save(self, task: Task):
        with self._lock:
            self._tasks[task.task_id] = task
            self._save()

    def update_state(self, task_id: str, state: TaskState, **kwargs):
        with self._lock:
            task = self._tasks.get(task_id)
            if task is None:
                return
            task.state = state
            if state == TaskState.RUNNING and task.started_at is None:
                task.started_at = time.time()
            if state in (TaskState.COMPLETED, TaskState.FAILED, TaskState.CANCELLED):
                task.completed_at = time.time()
            for k, v in kwargs.items():
                if hasattr(task, k):
                    setattr(task, k, v)
            self._save()

    def remove(self, task_id: str):
        with self._lock:
            self._tasks.pop(task_id, None)
            self._save()
