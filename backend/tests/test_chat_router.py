"""
Tests for POST /api/chat citation id translation.

The RAG layer (backend/rag/chat.answer) emits citations keyed by the ChromaDB
chunk metadata ``external_file_id``. The frontend's citation links resolve
``File.id`` (GET /api/files/{id}/download, FileRecord.file_id = str(File.id)).
The chat router translates external_file_id → File.id so citation links don't
404. These tests pin that contract.

Isolated in-memory SQLite (StaticPool) — RAG/Gemini fully mocked, no network.
"""
from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend.api.routers.chat import router, _external_to_db_id_map
from backend.db.session import get_db


def _make_engine():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    with engine.connect() as conn:
        conn.execute(text("""
            CREATE TABLE files (
                id               INTEGER PRIMARY KEY AUTOINCREMENT,
                external_file_id INTEGER NOT NULL UNIQUE,
                deal_id          INTEGER,
                portal_doc_type  TEXT,
                file_name        TEXT NOT NULL DEFAULT 'test.pdf',
                file_url         TEXT,
                content_hash     TEXT,
                local_path       TEXT,
                download_ts      TEXT,
                status           TEXT NOT NULL DEFAULT 'extracted',
                classification   TEXT,
                confidence       REAL,
                low_confidence   INTEGER,
                extraction_error TEXT,
                indexed          INTEGER NOT NULL DEFAULT 0,
                created_at       TEXT NOT NULL DEFAULT (datetime('now'))
            )
        """))
        # external_file_id 22023 deliberately != its File.id (autoincrement → 1)
        conn.execute(text(
            "INSERT INTO files (external_file_id, file_name, classification) "
            "VALUES (22023, 'fund_alpha_Q1_2023.pdf', 'capital_account_statement')"
        ))
        conn.commit()
    return engine


@pytest.fixture
def db_session():
    engine = _make_engine()
    Session = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    db = Session()
    try:
        yield db
    finally:
        db.close()
        engine.dispose()


@pytest.fixture
def client(db_session):
    app = FastAPI()
    app.include_router(router, prefix="/api")
    app.dependency_overrides[get_db] = lambda: db_session
    return TestClient(app)


def _db_id_for(db, ext_id: int) -> int:
    return db.execute(
        text("SELECT id FROM files WHERE external_file_id = :e"), {"e": ext_id}
    ).scalar_one()


# ---------------------------------------------------------------------------
# Unit: the id-map helper
# ---------------------------------------------------------------------------

def test_map_translates_known_external_id(db_session):
    db_id = _db_id_for(db_session, 22023)
    mapping = _external_to_db_id_map(db_session, ["22023"])
    assert mapping == {"22023": str(db_id)}
    assert "22023" != str(db_id)  # guard: the ids really differ


def test_map_skips_unknown_and_non_integer(db_session):
    mapping = _external_to_db_id_map(db_session, ["99999", "not-a-number", ""])
    assert mapping == {}


# ---------------------------------------------------------------------------
# Integration: POST /api/chat
# ---------------------------------------------------------------------------

def test_chat_citation_file_id_is_db_id(client, db_session, monkeypatch):
    """A citation's external_file_id is rewritten to the matching File.id."""
    db_id = _db_id_for(db_session, 22023)

    def fake_answer(query, *args, **kwargs):
        return {
            "answer": "Ending capital balance was $4,945,000.00.",
            "citations": [
                {"file_id": "22023", "file_name": "fund_alpha_Q1_2023.pdf", "period": "2023-03-31"},
            ],
            "out_of_context": False,
        }

    monkeypatch.setattr("backend.rag.chat.answer", fake_answer)

    resp = client.post("/api/chat", json={"query": "What is the balance?"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["out_of_context"] is False
    assert len(body["citations"]) == 1
    cite = body["citations"][0]
    assert cite["file_id"] == str(db_id), "citation must carry File.id, not external_file_id"
    assert cite["file_id"] != "22023"
    assert cite["file_name"] == "fund_alpha_Q1_2023.pdf"
    assert cite["period"] == "2023-03-31"


def test_chat_citation_unknown_external_id_falls_back(client, monkeypatch):
    """An external id with no File row is left unchanged (no crash, no drop)."""
    def fake_answer(query, *args, **kwargs):
        return {
            "answer": "See the report.",
            "citations": [
                {"file_id": "88888", "file_name": "ghost.pdf", "period": None},
            ],
            "out_of_context": False,
        }

    monkeypatch.setattr("backend.rag.chat.answer", fake_answer)

    resp = client.post("/api/chat", json={"query": "anything"})
    assert resp.status_code == 200
    assert resp.json()["citations"][0]["file_id"] == "88888"


def test_chat_ooc_has_no_citations(client, monkeypatch):
    def fake_answer(query, *args, **kwargs):
        return {
            "answer": "I could not find this information in the indexed documents.",
            "citations": [],
            "out_of_context": True,
        }

    monkeypatch.setattr("backend.rag.chat.answer", fake_answer)

    resp = client.post("/api/chat", json={"query": "unrelated"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["out_of_context"] is True
    assert body["citations"] == []
