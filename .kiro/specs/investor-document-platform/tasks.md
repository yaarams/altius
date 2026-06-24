# Implementation Plan: Investor Document Platform

## Overview

Full-stack implementation of an automated investor document pipeline: a Python FastAPI backend
that crawls `fo1.altius.finance`, classifies/extracts/indexes documents, and a React+TypeScript+Vite
frontend with Holdings, Chat, and Files pages. Tasks are ordered so each step builds on the previous.

---

## Tasks

- [ ] 1. Project scaffolding and directory structure
  - Create `backend/` and `frontend/` top-level directories
  - Create `backend/crawler/`, `backend/classifier/`, `backend/extractor/`, `backend/indexer/`,
    `backend/api/routers/`, `backend/api/`, `backend/db/`, `backend/core/` subdirectories
  - Add `__init__.py` files to all backend Python packages
  - Create `data/files/` directory for downloaded PDFs and a `.gitkeep`
  - Create root-level `pyproject.toml` (or `requirements.txt`) listing all Python dependencies:
    fastapi, uvicorn, sqlalchemy, alembic, playwright, pdfplumber, openai, chromadb,
    pydantic-settings, hypothesis, pytest, pytest-asyncio, httpx
  - Create `frontend/` Vite+React+TypeScript project skeleton (`npm create vite@latest`)
  - _Requirements: 12.1, 12.2, 12.3_


- [ ] 2. Configuration and secrets management
  - [ ] 2.1 Implement `backend/core/config.py` with pydantic-settings `Settings` class
    - Fields: `PORTAL_URL`, `PORTAL_USERNAME`, `PORTAL_PASSWORD`, `OPENAI_API_KEY`,
      `DATABASE_URL`, `CHROMA_PERSIST_DIR`, `DATA_FILES_DIR`
    - Use `pydantic_settings.BaseSettings` with `model_config = SettingsConfig(env_file=".env")`
    - Validate that no required field is empty string (custom validator → treat as missing)
    - On validation failure, collect all missing/empty field names, log them, and raise `SystemExit(1)`
    - _Requirements: 12.1, 12.2, 12.3, 12.5, 12.6_

  - [ ]* 2.2 Write property test for startup config validation (Property 14)
    - **Property 14: Startup Fails Fast on Missing Environment Variables**
    - **Validates: Requirements 12.5, 12.6**
    - Use Hypothesis `st.sets(st.sampled_from(REQUIRED_VARS))` to pick arbitrary subsets of missing vars
    - Assert that `Settings()` raises `SystemExit` or `ValidationError` naming each missing var

  - [ ] 2.3 Create `.env.example` in the project root
    - List every env var from `Settings` with clearly fake placeholder values
    - _Requirements: 12.4_


- [ ] 3. Database models, migrations, and startup auto-apply
  - [ ] 3.1 Define SQLAlchemy ORM models in `backend/db/models.py`
    - `FileRecord` model mapping to `files` table with all columns from schema:
      `id`, `portal_url`, `deal_name`, `file_name`, `local_path`, `download_ts`, `status`,
      `classification`, `confidence`, `low_confidence`, `extraction_error`, `indexed`, `created_at`
    - `UniqueConstraint("portal_url", "file_name")` on `FileRecord`
    - `Statement` model mapping to `statements` table:
      `id`, `file_id` (FK → files.id ON DELETE CASCADE), `fund_name`, `statement_date`, `current_value`
    - `Index("idx_statements_fund_date", "fund_name", "statement_date")` on `Statement`
    - _Requirements: 11.1, 11.2, 11.3_

  - [ ] 3.2 Set up Alembic in `backend/db/migrations/`
    - Run `alembic init backend/db/migrations` and configure `env.py` to use `Settings.DATABASE_URL`
      and import `Base.metadata` from `backend/db/models.py`
    - Generate initial migration creating `files` and `statements` tables
    - _Requirements: 11.5_

  - [ ] 3.3 Add startup migration auto-apply in `backend/api/main.py` lifespan
    - On app startup (lifespan `startup` event), run `alembic upgrade head` programmatically
    - If migration fails, log the failing migration name and call `sys.exit(1)` before binding port
    - _Requirements: 11.5, 11.6_

  - [ ]* 3.4 Write property test for DB uniqueness constraint (Property 13)
    - **Property 13: DB Uniqueness Constraint on (portal_url, file_name)**
    - **Validates: Requirements 11.3, 3.1**
    - Use Hypothesis `st.text()` strategies for `portal_url` and `file_name`
    - Insert first record, attempt duplicate insert, assert `IntegrityError` raised


