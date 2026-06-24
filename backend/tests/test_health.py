"""
/health endpoint smoke test.

Uses FastAPI TestClient.  The lifespan runs env validation and migrations;
the .env file at project root must have all 4 vars set (it does in dev).
For test isolation we monkeypatch the lifespan startup functions so the test
doesn't depend on the DB or real credentials being valid.
"""
from __future__ import annotations

import pytest
from unittest.mock import patch
from fastapi.testclient import TestClient


def test_health_returns_200():
    """GET /health must return 200 with body {"status": "ok"}."""
    # Patch startup side effects so TestClient doesn't call sys.exit or run migrations
    with (
        patch("backend.config.validate_required", return_value=None),
        patch("backend.db.migrations.run_migrations", return_value=None),
    ):
        from backend.api.main import app
        client = TestClient(app)
        resp = client.get("/health")
        assert resp.status_code == 200
        assert resp.json() == {"status": "ok"}
