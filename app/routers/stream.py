"""Server-Sent Events endpoint for live updates."""

import asyncio
import json
import logging

from fastapi import APIRouter, Request
from sse_starlette.sse import EventSourceResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["stream"])

# Connected SSE clients
_clients: list[asyncio.Queue] = []


async def broadcast(data: dict) -> None:
    """Send data to all connected SSE clients."""
    message = json.dumps(data)
    disconnected = []
    for q in _clients:
        try:
            q.put_nowait(message)
        except asyncio.QueueFull:
            disconnected.append(q)

    for q in disconnected:
        _clients.remove(q)


@router.get("/stream")
async def stream(request: Request):
    queue: asyncio.Queue = asyncio.Queue(maxsize=50)
    _clients.append(queue)

    async def event_generator():
        try:
            while True:
                if await request.is_disconnected():
                    break
                try:
                    message = await asyncio.wait_for(queue.get(), timeout=30.0)
                    yield {"data": message}
                except asyncio.TimeoutError:
                    # Send keepalive
                    yield {"comment": "keepalive"}
        finally:
            if queue in _clients:
                _clients.remove(queue)

    return EventSourceResponse(event_generator())
