"""
app/main.py — FastAPI application entry point.
"""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, WebSocket
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings
from app.db.database import engine
from app.db.models import Base
from app.db.seed import seed_database
from app.db.database import AsyncSessionLocal
from app.api.routes import router
from app.ws.gateway import book_ws_handler

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
log = logging.getLogger(__name__)
settings = get_settings()


# ---------------------------------------------------------------------------
# Lifespan: create tables + seed on startup
# ---------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI):
    log.info("Starting Bookey backend B0 (%s)", settings.app_env)

    # Create all tables (no-op if they exist)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    # Seed the database with Python course data
    async with AsyncSessionLocal() as session:
        await seed_database(session)

    log.info("Database ready")
    yield
    log.info("Shutting down")
    await engine.dispose()


# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------

app = FastAPI(
    title="Bookey Backend B0",
    description="Mock realtime backend for the Bookey interactive book reader.",
    version="0.1.0-B0",
    lifespan=lifespan,
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# REST routes
app.include_router(router)


# ---------------------------------------------------------------------------
# WebSocket
# ---------------------------------------------------------------------------

@app.websocket("/ws/book")
async def ws_book(websocket: WebSocket) -> None:
    await book_ws_handler(websocket)
