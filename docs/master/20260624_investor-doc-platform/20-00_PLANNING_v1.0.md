<!-- PLANNING RESUME STATE
planning_skill_version: 1.3.0
current_phase: Phase 4 (Synthesis) — complete, pending user approval
phases_completed: [0, 1, 2, 3]
qa_rounds_completed: 1
decisions_made: 5
open_questions: 2
last_updated: 2026-06-24
context_note: Greenfield take-home. By-risk 3-task split locked. Stack: Playwright + FastAPI + Postgres/pgvector + Claude + Voyage embeddings + React/Vite. Portal recon blocked on creds.
-->

# Implementation Plan: Investor Document Platform

**Version:** v1.0
**Created:** 2026-06-24
**Planning Skill:** my-planning-master v1.3
**Status:** Superseded by v1.1 (folded in formal PRD `.kiro/.../requirements.md`)
**Complexity Tier:** Complex (greenfield, live-portal automation, RAG, 3 frontend pages, ~17 tasks, high crawler risk)
**Estimated Total Effort:** L–XL (~20–30 h)

## Input Documents
- Spec: `ASSIGNMENT.md` (no separate PRD/research — assignment IS the spec)
- Decisions log: `20-50_DECISIONS_LOG.md`

## Scope Alignment

### In Scope
- Crawler: live login to `fo1.altius.finance`, walk deal hierarchy, idempotent download of all files.
- Classifier: capital-account-statement / report / other + confidence; low-confidence surfaced not hidden.
- Extractor: per statement → fund name, statement date, current value (heterogeneous field names).
- Postgres (+pgvector): files & types tracked, extracted statement data queryable.
- Frontend: sync action (live status), chat page (grounded RAG w/ citations), holdings page.
- Bonus: files page.

### Out of Scope
- Non-PDF formats (FAQ: PDF is enough).
- Auth, observability, rate limits, production hardening (explicitly not graded).
- Frontend visual polish (not graded).

### Constraints
- Submitted system must run the **live** crawler end-to-end (they sync at eval). Stub/cache allowed for dev only.
- Sync must be **idempotent**: no re-download, no dup rows, no re-extraction of known files.
- Holdings: **latest statement per fund**.
- Chat: real citations (file + reporting period), traceable to source; out-of-corpus answered honestly.

### Repos Involved
- Primary (only): `/Users/yaaracohen/Development/altius` (greenfield).

## Architecture Decisions

### ADR-001: By-risk task decomposition
- **Status:** Accepted
- **Context:** Three areas of unequal risk: live un-inspectable portal, heterogeneous-PDF extraction, RAG+UI.
- **Decision:** Sequence tasks by risk — crawler first, extraction second, RAG+frontend third.
- **Consequences:** Riskiest unknown fails fast. T2/T3 can partly parallelize once T1 lands files.
- **Promote to SharedKnowledge:** No.

### ADR-002: Playwright for crawler
- **Status:** Accepted (fallback to httpx after recon)
- **Context:** Portal has no API, layout unknown, likely JS-rendered SPA. Defend-the-choice expected.
- **Decision:** Drive a real headless browser (Playwright, Python). Reverse-engineered HTTP only if recon proves server-rendered + stable endpoints.
- **Consequences:** Robust to unknown portal + login flow; heavier/slower (acceptable, on-demand sync).
- **Promote:** No.

### ADR-003: Claude + Postgres/pgvector
- **Status:** Accepted
- **Context:** Need classify/extract/chat reasoning + a vector store; want minimal infra.
- **Decision:** Claude for all LLM steps. Single Postgres holds relational tables + pgvector embeddings.
- **Consequences:** One datastore, simpler ops. Vector + SQL joins in one place.
- **Promote:** No.

### ADR-004: Voyage embeddings (local fallback)
- **Status:** Accepted
- **Context:** Anthropic has no embeddings API.
- **Decision:** `voyage-3` behind an `Embedder` interface; `sentence-transformers` local impl as keyless fallback.
- **Consequences:** Swap providers without touching retrieval code. Documented tradeoff in README.
- **Promote:** No.

## Codebase Context
Greenfield. No existing patterns. Proposed structure:

