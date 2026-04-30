import os
from pathlib import Path
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    PROJECT_ROOT: Path = Path(__file__).resolve().parent.parent.parent

    DATABASE_URL: str = f"sqlite:///{Path(__file__).resolve().parent / 'farm.db'}"

    MQTT_BROKER: str = "localhost"
    MQTT_PORT: int = 1883
    MQTT_CLIENT_ID: str = "nodeflow-cloud"

    HEARTBEAT_TIMEOUT_SECONDS: int = 300
    DISPATCH_ACK_TIMEOUT_SECONDS: int = 30
    DISPATCH_MAX_RETRIES: int = 3

    AUTH_ENABLED: bool = False

    HTTP_SERVER_HOST: str = "0.0.0.0"
    HTTP_SERVER_PORT: int = 8080

    model_config = {"env_prefix": "NF_CLOUD_", "case_sensitive": False}


settings = Settings()
