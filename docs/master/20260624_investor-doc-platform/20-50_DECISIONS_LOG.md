# Decisions & Activity Log — Investor Document Platform

**Started:** 2026-06-24
**Skill:** my-planning-master v1.3
**Spec source:** `ASSIGNMENT.md` (no separate PRD/research docs — assignment IS the spec)

This log = running record of decisions made + actions taken during planning.
Append-only. Newest at bottom of each section.

---

## Activity Log

| When | Action | Result |
|------|--------|--------|
| 2026-06-24 | Read `ASSIGNMENT.md` | Investor doc platform take-home. Pipeline (crawl/classify/extract/DB) + frontend (holdings, chat/RAG, files). |
| 2026-06-24 | Inspected project dir | Greenfield. Empty `src/`, only `ASSIGNMENT.md`. Not a git repo. |
| 2026-06-24 | Phase 1 scope Q&A (round 1) | User chose **By-risk** task split. Other 3 questions deferred to clarify. |
| 2026-06-24 | Created this decisions log | Per user request. |
| 2026-06-24 | Locked D-002/003/004, added D-005 | Playwright + Claude/pgvector + React/Vite. Embeddings need own provider (Claude has none). |
| 2026-06-24 | Wrote plan v1.0 | `20-00_PLANNING_v1.0.md`. 3 tasks (by-risk), ~17 subtasks, Complex tier. |
| 2026-06-24 | Read `.kiro/specs/.../requirements.md` | Formal EARS PRD, 12 reqs. Authoritative. Refines plan + 1 conflict. |
| 2026-06-24 | Re-planned → v1.1 | Folded 12 PRD reqs in. Marked v1.0 Superseded. Logged conflict D-006. |
| 2026-06-24 | Created .gitignore + .env.example | Guard secrets (R1.4/R12.4). .env has real creds, not committed. |
| 2026-06-24 | Gemini key provided | Stack pivot signal: Gemini not Claude/Voyage. See D-008. Plan swap → v1.2 pending confirm. |
| 2026-06-24 | User confirmed Gemini + var rename | Updated .env + .env.example (PORTAL_USER/PORTAL_PASSWORD). |
| 2026-06-24 | Wrote plan v1.2 | Gemini stack. v1.1 Superseded. Active plan = v1.2. |
| 2026-06-24 | Read `.kiro/.../design.md` | Formal design. Overrides v1.2 on DB/vector/PDF/layout/testing. MAJOR change. |
| 2026-06-24 | Re-planned → v2.0 | Folded design.md. v1.2 Superseded. Active plan = v2.0. Logged D-009, CONF-2. |
| 2026-06-24 | v2.0 APPROVED | CONF-2 → Gemini. Approval recorded. |
| 2026-06-24 | Live portal recon (Playwright) | Mapped login + JSON API + corpus. See `20-60_RECON_FINDINGS.md`. D-011, CONF-3. |
| 2026-06-24 | User: CONF-3 → external_file_id, bump v2.1 | Folded recon. v2.0 Superseded. Active = v2.1. |

---

## Decisions

### D-001 — Task split strategy
- **Status:** Decided
- **Choice:** By-risk split.
  - **T1 — Crawler** (highest unknown: live portal, login, nav, idempotent download)
  - **T2 — Extraction + Classify** across heterogeneous PDFs (current-value field)
  - **T3 — Chat RAG + all frontend** (holdings, chat, files pages, sync UX)
