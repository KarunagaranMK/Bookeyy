"""
app/db/models.py — SQLAlchemy 2 async ORM models.

Design goals:
- Written for PostgreSQL; SQLite works unchanged for dev/tests (via aiosqlite).
- No PostgreSQL-specific types in column definitions (uses Text, Integer, JSON
  instead of ARRAY or JSONB) so SQLite never fails.
- Every table uses a UUID primary key stored as a VARCHAR(36) for portability.
"""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    JSON,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def _uuid() -> str:
    return str(uuid.uuid4())


class Base(DeclarativeBase):
    pass


# ---------------------------------------------------------------------------
# Users & Seats
# ---------------------------------------------------------------------------

class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    email: Mapped[str] = mapped_column(String(320), unique=True, nullable=False)
    display_name: Mapped[str] = mapped_column(String(120), nullable=False, default="")
    avatar_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    role: Mapped[str] = mapped_column(String(20), nullable=False, default="learner")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    seats: Mapped[list[Seat]] = relationship("Seat", back_populates="user")
    progress: Mapped[list[Progress]] = relationship("Progress", back_populates="user")
    bookmarks: Mapped[list[Bookmark]] = relationship("Bookmark", back_populates="user")
    notes: Mapped[list[Note]] = relationship("Note", back_populates="user")
    sessions: Mapped[list[Session]] = relationship("Session", back_populates="user")


