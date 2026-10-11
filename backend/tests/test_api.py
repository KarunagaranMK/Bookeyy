"""
tests/test_api.py — REST endpoint tests.
"""
from __future__ import annotations

import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport

from app.main import app


@pytest_asyncio.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


@pytest.mark.asyncio
async def test_health(client: AsyncClient):
    resp = await client.get("/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"


@pytest.mark.asyncio
async def test_list_courses(client: AsyncClient):
    resp = await client.get("/api/courses")
    assert resp.status_code == 200
    courses = resp.json()
    assert len(courses) == 1
    assert courses[0]["id"] == "python"
    assert courses[0]["chapter_count"] == 9
    assert courses[0]["total_pages"] > 0


@pytest.mark.asyncio
async def test_get_page_ok(client: AsyncClient):
    resp = await client.get("/api/courses/python/pages/lesson_python_1_1")
    assert resp.status_code == 200
    data = resp.json()
    assert data["id"] == "lesson_python_1_1"
    assert data["chapter_number"] == 1
    assert data["page_number"] == 1
    assert "variable" in data["narration_text"].lower() or "variable" in data["narration_text"]
    assert len(data["cues"]) > 0
    assert data["code_example"]["runnable"] is True


@pytest.mark.asyncio
async def test_get_page_not_found(client: AsyncClient):
    resp = await client.get("/api/courses/python/pages/nonexistent")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_get_page_unknown_course(client: AsyncClient):
    resp = await client.get("/api/courses/java/pages/lesson_python_1_1")
    assert resp.status_code == 404
