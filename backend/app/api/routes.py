"""
app/api/routes.py — REST endpoints.

GET /health        — liveness probe
GET /api/courses   — list all seeded courses (for the frontend /courses page)
GET /api/courses/{course_id}/pages/{page_id} — single page payload
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.db.seed import PYTHON_COURSE, PYTHON_CHAPTERS, PYTHON_PAGES

router = APIRouter()


# ---------------------------------------------------------------------------
# Response schemas
# ---------------------------------------------------------------------------

class HealthResponse(BaseModel):
    status: str = "ok"
    version: str = "B0"


class CourseListItem(BaseModel):
    id: str
    title: str
    subtitle: str
    level: str
    category: str
    language: str
    available: bool
    chapter_count: int
    total_pages: int


class PageResponse(BaseModel):
    id: str
    course_id: str
    chapter_number: int
    page_number: int
    title: str
    narration_text: str
    paragraphs: list[str]
    key_terms: list[str]
    code_example: dict
    diagram_spec: dict
    cues: list[dict]
    practice_prompts: list[str]
    analogies: dict
    estimated_minutes: int


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    return HealthResponse()


@router.get("/api/courses", response_model=list[CourseListItem])
async def list_courses() -> list[CourseListItem]:
    total_pages = sum(ch["page_count"] for ch in PYTHON_CHAPTERS)
    return [
        CourseListItem(
            id=PYTHON_COURSE["id"],
            title=PYTHON_COURSE["title"],
            subtitle=PYTHON_COURSE["subtitle"],
            level=PYTHON_COURSE["level"],
            category=PYTHON_COURSE["category"],
            language=PYTHON_COURSE["language"],
            available=PYTHON_COURSE["available"],
            chapter_count=len(PYTHON_CHAPTERS),
            total_pages=total_pages,
        )
    ]


@router.get("/api/courses/{course_id}/pages/{page_id}", response_model=PageResponse)
async def get_page(course_id: str, page_id: str) -> PageResponse:
    if course_id != "python":
        raise HTTPException(status_code=404, detail=f"Course {course_id!r} not found.")

    for p in PYTHON_PAGES:
        if p["id"] == page_id:
            return PageResponse(
                id=p["id"],
                course_id="python",
                chapter_number=p["chapter_number"],
                page_number=p["page_number"],
                title=p["title"],
                narration_text=p["narration_text"],
                paragraphs=p["paragraphs"],
                key_terms=p["key_terms"],
                code_example=p["code_example"],
                diagram_spec=p["diagram_spec"],
                cues=p["cues"],
                practice_prompts=p["practice_prompts"],
                analogies=p["analogies"],
                estimated_minutes=p["estimated_minutes"],
            )

    raise HTTPException(status_code=404, detail=f"Page {page_id!r} not found in course {course_id!r}.")
