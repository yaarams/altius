<!-- PLANNING RESUME STATE
planning_skill_version: 1.3.0
current_phase: Phase 4 (Synthesis) — complete, pending user approval
phases_completed: [0, 1, 2, 3]
qa_rounds_completed: 1
decisions_made: 7
open_questions: 1
last_updated: 2026-06-24
context_note: v1.1 folds formal EARS PRD (.kiro/specs/.../requirements.md, 12 reqs). By-risk 3-task split. Stack: Playwright+FastAPI+Postgres/pgvector+Claude+Voyage(local fallback)+React/Vite. Idempotency key = (portal_url,file_name) per PRD, content_hash secondary. Creds received (NOT stored in repo). Recon now unblocked.
-->

# Implementation Plan: Investor Document Platform

**Version:** v1.1
**Created:** 2026-06-24
**Updated:** 2026-06-24 (folded in formal PRD)
**Planning Skill:** my-planning-master v1.3
**Status:** Superseded by v1.2 (Gemini stack pivot, env var rename)
**Complexity Tier:** Complex
**Estimated Total Effort:** L–XL (~22–32 h)

## Input Documents
- Spec (narrative): `ASSIGNMENT.md`
- **PRD (authoritative, EARS): `.kiro/specs/investor-document-platform/requirements.md`** — 12 requirements
- Decisions log: `20-50_DECISIONS_LOG.md`
- Previous plan: `20-00_PLANNING_v1.0.md` (Superseded)

## Scope Alignment

### In Scope
- Crawler: live login `fo1.altius.finance`, walk deals, idempotent download. (PRD R1–R3)
- Classifier: 3 labels + confidence; <0.75 → low_confidence, surfaced. (PRD R4)
- Extractor: fund / date / current value, variant labels, failures recorded not null. (PRD R5, R10)
- DB: files + statements lifecycle tracked, queryable, auto-migrate. (PRD R11)
- Frontend: sync w/ live staged status, holdings, chat (grounded+cited), files (bonus). (PRD R6–R9)
- Config: env-only secrets, `.env.example`, fail-fast on missing var. (PRD R12)

### Out of Scope
- Non-PDF formats. Auth/observability/rate-limits/prod hardening. Visual polish.

### Constraints (PRD-mandated)
- Submitted system runs **live** crawler end-to-end.
- Idempotency: UNIQUE `(portal_url, file_name)`; no re-download, no dup rows, no re-extract of `extracted` files.
- Holdings: latest statement per fund, **single SQL query** (no app-side full-scan filter).
- Chat: retrieval-based (not whole-corpus in prompt), real citations (file + period), honest OOC.
- No secrets in code/committed files.

### Repos Involved
- Primary (only): `/Users/yaaracohen/Development/altius` (greenfield).

## Architecture Decisions

### ADR-001: By-risk task decomposition — *Accepted* (unchanged from v1.0)
Crawler → Extraction → RAG+Frontend. Riskiest unknown fails fast.

### ADR-002: Playwright crawler — *Accepted* (fallback httpx after recon)
Unknown likely-SPA portal; browser handles login/cookies/CSRF; defensible. Recon now unblocked (creds received).

### ADR-003: Claude + Postgres/pgvector — *Accepted*
One datastore (relational + vectors). Claude for classify/extract/chat.

### ADR-004: Voyage embeddings, local fallback — *Accepted*
Anthropic has no embeddings API. `voyage-3` behind `Embedder` interface; `sentence-transformers` keyless fallback.

### ADR-005: Idempotency key = (portal_url, file_name) — *Accepted (resolves conflict)*
- **Context:** v1.0 used content_hash; PRD R3.1+R11.3 mandate UNIQUE (portal_url, file_name).
- **Decision:** UNIQUE (portal_url, file_name) is the skip key. `content_hash` kept as **non-unique** column for corruption detection + secondary dedupe.
- **Consequences:** PRD-compliant; pre-download record (R2.3) keys on URL+name before bytes fetched.

### ADR-006: Single-flight sync + startup guards — *Accepted*
- Concurrent sync blocked (R6.6) via an in-process async lock / DB `sync_runs` row with `running` status.
- Alembic migrations auto-applied on startup before serving (R11.5).
- Missing required env var → log + exit before serving (R12.5).

