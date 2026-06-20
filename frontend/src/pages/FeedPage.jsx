import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { loadCreditBalance } from '../utils/tgStorage';

// ── Mock social proof events ──────────────────────────
const MOCK_FEED = [
  { type: 'unlock', user: 'Alex', postcode: 'SW16', product: 'The Deal Autopsy', icon: '🔥', time: '2m ago' },
  { type: 'unlock', user: 'Sarah', postcode: 'E1', product: 'Syndicate Street Map', icon: '💰', time: '4m ago' },
  { type: 'value', user: 'Mike', postcode: 'M1', typeLabel: 'Flat', icon: '🏠', time: '7m ago' },
  { type: 'unlock', user: 'Chris', postcode: 'SE1', product: 'The Lowball Counter-Email', icon: '😡', time: '12m ago' },
  { type: 'unlock', user: 'Riley', postcode: 'N22', product: 'Planning Permission Oracle', icon: '😴', time: '18m ago' },
  { type: 'value', user: 'Taylor', postcode: 'SE15', typeLabel: 'Terraced House', icon: '🏠', time: '23m ago' },
  { type: 'unlock', user: 'Morgan', postcode: 'B1', product: 'The Gentrification Radar', icon: '💰', time: '31m ago' },
  { type: 'arena', user: 'Casey', postcode: 'SW16', icon: '🏆', time: '38m ago' },
  { type: 'unlock', user: 'Jamie', postcode: 'EH1', product: 'Council Tax Challenger', icon: '😡', time: '45m ago' },
  { type: 'unlock', user: 'Drew', postcode: 'CF10', product: 'Leasehold Trap X-Ray', icon: '😰', time: '51m ago' },
  { type: 'value', user: 'Blake', postcode: 'G1', typeLabel: 'Semi-Detached', icon: '🏠', time: '1h ago' },
  { type: 'unlock', user: 'Skyler', postcode: 'N22', product: 'Neighbor Extension Blueprint', icon: '🔥', time: '1h ago' },
  { type: 'unlock', user: 'Reese', postcode: 'BS1', product: 'Counter-Offer Letter', icon: '😡', time: '1h ago' },
  { type: 'arena', user: 'Quinn', postcode: 'SW16', icon: '🏆', time: '2h ago' },
  { type: 'unlock', user: 'Harper', postcode: 'OX1', product: 'Area Growth Report', icon: '💰', time: '2h ago' },
  { type: 'value', user: 'Sage', postcode: 'M1', typeLabel: 'Detached', icon: '🏠', time: '2h ago' },
  { type: 'unlock', user: 'Emery', postcode: 'SE15', product: 'The Stealth Listing Sniper', icon: '🔥', time: '3h ago' },
  { type: 'unlock', user: 'Rowan', postcode: 'E17', product: 'Permitted Development Check', icon: '😴', time: '3h ago' },
  { type: 'value', user: 'Finley', postcode: 'N1', typeLabel: 'Flat', icon: '🏠', time: '4h ago' },
  { type: 'unlock', user: 'Parker', postcode: 'SW16', product: 'Ownership Intelligence', icon: '💰', time: '4h ago' },
];

function FeedCard({ event, index }) {
  const animationDelay = `${Math.min(index * 60, 800)}ms`;

  return (
    <div
      className="feed-card"
      style={{
        animation: `fadeSlideIn 0.4s ease both`,
        animationDelay,
        marginBottom: 8,
      }}
    >
      {/* Avatar */}
      <div style={{
        width: 36, height: 36, borderRadius: '50%',
        background: event.type === 'unlock' ? 'rgba(21,128,127,0.12)' : event.type === 'value' ? 'rgba(14,39,71,0.08)' : 'rgba(216,154,50,0.15)',
        display: 'flex', alignItems: 'center', justifyContent: 'center',
        fontSize: 16, flexShrink: 0,
      }}>
        {event.icon}
      </div>

      {/* Content */}
      <div style={{ flex: 1, minWidth: 0 }}>
        {event.type === 'unlock' && (
          <div className="ui-text" style={{ fontSize: 12, lineHeight: 1.4, color: 'var(--brand-ink)' }}>
            <strong>{event.user}</strong> in <strong>{event.postcode}</strong> unlocked<br />
            <span style={{ color: 'var(--brand-green)', fontWeight: 500 }}>{event.product}</span>
          </div>
        )}
        {event.type === 'value' && (
          <div className="ui-text" style={{ fontSize: 12, lineHeight: 1.4, color: 'var(--brand-ink)' }}>
            <strong>{event.user}</strong> in <strong>{event.postcode}</strong> valued a<br />
            <span style={{ fontWeight: 500 }}>{event.typeLabel}</span>
          </div>
        )}
        {event.type === 'arena' && (
          <div className="ui-text" style={{ fontSize: 12, lineHeight: 1.4, color: 'var(--brand-ink)' }}>
            <strong>{event.user}</strong> earned Arena points in <strong>{event.postcode}</strong>
          </div>
        )}
      </div>

      {/* Timestamp */}
      <span className="ui-text" style={{
        fontSize: 10, color: 'var(--brand-muted)', flexShrink: 0,
      }}>
        {event.time}
      </span>
    </div>
  );
}

