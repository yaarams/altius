"""
Sync orchestrator router — T1.6.

POST  /sync         → trigger a single-flight crawl→classify→extract→index pipeline.
POST  /sync/trigger → alias for POST /sync.
GET   /sync/stream  → SSE stream of stage progress events.

ADR-008: 4-stage pipeline (discover/download/classify/extract/index).
          Index stage failures are NON-FATAL — still emit overall complete.
ADR-009: asyncio.Lock single-flight. Second POST while running → HTTP 409.
Property 10: exactly one concurrent sync run at a time.

SSE contract (must match frontend/src/api/types.ts exactly):
  event: stage   data: { "type":"stage", "stage": SyncStage, "status": SyncStageStatus, ... }
  event: complete data: { "type":"complete", "stages": [...] }
  event: error   data: { "type":"error", "message": str }

SyncStage    ∈ "discover" | "download" | "classify" | "extract" | "index"
SyncStageStatus ∈ "pending" | "running" | "done" | "error"
"""
from __future__ import annotations

import asyncio
import json
import logging
from typing import Any
from uuid import uuid4

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

# Import pipeline dependencies at module level so they can be patched in tests.
# These are real imports; any ImportError here means a genuine missing module.
from backend.crawler.portal_crawler import PortalCrawler, LoginError  # noqa: E402
from backend.pipeline import process_all_pending  # noqa: E402

logger = logging.getLogger(__name__)

router = APIRouter(tags=["sync"])

# ---------------------------------------------------------------------------
# Pydantic response model
# ---------------------------------------------------------------------------

class SyncStartResponse(BaseModel):
    status: str
    sync_id: str


# ---------------------------------------------------------------------------
# Single-flight state (module-level, shared across all requests)
# ---------------------------------------------------------------------------

_lock = asyncio.Lock()          # guards _running / _sync_id mutation
_running: bool = False
_sync_id: str | None = None

# Event log for the current (or most recent) run.
# Each entry is a dict ready to be JSON-serialised as SSE data.
_event_log: list[dict] = []
# SSE subscriber queues — new subscribers start by replaying _event_log,
# then pull from their queue until a terminal event arrives.
_subscribers: set[asyncio.Queue[dict | None]] = set()

# Sentinel: a None put on the queue means "terminal — close the stream".
_TERMINAL_TYPES = {"complete", "error"}


def _reset_state(new_sync_id: str) -> None:
    """Called (under lock) at the start of every new run."""
    global _running, _sync_id, _event_log, _subscribers
    _running = True
    _sync_id = new_sync_id
    _event_log = []
    _subscribers = set()


def _mark_done() -> None:
    """Called (in finally) at the end of every run."""
    global _running
    _running = False


# ---------------------------------------------------------------------------
# Event helpers
# ---------------------------------------------------------------------------

def _make_stage_event(
    stage: str,
    status: str,
    *,
    files_discovered: int | None = None,
    files_downloaded: int | None = None,
    files_classified: int | None = None,
    files_extracted: int | None = None,
    files_indexed: int | None = None,
    error: str | None = None,
) -> dict:
    ev: dict[str, Any] = {"type": "stage", "stage": stage, "status": status}
    if files_discovered is not None:
        ev["files_discovered"] = files_discovered
    if files_downloaded is not None:
        ev["files_downloaded"] = files_downloaded
    if files_classified is not None:
        ev["files_classified"] = files_classified
    if files_extracted is not None:
        ev["files_extracted"] = files_extracted
    if files_indexed is not None:
        ev["files_indexed"] = files_indexed
    if error is not None:
        ev["error"] = error
    return ev


def _make_complete_event(stages: list[dict]) -> dict:
    return {"type": "complete", "stages": stages}


def _make_error_event(message: str) -> dict:
    return {"type": "error", "message": message}


def _broadcast(event: dict) -> None:
    """Append to log and push to all live subscriber queues."""
    _event_log.append(event)
    is_terminal = event.get("type") in _TERMINAL_TYPES
    for q in list(_subscribers):
        q.put_nowait(event)
        if is_terminal:
            q.put_nowait(None)  # signal stream to close


# ---------------------------------------------------------------------------
# Background pipeline coroutine
# ---------------------------------------------------------------------------

