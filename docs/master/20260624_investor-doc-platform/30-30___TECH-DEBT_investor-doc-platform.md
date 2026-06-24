# Investor Document Platform — Technical Debt & Known Issues

Updated 2026-06-24 after full live e2e. App is functionally complete end-to-end (live portal + real Gemini). This supersedes earlier mid-build notes.

## ✅ Resolved since earlier drafts
- ~~Backend wiring for frontend pages~~ — frontend now runs against the real FastAPI backend; Playwright e2e 16/16 pass.
- ~~Backend split-brain (pipeline → orphan modules)~~ — reconciled to canonical `classifier/document_classifier.py` + `llm/gemini_client.py`; duplicates deleted.
- ~~Index stage no-op / T3.1 not wired~~ — `sync.py` now calls `index_documents(db)`; live sync indexes 260 chunks.
- ~~T3.1 indexer / T3.2 chat not run~~ — indexer ran; ChromaDB populated; chat grounded with citations; OOC honest.
- ~~Holdings response-shape mismatch~~ — reconciled; holdings e2e 3/3 pass against real data.

## Open — deviations from plan
1. **Embedding model (ADR-004).** `text-embedding-004` returns 404 on this Gemini key tier → using **`gemini-embedding-001`** (3072-d). Works; update ADR-004 if key stays. Priority: Low.
2. **Gemini SDK declaration.** Verify `backend/pyproject.toml` declares the SDK the code actually imports (`google-genai` vs `google-generativeai`). If mismatched, a clean `pip install` from pyproject installs the wrong package. Priority: Med — confirm before handoff.
3. **Classifier fund-whitelist.** Precision fix names the 6 portal funds in the LLM prompt so out-of-portal CAS → `other`. Corpus-specific/brittle for a generic system. Priority: Med.

## Open — known issues
4. **SSE login-phase observability (R6).** No events during portal login; on slow logins the 30s keep-alive can close the stream before terminal `complete` → frontend shows "Lost connection" though backend completes. Fix: heartbeat / "Logging in…" event during login. Priority: Med (UX).
5. **Currency hardcoded to `$`.** `Statement` has no currency field; holdings formatter always prepends `$`. EUR/other-currency funds would mis-render. Fix: extractor captures currency → holdings formats per-fund. Priority: Med (R7 "consistent currency").
6. **Null citation `period`.** Some fund_zeta/fund_delta filenames don't match the period heuristic → citation period null (file still correct). Fix: fall back to statement_date / in-doc period. Priority: Low.
7. **Retrieval period-precision.** Quarter-specific questions sometimes cite an adjacent quarter (grounded + cited, but loose). Consider period-filtered retrieval. Priority: Low.
8. **Junk→`other` depends on LLM.** CAS text-heuristic removed; no-signal filenames fall to Gemini; if Gemini down → `unclassified` (visible per R4, not silent). Priority: Low.

## Stage-naming note
- Backend SSE emits 5 stages `discover|download|classify|extract|index` (matches frontend client) vs plan v2.1's 4 `Crawling|Classifying|Extracting|Indexing`. Informative superset; frontend is the live consumer. Cosmetic.

## Deferred (optional for take-home)
- Orchestration Phases 4–5 (formal code-review/UX audit, `30-35___LESSONS-LEARNED`).
- Frontend visual polish (explicitly not graded).
- Multi-deal: deals-list loop is coded but only exercised on deal 10495.

## Assumptions
- Single account, deal 10495, 40 PDFs, 6 funds (matches recon). Presigned URLs ~1h; download immediately after enumerate (403 → re-fetch).

## What's solid (verified e2e — live portal + real Gemini)
- Clean rebuild via `/api/sync`: SSE staged discover→download→classify→extract→index→complete; 40 downloaded / 40 classified (40/40 vs portal ground-truth) / 8 statements / 260 chunks; holdings 6 funds; chat grounded+cited; dividend OOC not_found.
- Idempotent re-sync (0 new, stable counts); concurrent sync → HTTP 409.
- Backend tests: 156 passed / 4 skipped. Frontend Playwright e2e: 16/16.