```
altius/
  backend/
    app/
      main.py              # FastAPI app + router mount + CORS
      config.py            # pydantic-settings, reads .env
      db/
        session.py         # engine, session, pgvector init
        models.py          # SQLAlchemy: Deal, File, Statement, ReportChunk
      crawler/
        portal.py          # Playwright driver: login, walk, list files
        sync.py            # orchestration: idempotent download loop
        downloader.py      # fetch + content-hash + dedupe
      classifier/
        classify.py        # Claude/hybrid → label + confidence
      extractor/
        pdf.py             # PDF → text (pymupdf/pdfplumber)
        statement.py       # Claude structured extract (fund/date/value)
      rag/
        embed.py           # Embedder interface (Voyage | local)
        ingest.py          # chunk reports → embed → pgvector
        retrieve.py        # similarity + metadata filter
        chat.py            # Claude grounded answer + citations
      api/
        sync_routes.py     # POST /sync, GET /sync/status (SSE)
        holdings_routes.py # GET /holdings
        chat_routes.py     # POST /chat
        files_routes.py    # GET /files, GET /files/{id} (open)
    pyproject.toml
  frontend/
    src/{App.tsx, api.ts, pages/{Holdings,Chat,Files}.tsx, components/SyncButton.tsx}
  docker-compose.yml       # postgres + pgvector
  .env.example
  README.md
```

## Implementation Plan

### TASK 1 — Crawler (highest risk)
**Effort:** ~8–10 h · **Dependencies:** none

#### T1.1 Project + infra skeleton
- **Files:** `backend/pyproject.toml`, `backend/app/main.py`, `backend/app/config.py`, `docker-compose.yml`, `.env.example`
- **Approach:** FastAPI app, pydantic-settings, docker-compose with `pgvector/pgvector` image. Health route.
- **Acceptance:** `docker compose up` + `uvicorn` boots; `GET /health` 200.
- **Verify:** curl /health.

#### T1.2 DB schema + session
- **Files:** `backend/app/db/session.py`, `backend/app/db/models.py`
- **Approach:** SQLAlchemy models — `Deal`, `File`(id, deal_id, name, source_url, content_hash UNIQUE, file_type, classify_confidence, downloaded_at, local_path), `Statement`(file_id, fund_name, statement_date, current_value, raw_field_label), `ReportChunk`(file_id, period, text, embedding vector). Enable pgvector extension.
- **Acceptance:** Tables create; `content_hash` unique constraint enforced.
- **Verify:** alembic/create_all + psql `\dt`.

#### T1.3 Portal login (Playwright)
- **Files:** `backend/app/crawler/portal.py`
- **Approach:** Launch chromium, navigate `fo1.altius.finance`, fill creds from env, submit, assert logged-in state. Raise typed `LoginError` on bad creds.
- **Acceptance:** Valid creds → authenticated session; bad creds → `LoginError` (no silent pass).
- **Verify:** integration run vs live portal (needs creds — see Risk R1).

#### T1.4 Walk deal hierarchy + enumerate files
- **Files:** `backend/app/crawler/portal.py`
- **Approach:** From dashboard, list deals; per deal list files (name + download URL/handle). Return structured `[Deal{files[]}]`.
- **Acceptance:** Returns ≥1 deal, each with file list matching portal UI.
- **Verify:** snapshot count vs manual portal browse.

#### T1.5 Idempotent download
- **Files:** `backend/app/crawler/downloader.py`, `backend/app/crawler/sync.py`
- **Approach:** For each file: download bytes, sha256 hash; if hash exists in `File` → skip (no re-download, no dup row, no re-extract flag). Else save to disk + insert row.
- **Acceptance:** Re-running sync downloads 0 new files, inserts 0 rows on 2nd pass.
- **Verify:** run sync twice, assert row count stable + log "skipped N".

#### T1.6 Sync endpoint + live status + honest failure
- **Files:** `backend/app/api/sync_routes.py`
- **Approach:** `POST /sync` kicks background job; `GET /sync/status` streams progress via SSE (logging in / N files found / downloaded / done|failed). Surface LoginError + per-file errors.
- **Acceptance:** UI can show progress without refresh; bad creds → visible failure status.
- **Verify:** trigger sync, observe SSE events; force bad creds → error event.

### TASK 2 — Classify + Extract (heterogeneous PDFs)
**Effort:** ~6–8 h · **Dependencies:** T1 (needs files on disk + rows). T2 ⟂ partly with T3.3.

#### T2.1 PDF → text
- **Files:** `backend/app/extractor/pdf.py`
- **Approach:** pymupdf primary, pdfplumber fallback for tables. Return text + per-page.
- **Acceptance:** Extracts text from sample statement + report PDFs.
- **Verify:** unit test on fixtures.

#### T2.2 Classifier
- **Files:** `backend/app/classifier/classify.py`
- **Approach:** Hybrid — cheap heuristics (keywords: "capital account", "ending balance" vs narrative length) then Claude for ambiguous. Return `label ∈ {capital_account, report, other}` + `confidence`. Below threshold → `needs_review` flag on File (visible, not bucketed).
- **Acceptance:** Sample files labeled correctly; low-confidence flagged.
- **Verify:** run on corpus, eyeball files page.

