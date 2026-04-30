import json
import time
import threading
import logging

import paho.mqtt.client as mqtt

from runtime.task.config import TaskAgentConfig
from runtime.task.models import Task, TaskState
from runtime.task.store import TaskStore
from runtime.task.executor import TaskExecutor
from runtime.task.reporter import StatusReporter

logger = logging.getLogger("task_agent")


class TaskAgent:
    def __init__(self, config: TaskAgentConfig = None):
        self._config = config or TaskAgentConfig.from_env()
        self._store = TaskStore()
        self._executor = TaskExecutor(self._store, self._config.machine_id)
        self._reporter: StatusReporter | None = None
        self._running = False
        self._heartbeat_timer: threading.Timer | None = None
        self._running_timers: dict[str, threading.Timer] = {}  # task_id → RUNNING delay timer

        self._client = mqtt.Client(
            client_id=self._config.client_id,
            protocol=mqtt.MQTTv311,
            callback_api_version=mqtt.CallbackAPIVersion.VERSION2,
        )
        self._client.on_connect = self._on_connect
        self._client.on_message = self._on_message
        self._client.on_disconnect = self._on_disconnect

    def start(self):
        self._reporter = StatusReporter(self._client, self._config.machine_id)
        self._client.connect(self._config.mqtt_broker, self._config.mqtt_port, keepalive=60)
        self._client.loop_start()
        self._running = True
        self._start_heartbeat()
        logger.info(f"TaskAgent started: {self._config.client_id} → {self._config.mqtt_broker}")

    def stop(self):
        self._running = False
        self._stop_heartbeat()
        self._client.loop_stop()
        self._client.disconnect()
        logger.info("TaskAgent stopped")

    def _on_connect(self, client, userdata, flags, reason_code, properties=None):
        if reason_code == 0:
            client.subscribe([(f"nodeflow/{self._config.machine_id}/task/dispatch", 1),
                              (f"nodeflow/{self._config.machine_id}/task/cancel", 1)])
            logger.info(f"Subscribed to nodeflow/{self._config.machine_id}/task/#")
        else:
            logger.error(f"MQTT connect failed: reason_code={reason_code}")

    def _on_disconnect(self, client, userdata, flags, reason_code, properties=None):
        logger.warning(f"MQTT disconnected (reason={reason_code}), will auto-reconnect")

    def _on_message(self, client, userdata, msg):
        try:
            payload = json.loads(msg.payload.decode("utf-8"))
            msg_type = payload.get("type", "")
            logger.info(f"MQTT ← [{msg_type}] on {msg.topic}")

            if msg_type == "task_dispatch":
                self._handle_dispatch(payload)
            elif msg_type == "task_cancel":
                self._handle_cancel(payload)
        except json.JSONDecodeError:
            logger.warning(f"Invalid JSON on {msg.topic}")
        except Exception as e:
            logger.error(f"Message handler error: {e}", exc_info=True)

    def _handle_dispatch(self, payload: dict):
        task_id = payload["task_id"]
        dispatch_id = payload.get("dispatch_id", "")
        machine_id = payload.get("machine_id", self._config.machine_id)

        # 去重: 已存在的 task 发送拒绝 ACK
        if self._store.exists(task_id):
            logger.info(f"Task {task_id} duplicate, sending reject ACK")
            self._reporter.send_ack(task_id, dispatch_id, accepted=False,
                                    reject_reason="duplicate_task_id")
            return

        task = Task(
            task_id=task_id,
            job_id=payload.get("job_id", ""),
            preset_yaml=payload.get("preset_yaml", ""),
            operation_type=payload.get("operation_type", ""),
            sequence_index=payload.get("sequence_index", 0),
            machine_id=machine_id,
            parcel_ref=payload.get("parcel_ref"),
            parcel_data=payload.get("parcel_data"),
            parcel_url=payload.get("parcel_url"),
            path_url=payload.get("path_url"),
            node_params=payload.get("node_params", {}),
            state=TaskState.PENDING,
        )
        self._store.save(task)
        self._reporter.send_ack(task_id, dispatch_id, accepted=True)

        if self._config.auto_accept:
            logger.info(f"Auto-accepting task {task_id}")
            self._reporter.send_status(task_id, TaskState.DOWNLOADING)
            self._reporter.send_status(task_id, TaskState.READY)

            try:
                ok = self._executor.execute(task)
                if ok:
                    self._schedule_running_report(task.task_id)
                else:
                    threading.Thread(
                        target=self._retry_execute,
                        args=(task,),
                        daemon=True,
                    ).start()
            except Exception as e:
                logger.error(f"Task {task_id} dispatch failed: {e}")
                self._executor.mark_failed(task_id, str(e))
                self._reporter.send_status(task_id, TaskState.FAILED,
                                           error_detail=str(e))

    def _schedule_running_report(self, task_id: str):
        """延迟 2s 上报 RUNNING，带状态守卫防止覆盖已失败/取消的任务"""
        def _report_if_still_ok():
            self._running_timers.pop(task_id, None)
            task = self._store.get(task_id)
            if task and task.state == TaskState.RUNNING:
                self._reporter.send_status(task_id, TaskState.RUNNING)

        timer = threading.Timer(2.0, _report_if_still_ok)
        self._running_timers[task_id] = timer
        timer.start()

    def _cancel_running_timer(self, task_id: str):
        timer = self._running_timers.pop(task_id, None)
        if timer:
            timer.cancel()

    def _retry_execute(self, task: Task):
        """工作线程中重试 execute，避免阻塞 MQTT 回调线程"""
        deadline = time.time() + 10
        while time.time() < deadline:
            time.sleep(0.5)
            # 检查是否已被取消
            t = self._store.get(task.task_id)
            if t and t.state in (TaskState.CANCELLED, TaskState.FAILED):
                return
            try:
                ok = self._executor.execute(task)
                if ok:
                    self._schedule_running_report(task.task_id)
                    return
            except Exception:
                pass
        logger.error(f"Task {task.task_id} failed: control buffer unavailable after retries")
        self._executor.mark_failed(task.task_id, "Control buffer unavailable")
        self._reporter.send_status(task.task_id, TaskState.FAILED,
                                   error_detail="Control buffer unavailable")

    def _handle_cancel(self, payload: dict):
        task_id = payload["task_id"]
        if not self._store.exists(task_id):
            logger.warning(f"Cancel for unknown task {task_id}, ignored")
            return
        logger.info(f"Cancelling task {task_id}")
        # 1. 停止 RUNNING 延迟定时器（防止覆盖取消状态）
        self._cancel_running_timer(task_id)
        # 2. 写 stop_dataflow 到 control buffer 让 daemon 停止数据流
        self._executor.cancel(task_id)
        # 3. 上报 CANCELLED（云端和边侧状态一致）
        self._reporter.send_status(task_id, TaskState.CANCELLED)

    def _start_heartbeat(self):
        self._send_heartbeat()
        if self._running:
            self._heartbeat_timer = threading.Timer(30, self._start_heartbeat)
            self._heartbeat_timer.daemon = True
            self._heartbeat_timer.start()

    def _stop_heartbeat(self):
        if self._heartbeat_timer:
            self._heartbeat_timer.cancel()
            self._heartbeat_timer = None

    def _send_heartbeat(self):
        state = "busy" if self._executor.current_task_id else "online"
        self._reporter.send_heartbeat(state=state, current_task_id=self._executor.current_task_id or "")
