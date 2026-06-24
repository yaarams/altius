# Backend — Investor Document Platform

FastAPI service that crawls an investor portal, classifies + extracts capital-account
statements, indexes them for retrieval-augmented chat, and serves the data to the
frontend.

**Stack:** Python ≥3.11 · FastAPI · SQLAlchemy + SQLite + Alembic · Playwright
(crawler) · pdfplumber/PyMuPDF · ChromaDB · Google Gemini (chat + `text-embedding-004`).

---

## Prerequisites

- Python 3.11+ (3.13 used in dev)
- A Gemini API key (for classify/extract/chat); the portal crawler needs portal creds.

## Setup

```bash
# from repo root
python -m venv .venv && source .venv/bin/activate

# install backend + dev deps (editable)
pip install -e "backend[dev]"

# Playwright browser (crawler only)
playwright install chromium
```

## Configuration

Copy `.env.example` → `.env` at the repo root and fill in:

| Var | Required | Purpose |
|-----|----------|---------|
| `DATABASE_URL` | yes | e.g. `sqlite:///./data/app.db` |
| `GEMINI_API_KEY` | for classify/extract/chat | Google Gemini key |
| `PORTAL_USER` / `PORTAL_PASSWORD` | for live sync | portal login |
| `PORTAL_BASE_URL`, `PORTAL_API_BASE_URL`, `PORTAL_LOGIN_PATH`, `PORTAL_MAX_LOGIN_RETRIES`, `PORTAL_HEADLESS` | no | crawler overrides (sensible defaults) |

> Secrets are env-only — never logged, never committed (`.env` is gitignored).
> On startup the app validates required env vars and auto-runs Alembic migrations;
> a missing var or failed migration exits the process with code 1 before serving.

## Database

Migrations run automatically on startup. To run manually:

```bash
alembic upgrade head
```

## Run

```bash
# from repo root
uvicorn backend.api.main:app --port 8000 --reload
```

Server on `http://localhost:8000` (the frontend dev proxy expects this port).

## Endpoints (mounted under `/api`)

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/health` | liveness |
| POST | `/api/sync` (alias `/api/sync/trigger`) | start a sync run; **409** if one is already running (single-flight) |
| GET | `/api/sync/stream` | SSE progress — stages `discover\|download\|classify\|extract\|index`, events `stage`/`complete`/`error` |
| GET | `/api/holdings` | latest value per fund |
| POST | `/api/chat` | grounded RAG answer with citations |
| GET | `/api/files` | list documents (`FileRecord[]`) |
| GET | `/api/files/{id}/download` | download source PDF |

## Tests

```bash
# from repo root
python -m pytest backend/ -q
```

External services are mocked (Gemini, portal) — tests are offline and deterministic.
Tests marked `@pytest.mark.live` require a real `GEMINI_API_KEY` and are skipped by default.

## Layout

```
backend/
  api/            FastAPI app + routers (sync, holdings, chat, files)
  crawler/        Playwright portal crawler (login, enumerate, download)
  pdf_parser/     PDF → text/tables
  classifier/     document type classification
  extractor/      structured statement extraction
  llm/            Gemini client (JSON generation)
  rag/            ChromaDB indexer + grounded chat
  pipeline.py     classify → extract → index orchestration
  db/             models, session, migrations
  alembic/        migration scripts
  tests/          pytest suite
```