## Codebase Context
Greenfield. Proposed structure:

```
altius/
  backend/
    app/
      main.py              # FastAPI; on-startup: validate env, run Alembic, mount routers, CORS
      config.py            # pydantic-settings; fail-fast missing var (R12.5)
      db/
        session.py         # engine/session; pgvector ext
        models.py          # Deal, File, Statement, ReportChunk, SyncRun
      alembic/             # migrations (auto-applied on startup)
      crawler/
        portal.py          # Playwright: login, walk deals, enumerate files, session-expiry re-auth+resume
        sync.py            # orchestrate; pre-record→download→classify→extract; single-flight; stage events
        downloader.py      # fetch bytes, sha256, status transitions
      classifier/classify.py   # heuristics→Claude; label+confidence; <0.75 low_confidence
      extractor/
        pdf.py             # PDF→text (pymupdf; pdfplumber tables); multi-page; parse-fail recorded
        statement.py       # Claude struct extract; variant labels; fail w/ reason (no silent null)
        canonical.py       # canonical repr for round-trip property (R10.3)
      rag/
        embed.py           # Embedder iface (Voyage|local)
        ingest.py          # chunk reports→embed→pgvector; idempotent; index new after sync
        retrieve.py        # top-k + period filter
        chat.py            # Claude grounded answer + citations; OOC honesty
      api/
        sync_routes.py     # POST /sync (single-flight), GET /sync/status (SSE staged)
        holdings_routes.py # GET /holdings (latest per fund, single query)
        chat_routes.py     # POST /chat
        files_routes.py    # GET /files (sortable), GET /files/{id}
    pyproject.toml
  frontend/src/{App.tsx, api.ts, pages/{Holdings,Chat,Files}.tsx, components/SyncButton.tsx}
  docker-compose.yml       # postgres + pgvector
  .env.example             # every var, placeholders, no secrets
  README.md
```

## Implementation Plan

### TASK 1 — Crawler (highest risk) · ~9–11 h · deps: none

#### T1.1 Infra + config + startup guards — *PRD R12, R11.5*
- **Files:** `pyproject.toml`, `app/main.py`, `app/config.py`, `docker-compose.yml`, `.env.example`, `alembic/`
- **Approach:** FastAPI; pydantic-settings reads env, **exits with clear error on missing required var** (R12.5); on startup **auto-run Alembic** (R11.5) before serving; pgvector postgres in compose. `.env.example` lists portal creds, Claude key, Voyage key, DB URL — placeholders only.
- **Acceptance:** missing var → process exits w/ named error; migrations applied at boot; `/health` 200.
- **Verify:** unset a var → boot fails clearly; psql `\dt` shows tables post-boot.

#### T1.2 DB schema — *PRD R11*
- **Files:** `app/db/models.py`, `app/alembic/versions/0001_init.py`
- **Approach:** `File`(id, portal_url, deal_name, file_name, content_hash, status[discovered|downloaded|extracted|failed], classification_label, confidence, low_confidence_flag, extraction_status, extraction_error, download_ts UTC, local_path) with **UNIQUE(portal_url, file_name)** (R11.3); `Statement`(id, file_id FK, fund_name, statement_date, current_value); `Deal`; `ReportChunk`(file_id, period, text, embedding vector); `SyncRun`(id, status, started_at, counts, error).
- **Acceptance:** UNIQUE(portal_url,file_name) enforced; columns match R11.1/R11.2.
- **Verify:** insert dup (url,name) → IntegrityError.

#### T1.3 Portal login + session resilience — *PRD R1*
- **Files:** `app/crawler/portal.py`
- **Approach:** Playwright chromium; creds from env; assert authed; bad creds → typed `LoginError`, abort, **no downloads** (R1.2); detect session expiry mid-crawl → **re-auth + resume from last completed deal** (R1.3).
- **Acceptance:** good creds authed; bad creds → LoginError no files; forced expiry → resumes.
- **Verify:** integration vs live portal (creds available); bad-creds test.