async def _run_pipeline() -> None:
    """
    Full pipeline coroutine run as a background asyncio.Task.

    Stages:
      1. discover + download  (crawler)
      2. classify + extract   (process_all_pending via asyncio.to_thread)
      3. index                (index_documents if available, NON-FATAL)

    Always releases the single-flight flag in finally.
    """
    # Snapshot of final stage events for the complete message.
    # key = stage name, value = last emitted dict for that stage
    final_stages: dict[str, dict] = {}

    def emit(event: dict) -> None:
        """Broadcast + track last-per-stage for the complete payload."""
        _broadcast(event)
        if event.get("type") == "stage":
            final_stages[event["stage"]] = event

    try:
        # ------------------------------------------------------------------
        # Stage 1a: discover  (enumerate phase of crawler)
        # ------------------------------------------------------------------
        emit(_make_stage_event("discover", "running"))

        # Track per-stage progress from the crawler callback
        _discover_count = 0
        _download_count = 0

        def _progress_callback(cb_event: dict) -> None:
            nonlocal _discover_count, _download_count
            cb_stage = cb_event.get("stage", "")
            cb_evt   = cb_event.get("event", "")

            if cb_stage == "Crawling":
                if cb_evt == "file_enumerated":
                    _discover_count += 1
                    emit(_make_stage_event("discover", "running",
                                           files_discovered=_discover_count))
                elif cb_evt == "file_downloaded":
                    _download_count += 1
                    emit(_make_stage_event("download", "running",
                                           files_downloaded=_download_count))
                elif cb_evt == "file_skipped":
                    # skipped counts toward download stage progress too
                    emit(_make_stage_event("download", "running",
                                           files_downloaded=_download_count))

        crawler = PortalCrawler()
        try:
            crawl_result = await crawler.run(progress_callback=_progress_callback)
        except LoginError as exc:
            # Don't leak credentials.  LoginError messages are written to not include them.
            short = "Login failed — check portal credentials."
            emit(_make_stage_event("discover", "error", error=short))
            emit(_make_stage_event("download", "error"))
            emit(_make_stage_event("classify", "error"))
            emit(_make_stage_event("extract", "error"))
            emit(_make_stage_event("index", "error"))
            emit(_make_error_event(short))
            return

        # Emit discover done
        emit(_make_stage_event("discover", "done",
                                files_discovered=crawl_result.enumerated))

        # ------------------------------------------------------------------
        # Stage 1b: download  (already happened inside crawler.run)
        # ------------------------------------------------------------------
        emit(_make_stage_event("download", "done",
                                files_downloaded=crawl_result.downloaded))

        # ------------------------------------------------------------------
        # Stage 2: classify + extract  (sync function, run in thread)
        # ------------------------------------------------------------------
        emit(_make_stage_event("classify", "running"))
        emit(_make_stage_event("extract", "running"))

        pipeline_result = await asyncio.to_thread(process_all_pending)

        classified = pipeline_result.get("classified", 0)
        extracted  = pipeline_result.get("extracted", 0)

        emit(_make_stage_event("classify", "done",
                                files_classified=classified))
        emit(_make_stage_event("extract", "done",
                                files_extracted=extracted))

        # ------------------------------------------------------------------
        # Stage 3: index  (NON-FATAL per ADR-008)
        # ------------------------------------------------------------------
        emit(_make_stage_event("index", "running"))

        indexed = 0
        try:
            # Wire in the real indexer (index_documents function, ADR-008).
            try:
                from backend.indexer import index_documents  # noqa: PLC0415
                from backend.db.session import get_session_factory  # noqa: PLC0415

                def _run_index() -> dict:
                    factory = get_session_factory()
                    _db = factory()
                    try:
                        return index_documents(_db)
                    finally:
                        _db.close()

                index_result = await asyncio.to_thread(_run_index)
                if isinstance(index_result, dict):
                    indexed = index_result.get("indexed", 0)
                elif isinstance(index_result, int):
                    indexed = index_result
            except ImportError:
                # Indexer module not yet built — not fatal
                logger.info("backend.indexer not available — skipping index stage")
            emit(_make_stage_event("index", "done", files_indexed=indexed))
        except Exception as idx_exc:
            logger.warning("Index stage failed (non-fatal): %s", idx_exc)
            emit(_make_stage_event("index", "error", error="Index stage failed"))
            # Re-set index stage to error in final_stages (already done by emit above)

        # ------------------------------------------------------------------
        # Terminal: complete
        # ------------------------------------------------------------------
        # Build ordered stages list (discover, download, classify, extract, index)
        _stage_order = ["discover", "download", "classify", "extract", "index"]
        stages_list = [
            final_stages.get(s, _make_stage_event(s, "done"))
            for s in _stage_order
        ]
        emit(_make_complete_event(stages_list))

    except Exception as exc:
        logger.exception("Sync pipeline unexpected error: %s", exc)
        msg = "Unexpected sync error — see server logs."
        emit(_make_error_event(msg))

    finally:
        _mark_done()


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