- [ ] 4. Crawler implementation
  - [ ] 4.1 Implement `PortalCrawler` class in `backend/crawler/portal_crawler.py`
    - Constructor accepts `settings: Settings`, `db_session`, `progress_callback`
    - `_login()`: navigate to portal URL, fill username/password fields, submit form,
      verify successful login by checking for post-login DOM element
    - `_enumerate_deals()`: scrape deal index page, return `list[DealInfo]`
      (dataclass with `deal_name: str`, `deal_url: str`)
    - `_enumerate_files(deal)`: navigate to deal URL, scrape file links,
      return `list[FileInfo]` (dataclass with `file_name`, `portal_url`, `deal_name`)
    - `_download_file(file_info)`: use Playwright download interception, save to
      `DATA_FILES_DIR/{deal_name}/{file_name}`, return `Path`
    - Before each download: query DB for existing `FileRecord` matching `(portal_url, file_name)`;
      skip if `status in ('downloaded', 'extracted')`; retry if `status == 'failed'`
    - Detect session expiry by watching for redirect to login URL during navigation;
      retry `_login()` up to 3 times; resume from current deal index on success
    - All deal/file DB records written before any download starts
    - Emit progress events via `progress_callback` for each stage
    - `run()` returns `CrawlResult` dataclass summarising counts
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 2.1, 2.2, 2.3, 2.4, 2.5, 3.1, 3.2, 3.3, 3.4, 3.6_

  - [ ]* 4.2 Write property test for crawler skip logic (Property 1)
    - **Property 1: Crawler Skips Already-Processed Files**
    - **Validates: Requirements 3.1, 3.2**
    - Mock DB returning records with `status in ('downloaded', 'extracted')`
    - Assert `_download_file` is never called for those files

  - [ ]* 4.3 Write property test for failed-file retry logic (Property 2)
    - **Property 2: Failed Files Are Retried**
    - **Validates: Requirements 3.6**
    - Seed DB with arbitrary number of `status='failed'` records
    - Assert `_download_file` is called exactly once per failed record

  - [ ]* 4.4 Write property test for download DB record (Property 3)
    - **Property 3: Download Produces Correct DB Record**
    - **Validates: Requirements 3.3**
    - Use Hypothesis `st.text()` for `file_name` and `portal_url`, mock download success
    - Assert resulting `FileRecord.status == 'downloaded'` and `download_ts` is non-null ISO 8601 UTC


- [ ] 5. PDF parsing layer
  - [ ] 5.1 Implement `_parse_pdf()` in `backend/extractor/statement_extractor.py`
    - Open PDF with `pdfplumber.open()`, iterate all pages
    - For each page, extract `page.extract_text()` and `page.extract_tables()`
    - Return `list[PageContent]` (dataclass: `page_number`, `text: str`, `tables: list[...]`)
    - If `pdfplumber` raises any exception, propagate it; caller handles DB failure recording
    - _Requirements: 10.1, 10.2, 10.4_

  - [ ]* 5.2 Write property test for multi-page PDF parsing (Property 11)
    - **Property 11: Extractor Handles All Pages of Multi-Page PDFs**
    - **Validates: Requirements 10.2**
    - Use Hypothesis `st.integers(min_value=1, max_value=20)` for page count
    - Build synthetic in-memory PDFs with unique marker text per page
    - Assert all N pages appear in the returned `PageContent` list with non-empty text