#### T1.4 Walk deals + enumerate + pre-record — *PRD R2*
- **Files:** `app/crawler/portal.py`, `app/crawler/sync.py`
- **Approach:** enumerate all deals; per deal enumerate files; **record (deal_name, file_name, portal_url) in DB BEFORE download** (R2.3); deal page fail → log, skip, continue (R2.4).
- **Acceptance:** all portal files pre-recorded; one bad deal doesn't abort run.
- **Verify:** row count vs manual browse; simulate deal failure.

#### T1.5 Idempotent download — *PRD R3, ADR-005*
- **Files:** `app/crawler/downloader.py`, `app/crawler/sync.py`
- **Approach:** before download check existing (portal_url, file_name) (R3.1/3.2) → skip if present; on success set status `downloaded` + UTC ts + content_hash (R3.3); on fail record failure, continue, don't mark downloaded (R3.4).
- **Acceptance:** 2nd sync → 0 new downloads, 0 dup rows.
- **Verify:** run twice; assert counts stable + "skipped N".

#### T1.6 Sync orchestration: single-flight + staged SSE — *PRD R6*
- **Files:** `app/api/sync_routes.py`, `app/crawler/sync.py`
- **Approach:** `POST /sync` starts bg job; **reject concurrent run** → "already running" (R6.6); `GET /sync/status` SSE emits stage events `Crawling|Classifying|Extracting` (R6.3) + final summary counts new downloaded/classified/extracted (R6.4) or staged failure (R6.5).
- **Acceptance:** 2nd trigger while running → "already running"; UI sees staged progress + counts, no refresh.
- **Verify:** double-trigger; observe SSE; force fail → failure event names stage.

### TASK 2 — Classify + Extract · ~7–9 h · deps: T1 (files). ⟂ partly T3.3

#### T2.1 PDF parsing — *PRD R10*
- **Files:** `app/extractor/pdf.py`
- **Approach:** pymupdf primary, pdfplumber table fallback; **all pages, no truncation** (R10.2); unopenable/corrupt → record parse failure w/ reason, **no extraction attempt** (R10.4).
- **Acceptance:** multi-page text complete; corrupt PDF → recorded parse failure.
- **Verify:** unit tests on fixtures incl a corrupt file.

#### T2.2 Classifier — *PRD R4*
- **Files:** `app/classifier/classify.py`
- **Approach:** heuristics (keywords/structure) → Claude for ambiguous; output label + confidence 0–1 (R4.2); **<0.75 → low_confidence flag** (R4.3); store label+confidence (R4.5); no manual input (R4.6); surfaced on Files page + sync summary (R4.4).
- **Acceptance:** sample labeled right; borderline → low_confidence visible.
- **Verify:** run corpus; eyeball Files page flags + summary count.

#### T2.3 Statement extractor — *PRD R5*
- **Files:** `app/extractor/statement.py`, `app/extractor/canonical.py`
- **Approach:** Claude JSON struct → fund_name, statement_date, current_value + matched raw label; variant labels incl "ending capital balance"/"closing NAV"/"partner's capital — ending"/"net asset value" (R5.2); **no current_value → record failure w/ reason, no silent null** (R5.3); no date → record failure (R5.4); canonical repr supports round-trip property (R10.3).
- **Acceptance:** current_value correct ≥3 layouts; failures recorded with reason.
- **Verify:** spot-check vs source PDFs; round-trip property test (parse→canonical→parse equivalent).

#### T2.4 Persist + holdings query — *PRD R5.5/5.6, R11.4*
- **Files:** `app/db/models.py`, `app/api/holdings_routes.py`
- **Approach:** Statement rows linked to file (R5.5); retain all; `GET /holdings` = **latest per fund in single query** (`DISTINCT ON (fund) ORDER BY statement_date DESC`) (R5.6/R11.4).
- **Acceptance:** one row/fund, newest date+value; single SQL.
- **Verify:** SQL EXPLAIN single query; endpoint vs known data.

#### T2.5 Wire into sync, idempotent — *PRD R3.5*
- **Files:** `app/crawler/sync.py`
- **Approach:** new file → classify → if capital_account extract; **skip files already `extracted`** (R3.5); set status `extracted` on success.
- **Acceptance:** 2nd sync → 0 re-classify/re-extract.
- **Verify:** run twice; 0 new Statement rows.

### TASK 3 — RAG + Frontend · ~9–11 h · deps: T3.1/3.2 need T2; T3.3 ⟂ T2

