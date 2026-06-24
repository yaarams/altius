<!-- PLANNING RESUME STATE
planning_skill_version: 1.3.0
current_phase: Phase 4 (Synthesis) — complete, pending user approval
phases_completed: [0, 1, 2, 3]
qa_rounds_completed: 2
decisions_made: 8
open_questions: 1
last_updated: 2026-06-24
context_note: v1.2 = v1.1 + Gemini pivot (D-008). Stack: Playwright+FastAPI+Postgres/pgvector+Gemini(gemini-2.x + text-embedding-004)+React/Vite. Env vars PORTAL_USER/PORTAL_PASSWORD/GEMINI_API_KEY/DATABASE_URL. Idempotency key=(portal_url,file_name), content_hash secondary. Creds in .env (gitignored), not committed. Recon unblocked.
-->

# Implementation Plan: Investor Document Platform

**Version:** v1.2
**Created:** 2026-06-24
**Updated:** 2026-06-24 (Gemini stack pivot + env var rename)
**Planning Skill:** my-planning-master v1.3
**Status:** Superseded by v2.0 (folded in formal design.md — SQLite/ChromaDB/pdfplumber/Indexer/19 properties)
**Complexity Tier:** Complex
**Estimated Total Effort:** L–XL (~22–32 h)

## Input Documents
- Spec (narrative): `ASSIGNMENT.md`
- **PRD (authoritative, EARS): `.kiro/specs/investor-document-platform/requirements.md`** — 12 requirements
- Decisions log: `20-50_DECISIONS_LOG.md`
- Previous plans: `20-00_PLANNING_v1.0.md`, `v1.1.md` (both Superseded)

## Scope Alignment

### In Scope
- Crawler: live login `fo1.altius.finance`, walk deals, idempotent download. (R1–R3)
- Classifier: 3 labels + confidence; <0.75 → low_confidence, surfaced. (R4)
- Extractor: fund / date / current value, variant labels, failures recorded not null. (R5, R10)
- DB: files + statements lifecycle tracked, queryable, auto-migrate. (R11)
- Frontend: sync w/ live staged status, holdings, chat (grounded+cited), files (bonus). (R6–R9)
- Config: env-only secrets, `.env.example`, fail-fast on missing var. (R12)

### Out of Scope
- Non-PDF formats. Auth/observability/rate-limits/prod hardening. Visual polish.

### Constraints (PRD-mandated)
- Live crawler end-to-end. Idempotency UNIQUE `(portal_url, file_name)`; no re-download/dup/re-extract.
- Holdings: latest per fund in single SQL. Chat: retrieval-based, real citations, honest OOC. No secrets committed.

### Env vars (D-008)
`PORTAL_USER`, `PORTAL_PASSWORD`, `GEMINI_API_KEY`, `DATABASE_URL`. Real values in `.env` (gitignored). Placeholders in `.env.example`.

### Repos Involved
- Primary (only): `/Users/yaaracohen/Development/altius` (greenfield).

## Architecture Decisions

### ADR-001: By-risk task decomposition — *Accepted*
Crawler → Extraction → RAG+Frontend. Riskiest unknown fails fast.

### ADR-002: Playwright crawler — *Accepted* (fallback httpx after recon)
Unknown likely-SPA portal; browser handles login/cookies/CSRF; defensible. Recon unblocked (creds in `.env`).

### ADR-003: Gemini for all LLM steps — *Accepted (was Claude; pivoted D-008)*
- **Context:** Only `GEMINI_API_KEY` provided.
- **Decision:** `gemini-2.x` for classification (ambiguous cases), statement extraction (structured JSON), and chat answer synthesis.
- **Consequences:** Single vendor/key. Use Gemini structured-output / JSON mode for the extractor.

### ADR-004: Gemini embeddings + pgvector — *Accepted (was Voyage; pivoted D-008)*
- **Decision:** `text-embedding-004` produces vectors stored in Postgres pgvector. `Embedder` interface retained so a local model could swap in if needed.
- **Consequences:** One key covers LLM + embeddings. No second vendor.