- [ ] 6. Statement extractor
  - [ ] 6.1 Implement field extraction methods in `backend/extractor/statement_extractor.py`
    - `_extract_fund_name()`: search page headers and first-page text for fund name patterns
    - `_extract_statement_date()`: regex for date patterns (MM/DD/YYYY, Month D YYYY, etc.),
      parse to `datetime.date`, store as ISO 8601
    - `_extract_current_value()`: scan all table cells and text lines for the variant labels
      listed in the design (`ending capital balance`, `closing nav`, `partner's capital — ending`,
      `partner's capital - ending`, `net asset value`, `ending balance`, `closing balance`,
      `partners' capital, end of period`); strip `$`, `,`, whitespace from adjacent value;
      parse to `Decimal`
    - `extract()` public method: call `_parse_pdf()`, then all three field extractors;
      if any required field is `None`, record `files.extraction_error` with descriptive reason,
      do NOT write to `statements` table; if all present, write complete `Statement` row and
      update `files.status = 'extracted'`
    - _Requirements: 5.1, 5.2, 5.3, 5.4, 5.5, 10.1, 10.4, 10.5_

  - [ ]* 6.2 Write property test for extraction atomicity (Property 7)
    - **Property 7: Extraction Produces Complete or No Record**
    - **Validates: Requirements 5.3, 5.4, 10.5**
    - Use Hypothesis to generate `PageContent` lists with random subsets of fields present/absent
    - Assert: if any required field absent → zero `Statement` rows written + `extraction_error` set
    - Assert: if all required fields present → exactly one complete `Statement` row with no nulls

  - [ ]* 6.3 Write property test for extraction persistence fidelity (Property 8)
    - **Property 8: Extraction Stores Fields Matching Extracted Values**
    - **Validates: Requirements 5.5**
    - Use Hypothesis `st.text()`, `st.dates()`, `st.decimals()` to generate field values
    - Assert values stored in DB exactly match values returned by extractor (no transformation)

  - [ ]* 6.4 Write property test for round-trip fidelity (Property 12)
    - **Property 12: Extraction Round-Trip Fidelity**
    - **Validates: Requirements 10.3**
    - Generate `ExtractionResult` with arbitrary field values, format to canonical output,
      parse again, assert field names / count / values identical


- [ ] 7. Classifier
  - [ ] 7.1 Implement `DocumentClassifier` in `backend/classifier/document_classifier.py`
    - `_heuristic_classify(text, filename)`: apply filename keyword rules and structural table
      cues (committed/contributed/distributed within first 3 pages); return `ClassificationResult`
      with `method='heuristic'` and `confidence ≥ 0.90` if rules match, else return `None`
    - `_llm_classify(text, filename)`: call OpenAI gpt-4o-mini with system + user prompt;
      temperature=0.0; parse JSON response `{label, confidence, reasoning}`;
      on invalid JSON, retry once with explicit format instruction; on second failure return
      `ClassificationResult(label='unclassified', confidence=0.0, method='failed')`
    - `classify(file_record)`: check DB for existing non-null `classification` → skip if present
      (return existing); else call `_heuristic_classify` first; if confidence ≥ 0.90 use result;
      else call `_llm_classify`; set `low_confidence = (confidence < 0.75)`;
      persist label, confidence, `low_confidence` to `files` record
    - _Requirements: 4.1, 4.2, 4.3, 4.5, 4.6, 4.7, 4.8_

  - [ ]* 7.2 Write property test for classifier output invariants (Property 4)
    - **Property 4: Classifier Output Invariants**
    - **Validates: Requirements 4.1, 4.2, 4.3**
    - Use Hypothesis `st.text()` for filenames and PDF text; mock LLM to return arbitrary labels
    - Assert: label ∈ {capital_account_statement, report, other, unclassified}
    - Assert: confidence ∈ [0.0, 1.0]
    - Assert: `low_confidence == True` iff `confidence < 0.75`

  - [ ]* 7.3 Write property test for skip-if-classified logic (Property 5)
    - **Property 5: Classification Is Not Repeated**
    - **Validates: Requirements 4.8**
    - Seed `FileRecord` with arbitrary non-null `classification` value (including `unclassified`)
    - Assert `_llm_classify` and `_heuristic_classify` are never called


