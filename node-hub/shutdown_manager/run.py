#!/usr/bin/env python3
import sys
import time
from pathlib import Path
from typing import Optional

# Pydantic 导入
try:
    from pydantic import BaseModel, Field
except ImportError:
    class BaseModel: pass
    def Field(*args, **kwargs): return None

project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from sdk.nodeflow_sdk import NodeFlowSDK
from sdk.shared_buffer_lite import SharedBufferLite

# --- Schema Definitions ---

class IdleEvent(BaseModel):
    shutdown: bool
    reason: str
    window_secs: float
    idle_radius_m: float
    timestamp: float

class ShutdownStatus(BaseModel):
    emitted: bool
    ts: float

# --- End Schema Definitions ---

class ShutdownManager:
    def __init__(self, sdk: NodeFlowSDK):
        p = sdk.params
        self.debounce_secs = float(p.get("debounce_secs", 5.0))
        self.last_emit = 0.0
        self.trigger_port = sdk.create_input_port("idle_event")
        self.status_port = sdk.create_output_port("shutdown_status", schema=ShutdownStatus)
        self.buf = SharedBufferLite("control.shutdown_request", create=True)

    def run(self):
        try:
            while True:
                evt = self.trigger_port.recv_latest()
                # Check for shutdown flag using .get() because recv_latest returns dict
                if evt and evt.get("shutdown"):
                    now = time.time()
                    if (now - self.last_emit) >= self.debounce_secs:
                        try:
                            self.buf.write(evt)
                            self.status_port.send({"emitted": True, "ts": now})
                            self.last_emit = now
                        except Exception:
                            pass
                time.sleep(0.1)
        except KeyboardInterrupt:
            pass
        finally:
            try:
                self.buf.close()
            except Exception:
                pass


def main():
    with NodeFlowSDK(log_level="INFO") as sdk:
        node = ShutdownManager(sdk)
        node.run()


if __name__ == "__main__":
    main()

