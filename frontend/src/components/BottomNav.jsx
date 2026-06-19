import { useLocation, useNavigate } from 'react-router-dom';

const tabs = [
  {
    path: '/',
    label: 'Valuate',
    icon: (active) => active
      ? 'M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm-1 17.93c-3.95-.49-7-3.85-7-7.93 0-.62.08-1.21.21-1.79L9 15v1c0 1.1.9 2 2 2v1.93zm6.9-2.54c-.26-.81-1-1.39-1.9-1.39h-1v-3c0-.55-.45-1-1-1H8v-2h2c.55 0 1-.45 1-1V7h2c1.1 0 2-.9 2-2v-.41c2.93 1.19 5 4.06 5 7.41 0 2.08-.8 3.97-2.1 5.39z'
      : 'M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm-1 17.93c-3.95-.49-7-3.85-7-7.93 0-.62.08-1.21.21-1.79L9 15v1c0 1.1.9 2 2 2v1.93zm6.9-2.54c-.26-.81-1-1.39-1.9-1.39h-1v-3c0-.55-.45-1-1-1H8v-2h2c.55 0 1-.45 1-1V7h2c1.1 0 2-.9 2-2v-.41c2.93 1.19 5 4.06 5 7.41 0 2.08-.8 3.97-2.1 5.39z',
  },
  {
    path: '/arena',
    label: 'Arena',
    icon: (active) => active
      ? 'M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm-2 15l-5-5 1.41-1.41L10 14.17l7.59-7.59L19 8l-9 9z'
      : 'M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm-2 15l-5-5 1.41-1.41L10 14.17l7.59-7.59L19 8l-9 9z',
  },
  {
    path: '/store',
    label: 'Store',
    icon: (active) => active
      ? 'M11.8 2L2 22h20L11.8 2zM12 18c-.6 0-1-.4-1-1s.4-1 1-1 1 .4 1 1-.4 1-1 1zm1-4h-2V7h2v7z'
      : 'M11.8 2L2 22h20L11.8 2zM12 18c-.6 0-1-.4-1-1s.4-1 1-1 1 .4 1 1-.4 1-1 1zm1-4h-2V7h2v7z',
  },
];

export default function BottomNav() {
  const location = useLocation();
  const navigate = useNavigate();

  const isActive = (path) => {
    if (path === '/') return location.pathname === '/';
    return location.pathname.startsWith(path);
  };

  return (
    <nav
      style={{
        position: 'fixed',
        bottom: 0,
        left: 0,
        right: 0,
        background: 'var(--tg-bottom-nav-bg)',
        borderTop: '1px solid var(--tg-section-separator)',
        display: 'flex',
        justifyContent: 'space-around',
        padding: '6px 0 20px',
        zIndex: 90,
      }}
    >
      {tabs.map((tab) => {
        const active = isActive(tab.path);
        return (
          <button
            key={tab.path}
            onClick={() => {
              window.Telegram?.WebApp?.HapticFeedback?.impactOccurred?.('light');
              navigate(tab.path);
            }}
            style={{
              display: 'flex',
              flexDirection: 'column',
              alignItems: 'center',
              gap: 2,
              background: 'none',
              border: 'none',
              color: active ? 'var(--tg-button)' : 'var(--tg-hint)',
              fontSize: 10,
              cursor: 'pointer',
              padding: '4px 16px',
              WebkitTapHighlightColor: 'transparent',
            }}
          >
            <svg viewBox="0 0 24 24" width="24" height="24" fill="currentColor">
              <path d={tab.icon(active)} />
            </svg>
            <span style={{ fontWeight: active ? 600 : 400 }}>{tab.label}</span>
          </button>
        );
      })}
    </nav>
  );
}