- [ ] 8. Indexer
  - [ ] 8.1 Implement `DocumentIndexer` in `backend/indexer/document_indexer.py`
    - `_chunk_text(text, chunk_size=800, overlap=100)`: sliding-window chunker that prefers
      paragraph break boundaries; return `list[str]`
    - `index_file(file_record)`: extract full text via pdfplumber, chunk it, batch-embed in
      groups of 100 using OpenAI `text-embedding-3-small`, upsert to ChromaDB collection
      `investor_documents` with document ID `{file_id}_{chunk_index}` and metadata
      (`file_id`, `file_name`, `deal_name`, `document_type`, `statement_date`, `chunk_index`);
      set `files.indexed = 1` on success; on failure, log and leave `indexed = 0`
    - `index_all_pending(progress_callback)`: query for all `FileRecord` where
      `indexed=0` and `status in ('downloaded','extracted')` and
      `classification in ('report','capital_account_statement')`; call `index_file` for each
    - _Requirements: 8.7_

  - [ ]* 8.2 Write property test for document retrievability after indexing (Property 17)
    - **Property 17: New Documents Are Retrievable After Indexing**
    - **Validates: Requirements 8.7**
    - Use Hypothesis `st.text(min_size=50)` for document content; build synthetic `FileRecord`;
      call `index_file`, then query ChromaDB with a phrase from the document
    - Assert at least one result returned with matching `file_id` in metadata

- [ ] 9. Checkpoint — Core pipeline stages complete
  - Ensure all tests pass. Verify that crawler, classifier, extractor, and indexer can be
    imported and instantiated without errors. Ask the user if questions arise.


- [ ] 10. Pipeline orchestrator
  - [ ] 10.1 Implement `backend/pipeline/orchestrator.py` with `PipelineOrchestrator`
    - Module-level `asyncio.Lock` `_pipeline_lock` and `bool` flag `_pipeline_running`
    - `run(progress_queue: asyncio.Queue)` async method:
      - Set `_pipeline_running = True` under lock; ensure `finally` clears flag
      - Run stages in sequence: `Crawler.run()` → `Classifier` (all pending files) →
        `Extractor` (all `capital_account_statement` files) → `Indexer.index_all_pending()`
      - After each stage, put `SyncProgressEvent` onto the queue
      - On stage completion, put `SyncCompleteEvent(type='complete', summary=...)` with counts
      - On any unhandled exception, put `SyncCompleteEvent(type='error', ...)` and re-raise
    - `is_running() -> bool` helper
    - _Requirements: 6.2, 6.3, 6.4, 6.5, 6.6_

  - [ ]* 10.2 Write property test for sync summary counts (Property 6)
    - **Property 6: Sync Summary Counts Match Database**
    - **Validates: Requirements 4.4**
    - Use Hypothesis to generate a list of `FileRecord` dicts with arbitrary `low_confidence` values
    - Run orchestrator's summary-count logic with mocked DB result
    - Assert `summary.low_confidence_count` equals count of records with `low_confidence=True`
      that were classified during the run

  - [ ]* 10.3 Write property test for concurrent sync 409 (Property 10)
    - **Property 10: Concurrent Sync Trigger Returns 409**
    - **Validates: Requirements 6.6**
    - Start a fake background pipeline run (set `_pipeline_running = True`)
    - Fire a second `POST /api/sync/trigger` via FastAPI `TestClient`
    - Assert HTTP 409 with body indicating pipeline already running


