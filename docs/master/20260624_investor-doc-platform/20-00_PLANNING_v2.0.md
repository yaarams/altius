<!-- PLANNING RESUME STATE
planning_skill_version: 1.3.0
current_phase: Phase 4 (Synthesis) — complete, pending user approval
phases_completed: [0, 1, 2, 3]
qa_rounds_completed: 2
decisions_made: 10
open_questions: 2
last_updated: 2026-06-24
context_note: v2.0 folds formal design.md. Stack: Playwright(async) + FastAPI + SQLite(SQLAlchemy+Alembic) + ChromaDB(local) + pdfplumber + Gemini(gemini-2.x + text-embedding-004, OVERRIDES design's OpenAI per user D-008) + React/TS/Vite/Tailwind. Pipeline: Crawl→Classify→Extract→Index. 19 correctness properties + Hypothesis PBT. CONF-2 open: design says OpenAI, user chose Gemini (kept Gemini).
-->

# Implementation Plan: Investor Document Platform

**Version:** v2.0
**Created:** 2026-06-24
**Updated:** 2026-06-24 (folded formal design.md)
**Planning Skill:** my-planning-master v1.3
**Status:** Superseded by v2.1 (recon findings folded in — JSON API crawler + external_file_id idempotency)
**Complexity Tier:** Complex
**Estimated Total Effort:** L–XL (~24–34 h, +Indexer +19 PBT properties)

## Input Documents
- Spec (narrative): `ASSIGNMENT.md`
- **PRD (authoritative, EARS): `.kiro/specs/investor-document-platform/requirements.md`** — 12 requirements
- **Design (authoritative): `.kiro/specs/investor-document-platform/design.md`** — components, schema, 19 correctness properties
- Decisions log: `20-50_DECISIONS_LOG.md`
- Previous plans: `v1.0`, `v1.1`, `v1.2` (all Superseded)

## Scope Alignment

### In Scope
- Crawler (Playwright async): login, walk deals, idempotent download. (R1–R3)
- Classifier (heuristic→LLM hybrid): 3 labels + confidence; <0.75 low_confidence surfaced. (R4)
- Extractor (pdfplumber): fund/date/current value, variant labels, atomic all-or-nothing. (R5, R10)
- Indexer (ChromaDB): chunk + embed reports & statements for RAG. (R8.7)
- DB (SQLite): files + statements lifecycle, queryable, Alembic auto-migrate. (R11)
- Frontend (React/TS/Vite/Tailwind): sync staged status, holdings, chat (grounded+cited), files. (R6–R9)
- Config: env-only secrets, `.env.example`, fail-fast. (R12)

### Out of Scope
- Non-PDF formats. Auth/observability/rate-limits/prod hardening. Visual polish.

### Constraints (PRD + design)
- Live crawler end-to-end. Idempotency UNIQUE `(portal_url, file_name)`; skip downloaded/extracted, retry failed.
- Holdings: latest per fund in single normalized SQL. Chat: retrieval-bounded (top_k≤20), real citations, honest OOC.
- No secrets committed. Extraction atomic (no partial rows). Startup fail-fast on missing env / failed migration.

### Env vars
`PORTAL_USER`, `PORTAL_PASSWORD`, `GEMINI_API_KEY`, `DATABASE_URL` (sqlite path). Real values in `.env` (gitignored); placeholders in `.env.example`.
*Note: design.md names `PORTAL_USERNAME`; plan keeps `PORTAL_USER` to match existing `.env`.*

### Repos Involved
- Primary (only): `/Users/yaaracohen/Development/altius` (greenfield).

## Architecture Decisions

### ADR-001: By-risk task decomposition — *Accepted*
Crawler → Classify+Extract → Index+RAG+Frontend. Riskiest unknown (live portal) fails fast.

### ADR-002: Playwright (async) crawler — *Accepted* (fallback httpx after recon)
Design rationale: reliable on SPAs, built-in download capture via network interception, context managers avoid leaks. Recon unblocked (creds in `.env`).

### ADR-003: Gemini for all LLM steps — *Accepted; OVERRIDES design.md OpenAI (see CONF-2)*
- **Context:** design.md specifies OpenAI (gpt-4o-mini/gpt-4o). User confirmed Gemini (D-008), only `GEMINI_API_KEY` available.
- **Decision:** `gemini-2.x` for classifier ambiguous-case calls + chat synthesis; Gemini JSON mode for extraction assist. Temperature 0.0 for classifier determinism.
- **Consequences:** Single vendor/key. One LLM wrapper `backend/llm/gemini.py` isolates provider → swap to OpenAI is a one-file change if CONF-2 reverses.

### ADR-004: ChromaDB vector store + Gemini embeddings — *Accepted (was pgvector; design.md → ChromaDB)*
- **Decision:** ChromaDB local-persistent, single collection `investor_documents`, doc id `{file_id}_{chunk_index}` for idempotent upsert. Embeddings via Gemini `text-embedding-004` (768-d; design used OpenAI text-embedding-3-small 1536-d — dimension change noted, ChromaDB is dim-agnostic per collection).
- **Consequences:** No DB infra for vectors; embedded in process; persistent across restarts.

### ADR-005: SQLite + SQLAlchemy + Alembic — *Accepted (was Postgres/pgvector; design.md → SQLite)*
- **Decision:** SQLite single-file DB. SQLAlchemy models, Alembic migrations auto-applied on startup. Schema per design.md.
- **Consequences:** Zero infra (no docker-compose Postgres). pgvector no longer needed (ChromaDB handles vectors). Easy swap to Postgres later.

### ADR-006: pdfplumber primary — *Accepted (was pymupdf; design.md → pdfplumber)*
Best-in-class table extraction (needed for CAS). Raw-text fallback. No external service.

### ADR-007: Idempotency key = (portal_url, file_name) — *Accepted*
UNIQUE (portal_url, file_name) skip key (R3.1/R11.3). Skip if status downloaded/extracted; **retry if failed** (R3.6). Pre-download record (R2.3).

### ADR-008: Separate Indexer subsystem + 4-stage pipeline — *Accepted (design.md)*
Pipeline Crawler→Classifier→Extractor→**Indexer**. SSE stages: `Crawling`, `Classifying`, `Extracting`, `Indexing`. Indexer failures non-fatal (mark `indexed=0`, re-index next sync).

### ADR-009: Single-flight + startup guards — *Accepted*
Module-level `asyncio.Lock` + `_pipeline_running` flag; concurrent trigger → **HTTP 409** (R6.6). Missing env / failed migration → log all + exit code 1 before binding port (R11.5/R12.5/R12.6).

### ADR-010: Property-based testing (Hypothesis) — *Accepted (design.md)*
19 correctness properties (design.md §Correctness Properties). PBT via Hypothesis, ≥100 examples/property, `ci` profile. Tag: `# Feature: investor-document-platform, Property {N}`.

## Codebase Context
Greenfield. Structure per design.md:

```
altius/
  backend/
    api/
      main.py            # app factory, lifespan (env+migrate guard), middleware, router mount
      dependencies.py    # DB session, settings injection
      schemas.py         # Pydantic request/response (HoldingRow, ChatResponse, SyncProgressEvent, ...)
      routers/{sync.py, holdings.py, chat.py, files.py}
    config.py            # pydantic-settings; reads PORTAL_USER/PORTAL_PASSWORD/GEMINI_API_KEY/DATABASE_URL; fail-fast
    llm/gemini.py        # Gemini wrapper (chat + JSON mode) — provider isolation
    crawler/portal_crawler.py    # PortalCrawler: run/_login/_enumerate_deals/_enumerate_files/_download_file
    classifier/document_classifier.py  # DocumentClassifier: classify/_heuristic_classify/_llm_classify
    extractor/statement_extractor.py   # StatementExtractor: extract/_parse_pdf/_extract_* ; canonical repr
    indexer/document_indexer.py        # DocumentIndexer: index_file/index_all_pending/_chunk_text
    orchestrator.py      # pipeline runner; single-flight; asyncio.Queue → SSE events
    db/{models.py, session.py}         # SQLAlchemy: files, statements
    alembic/             # migrations (auto-applied on startup)
  frontend/
    src/
      App.tsx            # router
      components/{SyncControl.tsx, Layout.tsx}
      pages/{HoldingsPage.tsx, ChatPage.tsx, FilesPage.tsx}
      hooks/{useSyncStream.ts, useHoldings.ts}
      api/client.ts
      types/index.ts
    (Vite + TypeScript + Tailwind)
  tests/                 # pytest + Hypothesis (19 properties) + example tests
  .env / .env.example / .gitignore / README.md
```

### DB schema (design.md, SQLite)
- `files`(id PK, portal_url, deal_name, file_name, local_path, download_ts ISO-UTC, status[pending|downloaded|extracted|failed], classification[capital_account_statement|report|other|unclassified], confidence, low_confidence 0|1, extraction_error, indexed 0|1, created_at, **UNIQUE(portal_url, file_name)**)
- `statements`(id PK, file_id FK ON DELETE CASCADE, fund_name, statement_date ISO date, current_value TEXT[decimal-preserving]); INDEX(fund_name, statement_date)

## Implementation Plan

### TASK 1 — Crawler + infra (highest risk) · ~9–11 h · deps: none

#### T1.1 Infra + config + startup guards — *R11.5, R12; Property 14*
- **Files:** `backend/pyproject.toml`, `backend/api/main.py`, `backend/config.py`, `.env.example`, `.gitignore`, `backend/alembic/`
- **Approach:** FastAPI app factory + lifespan; pydantic-settings reads 4 env vars, **on missing/empty: log single message naming every missing var, exit code 1 before binding** (R12.5/6, Prop 14); lifespan runs Alembic, **migration failure → log name, exit 1** (R11.5). SQLite path from `DATABASE_URL`.
- **Acceptance:** missing vars → named error + exit 1; migrations applied at boot; `/health` 200.
- **Verify:** Hypothesis Prop 14 (any subset missing → exit); boot with bad migration → exit 1.

#### T1.2 DB schema + session — *R11; Property 13*
- **Files:** `backend/db/models.py`, `backend/db/session.py`, `backend/alembic/versions/0001_init.py`
- **Approach:** SQLAlchemy `files` + `statements` per design schema; **UNIQUE(portal_url, file_name)**; CASCADE; index(fund_name, statement_date).
- **Acceptance:** tables match design; unique constraint enforced.
- **Verify:** Hypothesis Prop 13 (dup (url,name) → IntegrityError).

#### T1.3 Portal login + session resilience — *R1; Error-handling §Auth*
- **Files:** `backend/crawler/portal_crawler.py` (`_login`)
- **Approach:** Playwright async chromium; creds from settings; bad creds → abort + SSE `error` `"Authentication failed: invalid credentials"`, no downloads (R1.2); session expiry detected via redirect-to-login → retry `_login()` **up to 3×**, resume from last completed deal; 3rd fail → SSE error (R1.3). Credentials never logged.
- **Acceptance:** good→authed; bad→error no files; expiry→resume; 3-fail→error event.
- **Verify:** integration vs live portal; bad-creds example test; mocked expiry.

#### T1.4 Walk deals + enumerate + pre-record — *R2; Error-handling §Crawler*
- **Files:** `backend/crawler/portal_crawler.py` (`_enumerate_deals`/`_enumerate_files`), `backend/orchestrator.py`
- **Approach:** enumerate deals → per deal enumerate files; **record (deal_name, file_name, portal_url) before any download** (R2.3/2.5); deal-page load fail → log name+status, skip, continue (R2.4); emit `deal_discovered` events.
- **Acceptance:** all files pre-recorded; one bad deal doesn't abort.
- **Verify:** rows vs manual browse; simulate deal failure.

#### T1.5 Idempotent download — *R3; Properties 1, 2, 3*
- **Files:** `backend/crawler/portal_crawler.py` (`_download_file`), `backend/orchestrator.py`
- **Approach:** before download query (portal_url,file_name): **skip if downloaded/extracted (Prop 1), retry if failed (Prop 2)**; success → status `downloaded` + non-null UTC `download_ts` (Prop 3); fail → status `failed`, log, continue (R3.4). Emit `file_downloaded`/`file_skipped` events.
- **Acceptance:** 2nd sync → 0 new for downloaded/extracted; failed retried.
- **Verify:** Hypothesis Props 1/2/3.

#### T1.6 Orchestrator: single-flight + staged SSE — *R6; Property 10*
- **Files:** `backend/orchestrator.py`, `backend/api/routers/sync.py`, `backend/api/schemas.py`
- **Approach:** `POST /api/sync/trigger` → if running **HTTP 409** (R6.6, Prop 10) else start background task (lock + `_pipeline_running`, cleared in `finally`); `GET /api/sync/stream` `StreamingResponse` + `asyncio.Queue` emits `data: {json}\n\n` for stages `Crawling|Classifying|Extracting|Indexing` (R6.3) then terminal `complete`(summary) / `error`(stage,msg), then close (R6.4/6.5).
- **Acceptance:** concurrent trigger → 409; staged events + summary; terminal closes stream.
- **Verify:** Hypothesis Prop 10; SSE manual; force fail.

### TASK 2 — Classifier + Extractor · ~8–10 h · deps: T1. ⟂ partly T3.5

#### T2.1 PDF parsing (pdfplumber) — *R10; Property 11*
- **Files:** `backend/extractor/statement_extractor.py` (`_parse_pdf`), `PageContent`
- **Approach:** pdfplumber → per-page text + tables; **all N pages, no truncation** (R10.2, Prop 11); unopenable → record `extraction_error`, status `failed`, no extraction (R10.4).
- **Acceptance:** multi-page complete; corrupt → recorded failure.
- **Verify:** Hypothesis Prop 11 (N-page coverage); corrupt-file example test.

#### T2.2 Classifier (hybrid) — *R4; Properties 4, 5, 6*
- **Files:** `backend/classifier/document_classifier.py`, `ClassificationResult`
- **Approach:** `_heuristic_classify` first (filename + structure cues; **early-return if confidence ≥0.90**); else `_llm_classify` via Gemini (first ~2000 chars, temp 0.0, JSON `{label,confidence,reasoning}`, retry once on bad JSON → else `unclassified`/0.0). Output invariants: label∈{cas,report,other,unclassified}, confidence∈[0,1], **low_confidence ⇔ confidence<0.75** (Prop 4). **Skip if already classified** incl `unclassified` (R4.8, Prop 5). Sync summary `low_confidence_count` = DB low_confidence count this run (Prop 6).
- **Acceptance:** labeled right; borderline flagged; no re-classify; summary count matches DB.
- **Verify:** Hypothesis Props 4/5/6.

#### T2.3 Statement extractor — *R5, R10.3; Properties 7, 8, 12*
- **Files:** `backend/extractor/statement_extractor.py` (`_extract_fund_name/_extract_statement_date/_extract_current_value`), canonical formatter
- **Approach:** regex + Gemini-JSON hybrid; current-value variant labels (case-insensitive, whitespace-norm): "ending capital balance","closing nav","partner's capital — ending"/"- ending","net asset value","ending balance","closing balance","partners' capital, end of period" (R5.2); adjacent numeric (right col / right-justified), strip currency+commas → Decimal. **Atomic: all-or-nothing** — any required field missing → no `statements` row, write `files.extraction_error` (Prop 7, R5.3/5.4/10.5). Stored fields == extracted (Prop 8). Canonical round-trip equivalent (Prop 12, R10.3).
- **Acceptance:** value correct across variants; failures atomic; round-trip holds.
- **Verify:** Hypothesis Props 7/8/12; per-variant example tests; date-format + fund-normalization unit tests.

#### T2.4 Persist + holdings query — *R5.5/5.6, R7, R11.4; Property 9*
- **Files:** `backend/db/models.py`, `backend/api/routers/holdings.py`, `backend/api/schemas.py`
- **Approach:** statements rows linked to file (CASCADE). `GET /api/holdings` = **single SQL**, latest per fund with `lower(trim(fund_name))` normalization + `MAX(statement_date)` + `MAX(id)` tie-breaker (design query, Prop 9). Response `HoldingRow{fund_name, current_value "$1,234,567.89", statement_date "March 31, 2025", file_id}`.
- **Acceptance:** one row/normalized-fund, latest date+value; formatted; single query.
- **Verify:** Hypothesis Prop 9 (variants/dupes/case); endpoint formatting unit tests.

#### T2.5 Wire classify+extract into pipeline, idempotent — *R3.5*
- **Files:** `backend/orchestrator.py`
- **Approach:** per new file → classify → if `capital_account_statement` extract; skip already-`extracted` (R3.5); set `extracted` on success.
- **Acceptance:** 2nd sync → 0 re-classify/re-extract.
- **Verify:** run twice; 0 new statements.

### TASK 3 — Indexer + RAG Chat + Frontend · ~10–12 h · deps: T3.1–3.4 need T2; T3.5 ⟂ T2

#### T3.1 Indexer → ChromaDB — *R8.7; Property 17*
- **Files:** `backend/indexer/document_indexer.py`
- **Approach:** `index_all_pending` over downloaded PDFs (reports + CAS); `_chunk_text` sliding window **800-token / 100 overlap**, prefer paragraph breaks; metadata file_id, file_name, deal_name, document_type, statement_date, chunk_index; embed Gemini `text-embedding-004` batched 100; upsert ChromaDB `investor_documents` id `{file_id}_{chunk_index}` (idempotent); set `indexed=1`. Failures non-fatal → `indexed=0`, re-index next sync. Emit `Indexing` stage events.
- **Acceptance:** chunked+embedded; new docs retrievable post-sync; re-index idempotent.
- **Verify:** Hypothesis Prop 17 (added doc retrievable).

#### T3.2 Retrieval + grounded chat — *R8; Properties 15, 16*
- **Files:** `backend/indexer` query helper, `backend/llm/gemini.py`, `backend/api/routers/chat.py`, `backend/api/schemas.py`
- **Approach:** `POST /api/chat` → embed question (Gemini) → ChromaDB `query(top_k=20)` **bounded ≤20** (R8.8, Prop 15) → prompt = passages + citation metadata → Gemini synthesis (not whole-corpus). Every grounded answer ≥1 citation `{file_name, period, file_url=/api/files/{id}/download}` (R8.3/8.4, Prop 16). No passages → 200 `not_found:true` (R8.5). Cross-quarter synthesis supported (R8.6). 60s timeout → 504; vector store down → 503; LLM error → 502.
- **Acceptance:** sample Qs cited; dividend Q → not_found; cross-quarter pulls multiple sources.
- **Verify:** Hypothesis Props 15/16; 5 sample questions integration; OOC example test.

#### T3.3 Frontend scaffold + sync control — *R6.1/6.2*
- **Files:** `frontend/src/App.tsx`, `components/Layout.tsx`, `components/SyncControl.tsx`, `hooks/useSyncStream.ts`, `api/client.ts`, `types/index.ts`
- **Approach:** React/TS/Vite/Tailwind; router; `SyncControl` in `Layout` on **all pages**; click → `POST /api/sync/trigger`, disable button, open `EventSource /api/sync/stream`; events update status ("Crawling…"); `complete` → trigger Holdings refresh via context + re-enable; `error` → show msg + re-enable; **409 → inline "Sync already in progress", button not disabled**.
- **Acceptance:** nav works; staged status; 409 inline; refresh on complete; no page reload.
- **Verify:** Vitest (disable/re-enable, 409 message); manual sync.

#### T3.4 Holdings page — *R7; Property (uses Prop 9 data)*
- **Files:** `frontend/src/pages/HoldingsPage.tsx`, `hooks/useHoldings.ts`
- **Approach:** `GET /api/holdings` on mount; refresh on sync `complete` via shared context (R7.5); empty-state CTA → run sync (R7.4); failed-extraction value cell → "—"; currency formatted (R7.6).
- **Acceptance:** matches DB; empty-state; live refresh; "—" placeholders.
- **Verify:** Vitest (currency, empty-state); manual vs DB.

#### T3.5 Chat page — *R8.4*
- **Files:** `frontend/src/pages/ChatPage.tsx`
- **Approach:** textarea (Enter submit, Shift+Enter newline) → `POST /api/chat`; loading indicator; answer + inline citation chips linking `/api/files/{id}/download`; `not_found:true` → "not available in documents"; 60s client timeout → "Request timed out" + retry.
- **Acceptance:** citations clickable → open source; OOC message; timeout handled.
- **Verify:** Vitest (citation chips, not_found, timeout); sample Q manual.

#### T3.6 Files page (bonus) — *R9; Properties 18, 19*
- **Files:** `frontend/src/pages/FilesPage.tsx`, `backend/api/routers/files.py`
- **Approach:** `GET /api/files` lists **all** records (Prop 18): file_name, deal_name, document_type(null if pending), confidence(null if pending), low_confidence, download_date, status; default sort download_date desc; column sort on document_type (R9.5); **amber "Low confidence" pill iff confidence<0.75** (Prop 19, R9.3); "Open" → `GET /api/files/{id}/download` new tab (R9.4).
- **Acceptance:** all listed w/ all fields; sort works; badge exactly <0.75; open works.
- **Verify:** Hypothesis Props 18/19; Vitest badge threshold; manual sort/open.

## Parallel Execution Groups
```
Group A (serial, risk-first): T1.1→T1.2→T1.3→T1.4→T1.5→T1.6
Group B (after files):        T2.1→T2.2→T2.3→T2.4→T2.5
Group C: T3.3 ⟂ B; T3.1→T3.2 need T2; T3.4 needs T2.4; T3.5 needs T3.2; T3.6 needs T2.2
Critical path: T1.1→T1.2→T1.3→T1.4→T1.5→T2.1→T2.2→T2.3→T2.4→T3.4
```

## Testing Strategy (design.md dual approach)
- **Property-based (Hypothesis, ≥100 ex, `ci` profile):** Properties 1–19 mapped to tasks above. Tag `# Feature: investor-document-platform, Property {N}`.
- **Example/unit:** extractor per-variant labels, fund normalization, date formats, empty PDF; API (currency format, empty holdings, files sort, 409 mock, chat schema); frontend Vitest (sync button states, 409 msg, currency, badge threshold, citation chips, not_found).
- **Integration:** live portal end-to-end sync; cross-quarter chat multi-citation; holdings correct post-sync.
- **NOT PBT (example/integration):** portal login (live), SSE frequency, chat 60s timeout, cross-quarter semantic quality.

## Traceability Matrix (PRD → tasks → properties)
| PRD Req | Task(s) | Property | Verify |
|---|---|---|---|
| R1 Auth + expiry + no-secret | T1.1, T1.3 | P14 | bad-creds, expiry, env |
| R2 Discovery + pre-record | T1.4 | — | rows before download |
| R3 Idempotent download | T1.5, T2.5 | P1,P2,P3,P13 | sync twice, retry failed |
| R4 Classification + low_confidence | T2.2, T3.6 | P4,P5,P6,P19 | flags, summary, no re-classify |
| R5 Extraction variants + atomic | T2.3, T2.4 | P7,P8 | per-variant, atomic |
| R6 Sync staged + single-flight | T1.6, T3.3 | P10 | SSE stages, 409 |
| R7 Holdings latest/fund + empty/currency | T2.4, T3.4 | P9 | normalized query, empty-state |
| R8 Chat grounded+cited+OOC+bounded | T3.1, T3.2, T3.5 | P15,P16,P17 | 5 Qs, top_k≤20, citations |
| R9 Files page (bonus) | T3.6 | P18,P19 | list-all, sort, badge |
| R10 PDF parse + round-trip | T2.1, T2.3 | P7,P11,P12 | multi-page, corrupt, round-trip |
| R11 DB schema/unique/single-query/migrate | T1.1, T1.2, T2.4 | P9,P13 | constraints, EXPLAIN, boot |
| R12 Env secrets + fail-fast | T1.1 | P14 | unset var → exit 1 |

## Risk Register
| Risk | L | I | Mitigation |
|---|---|---|---|
| R1: Portal selectors fragile/unknown | M | H | Recon-then-code (creds in .env); centralize selectors; screenshot on failure. |
| R2: Heterogeneous layouts → wrong current_value | M | H | pdfplumber tables + variant-label list + Gemini assist; atomic failures; round-trip (P12) + spot-check. |
| R3: RAG hallucination / weak citations | M | H | top_k≤20 retrieval-only prompt; cite file+period (P16); empty → not_found. |
| R4: Session expiry mid-crawl | M | M | Re-auth ≤3× + resume (R1.3); pre-recorded rows. |
| R5: Gemini JSON drift on messy PDFs | M | M | JSON mode + retry-once + schema validation; atomic no-partial; spot-check. |
| R6: Concurrent sync corrupts state | L | M | Single-flight lock + 409 (P10). |
| R7: Embedding dim change (768 vs design 1536) | L | L | ChromaDB collection dim-agnostic; fix collection at create; document in README. |

### Rollback Strategy
- Greenfield → git revert per task branch. Data: delete SQLite file + ChromaDB dir; idempotent re-sync repopulates. Alembic downgrade available.

## Open Questions
- **CONF-2:** RESOLVED 2026-06-24 — user confirmed **keep Gemini**. design.md's OpenAI superseded.
- Playwright vs HTTP confirmed after first live recon (creds in .env → first T1.3 action).

## Version History
| Version | Date | Changes |
|---|---|---|
| v1.0 | 2026-06-24 | Initial. By-risk 3-task split. |
| v1.1 | 2026-06-24 | Folded EARS PRD (12 reqs); idempotency conflict resolved; full traceability. |
| v1.2 | 2026-06-24 | Gemini pivot; env vars renamed. |
| v2.0 | 2026-06-24 | **Folded formal design.md (MAJOR):** Postgres/pgvector→SQLite+ChromaDB; pymupdf→pdfplumber; added Indexer subsystem (4-stage pipeline, Indexing SSE stage); design module layout + exact `/api/*` paths; 19 correctness properties + Hypothesis PBT; status enum `pending|...`+`unclassified`+`indexed`; holdings normalized query w/ tie-breaker; heuristic ≥0.90 early-return; chat top_k=20; 60s timeout + HTTP 409/502/503/504; error-handling tables. Kept Gemini over design's OpenAI (CONF-2). |

## Orchestrator Execution Config
- **Mode:** New System · **Governance:** Lightweight · **Agents:** 3 (T3 frontend ⟂ T2)
- **Critical Path:** T1.1→T1.2→T1.3→T1.4→T1.5→T2.1→T2.2→T2.3→T2.4→T3.4
- **Rollback Trigger:** crawler can't authenticate after recon → escalate (blocks all)
- **Known Gotchas:** pre-record before download; skip downloaded/extracted but retry failed; extraction atomic (no partial rows); top_k≤20; citations traceable; never fabricate OOC; validate Gemini JSON (retry once); Indexer failures non-fatal; secrets env-only + never logged.

## Definition of Ready (DoR)
### Mandatory
- [x] Every PRD req maps to ≥1 task (12/12) + property coverage (19/19)
- [x] Every task names specific files (design module layout)
- [x] Every task has acceptance criteria + verify (property or example)
- [x] Scope in/out explicit
- [x] ADRs documented (ADR-001..010)
- [x] Dependencies + parallel groups mapped
- [x] Plan approved by user
- [x] CONF-2 (Gemini vs OpenAI) confirmed → Gemini
### Standard + Complex
- [x] Testing strategy (PBT 19 properties + example + integration)
- [x] Risk register + rollback
- [x] Traceability matrix (PRD + properties)
- [x] Codebase context (design module layout + schema)
### Complex
- [x] ADRs (none for SK promotion — local take-home)
- [x] Single-repo
- [x] Security/perf: secrets env-only + never logged + fail-fast; RAG-grounding = core correctness

### Approval Record
- Approved by: user (yaara.yacv@gmail.com)
- Approved at: 2026-06-24
- Method: AskUserQuestion response ("Approve")
- Complexity Tier confirmed: Complex
