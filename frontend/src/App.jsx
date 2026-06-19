import { useEffect } from 'react';
import { BrowserRouter, Routes, Route, useLocation } from 'react-router-dom';
import BottomNav from './components/BottomNav';
import ValuatePage from './pages/ValuatePage';
import ReportPage from './pages/ReportPage';
import ArenaPage from './pages/ArenaPage';
import StorePage from './pages/StorePage';

function AppContent() {
  const location = useLocation();

  useEffect(() => {
    // Initialise Telegram WebApp
    const tg = window.Telegram?.WebApp;
    if (tg) {
      tg.ready();
      tg.expand();
    }
  }, []);

  // Hide nav on report page (full-screen content)
  const showNav = location.pathname !== '/report';

  return (
    <div style={{ minHeight: '100vh', paddingBottom: showNav ? 80 : 0 }}>
      <Routes>
        <Route path="/" element={<ValuatePage />} />
        <Route path="/report" element={<ReportPage />} />
        <Route path="/arena" element={<ArenaPage />} />
        <Route path="/store" element={<StorePage />} />
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