- [ ] 11. FastAPI application and API layer
  - [ ] 11.1 Implement `backend/api/main.py` app factory and lifespan
    - Create `FastAPI` app with lifespan context manager (startup: migrations, settings validation;
      shutdown: cleanup Playwright context if open)
    - Add CORS middleware allowing the Vite dev server origin
    - Mount all routers under `/api`
    - _Requirements: 11.5, 11.6, 12.5_

  - [ ] 11.2 Implement Pydantic schemas in `backend/api/schemas.py`
    - `HoldingRow`, `HoldingsResponse`, `ChatRequest`, `Citation`, `ChatResponse`,
      `SyncProgressEvent`, `SyncCompleteEvent`, `SyncSummary`, `LowConfidenceFile`, `FileEntry`
    - All fields typed per design document; `current_value` as `str` (pre-formatted)
    - _Requirements: 7.2, 8.3, 9.2_

  - [ ] 11.3 Implement sync router in `backend/api/routers/sync.py`
    - `POST /api/sync/trigger`: check `orchestrator.is_running()`; if true return 409;
      else start background task via `BackgroundTasks`; return 202
    - `GET /api/sync/stream`: `StreamingResponse` with `text/event-stream` content type;
      async generator reads from `asyncio.Queue` until terminal event; formats as `data: {json}\n\n`
    - _Requirements: 6.2, 6.3, 6.4, 6.5, 6.6_

  - [ ] 11.4 Implement holdings router in `backend/api/routers/holdings.py`
    - `GET /api/holdings`: execute latest-per-fund SQL query from design doc;
      format `current_value` as `"$1,234,567.89"`, `statement_date` as `"March 31, 2025"`;
      return `HoldingsResponse`
    - _Requirements: 7.1, 7.2, 7.3, 7.4, 5.6_

  - [ ] 11.5 Implement chat router in `backend/api/routers/chat.py`
    - `POST /api/chat`: embed `question` with `text-embedding-3-small`; query ChromaDB
      `top_k=20`; build prompt with retrieved passages and metadata; call gpt-4o;
      parse response into `ChatResponse` with citations; set `not_found=True` if LLM
      signals no supporting passages; handle 503/504/502 error cases per design doc
    - _Requirements: 8.1, 8.2, 8.3, 8.4, 8.5, 8.6, 8.8, 8.9_

  - [ ] 11.6 Implement files router in `backend/api/routers/files.py`
    - `GET /api/files`: query all `FileRecord` rows; default sort `download_ts DESC`;
      accept optional `?sort=document_type` query param for alphabetical sort;
      return `list[FileEntry]`
    - `GET /api/files/{id}/download`: look up `FileRecord.local_path`; stream file bytes
      with `application/pdf` content type; 404 if not found
    - _Requirements: 9.1, 9.2, 9.4, 9.5_

  - [ ] 11.7 Implement `backend/api/dependencies.py`
    - DB session dependency (per-request SQLAlchemy `Session` via `yield`)
    - Settings singleton dependency
    - ChromaDB client singleton dependency
    - _Requirements: 12.1, 12.2, 12.3_


  - [ ]* 11.8 Write property test for holdings query (Property 9)
    - **Property 9: Holdings Query Returns One Row Per Fund With Latest Date**
    - **Validates: Requirements 5.6, 7.1, 7.3**
    - Use Hypothesis to generate lists of `Statement` dicts with varying fund names (including
      whitespace/case variants), dates, and tie-breaking IDs
    - Run the holdings SQL query against an in-memory SQLite DB
    - Assert exactly one row per normalized fund name, each with the latest `statement_date`
      and highest `id` as tie-breaker

  - [ ]* 11.9 Write property test for chat retrieval bound (Property 15)
    - **Property 15: Chat Retrieval Is Bounded**
    - **Validates: Requirements 8.8**
    - Use Hypothesis `st.text()` for query; mock ChromaDB to record call arguments
    - Assert `top_k` argument passed to `collection.query()` is always ≤ 20

  - [ ]* 11.10 Write property test for citation completeness (Property 16)
    - **Property 16: Every Chat Answer Includes Citations**
    - **Validates: Requirements 8.3, 8.4**
    - Mock ChromaDB to return N ≥ 1 passages with metadata; mock LLM response
    - Assert `ChatResponse.citations` has ≥ 1 entry with non-null `file_name` and `period`

  - [ ]* 11.11 Write property test for files page completeness (Property 18)
    - **Property 18: Files Page Lists All DB Records With All Fields**
    - **Validates: Requirements 9.1, 9.2**
    - Use Hypothesis `st.integers(min_value=0, max_value=50)` for DB record count
    - Insert N records into in-memory DB; call `GET /api/files` via `TestClient`
    - Assert response contains exactly N entries; each has non-null required fields

  - [ ]* 11.12 Write property test for low-confidence badge threshold (Property 19)
    - **Property 19: Low-Confidence Badge Threshold Is Exactly 0.75**
    - **Validates: Requirements 9.3, 4.3**
    - Use Hypothesis `st.floats(min_value=0.0, max_value=1.0)` for confidence scores
    - Assert `FileEntry.low_confidence == True` iff `confidence < 0.75`


