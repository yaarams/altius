"""
SQLAlchemy 2.x engine + session factory.

DATABASE_URL is read from settings (lazily — engine is created on first use).
For SQLite the data/ directory is created automatically so the app starts clean.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Generator

from sqlalchemy import create_engine, event
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Declarative base — shared by all model modules
# ---------------------------------------------------------------------------

class Base(DeclarativeBase):
    """Shared declarative base — imported by all model modules."""
    pass


# ---------------------------------------------------------------------------
# Lazy engine / session factory (created once on first call)
# ---------------------------------------------------------------------------

_engine = None
_SessionLocal = None


def _ensure_sqlite_dir(url: str) -> None:
    """Create the data directory for SQLite if the URL points to a file."""
    if not url.startswith("sqlite"):
        return
    path_part = url.split("///", 1)[-1]
    if path_part in ("", ":memory:"):
        return
    db_path = Path(path_part)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    logger.debug("SQLite data directory ensured: %s", db_path.parent)


def get_engine():
    """Return the (lazily-created) SQLAlchemy engine."""
    global _engine
    if _engine is None:
        from backend.config import get_settings
        database_url = get_settings().DATABASE_URL
        _ensure_sqlite_dir(database_url)

        connect_args: dict = {}
        if database_url.startswith("sqlite"):
            connect_args["check_same_thread"] = False

        _engine = create_engine(
            database_url,
            connect_args=connect_args,
            echo=False,
        )

        # Enable WAL mode + foreign keys for SQLite
        if database_url.startswith("sqlite"):
            @event.listens_for(_engine, "connect")
            def _set_sqlite_pragmas(dbapi_conn, _connection_record):
                dbapi_conn.execute("PRAGMA journal_mode=WAL")
                dbapi_conn.execute("PRAGMA foreign_keys=ON")

    return _engine


def get_session_factory():
    """Return the (lazily-created) session factory."""
    global _SessionLocal
    if _SessionLocal is None:
        _SessionLocal = sessionmaker(
            bind=get_engine(),
            autoflush=False,
            autocommit=False,
            expire_on_commit=False,
        )
    return _SessionLocal


def get_db() -> Generator[Session, None, None]:
    """FastAPI dependency: yield a DB session, close when done."""
    factory = get_session_factory()
    db = factory()
    try:
        yield db
    finally:
        db.close()
