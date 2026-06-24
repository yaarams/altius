# Investor Document Platform — Technical Debt & Future Work

## Deferred Items
1. **Backend wiring for frontend pages (T3.4/T3.5/T3.6)**
   - Priority: High
   - Reason: Frontend-first build (user-approved). Pages run against MSW mocks; real FastAPI endpoints not yet implemented.
   - Affected endpoints: `GET /api/files` (T3.6 / files-list), `GET /api/holdings` (T3.4 / T2.4), `POST /api/chat` + `GET /api/sync/stream` (T3.5/T3.3 / T3.2), `GET /api/files/{id}/download`.
   - Proposed: implement backend tasks T1.3–T1.6, T2.x, T3.1–T3.2 + REST endpoints conforming to frontend/src/api/types.ts contract; then swap MSW off in prod build and run live e2e verification.

2. **Live e2e verification of T3.6 Files page**
   - Priority: Med
   - Reason: Property 18 (sort) + Property 19 (low-confidence badge) verified against mock fixtures only, not real classifier output.
   - Proposed: after `GET /api/files` lands, verify 40 real files render, low-confidence (<0.75) flags match classifier, sort correct on real data.

## Frontend pages — all built (MSW-mocked, live wiring pending)
- T3.3 Sync, T3.6 Files, T3.4 Holdings, T3.5 Chat — all implemented; consolidated build exit 0.
- Outstanding: real /api/* endpoints + live e2e (see item 1).

## Assumptions Made
- API contract in frontend/src/api/types.ts is authoritative; backend must conform (or contract adapted when backend lands).
- low_confidence threshold = classification_confidence < 0.75 (per plan R4/Property 19).

## Pattern Gaps Identified
- No SharedKnowledge available on host (Windows path absent) → no team patterns applied; consider seeding frontend table/sort pattern later.

## CRITICAL — Backend split-brain (worktree merge artifact)
3. **pipeline.py wired to untested orphan code path**
   - Priority: CRITICAL
   - `pipeline.py` imports `classifier/document_classifier.py` → `llm/gemini.py` (gemini-2.5-flash) → `extractor/pdf.py`.
   - The TESTED path is `classifier/classifier.py` → `llm/gemini_client.py` (gemini-2.0-flash) → `pdf_parser/parser.py`.
   - Effect: 88 passing tests do NOT cover the live pipeline; monkeypatch of gemini_client misses gemini.py → live Gemini calls.
   - Fix: repoint pipeline.py to classifier.py path; delete orphans `document_classifier.py`, `llm/gemini.py`, `extractor/pdf.py` (port pymupdf fallback from extractor/pdf.py into pdf_parser/parser.py first if wanted).
4. **pyproject wrong Gemini SDK**
   - Declares `google-generativeai>=0.7.0`; code uses `from google import genai` (package `google-genai`). `pip install` from pyproject installs wrong SDK. Fix the declaration.

## Backend remaining tasks (features)
- T1.6 sync orchestration HTTP: POST /api/sync (asyncio.Lock single-flight→409, Prop 10) + GET /api/sync/stream SSE (Crawling|Classifying|Extracting|Indexing).
- T3.1 indexer→ChromaDB (text-embedding-004, idempotent upsert, set File.indexed).
- T3.2 retrieval+chat: POST /api/chat (top_k≤20, citations file+period, OOC honest).
- GET /api/files (list, confidence) + GET /api/files/{id}/download — needed by T3.6 frontend.

## T1.6 Sync Orchestrator (added 2026-06-24 16:15)
- **Stage-naming deviation from plan.** Backend emits 5 stages `discover|download|classify|extract|index` (matches already-built frontend client.ts/types.ts) vs plan v2.1's 4 `Crawling|Classifying|Extracting|Indexing`. Frontend = live consumer → frontend won. Informative superset (discover/download split). Priority: Low (cosmetic; plan doc could be updated to match). 
- **No live e2e for sync.** test_sync.py mocks crawler/Gemini/indexer (offline, deterministic). Real path (portal crawl → SSE → browser) NOT exercised. Priority: Med — needs one live run before ship.
- **Index stage is a no-op.** DocumentIndexer (T3.1) not wired into the index stage; orchestrator emits `index: done, files_indexed=0` (ADR-008 non-fatal). Wire real indexer once T3.1 canonical module settled. Priority: Med.