- [ ] 12. Checkpoint — Backend API complete
  - Ensure all tests pass. Manually verify that `uvicorn backend.api.main:app --reload` starts
    without errors and that Swagger UI at `/docs` shows all 6 endpoints. Ask the user if questions arise.

- [ ] 13. Frontend scaffolding and shared infrastructure
  - [ ] 13.1 Configure Vite+React+TypeScript project with Tailwind CSS
    - Install Tailwind CSS, `@tailwindcss/vite`, configure `tailwind.config.ts` and `index.css`
    - Install `react-router-dom` for client-side routing
    - Configure `vite.config.ts` API proxy: `/api` → `http://localhost:8000`
    - _Requirements: 6.1_

  - [ ] 13.2 Define shared TypeScript types in `frontend/src/types/index.ts`
    - `HoldingRow`, `ChatResponse`, `Citation`, `FileEntry`, `SyncProgressEvent`,
      `SyncCompleteEvent` matching backend Pydantic schemas exactly
    - _Requirements: 7.2, 8.3, 9.2_

  - [ ] 13.3 Implement `frontend/src/api/client.ts` typed API wrappers
    - `getHoldings(): Promise<HoldingRow[]>`
    - `postChat(question: string): Promise<ChatResponse>`
    - `getFiles(): Promise<FileEntry[]>`
    - `triggerSync(): Promise<Response>` (returns raw Response to inspect status code)
    - `fileDownloadUrl(id: number): string` — returns `/api/files/{id}/download`
    - _Requirements: 6.2, 7.1, 8.1, 9.4_


- [ ] 14. Frontend Layout and SyncControl component
  - [ ] 14.1 Implement `frontend/src/hooks/useSyncStream.ts`
    - Manages `EventSource` lifecycle for `/api/sync/stream`
    - Opens `EventSource` after successful `POST /api/sync/trigger`
    - Parses progress events and terminal `complete`/`error` events
    - Exposes `{ isSyncing, statusMessage, lastComplete, triggerSync }` from hook
    - On 409 response to trigger, sets `statusMessage` to "Sync already in progress"
      without setting `isSyncing = true`
    - Closes `EventSource` on terminal event or component unmount
    - _Requirements: 6.2, 6.3, 6.4, 6.5, 6.6_

  - [ ] 14.2 Implement `frontend/src/components/Layout.tsx` and `SyncControl.tsx`
    - `Layout.tsx`: top nav with links to Holdings, Chat, Files pages; renders `SyncControl`;
      wraps `<Outlet />` from react-router-dom
    - `SyncControl.tsx`: "Sync" button; disabled while `isSyncing`; shows progress stage string
      ("Crawling…", "Classifying…", etc.); shows success/error message on completion;
      displays "Sync already in progress" inline (without disabling button) on 409
    - Wire `useSyncStream` hook; broadcast `lastComplete` event via React context for Holdings refresh
    - _Requirements: 6.1, 6.2, 6.3, 6.4, 6.5, 6.6_

  - [ ] 14.3 Set up routing in `frontend/src/App.tsx`
    - `<Route path="/" element={<Layout />}>`
    - Nested routes: `/` → `HoldingsPage`, `/chat` → `ChatPage`, `/files` → `FilesPage`
    - _Requirements: 6.1_