- **Why:** Front-load the riskiest unknown (crawler against a portal we can't inspect ahead). Fail-fast on the part most likely to blow the timeline.

### D-002 — Crawler tool
- **Status:** Recommended, pending confirm
- **Choice (proposed):** Playwright (headless browser).
- **Why:**
  - Portal is unknown + likely a JS-rendered SPA → plain HTTP would see empty HTML.
  - Browser handles login forms, cookies, CSRF, redirects automatically.
  - "Defend the choice" in interview: drove it like a real user, robust to an un-inspectable portal.
  - Playwright MCP available this session → can recon the live portal during planning.
- **Cost / counter:** Heavier + slower than raw HTTP. If recon shows server-rendered HTML + stable endpoints, plain `httpx` would be faster and more idempotent-friendly. Fallback path noted.

### D-003 — LLM stack
- **Status:** Decided
- **Choice:** Claude (Anthropic) for classify, extract, chat. Postgres + **pgvector** for both relational data and embeddings (one datastore).
- **Why:** One DB = less infra. Claude strong at structured extraction over messy heterogeneous PDFs and grounded citation-style answers.

### D-004 — Frontend framework
- **Status:** Decided
- **Choice:** React + Vite. SSE (or poll) for live sync status.
- **Why:** Light, fast, easy live updates without refresh. Polish not graded.

### D-005 — Embeddings provider
- **Status:** Decided (with fallback)
- **Context:** Anthropic offers **no embeddings API**. pgvector needs an embedding model.
- **Choice:** **Voyage AI** (`voyage-3`) — the embeddings provider Anthropic recommends. **Fallback:** local `sentence-transformers` (no extra API key) if avoiding a second vendor key.
- **Why:** Voyage = high retrieval quality, pairs with Claude. Local model = zero-key dev. Plan supports either behind one interface.

---

### D-006 — Idempotency key (CONFLICT resolved)
- **Status:** Decided
- **Conflict:** v1.0 used `content_hash` for dedupe. PRD R3.1 + R11.3 mandate uniqueness on **(portal_url, file_name)**.
- **Resolution:** Follow PRD — UNIQUE `(portal_url, file_name)` is the skip/idempotency key. **Keep `content_hash` as a non-unique stored column** for corruption detection + secondary dedupe.
- **Why:** PRD is authoritative. Hybrid keeps both guarantees: PRD's required key + hash integrity benefit.

### D-007 — Adopt PRD specifics
- **Status:** Decided
- **Choice:** Lock PRD-explicit values into plan: confidence threshold **0.75**; file `status` lifecycle (discovered/downloaded/extracted/failed) + extraction_error column; **single-flight** sync (no concurrent runs, R6.6); **Alembic auto-migrate on startup** (R11.5); **fail-fast on missing env var** (R12.5); pre-download DB record (R2.3); session-expiry resume (R1.3); round-trip property test (R10.3).

### D-008 — Gemini stack (supersedes D-003 LLM + D-005 embeddings)
- **Status:** ACCEPTED (user confirmed 2026-06-24: "Yes, all Gemini" + rename vars)
- **Vars:** Renamed to `PORTAL_USER` / `PORTAL_PASSWORD` (shell `$USER` collision avoided). .env + .env.example updated.
- **Trigger:** User supplied only `GEMINI_API_KEY` (no Anthropic/Voyage key).
- **Choice (proposed):** Google Gemini for everything — `gemini-2.x` for classify/extract/chat; `text-embedding-004` for pgvector embeddings.
- **Why:** Single vendor, single key. Drops Voyage (D-005) and Claude (D-003). Gemini covers both LLM + embeddings.
- **Impact:** Plan v1.1 → v1.2 swap (ADR-003/004 rewrite, embed.py uses Gemini). No task-structure change.
- **Secondary:** `.env` uses `USER`/`PWD` — shell `$USER` collision risk; recommend `PORTAL_USER`/`PORTAL_PASSWORD`.

### D-009 — Adopt formal design.md (supersedes ADR-003/004/005 of v1.2)
- **Status:** ACCEPTED
- **Changes:** DB Postgres/pgvector → **SQLite** (SQLAlchemy+Alembic); vector store → **ChromaDB** (local persistent); PDF → **pdfplumber** primary; added **Indexer** subsystem (4-stage pipeline + Indexing SSE stage); design module layout (`backend/{crawler,classifier,extractor,indexer,api}`); exact `/api/*` paths; **19 correctness properties + Hypothesis PBT**; status enum `pending|downloaded|extracted|failed` + `unclassified` label + `indexed` flag; holdings normalized query w/ `MAX(id)` tie-breaker; heuristic ≥0.90 early-return; chat top_k=20; 60s timeout + HTTP 409/502/503/504.
- **Why:** design.md is the authoritative technical design artifact; user asked to align plan to it.

### CONF-2 — Provider conflict: design.md OpenAI vs user Gemini
- **Status:** RESOLVED 2026-06-24 — user confirmed **keep Gemini**. Plan v2.0 APPROVED.
- **Conflict:** design.md §Tech Choices = OpenAI (gpt-4o-mini/gpt-4o, text-embedding-3-small 1536-d). User D-008 = Gemini (only GEMINI_API_KEY provided).
- **Resolution (provisional):** Keep **Gemini** (gemini-2.x + text-embedding-004, 768-d). User's explicit live instruction + available key outweigh the doc. Provider isolated in `backend/llm/gemini.py` → reverting to OpenAI = one-file + key change.
- **Needs:** user confirm Gemini stays, or revert to OpenAI.

### D-011 — Crawler = Playwright login + internal JSON API
- **Status:** ACCEPTED (v2.1)
- **Finding:** Portal has an internal JSON API (`fo1.api.altius.finance/api/v0.0.x`), cookie-auth. `/deals-list` + `/deals/{id}/files` give all metadata; `file_url` = presigned S3 (1h).
- **Choice:** Playwright logs in (cookie), then Playwright `APIRequestContext` calls the JSON API + downloads presigned URLs. Not DOM scraping; not pure httpx.
- **Why:** Robust auth + clean structured data + fast. Defensible vs assignment's "drive like a user."

### CONF-3 — Idempotency key: presigned URL is not stable
- **Status:** RESOLVED (v2.1) — user chose stable `external_file_id`. Overrides design.md/PRD R11.3.
- **Conflict:** approved key = UNIQUE(portal_url, file_name). But `file_url` rotates every API call (presigned, 1h) → not stable; names have `(1)` suffixes.
- **Proposed fix:** key on the API's **stable integer `file id`** → `files.external_file_id` UNIQUE. Keep (deal_id, name) secondary. Updates ADR-007, R3.1/R11.3, Property 13.

---

## Open Questions
- None. CONF-2 → Gemini. CONF-3 → external_file_id. Crawler → Playwright+API. Plan v2.1 APPROVED.
- D-008 Gemini pivot → confirmed, triggered v1.2.
- `USER`/`PWD` rename to `PORTAL_USER`/`PORTAL_PASSWORD`? (collision risk)
- Live portal recon blocked — credentials "sent separately", not yet in hand. Confirm Playwright vs HTTP after first login. (D-002 default = Playwright.)
- Voyage vs local embeddings — final pick at impl time (D-005), interface abstracts both.
