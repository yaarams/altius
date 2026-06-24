"""
Tests for the sync orchestrator — T1.6.

Covers:
  - Property 10 / ADR-009: single-flight / 409 when already running
  - SSE shape: 5 stages + terminal complete event
  - Error path: crawler raises → terminal error event, lock released
  - Indexer non-fatal: indexer raises → run still emits complete

All external I/O is mocked — no live portal, no Gemini, no network.
"""
from __future__ import annotations

import asyncio
import json
import sys
import threading
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

# ---------------------------------------------------------------------------
# Helpers: SSE frame parser
# ---------------------------------------------------------------------------

def parse_sse_frames(raw: str) -> list[dict]:
    """
    Parse a raw SSE response body into a list of dicts.

    Each SSE frame looks like:
        event: <type>\ndata: <json>\n\n
    """
    frames = []
    current_event: dict = {}

    for line in raw.splitlines():
        line = line.strip()
        if line.startswith("event:"):
            current_event["event"] = line[len("event:"):].strip()
        elif line.startswith("data:"):
            current_event["data"] = json.loads(line[len("data:"):].strip())
        elif line == "" and current_event:
            frames.append(current_event)
            current_event = {}

    if current_event:
        frames.append(current_event)

    return frames


# ---------------------------------------------------------------------------
# Fake pipeline objects
# ---------------------------------------------------------------------------

FAKE_CRAWL_RESULT_CLASS = None  # set per-test via monkeypatch


def _make_fake_crawl_result(enumerated: int = 3, downloaded: int = 2):
    """Create a fake CrawlResult-like object."""
    r = MagicMock()
    r.enumerated = enumerated
    r.downloaded = downloaded
    r.deals = [1, 2]
    r.skipped = 1
    r.failed = 0
    return r


def _make_fake_pipeline_result(classified: int = 3, extracted: int = 2):
    return {
        "total_files": classified,
        "classified": classified,
        "extracted": extracted,
        "failed_extraction": 0,
        "skipped": 0,
    }


# ---------------------------------------------------------------------------
# App factory for tests (no lifespan guards, no real DB dependency)
# ---------------------------------------------------------------------------

def _make_test_app() -> FastAPI:
    """Build a minimal FastAPI app that only includes the sync router."""
    app = FastAPI()
    # Import fresh to avoid polluting module-level state from prior tests.
    # We use the actual module but reset its state before each test via fixture.
    from backend.api.routers import sync as sync_router
    app.include_router(sync_router.router, prefix="/api")
    return app


# ---------------------------------------------------------------------------
# Fixture: reset sync module state + provide a test client
# ---------------------------------------------------------------------------

@pytest.fixture()
def sync_client():
    """
    Yield a TestClient for the sync router, with module-level state reset.
    """
    import backend.api.routers.sync as sync_mod

    # Reset all module-level state before each test
    sync_mod._running = False
    sync_mod._sync_id = None
    sync_mod._event_log = []
    sync_mod._subscribers = set()
    # Replace lock with a fresh one so tests don't inherit a held lock
    sync_mod._lock = asyncio.Lock()

    app = _make_test_app()
    with TestClient(app, raise_server_exceptions=True) as client:
        yield client

    # Also reset after
    sync_mod._running = False
    sync_mod._sync_id = None
    sync_mod._event_log = []
    sync_mod._subscribers = set()


# ---------------------------------------------------------------------------
# Helper: run background tasks in TestClient context
# ---------------------------------------------------------------------------

def _drain_tasks(client: TestClient) -> None:
    """
    Give the background pipeline task a chance to complete.

    TestClient uses an event loop; we poll until _running is False.
    """
    import backend.api.routers.sync as sync_mod

    for _ in range(200):  # max 2 s total at 10 ms each
        if not sync_mod._running:
            break
        # Yield to the event loop by doing a tiny blocking call
        import time
        time.sleep(0.01)


# ---------------------------------------------------------------------------
# Fixtures: fast fake crawler and pipeline
# ---------------------------------------------------------------------------

@pytest.fixture()
def mock_crawler_ok():
    """Patch PortalCrawler to return a successful CrawlResult immediately."""
    fake_result = _make_fake_crawl_result(enumerated=5, downloaded=3)

    async def fake_run(self, progress_callback=None):
        # Emit a couple of download events so we confirm callbacks work
        if progress_callback:
            progress_callback({"stage": "Crawling", "event": "file_downloaded",
                                "file_name": "fund_report.pdf"})
            progress_callback({"stage": "Crawling", "event": "file_downloaded",
                                "file_name": "fund_report2.pdf"})
        return fake_result

    with patch("backend.api.routers.sync.PortalCrawler") as MockClass:
        instance = MockClass.return_value
        instance.run = lambda progress_callback=None: fake_run(instance, progress_callback)
        yield MockClass


@pytest.fixture()
def mock_pipeline_ok():
    """Patch process_all_pending to return a success dict."""
    result = _make_fake_pipeline_result(classified=5, extracted=3)
    with patch("backend.api.routers.sync.process_all_pending", return_value=result):
        yield result


