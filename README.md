# Investor Document Platform

Automates pulling investor documents from a family-office portal, classifying and
extracting structured data, and surfacing it through a web frontend (holdings table,
grounded chat, sync action, files browser).

- **Backend** — FastAPI (Python ≥3.11), SQLite + SQLAlchemy/Alembic, ChromaDB vector
  store, Gemini (`gemini-2.x` + `text-embedding-004`), Playwright-driven portal crawler,
  pdfplumber/PyMuPDF parsing.
- **Frontend** — React + TypeScript + Vite + Tailwind. MSW for mock-mode dev.

Requirements live in `.kiro/specs/investor-document-platform/requirements.md`.

---

## 1. Prerequisites

- Python ≥ 3.11, Node ≥ 18
- A virtualenv at `.venv/` (already present in this checkout)

## 2. Configuration

All secrets come from environment variables — copy the template and fill real values:

```bash
cp .env.example .env
# edit .env: PORTAL_USER, PORTAL_PASSWORD, GEMINI_API_KEY
```

Required: `PORTAL_USER`, `PORTAL_PASSWORD`, `GEMINI_API_KEY`. `DATABASE_URL` defaults to
`sqlite:///./data/app.db`. The backend **fails fast** at startup if any required var is
missing or empty (lists every missing name, then exits).

## 3. Install

```bash
# Backend (into the existing venv)
source .venv/bin/activate
pip install -e "backend[dev]"
playwright install            # browser binaries for the crawler

# Frontend
cd frontend && npm install
```

---

## Running the project

### Backend (port 8000)

```bash
# from repo root
.venv/bin/python -m uvicorn backend.api.main:app --reload --port 8000
```

Startup runs Alembic migrations automatically, then serves:

| Method | Route | Purpose |
|--------|-------|---------|
| GET  | `/health` | liveness |
| GET  | `/api/holdings` | latest statement value per fund |
| POST | `/api/sync` · `/api/sync/trigger` | start pipeline (409 if already running) |
| GET  | `/api/sync/stream` | SSE stage progress |
| POST | `/api/chat` | grounded Q&A over the corpus |
| GET  | `/api/files` | all ingested files |
| GET  | `/api/files/{id}/download` | original PDF |

### Frontend (port 5173)

```bash
cd frontend
npm run dev          # http://localhost:5173
```

**Two modes**, controlled by `VITE_DISABLE_MSW`:

- **Real backend (default in dev)** — `frontend/.env.development` sets
  `VITE_DISABLE_MSW=true`, so the app talks to the live backend through the Vite proxy
  (`/api` → `http://localhost:8000`). Start the backend first.
- **Mock mode** — set `VITE_DISABLE_MSW=false` (or remove `.env.development`) to serve
  MSW fixtures with no backend running.

```bash
npm run build        # production build (tsc + vite)
```

---

## Running the tests

### Backend unit / property tests (pytest)

```bash
# from repo root, venv active
pytest
```

Current status: **140 passed, 4 skipped**. The 4 skipped are marked `@pytest.mark.live`
(real Gemini calls) and are excluded by default. To include them:

```bash
pytest -m live       # needs a working GEMINI_API_KEY (spends quota)
```

### Frontend end-to-end tests (Playwright)

These drive the **real frontend in front of the real backend** in a headless browser.
The Playwright config (`frontend/playwright.config.ts`) auto-starts **both** servers:

1. Backend — `uvicorn` on `:8000` (reads `.env`, runs migrations)
2. Frontend — `vite` on `:5173` with `VITE_DISABLE_MSW=true`

```bash
cd frontend
npx playwright install chromium   # once
npm run test:e2e                  # headless, list + HTML reporter
npm run test:e2e:ui               # interactive watch mode
npx playwright show-report        # open the last HTML report
```

Coverage (one spec per requirement area, in `frontend/e2e/`):

| Spec | Requirement | Notes |
|------|-------------|-------|
| `nav.spec.ts` | R6.1 shell / sync control on every page | |
| `sync.spec.ts` | R6 sync action + staged progress | **triggers a live portal crawl** |
| `holdings.spec.ts` | R7 holdings table | uses the client-side holdings adapter |
| `chat.spec.ts` | R8 chat | **hits live Gemini**; passes on grounded answer *or* honest out-of-context |
| `files.spec.ts` | R9 files list + sort | |

Current status: **9 passed**.

> ⚠️ The sync e2e starts a real crawl of `fo1.altius.finance` with the configured
> credentials, and chat queries hit the live Gemini API. Both require valid `.env`
> values. The sync test only asserts the initial UI transition and does not wait for the
> crawl to finish.
