#!/usr/bin/env python3
"""
TaskAgent standalone entry point.

Usage:
    python3 -m runtime.task.agent_main

Environment variables:
    NF_MQTT_BROKER    MQTT broker URL (default: localhost)
    NF_MQTT_PORT      MQTT port (default: 1883)
    NF_MACHINE_ID     Machine ID (default: hostname)
    NF_TASK_AUTO_ACCEPT  Auto-accept tasks (default: true)
    NF_HTTP_SERVER_URL   Cloud HTTP server for payloads
"""

import signal
import sys
import logging
from runtime.task.agent import TaskAgent

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
)
logger = logging.getLogger("task_agent_main")

agent = TaskAgent()


def shutdown(sig=None, frame=None):
    logger.info("Shutting down...")
    agent.stop()
    sys.exit(0)


signal.signal(signal.SIGINT, shutdown)
signal.signal(signal.SIGTERM, shutdown)

logger.info("=" * 50)
logger.info("NodeFlow TaskAgent starting")
logger.info("=" * 50)
agent.start()

signal.pause()
