"""
app/ws/gateway.py

WebSocket gateway for /ws/book.

Responsibilities:
- One WebSocket per reader tab (one MockBookService per connection)
- sessionId handshake: client sends start_page, server replies with session_started
- Resume by last seq: tracked in session table (B1 will use this; B0 tracks in memory)
- Heartbeat: responds to ping with pong
- Frame validation: every inbound frame goes through parse_client_event()
  Invalid frames → error event, connection stays alive
- Backpressure-safe send queue: asyncio.Queue drains to websocket.send_text()
- Graceful cleanup on disconnect or error
- Authentication is a stub in B0 (auth_stub module)
"""
from __future__ import annotations

import asyncio
import json
import logging
import time
from typing import Any

from fastapi import WebSocket, WebSocketDisconnect

from app.config import get_settings
from app.contracts.models import ErrorEvent, ErrorPayload, PongEvent, PongPayload
from app.contracts.validate import ParseError, parse_client_event
from app.services.mock_book_service import MockBookService

log = logging.getLogger(__name__)
settings = get_settings()


# ---------------------------------------------------------------------------
# Auth stub (B1 replaces this with a ticket flow)
# ---------------------------------------------------------------------------

class AuthStub:
    """
    B0 stub: always succeeds. No credentials required.
    B1: receive a short-lived ticket in the first frame or query param,
    validate it against the auth service, return a User model.
    """
    async def authenticate(self, websocket: WebSocket) -> dict:
        return {"user_id": None, "anonymous": True}


_auth = AuthStub()


# ---------------------------------------------------------------------------
# Send queue (backpressure)
# ---------------------------------------------------------------------------

class _SendQueue:
    """Drains a queue of JSON dicts to the WebSocket without blocking the event loop."""

    def __init__(self, websocket: WebSocket) -> None:
        self._ws = websocket
        self._queue: asyncio.Queue[dict | None] = asyncio.Queue(maxsize=512)
        self._task: asyncio.Task | None = None

    def start(self) -> None:
        self._task = asyncio.create_task(self._drain())

    async def send(self, data: dict) -> None:
        await self._queue.put(data)

    async def close(self) -> None:
        await self._queue.put(None)  # sentinel
        if self._task:
            try:
                await asyncio.wait_for(self._task, timeout=3.0)
            except (asyncio.TimeoutError, asyncio.CancelledError):
                self._task.cancel()

    async def _drain(self) -> None:
        while True:
            item = await self._queue.get()
            if item is None:
                break
            try:
                await self._ws.send_text(json.dumps(item))
            except Exception:
                break  # connection closed


# ---------------------------------------------------------------------------
# Connection handler
# ---------------------------------------------------------------------------

async def book_ws_handler(websocket: WebSocket) -> None:
    """Main WebSocket handler for /ws/book."""
    await websocket.accept()
    log.info("WS connected: %s", websocket.client)

    # Authenticate (stub in B0)
    try:
        _identity = await _auth.authenticate(websocket)
    except Exception as exc:
        log.warning("Auth failed: %s", exc)
        await websocket.close(code=4001, reason="auth failed")
        return

    # Set up send queue
    queue = _SendQueue(websocket)
    queue.start()

    async def send(data: dict) -> None:
        await queue.send(data)

    # Create per-connection service
    service = MockBookService(
        send=send,
        token_ms=settings.mock_token_ms,
        thinking_ms=settings.mock_thinking_ms,
        answer_token_ms=settings.mock_answer_token_ms,
        code_stream_ms=settings.mock_code_stream_ms,
    )

    # Monotonic seq for error frames (service manages its own)
    conn_seq = 0

    def _next_conn_seq() -> int:
        nonlocal conn_seq
        conn_seq += 1
        return conn_seq

    async def send_error(code: str, message: str, recoverable: bool = True) -> None:
        ev = ErrorEvent(
            seq=_next_conn_seq(),
            sessionId=None,
            ts=int(time.time() * 1000),
            payload=ErrorPayload(code=code, message=message, recoverable=recoverable),
        )
        await send(ev.model_dump(mode="json"))

    try:
        async for raw_message in websocket.iter_text():
            # ----------------------------------------------------------------
            # Parse & validate inbound frame
            # ----------------------------------------------------------------
            try:
                event = parse_client_event(raw_message)
            except ParseError as exc:
                log.debug("Invalid frame: %s", exc.message)
                await send_error("invalid_frame", exc.message, recoverable=True)
                continue
            except Exception as exc:
                log.exception("Unexpected parse error")
                await send_error("invalid_frame", str(exc), recoverable=True)
                continue

            # ----------------------------------------------------------------
            # Dispatch
            # ----------------------------------------------------------------
            etype = event.type

            # Connection-level: ping → pong
            if etype == "ping":
                pong = PongEvent(payload=PongPayload(ts=int(time.time() * 1000)))
                await send(pong.model_dump(mode="json"))
                continue

            # Protocol-level events
            p = event.payload

            if etype == "start_page":
                asyncio.create_task(service.handle_start_page(
                    course_id=p.courseId, page_id=p.pageId,
                ))

            elif etype == "pause":
                asyncio.create_task(service.handle_pause(session_id=p.sessionId))

            elif etype == "resume":
                asyncio.create_task(service.handle_resume(session_id=p.sessionId))

            elif etype == "seek":
                asyncio.create_task(service.handle_seek(
                    session_id=p.sessionId,
                    segment_id=p.segmentId,
                    word_index=p.wordIndex,
                ))

            elif etype == "speed":
                asyncio.create_task(service.handle_speed(
                    session_id=p.sessionId, value=p.value,
                ))

            elif etype == "ask_question":
                asyncio.create_task(service.handle_ask_question(
                    session_id=p.sessionId,
                    source=p.source,
                    text=p.text,
                    question_id=p.questionId,
                    context=p.context.model_dump(),
                ))

            elif etype == "run_code":
                asyncio.create_task(service.handle_run_code(
                    course_id=p.courseId,
                    page_id=p.pageId,
                    code=p.code,
                    language=p.language,
                    code_id=p.codeId,
                    stdin=p.stdin,
                    use_sample_input=p.useSampleInput,
                ))

            elif etype == "submit_survey":
                asyncio.create_task(service.handle_submit_survey(
                    course_id=p.courseId, answers=p.answers,
                ))

            elif etype == "audio_in":
                asyncio.create_task(service.handle_audio_in(
                    session_id=p.sessionId, seq=p.seq,
                    mime=p.mime, base64=p.base64, final=p.final,
                ))

            else:
                await send_error("unknown_event", f"Unknown event type: {etype!r}", recoverable=True)

    except WebSocketDisconnect:
        log.info("WS disconnected: %s", websocket.client)
    except Exception as exc:
        log.exception("WS handler error: %s", exc)
    finally:
        await service.dispose()
        await queue.close()
        log.info("WS cleanup complete")