### ADR-005: Idempotency key = (portal_url, file_name) — *Accepted (resolves conflict)*
UNIQUE (portal_url, file_name) = skip key (R3.1/R11.3). `content_hash` non-unique column for corruption/secondary dedupe. Pre-download record (R2.3) keys on URL+name.

### ADR-006: Single-flight sync + startup guards — *Accepted*
Concurrent sync blocked (R6.6) via async lock + `SyncRun` row. Alembic auto-migrate on startup before serving (R11.5). Missing required env var → log + exit (R12.5).

## Codebase Context
Greenfield. Proposed structure:

```
altius/
  backend/
    app/
      main.py              # FastAPI; startup: validate env, run Alembic, mount routers, CORS
      config.py            # pydantic-settings; reads PORTAL_USER/PORTAL_PASSWORD/GEMINI_API_KEY/DATABASE_URL; fail-fast
      llm/gemini.py        # Gemini client wrapper (chat + structured JSON)
      db/{session.py, models.py}     # Deal, File, Statement, ReportChunk, SyncRun; pgvector
      alembic/             # migrations (auto-applied on startup)
      crawler/{portal.py, sync.py, downloader.py}   # Playwright; pre-record→download; single-flight; expiry resume
      classifier/classify.py         # heuristics→Gemini; label+confidence; <0.75 low_confidence
      extractor/{pdf.py, statement.py, canonical.py} # pymupdf/pdfplumber; Gemini JSON extract; round-trip
      rag/
        embed.py           # Embedder iface → text-embedding-004 (local fallback)
        ingest.py          # chunk reports→embed→pgvector; idempotent; index new after sync
        retrieve.py        # top-k + period filter
        chat.py            # Gemini grounded answer + citations; OOC honesty
      api/{sync_routes.py, holdings_routes.py, chat_routes.py, files_routes.py}
    pyproject.toml
  frontend/src/{App.tsx, api.ts, pages/{Holdings,Chat,Files}.tsx, components/SyncButton.tsx}
  docker-compose.yml       # postgres + pgvector
  .env / .env.example / .gitignore / README.md
```

## Implementation Plan

### TASK 1 — Crawler (highest risk) · ~9–11 h · deps: none

#### T1.1 Infra + config + startup guards — *R12, R11.5*
- **Files:** `pyproject.toml`, `app/main.py`, `app/config.py`, `docker-compose.yml`, `.env.example`, `.gitignore`, `alembic/`
- **Approach:** FastAPI; pydantic-settings reads `PORTAL_USER`/`PORTAL_PASSWORD`/`GEMINI_API_KEY`/`DATABASE_URL`, **exits w/ named error on missing required var** (R12.5); startup **auto-runs Alembic** (R11.5) before serving; pgvector postgres in compose.
- **Acceptance:** missing var → clean exit; migrations at boot; `/health` 200.
- **Verify:** unset var → boot fails named; psql `\dt` post-boot.

#### T1.2 DB schema — *R11*
- **Files:** `app/db/models.py`, `alembic/versions/0001_init.py`
- **Approach:** `File`(id, portal_url, deal_name, file_name, content_hash, status[discovered|downloaded|extracted|failed], classification_label, confidence, low_confidence_flag, extraction_status, extraction_error, download_ts UTC, local_path), **UNIQUE(portal_url, file_name)**; `Statement`(id, file_id, fund_name, statement_date, current_value); `Deal`; `ReportChunk`(file_id, period, text, embedding vector); `SyncRun`(id, status, started_at, counts, error).
- **Acceptance:** UNIQUE(portal_url,file_name) enforced; columns per R11.1/R11.2.
- **Verify:** dup (url,name) → IntegrityError.

#### T1.3 Portal login + session resilience — *R1*
- **Files:** `app/crawler/portal.py`
- **Approach:** Playwright chromium; creds from env; bad creds → `LoginError`, abort, no downloads (R1.2); session expiry → re-auth + resume from last completed deal (R1.3).
- **Acceptance:** good→authed; bad→LoginError no files; expiry→resume.
- **Verify:** integration vs live portal; bad-creds test.