#### T2.3 Statement extractor
- **Files:** `backend/app/extractor/statement.py`
- **Approach:** Claude structured output (JSON) → `fund_name`, `statement_date`, `current_value` + the raw field label it matched ("ending capital balance"/"closing NAV"/"partner's capital — ending"). Prompt lists synonyms. Parse failure → record error, mark `needs_review`.
- **Acceptance:** current_value correct across ≥3 differing layouts; failures visible.
- **Verify:** spot-check extracted value vs source PDF.

#### T2.4 Persist + holdings query
- **Files:** `backend/app/db/models.py` (Statement), `backend/app/api/holdings_routes.py`
- **Approach:** Insert Statement rows. `GET /holdings` = latest statement per fund (window/`DISTINCT ON fund ORDER BY statement_date DESC`).
- **Acceptance:** One row per fund, newest date, correct value.
- **Verify:** SQL + endpoint vs known data.

#### T2.5 Wire classify+extract into sync (idempotent)
- **Files:** `backend/app/crawler/sync.py`
- **Approach:** After a new file downloads → classify → if capital_account extract. Skip files already processed (hash-keyed). No re-work on re-sync.
- **Acceptance:** 2nd sync re-classifies/re-extracts nothing.
- **Verify:** run twice, assert no new Statement rows.

### TASK 3 — RAG + Frontend
**Effort:** ~8–10 h · **Dependencies:** T3.1–3.2 need T2 (reports identified). T3.3 ⟂ with T2.

#### T3.1 Report ingestion → pgvector
- **Files:** `backend/app/rag/embed.py`, `backend/app/rag/ingest.py`
- **Approach:** Chunk report text (token-aware, overlap). Metadata per chunk: `file_id`, `fund`, `reporting_period` (parse Q/Year from doc/date). Embed via `Embedder` (Voyage|local) → `ReportChunk.embedding`. Idempotent (skip ingested files).
- **Acceptance:** Reports chunked + embedded; periods captured.
- **Verify:** count chunks; sample similarity query returns sane hits.

#### T3.2 Retrieval + grounded chat
- **Files:** `backend/app/rag/retrieve.py`, `backend/app/rag/chat.py`, `backend/app/api/chat_routes.py`
- **Approach:** Embed query → pgvector top-k (+ optional period filter for cross-quarter Qs) → Claude answers ONLY from retrieved chunks, returns answer + citations `[{file, period}]`. If retrieval weak/empty → say not in corpus (no fabrication). Does NOT stuff whole corpus in prompt.
- **Acceptance:** Sample Qs answered w/ real citations; out-of-corpus Q (dividend policy) → honest "not found".
- **Verify:** run the 5 sample questions, check citations resolve.

#### T3.3 Frontend scaffold
- **Files:** `frontend/src/App.tsx`, `frontend/src/api.ts`, `frontend/src/components/SyncButton.tsx`
- **Approach:** React+Vite, routing (Holdings/Chat/Files), API client, SyncButton triggers `/sync` + subscribes SSE status (toast/spinner, success|fail).
- **Acceptance:** App runs, nav works, sync button shows live status without refresh.
- **Verify:** click sync, watch status update.

#### T3.4 Holdings page
- **Files:** `frontend/src/pages/Holdings.tsx`
- **Approach:** Table from `/holdings`: fund name, current value, statement date. One row/fund.
- **Acceptance:** Matches DB; latest per fund.
- **Verify:** compare table vs psql.

#### T3.5 Chat page
- **Files:** `frontend/src/pages/Chat.tsx`
- **Approach:** Message UI → `/chat`. Render answer + clickable citations (file + period) → opens source doc.
- **Acceptance:** Citations clickable, open correct file/period.
- **Verify:** ask sample Q, click citation.

#### T3.6 Files page (bonus) + failure UX
- **Files:** `frontend/src/pages/Files.tsx`, `backend/app/api/files_routes.py`
- **Approach:** `GET /files` → name, detected type, confidence/needs_review badge, source deal, download date, open link. `GET /files/{id}` serves PDF.
- **Acceptance:** Lists all files; low-confidence visibly flagged; open works.
- **Verify:** open a few files, confirm flags.

## Parallel Execution Groups
```
Group A (serial, risk-first): T1.1 → T1.2 → T1.3 → T1.4 → T1.5 → T1.6
Group B (after files exist):  T2.1 → T2.2 → T2.3 → T2.4 → T2.5
Group C (⟂ with B once T1 done):
   T3.3 (scaffold) can start alongside T2
   T3.1 → T3.2 need T2 reports
   T3.4 needs T2.4 ; T3.5 needs T3.2 ; T3.6 needs T2.2
Critical path: T1.1→T1.2→T1.3→T1.4→T1.5→T2.2→T2.3→T2.4→T3.4
```

