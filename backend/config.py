"""
Configuration module — reads env vars via pydantic-settings.

R12.5/R12.6: if any required var is missing or empty, validate_required() returns
the list of missing names.  The startup check in api/main.py calls this and exits 1.

Secrets are never logged.
"""
from __future__ import annotations

import logging
import os
import sys
from pathlib import Path
from typing import Optional

from pydantic_settings import BaseSettings, SettingsConfigDict

logger = logging.getLogger(__name__)

# Required env-var names (R12.1, R12.2, R12.3)
_REQUIRED_VARS: list[str] = [
    "PORTAL_USER",
    "PORTAL_PASSWORD",
    "GEMINI_API_KEY",
]

# Load from .env at project root (two levels up from this file: backend/config.py → altius/)
_ENV_FILE = Path(__file__).parent.parent / ".env"


class Settings(BaseSettings):
    """Application settings loaded from environment / .env file."""

    model_config = SettingsConfigDict(
        env_file=str(_ENV_FILE),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    PORTAL_USER: str = ""
    PORTAL_PASSWORD: str = ""
    GEMINI_API_KEY: str = ""
    DATABASE_URL: str = "sqlite:///./data/app.db"

    # --- Portal (optional overrides) ---
    PORTAL_BASE_URL: str = "https://fo1.altius.finance"
    PORTAL_API_BASE_URL: str = "https://fo1.api.altius.finance"
    PORTAL_LOGIN_PATH: str = "/login"
    PORTAL_MAX_LOGIN_RETRIES: int = 3
    PORTAL_HEADLESS: bool = True


def get_settings() -> Settings:
    """Return a Settings instance (reads .env + environment)."""
    return Settings()


def missing_required_vars(settings: Optional[Settings] = None) -> list[str]:
    """
    Return the list of required env var names that are absent or empty.

    This is the testable kernel of Property 14.  It does NOT call sys.exit —
    that responsibility belongs to the caller (lifespan startup).

    Args:
        settings: A Settings instance.  If None, one is created.

    Returns:
        Sorted list of missing variable names (empty list means all present).
    """
    if settings is None:
        settings = get_settings()

    missing: list[str] = []
    for var in _REQUIRED_VARS:
        value = getattr(settings, var, "")
        if not value or not value.strip():
            missing.append(var)
    return sorted(missing)


def validate_required(settings: Optional[Settings] = None) -> None:
    """
    Check required vars; if any are missing log ONE error naming ALL of them and exit(1).

    Called from the FastAPI lifespan — never at import time, so TestClient imports
    cleanly without side effects.
    """
    missing = missing_required_vars(settings)
    if missing:
        # Single error message naming every missing var (R12.5)
        logger.error(
            "Missing required environment variables: %s — set them in .env or the shell "
            "before starting the server.",
            ", ".join(missing),
        )
        sys.exit(1)
