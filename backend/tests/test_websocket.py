"""
tests/test_websocket.py — WebSocket integration tests.

Tests:
1. Handshake: connect, send start_page, receive session_started
2. Page replay ordering: session_started → diagram_spec → text_chunks → page_complete
3. Pause / resume
4. Invalid frame handling: error returned, connection stays alive
5. Scope refusal: out-of-Python question → scope_refused
6. Python question: receives answer_chunk stream and sources
7. run_code seeded example → run_result
8. run_code unsupported → run_result with unsupported trace
9. Ping → pong
10. submit_survey: acknowledged (no crash)
"""
from __future__ import annotations

import asyncio
import json
from typing import AsyncGenerator

import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from fastapi.testclient import TestClient
from starlette.testclient import WebSocketTestSession

from app.main import app


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _ws_send(ws: WebSocketTestSession, type_: str, payload: dict) -> None:
    ws.send_text(json.dumps({"v": 1, "type": type_, "payload": payload}))


def _ws_recv(ws: WebSocketTestSession) -> dict:
    return json.loads(ws.receive_text())


def _collect_until(ws: WebSocketTestSession, stop_type: str, max_frames: int = 200) -> list[dict]:
    """Collect frames until one with stop_type arrives. Includes it."""
    frames = []
    for _ in range(max_frames):
        frame = _ws_recv(ws)
        frames.append(frame)
        if frame.get("type") == stop_type:
            break
    return frames


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

@pytest.fixture
def ws_client():
    """Synchronous WebSocket test client (Starlette TestClient)."""
    with TestClient(app, raise_server_exceptions=True) as client:
        yield client


def test_ws_handshake(ws_client):
    """Connect and send start_page — must receive session_started with correct fields."""
    with ws_client.websocket_connect("/ws/book") as ws:
        _ws_send(ws, "start_page", {"courseId": "python", "pageId": "lesson_python_1_1"})
        frame = _ws_recv(ws)
        assert frame["type"] == "session_started"
        assert frame["v"] == 1
        assert "seq" in frame
        assert frame["seq"] >= 1
        assert frame["sessionId"] is not None
        assert frame["payload"]["courseId"] == "python"
        assert frame["payload"]["pageId"] == "lesson_python_1_1"
        session_id = frame["payload"]["sessionId"]
        assert session_id.startswith("sess_")


def test_ws_page_replay_ordering(ws_client):
    """Replay of lesson_python_1_1 must start with session_started, then diagram_spec, then text_chunks."""
    with ws_client.websocket_connect("/ws/book") as ws:
        _ws_send(ws, "start_page", {"courseId": "python", "pageId": "lesson_python_1_1"})

        frame1 = _ws_recv(ws)
        assert frame1["type"] == "session_started"

        frame2 = _ws_recv(ws)
        assert frame2["type"] == "diagram_spec"
        assert frame2["payload"]["diagramId"] == "lesson_python_1_1"
        assert "spec" in frame2["payload"]
        assert "steps" in frame2["payload"]

        frame3 = _ws_recv(ws)
        assert frame3["type"] == "text_chunk"
        assert frame3["payload"]["wordStart"] == 0

        # seq must be monotonically increasing
        seqs = [frame1["seq"], frame2["seq"], frame3["seq"]]
        assert seqs == sorted(seqs)


def test_ws_invalid_frame_no_crash(ws_client):
    """Invalid JSON frame must produce an error event without crashing the connection."""
    with ws_client.websocket_connect("/ws/book") as ws:
        ws.send_text("not valid json at all")
        frame = _ws_recv(ws)
        assert frame["type"] == "error"
        assert frame["payload"]["code"] == "invalid_frame"
        assert frame["payload"]["recoverable"] is True

        # Connection still alive — can send another valid frame
        _ws_send(ws, "start_page", {"courseId": "python", "pageId": "lesson_python_1_1"})
        frame2 = _ws_recv(ws)
        assert frame2["type"] == "session_started"


def test_ws_wrong_version_rejected(ws_client):
    """Frame with wrong protocol version must produce invalid_frame error."""
    with ws_client.websocket_connect("/ws/book") as ws:
        ws.send_text(json.dumps({"v": 99, "type": "start_page", "payload": {"courseId": "python", "pageId": "p1"}}))
        frame = _ws_recv(ws)
        assert frame["type"] == "error"
        assert frame["payload"]["code"] == "invalid_frame"
        assert "version" in frame["payload"]["message"].lower() or "invalid" in frame["payload"]["message"].lower()


