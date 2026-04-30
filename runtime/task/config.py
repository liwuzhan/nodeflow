import os


class TaskAgentConfig:
    def __init__(self):
        self.mqtt_broker = os.getenv("NF_MQTT_BROKER", "localhost")
        self.mqtt_port = int(os.getenv("NF_MQTT_PORT", "1883"))
        self.machine_id = os.getenv("NF_MACHINE_ID", os.uname().nodename if hasattr(os, "uname") else "edge-01")
        self.auto_accept = os.getenv("NF_TASK_AUTO_ACCEPT", "true").lower() == "true"
        self.http_server_url = os.getenv("NF_HTTP_SERVER_URL", "http://localhost:8080")
        self.client_id = f"nodeflow-{self.machine_id}"

    @classmethod
    def from_env(cls) -> "TaskAgentConfig":
        return cls()
