import asyncio
import json
import logging
import threading
from typing import AsyncGenerator

logger = logging.getLogger("sse_broker")


class SSEBroker:
    def __init__(self):
        self._subscribers: list[tuple[asyncio.AbstractEventLoop, asyncio.Queue]] = []
        self._lock = threading.Lock()

    def publish(self, event_type: str, data: dict):
        payload = {"event": event_type, "data": json.dumps(data, default=str)}
        with self._lock:
            subscribers = list(self._subscribers)
        for loop, queue in subscribers:
            loop.call_soon_threadsafe(
                lambda q=queue, p=payload: q.put_nowait(p) if not q.full() else None
            )

    async def subscribe(self) -> AsyncGenerator[dict, None]:
        queue: asyncio.Queue = asyncio.Queue(maxsize=256)
        loop = asyncio.get_running_loop()
        with self._lock:
            self._subscribers.append((loop, queue))
        try:
            while True:
                msg = await queue.get()
                yield msg
        except asyncio.CancelledError:
            pass
        finally:
            with self._lock:
                self._subscribers.remove((loop, queue))

    @property
    def subscriber_count(self) -> int:
        with self._lock:
            return len(self._subscribers)