#### T3.1 Report ingestion → pgvector — *PRD R8.7/8.8*
- **Files:** `app/rag/embed.py`, `app/rag/ingest.py`
- **Approach:** chunk reports (token-aware overlap); metadata file_id, fund, reporting_period; embed (Voyage|local) → ReportChunk.embedding; **index newly added docs after each sync** (R8.7); idempotent (skip ingested).
- **Acceptance:** reports chunked+embedded; new docs queryable post-sync.
- **Verify:** chunk count; post-sync query hits new doc.

#### T3.2 Retrieval + grounded chat — *PRD R8*
- **Files:** `app/rag/retrieve.py`, `app/rag/chat.py`, `app/api/chat_routes.py`
- **Approach:** embed query → pgvector top-k (+period filter for cross-quarter, R8.6); Claude answers **only** from retrieved passages (R8.2), cite file(s)+period(s) (R8.3); empty/weak retrieval → **"not in downloaded documents"** (R8.5); **not whole-corpus-in-prompt** (R8.8).
- **Acceptance:** sample Qs cited correctly; dividend-policy Q → honest OOC.
- **Verify:** 5 sample questions; citations resolve to real files/periods.

#### T3.3 Frontend scaffold + sync control — *PRD R6.1/6.2*
- **Files:** `frontend/src/App.tsx`, `api.ts`, `components/SyncButton.tsx`
- **Approach:** React+Vite; routes Holdings/Chat/Files; sync control on **every page** (R6.1); triggers `/sync` no reload (R6.2); subscribes SSE → staged status + summary/failure.
- **Acceptance:** nav works; sync shows staged live status, counts on done, error on fail — no refresh.
- **Verify:** click sync; watch stages; force fail.

#### T3.4 Holdings page — *PRD R7*
- **Files:** `frontend/src/pages/Holdings.tsx`
- **Approach:** table from `/holdings`: fund, current value (**consistent currency format**, R7.6), statement date; one row/fund latest (R7.3); **empty-state** prompts sync (R7.4); refresh on sync-complete w/o reload (R7.5).
- **Acceptance:** matches DB; empty-state shown when no data; live update.
- **Verify:** compare vs psql; clear DB → empty-state; post-sync auto-update.

#### T3.5 Chat page — *PRD R8.4*
- **Files:** `frontend/src/pages/Chat.tsx`
- **Approach:** message UI → `/chat`; render citations as references identifying source doc, **traceable to original file** (R8.4).
- **Acceptance:** citations clickable → open correct file/period.
- **Verify:** ask sample Q; click citation opens source.

#### T3.6 Files page (bonus) — *PRD R9*
- **Files:** `frontend/src/pages/Files.tsx`, `app/api/files_routes.py`
- **Approach:** list every file (R9.1): name, detected type, source deal, download date, confidence (R9.2); low_confidence visually distinguished badge (R9.3); open/download original (R9.4); **sortable by download date + type** (R9.5).
- **Acceptance:** all files listed; low-confidence badged; sort works; open works.
- **Verify:** sort both columns; open files; confirm badges.

## Parallel Execution Groups
```
Group A (serial, risk-first): T1.1→T1.2→T1.3→T1.4→T1.5→T1.6
Group B (after files):        T2.1→T2.2→T2.3→T2.4→T2.5
Group C: T3.3 ⟂ with B; T3.1→T3.2 need T2; T3.4 needs T2.4; T3.5 needs T3.2; T3.6 needs T2.2
Critical path: T1.1→T1.2→T1.3→T1.4→T1.5→T2.2→T2.3→T2.4→T3.4
```

## Testing Strategy
- **Unit:** PDF multi-page+corrupt (R10), classifier threshold 0.75, (url,name) dedupe, holdings single-query, chunker, env fail-fast.
- **Property:** statement round-trip (R10.3).
- **Integration:** live login/walk/download; **idempotency (run twice → 0 new)**; single-flight (concurrent trigger → "already running"); startup migration; session-expiry resume.
- **RAG eval:** 5 sample questions — citations real+resolvable; dividend Q honest OOC.
- **Manual:** spot-check current_value vs PDFs; files-page badges + sort; holdings currency format + empty-state.