- [ ] 15. Holdings page
  - [ ] 15.1 Implement `frontend/src/hooks/useHoldings.ts`
    - Fetches from `GET /api/holdings` on mount
    - Re-fetches when `lastComplete` sync event fires (via context)
    - Exposes `{ holdings, loading, error }`
    - _Requirements: 7.1, 7.5_

  - [ ] 15.2 Implement `frontend/src/pages/HoldingsPage.tsx`
    - Table with columns: Fund Name, Current Value, Statement Date
    - `current_value` displayed as-is from API (already formatted `"$1,234,567.89"`)
    - `statement_date` displayed as-is from API (already formatted `"March 31, 2025"`)
    - Show "—" placeholder for rows where value is unavailable
    - Empty state: message "No holdings data — run a sync to get started" with sync CTA
    - Auto-refreshes on sync complete without full page reload
    - _Requirements: 7.1, 7.2, 7.3, 7.4, 7.5, 7.6_

- [ ] 16. Chat page
  - [ ] 16.1 Implement `frontend/src/pages/ChatPage.tsx`
    - Uncontrolled `<textarea>`: Enter submits, Shift+Enter inserts newline
    - Submit button; both disabled during pending request
    - On submit: POST to `/api/chat`; show spinner/loading indicator while awaiting response
    - 60-second `AbortController` timeout: on abort, show "Request timed out — please try again"
      with retry option
    - Render `answer` text in response area
    - Render `citations` as inline chips showing `file_name` and `period`; each chip is an
      `<a target="_blank">` linking to `fileDownloadUrl(citation.file_id)`
    - If `not_found === true`, show "This information is not available in the downloaded documents"
    - _Requirements: 8.1, 8.2, 8.3, 8.4, 8.5_


- [ ] 17. Files page
  - [ ] 17.1 Implement `frontend/src/pages/FilesPage.tsx`
    - Fetch all files from `GET /api/files`
    - Default sort: `download_date` descending
    - Clickable column header on "Document Type" re-sorts ascending alphabetically
    - Each row: file name, document type (or "Pending" if null), deal name, download date,
      confidence score formatted to 2 decimal places (or "—" if null)
    - Amber pill badge "Low confidence" on rows where `low_confidence === true`;
      NO badge when `low_confidence === false`
    - "Open" button: `window.open(fileDownloadUrl(file.id), '_blank')`
    - _Requirements: 9.1, 9.2, 9.3, 9.4, 9.5_

- [ ] 18. Backend unit and API integration tests
  - [ ] 18.1 Write extractor unit tests in `backend/tests/test_extractor_unit.py`
    - Each known current-value label variant extracted correctly from synthetic `PageContent`
    - Fund name normalization (extra whitespace, mixed case)
    - Statement date parsing for formats: MM/DD/YYYY, Month D YYYY, YYYY-MM-DD
    - Empty PDF (zero pages) returns parse failure, no `Statement` written
    - _Requirements: 5.1, 5.2, 10.1, 10.2_

  - [ ] 18.2 Write API unit tests in `backend/tests/test_api.py` using FastAPI `TestClient`
    - Holdings endpoint returns formatted currency string for valid data
    - Holdings endpoint returns empty list when no statements in DB
    - Files endpoint default sort is `download_date` descending
    - Files endpoint `?sort=document_type` returns alphabetical order
    - Sync trigger returns 409 when `_pipeline_running = True` (patched)
    - Chat endpoint with mocked ChromaDB and OpenAI returns correct `ChatResponse` schema
    - Chat endpoint returns `not_found=True` when no passages retrieved
    - _Requirements: 6.6, 7.2, 7.4, 8.3, 9.5_


  - [ ] 18.3 Configure Hypothesis test profile in `backend/tests/conftest.py`
    - Register and load `"ci"` profile with `max_examples=100`,
      `suppress_health_check=[HealthCheck.too_slow]`, `deadline=5000`
    - _Requirements: (testing infrastructure)_

