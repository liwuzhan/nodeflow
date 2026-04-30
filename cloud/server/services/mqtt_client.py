import json
import logging
import time
from typing import Callable

from paho.mqtt import client as mqtt

from cloud.server.config import settings
from cloud.server.database import SessionLocal
from cloud.server.models.machine import Machine
from cloud.server.models.edge_task import EdgeTask
from cloud.server.services.sse_broker import SSEBroker

logger = logging.getLogger("mqtt_client")

MqttCallback = Callable[[str, dict], None]


class MQTTClient:
    def __init__(self, sse_broker: SSEBroker | None = None):
        self._client = mqtt.Client(
            client_id=settings.MQTT_CLIENT_ID,
            protocol=mqtt.MQTTv311,
            callback_api_version=mqtt.CallbackAPIVersion.VERSION2,
        )
        self._client.on_connect = self._on_connect
        self._client.on_message = self._on_message
        self._sse = sse_broker
        self._callbacks: dict[str, list[MqttCallback]] = {}

    def on(self, event_type: str, callback: MqttCallback):
        self._callbacks.setdefault(event_type, []).append(callback)

    def connect(self):
        self._client.connect(settings.MQTT_BROKER, settings.MQTT_PORT, keepalive=60)
        self._client.loop_start()
        logger.info(f"MQTT connected to {settings.MQTT_BROKER}:{settings.MQTT_PORT}")

    def disconnect(self):
        self._client.loop_stop()
        self._client.disconnect()
        logger.info("MQTT disconnected")

    def publish(self, machine_id: str, payload: dict, qos: int = 1):
        topic = f"nodeflow/{machine_id}/task/dispatch"
        msg = json.dumps(payload)
        result = self._client.publish(topic, msg, qos=qos)
        logger.info(f"MQTT publish → {topic} (mid={result.mid})")
        return result

    def publish_cancel(self, machine_id: str, task_id: str):
        topic = f"nodeflow/{machine_id}/task/cancel"
        payload = json.dumps({
            "type": "task_cancel",
            "task_id": task_id,
            "machine_id": machine_id,
            "reason": "operator_request",
            "timestamp": time.time(),
        })
        self._client.publish(topic, payload, qos=1)
        logger.info(f"MQTT cancel → {topic}")

    def _on_connect(self, client, userdata, flags, reason_code, properties=None):
        if reason_code == 0:
            logger.info("MQTT connected OK")
            topics = [
                ("nodeflow/+/heartbeat", 0),
                ("nodeflow/+/status", 0),
                ("nodeflow/+/task/ack", 1),
            ]
            client.subscribe(topics)
            logger.info(f"Subscribed to {len(topics)} wildcard topics")
        else:
            logger.error(f"MQTT connect failed: reason_code={reason_code}")

    def _on_message(self, client, userdata, msg):
        try:
            payload = json.loads(msg.payload.decode("utf-8"))
            msg_type = payload.get("type", "")
            machine_id = payload.get("machine_id", "")

            if not machine_id:
                topic_parts = msg.topic.split("/")
                if len(topic_parts) >= 2:
                    machine_id = topic_parts[1]

            logger.debug(f"MQTT recv [{msg_type}] from {machine_id}")

            if msg_type == "heartbeat":
                self._handle_heartbeat(payload, machine_id)
            elif msg_type == "task_status":
                self._handle_task_status(payload)
            elif msg_type == "task_ack":
                self._handle_task_ack(payload)

            for cb in self._callbacks.get(msg_type, []):
                try:
                    cb(machine_id, payload)
                except Exception as e:
                    logger.error(f"Callback error for {msg_type}: {e}")

        except json.JSONDecodeError:
            logger.warning(f"Invalid JSON on {msg.topic}")
        except Exception as e:
            logger.error(f"MQTT message handler error: {e}", exc_info=True)

    def _handle_heartbeat(self, payload: dict, machine_id: str):
        db = SessionLocal()
        try:
            m = db.query(Machine).filter(Machine.id == machine_id).first()
            from datetime import datetime, timezone
            if m:
                if m.status == "unregistered":
                    pass  # keep unregistered until operator confirms
                else:
                    m.status = payload.get("state", "online" if m.status != "busy" else "busy")
                m.last_heartbeat = datetime.now(timezone.utc)
                m.current_task_id = payload.get("current_task_id")
                m.cpu_pct = payload.get("cpu_pct", 0)
                m.memory_mb = payload.get("memory_mb", 0)
                m.disk_free_gb = payload.get("disk_free_gb", 0)
                m.runtime_uptime_s = payload.get("runtime_uptime_seconds", 0)
                db.commit()
            else:
                # auto-discover: create machine as unregistered
                m = Machine(
                    id=machine_id,
                    name=machine_id,
                    machine_type="unknown",
                    status="unregistered",
                    last_heartbeat=datetime.now(timezone.utc),
                    cpu_pct=payload.get("cpu_pct", 0),
                    memory_mb=payload.get("memory_mb", 0),
                    runtime_uptime_s=payload.get("runtime_uptime_seconds", 0),
                )
                db.add(m)
                db.commit()
                logger.info(f"Discovered new machine: {machine_id} (pending confirmation)")

            if self._sse:
                self._sse.publish("heartbeat", {
                    "machine_id": machine_id,
                    "status": payload.get("state", "online"),
                    "current_task_id": payload.get("current_task_id"),
                    "timestamp": payload.get("timestamp"),
                })
        finally:
            db.close()

    def _handle_task_status(self, payload: dict):
        task_id = payload.get("task_id", "")
        if not task_id:
            return

        db = SessionLocal()
        try:
            t = db.query(EdgeTask).filter(EdgeTask.edge_task_id == task_id).first()
            if t:
                t.state = payload.get("state", t.state)
                t.progress_pct = payload.get("progress_pct", t.progress_pct)
                t.current_node = payload.get("current_node")
                t.error_code = payload.get("error_code")
                t.error_detail = payload.get("error_detail")

                if t.state in ("completed", "failed", "cancelled"):
                    t.completed_at = time.time()

                db.commit()

                # 步骤自动推进: 当前 step 所有 task 完成后下发下一步
                if t.state == "completed" and t.step_id:
                    self._try_advance_step(db, t)

                if self._sse:
                    self._sse.publish("task_status", {
                        "edge_task_id": task_id,
                        "state": t.state,
                        "progress_pct": t.progress_pct,
                        "current_node": t.current_node,
                        "machine_id": payload.get("machine_id", ""),
                    })
        finally:
            db.close()

    def _handle_task_ack(self, payload: dict):
        dispatch_id = payload.get("dispatch_id", "")
        accepted = payload.get("accepted", False)

        db = SessionLocal()
        try:
            t = db.query(EdgeTask).filter(EdgeTask.dispatch_id == dispatch_id).first()
            if t:
                if accepted:
                    t.state = "downloading"
                    t.dispatched_at = time.time()
                else:
                    t.error_detail = payload.get("reject_reason", "rejected by edge")
                db.commit()

                if self._sse:
                    self._sse.publish("task_ack", {
                        "edge_task_id": t.edge_task_id,
                        "accepted": accepted,
                        "dispatch_id": dispatch_id,
                    })
        finally:
            db.close()

    def _try_advance_step(self, db, edge_task):
        """一个 step 的所有 task 完成后，自动下发下一步"""
        from cloud.server.models.job import JobStep
        from cloud.server.services.dispatcher import Dispatcher

        # 幂等守卫: step 已完成则跳过
        step = db.query(JobStep).filter(JobStep.id == edge_task.step_id).first()
        if not step or step.status == "completed":
            return

        # 检查同 step 所有 task 是否都 completed
        step_tasks = db.query(EdgeTask).filter(
            EdgeTask.step_id == edge_task.step_id
        ).all()
        if not all(et.state == "completed" for et in step_tasks):
            return

        step.status = "completed"
        db.commit()
        logger.info(f"Step {step.seq_index} completed, advancing job {edge_task.job_id}")

        dispatcher = Dispatcher(self)
        dispatcher.dispatch_next_step(db, edge_task.job_id)
