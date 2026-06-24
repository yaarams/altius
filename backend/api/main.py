"""
FastAPI application factory.

Lifespan startup order (R11.5, R12.5, R12.6, ADR-009):
  1. Validate required environment variables → log all missing + exit 1 if any absent.
  2. Apply Alembic migrations → exit 1 on failure.
  3. Start serving.

Only GET /health is mounted here.  All other routers (sync, holdings, chat, files)
are added in later tasks.
"""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup guards run before the server accepts any request."""
    # Step 1: fail-fast on missing env vars (R12.5, R12.6, Property 14)
    # Import here (not at module level) so that TestClient import does NOT trigger exit.
    from backend.config import get_settings, validate_required

    settings = get_settings()
    validate_required(settings)  # exits 1 if any var is missing/empty

    # Step 2: auto-migrate (R11.5, R11.6)
    from backend.db.migrations import run_migrations

    run_migrations()  # exits 1 on failure

    logger.info("Startup complete — server is ready.")
    yield
    # Shutdown (no cleanup needed for sqlite / in-process chromadb yet)
    logger.info("Server shutting down.")


def create_app() -> FastAPI:
    """Construct and configure the FastAPI application."""
    app = FastAPI(
        title="Investor Document Platform",
        version="0.1.0",
        lifespan=lifespan,
    )

    # Permissive CORS for local development
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # -----------------------------------------------------------------------
    # Health check — no auth, no DB required
    # -----------------------------------------------------------------------
    @app.get("/health", tags=["infra"])
    async def health():
        return {"status": "ok"}

    # -----------------------------------------------------------------------
    # Routers
    # -----------------------------------------------------------------------
    from backend.api.routers import holdings as holdings_router
    app.include_router(holdings_router.router, prefix="/api")

    from backend.api.routers import sync as sync_router
    app.include_router(sync_router.router, prefix="/api")

    from backend.api.routers import chat as chat_router
    app.include_router(chat_router.router, prefix="/api")

    from backend.api.routers import files as files_router
    app.include_router(files_router.router, prefix="/api")

    return app


# Module-level app instance for uvicorn / TestClient
app = create_app()
