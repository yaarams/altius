# E2E Requirements Coverage

Maps every acceptance criterion in
[`.kiro/specs/investor-document-platform/requirements.md`](../../.kiro/specs/investor-document-platform/requirements.md)
to a Playwright e2e test, and cross-checks against the graded deliverables in
[`ASSIGNMENT.md`](../../ASSIGNMENT.md).

**Mode:** live backend (`VITE_DISABLE_MSW=true`) — the Playwright config auto-starts
uvicorn (:8000) + vite (:5173) and drives the real stack. **Scope of this suite:**
browser-reachable behavior only. Backend-only criteria (auth, enumeration, download
idempotency, parsing, DB integrity, config) are **out of scope for Playwright** and are
covered by the pytest suite (`backend/tests/`, 140 passed / 4 live-skipped); they are
listed below with that rationale rather than silently dropped.

Legend: ✅ asserted in browser · 🟡 partial / negative-case only · ⚙️ backend (pytest) · 📝 deviation noted

| Req | Criterion | Status | Where |
|-----|-----------|--------|-------|
| **R1 Auth** | 1.1–1.5 login / re-auth / no-secret-logging | ⚙️ | `backend/tests/test_crawler_idempotency.py`, crawler `LoginError` paths |
| | 1.2 / 1.4 surface auth/session error to UI | ⚙️ | sync router emits `error` event → UI error banner (UI path shares R6.5) |
| **R2 Enumerate** | 2.1–2.5 walk deals, pre-record before download | ⚙️ | crawler `_enumerate_*` / `_prerecord_files`; pytest |
| **R3 Idempotent download** | 3.1–3.6 skip/retry by status, dedupe key | ⚙️ | `test_crawler_idempotency.py`, `test_db_unique.py` |
| **R4 Classify** | 4.1–4.3, 4.5–4.8 labels/confidence/skip | ⚙️ | `test_classifier.py` |
| | 4.4 low-confidence files surfaced | 🟡 / ✅ | Files page badge `files.spec.ts` (R9.3); live corpus has 0 low-conf |
| **R5 Extract** | 5.1–5.5 fields, atomicity, ISO date | ⚙️ | `test_extractor.py` |
| | 5.6 latest-per-fund query | ✅ | `holdings.spec.ts` R7.3 (each fund once) + `test_holdings.py` |
| **R6 Sync UI** | 6.1 control on every page | ✅ | `nav.spec.ts` |
| | 6.2 trigger w/o reload, control disabled | ✅ | `sync.spec.ts` lifecycle |
| | 6.3 live staged progress indicator | ✅ 📝 | `sync.spec.ts` — see stage-naming note below |
| | 6.4 success summary + counts + re-enable | ✅ | `sync.spec.ts` lifecycle |
| | 6.5 failure message names the stage + re-enable | ⚙️ | needs fault injection; `test_sync.py` error events |
| | 6.6 concurrent trigger → 409 message, control stays usable | ✅ | `sync.spec.ts` (second browser context) |
| **R7 Holdings** | 7.1 one row per fund | ✅ | `holdings.spec.ts` |
| | 7.2 name + currency value (symbol, 2dp) + human date | ✅ | `holdings.spec.ts` |
| | 7.3 latest statement per fund | ✅ | `holdings.spec.ts` (fund names unique) |
| | 7.4 empty-state prompt | ✅ | `holdings.spec.ts` (conditional branch) |
| | 7.5 updates without full reload | ✅ | `holdings.spec.ts` (refresh, marker survives) |
| | 7.6 placeholder when value undisplayable | ⚙️ | no such row in live corpus; extractor atomicity (`test_extractor.py`) |
| **R8 Chat** | 8.1 submit via Enter and Send button | ✅ | `chat.spec.ts` |
| | 8.2 loader + answer within budget | ✅ | `chat.spec.ts` |
| | 8.3 answer cites file(s) + period(s) | ✅ | `chat.spec.ts` |
| | 8.4 citation = link opening the original file | ✅ | `chat.spec.ts` (href `/api/files/{id}/download`, `target=_blank`) |
| | 8.5 honest out-of-corpus answer | ✅ | `chat.spec.ts` (Out-of-context, no citations) |
| | 8.6 cross-quarter synthesis | ✅ | `chat.spec.ts` |
| | 8.7 vector store indexes new docs after sync | ⚙️ | `test_indexer.py` (and see Known issue below) |
| | 8.8 bounded retrieval ≤20 passages | ⚙️ | `rag/chat.py` `TOP_K_CAP`; `test_rag_chat.py` |
| | 8.9 vector-store-unavailable error path | ⚙️ | fault injection; backend |
| **R9 Files** | 9.1 lists every file | ✅ | `files.spec.ts` |
| | 9.2 columns: name, type, source, date, confidence 0–1 | ✅ 📝 | `files.spec.ts` — shows **Fund** not deal name (see note) |
| | 9.3 low-confidence badge (<0.75); none ≥0.75 | 🟡 | `files.spec.ts` negative case; 0 low-conf rows in live corpus |
| | 9.4 open control opens file in new tab | ✅ | `files.spec.ts` |
| | 9.5 default date-desc; Doc Type → ascending | ✅ | `files.spec.ts` |
| **R10 Parsing** | 10.1–10.5 text/multipage/round-trip/atomicity | ⚙️ | `test_pdf_parser.py`, `test_extractor.py` (Hypothesis round-trip) |
| **R11 DB** | 11.1–11.6 schema/uniqueness/latest-query/auto-migrate | ⚙️ | `test_db_unique.py`, `db/migrations.py`, `test_health.py` |
| **R12 Config** | 12.1–12.6 env-only secrets, fail-fast on missing/empty | ⚙️ | `test_config.py`, `api/main.py` lifespan |