async def _trigger_sync() -> SyncStartResponse:
    """Shared handler for POST /sync and POST /sync/trigger."""
    global _running, _sync_id

    # Check + acquire under lock (ADR-009 single-flight)
    async with _lock:
        if _running:
            raise HTTPException(status_code=409, detail="Sync already in progress")
        new_id = uuid4().hex
        _reset_state(new_id)

    # Launch pipeline as background task (do NOT await)
    asyncio.create_task(_run_pipeline())

    return SyncStartResponse(status="started", sync_id=new_id)


@router.post("/sync", response_model=SyncStartResponse)
async def post_sync() -> SyncStartResponse:
    """Start a sync run.  Returns 409 if one is already in progress."""
    return await _trigger_sync()


@router.post("/sync/trigger", response_model=SyncStartResponse)
async def post_sync_trigger() -> SyncStartResponse:
    """Alias for POST /sync."""
    return await _trigger_sync()


@router.get("/sync/stream")
async def get_sync_stream():
    """
    SSE stream of sync progress events.

    Replays the current run's event log (for late-joiners), then streams
    live events until a terminal event (complete / error), then closes.

    If no run has been started yet, sends a single idle complete event
    with empty stages so the frontend doesn't hang.
    """

    async def event_generator():
        # Register subscriber queue BEFORE replaying log so we don't miss
        # events that arrive between log-replay and queue-attachment.
        q: asyncio.Queue[dict | None] = asyncio.Queue()

        # Snapshot: was there ANY run already started?
        log_snapshot = list(_event_log)
        is_terminal_already = any(
            e.get("type") in _TERMINAL_TYPES for e in log_snapshot
        )

        # If a run is active (or was just completed), replay the log.
        if log_snapshot:
            _subscribers.add(q)
            for ev in log_snapshot:
                yield _sse_frame(ev)

            # If the log already contains a terminal event, we're done.
            if is_terminal_already:
                _subscribers.discard(q)
                return

            # Otherwise drain live events from queue
            try:
                while True:
                    item = await asyncio.wait_for(q.get(), timeout=30.0)
                    if item is None:
                        break
                    yield _sse_frame(item)
                    if item.get("type") in _TERMINAL_TYPES:
                        break
            except asyncio.TimeoutError:
                # Keep-alive comment to prevent proxy timeout
                yield ": keep-alive\n\n"
            finally:
                _subscribers.discard(q)

        elif _running:
            # Run started but log is empty (race) — subscribe and stream
            _subscribers.add(q)
            try:
                while True:
                    item = await asyncio.wait_for(q.get(), timeout=30.0)
                    if item is None:
                        break
                    yield _sse_frame(item)
                    if item.get("type") in _TERMINAL_TYPES:
                        break
            except asyncio.TimeoutError:
                yield ": keep-alive\n\n"
            finally:
                _subscribers.discard(q)

        else:
            # No run has ever started — emit an idle complete so frontend
            # doesn't hang waiting for a terminal event.
            idle = _make_complete_event([])
            yield _sse_frame(idle)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


def _sse_frame(event: dict) -> str:
    """Format a dict as a named SSE frame:  event: <type>\ndata: <json>\n\n"""
    event_type = event.get("type", "stage")
    data = json.dumps(event, separators=(",", ":"))
    return f"event: {event_type}\ndata: {data}\n\n"
