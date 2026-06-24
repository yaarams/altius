import { defineConfig, devices } from '@playwright/test';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));

/**
 * E2E config: real frontend in front of the real FastAPI backend.
 *
 * Two webServers are launched:
 *   1. Backend  — uvicorn on :8000 (reads .env, runs migrations, serves /api).
 *   2. Frontend — vite dev on :5173 with VITE_DISABLE_MSW=true so the browser
 *                 hits the live backend through the /api proxy instead of MSW.
 *
 * NOTE: "real backend as-is" — the backend's holdings shape and missing /files
 * route diverge from the frontend contract, so holdings.spec and files.spec are
 * expected to fail; they document the integration gap. The sync test triggers a
 * LIVE portal crawl, and chat hits the live Gemini API.
 */

const REPO_ROOT = path.resolve(__dirname, '..');
const BACKEND_PORT = 8000;
const FRONTEND_PORT = 5173;

export default defineConfig({
  testDir: './e2e',
  // Live Gemini chat + portal crawl are slow; give generous time.
  timeout: 90_000,
  expect: { timeout: 15_000 },
  fullyParallel: false,
  workers: 1,
  retries: 0,
  reporter: [['list'], ['html', { open: 'never' }]],

  use: {
    baseURL: `http://localhost:${FRONTEND_PORT}`,
    trace: 'on-first-retry',
    screenshot: 'only-on-failure',
  },

  projects: [
    { name: 'chromium', use: { ...devices['Desktop Chrome'] } },
  ],

  webServer: [
    {
      command: `.venv/bin/python -m uvicorn backend.api.main:app --port ${BACKEND_PORT}`,
      cwd: REPO_ROOT,
      url: `http://localhost:${BACKEND_PORT}/health`,
      reuseExistingServer: !process.env.CI,
      timeout: 60_000,
      stdout: 'pipe',
      stderr: 'pipe',
    },
    {
      command: 'npm run dev',
      cwd: __dirname,
      url: `http://localhost:${FRONTEND_PORT}`,
      reuseExistingServer: !process.env.CI,
      timeout: 60_000,
      env: {
        VITE_DISABLE_MSW: 'true',
        BACKEND_URL: `http://localhost:${BACKEND_PORT}`,
      },
    },
  ],
});
