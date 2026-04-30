import asyncio
import json
import logging
from typing import AsyncGenerator

logger = logging.getLogger("sse_broker")


class SSEBroker:
    def __init__(self):
        self._queues: list[asyncio.Queue] = []

    def publish(self, event_type: str, data: dict):
        for q in self._queues:
            try:
                q.put_nowait({"event": event_type, "data": json.dumps(data, default=str)})
            except asyncio.QueueFull:
                pass

    async def subscribe(self) -> AsyncGenerator[dict, None]:
        queue: asyncio.Queue = asyncio.Queue(maxsize=256)
        self._queues.append(queue)
        try:
            while True:
                msg = await queue.get()
                yield msg
        except asyncio.CancelledError:
            pass
        finally:
            self._queues.remove(queue)

    @property
    def subscriber_count(self) -> int:
        return len(self._queues)
