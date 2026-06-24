import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// In normal dev MSW intercepts /api in the browser, so this proxy is inert.
// When VITE_DISABLE_MSW=true (Playwright e2e) requests fall through to the
// real FastAPI backend on :8000.
const proxy = {
  '/api': {
    target: process.env.BACKEND_URL ?? 'http://localhost:8000',
    changeOrigin: true,
  },
}

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy,
  },
})
