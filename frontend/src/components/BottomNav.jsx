import { useLocation, useNavigate } from 'react-router-dom';

const tabs = [
  { path: '/feed', label: 'Live', icon: (a) => a ? 'M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm0 3c1.66 0 3 1.34 3 3s-1.34 3-3 3-3-1.34-3-3 1.34-3 3-3zm0 14.2c-2.5 0-4.71-1.28-6-3.22.03-1.99 4-3.08 6-3.08 1.99 0 5.97 1.09 6 3.08-1.29 1.94-3.5 3.22-6 3.22z' : 'M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm0 3c1.66 0 3 1.34 3 3s-1.34 3-3 3-3-1.34-3-3 1.34-3 3-3zm0 14.2c-2.5 0-4.71-1.28-6-3.22.03-1.99 4-3.08 6-3.08 1.99 0 5.97 1.09 6 3.08-1.29 1.94-3.5 3.22-6 3.22z' },
  { path: '/store', label: 'Discover', icon: (a) => a ? 'M11.8 2L2 22h20L11.8 2zM12 18c-.6 0-1-.4-1-1s.4-1 1-1 1 .4 1 1-.4 1-1 1zm1-4h-2V7h2v7z' : 'M11.8 2L2 22h20L11.8 2zM12 18c-.6 0-1-.4-1-1s.4-1 1-1 1 .4 1 1-.4 1-1 1zm1-4h-2V7h2v7z' },
  { path: '/arena', label: 'Rooms', icon: (a) => a ? 'M20 2H4c-1.1 0-2 .9-2 2v18l4-4h14c1.1 0 2-.9 2-2V4c0-1.1-.9-2-2-2zm0 14H5.17L4 17.17V4h16v12z' : 'M20 2H4c-1.1 0-2 .9-2 2v18l4-4h14c1.1 0 2-.9 2-2V4c0-1.1-.9-2-2-2zm0 14H5.17L4 17.17V4h16v12z' },
];

export default function BottomNav() {
  const location = useLocation();
  const navigate = useNavigate();

  const isActive = (path) => {
    if (location.pathname === '/' || location.pathname === '/feed') return path === '/feed';
    return location.pathname.startsWith(path);
  };

  return (
    <nav style={{
      position: 'fixed', bottom: 0, left: 0, right: 0,
      background: 'rgba(10,10,15,0.92)',
      backdropFilter: 'blur(24px)',
      WebkitBackdropFilter: 'blur(24px)',
      borderTop: '1px solid var(--border-glass)',
      display: 'flex', justifyContent: 'space-around',
      padding: '6px 0 20px', zIndex: 90,
    }}>
      {tabs.map((tab) => {
        const active = isActive(tab.path);
        return (
          <button
            key={tab.path}
            onClick={() => {
              window.Telegram?.WebApp?.HapticFeedback?.impactOccurred?.('light');
              if (tab.path === '/feed') navigate('/feed');
              else navigate(tab.path);
            }}
            style={{
              display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 2,
              background: 'none', border: 'none',
              color: active ? 'var(--brand-green)' : 'var(--brand-muted)',
              fontSize: 10, fontWeight: active ? 600 : 400,
              cursor: 'pointer', padding: '4px 16px',
              letterSpacing: '0.03em',
            }}
          >
            <svg viewBox="0 0 24 24" width="22" height="22" fill="currentColor">
              <path d={tab.icon(active)} />
            </svg>
            <span>{tab.label}</span>
          </button>
        );
      })}
    </nav>
  );
}