@pytest.fixture()
def mock_no_indexer():
    """Ensure backend.indexer import raises ImportError (indexer not built)."""
    with patch.dict(sys.modules, {"backend.indexer": None}):
        yield


# ---------------------------------------------------------------------------
# Test: POST /api/sync happy path
# ---------------------------------------------------------------------------

class TestPostSync:
    def test_start_sync_returns_started(self, sync_client, mock_crawler_ok,
                                         mock_pipeline_ok, mock_no_indexer):
        resp = sync_client.post("/api/sync")
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "started"
        assert isinstance(body["sync_id"], str)
        assert len(body["sync_id"]) == 32  # uuid4().hex

    def test_trigger_alias_returns_started(self, sync_client, mock_crawler_ok,
                                            mock_pipeline_ok, mock_no_indexer):
        resp = sync_client.post("/api/sync/trigger")
        assert resp.status_code == 200
        assert resp.json()["status"] == "started"


# ---------------------------------------------------------------------------
# Property 10 / ADR-009: single-flight / 409
# ---------------------------------------------------------------------------

class TestSingleFlight:
    def test_409_while_running(self, sync_client, mock_pipeline_ok, mock_no_indexer):
        """
        Property 10: while a sync is running, a second POST /api/sync
        must return HTTP 409.
        """
        import backend.api.routers.sync as sync_mod

        # Use a slow fake crawler: blocks until an event is set
        stop_event = threading.Event()
        completed_event = threading.Event()

        async def slow_crawler_run(progress_callback=None):
            # Signal that we've started, then wait
            completed_event.set()
            # Simulate a long-running crawl
            await asyncio.sleep(5)  # will be cancelled when test ends
            return _make_fake_crawl_result()

        with patch("backend.api.routers.sync.PortalCrawler") as MockClass:
            instance = MockClass.return_value
            instance.run = slow_crawler_run

            # First POST — starts a run
            resp1 = sync_client.post("/api/sync")
            assert resp1.status_code == 200

            # Give the background task a moment to acquire the running flag
            import time
            for _ in range(50):
                if sync_mod._running:
                    break
                time.sleep(0.01)

            assert sync_mod._running, "Expected _running to be True after first POST"

            # Second POST — must be 409
            resp2 = sync_client.post("/api/sync")
            assert resp2.status_code == 409
            body2 = resp2.json()
            # FastAPI wraps HTTPException detail in {"detail": ...}
            assert "detail" in body2 or "message" in body2

    def test_lock_released_after_completion(self, sync_client, mock_crawler_ok,
                                              mock_pipeline_ok, mock_no_indexer):
        """
        After a completed run, a new POST /api/sync must succeed (lock released).
        """
        import backend.api.routers.sync as sync_mod

        # First run
        resp1 = sync_client.post("/api/sync")
        assert resp1.status_code == 200
        id1 = resp1.json()["sync_id"]

        # Wait for pipeline to finish
        _drain_tasks(sync_client)
        assert not sync_mod._running

        # Second run should succeed
        resp2 = sync_client.post("/api/sync")
        assert resp2.status_code == 200
        id2 = resp2.json()["sync_id"]

        # sync_ids must be different
        assert id1 != id2


# ---------------------------------------------------------------------------
# SSE shape: 5 stages + complete
# ---------------------------------------------------------------------------

