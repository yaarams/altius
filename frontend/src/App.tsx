import { BrowserRouter, NavLink, Route, Routes, useLocation } from 'react-router-dom';
import SyncPage from './pages/SyncPage';
import HoldingsPage from './pages/HoldingsPage';
import ChatPage from './pages/ChatPage';
import FilesPage from './pages/FilesPage';
import { ErrorBoundary } from './components/ErrorBoundary';

const NAV_ITEMS = [
  { to: '/', label: 'Sync', icon: '↻' },
  { to: '/holdings', label: 'Holdings', icon: '◈' },
  { to: '/chat', label: 'Chat', icon: '💬' },
  { to: '/files', label: 'Files', icon: '📁' },
];

function Sidebar() {
  return (
    <aside className="flex h-screen w-56 flex-col bg-brand-900 text-white shadow-lg">
      <div className="flex items-center gap-2 px-5 py-5 border-b border-white/10">
        <span className="text-xl font-bold tracking-tight text-white">Altius</span>
        <span className="text-xs text-brand-100 mt-0.5 font-medium">Investor Portal</span>
      </div>
      <nav className="flex-1 px-3 py-4 space-y-1">
        {NAV_ITEMS.map(({ to, label, icon }) => (
          <NavLink
            key={to}
            to={to}
            end={to === '/'}
            className={({ isActive }) =>
              [
                'flex items-center gap-3 rounded-md px-3 py-2.5 text-sm font-medium transition-colors',
                isActive
                  ? 'bg-brand-600 text-white'
                  : 'text-blue-100 hover:bg-white/10 hover:text-white',
              ].join(' ')
            }
          >
            <span className="text-base leading-none">{icon}</span>
            {label}
          </NavLink>
        ))}
      </nav>
      <div className="px-5 py-4 border-t border-white/10">
        <p className="text-xs text-blue-200 opacity-60">v0.1.0 · dev</p>
      </div>
    </aside>
  );
}

// Keyed by pathname so a crash on one route clears when navigating to another,
// while the surrounding shell (sidebar / sync control) stays mounted.
function RoutedContent() {
  const location = useLocation();
  return (
    <ErrorBoundary key={location.pathname}>
      <Routes>
        <Route path="/" element={<SyncPage />} />
        <Route path="/holdings" element={<HoldingsPage />} />
        <Route path="/chat" element={<ChatPage />} />
        <Route path="/files" element={<FilesPage />} />
      </Routes>
    </ErrorBoundary>
  );
}

export default function App() {
  return (
    <BrowserRouter>
      <div className="flex h-screen bg-gray-50">
        <Sidebar />
        <main className="flex-1 overflow-y-auto">
          <RoutedContent />
        </main>
      </div>
    </BrowserRouter>
  );
}