#### T1.4 Walk deals + enumerate + pre-record — *R2*
- **Files:** `app/crawler/portal.py`, `app/crawler/sync.py`
- **Approach:** enumerate deals; per deal enumerate files; **record (deal_name, file_name, portal_url) before download** (R2.3); deal-page fail → log, skip, continue (R2.4).
- **Acceptance:** all files pre-recorded; one bad deal doesn't abort.
- **Verify:** rows vs manual browse; simulate deal failure.

#### T1.5 Idempotent download — *R3, ADR-005*
- **Files:** `app/crawler/downloader.py`, `app/crawler/sync.py`
- **Approach:** check (portal_url,file_name) → skip if present (R3.1/3.2); on success status `downloaded`+UTC ts+content_hash (R3.3); on fail record + continue, not `downloaded` (R3.4).
- **Acceptance:** 2nd sync → 0 new, 0 dup.
- **Verify:** run twice; counts stable + "skipped N".

#### T1.6 Sync orchestration: single-flight + staged SSE — *R6*
- **Files:** `app/api/sync_routes.py`, `app/crawler/sync.py`
- **Approach:** `POST /sync` bg job; concurrent → "already running" (R6.6); `GET /sync/status` SSE stages `Crawling|Classifying|Extracting` (R6.3) + summary counts (R6.4) or staged failure (R6.5).
- **Acceptance:** 2nd trigger → "already running"; staged progress + counts, no refresh.
- **Verify:** double-trigger; SSE observe; force fail.

### TASK 2 — Classify + Extract · ~7–9 h · deps: T1 (files). ⟂ partly T3.3

#### T2.1 PDF parsing — *R10*
- **Files:** `app/extractor/pdf.py`
- **Approach:** pymupdf primary, pdfplumber table fallback; all pages no truncation (R10.2); corrupt → record parse failure w/ reason, no extraction (R10.4).
- **Acceptance:** multi-page complete; corrupt → recorded failure.
- **Verify:** unit tests incl corrupt fixture.

#### T2.2 Classifier — *R4*
- **Files:** `app/classifier/classify.py`
- **Approach:** heuristics → **Gemini** for ambiguous; label + confidence 0–1 (R4.2); **<0.75 → low_confidence** (R4.3); store label+conf (R4.5); no manual input (R4.6); surfaced Files page + sync summary (R4.4).
- **Acceptance:** sample right; borderline → low_confidence visible.
- **Verify:** run corpus; eyeball flags + summary.

#### T2.3 Statement extractor — *R5*
- **Files:** `app/extractor/statement.py`, `app/extractor/canonical.py`
- **Approach:** **Gemini structured/JSON** → fund_name, statement_date, current_value + matched raw label; variant labels incl "ending capital balance"/"closing NAV"/"partner's capital — ending"/"net asset value" (R5.2); no value → record failure w/ reason, no silent null (R5.3); no date → failure (R5.4); canonical repr for round-trip (R10.3).
- **Acceptance:** current_value correct ≥3 layouts; failures recorded.
- **Verify:** spot-check vs PDFs; round-trip property test.

#### T2.4 Persist + holdings query — *R5.5/5.6, R11.4*
- **Files:** `app/db/models.py`, `app/api/holdings_routes.py`
- **Approach:** Statement rows linked to file; retain all; `GET /holdings` latest per fund **single query** (`DISTINCT ON (fund) ORDER BY statement_date DESC`) (R5.6/R11.4).
- **Acceptance:** one row/fund newest; single SQL.
- **Verify:** EXPLAIN single query; endpoint vs known data.

#### T2.5 Wire into sync, idempotent — *R3.5*
- **Files:** `app/crawler/sync.py`
- **Approach:** new file → classify → if capital_account extract; skip already-`extracted` (R3.5); set `extracted` on success.
- **Acceptance:** 2nd sync → 0 re-work.
- **Verify:** run twice; 0 new Statement rows.

### TASK 3 — RAG + Frontend · ~9–11 h · deps: T3.1/3.2 need T2; T3.3 ⟂ T2