- [ ] 19. Frontend unit tests
  - [ ] 19.1 Set up Vitest + React Testing Library in `frontend/`
    - Install `vitest`, `@testing-library/react`, `@testing-library/user-event`, `jsdom`
    - Configure `vite.config.ts` test environment: `jsdom`

  - [ ]* 19.2 Write frontend unit tests in `frontend/src/__tests__/`
    - `SyncControl`: button disables on click, re-enables on `complete` SSE event
    - `SyncControl`: shows "Sync already in progress" on 409 without disabling button
    - `HoldingsPage`: renders currency and date formatting from API data correctly
    - `HoldingsPage`: shows empty-state message when `holdings` is empty array
    - `FilesPage`: low-confidence badge appears only when `low_confidence === true`
    - `FilesPage`: badge absent when `low_confidence === false` even at confidence 0.749
    - `ChatPage`: citation chips render `file_name`, `period`, and clickable `href`
    - `ChatPage`: shows "not available" message when `not_found === true`
    - _Requirements: 6.6, 7.4, 7.6, 8.3, 8.5, 9.3_

- [ ] 20. Checkpoint — All tests passing
  - Run `pytest backend/` and `npm run test -- --run` in `frontend/`
  - Ensure all property-based and unit tests pass. Ask the user if questions arise.


- [ ] 21. Final wiring, README, and repo hygiene
  - [ ] 21.1 Wire all backend components together in `backend/api/main.py`
    - Confirm `PortalCrawler`, `DocumentClassifier`, `StatementExtractor`, `DocumentIndexer`,
      and `PipelineOrchestrator` are all instantiated (or injected) correctly via dependencies
    - Verify SSE queue is shared between orchestrator and `/api/sync/stream` endpoint
    - _Requirements: 6.2, 6.3_

  - [ ] 21.2 Verify `.env.example` is complete and accurate
    - Cross-check every `Settings` field has a corresponding entry in `.env.example`
    - Confirm no real credentials are present
    - _Requirements: 12.4_

  - [ ] 21.3 Write `README.md` in the project root
    - Setup and run instructions (Python venv, `pip install`, Playwright install, `npm install`,
      `.env` setup, `uvicorn` start, `npm run dev` start)
    - Short architecture overview (diagram or prose)
    - Three or four most interesting design decisions with reasoning
    - Short note on improvements / open questions
    - _Requirements: (deliverable)_

  - [ ] 21.4 Add `.gitignore` entries
    - `.env`, `data/files/`, `chroma_db/`, `__pycache__/`, `.pytest_cache/`,
      `node_modules/`, `dist/`, `*.pyc`

---

## Notes

- Tasks marked with `*` are optional and can be skipped for a faster MVP
- Each task references specific requirements for traceability
- Checkpoints (tasks 9, 12, 20) are integration gates — run all tests before proceeding past each
- Property-based tests use Hypothesis; configure the `"ci"` profile in `conftest.py` (task 18.3)
  before running any `*` test tasks
- All 19 correctness properties from the design document are covered by PBT sub-tasks
- Frontend tests use Vitest + React Testing Library; set up in task 19.1 before task 19.2
- The backend language is Python 3.11+; the frontend is TypeScript + React 18 + Vite


## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["2.1", "3.1"] },
    { "id": 1, "tasks": ["2.2", "2.3", "3.2", "13.2"] },
    { "id": 2, "tasks": ["3.3", "3.4", "5.1", "13.1", "13.3"] },
    { "id": 3, "tasks": ["4.1", "5.2", "11.1", "11.2"] },
    { "id": 4, "tasks": ["4.2", "4.3", "4.4", "6.1", "7.1", "8.1", "11.3", "11.7"] },
    { "id": 5, "tasks": ["6.2", "6.3", "6.4", "7.2", "7.3", "8.2", "10.1", "11.4", "11.5", "11.6"] },
    { "id": 6, "tasks": ["10.2", "10.3", "11.8", "11.9", "11.10", "11.11", "11.12", "14.1", "14.2", "18.3"] },
    { "id": 7, "tasks": ["14.3", "18.1", "18.2"] },
    { "id": 8, "tasks": ["15.1", "16.1", "17.1", "19.1"] },
    { "id": 9, "tasks": ["15.2", "19.2"] },
    { "id": 10, "tasks": ["21.1", "21.2", "21.3", "21.4"] }
  ]
}
```