## ASSIGNMENT.md cross-check (graded items)

| Assignment ask | Covered by |
|----------------|-----------|
| Login, walk deals, download without duplicates | ⚙️ pytest (R1–R3) |
| Holdings table populated correctly from statements | ✅ `holdings.spec.ts` (R7) |
| Chat answers report questions with real citations | ✅ `chat.spec.ts` (R8.3/8.4) |
| Out-of-corpus questions answered honestly | ✅ `chat.spec.ts` (R8.5) |
| Cross-quarter synthesis (sample Qs) | ✅ `chat.spec.ts` (R8.6) |
| Sync action shows progress, success/failure, no refresh | ✅ `sync.spec.ts` (R6) |
| Files page: type, source, date, open | ✅ `files.spec.ts` (R9) |
| Low-confidence classifications visible, not silently bucketed | 🟡 `files.spec.ts` (badge logic; 0 low-conf in corpus) |

## Notes / deviations

- **📝 Stage naming (R6.3).** The requirement names stages *Crawling / Classifying /
  Extracting / Indexing*. The implementation exposes five SSE stages —
  *Discover · Download · Classify · Extract · Build index* — splitting crawl into
  discover+download. Functionally a superset; tests assert the UI's labels.
- **📝 Source identifier (R9.2).** The requirement names *source deal name*; the Files
  page surfaces the source **fund** and **period** (the backend `FileRecord` does not
  expose deal name). Same audit purpose, different field.
- **🟡 Low-confidence (R4.4 / R9.3).** The current live corpus classifies every file at
  ≥0.92, so there is no low-confidence row to assert the positive badge against. Tests
  assert the negative invariant (no badge ≥0.75); the positive path is exercised by the
  page's `isLowConfidence` logic and `test_classifier.py`.
- **Known issue affecting R8.7.** The sync orchestrator's `index` stage is currently a
  no-op (it imports a `DocumentIndexer` class that isn't the real
  `indexer.index_documents` entry point). Indexing works when invoked directly and the
  ChromaDB corpus is already populated, so chat retrieval is live; but newly synced docs
  are not auto-indexed by the sync run until that wiring is fixed. See
  `docs/PROJECT_DEEP_DIVE.md` §10.

## Running

```bash
cd frontend
npx playwright install chromium      # once
npm run test:e2e                     # all specs (sync.spec drives a LIVE crawl)
npm run test:e2e -- chat files holdings nav   # read-only specs, no crawl
```

Requires a valid `.env` (PORTAL_USER, PORTAL_PASSWORD, GEMINI_API_KEY): chat hits live
Gemini and the sync lifecycle test triggers a real portal crawl.
