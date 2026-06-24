# Investor Document Platform — Technical Deep Dive

**Audience:** an engineer reading the code for the first time.
**Scope:** what the system does, how data flows end-to-end, every backend subsystem,
the database schema, the RAG path, the HTTP API, and the frontend wiring.

For setup/run instructions see [`../README.md`](../README.md). For the *why* behind the
big choices see the [Design Decisions](#9-design-decisions-the-why) section near the end.

---

## 1. What the system does

A family office invests in private-equity funds. Each fund's manager (GP) publishes
documents to a per-GP **investor portal** — capital account statements (tabular, one
LP's position) and reports (narrative). The portals have no standard format and no API.

This platform automates the whole loop:

1. **Crawl** the portal (login → walk deals → download new files), idempotently.
2. **Classify** each PDF: `capital_account_statement` | `report` | `other` | `unclassified`.
3. **Extract** structured data from statements: fund name, statement date, current value.
4. **Index** statements + reports into a vector store for retrieval.
5. **Serve** a React UI: trigger sync, watch staged progress, view a holdings table,
   ask grounded questions over the corpus, browse/download source files.

---

## 2. Tech stack at a glance

| Layer | Choice |
|-------|--------|
| Backend framework | FastAPI (Python ≥ 3.11), async |
| Relational DB | SQLite via SQLAlchemy ORM + Alembic migrations |
| Vector store | ChromaDB (persistent, local), cosine space |
| LLM + embeddings | Google Gemini (`gemini-2.x` + `text-embedding-004`, 768-d) |
| Crawler | Playwright (Chromium) login + `APIRequestContext` JSON API |
| PDF parsing | pdfplumber (primary) / PyMuPDF |
| Frontend | React + TypeScript + Vite + Tailwind |
| Frontend mocks | MSW (Mock Service Worker), opt-in |

Single LLM vendor, single key (`GEMINI_API_KEY`). Provider is isolated in
`backend/llm/gemini_client.py`, so swapping vendors is a one-file change.

---

## 3. Repository map

```
backend/
  api/
    main.py                 # FastAPI app factory + lifespan startup guards
    routers/
      holdings.py           # GET /api/holdings        (latest stmt per fund)
      sync.py               # POST /api/sync + GET /api/sync/stream (SSE)
      chat.py               # POST /api/chat           (grounded RAG)
      files.py              # GET /api/files + /files/{id}/download
  crawler/portal_crawler.py # Playwright login + JSON-API enumerate + download
  pdf_parser/parser.py      # PDF → ParsedPdf (text + tables)
  classifier/document_classifier.py  # hybrid heuristic + Gemini
  extractor/statement_extractor.py   # 3-field extraction, atomic
  indexer/indexer.py        # chunk → embed → ChromaDB upsert
  rag/chat.py               # retrieve + grounded answer
  llm/gemini_client.py      # generate_text / generate_json / embed_text
  pipeline.py               # classify→extract orchestration over pending files
  db/
    models.py               # File, Statement ORM
    session.py              # engine, Session factory, get_db dependency
    migrations.py           # Alembic auto-migrate on startup
  alembic/versions/0001_init.py
  tests/                    # pytest unit + Hypothesis property tests

frontend/src/
  api/{client.ts,types.ts}  # typed API client + contract
  pages/{SyncPage,HoldingsPage,ChatPage,FilesPage}.tsx
  components/{Table,Card,Badge,ErrorBoundary}.tsx
  mocks/                    # MSW handlers + fixtures (opt-in dev mode)

data/                       # app.db (SQLite), files/ (downloaded PDFs), chroma/
docs/                       # this doc + planning/decision artifacts under master/
```

---

## 4. End-to-end data flow

```
                    POST /api/sync  (single-flight, 409 if running)
                            │
                            ▼
        ┌──────────────────────────────────────────────┐
        │  _run_pipeline() background asyncio.Task       │
        │                                                │
        │  1. discover ─┐                                │
        │  2. download ─┴─ PortalCrawler.run()           │  → data/files/*.pdf
        │                  (Playwright + JSON API)        │  → File rows (status=downloaded)
        │                                                │
        │  3. classify ─┐                                │
        │  4. extract  ─┴─ process_all_pending()         │  → File.classification
        │                  (pdf_parser→classifier→extractor)  → Statement rows
        │                                                │
        │  5. index ────── indexer (NON-FATAL)           │  → ChromaDB vectors
        └──────────────────────────────────────────────┘
                            │
              SSE events ───┘   GET /api/sync/stream  (stage / complete / error)

        Reads:  GET /api/holdings → latest Statement per fund
                POST /api/chat    → retrieve (ChromaDB) → grounded Gemini answer
                GET /api/files     → all File rows
```

The pipeline runs as a **background task**; the POST returns immediately with a
`sync_id`, and the frontend subscribes to the SSE stream for progress.

---

## 5. Database schema

Two tables, SQLite, defined in `backend/db/models.py`. Constraints are enforced at the
DB level (CHECK constraints, UNIQUE, FK CASCADE).

### `files` — one row per discovered portal file, tracked through its lifecycle

| Column | Notes |
|--------|-------|
| `id` PK | autoincrement |
| `external_file_id` **UNIQUE** | stable integer from the portal JSON API — **the idempotency key** |
| `deal_id` | portal deal the file came from |
| `portal_doc_type` | portal's own label — **eval ground-truth only, never used as our classification** |
| `file_name` | |
| `file_url` | presigned S3 URL; **rotates ~hourly, NOT a uniqueness key** |
| `content_hash` | SHA-256 of content (integrity / secondary dedupe) |
| `local_path` | path on disk after download |
| `download_ts` | ISO 8601 UTC |
| `status` | `pending` → `downloaded` → `extracted` / `failed` (CHECK constrained) |
| `classification` | `capital_account_statement` / `report` / `other` / `unclassified` (CHECK) |
| `confidence` | float [0,1] |
| `low_confidence` | 1 when `confidence < 0.75` — drives the UI badge |
| `extraction_error` | human-readable failure reason |
| `indexed` | 0/1 — set after ChromaDB upsert |

### `statements` — structured data extracted from a CAS (1:N from files, CASCADE delete)

| Column | Notes |
|--------|-------|
| `id` PK | |
| `file_id` FK → files.id | `ON DELETE CASCADE` |
| `fund_name` | required |
| `statement_date` | required, ISO `YYYY-MM-DD` |
| `current_value` | required, stored as **TEXT** to preserve decimal precision (never cast to float) |

Index `idx_statements_fund_date(fund_name, statement_date)` backs the holdings query.

**Atomicity invariant:** a Statement row exists only if all three fields were extracted
and validated. No partial rows (enforced in the extractor).

---

## 6. Backend subsystems

### 6.1 Crawler (`crawler/portal_crawler.py`)

Async `PortalCrawler` class. Lifecycle: `_login → _enumerate_deals → per-deal
_enumerate_files → _prerecord → _download_file`.

- **Login** — Playwright Chromium fills the email/password form, asserts redirect away
  from `/login`. Credentials are **never logged**. Mid-crawl session-expiry triggers
  re-login (up to `PORTAL_MAX_LOGIN_RETRIES`).
- **Enumerate** — after login, calls the portal's internal JSON API through Playwright's
  `page.request` (the browser cookie is shared automatically):
  - `POST /api/v0.0.2/deals-list` → deal ids (DOM-scrape fallback if the API fails)
  - `GET /api/v0.0.3/deals/{id}/files` → file metadata
- **Pre-record (R2.3)** — before downloading, UPSERT a `File` row keyed on
  `external_file_id` with `status=pending`. Existing rows only get their rotating
  `file_url` refreshed; status/hash are left untouched.
- **Idempotent download** — for each file:
  - skip if `status ∈ {downloaded, extracted}`
  - retry if `status == failed`
  - on a 403 (presigned URL expired) → re-enumerate the deal for a fresh URL, retry once
  - on success → write `local_path`, `content_hash` (SHA-256), `download_ts`,
    `status=downloaded`
- **Progress** — emits callback events (`login_ok`, `deals_found`, `file_downloaded`,
  `file_skipped`, …) that the sync router turns into SSE frames.

Runnable standalone: `python -m backend.crawler.portal_crawler` (`HEADLESS=0` to watch).

### 6.2 PDF parser (`pdf_parser/parser.py`)

Produces a `ParsedPdf` with `.text` and `.tables_as_lists()`. pdfplumber primary
(good at tabular CAS layouts); raises `PdfParseError` on failure (the pipeline marks the
file `failed` rather than crashing).

### 6.3 Classifier (`classifier/document_classifier.py`) — hybrid

Two-stage, cost-aware:

1. **Heuristic pre-screen** (free, no LLM):
   - Strong filename signal → `capital_account_statement` or `report` @ 0.92, early return.
   - Text keyword analysis is used **only for report detection** (≥2 distinct report
     keywords → `report` @ 0.90). CAS is deliberately *not* decided from free text —
     3rd-party/junk docs contain the same capital vocabulary and would false-positive.
   - A `_CAS_VALUE_SIGNAL` regex (a CAS label within ~80 chars of a dollar number) guards
     against narrative mentions masquerading as real CAS tables.
2. **Gemini JSON fallback** (`generate_json`) when the heuristic is inconclusive. The
   system prompt pins the six known portal funds (Alpha…Zeta) and forces `other` when in
   doubt — statements from *other* funds are explicitly `other`, not CAS.
3. Higher-confidence result wins when both stages produce one.

**Invariants (Property 4):** label ∈ the four valid values; confidence ∈ [0,1];
`low_confidence` iff `confidence < 0.75`. **Idempotent (Property 5):**
`classify_and_persist` skips a file that already has a classification.

### 6.4 Extractor (`extractor/statement_extractor.py`)

Pulls exactly three fields from a CAS, in priority order:

1. **pdfplumber tables** — scan for a known current-value label cell, take the numeric
   cell in the same row (handles "different GPs call it different things": *ending capital
   balance*, *closing NAV*, *partners' capital — ending*, … — a long `_CV_LABELS` list).
2. **Text regex** — date (named-month / ISO / US / `Q3 2025`, context-scored so "as of"/
   "period ended" dates win), fund name (text heading → filename fallback), value.
3. **Gemini JSON fallback** — only for fields still missing after 1–2.

**Atomicity (Properties 7/8/12):** if *any* field can't be extracted+validated, raises
`ExtractionError`, sets `status=failed` + `extraction_error`, and writes **no** Statement
row. `current_value` is validated as non-empty TEXT and never coerced to float;
`statement_date` round-trips through `date.fromisoformat`.

### 6.5 Indexer (`indexer/indexer.py`)

Indexes `report` + `capital_account_statement` files into ChromaDB:

- **Chunking:** 800 chars, 100-char overlap.
- **Embeddings:** Gemini `text-embedding-004` per chunk.
- **Chunk id:** `{external_file_id}_{chunk_index}` — stable, so `upsert` is **idempotent**
  (re-indexing overwrites, never duplicates).
- **Metadata per chunk:** `external_file_id`, `file_name`, `classification`, `period`.
  `period` comes from the related Statement date, else a filename heuristic (`Q1_2023`,
  `Mar2022`, bare year).
- Collection `investor_documents`, `hnsw:space = cosine`. Sets `File.indexed = 1` on
  success. Index failures are **non-fatal** at the orchestrator level.

> ⚠️ Known gap: the sync orchestrator's index stage tries to import a
> `DocumentIndexer` class and silently skips if absent — so `indexer.index_documents`
> is **not currently wired into the live sync run** (it's a no-op stage). Indexing works
> when called directly. See [§10 Known issues](#10-known-issues--tech-debt).

### 6.6 RAG chat (`rag/chat.py`)

- **`retrieve(query, top_k)`** — embed the query, ChromaDB cosine similarity search.
  `top_k` hard-capped at 20 (Property 17). Returns `[{id, document, metadata, distance}]`.
- **`answer(query, top_k)`** — filters chunks to `distance < 0.8` (the out-of-context
  threshold), builds a numbered context block, and calls Gemini with a strict grounding
  system prompt ("answer ONLY from context… never fabricate"). Returns:
  ```json
  { "answer": "...", "citations": [{"file_id","file_name","period"}], "out_of_context": false }
  ```
- **Out-of-corpus honesty (Property 16):** if nothing is retrieved, or all distances ≥ 0.8,
  or Gemini itself returns the canned "I could not find this…" line → empty citations and
  `out_of_context = true`. Citations are deduplicated by `external_file_id`, ordered by
  relevance.

### 6.7 LLM client (`llm/gemini_client.py`)

The single Gemini integration point: `generate_text`, `generate_json` (with a JSON
parse-retry), `embed_text`, and a `GeminiError`. Everything else imports from here, so the
provider is swappable in one file. Live-network tests are marked `@pytest.mark.live` and
skipped by default.

### 6.8 Sync orchestration (`api/routers/sync.py`)

- **Single-flight (ADR-009, Property 10):** an `asyncio.Lock` guards a module-level
  `_running` flag. A second `POST /sync` while a run is active → **HTTP 409**.
- **Background task:** `_run_pipeline()` runs detached; sync functions
  (`process_all_pending`) are offloaded with `asyncio.to_thread` so they don't block the loop.
- **SSE fan-out:** an `_event_log` records every event; subscriber queues replay the log
  on connect (late joiners catch up) then stream live until a terminal event. 30s
  keep-alive comments prevent proxy timeouts.
- **Stages:** `discover → download → classify → extract → index`. The index stage is
  non-fatal — a failure there still emits an overall `complete`.

---

## 7. HTTP API

All under `/api` (mounted in `api/main.py`). Startup **lifespan** runs two guards before
serving: (1) validate required env vars → log every missing one and `exit 1`;
(2) Alembic auto-migrate → `exit 1` on failure.

| Method | Route | Purpose |
|--------|-------|---------|
| GET  | `/health` | liveness (no DB/auth) |
| GET  | `/api/holdings` | latest statement value per fund |
| POST | `/api/sync` · `/api/sync/trigger` | start pipeline (409 if already running) |
| GET  | `/api/sync/stream` | SSE stage progress |
| POST | `/api/chat` | grounded Q&A over the corpus |
| GET  | `/api/files` | all ingested files |
| GET  | `/api/files/{id}/download` | original PDF |

**Holdings query** (`routers/holdings.py`) is pure SQL: normalizes `lower(trim(fund_name))`,
takes `MAX(statement_date)` per fund, and breaks date ties with `MAX(id)` — guaranteeing
exactly one row per fund (Property 9). Values/dates are formatted server-side
(`$1,234,567.89`, `September 30, 2025`).

---

## 8. Frontend

React + TS + Vite + Tailwind. Four pages (`SyncPage`, `HoldingsPage`, `ChatPage`,
`FilesPage`) over a typed client in `api/client.ts`, contract in `api/types.ts`.

- **Single base URL `/api`** proxied by Vite to `http://localhost:8000` in dev.
- **Sync** uses the browser `EventSource` against `/api/sync/stream`; `startSync()`
  throws a typed `SyncInProgressError` on 409.
- **Holdings adapter:** the client maps the backend's pre-formatted `HoldingRow`
  (`"$15,400,000.00"`, `"March 31, 2025"`) into the frontend's `FundSnapshot` shape —
  parsing the currency back to a number, inferring an ISO 4217 code from the symbol, and
  normalizing the date to `YYYY-MM-DD`.
- **Two run modes** via `VITE_DISABLE_MSW`:
  - **Real backend** (default in dev) — talks to the live API through the proxy.
  - **Mock mode** — MSW serves fixtures with no backend running. Mocks are preserved as
    an opt-in, not deleted.

Visual polish is intentionally not a focus; clarity and a correct holdings table are.

---

## 9. Design decisions (the "why")

Condensed from `docs/master/.../20-50_DECISIONS_LOG.md`. Stack evolved during planning
(Claude+pgvector+Voyage → all-Gemini; Postgres → SQLite; design.md adopted).

1. **Crawler = Playwright login + the portal's internal JSON API.** Recon found an
   internal cookie-authed JSON API (`deals-list`, `deals/{id}/files`) with presigned S3
   `file_url`s. So Playwright handles the messy auth (forms, cookies, redirects), then its
   `APIRequestContext` calls the structured API and downloads presigned URLs. Robust auth +
   clean data + fast — and still defensible as "drive it like a user," not brittle DOM
   scraping. Plain `httpx` couldn't survive the JS login; pure DOM scraping would be fragile.

2. **Idempotency key = `external_file_id`, not URL or filename.** The original plan keyed on
   `(portal_url, file_name)`, but the presigned `file_url` rotates hourly and filenames carry
   `(1)` suffixes — neither is stable. The portal's stable integer file id is. `content_hash`
   is kept as a secondary integrity check. This is what makes re-sync truly idempotent:
   re-running downloads 0 new files.

3. **Single Gemini vendor, isolated behind one client.** Only a `GEMINI_API_KEY` was
   provided, so classify/extract/chat and embeddings all use Gemini, isolated in
   `gemini_client.py`. One vendor, one key, one file to change to swap providers.

4. **Hybrid classifier, not LLM-only.** Cheap deterministic heuristics handle the clearly-
   labeled majority (no token cost, no latency); Gemini is the fallback for genuinely
   ambiguous docs. The deliberate asymmetry — filenames can confirm CAS, but free text
   cannot — exists because junk/3rd-party docs share CAS vocabulary and would false-positive.

5. **SQLite + ChromaDB (local, file-based).** Zero external infra to stand up; the relational
   data lives in `data/app.db`, vectors in `data/chroma/`. Adopted from the formal design.md
   over the earlier Postgres/pgvector single-store idea — simpler for a take-home that must
   run end-to-end on a reviewer's machine.

6. **Grounding + honesty as hard requirements.** A cosine-distance OOC threshold plus a strict
   system prompt, and citations carried as structured metadata (file + period) traceable back
   to the original PDF via `/api/files/{id}/download`. Out-of-corpus questions return an honest
   "not found," never a fabrication.

---

## 10. Known issues / tech debt

From `docs/master/.../30-30___TECH-DEBT...` and the implementation summary:

- **Index stage is a no-op in live sync** — the orchestrator imports a `DocumentIndexer`
  class that isn't the actual `indexer.index_documents` entry point, so it silently skips.
  Indexing works when invoked directly but isn't wired into the sync run yet.
- **SSE stream closes on a 30s event gap** — `sync.py`'s `event_generator` yields a
  single keep-alive on `asyncio.wait_for(..., timeout=30)` then *ends* instead of
  continuing the drain loop. The crawler's login phase emits no mapped progress events,
  so a slow live login (>30s) closes the stream and the UI shows "Lost connection to sync
  stream" instead of the terminal complete event. Fix: loop on keep-alive instead of
  returning. (Surfaced by the e2e sync lifecycle test.)
- **Classifier precision** — observed 9 CAS vs ground-truth 8 (one spurious fund) on the
  live corpus.
- **Stage-naming deviation** — five SSE stages (`discover/download/classify/extract/index`)
  vs the plan's four; documented, frontend matches.
- **No real in-browser e2e at build time** — backend was verified by curl; Playwright e2e
  (`frontend/e2e/`) added after, 9 passing.
- **Blank `PORTAL_*` / `GEMINI_API_KEY`** → live sync/chat error until provisioned (by design:
  fail-fast).
- Duplicate modules from concurrent build sessions needed reconciliation.

---

## 11. Testing

- **Backend:** `pytest` — 140 passed, 4 skipped (the 4 are `@pytest.mark.live`, real Gemini).
  Includes Hypothesis property-based tests (idempotency, extraction round-trip, holdings
  uniqueness). External deps (Gemini, portal) mocked in the default suite.
- **Frontend e2e:** Playwright auto-starts both servers (uvicorn :8000 + vite :5173 with
  `VITE_DISABLE_MSW=true`) and drives the real stack — 9 passing. The sync spec triggers a
  **live** portal crawl and chat hits **live** Gemini, so both need valid `.env` values.

---

*This document describes the system as built on the `build/investor-doc-platform` branch.
Authoritative requirements: `.kiro/specs/investor-document-platform/requirements.md` and
`ASSIGNMENT.md`. Planning/decision history: `docs/master/20260624_investor-doc-platform/`.*