#### T3.1 Report ingestion → pgvector — *R8.7/8.8*
- **Files:** `app/rag/embed.py`, `app/rag/ingest.py`
- **Approach:** chunk reports (token-aware overlap); metadata file_id, fund, reporting_period; embed via **text-embedding-004** → ReportChunk.embedding; index new docs after sync (R8.7); idempotent.
- **Acceptance:** chunked+embedded; new docs queryable post-sync.
- **Verify:** chunk count; post-sync query hits new doc.

#### T3.2 Retrieval + grounded chat — *R8*
- **Files:** `app/rag/retrieve.py`, `app/rag/chat.py`, `app/api/chat_routes.py`
- **Approach:** embed query → pgvector top-k (+period filter, R8.6); **Gemini** answers only from retrieved passages (R8.2), cite file(s)+period(s) (R8.3); empty/weak → "not in downloaded documents" (R8.5); not whole-corpus-in-prompt (R8.8).
- **Acceptance:** sample Qs cited; dividend Q → honest OOC.
- **Verify:** 5 sample questions; citations resolve.

#### T3.3 Frontend scaffold + sync control — *R6.1/6.2*
- **Files:** `frontend/src/App.tsx`, `api.ts`, `components/SyncButton.tsx`
- **Approach:** React+Vite; routes Holdings/Chat/Files; sync control on every page (R6.1); triggers `/sync` no reload (R6.2); SSE → staged status + summary/failure.
- **Acceptance:** nav works; staged live status + counts/error, no refresh.
- **Verify:** click sync; watch stages; force fail.

#### T3.4 Holdings page — *R7*
- **Files:** `frontend/src/pages/Holdings.tsx`
- **Approach:** table from `/holdings`: fund, current value (consistent currency, R7.6), statement date; one row/fund latest (R7.3); empty-state prompts sync (R7.4); live update on sync-complete (R7.5).
- **Acceptance:** matches DB; empty-state; live update.
- **Verify:** vs psql; clear DB→empty-state; post-sync auto-update.

#### T3.5 Chat page — *R8.4*
- **Files:** `frontend/src/pages/Chat.tsx`
- **Approach:** message UI → `/chat`; citations rendered as references to source doc, traceable to original file (R8.4).
- **Acceptance:** citations clickable → open correct file/period.
- **Verify:** ask sample Q; click opens source.

#### T3.6 Files page (bonus) — *R9*
- **Files:** `frontend/src/pages/Files.tsx`, `app/api/files_routes.py`
- **Approach:** list every file (R9.1): name, type, source deal, download date, confidence (R9.2); low_confidence badge (R9.3); open/download original (R9.4); sortable by date + type (R9.5).
- **Acceptance:** all listed; badged; sort + open work.
- **Verify:** sort both; open files; confirm badges.

## Parallel Execution Groups
```
Group A (serial, risk-first): T1.1→T1.2→T1.3→T1.4→T1.5→T1.6
Group B (after files):        T2.1→T2.2→T2.3→T2.4→T2.5
Group C: T3.3 ⟂ B; T3.1→T3.2 need T2; T3.4 needs T2.4; T3.5 needs T3.2; T3.6 needs T2.2
Critical path: T1.1→T1.2→T1.3→T1.4→T1.5→T2.2→T2.3→T2.4→T3.4
```

## Testing Strategy
- **Unit:** PDF multi-page+corrupt, classifier 0.75 threshold, (url,name) dedupe, holdings single-query, chunker, env fail-fast.
- **Property:** statement round-trip (R10.3).
- **Integration:** live login/walk/download; idempotency (twice→0 new); single-flight; startup migration; expiry resume.
- **RAG eval:** 5 sample questions — citations real; dividend Q honest OOC.
- **Manual:** current_value vs PDFs; files badges+sort; holdings currency+empty-state.

