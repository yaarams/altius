<!-- PLANNING RESUME STATE
planning_skill_version: 1.3.0
current_phase: Phase 4 (Synthesis) — complete, APPROVED
phases_completed: [0, 1, 2, 3]
qa_rounds_completed: 3
decisions_made: 12
open_questions: 0
last_updated: 2026-06-24
context_note: v2.1 = v2.0 + live recon. Crawler = Playwright login + APIRequestContext over internal JSON API (fo1.api.altius.finance). Idempotency key = stable external_file_id (CONF-3 resolved; presigned file_url rotates). Corpus: 40 PDFs / deal 10495 / 6 funds (alpha-zeta) / 8 CAS + 30 reports + 2 other. Stack: SQLite+ChromaDB+pdfplumber+Gemini+React. 19 properties + Hypothesis.
-->

# Implementation Plan: Investor Document Platform

**Version:** v2.1
**Created:** 2026-06-24
**Updated:** 2026-06-24 (folded live recon findings)
**Planning Skill:** my-planning-master v1.3
**Status:** APPROVED — ready for /my-orchestration-master
**Complexity Tier:** Complex
**Estimated Total Effort:** L–XL (~22–30 h; crawler simpler via API, recon retired biggest unknown)

## Input Documents
- Spec: `ASSIGNMENT.md`
- PRD (EARS): `.kiro/specs/investor-document-platform/requirements.md` (12 reqs)
- Design: `.kiro/specs/investor-document-platform/design.md` (components, schema, 19 properties)
- **Recon: `20-60_RECON_FINDINGS.md` (live portal map, API, corpus)**
- Decisions log: `20-50_DECISIONS_LOG.md`
- Previous plans: v1.0/v1.1/v1.2/v2.0 (all Superseded)

## Scope Alignment

### In Scope
Crawler (login + JSON-API enumeration + download), Classifier (3 labels+confidence), Extractor (fund/date/value, atomic), Indexer (ChromaDB RAG), DB (SQLite), Frontend (sync/holdings/chat/files), Config (env-only, fail-fast).

### Concrete corpus (from recon)
- **1 deal (id 10495), 40 PDFs, 6 funds:** alpha, beta, gamma, delta, epsilon, zeta.
- **8 capital-account statements** → holdings; **30 quarterly-update reports** → chat; **2 unlabeled junk** (`345.pdf`, `7470-01-136 - 3 2021.pdf`) → "other"/low-confidence targets.
- Portal exposes its own `document_type` → use as **classifier eval ground-truth** (we still classify independently).

### Out of Scope
Non-PDF, auth/observability/rate-limits/prod-hardening, visual polish.

### Constraints
- Live crawler end-to-end. Idempotency UNIQUE **`external_file_id`** (stable). Skip downloaded/extracted, retry failed.
- Holdings latest-per-fund single normalized SQL. Chat retrieval-bounded (top_k≤20), real citations, honest OOC.
- No secrets committed. Extraction atomic. Startup fail-fast.

### Env vars
`PORTAL_USER`, `PORTAL_PASSWORD`, `GEMINI_API_KEY`, `DATABASE_URL` (sqlite). `.env` gitignored; `.env.example` placeholders.

### Repos
Primary (only): `/Users/yaaracohen/Development/altius` (greenfield).

## Architecture Decisions

### ADR-001: By-risk task decomposition — *Accepted*
Crawler → Classify+Extract → Index+RAG+Frontend.

### ADR-002: Playwright login + APIRequestContext over internal JSON API — *Accepted (recon-confirmed; refines earlier Playwright-DOM idea)*
- **Recon:** Portal SPA backed by `fo1.api.altius.finance/api/v0.0.x`, **httpOnly session cookie** auth. `/deals-list` + `/deals/{id}/files` return structured metadata; `file_url` = presigned S3 (1h).
- **Decision:** Playwright `chromium` logs in (cookie handled), then **Playwright `APIRequestContext` (`page.request`/`context.request`) calls the JSON API and downloads presigned URLs** using the shared cookie jar. No DOM scraping; no pure-httpx login reverse-engineering.
- **Consequences:** Robust auth + clean data + fast. Defensible: "logged in as a user, consumed the same internal API the SPA uses."

### ADR-011: API enumeration + presigned download — *Accepted (recon)*
- Enumerate: `POST /api/v0.0.2/deals-list` → deal ids; per deal `GET /api/v0.0.3/deals/{id}/files` → `{data: {<file_id>: {name, file_url, document_type, type, size_in_bytes, date, created_at, state, …}}}`.
- Download: GET the presigned `file_url` (no extra auth; <1h). **Re-fetch the files list to refresh URLs if a download 403s on expiry.**
- Store portal's `document_type` as `portal_doc_type` (eval ground-truth only; not used as our label).

