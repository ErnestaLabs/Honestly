import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { getVibe, getLeaderboard, getRoom } from '../api';
import { loadCreditBalance } from '../utils/tgStorage';

const MOCK_EVENTS = [
  { type: 'unlock', user: 'Alex', postcode: 'SW16', product: 'The Lowball Counter-Email', icon: '😡', time: '2m ago' },
  { type: 'unlock', user: 'Sam', postcode: 'E1', product: 'The Deal Autopsy', icon: '😰', time: '4m ago' },
  { type: 'value', user: 'Jordan', postcode: 'M1', type_label: 'Flat', value: '£285k', time: '7m ago' },
  { type: 'unlock', user: 'Riley', postcode: 'N22', product: 'Planning Permission Oracle', icon: '😴', time: '12m ago' },
  { type: 'value', user: 'Taylor', postcode: 'SE15', type_label: 'Terraced House', value: '£620k', time: '18m ago' },
  { type: 'unlock', user: 'Morgan', postcode: 'B1', product: 'The Gentrification Radar', icon: '💰', time: '23m ago' },
  { type: 'value', user: 'Casey', postcode: 'LS1', type_label: 'Semi-Detached', value: '£340k', time: '31m ago' },
  { type: 'unlock', user: 'Avery', postcode: 'SW16', product: 'Council Tax Challenger', icon: '😡', time: '38m ago' },
  { type: 'arena', user: 'Quinn', postcode: 'SW16', score: '+10', time: '45m ago' },
  { type: 'unlock', user: 'Jamie', postcode: 'EH1', product: 'Syndicate Street Map', icon: '💰', time: '51m ago' },
  { type: 'value', user: 'Drew', postcode: 'CF10', type_label: 'Flat', value: '£195k', time: '1h ago' },
  { type: 'unlock', user: 'Blake', postcode: 'G1', product: 'Neighbor Extension Blueprint', icon: '🔥', time: '1h ago' },
  { type: 'arena', user: 'Skyler', postcode: 'N22', score: '+5', time: '1h ago' },
  { type: 'unlock', user: 'Reese', postcode: 'BS1', product: 'Leasehold Trap X-Ray', icon: '😰', time: '1h ago' },
  { type: 'value', user: 'Harper', postcode: 'OX1', type_label: 'Detached', value: '£890k', time: '2h ago' },
  { type: 'unlock', user: 'Sage', postcode: 'M1', product: 'The Architect\'s Vision', icon: '💰', time: '2h ago' },
  { type: 'unlock', user: 'Emery', postcode: 'SE15', product: 'The Stealth Listing Sniper', icon: '🔥', time: '2h ago' },
  { type: 'arena', user: 'Rowan', postcode: 'SW16', score: '+3', time: '3h ago' },
  { type: 'value', user: 'Finley', postcode: 'E17', type_label: 'Terraced House', value: '£475k', time: '3h ago' },
  { type: 'unlock', user: 'Parker', postcode: 'N1', product: 'Council Tax Challenger', icon: '😡', time: '4h ago' },
];

function formatPrice(n) {
  if (!n) return '';
  return '\u00a3' + Number(n).toLocaleString('en-GB');
}