class TestSSEShape:
    def test_stream_has_all_5_stages_and_complete(self, sync_client, mock_crawler_ok,
                                                    mock_pipeline_ok, mock_no_indexer):
        """
        Drive one full run and assert:
        - Stage events for all 5 stages (discover/download/classify/extract/index)
        - A terminal complete event with 5 entries in stages[]
        - files_discovered / files_downloaded / files_classified / files_extracted present
        """
        # Trigger the sync
        start_resp = sync_client.post("/api/sync")
        assert start_resp.status_code == 200

        # Wait for pipeline to finish
        _drain_tasks(sync_client)

        # Stream — at this point the event log should contain all events
        stream_resp = sync_client.get("/api/sync/stream")
        assert stream_resp.status_code == 200

        frames = parse_sse_frames(stream_resp.text)
        assert len(frames) > 0, "Expected SSE frames, got none"

        # Collect stage names and events
        stage_events: dict[str, list[dict]] = {}
        complete_event = None

        for frame in frames:
            ev_type = frame.get("event")
            data = frame.get("data", {})

            if ev_type == "stage":
                stage_name = data.get("stage")
                stage_events.setdefault(stage_name, []).append(data)
                assert data.get("type") == "stage", f"Expected type='stage', got {data.get('type')}"
            elif ev_type == "complete":
                complete_event = data
                assert data.get("type") == "complete"

        # All 5 stage names must appear
        expected_stages = {"discover", "download", "classify", "extract", "index"}
        assert expected_stages.issubset(set(stage_events.keys())), (
            f"Missing stages: {expected_stages - set(stage_events.keys())}"
        )

        # Terminal complete must be present
        assert complete_event is not None, "No complete event in SSE stream"
        assert len(complete_event["stages"]) == 5, (
            f"Expected 5 entries in complete.stages, got {len(complete_event['stages'])}"
        )

        # Count fields must be present in done events
        done_events = {
            s: next((e for e in evts if e.get("status") == "done"), None)
            for s, evts in stage_events.items()
        }
        assert done_events["discover"] is not None
        assert "files_discovered" in done_events["discover"]

        assert done_events["download"] is not None
        assert "files_downloaded" in done_events["download"]

        assert done_events["classify"] is not None
        assert "files_classified" in done_events["classify"]

        assert done_events["extract"] is not None
        assert "files_extracted" in done_events["extract"]

    def test_stream_count_values_correct(self, sync_client, mock_crawler_ok,
                                          mock_pipeline_ok, mock_no_indexer):
        """
        Verify specific count values from the fake crawler/pipeline flow through
        to the SSE done events.
        mock_crawler_ok: enumerated=5, downloaded=3
        mock_pipeline_ok: classified=5, extracted=3
        """
        sync_client.post("/api/sync")
        _drain_tasks(sync_client)

        stream_resp = sync_client.get("/api/sync/stream")
        frames = parse_sse_frames(stream_resp.text)

        done_discover = next(
            (f["data"] for f in frames
             if f.get("event") == "stage"
             and f["data"].get("stage") == "discover"
             and f["data"].get("status") == "done"),
            None,
        )
        assert done_discover is not None
        assert done_discover["files_discovered"] == 5

        done_download = next(
            (f["data"] for f in frames
             if f.get("event") == "stage"
             and f["data"].get("stage") == "download"
             and f["data"].get("status") == "done"),
            None,
        )
        assert done_download is not None
        assert done_download["files_downloaded"] == 3

        done_classify = next(
            (f["data"] for f in frames
             if f.get("event") == "stage"
             and f["data"].get("stage") == "classify"
             and f["data"].get("status") == "done"),
            None,
        )
        assert done_classify is not None
        assert done_classify["files_classified"] == 5

        done_extract = next(
            (f["data"] for f in frames
             if f.get("event") == "stage"
             and f["data"].get("stage") == "extract"
             and f["data"].get("status") == "done"),
            None,
        )
        assert done_extract is not None
        assert done_extract["files_extracted"] == 3

    def test_complete_stages_array_has_5_entries(self, sync_client, mock_crawler_ok,
                                                   mock_pipeline_ok, mock_no_indexer):
        """complete.stages must have exactly 5 entries (one per stage)."""
        sync_client.post("/api/sync")
        _drain_tasks(sync_client)

        stream_resp = sync_client.get("/api/sync/stream")
        frames = parse_sse_frames(stream_resp.text)

        complete_frame = next(
            (f for f in frames if f.get("event") == "complete"), None
        )
        assert complete_frame is not None
        stages = complete_frame["data"]["stages"]
        assert len(stages) == 5
        stage_names = {s["stage"] for s in stages}
        assert stage_names == {"discover", "download", "classify", "extract", "index"}

    def test_stream_no_run_returns_idle_complete(self, sync_client):
        """GET /sync/stream with no run ever started → idle complete with empty stages."""
        resp = sync_client.get("/api/sync/stream")
        assert resp.status_code == 200

        frames = parse_sse_frames(resp.text)
        complete_frames = [f for f in frames if f.get("event") == "complete"]
        assert len(complete_frames) >= 1
        assert complete_frames[0]["data"]["type"] == "complete"


# ---------------------------------------------------------------------------
# Error path: crawler raises LoginError
# ---------------------------------------------------------------------------

