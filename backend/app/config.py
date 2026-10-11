"""
app/config.py — pydantic-settings configuration.
All values have safe defaults so the server starts with no .env file (dev/test).
"""
from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # --- App ---
    app_env: Literal["development", "testing", "production"] = "development"
    debug: bool = True

    # --- Server ---
    host: str = "0.0.0.0"
    port: int = 8000

    # --- Database ---
    # SQLite for dev/tests; PostgreSQL for production (same SQLAlchemy models, no changes needed).
    database_url: str = Field(
        default="sqlite+aiosqlite:///./bookey_dev.db",
        description="Async SQLAlchemy URL. Use postgresql+asyncpg://... for production.",
    )
    db_echo: bool = False

    # --- CORS ---
    cors_origins: list[str] = [
        "http://localhost:3000",
        "http://localhost:4100",
        "http://127.0.0.1:3000",
    ]

    # --- WebSocket ---
    ws_heartbeat_interval: int = 30  # seconds
    ws_heartbeat_timeout: int = 10   # seconds after ping with no pong
    ws_max_message_size: int = 1024 * 512  # 512 KB

    # --- Protocol ---
    book_protocol_version: int = 1

    # --- MockBookService timing (ms) ---
    mock_token_ms: int = 85          # delay between word tokens
    mock_thinking_ms: int = 600      # tutor "thinking" pause
    mock_answer_token_ms: int = 45   # delay between answer tokens
    mock_code_stream_ms: int = 30    # delay between code stream chunks


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