class Seat(Base):
    """Which courses a user has access to."""
    __tablename__ = "seats"
    __table_args__ = (UniqueConstraint("user_id", "course_id"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    course_id: Mapped[str] = mapped_column(ForeignKey("courses.id", ondelete="CASCADE"), nullable=False)
    granted_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    user: Mapped[User] = relationship("User", back_populates="seats")
    course: Mapped[Course] = relationship("Course", back_populates="seats")


# ---------------------------------------------------------------------------
# Courses, Chapters, Pages
# ---------------------------------------------------------------------------

class Course(Base):
    __tablename__ = "courses"

    id: Mapped[str] = mapped_column(String(80), primary_key=True)  # e.g. "python"
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    subtitle: Mapped[str] = mapped_column(String(400), nullable=False, default="")
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    level: Mapped[str] = mapped_column(String(20), nullable=False, default="Beginner")
    category: Mapped[str] = mapped_column(String(80), nullable=False, default="Programming")
    language: Mapped[str] = mapped_column(String(40), nullable=False, default="Python")
    available: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    author: Mapped[str] = mapped_column(String(120), nullable=False, default="Bookey")
    cover: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    outcomes: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    topics: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    tutor_style: Mapped[str] = mapped_column(Text, nullable=False, default="")
    minutes_per_page: Mapped[int] = mapped_column(Integer, nullable=False, default=4)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    chapters: Mapped[list[Chapter]] = relationship("Chapter", back_populates="course", order_by="Chapter.number")
    seats: Mapped[list[Seat]] = relationship("Seat", back_populates="course")
    progress: Mapped[list[Progress]] = relationship("Progress", back_populates="course")
    sessions: Mapped[list[Session]] = relationship("Session", back_populates="course")


class Chapter(Base):
    __tablename__ = "chapters"
    __table_args__ = (UniqueConstraint("course_id", "number"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    course_id: Mapped[str] = mapped_column(ForeignKey("courses.id", ondelete="CASCADE"), nullable=False)
    number: Mapped[int] = mapped_column(Integer, nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    summary: Mapped[str] = mapped_column(Text, nullable=False, default="")
    page_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    locked: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    course: Mapped[Course] = relationship("Course", back_populates="chapters")
    pages: Mapped[list[Page]] = relationship("Page", back_populates="chapter", order_by="Page.page_number")


class Page(Base):
    __tablename__ = "pages"
    __table_args__ = (UniqueConstraint("chapter_id", "page_number"),)

    id: Mapped[str] = mapped_column(String(80), primary_key=True)  # e.g. "lesson_python_1_1"
    course_id: Mapped[str] = mapped_column(ForeignKey("courses.id", ondelete="CASCADE"), nullable=False)
    chapter_id: Mapped[str] = mapped_column(ForeignKey("chapters.id", ondelete="CASCADE"), nullable=False)
    page_number: Mapped[int] = mapped_column(Integer, nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    narration_text: Mapped[str] = mapped_column(Text, nullable=False, default="")
    paragraphs: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    key_terms: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    code_example: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    diagram_spec: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    cues: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    practice_prompts: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    analogies: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    estimated_minutes: Mapped[int] = mapped_column(Integer, nullable=False, default=4)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    chapter: Mapped[Chapter] = relationship("Chapter", back_populates="pages")
    progress: Mapped[list[Progress]] = relationship("Progress", back_populates="page")


# ---------------------------------------------------------------------------
# Progress, Bookmarks, Notes
# ---------------------------------------------------------------------------

class Progress(Base):
    __tablename__ = "progress"
    __table_args__ = (UniqueConstraint("user_id", "page_id"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    course_id: Mapped[str] = mapped_column(ForeignKey("courses.id", ondelete="CASCADE"), nullable=False)
    page_id: Mapped[str] = mapped_column(ForeignKey("pages.id", ondelete="CASCADE"), nullable=False)
    completed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    last_word_index: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_segment_id: Mapped[str | None] = mapped_column(String(120), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    user: Mapped[User] = relationship("User", back_populates="progress")
    course: Mapped[Course] = relationship("Course", back_populates="progress")
    page: Mapped[Page] = relationship("Page", back_populates="progress")


class Bookmark(Base):
    __tablename__ = "bookmarks"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    course_id: Mapped[str] = mapped_column(String(80), nullable=False)
    chapter_number: Mapped[int] = mapped_column(Integer, nullable=False)
    page_id: Mapped[str] = mapped_column(String(80), nullable=False)
    excerpt: Mapped[str] = mapped_column(Text, nullable=False, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    user: Mapped[User] = relationship("User", back_populates="bookmarks")


class Note(Base):
    __tablename__ = "notes"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    course_id: Mapped[str] = mapped_column(String(80), nullable=False)
    chapter_number: Mapped[int] = mapped_column(Integer, nullable=False)
    page_id: Mapped[str] = mapped_column(String(80), nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    user: Mapped[User] = relationship("User", back_populates="notes")


# ---------------------------------------------------------------------------
# Sessions (narration sessions)
# ---------------------------------------------------------------------------

class Session(Base):
    __tablename__ = "sessions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    user_id: Mapped[str | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    course_id: Mapped[str] = mapped_column(ForeignKey("courses.id", ondelete="CASCADE"), nullable=False)
    page_id: Mapped[str] = mapped_column(String(80), nullable=False)
    last_seq: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_word_index: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_segment_id: Mapped[str | None] = mapped_column(String(120), nullable=True)
    started_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    user: Mapped[User | None] = relationship("User", back_populates="sessions")
    course: Mapped[Course] = relationship("Course", back_populates="sessions")


# ---------------------------------------------------------------------------
# Admin: Documents, Generated Pages, Media Assets, Jobs
# ---------------------------------------------------------------------------

class Document(Base):
    """Source documents uploaded by admins (future knowledge base)."""
    __tablename__ = "documents"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    course_id: Mapped[str | None] = mapped_column(ForeignKey("courses.id", ondelete="SET NULL"), nullable=True)
    filename: Mapped[str] = mapped_column(String(400), nullable=False)
    mime_type: Mapped[str] = mapped_column(String(120), nullable=False, default="application/octet-stream")
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending")
    uploaded_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    chunk_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)


class ChunkMetadata(Base):
    """Vector chunk metadata for RAG retrieval."""
    __tablename__ = "chunk_metadata"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    document_id: Mapped[str] = mapped_column(ForeignKey("documents.id", ondelete="CASCADE"), nullable=False)
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    token_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    page_ref: Mapped[str | None] = mapped_column(String(80), nullable=True)
    text_preview: Mapped[str] = mapped_column(Text, nullable=False, default="")


class GeneratedPage(Base):
    """AI-generated book pages (B1+)."""
    __tablename__ = "generated_pages"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    course_id: Mapped[str] = mapped_column(String(80), nullable=False)
    chapter_number: Mapped[int] = mapped_column(Integer, nullable=False)
    page_number: Mapped[int] = mapped_column(Integer, nullable=False)
    job_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending")
    content: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class MediaAsset(Base):
    """TTS audio and diagram images (B1+)."""
    __tablename__ = "media_assets"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    page_id: Mapped[str | None] = mapped_column(String(80), nullable=True)
    kind: Mapped[str] = mapped_column(String(20), nullable=False)  # "audio" | "image"
    mime_type: Mapped[str] = mapped_column(String(120), nullable=False)
    url: Mapped[str] = mapped_column(Text, nullable=False)
    duration_ms: Mapped[float | None] = mapped_column(Float, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class Job(Base):
    """Background generation / processing jobs."""
    __tablename__ = "jobs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    kind: Mapped[str] = mapped_column(String(40), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="queued")
    course_id: Mapped[str | None] = mapped_column(String(80), nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    metadata: Mapped[dict] = mapped_column("job_meta", JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