class TestErrorPath:
    def test_login_error_emits_terminal_error_event(self, sync_client,
                                                      mock_pipeline_ok,
                                                      mock_no_indexer):
        """
        When the crawler raises LoginError, the stream must contain a
        terminal error event with a non-empty message field.
        """
        from backend.crawler.portal_crawler import LoginError

        async def failing_run(progress_callback=None):
            raise LoginError("Login failed: still at '/login'.")

        with patch("backend.api.routers.sync.PortalCrawler") as MockClass:
            instance = MockClass.return_value
            instance.run = failing_run

            resp = sync_client.post("/api/sync")
            assert resp.status_code == 200

            _drain_tasks(sync_client)

            stream_resp = sync_client.get("/api/sync/stream")
            frames = parse_sse_frames(stream_resp.text)

        error_frames = [f for f in frames if f.get("event") == "error"]
        assert len(error_frames) >= 1, "Expected an error SSE event"
        err_data = error_frames[0]["data"]
        assert err_data.get("type") == "error"
        assert isinstance(err_data.get("message"), str)
        assert len(err_data["message"]) > 0

    def test_login_error_does_not_leak_credentials(self, sync_client,
                                                     mock_pipeline_ok,
                                                     mock_no_indexer):
        """
        The error message must not contain credential-looking content.
        (Simple check: message is short / doesn't contain real user data.)
        """
        from backend.crawler.portal_crawler import LoginError

        # Simulate a LoginError that might have credentials in it
        async def failing_run(progress_callback=None):
            raise LoginError("Login failed: bad password superSecretPass123!")

        with patch("backend.api.routers.sync.PortalCrawler") as MockClass:
            instance = MockClass.return_value
            instance.run = failing_run

            sync_client.post("/api/sync")
            _drain_tasks(sync_client)

            stream_resp = sync_client.get("/api/sync/stream")
            frames = parse_sse_frames(stream_resp.text)

        error_frames = [f for f in frames if f.get("event") == "error"]
        assert error_frames
        msg = error_frames[0]["data"]["message"]
        # Our handler uses a fixed message, never the raw exc message
        assert "superSecretPass123" not in msg
        assert "portal credentials" in msg.lower() or "login" in msg.lower()

    def test_lock_released_after_error(self, sync_client, mock_pipeline_ok,
                                        mock_no_indexer):
        """
        After an error, a new POST /api/sync must return 200 (lock released).
        """
        import backend.api.routers.sync as sync_mod
        from backend.crawler.portal_crawler import LoginError

        async def failing_run(progress_callback=None):
            raise LoginError("bad creds")

        with patch("backend.api.routers.sync.PortalCrawler") as MockClass:
            instance = MockClass.return_value
            instance.run = failing_run

            sync_client.post("/api/sync")
            _drain_tasks(sync_client)

        assert not sync_mod._running, "_running should be False after error"

        # After error a new POST should succeed
        with patch("backend.api.routers.sync.PortalCrawler") as MockClass2:
            async def ok_run(progress_callback=None):
                return _make_fake_crawl_result()

            instance2 = MockClass2.return_value
            instance2.run = ok_run

            resp = sync_client.post("/api/sync")
            assert resp.status_code == 200


# ---------------------------------------------------------------------------
# Indexer non-fatal (ADR-008)
# ---------------------------------------------------------------------------

class TestIndexerNonFatal:
    def test_indexer_raises_still_emits_complete(self, sync_client,
                                                   mock_crawler_ok,
                                                   mock_pipeline_ok):
        """
        When the indexer raises, the run must still emit a complete event.
        The index stage may be 'error' but the overall event is 'complete'.
        """
        # Make backend.indexer importable but index_documents raises
        fake_indexer_module = MagicMock()
        fake_indexer_module.index_documents.side_effect = RuntimeError("ChromaDB unavailable")

        with patch.dict(sys.modules, {"backend.indexer": fake_indexer_module}):
            resp = sync_client.post("/api/sync")
            assert resp.status_code == 200

            _drain_tasks(sync_client)

            stream_resp = sync_client.get("/api/sync/stream")
            frames = parse_sse_frames(stream_resp.text)

        # Must have a complete event (not just error)
        complete_frames = [f for f in frames if f.get("event") == "complete"]
        assert len(complete_frames) >= 1, (
            "Expected complete event even when indexer fails"
        )
        complete_data = complete_frames[0]["data"]
        assert complete_data["type"] == "complete"
        assert len(complete_data["stages"]) == 5

        # Index stage should be marked error
        index_stage = next(
            (s for s in complete_data["stages"] if s["stage"] == "index"), None
        )
        assert index_stage is not None
        assert index_stage["status"] == "error"

    def test_indexer_missing_still_emits_complete(self, sync_client,
                                                    mock_crawler_ok,
                                                    mock_pipeline_ok):
        """
        When backend.indexer does not exist (ImportError), the run still
        emits a complete event with index stage 'done'.
        """
        with patch.dict(sys.modules, {"backend.indexer": None}):
            resp = sync_client.post("/api/sync")
            assert resp.status_code == 200

            _drain_tasks(sync_client)

            stream_resp = sync_client.get("/api/sync/stream")
            frames = parse_sse_frames(stream_resp.text)

        complete_frames = [f for f in frames if f.get("event") == "complete"]
        assert len(complete_frames) >= 1

        complete_data = complete_frames[0]["data"]
        assert complete_data["type"] == "complete"

        # When indexer is missing, index stage should be 'done' (not error)
        index_stage = next(
            (s for s in complete_data["stages"] if s["stage"] == "index"), None
        )
        assert index_stage is not None
        assert index_stage["status"] == "done"


