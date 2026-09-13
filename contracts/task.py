from enum import Enum


PROTOCOL_VERSION = "1.0"


class PlanningMode(str, Enum):
    EDGE = "edge"
    CLOUD = "cloud"
    CLOUD_PREFERRED = "cloud_preferred"


class FallbackPolicy(str, Enum):
    DENY = "deny"
    ALLOW_EDGE_REPLAN = "allow_edge_replan"


class TaskState(str, Enum):
    QUEUED = "queued"
    PENDING = "pending"
    DOWNLOADING = "downloading"
    READY = "ready"
    RUNNING = "running"
    CANCEL_REQUESTED = "cancel_requested"
    COMMUNICATION_LOST = "communication_lost"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


TERMINAL_TASK_STATES = {
    TaskState.COMPLETED.value,
    TaskState.FAILED.value,
    TaskState.CANCELLED.value,
}

_TASK_TRANSITIONS = {
    TaskState.QUEUED.value: {TaskState.PENDING.value, TaskState.CANCELLED.value},
    TaskState.PENDING.value: {
        TaskState.DOWNLOADING.value, TaskState.READY.value, TaskState.RUNNING.value,
        TaskState.COMPLETED.value, TaskState.FAILED.value,
        TaskState.CANCEL_REQUESTED.value, TaskState.CANCELLED.value,
    },
    TaskState.DOWNLOADING.value: {
        TaskState.READY.value, TaskState.RUNNING.value, TaskState.COMPLETED.value,
        TaskState.FAILED.value,
        TaskState.CANCEL_REQUESTED.value, TaskState.CANCELLED.value,
    },
    TaskState.READY.value: {
        TaskState.RUNNING.value, TaskState.COMPLETED.value, TaskState.FAILED.value,
        TaskState.CANCEL_REQUESTED.value, TaskState.CANCELLED.value,
    },
    TaskState.RUNNING.value: {
        TaskState.COMPLETED.value, TaskState.FAILED.value,
        TaskState.CANCEL_REQUESTED.value, TaskState.COMMUNICATION_LOST.value,
        TaskState.CANCELLED.value,
    },
    TaskState.CANCEL_REQUESTED.value: {
        TaskState.CANCELLED.value, TaskState.FAILED.value,
        TaskState.RUNNING.value, TaskState.COMMUNICATION_LOST.value,
    },
    TaskState.COMMUNICATION_LOST.value: {
        TaskState.RUNNING.value, TaskState.COMPLETED.value, TaskState.FAILED.value,
        TaskState.CANCEL_REQUESTED.value, TaskState.CANCELLED.value,
    },
}


def can_transition_task_state(current: str, incoming: str) -> bool:
    if current == incoming:
        return True
    if current in TERMINAL_TASK_STATES:
        return False
    return incoming in _TASK_TRANSITIONS.get(current, set())
