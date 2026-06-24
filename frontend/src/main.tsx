import React from 'react';
import ReactDOM from 'react-dom/client';
import App from './App';
import './index.css';

async function enableMocking() {
  // Skip MSW when VITE_DISABLE_MSW=true so the app talks to the real backend
  // (used by Playwright e2e: frontend in front of the live FastAPI server).
  if (import.meta.env.DEV && import.meta.env.VITE_DISABLE_MSW !== 'true') {
    const { worker } = await import('./mocks/browser');
    return worker.start({
      onUnhandledRequest: 'bypass',
    });
  }
}

enableMocking().then(() => {
  ReactDOM.createRoot(document.getElementById('root')!).render(
    <React.StrictMode>
      <App />
    </React.StrictMode>,
  );
});