# ---------------------------------------------------------------------------
# T-DIFF: "2nd sync run does ZERO new work" guard tests
#
# These tests exercise the REAL pipeline functions (process_all_pending,
# index_documents) against an in-memory SQLite DB.  All network I/O is mocked:
#   - parse_pdf  → fake ParsedPdf (no disk file needed)
#   - generate_json  → deterministic JSON response (no Gemini)
#   - embed_text     → deterministic hash vector  (no Gemini)
#
# Corpus: 2 files
#   file_id=1001  →  capital_account_statement  ("cas_statement.pdf")
#   file_id=1002  →  report                     ("fund_report.pdf")
#
# Run 1: both files in status='downloaded', no classification.
#   Expected: classified=2 (1 CAS + 1 report), extracted=1 (CAS only),
#             indexed=2.
#
# Run 2: CAS → status='extracted' (filtered out of query), report → status still
#   'downloaded' but classification is already set (P5 prevents Gemini call).
#   Expected: classified=0, extracted=0, indexed=0 (all skipped at indexer).
#   NOTE: Gemini generate_json must NOT be called on run 2.
#
# Diff-only verdict embedded in the assertions:
#   • If CAS is re-processed on run 2 → assertion on extracted=0 fails.
#   • If report triggers a new Gemini call → assertion on call_count fails.
#   • If indexer re-indexes → assertion on chroma count fails.
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Shared helpers (reused across diff-only tests)
# ---------------------------------------------------------------------------

def _make_in_memory_db():
    """Return an in-memory SQLite session with the full schema."""
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from backend.db.session import Base

    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False, autocommit=False,
                           expire_on_commit=False)
    return factory()


