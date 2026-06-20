import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { loadCreditBalance } from '../utils/tgStorage';

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
];

export default function FeedPage() {
  const navigate = useNavigate();
  const [balance, setBalance] = useState(0);

  useEffect(() => {
    window.Telegram?.WebApp?.expand?.();
    loadCreditBalance().then(b => setBalance(b || 0));
  }, []);

  return (
    <div style={{ paddingBottom: 120 }}>
      {/* ── Sticky Top Bar ────────────────────────────── */}
      <div style={{
        position: 'sticky', top: 0, zIndex: 40,
        background: 'var(--bg-deep)',
        borderBottom: '1px solid var(--border-glass)',
        padding: '14px 20px',
        display: 'flex', justifyContent: 'space-between', alignItems: 'center',
      }}>
        <div style={{
          width: 36, height: 36, borderRadius: 10,
          background: 'linear-gradient(135deg, var(--brand-green), #10b981)',
          display: 'flex', alignItems: 'center', justifyContent: 'center',
          color: '#0a0a0f', fontWeight: 700, fontSize: 14,
        }}>
          H
        </div>
        <div style={{
          display: 'flex', alignItems: 'center', gap: 8,
          background: 'var(--bg-glass)',
          border: '1px solid var(--border-glass)',
          borderRadius: 999, padding: '6px 14px 6px 12px',
        }}>
          <span style={{ fontSize: 13, color: 'var(--brand-green)' }}>⚡</span>
          <span style={{ fontSize: 14, fontWeight: 600, letterSpacing: '-0.02em' }}>
            {'\u00a3'}{balance.toFixed(2)}
          </span>
          <button
            onClick={() => { window.Telegram?.WebApp?.HapticFeedback?.impactOccurred?.('medium'); navigate('/store'); }}
            style={{
              width: 20, height: 20, borderRadius: '50%',
              background: 'linear-gradient(135deg, var(--brand-green), #10b981)',
              color: '#0a0a0f', border: 'none', fontSize: 13, cursor: 'pointer',
              display: 'flex', alignItems: 'center', justifyContent: 'center',
              padding: 0, fontWeight: 700,
            }}
          >
            +
          </button>
        </div>
      </div>

      {/* ── Hero ───────────────────────────────────────── */}
      <div style={{ padding: '36px 24px 24px', textAlign: 'center' }}>
        <p className="label" style={{ marginBottom: 8 }}>Property Intelligence</p>
        <h1 style={{
          fontFamily: '"Fraunces", Georgia, serif', fontWeight: 600, fontSize: 28,
          color: 'var(--brand-ink)', letterSpacing: '-0.03em',
          margin: '0 0 6px', lineHeight: 1.1,
        }}>
          Your property's price,<br />
          <span style={{ color: 'var(--brand-green)' }}>proved</span>
        </h1>
        <p style={{
          fontSize: 13, color: 'var(--brand-muted)',
          margin: '0 auto 24px', maxWidth: 240, lineHeight: 1.6,
        }}>
          Free valuations backed by HM Land Registry. See what others are discovering.
        </p>
      </div>

      {/* ── Live Activity ─────────────────────────────── */}
      <div style={{ padding: '0 20px 10px', display: 'flex', alignItems: 'center', gap: 8 }}>
        <span style={{
          width: 6, height: 6, borderRadius: '50%',
          background: 'var(--brand-green)',
          animation: 'livePulse 2s ease-in-out infinite',
        }} />
        <span className="label" style={{ fontSize: 11 }}>Live Activity</span>
        <span style={{ flex: 1, height: 1, background: 'var(--border-glass)' }} />
      </div>

      {/* ── Feed ──────────────────────────────────────── */}
      <div style={{ padding: '0 16px', display: 'flex', flexDirection: 'column', gap: 8 }}>
        {MOCK_FEED.map((event, i) => (
          <div
            key={i}
            className="feed-card"
            style={{ animation: `fadeSlideIn 0.4s ease ${Math.min(i * 50, 700)}ms both` }}
          >
            <div style={{
              width: 36, height: 36, borderRadius: '50%',
              background: event.type === 'unlock' ? 'rgba(52,211,153,0.12)' : event.type === 'value' ? 'rgba(255,255,255,0.05)' : 'rgba(251,191,36,0.12)',
              display: 'flex', alignItems: 'center', justifyContent: 'center',
              fontSize: 15, flexShrink: 0,
            }}>
              {event.icon}
            </div>
            <div style={{ flex: 1, minWidth: 0 }}>
              {event.type === 'unlock' && (
                <div style={{ fontSize: 12, lineHeight: 1.5, color: 'var(--brand-ink)' }}>
                  <strong>{event.user}</strong> in <strong>{event.postcode}</strong> unlocked<br />
                  <span style={{ color: 'var(--brand-green)', fontWeight: 500 }}>{event.product}</span>
                </div>
              )}
              {event.type === 'value' && (
                <div style={{ fontSize: 12, lineHeight: 1.5, color: 'var(--brand-ink)' }}>
                  <strong>{event.user}</strong> in <strong>{event.postcode}</strong> valued a<br />
                  <span style={{ fontWeight: 500 }}>{event.typeLabel}</span>
                </div>
              )}
              {event.type === 'arena' && (
                <div style={{ fontSize: 12, lineHeight: 1.5, color: 'var(--brand-ink)' }}>
                  <strong>{event.user}</strong> earned Arena points in <strong>{event.postcode}</strong>
                </div>
              )}
            </div>
            <span style={{ fontSize: 10, color: 'var(--brand-muted)', flexShrink: 0 }}>
              {event.time}
            </span>
          </div>
        ))}
      </div>

      {/* ── Floating CTA ──────────────────────────────── */}
      <div style={{
        position: 'fixed', bottom: 80, left: 16, right: 16, zIndex: 50,
        animation: 'fadeSlideIn 0.5s ease 0.4s both',
      }}>
        <button
          onClick={() => { window.Telegram?.WebApp?.HapticFeedback?.impactOccurred?.('light'); navigate('/'); }}
          className="btn-primary"
          style={{ padding: 16, fontSize: 15 }}
        >
          Value a Property 🏠
        </button>
      </div>
    </div>
  );
}
