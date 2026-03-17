"""Chat endpoint — SSE streaming of agent responses."""

import asyncio
import json
import logging
import threading
import time

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse

from api.auth import require_auth, AuthUser
from api.schemas import ChatRequest
from api.session import session_manager

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/chat", tags=["chat"])


def _sse_event(event: str, data: dict) -> str:
    """Format a single SSE event."""
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"


@router.post("")
async def chat(body: ChatRequest, user: AuthUser = Depends(require_auth)):
    """Run the agent and stream back SSE events in real time."""
    if user.resy_email is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Resy account not linked",
        )

    session_id, agent = session_manager.get_or_create(body.session_id, resy_email=user.resy_email)

    # asyncio.Queue bridges the agent thread → async generator
    event_queue: asyncio.Queue = asyncio.Queue()
    loop = asyncio.get_event_loop()

    def event_callback(event_type: str, data: dict):
        logger.debug("Queuing SSE event: %s (data_keys=%s)", event_type, list(data.keys()))
        loop.call_soon_threadsafe(event_queue.put_nowait, (event_type, data))

    def run_agent():
        try:
            agent.run(body.message, event_callback=event_callback)
        except Exception as e:
            logger.error("Agent error in session %s: %s", session_id, e)
            loop.call_soon_threadsafe(event_queue.put_nowait, ("error", {"detail": str(e)}))
            loop.call_soon_threadsafe(event_queue.put_nowait, ("done", {}))

    async def event_stream():
        yield _sse_event("session", {"session_id": session_id})

        thread = threading.Thread(target=run_agent, daemon=True)
        thread.start()

        start_time = time.time()
        MAX_STREAM_SECONDS = 300  # 5 min absolute max

        while True:
            try:
                event_type, data = await asyncio.wait_for(event_queue.get(), timeout=120)
                logger.debug("Delivering SSE event: %s", event_type)
            except asyncio.TimeoutError:
                if time.time() - start_time > MAX_STREAM_SECONDS:
                    yield _sse_event("error", {"detail": "Request timed out"})
                    yield _sse_event("done", {})
                    break
                yield ": keepalive\n\n"
                continue

            yield _sse_event(event_type, data)

            if event_type == "done":
                break

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/history/{session_id}")
def get_history(session_id: str, _user: AuthUser = Depends(require_auth)):
    """Return conversation history for a session."""
    history = session_manager.get_history(session_id)
    return {"session_id": session_id, "history": history}


@router.delete("/session/{session_id}")
def delete_session(session_id: str, _user: AuthUser = Depends(require_auth)):
    """Delete a session and its agent."""
    deleted = session_manager.delete(session_id)
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")
    return {"deleted": True}
