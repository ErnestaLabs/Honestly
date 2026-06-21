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
    <div style={{ minHeight: '100vh', background: '#f8fafb', paddingBottom: 120 }}>
      {/* Top Bar */}
      <div style={{
        background: '#fff', padding: '14px 20px',
        display: 'flex', justifyContent: 'space-between', alignItems: 'center',
        borderBottom: '1px solid #f1f5f9',
      }}>
        <span style={{ fontFamily: '"Fraunces", Georgia, serif', fontWeight: 600, fontSize: 18, color: '#0f172a' }}>
          Honestly
        </span>
        <div style={{
          display: 'flex', alignItems: 'center', gap: 6,
          background: '#f8fafb', borderRadius: 999,
          padding: '5px 12px 5px 10px',
          border: '1px solid #f1f5f9',
        }}>
          <span style={{ fontSize: 13, color: '#334155' }}>⚡</span>
          <span style={{ fontSize: 14, fontWeight: 600, color: '#0f172a' }}>
            {'\u00a3'}{balance.toFixed(2)}
          </span>
          <button
            onClick={() => { window.Telegram?.WebApp?.HapticFeedback?.impactOccurred?.('medium'); navigate('/store'); }}
            style={{
              width: 20, height: 20, borderRadius: '50%',
              background: '#0f172a', color: '#fff',
              border: 'none', fontSize: 13, cursor: 'pointer',
              display: 'flex', alignItems: 'center', justifyContent: 'center',
              padding: 0, fontWeight: 600,
            }}
          >
            +
          </button>
        </div>
      </div>

      {/* Hero */}
      <div style={{ padding: '40px 20px 24px', textAlign: 'center' }}>
        <h1 style={{
          fontFamily: '"Fraunces", Georgia, serif', fontWeight: 600, fontSize: 28,
          color: '#0f172a', letterSpacing: '-0.02em',
          margin: '0 0 6px', lineHeight: 1.15,
        }}>
          Your property's price,<br />
          <span style={{ color: '#334155' }}>proved</span>
        </h1>
        <p style={{ fontSize: 14, color: '#94a3b8', margin: '0 auto 24px', maxWidth: 240, lineHeight: 1.5 }}>
          Free valuations backed by HM Land Registry. See what others are discovering.
        </p>
        <button
          onClick={() => navigate('/')}
          className="btn-primary"
          style={{ padding: '12px 28px', fontSize: 14 }}
        >
          Value a Property 🏠
        </button>
      </div>

      {/* Live Activity */}
      <div style={{ padding: '0 20px 10px', display: 'flex', alignItems: 'center', gap: 8 }}>
        <span style={{ width: 6, height: 6, borderRadius: '50%', background: '#0f172a', animation: 'livePulse 2s ease-in-out infinite' }} />
        <span className="label-upper" style={{ fontSize: 11, margin: 0 }}>Live Activity</span>
        <span style={{ flex: 1, height: 1, background: '#f1f5f9' }} />
      </div>

      {/* Feed */}
      <div style={{ padding: '0 16px', display: 'flex', flexDirection: 'column', gap: 8 }}>
        {MOCK_FEED.map((event, i) => (
          <div
            key={i}
            className="feed-card"
            style={{ animation: `fadeSlideIn 0.4s ease ${Math.min(i * 50, 700)}ms both` }}
          >
            <div style={{
              width: 36, height: 36, borderRadius: '50%',
              background: event.type === 'unlock' ? 'rgba(15,23,42,0.06)' : event.type === 'value' ? '#f8fafb' : 'rgba(245,158,11,0.1)',
              display: 'flex', alignItems: 'center', justifyContent: 'center',
              fontSize: 15, flexShrink: 0,
            }}>
              {event.icon}
            </div>
            <div style={{ flex: 1, minWidth: 0 }}>
              {event.type === 'unlock' && (
                <div style={{ fontSize: 12, lineHeight: 1.5, color: '#334155' }}>
                  <strong>{event.user}</strong> in <strong>{event.postcode}</strong> unlocked<br />
                  <span style={{ color: '#0f172a', fontWeight: 500 }}>{event.product}</span>
                </div>
              )}
              {event.type === 'value' && (
                <div style={{ fontSize: 12, lineHeight: 1.5, color: '#334155' }}>
                  <strong>{event.user}</strong> in <strong>{event.postcode}</strong> valued a<br />
                  <span style={{ fontWeight: 500 }}>{event.typeLabel}</span>
                </div>
              )}
              {event.type === 'arena' && (
                <div style={{ fontSize: 12, lineHeight: 1.5, color: '#334155' }}>
                  <strong>{event.user}</strong> earned Arena points in <strong>{event.postcode}</strong>
                </div>
              )}
            </div>
            <span style={{ fontSize: 10, color: '#94a3b8', flexShrink: 0 }}>
              {event.time}
            </span>
          </div>
        ))}
      </div>

      {/* Floating CTA */}
      <div style={{
        position: 'fixed', bottom: 80, left: 16, right: 16, zIndex: 50,
      }}>
        <button
          onClick={() => navigate('/')}
          className="btn-primary"
          style={{ width: '100%', padding: 14, fontSize: 14 }}
        >
          Value a Property 🏠
        </button>
      </div>
    </div>
  );
}