## Traceability Matrix
| PRD Req | Task(s) | Verify |
|---|---|---|
| R1 Auth (+expiry, no-secret) | T1.1, T1.3 | bad-creds, expiry |
| R2 Deal discovery + pre-record | T1.4 | rows before download |
| R3 Idempotent download | T1.5, T2.5 | sync twice 0 new |
| R4 Classification + low_confidence | T2.2, T3.6 | flags + summary |
| R5 Extraction variants + failures | T2.3, T2.4 | spot-check, failure rows |
| R6 Sync staged + single-flight | T1.6, T3.3 | SSE stages, reject concurrent |
| R7 Holdings latest/fund + empty/currency | T2.4, T3.4 | table vs DB, empty-state |
| R8 Chat grounded+cited+OOC | T3.1, T3.2, T3.5 | 5 sample Qs |
| R9 Files page sortable+badge (bonus) | T3.6 | sort, open, badges |
| R10 PDF parse + round-trip | T2.1, T2.3 | property test, corrupt |
| R11 DB schema/unique/single-query/migrate | T1.1, T1.2, T2.4 | constraints, EXPLAIN, boot |
| R12 Env secrets + fail-fast + .env.example | T1.1 | unset var → exit |

## Risk Register
| Risk | L | I | Mitigation |
|---|---|---|---|
| R1: Portal selectors fragile/unknown | M | H | Recon-then-code (creds in .env); centralize selectors; screenshot on failure. |
| R2: Heterogeneous layouts → wrong current_value | M | H | Gemini + variant-label list + raw_label capture; failures recorded; round-trip + spot-check. |
| R3: RAG hallucination / weak citations | M | H | Retrieval-only prompt; cite file+period; empty → honest OOC. |
| R4: Session expiry mid-crawl | M | M | Re-auth + resume (R1.3); pre-recorded rows. |
| R5: Gemini structured-output drift on messy PDFs | M | M | JSON schema + validation; failure recorded not null; spot-check. |
| R6: Concurrent sync corrupts state | L | M | Single-flight lock + SyncRun row. |

### Rollback Strategy
- Greenfield → git revert per task branch. Data: Alembic downgrade / drop-recreate dev DB; idempotent re-sync repopulates.

## Open Questions
- Confirm Playwright vs HTTP after first live recon (creds in .env → recon is first T1.3 action).

## Version History
| Version | Date | Changes |
|---|---|---|
| v1.0 | 2026-06-24 | Initial. By-risk 3-task split, ~17 subtasks. |
| v1.1 | 2026-06-24 | Folded EARS PRD (12 reqs); idempotency-key conflict resolved; pre-record, single-flight, auto-migrate, env fail-fast, round-trip, 0.75 threshold; full traceability. |
| v1.2 | 2026-06-24 | Gemini pivot (D-008): gemini-2.x for classify/extract/chat, text-embedding-004 for embeddings; dropped Claude+Voyage (ADR-003/004 rewritten). Env vars renamed PORTAL_USER/PORTAL_PASSWORD. |

## Orchestrator Execution Config
- **Mode:** New System · **Governance:** Lightweight · **Agents:** 3 (T3 frontend ⟂ T2)
- **Critical Path:** T1.1→T1.2→T1.3→T1.4→T1.5→T2.2→T2.3→T2.4→T3.4
- **Rollback Trigger:** crawler can't authenticate after recon → escalate (blocks all)
- **Known Gotchas:** idempotency guards every stage; pre-record before download; secrets env-only; citations traceable; never fabricate OOC; validate Gemini JSON output.

## Definition of Ready (DoR)
### Mandatory
- [x] Every PRD req maps to ≥1 task (12/12)
- [x] Every task names specific files
- [x] Every task has acceptance criteria + verify
- [x] Scope in/out explicit
- [x] ADRs documented (ADR-001..006)
- [x] Dependencies + parallel groups mapped
- [ ] Plan approved by user
### Standard + Complex
- [x] Testing strategy (unit/property/integration/RAG)
- [x] Risk register + rollback
- [x] Traceability matrix (12/12)
- [x] Codebase context (greenfield)
### Complex
- [x] ADRs (none for SK promotion — local take-home)
- [x] Single-repo
- [x] Security/perf: secrets env-only + fail-fast; RAG-grounding = core correctness

### Approval Record
- Approved by: _pending_
- Approved at: _pending_
- Method: _pending_
- Complexity Tier confirmed: Complex
