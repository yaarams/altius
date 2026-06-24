# Frontend — Investor Document Platform

React + TypeScript + Vite + Tailwind UI for the platform: trigger a portal sync with
staged progress, browse holdings, ask grounded questions over documents, and list/
download source files.

**Stack:** Vite · React · TypeScript · Tailwind · MSW (mocks) · Playwright (e2e).

---

## Prerequisites

- Node.js 18+ and npm
- For real data: the backend running on `http://localhost:8000` (see `backend/README.md`)

## Setup

```bash
cd frontend
npm install
```

## Run (dev)

```bash
npm run dev
```

The dev server proxies `/api/*` → `http://localhost:8000` (override with `BACKEND_URL`).

### Real backend vs. mocks (MSW)

The app ships with an MSW mock layer for offline UI work. Behaviour is controlled by
`VITE_DISABLE_MSW`:

| `VITE_DISABLE_MSW` | Behaviour |
|--------------------|-----------|
| `true` (default — set in `.env.development`) | Mocks OFF — app calls the **real backend** via the proxy. **Backend must be running on :8000.** |
| `false` | Mocks ON — app serves from MSW fixtures, no backend needed. |

To work fully offline against mocks, set `VITE_DISABLE_MSW=false` (edit
`.env.development` or pass it inline), then `npm run dev`.

## Build

```bash
npm run build      # tsc typecheck + vite production build → dist/
npm run preview    # serve the built bundle
```

## End-to-end tests

```bash
npm run test:e2e        # Playwright (headless)
npm run test:e2e:ui     # Playwright UI mode
```

## Layout

```
frontend/src/
  api/        typed client + contract types (client.ts, types.ts)
  pages/      SyncPage, HoldingsPage, ChatPage, FilesPage
  mocks/      MSW worker + handlers + fixtures (opt-in)
  ...         router, nav, app shell
```

## API contract notes

- `client.ts` is the single source of API calls; `types.ts` holds the shared shapes.
- Holdings: the backend returns formatted/wrapped rows; `getHoldings()` adapts them to
  `FundSnapshot[]` (parses value→number, infers currency, normalises date to ISO).
- Sync uses an `EventSource` on `/api/sync/stream`; a 409 from `POST /api/sync` surfaces
  as `SyncInProgressError` (a sync is already running).