export default function FeedPage() {
  const navigate = useNavigate();
  const [creditBalance, setCreditBalance] = useState(0);
  const [postcode, setPostcode] = useState('');
  const [vibe, setVibe] = useState(null);
  const [leaderboard, setLeaderboard] = useState([]);

  useEffect(() => {
    window.Telegram?.WebApp?.expand?.();
    loadCreditBalance().then(b => setCreditBalance(b || 0));
    // Try to get postcode from last AVM
    try {
      const avm = JSON.parse(sessionStorage.getItem('honestly_last_avm') || '{}');
      if (avm.avm?.postcode) setPostcode(avm.avm.postcode);
    } catch {}
  }, []);

  const handleValuate = () => {
    window.Telegram?.WebApp?.HapticFeedback?.impactOccurred?.('light');
    navigate('/');
  };

  const handleTopUp = () => {
    window.Telegram?.WebApp?.HapticFeedback?.impactOccurred?.('medium');
    navigate('/store');
  };

  const renderEvent = (e, i) => {
    if (e.type === 'unlock') {
      return (
        <div key={i} className="feed-card">
          <div className="avatar" style={{ background: 'var(--brand-green)', color: 'white' }}>
            {e.user[0]}
          </div>
          <div style={{ flex: 1, minWidth: 0 }}>
            <span className="ui-text" style={{ fontSize: 13, lineHeight: 1.4 }}>
              <strong>{e.user}</strong> in <strong>{e.postcode}</strong> just unlocked<br />
              <span style={{ color: 'var(--brand-green)', fontWeight: 500 }}>{e.product}</span>
            </span>
          </div>
          <span style={{ fontSize: 18 }}>{e.icon}</span>
        </div>
      );
    }
    if (e.type === 'value') {
      return (
        <div key={i} className="feed-card">
          <div className="avatar">🏠</div>
          <div style={{ flex: 1, minWidth: 0 }}>
            <span className="ui-text" style={{ fontSize: 13, lineHeight: 1.4 }}>
              <strong>{e.user}</strong> in <strong>{e.postcode}</strong> just valued a<br />
              <span style={{ color: 'var(--brand-dark)', fontWeight: 500 }}>{e.type_label} · {e.value}</span>
            </span>
          </div>
          <span style={{ fontSize: 11, color: 'var(--brand-muted)', whiteSpace: 'nowrap' }}>{e.time}</span>
        </div>
      );
    }
    if (e.type === 'arena') {
      return (
        <div key={i} className="feed-card">
          <div className="avatar" style={{ background: '#d89a32', color: 'white' }}>🏆</div>
          <div style={{ flex: 1, minWidth: 0 }}>
            <span className="ui-text" style={{ fontSize: 13, lineHeight: 1.4 }}>
              <strong>{e.user}</strong> earned <strong>{e.score}</strong> Arena points<br />
              in <strong>{e.postcode}</strong> leaderboard
            </span>
          </div>
          <span style={{ fontSize: 11, color: 'var(--brand-muted)', whiteSpace: 'nowrap' }}>{e.time}</span>
        </div>
      );
    }
    return null;
  };

  return (
    <div style={{ padding: '0 0 100px' }}>
      {/* ── Top Bar ────────────────────────────────────── */}
      <div style={{
        position: 'sticky', top: 0, zIndex: 40,
        background: 'var(--brand-cream)',
        borderBottom: '1px solid var(--brand-line)',
        padding: '12px 16px',
        display: 'flex', justifyContent: 'space-between', alignItems: 'center',
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <div className="avatar" style={{ width: 36, height: 36, background: 'var(--brand-dark)', color: 'var(--brand-cream)', fontWeight: 700 }}>
            H
          </div>
          <div>
            <div style={{ fontFamily: '"Fraunces", Georgia, serif', fontWeight: 600, fontSize: 15, color: 'var(--brand-ink)' }}>
              Honestly
            </div>
            <div className="brand-label" style={{ fontSize: 8, color: 'var(--brand-muted)', letterSpacing: '0.18em' }}>
              Live Feed
            </div>
          </div>
        </div>
        <button className="credit-pill" onClick={handleTopUp}>
          <span style={{ opacity: 0.7 }}>⚡</span>
          {'\u00a3'}{creditBalance.toFixed(2)}
          <span className="plus-btn">+</span>
        </button>
      </div>

      {/* ── Live Ticker ────────────────────────────────── */}
      <div style={{ padding: '12px 16px' }}>
        <div className="brand-label" style={{ fontSize: 10, color: 'var(--brand-muted)', marginBottom: 8, display: 'flex', alignItems: 'center', gap: 6 }}>
          <span style={{ display: 'inline-block', width: 6, height: 6, borderRadius: '50%', background: 'var(--brand-green)', animation: 'pulse 2s infinite' }} />
          LIVE · Community Activity
        </div>

        <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
          {MOCK_EVENTS.slice(0, 10).map((e, i) => renderEvent(e, i))}
        </div>

        {/* ── Vibe + Leaderboard section ──────────────── */}
        {postcode && (
          <div style={{ marginTop: 16, display: 'flex', flexDirection: 'column', gap: 10 }}>
            <div className="brand-hair" style={{ margin: '4px 0' }} />
            <div className="brand-label" style={{ fontSize: 10, color: 'var(--brand-muted)' }}>
              📍 {postcode} · Community
            </div>
            <div className="feed-card" style={{ justifyContent: 'space-between' }}>
              <span className="ui-text" style={{ fontSize: 13 }}>Vibe Score</span>
              <span style={{ fontFamily: '"Fraunces", Georgia, serif', fontSize: 18, fontWeight: 600, color: 'var(--brand-green)' }}>
                {vibe?.vibe_score || '--'}
              </span>
            </div>
            <div className="feed-card" style={{ justifyContent: 'center' }}>
              <span style={{ fontSize: 14 }}>💬</span>
              <span className="ui-text" style={{ fontSize: 13 }}>Enter {postcode} Room</span>
            </div>
          </div>
        )}

        {/* ── More events (scroll for more) ────────────── */}
        <div style={{ marginTop: 16, display: 'flex', flexDirection: 'column', gap: 8, opacity: 0.7 }}>
          {MOCK_EVENTS.slice(10, 20).map((e, i) => renderEvent(e, i + 10))}
        </div>
      </div>

      {/* ── Floating CTA ──────────────────────────────── */}
      <div className="floating-cta">
        <button
          onClick={handleValuate}
          className="unlock-button"
          style={{ boxShadow: '0 4px 24px rgba(14, 39, 71, 0.4)', fontSize: 16 }}
        >
          🔍 Value a Property
        </button>
      </div>
    </div>
  );
}

// Pulse animation for LIVE dot
const style = document.createElement('style');
style.textContent = `
  @keyframes pulse { 0%, 100% { opacity: 1; } 50% { opacity: 0.3; } }
`;
document.head.appendChild(style);