def _seed_downloaded_file(db, external_file_id: int, file_name: str,
                           local_path: str) -> "File":
    """Insert a File row in status='downloaded', no classification yet."""
    from backend.db.models import File
    row = File(
        external_file_id=external_file_id,
        file_name=file_name,
        local_path=local_path,
        status="downloaded",
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def _fake_parsed_pdf(text: str, path: str = "/fake/file.pdf"):
    """Build a minimal ParsedPdf without touching disk."""
    from backend.pdf_parser.parser import ParsedPdf
    return ParsedPdf(
        path=path,
        n_pages=1,
        text=text,
        pages=(text,),
        tables=(),
    )


def _fake_embed(text: str) -> list:
    """Deterministic 768-d embedding vector (no Gemini call)."""
    import hashlib
    h = hashlib.sha256(text.encode()).digest()
    expanded = (h * 24)[:768]
    return [float(b) / 255.0 for b in expanded]


# ---------------------------------------------------------------------------
# CAS PDF text: contains strong filename + value-table signal so heuristic
# fires at 0.92 — NO Gemini call needed for classification.
# Extraction: we mock generate_json to return the three required fields.
# Report PDF text: contains "quarterly letter" → heuristic fires at 0.90 for
# report — NO Gemini call needed.
# ---------------------------------------------------------------------------

_CAS_TEXT = (
    "Fund Alpha Capital Account Statement\n"
    "As of September 30, 2025\n"
    "Ending Capital Balance $1,234,567.00\n"
    "Partners' Capital — Ending $1,234,567.00\n"
    "Committed Capital $2,000,000.00\n"
    "Capital Contributions $1,800,000.00\n"
    "Cumulative Distributions $100,000.00\n"
)

_REPORT_TEXT = (
    "Fund Alpha Quarterly Letter\n"
    "Q3 2025 Portfolio Update\n"
    "Market Commentary: performance summary of the quarter.\n"
    "Fund Commentary: investment highlights and portfolio update.\n"
)


# ---------------------------------------------------------------------------
# Gemini generate_json mock: returns CAS extraction fields for CAS file,
# a report classification for report file.
# ---------------------------------------------------------------------------

def _make_fake_generate_json(call_log: list):
    """
    Return a fake generate_json that records calls and returns sensible data.

    For extraction prompts (contain 'fund_name') → return extraction fields.
    For classification prompts (contain 'label') → return classification.
    """
    def _fake_generate_json(prompt: str, system_prompt: str = "") -> dict:
        call_log.append({"prompt": prompt[:80], "system": system_prompt[:40]})
        if "fund_name" in system_prompt or "fund_name" in prompt:
            # Extraction call
            return {
                "fund_name": "Fund Alpha",
                "statement_date": "2025-09-30",
                "current_value": "$1,234,567.00",
            }
        # Classification call
        if "capital" in prompt.lower() or "cas" in prompt.lower():
            return {"label": "capital_account_statement", "confidence": 0.95}
        return {"label": "report", "confidence": 0.92}

    return _fake_generate_json


class TestDiffOnlySecondRunDoesZeroWork:
    """
    Guards that a 2nd sync pipeline invocation does ZERO new work when all
    files were fully processed in run 1.

    Calls process_all_pending(db) + index_documents(db) directly — same
    functions the orchestrator (_run_pipeline) calls via asyncio.to_thread.
    """

    def _run_full_pipeline(self, db, chroma_path: str) -> dict:
        """
        Run classify+extract stage then index stage, return combined counts.
        Mirrors _run_pipeline logic: process_all_pending then index_documents.
        """
        from backend.pipeline import process_all_pending
        from backend.indexer.indexer import index_documents

        pipe_result = process_all_pending(db)
        idx_result = index_documents(db, chroma_path=chroma_path)
        return {
            "classified": pipe_result.get("classified", 0),
            "extracted": pipe_result.get("extracted", 0),
            "skipped_pipeline": pipe_result.get("skipped", 0),
            "indexed": idx_result.get("indexed", 0),
            "skipped_index": idx_result.get("skipped", 0),
        }

    def test_second_run_zero_new_work(self, monkeypatch, tmp_path):
        """
        Core diff-only guard:
          Run 1: classifies + extracts 2 files (1 CAS, 1 report), indexes 2.
          Run 2: all counts must be 0 (no re-processing, no duplicate vectors).
        """
        import backend.llm.gemini_client as gc

        # Patch embed_text (used by indexer)
        monkeypatch.setattr(gc, "embed_text", _fake_embed)

        # Patch generate_json (used by extractor when heuristics fail)
        # For our crafted texts the heuristic WILL fire (no Gemini classification),
        # but extraction needs Gemini for CAS.
        gemini_calls_run1: list = []
        gemini_calls_run2: list = []
        monkeypatch.setattr(gc, "generate_json",
                            _make_fake_generate_json(gemini_calls_run1))

        # Create placeholder files on disk so indexer's exists() check passes.
        # Content is irrelevant — parse_pdf is mocked before it reads anything.
        import backend.pdf_parser as pdf_mod
        cas_path = str(tmp_path / "1001_cas_statement.pdf")
        report_path = str(tmp_path / "1002_fund_report.pdf")
        (tmp_path / "1001_cas_statement.pdf").write_bytes(b"%PDF-1.4 fake")
        (tmp_path / "1002_fund_report.pdf").write_bytes(b"%PDF-1.4 fake")

        def fake_parse_pdf(path):
            p = str(path)
            if "1001" in p or "cas" in p.lower():
                return _fake_parsed_pdf(_CAS_TEXT, path=p)
            return _fake_parsed_pdf(_REPORT_TEXT, path=p)

        monkeypatch.setattr(pdf_mod, "parse_pdf", fake_parse_pdf)
        # Also patch the parse_pdf imported inside pipeline, classifier, extractor
        import backend.pipeline as pipe_mod
        monkeypatch.setattr(pipe_mod, "parse_pdf", fake_parse_pdf)
        import backend.classifier.document_classifier as clf_mod
        # classifier imports parse_pdf lazily; patch the module attribute
        import backend.indexer.indexer as idx_mod
        monkeypatch.setattr(idx_mod, "parse_pdf", fake_parse_pdf, raising=False)

        # patch the extract_from_parsed_pdf used inside extractor to avoid
        # needing real Gemini — control via generate_json mock above, but also
        # patch parse_pdf inside extractor scope
        import backend.extractor.statement_extractor as ext_mod
        # no parse_pdf import in extractor (it receives ParsedPdf directly)

        # Reset indexer singleton so tmp_path chroma_path takes effect
        import backend.indexer.indexer as indexer_mod
        indexer_mod._chroma_client = None
        indexer_mod._chroma_path = None

        chroma_path = str(tmp_path / "chroma")

        # Seed DB
        db = _make_in_memory_db()
        _seed_downloaded_file(db, 1001, "1001_cas_statement.pdf", cas_path)
        _seed_downloaded_file(db, 1002, "1002_fund_report.pdf", report_path)

        from backend.db.models import File, Statement

        # -----------------------------------------------------------------
        # RUN 1
        # -----------------------------------------------------------------
        result1 = self._run_full_pipeline(db, chroma_path)

        assert result1["classified"] >= 2, (
            f"Run 1: expected >=2 classified, got {result1['classified']}"
        )
        assert result1["extracted"] >= 1, (
            f"Run 1: expected >=1 extracted (CAS), got {result1['extracted']}"
        )
        assert result1["indexed"] == 2, (
            f"Run 1: expected 2 indexed, got {result1['indexed']}"
        )

        # Capture baseline row counts and chroma count
        from backend.indexer.indexer import get_collection
        collection = get_collection(chroma_path)
        chroma_count_after_run1 = collection.count()
        assert chroma_count_after_run1 > 0, "Run 1 must produce ChromaDB chunks"

        file_count_after_run1 = db.query(File).count()
        stmt_count_after_run1 = db.query(Statement).count()

        assert file_count_after_run1 == 2, "Should have exactly 2 File rows"
        assert stmt_count_after_run1 == 1, "Should have exactly 1 Statement (CAS only)"

        # Verify CAS file is now status='extracted'
        cas_file = db.query(File).filter(File.external_file_id == 1001).first()
        assert cas_file.status == "extracted", (
            f"CAS file status expected 'extracted', got {cas_file.status!r}"
        )
        # Verify report file is status='downloaded' (reports don't get 'extracted')
        report_file = db.query(File).filter(File.external_file_id == 1002).first()
        assert report_file.status == "downloaded", (
            f"Report file status expected 'downloaded', got {report_file.status!r}"
        )

        # -----------------------------------------------------------------
        # RUN 2 — switch to a fresh call log to detect any NEW Gemini calls
        # -----------------------------------------------------------------
        gemini_calls_run2_log: list = []
        monkeypatch.setattr(gc, "generate_json",
                            _make_fake_generate_json(gemini_calls_run2_log))

        result2 = self._run_full_pipeline(db, chroma_path)

        # ---- Core assertions: 0 new work ----

        # No new extractions (CAS already extracted → status='extracted' filtered)
        assert result2["extracted"] == 0, (
            f"DIFF-ONLY BUG: Run 2 extracted={result2['extracted']} "
            f"(expected 0). CAS file is being re-extracted."
        )

        # No new indexing (all files.indexed==1 → skipped by indexer)
        assert result2["indexed"] == 0, (
            f"DIFF-ONLY BUG: Run 2 indexed={result2['indexed']} "
            f"(expected 0). Files are being re-indexed."
        )

        # Gemini must NOT be called for classification on run 2
        # (either P5 fires or file is not in the query at all)
        classify_calls_run2 = [
            c for c in gemini_calls_run2_log
            if "fund_name" not in c.get("system", "") and "fund_name" not in c.get("prompt", "")
        ]
        assert len(classify_calls_run2) == 0, (
            f"DIFF-ONLY BUG: Gemini was called for classification on run 2 "
            f"({len(classify_calls_run2)} times). P5 or query filter failed."
        )

        # ---- Invariants: no duplicate rows / vectors ----

        file_count_after_run2 = db.query(File).count()
        stmt_count_after_run2 = db.query(Statement).count()
        chroma_count_after_run2 = collection.count()

        assert file_count_after_run2 == file_count_after_run1, (
            f"DIFF-ONLY BUG: File row count changed from {file_count_after_run1} "
            f"to {file_count_after_run2}. Duplicate File rows written."
        )
        assert stmt_count_after_run2 == stmt_count_after_run1, (
            f"DIFF-ONLY BUG: Statement row count changed from {stmt_count_after_run1} "
            f"to {stmt_count_after_run2}. Duplicate Statement rows written."
        )
        assert chroma_count_after_run2 == chroma_count_after_run1, (
            f"DIFF-ONLY BUG: ChromaDB chunk count changed from "
            f"{chroma_count_after_run1} to {chroma_count_after_run2}. "
            f"Vectors were duplicated or re-added."
        )

    def test_second_run_report_not_reclassified_via_gemini(self, monkeypatch, tmp_path):
        """
        Focused check: even though the report file stays in status='downloaded'
        (and thus appears in the process_all_pending query on run 2), P5 must
        prevent ANY Gemini classify call for it.

        If this assertion fails, it means P5 (idempotency in classify_and_persist)
        is not firing — a classifier-level diff-only bug.
        """
        import backend.llm.gemini_client as gc

        monkeypatch.setattr(gc, "embed_text", _fake_embed)

        gemini_classification_calls: list = []

        def _spy_generate_json(prompt: str, system_prompt: str = "") -> dict:
            # Only log classification calls (not extraction)
            if "fund_name" not in system_prompt:
                gemini_classification_calls.append(prompt[:60])
            # Return extraction data for extraction calls
            if "fund_name" in system_prompt or "fund_name" in prompt:
                return {
                    "fund_name": "Fund Alpha",
                    "statement_date": "2025-09-30",
                    "current_value": "$1,234,567.00",
                }
            return {"label": "report", "confidence": 0.92}

        monkeypatch.setattr(gc, "generate_json", _spy_generate_json)

        import backend.pdf_parser as pdf_mod
        import backend.pipeline as pipe_mod
        import backend.indexer.indexer as idx_mod

        report_path = str(tmp_path / "1002_fund_report.pdf")
        cas_path = str(tmp_path / "1001_cas_statement.pdf")
        (tmp_path / "1001_cas_statement.pdf").write_bytes(b"%PDF-1.4 fake")
        (tmp_path / "1002_fund_report.pdf").write_bytes(b"%PDF-1.4 fake")

        def fake_parse_pdf(path):
            p = str(path)
            if "1001" in p or "cas" in p.lower():
                return _fake_parsed_pdf(_CAS_TEXT, path=p)
            return _fake_parsed_pdf(_REPORT_TEXT, path=p)

        monkeypatch.setattr(pdf_mod, "parse_pdf", fake_parse_pdf)
        monkeypatch.setattr(pipe_mod, "parse_pdf", fake_parse_pdf)
        monkeypatch.setattr(idx_mod, "parse_pdf", fake_parse_pdf, raising=False)

        # Reset indexer singleton
        idx_mod._chroma_client = None
        idx_mod._chroma_path = None

        chroma_path = str(tmp_path / "chroma")
        db = _make_in_memory_db()
        _seed_downloaded_file(db, 1001, "1001_cas_statement.pdf", cas_path)
        _seed_downloaded_file(db, 1002, "1002_fund_report.pdf", report_path)

        # Run 1
        self._run_full_pipeline(db, chroma_path)

        # Reset call log for run 2
        gemini_classification_calls.clear()

        # Run 2
        self._run_full_pipeline(db, chroma_path)

        assert gemini_classification_calls == [], (
            f"DIFF-ONLY BUG (classifier/P5): Gemini was called for classification "
            f"on run 2: {gemini_classification_calls}. "
            f"P5 (classify_and_persist idempotency) failed."
        )

    def test_failed_file_retried_on_run2(self, monkeypatch, tmp_path):
        """
        Retry-on-fail: if a file has status='failed' before run 2, it should
        be retried (diff = the failed file), proving retry-on-fail still works
        alongside skip-on-done.

        Corpus: 1 CAS (fully processed), 1 report (fully processed), 1 failed CAS.
        After run 1: mark the extra CAS as status='failed'.
        Run 2: only the failed file is retried; the other two are untouched.
        """
        import backend.llm.gemini_client as gc

        monkeypatch.setattr(gc, "embed_text", _fake_embed)

        call_log: list = []
        monkeypatch.setattr(gc, "generate_json", _make_fake_generate_json(call_log))

        import backend.pdf_parser as pdf_mod
        import backend.pipeline as pipe_mod
        import backend.indexer.indexer as idx_mod

        cas_path = str(tmp_path / "1001_cas_statement.pdf")
        report_path = str(tmp_path / "1002_fund_report.pdf")
        failed_cas_path = str(tmp_path / "1003_cas_failed.pdf")
        (tmp_path / "1001_cas_statement.pdf").write_bytes(b"%PDF-1.4 fake")
        (tmp_path / "1002_fund_report.pdf").write_bytes(b"%PDF-1.4 fake")
        (tmp_path / "1003_cas_failed.pdf").write_bytes(b"%PDF-1.4 fake")

        def fake_parse_pdf(path):
            p = str(path)
            if "1002" in p or "report" in p.lower():
                return _fake_parsed_pdf(_REPORT_TEXT, path=p)
            return _fake_parsed_pdf(_CAS_TEXT, path=p)

        monkeypatch.setattr(pdf_mod, "parse_pdf", fake_parse_pdf)
        monkeypatch.setattr(pipe_mod, "parse_pdf", fake_parse_pdf)
        monkeypatch.setattr(idx_mod, "parse_pdf", fake_parse_pdf, raising=False)

        idx_mod._chroma_client = None
        idx_mod._chroma_path = None

        chroma_path = str(tmp_path / "chroma")
        db = _make_in_memory_db()

        _seed_downloaded_file(db, 1001, "1001_cas_statement.pdf", cas_path)
        _seed_downloaded_file(db, 1002, "1002_fund_report.pdf", report_path)
        _seed_downloaded_file(db, 1003, "1003_cas_failed.pdf", failed_cas_path)

        # Run 1: process all 3 files
        result1 = self._run_full_pipeline(db, chroma_path)
        assert result1["indexed"] == 3, (
            f"Run 1: expected 3 indexed, got {result1['indexed']}"
        )

        from backend.db.models import File, Statement
        from backend.indexer.indexer import get_collection

        collection = get_collection(chroma_path)
        chroma_after_run1 = collection.count()
        stmt_after_run1 = db.query(Statement).count()  # 2 CAS → 2 statements

        # Simulate failure: mark file 1003 as 'failed' and un-index it
        failed_file = db.query(File).filter(File.external_file_id == 1003).first()
        assert failed_file is not None
        failed_file.status = "failed"
        failed_file.indexed = 0  # treat as not indexed so indexer retries it
        db.commit()

        # Reset call log for run 2
        call_log.clear()
        call_log_run2: list = []
        monkeypatch.setattr(gc, "generate_json",
                            _make_fake_generate_json(call_log_run2))

        # Run 2
        result2 = self._run_full_pipeline(db, chroma_path)

        # Failed file should be retried → extracted=1, indexed=1
        assert result2["extracted"] == 1, (
            f"Run 2 (retry): expected extracted=1 for the failed CAS, "
            f"got {result2['extracted']}"
        )
        assert result2["indexed"] == 1, (
            f"Run 2 (retry): expected indexed=1 for the failed CAS, "
            f"got {result2['indexed']}"
        )

        # File/Statement counts: statement for the retried file should now exist
        # (was removed by failure, now re-created)
        stmt_after_run2 = db.query(Statement).count()
        assert stmt_after_run2 >= stmt_after_run1, (
            "Run 2 (retry): Statement count should not decrease after retry"
        )

        # ChromaDB: upsert semantics — count should NOT exceed run1 count
        # (same chunk ids → overwrites, not duplicates)
        chroma_after_run2 = collection.count()
        assert chroma_after_run2 == chroma_after_run1, (
            f"Run 2 (retry): ChromaDB count changed from {chroma_after_run1} "
            f"to {chroma_after_run2}. Upsert should overwrite, not duplicate."
        )