## Traceability Matrix
| PRD Req | Task(s) | Verify |
|---|---|---|
| R1 Auth (+expiry resume, no-secret) | T1.1, T1.3 | bad-creds, expiry test |
| R2 Deal discovery + pre-record | T1.4 | rows before download |
| R3 Idempotent download | T1.5, T2.5 | sync twice 0 new |
| R4 Classification + low_confidence | T2.2, T3.6 | files page flags + summary |
| R5 Extraction variants + failures | T2.3, T2.4 | spot-check, failure rows |
| R6 Sync staged + single-flight | T1.6, T3.3 | SSE stages, concurrent reject |
| R7 Holdings latest/fund + empty/currency | T2.4, T3.4 | table vs DB, empty-state |
| R8 Chat grounded+cited+OOC | T3.1, T3.2, T3.5 | 5 sample Qs |
| R9 Files page sortable+badge (bonus) | T3.6 | sort, open, badges |
| R10 PDF parse + round-trip | T2.1, T2.3 | property test, corrupt file |
| R11 DB schema/unique/single-query/migrate | T1.1, T1.2, T2.4 | constraints, EXPLAIN, boot |
| R12 Env secrets + fail-fast + .env.example | T1.1 | unset var → exit |

## Risk Register
| Risk | L | I | Mitigation |
|---|---|---|---|
| R1: Portal selectors fragile/unknown | M | H | Recon-then-code (creds now available); centralize selectors; screenshot on failure. |
| R2: Heterogeneous layouts → wrong current_value | M | H | Claude + variant-label list + raw_label capture; failures recorded; round-trip + spot-check. |
| R3: RAG hallucination / weak citations | M | H | Retrieval-only prompt; cite file+period; empty → honest OOC. |
| R4: Session expiry mid-crawl loses progress | M | M | Re-auth + resume from last completed deal (R1.3); pre-recorded rows. |
| R5: 2nd embeddings vendor key friction | L | M | Embedder iface w/ local fallback. |
| R6: Concurrent sync corrupts state | L | M | Single-flight lock + SyncRun row (R6.6). |

### Rollback Strategy
- Greenfield → git revert per task branch.
- Data: Alembic downgrade or drop/recreate DB in dev; sync re-populates from portal (idempotent).

## Open Questions
- Confirm Playwright vs HTTP after first live recon (creds available → recon is first T1.3 action).

## Version History
| Version | Date | Changes |
|---|---|---|
| v1.0 | 2026-06-24 | Initial. By-risk 3-task split, ~17 subtasks. |
| v1.1 | 2026-06-24 | Folded formal EARS PRD (12 reqs). Resolved idempotency-key conflict (ADR-005). Added: pre-download record, session-resume, single-flight, auto-migrate, env fail-fast, round-trip property, 0.75 threshold, empty-state/currency. Full traceability to PRD. |

## Orchestrator Execution Config
- **Mode:** New System · **Governance:** Lightweight · **Agents:** 3 (T3 frontend ⟂ T2)
- **Critical Path:** T1.1→T1.2→T1.3→T1.4→T1.5→T2.2→T2.3→T2.4→T3.4
- **Rollback Trigger:** crawler can't authenticate after recon → escalate (blocks all)
- **Known Gotchas:** idempotency guards every stage; pre-record before download; secrets env-only; citations traceable; never fabricate OOC.

## Definition of Ready (DoR)
### Mandatory
- [x] Every PRD req maps to ≥1 task (traceability matrix, 12/12)
- [x] Every task names specific files
- [x] Every task has acceptance criteria + verify
- [x] Scope in/out explicit
- [x] ADRs documented (ADR-001..006)
- [x] Dependencies + parallel groups mapped
- [ ] Plan approved by user
### Standard + Complex
- [x] Testing strategy (unit/property/integration/RAG)
- [x] Risk register + rollback
- [x] Traceability matrix (12/12 PRD reqs)
- [x] Codebase context (greenfield structure)
### Complex
- [x] ADRs (none for SK promotion — local take-home)
- [x] Single-repo
- [x] Security/perf: secrets env-only + fail-fast covered; RAG-grounding = core correctness

### Approval Record
- Approved by: _pending_
- Approved at: _pending_
- Method: _pending_
- Complexity Tier confirmed: Complex