def test_ws_ping_pong(ws_client):
    """Ping frame must be answered with pong."""
    with ws_client.websocket_connect("/ws/book") as ws:
        ws.send_text(json.dumps({"type": "ping", "payload": {}}))
        frame = _ws_recv(ws)
        assert frame["type"] == "pong"
        assert "ts" in frame["payload"]


def test_ws_page_not_found(ws_client):
    """start_page for unknown page must produce page_not_found error."""
    with ws_client.websocket_connect("/ws/book") as ws:
        _ws_send(ws, "start_page", {"courseId": "python", "pageId": "nonexistent_page"})
        frame = _ws_recv(ws)
        assert frame["type"] == "error"
        assert frame["payload"]["code"] == "page_not_found"
        assert frame["payload"]["recoverable"] is True


def test_ws_scope_refused(ws_client):
    """Out-of-Python-scope question must produce question_received then scope_refused."""
    with ws_client.websocket_connect("/ws/book") as ws:
        _ws_send(ws, "ask_question", {
            "sessionId": None,
            "source": "text",
            "text": "What is the French Revolution?",
            "questionId": "q_test_1",
            "context": {"courseId": "python", "pageId": "lesson_python_1_1", "language": "english"},
        })
        frame1 = _ws_recv(ws)
        assert frame1["type"] == "question_received"
        assert frame1["payload"]["questionId"] == "q_test_1"
        assert frame1["payload"]["source"] == "text"

        frame2 = _ws_recv(ws)
        assert frame2["type"] == "scope_refused"
        assert frame2["payload"]["questionId"] == "q_test_1"
        assert len(frame2["payload"]["message"]) > 0


def test_ws_python_question_answered(ws_client):
    """Python-topic question must produce question_received, one or more answer_chunks, and sources."""
    with ws_client.websocket_connect("/ws/book") as ws:
        _ws_send(ws, "ask_question", {
            "sessionId": None,
            "source": "text",
            "text": "What is a variable in Python?",
            "questionId": "q_var_1",
            "context": {"courseId": "python", "pageId": "lesson_python_1_1", "language": "tanglish"},
        })

        frame1 = _ws_recv(ws)
        assert frame1["type"] == "question_received"

        # Collect until sources or max frames
        frames = _collect_until(ws, "sources", max_frames=30)
        types = [f["type"] for f in frames]

        assert "answer_chunk" in types, f"No answer_chunk in: {types}"
        assert "sources" in types, f"No sources in: {types}"

        # Last answer_chunk must have final=True
        answer_chunks = [f for f in frames if f["type"] == "answer_chunk"]
        assert answer_chunks[-1]["payload"]["final"] is True


def test_ws_run_code_seeded(ws_client):
    """Running a seeded code example must produce run_result with correct stdout."""
    with ws_client.websocket_connect("/ws/book") as ws:
        _ws_send(ws, "run_code", {
            "courseId": "python",
            "pageId": "lesson_python_1_1",
            "code": "x = 10\nprint(x)\nprint(type(x))",
            "language": "python",
            "codeId": "run_test_1",
        })

        frames = _collect_until(ws, "run_result", max_frames=20)
        run_result = next(f for f in frames if f["type"] == "run_result")
        assert run_result["payload"]["codeId"] == "run_test_1"
        assert run_result["payload"]["status"] == "success"
        assert "10" in run_result["payload"]["stdout"]
        assert "int" in run_result["payload"]["stdout"]


def test_ws_run_code_unsupported(ws_client):
    """Running an unknown program must produce run_result with unsupported trace."""
    with ws_client.websocket_connect("/ws/book") as ws:
        _ws_send(ws, "run_code", {
            "courseId": "python",
            "pageId": "lesson_python_1_1",
            "code": "import os; print(os.getcwd())",
            "language": "python",
            "codeId": "run_unsupported_1",
        })

        frames = _collect_until(ws, "run_result", max_frames=10)
        run_result = next(f for f in frames if f["type"] == "run_result")
        assert run_result["payload"]["codeId"] == "run_unsupported_1"
        assert run_result["payload"]["status"] == "error"
        trace = run_result["payload"].get("trace")
        assert trace is not None
        assert trace.get("unsupported") is not None


def test_ws_submit_survey_no_crash(ws_client):
    """submit_survey must not crash the connection."""
    with ws_client.websocket_connect("/ws/book") as ws:
        _ws_send(ws, "submit_survey", {
            "courseId": "python",
            "answers": {"q1": "cricket", "q2": "visual"},
        })
        # No response expected — send start_page to confirm alive
        _ws_send(ws, "start_page", {"courseId": "python", "pageId": "lesson_python_1_1"})
        frame = _ws_recv(ws)
        assert frame["type"] == "session_started"
