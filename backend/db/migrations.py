"""
Programmatic Alembic migration runner.

run_migrations() is called from the FastAPI lifespan (R11.5):
  - applies all pending migrations (alembic upgrade head)
  - on failure: logs a clear error and exits with code 1 BEFORE the server binds
"""
from __future__ import annotations

import logging
import sys
from pathlib import Path

logger = logging.getLogger(__name__)

# migrations.py is at backend/db/migrations.py → parents[2] = project root (altius/)
_ALEMBIC_INI = str(Path(__file__).resolve().parents[2] / "alembic.ini")
# Script location = backend/alembic/
_SCRIPT_LOCATION = str(Path(__file__).resolve().parents[1] / "alembic")


def run_migrations() -> None:
    """
    Apply all pending Alembic migrations (upgrade head).

    On failure: logs the error and calls sys.exit(1) — server must not bind (R11.5, R11.6).
    """
    try:
        from alembic.config import Config
        from alembic import command

        alembic_cfg = Config(_ALEMBIC_INI)
        # Override script_location to the resolved path so it works regardless of cwd
        alembic_cfg.set_main_option("script_location", _SCRIPT_LOCATION)

        logger.info("Applying Alembic migrations (upgrade head)…")
        command.upgrade(alembic_cfg, "head")
        logger.info("Migrations applied successfully.")
    except Exception as exc:
        logger.error(
            "Database migration failed — cannot start server. Error: %s",
            exc,
            exc_info=True,
        )
        sys.exit(1)