## Testing Strategy
- **Unit:** PDF extract (T2.1), classifier heuristics (T2.2), hash dedupe (T1.5), holdings latest-per-fund query (T2.4), chunker (T3.1).
- **Integration:** live login + walk + download vs portal (T1.3–1.5); sync idempotency (run twice); end-to-end sync→holdings.
- **Regression:** re-sync produces 0 new rows/downloads/extractions.
- **RAG eval:** the 5 sample questions — citations real + resolvable; dividend-policy Q answered honestly.
- **Manual:** spot-check current_value vs source PDFs; files page low-confidence flags.

## Traceability Matrix
| Spec Req | Task(s) | Verify |
|---|---|---|
| Crawler: login/walk/download idempotent | T1.3–T1.6 | sync twice, 0 new |
| Classifier 3-label + low-confidence visible | T2.2, T3.6 | files page flags |
| Extractor: fund/date/current value | T2.3, T2.4 | spot-check vs PDF |
| DB: files+types tracked, statements queryable | T1.2, T2.4 | psql |
| Sync action + live status + success/fail | T1.6, T3.3 | SSE observe |
| Chat grounded + citations + honest OOC | T3.1, T3.2, T3.5 | 5 sample Qs |
| Holdings latest-per-fund | T2.4, T3.4 | table vs DB |
| Files page (bonus) | T3.6 | open files |

## Risk Register
| Risk | L | I | Mitigation |
|---|---|---|---|
| R1: Portal creds "sent separately" not yet in hand → can't recon/test crawler | H | H | Build against Playwright codegen on first login; design portal.py with selectors centralized; request creds ASAP. |
| R2: Portal layout unknown → selectors fragile | M | H | Recon-then-code; centralize selectors; screenshot on failure for debug. |
| R3: Heterogeneous statement layouts → wrong current_value | M | H | Claude extract w/ synonym list + raw_field_label capture; needs_review on low confidence; spot-check. |
| R4: RAG hallucination / weak citations | M | H | Retrieval-only prompt; cite file+period; empty-retrieval → honest "not in corpus". |
| R5: 2nd embeddings vendor key (Voyage) friction | L | M | Embedder interface w/ local sentence-transformers fallback. |
| R6: Non-idempotent sync dup rows | M | M | content_hash UNIQUE + skip-by-hash before any work. |

### Rollback Strategy
- Greenfield → feature-level rollback = git revert per task branch.
- Data: drop/recreate DB (no migrations to preserve in dev); sync re-populates from portal.

## Open Questions
- Live recon pending credentials (R1). Confirm Playwright vs HTTP after first successful login.
- Voyage vs local embeddings final pick at impl (interface abstracts both).

## Version History
| Version | Date | Changes |
|---|---|---|
| v1.0 | 2026-06-24 | Initial plan. By-risk 3-task split, ~17 subtasks, Complex tier. |

## Orchestrator Execution Config
- **Suggested Mode:** New System
- **Suggested Governance:** Lightweight (take-home, single dev)
- **Estimated Agents:** 3 (one per task), T3 frontend ⟂ T2
- **Critical Path:** T1.1→…→T1.5→T2.2→T2.3→T2.4→T3.4
- **Rollback Trigger:** crawler can't authenticate after recon → escalate (blocks everything)
- **Known Gotchas:** idempotency must guard every stage (download, classify, extract, embed); citations must be traceable; never fabricate OOC answers.

## Definition of Ready (DoR)
### Mandatory
- [x] Every spec req maps to ≥1 task (traceability matrix)
- [x] Every task names specific files
- [x] Every task has acceptance criteria + verify method
- [x] Scope in/out explicit
- [x] Architecture decisions documented (ADR-001..004)
- [x] Dependencies mapped + parallel groups identified
- [ ] Plan approved by user
### Standard + Complex
- [x] Testing strategy (unit+integration+RAG eval)
- [x] Risk register + rollback
- [x] Traceability matrix
- [x] Codebase context (greenfield structure proposed)
### Complex
- [x] ADRs (none marked for SK promotion — local take-home)
- [x] Single-repo (no cross-repo coord)
- [x] Security/perf: out of scope per assignment; RAG-grounding is the main correctness concern

### Approval Record
- Approved by: _pending_
- Approved at: _pending_
- Method: _pending_
- Complexity Tier confirmed: Complex