### ADR-003: Gemini for all LLM steps — *Accepted (CONF-2)*
`gemini-2.x` classify/extract/chat; `text-embedding-004` embeddings. Provider isolated in `backend/llm/gemini.py`.

### ADR-004: ChromaDB vector store — *Accepted*
Local persistent, collection `investor_documents`, id `{file_id}_{chunk_index}` idempotent upsert. Gemini `text-embedding-004` (768-d).

### ADR-005: SQLite + SQLAlchemy + Alembic — *Accepted*
Single-file DB, migrations auto-applied on startup.

### ADR-006: pdfplumber primary — *Accepted*
Table extraction for CAS; raw-text fallback.

### ADR-007: Idempotency key = external_file_id — *Accepted (CONF-3 resolved; overrides design/PRD R11.3)*
- **Recon problem:** presigned `file_url` rotates every call → `(portal_url, file_name)` not stable; names carry `(1)` suffixes.
- **Decision:** UNIQUE **`external_file_id`** (the API's stable integer id) = skip key. `(deal_id, name)` secondary. `content_hash` stored for integrity. Skip if downloaded/extracted; retry if failed.

### ADR-008: Separate Indexer + 4-stage pipeline — *Accepted*
Crawl→Classify→Extract→Index. SSE stages incl `Indexing`. Indexer failures non-fatal.

### ADR-009: Single-flight + startup guards — *Accepted*
asyncio.Lock + flag; concurrent → HTTP 409. Missing env / failed migration → exit 1 before serving.

### ADR-010: Property-based testing (Hypothesis) — *Accepted*
19 properties (design.md), ≥100 ex/property.

## Codebase Context
Greenfield, layout per design.md (`backend/{api,crawler,classifier,extractor,indexer,db,llm}`, `frontend/src/...`, `tests/`). See v2.0 §Codebase Context — unchanged except crawler internals (API) and schema key.

### DB schema (SQLite) — updated key
- `files`(id PK, **external_file_id INT UNIQUE**, deal_id, portal_doc_type, file_name, file_url, content_hash, local_path, download_ts ISO-UTC, status[pending|downloaded|extracted|failed], classification[capital_account_statement|report|other|unclassified], confidence, low_confidence, extraction_error, indexed, created_at). *(portal_url/file_url stored but NOT a uniqueness key.)*
- `statements`(id PK, file_id FK CASCADE, fund_name, statement_date, current_value TEXT); INDEX(fund_name, statement_date).

## Implementation Plan

### TASK 1 — Crawler + infra (risk retired by recon) · ~6–8 h · deps: none

#### T1.1 Infra + config + startup guards — *R11.5, R12; Property 14*
Same as v2.0 T1.1. Files: `backend/pyproject.toml`, `api/main.py`, `config.py`, `.env.example`, `.gitignore`, `alembic/`. Fail-fast on missing env (Prop 14); Alembic auto-migrate; SQLite. Verify: Prop 14, `/health`.

#### T1.2 DB schema + session — *R11; Property 13*
- **Files:** `backend/db/models.py`, `db/session.py`, `alembic/versions/0001_init.py`
- **Approach:** schema above; **UNIQUE `external_file_id`** (ADR-007); CASCADE; index(fund_name, statement_date).
- **Verify:** Hypothesis Prop 13 (dup external_file_id → IntegrityError).

#### T1.3 Portal login (Playwright) — *R1; Error-handling §Auth*
- **Files:** `backend/crawler/portal_crawler.py` (`_login`)
- **Approach:** Playwright chromium → `/login`, fill `PORTAL_USER`/`PORTAL_PASSWORD`, submit, assert redirect to `/main/*`. Bad creds → `LoginError`, abort, SSE error, no downloads (R1.2). Session expiry (redirect to `/login`) → re-`_login()` ≤3×, resume (R1.3). Creds never logged.
- **Recon notes:** standard email+password form works; OTP/SSO present but unused.
- **Verify:** live login; bad-creds example; mocked expiry.

#### T1.4 Enumerate via JSON API + pre-record — *R2, ADR-011*
- **Files:** `backend/crawler/portal_crawler.py` (`_enumerate_deals`/`_enumerate_files`), `orchestrator.py`
- **Approach:** via `context.request`: `POST /api/v0.0.2/deals-list` → deal ids; per deal `GET /api/v0.0.3/deals/{id}/files` → iterate `data` map. **Pre-record** each file (external_file_id, deal_id, file_name, portal_doc_type, file_url) before download (R2.3). API/deal error → log, skip, continue (R2.4). Emit `deal_discovered`.
- **Verify:** rows == 40 for deal 10495; simulate API failure → skip+continue.

#### T1.5 Idempotent download (presigned) — *R3, ADR-007; Properties 1,2,3*
- **Files:** `backend/crawler/portal_crawler.py` (`_download_file`), `orchestrator.py`
- **Approach:** for each file check `external_file_id`: skip if downloaded/extracted (Prop 1), retry if failed (Prop 2). Download presigned `file_url` (GET); on 403/expiry **re-fetch files list** for a fresh URL then retry. Success → status `downloaded` + UTC `download_ts` + `content_hash` (Prop 3). Fail → `failed`, log, continue (R3.4). Emit `file_downloaded`/`file_skipped`.
- **Verify:** Props 1/2/3; 2nd sync → 0 new; forced-expiry retry.

#### T1.6 Orchestrator: single-flight + staged SSE — *R6; Property 10*
Same as v2.0 T1.6. `POST /api/sync/trigger` (409 if running, Prop 10) + `GET /api/sync/stream` SSE stages `Crawling|Classifying|Extracting|Indexing` + terminal complete/error. Verify Prop 10, SSE.

### TASK 2 — Classifier + Extractor · ~8–10 h · deps: T1. ⟂ partly T3.3

*(Unchanged from v2.0 T2.1–T2.5. Note: 8 CAS + 30 reports + 2 junk known from recon; `portal_doc_type` available as eval ground-truth — measure classifier accuracy against it, do NOT use it as the label.)*

#### T2.1 PDF parsing (pdfplumber) — *R10; Property 11* — as v2.0.
#### T2.2 Classifier (heuristic→Gemini) — *R4; Properties 4,5,6* — as v2.0. Eval vs `portal_doc_type` (expect ~8 CAS / 30 report / 2 other). The 2 junk files should surface as low-confidence/other.
#### T2.3 Statement extractor — *R5, R10.3; Properties 7,8,12* — as v2.0. 8 CAS across 6 funds, varied layouts.
#### T2.4 Persist + holdings query — *R5.5/5.6, R7, R11.4; Property 9* — as v2.0. Expect ≤6 fund rows (latest per fund).
#### T2.5 Wire classify+extract, idempotent — *R3.5* — as v2.0.

### TASK 3 — Indexer + RAG Chat + Frontend · ~10–12 h · deps: T3.1–3.4 need T2; T3.3 ⟂ T2

*(Unchanged from v2.0 T3.1–T3.6.)*
#### T3.1 Indexer → ChromaDB — *R8.7; Property 17* — index 30 reports + 8 CAS; 800/100 chunks; Gemini embeddings.
#### T3.2 Retrieval + grounded chat — *R8; Properties 15,16* — top_k≤20; citations file+period; OOC honest (dividend Q).
#### T3.3 Frontend scaffold + sync control — *R6.1/6.2* — as v2.0.
#### T3.4 Holdings page — *R7* — ≤6 fund rows, currency, empty-state, live refresh.
#### T3.5 Chat page — *R8.4* — citation chips → file download.
#### T3.6 Files page (bonus) — *R9; Properties 18,19* — list 40 files, low-confidence badge <0.75, sort, open.

## Parallel Execution Groups
```
A (serial): T1.1→T1.2→T1.3→T1.4→T1.5→T1.6
B (after files): T2.1→T2.2→T2.3→T2.4→T2.5
C: T3.3 ⟂ B; T3.1→T3.2 need T2; T3.4 needs T2.4; T3.5 needs T3.2; T3.6 needs T2.2
Critical path: T1.1→T1.2→T1.3→T1.4→T1.5→T2.1→T2.2→T2.3→T2.4→T3.4
```

## Testing Strategy
Per design.md dual approach: Hypothesis PBT (Properties 1–19, ≥100 ex), example/unit, integration (live portal sync → expect 40 files / ≤6 fund holdings; cross-quarter chat multi-citation). Prop 13 now asserts **external_file_id** uniqueness.

## Traceability Matrix (PRD → tasks → properties)
| PRD Req | Task(s) | Property | Verify |
|---|---|---|---|
| R1 Auth + expiry + no-secret | T1.1,T1.3 | P14 | live login, expiry |
| R2 Discovery (API) + pre-record | T1.4 | — | 40 rows pre-download |
| R3 Idempotent download | T1.5,T2.5 | P1,P2,P3,P13 | sync twice, retry, external_file_id |
| R4 Classification + low_confidence | T2.2,T3.6 | P4,P5,P6,P19 | flags, eval vs portal_doc_type |
| R5 Extraction variants + atomic | T2.3,T2.4 | P7,P8 | per-variant, atomic |
| R6 Sync staged + single-flight | T1.6,T3.3 | P10 | SSE, 409 |
| R7 Holdings latest/fund + empty/currency | T2.4,T3.4 | P9 | ≤6 rows, empty-state |
| R8 Chat grounded+cited+OOC+bounded | T3.1,T3.2,T3.5 | P15,P16,P17 | 5 Qs, top_k≤20 |
| R9 Files page (bonus) | T3.6 | P18,P19 | list 40, sort, badge |
| R10 PDF parse + round-trip | T2.1,T2.3 | P7,P11,P12 | multi-page, corrupt, round-trip |
| R11 DB schema/unique/single-query/migrate | T1.1,T1.2,T2.4 | P9,P13 | external_file_id unique, EXPLAIN |
| R12 Env secrets + fail-fast | T1.1 | P14 | unset → exit 1 |

## Risk Register
| Risk | L | I | Mitigation |
|---|---|---|---|
| ~~Portal unknown~~ | — | — | **RETIRED by recon** (mapped end-to-end). |
| Presigned URL 1h expiry | M | M | Enumerate→download promptly; on 403 re-fetch files list for fresh URL (ADR-011). |
| API version drift (v0.0.2 vs v0.0.3) | L | M | Pin per-endpoint versions; centralize base paths. |
| Login flow change (OTP/SSO enforced) | L | M | Playwright login keeps robust; surface LoginError. |
| Heterogeneous CAS layouts → wrong value | M | H | pdfplumber tables + variant labels + Gemini; atomic; round-trip (P12); spot-check 8 CAS. |
| RAG hallucination / weak citations | M | H | top_k≤20 retrieval-only; cite file+period (P16); OOC honest. |
| Gemini JSON drift | M | M | JSON mode + retry-once + validation; atomic no-partial. |
| Concurrent sync | L | M | Single-flight + 409 (P10). |

### Rollback Strategy
Greenfield → git revert per task. Data: delete SQLite + ChromaDB dir; idempotent re-sync repopulates.

## Open Questions
- None. (CONF-2 → Gemini; CONF-3 → external_file_id; Playwright-vs-HTTP → Playwright+API per recon.)

## Version History
| Version | Date | Changes |
|---|---|---|
| v1.0–v1.2 | 2026-06-24 | Initial → PRD fold → Gemini pivot. |
| v2.0 | 2026-06-24 | Folded design.md (SQLite/ChromaDB/pdfplumber/Indexer/19 properties). APPROVED. |
| v2.1 | 2026-06-24 | **Folded live recon:** crawler = Playwright login + APIRequestContext over internal JSON API (ADR-002/011); idempotency key → stable `external_file_id` (ADR-007, CONF-3, overrides design/PRD R11.3); concrete corpus (40 PDFs/deal 10495/6 funds/8 CAS+30 reports+2 other); portal `document_type` as eval ground-truth; risk "portal unknown" retired, presigned-expiry + API-version risks added. |

## Orchestrator Execution Config
- **Mode:** New System · **Governance:** Lightweight · **Agents:** 3 (T3 ⟂ T2)
- **Critical Path:** T1.1→…→T1.5→T2.1→T2.2→T2.3→T2.4→T3.4
- **Rollback Trigger:** crawler can't authenticate → escalate.
- **Known Gotchas:** dedup on external_file_id (NOT presigned url); presigned URLs expire 1h (download promptly, re-fetch on 403); pre-record before download; extraction atomic; top_k≤20; citations traceable; never fabricate OOC; validate Gemini JSON; Indexer failures non-fatal; secrets env-only + never logged; portal_doc_type is eval-only, classify independently.

## Definition of Ready (DoR)
### Mandatory
- [x] Every PRD req maps to ≥1 task (12/12) + properties (19/19)
- [x] Every task names specific files
- [x] Every task has acceptance criteria + verify
- [x] Scope in/out explicit (+ concrete corpus)
- [x] ADRs documented (ADR-001..011)
- [x] Dependencies + parallel groups mapped
- [x] Plan approved by user
- [x] CONF-2 (Gemini) + CONF-3 (external_file_id) resolved
### Standard + Complex
- [x] Testing strategy (PBT + example + integration)
- [x] Risk register + rollback
- [x] Traceability (PRD + properties)
- [x] Codebase context + recon
### Complex
- [x] ADRs (none for SK promotion)
- [x] Single-repo
- [x] Security/perf: secrets env-only + never logged + fail-fast; RAG-grounding core

### Approval Record
- Approved by: user (yaara.yacv@gmail.com)
- Approved at: 2026-06-24
- Method: AskUserQuestion ("Approve" on v2.0) + recon decisions (CONF-3 external_file_id, bump v2.1)
- Complexity Tier confirmed: Complex