export default function FeedPage() {
  const navigate = useNavigate();
  const [balance, setBalance] = useState(0);

  useEffect(() => {
    window.Telegram?.WebApp?.expand?.();
    loadCreditBalance().then(b => setBalance(b || 0));
  }, []);

  return (
    <div style={{ paddingBottom: 100 }}>
      {/* ── Sticky Top Bar ────────────────────────────── */}
      <div style={{
        position: 'sticky', top: 0, zIndex: 40,
        background: 'var(--brand-cream)',
        borderBottom: '1px solid var(--brand-line)',
        padding: '12px 16px',
        display: 'flex', justifyContent: 'space-between', alignItems: 'center',
      }}>
        {/* Avatar */}
        <div style={{
          width: 36, height: 36, borderRadius: '50%',
          background: 'var(--brand-dark)',
          display: 'flex', alignItems: 'center', justifyContent: 'center',
          color: 'var(--brand-cream)', fontWeight: 600, fontSize: 14,
          fontFamily: '"Fraunces", Georgia, serif',
        }}>
          H
        </div>

        {/* Credit Balance Pill */}
        <div style={{
          display: 'flex', alignItems: 'center', gap: 6,
          background: 'var(--brand-dark)', color: 'var(--brand-cream)',
          borderRadius: 999, padding: '5px 12px 5px 10px',
        }}>
          <span style={{ fontSize: 12 }}>⚡</span>
          <span className="ui-text" style={{ fontSize: 13, fontWeight: 600 }}>
            {'\u00a3'}{balance.toFixed(2)}
          </span>
          <button
            onClick={() => { window.Telegram?.WebApp?.HapticFeedback?.impactOccurred?.('medium'); navigate('/store'); }}
            style={{
              width: 20, height: 20, borderRadius: '50%',
              background: 'var(--brand-green)', color: '#fff',
              border: 'none', fontSize: 14, cursor: 'pointer',
              display: 'flex', alignItems: 'center', justifyContent: 'center',
              padding: 0, lineHeight: 1,
            }}
          >
            +
          </button>
        </div>
      </div>

      {/* ── Hero ───────────────────────────────────────── */}
      <div style={{ padding: '24px 16px 20px', textAlign: 'center' }}>
        <h1 style={{
          fontFamily: '"Fraunces", Georgia, serif', fontWeight: 600, fontSize: 26,
          color: 'var(--brand-ink)', letterSpacing: '-0.02em', margin: '0 0 4px',
        }}>
          Your property's price, <span style={{ color: 'var(--brand-green)' }}>proved</span>
        </h1>
        <p className="ui-text" style={{ fontSize: 13, color: 'var(--brand-muted)', margin: '0 auto 20px', maxWidth: 240, lineHeight: 1.5 }}>
          Free valuations backed by HM Land Registry. Watch the community in action.
        </p>
      </div>

      {/* ── Live Activity Label ────────────────────────── */}
      <div style={{ padding: '0 16px 8px' }}>
        <div style={{
          display: 'flex', alignItems: 'center', gap: 6,
        }}>
          <span style={{
            display: 'inline-block', width: 7, height: 7, borderRadius: '50%',
            background: 'var(--brand-green)',
            animation: 'livePulse 2s ease-in-out infinite',
          }} />
          <span className="ui-text" style={{
            fontSize: 11, fontWeight: 500, color: 'var(--brand-muted)',
            textTransform: 'uppercase', letterSpacing: '0.1em',
          }}>
            Live Activity
          </span>
        </div>
      </div>

      {/* ── The Feed ──────────────────────────────────── */}
      <div style={{ padding: '0 16px' }}>
        {MOCK_FEED.map((event, i) => (
          <FeedCard key={i} event={event} index={i} />
        ))}
      </div>

      {/* ── Floating CTA ──────────────────────────────── */}
      <div style={{
        position: 'fixed', bottom: 76, left: 16, right: 16, zIndex: 50,
        animation: 'fadeSlideIn 0.6s ease 0.3s both',
      }}>
        <button
          onClick={() => { window.Telegram?.WebApp?.HapticFeedback?.impactOccurred?.('light'); navigate('/'); }}
          style={{
            width: '100%', padding: 16, borderRadius: 8,
            border: 'none', fontSize: 16, fontWeight: 600,
            cursor: 'pointer',
            background: 'var(--brand-dark)',
            color: 'var(--brand-cream)',
            fontFamily: '-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif',
          }}
        >
          Value a Property 🏠
        </button>
      </div>

      {/* ── Animations ────────────────────────────────── */}
      <style>{`
        @keyframes fadeSlideIn {
          from { opacity: 0; transform: translateY(12px); }
          to { opacity: 1; transform: translateY(0); }
        }
        @keyframes livePulse {
          0%, 100% { opacity: 1; transform: scale(1); }
          50% { opacity: 0.4; transform: scale(0.7); }
        }
      `}</style>
    </div>
  );
}
