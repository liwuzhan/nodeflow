import json
import time
import logging

from runtime.task.models import TaskState

logger = logging.getLogger("task_reporter")


class StatusReporter:
    def __init__(self, mqtt_client, machine_id: str):
        self._mqtt = mqtt_client
        self._machine_id = machine_id

    def send_status(self, task_id: str, state: TaskState, progress_pct: float = 0.0,
                    current_node: str = "", error_detail: str = ""):
        payload = {
            "type": "task_status",
            "task_id": task_id,
            "machine_id": self._machine_id,
            "state": state.value,
            "progress_pct": progress_pct,
            "current_node": current_node,
            "nodes_healthy": 0,
            "nodes_total": 0,
            "error_detail": error_detail,
            "timestamp": time.time(),
        }
        self._publish("status", payload)

    def send_ack(self, task_id: str, dispatch_id: str, accepted: bool = True, reject_reason: str = ""):
        payload = {
            "type": "task_ack",
            "task_id": task_id,
            "dispatch_id": dispatch_id,
            "machine_id": self._machine_id,
            "accepted": accepted,
            "reject_reason": reject_reason,
            "timestamp": time.time(),
        }
        self._publish("task/ack", payload)

    def send_heartbeat(self, state: str = "online", current_task_id: str = ""):
        payload = {
            "type": "heartbeat",
            "machine_id": self._machine_id,
            "state": state,
            "current_task_id": current_task_id,
            "timestamp": time.time(),
        }
        self._publish("heartbeat", payload)

    def _publish(self, subtopic: str, payload: dict):
        try:
            topic = f"nodeflow/{self._machine_id}/{subtopic}"
            self._mqtt.publish(topic, json.dumps(payload), qos=0 if subtopic not in ("task/ack",) else 1)
        except Exception as e:
            logger.error(f"Failed to publish to {subtopic}: {e}")
