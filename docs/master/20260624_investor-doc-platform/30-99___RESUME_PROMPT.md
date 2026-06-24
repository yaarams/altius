# ORCHESTRATION RESUME PROMPT
<!-- Generated: 2026-06-24 16:45 | Orchestration v2.5 | Context: ~50% -->

## IMMEDIATE CONTEXT
You are resuming an in-progress orchestration run. Do NOT restart from Phase 0.

**Project:** Investor Document Platform — `/Users/yaaracohen/Development/altius`
**Branch:** build/investor-doc-platform
**Feature folder:** docs/master/20260624_investor-doc-platform/
**Mode:** New System · **Tier:** Complex
**Plan:** 20-00_PLANNING_v2.1.md (APPROVED, DoR verified)

## CURRENT STATE
**Phase:** Phase 2/3 — implementation + integration wiring (most of plan built)
**Backend + frontend exist and are wired together (curl-verified live).**

### Completed Phases
- [x] Phase -1: Governance → 30-05___GOVERNANCE.md
- [x] Phase 0: Validation (DoR fast path)
- [x] Phase 1: Execution config
- [~] Phase 2: Implementation — nearly all tasks done (see below)
- [~] Phase 3: Testing — unit/contract done; live in-browser e2e NOT done
- [ ] Phase 4: Review / UX validation
- [ ] Phase 5: Post-mortem / lessons

## TASK STATUS

### Done (built + tested)
| Task | What | Verify |
|------|------|--------|
| T1.1/T1.2 | Infra, config, DB schema (SQLite+Alembic, external_file_id UNIQUE) | migrations + unit |
| T1.3/4/5 | PortalCrawler login+enumerate+download | LIVE 40/40, idempotent |
| T2.1/2.2/2.3 | pdf parser, classifier, extractor | unit (Gemini mocked) |
| T2.4 | GET /api/holdings | live, 7 funds |
| T3.1/T3.2 | ChromaDB indexer + POST /api/chat grounded RAG | unit (mocked) |
| T1.6 | Sync orchestrator: POST /api/sync (+/trigger), GET /api/sync/stream, 409 P10, 5-stage SSE | 13 tests + LIVE 200/409 |
| files | GET /api/files, GET /api/files/{id}/download | 23 tests + LIVE 40 files/pdf/404 |
| T3.3–T3.6 | Frontend: scaffold + Holdings + Chat + Files pages | npm build exit 0 |
| wiring | Frontend → real backend; MSW off by default (.env.development); holdings client adapter | LIVE curl all endpoints |

### Remaining
| Item | Notes |
|------|-------|
| Provision env | PORTAL_USER/PORTAL_PASSWORD/GEMINI_API_KEY are blank → live sync/chat error at runtime |
| Wire indexer into sync | sync `index` stage = no-op (files_indexed=0); connect DocumentIndexer |
| Real in-browser e2e | only curl-verified so far; run app + backend together |
| Reconcile duplicate modules | classifier.py vs document_classifier.py; llm/gemini.py vs gemini_client.py; pdf_parser/parser.py vs extractor/pdf.py |
| Classifier precision | 9 CAS vs ground-truth 8 (junk misclassified → spurious 7th fund) |
| Phase 4/5 | review + UX validation + lessons not yet run |

## KEY FILES TO READ (in order)
1. **30-10___JOURNAL_investor-doc-platform.md** — full execution log (read last ~60 lines)
2. **30-15___CONTEXT-SNAPSHOT.json** — machine state
3. **30-30___TECH-DEBT_investor-doc-platform.md** — known gaps
4. **20-00_PLANNING_v2.1.md** — plan (reference, don't re-read fully)

## GIT STATE
- Branch: build/investor-doc-platform
- Last commit: 8543689 "Baseline: planning docs + env scaffolding before build"
- Uncommitted: `backend/`, `frontend/`, `alembic.ini` untracked; `.env.example` + journal modified. **Nothing committed since baseline** — entire build is uncommitted.

## CRITICAL DECISIONS (do not revisit)
1. SSE = 5 stages `discover|download|classify|extract|index` (matches already-built frontend), NOT plan's 4. Frontend is the live contract.
2. Sync canonical path = POST /api/sync; /api/sync/trigger is an alias for plan literal.
3. Holdings shape: frontend adapts to backend (client maps wrapped/formatted → FundSnapshot; positions [] — backend has none). No faked nested positions.
4. MSW kept but default OFF (VITE_DISABLE_MSW=true in .env.development); opt back in by flipping flag.
5. Indexer failures non-fatal in sync (ADR-008).

## IMMEDIATE NEXT ACTIONS
1. Read journal last 60 lines + 30-15 snapshot.
2. Decide priority: (a) provision env + real in-browser e2e, or (b) wire indexer into sync index stage, or (c) reconcile duplicate modules.
3. Whichever: dispatch a sonnet sub-agent, verify, journal.

## RESUME INSTRUCTIONS
1. Invoke `/my-orchestration-master`.
2. Skip Phases -1..1 (done). Resume in Phase 2/3 on the Remaining table above.
3. Governance/plan/tasks already in feature folder — read, don't recreate.
4. After work, update this file + 30-15 snapshot + journal.

## BUDGET
- Time: well within ~6h budget (~2h15m elapsed).
- Tokens: fresh 200k on resume — prioritize work over re-reading.
- Agents: max 4 parallel, sonnet default.
