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
        # Make backend.indexer importable but its index_all raises
        fake_indexer_instance = MagicMock()
        fake_indexer_instance.index_all.side_effect = RuntimeError("ChromaDB unavailable")
        fake_indexer_module = MagicMock()
        fake_indexer_module.DocumentIndexer.return_value = fake_indexer_instance

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
