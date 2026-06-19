import { useEffect } from 'react';
import { BrowserRouter, Routes, Route, useLocation, Navigate } from 'react-router-dom';
import BottomNav from './components/BottomNav';
import ValuatePage from './pages/ValuatePage';
import ReportPage from './pages/ReportPage';
import FeedPage from './pages/FeedPage';
import ArenaPage from './pages/ArenaPage';
import DiscoverPage from './pages/DiscoverPage';

function AppContent() {
  const location = useLocation();

  useEffect(() => {
    const tg = window.Telegram?.WebApp;
    if (tg) { tg.ready(); tg.expand(); }
  }, []);

  const showNav = !['/report'].includes(location.pathname);

  return (
    <div style={{ minHeight: '100vh', paddingBottom: showNav ? 80 : 0 }}>
      <Routes>
        <Route path="/" element={<ValuatePage />} />
        <Route path="/feed" element={<FeedPage />} />
        <Route path="/report" element={<ReportPage />} />
        <Route path="/arena" element={<ArenaPage />} />
        <Route path="/store" element={<DiscoverPage />} />
        <Route path="*" element={<Navigate to="/feed" replace />} />
      </Routes>
      {showNav && <BottomNav />}
    </div>
  );
}

export default function App() {
  return (
    <BrowserRouter>
      <AppContent />
    </BrowserRouter>
  );
}
