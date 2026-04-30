import logging
from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse

logger = logging.getLogger("routers.events")
router = APIRouter(prefix="/events", tags=["events"])


@router.get("/status")
async def status_stream(request: Request):
    sse = request.app.state.sse

    async def event_generator():
        subscription = sse.subscribe()
        try:
            async for msg in subscription:
                event_type = msg.get("event", "message")
                data = msg.get("data", "")
                yield f"event: {event_type}\ndata: {data}\n\n"
        except Exception as e:
            logger.error(f"SSE stream error: {e}")

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
