import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { loadCreditBalance } from '../utils/tgStorage';

export default function FeedPage() {
  const navigate = useNavigate();
  const [creditBalance, setCreditBalance] = useState(0);
  const [recentPostcode, setRecentPostcode] = useState('');

  useEffect(() => {
    window.Telegram?.WebApp?.expand?.();
    loadCreditBalance().then(b => setCreditBalance(b || 0));
    try {
      const avm = JSON.parse(sessionStorage.getItem('honestly_last_avm') || '{}');
      if (avm.avm?.postcode) setRecentPostcode(avm.avm.postcode);
    } catch {}
  }, []);

  const handleNewValuation = () => {
    window.Telegram?.WebApp?.HapticFeedback?.impactOccurred?.('light');
    navigate('/');
  };

  return (
    <div style={{ padding: '0 0 100px' }}>
      {/* ── Top Bar ────────────────────────────────────── */}
      <div style={{
        padding: '14px 16px',
        borderBottom: '1px solid var(--brand-line)',
        display: 'flex', justifyContent: 'space-between', alignItems: 'center',
      }}>
        <img
          src="/logo-wordmark.png"
          alt="Honestly"
          style={{ height: 22, opacity: 0.9 }}
          onError={(e) => {
            e.target.style.display = 'none';
            e.target.parentNode.innerHTML = '<span style="font-family:Fraunces,Georgia,serif;font-weight:600;font-size:18px;color:var(--brand-ink)">Honestly</span>';
          }}
        />
        <div style={{
          display: 'flex', alignItems: 'center', gap: 6,
          background: 'var(--brand-paper)',
          border: '1px solid var(--brand-line)',
          borderRadius: 8,
          padding: '6px 12px',
        }}>
          <span className="ui-text" style={{ fontSize: 12, color: 'var(--brand-muted)' }}>
            {'\u00a3'}{creditBalance.toFixed(2)}
          </span>
          <button
            onClick={() => { window.Telegram?.WebApp?.HapticFeedback?.impactOccurred?.('medium'); navigate('/store'); }}
            style={{
              width: 18, height: 18, borderRadius: '50%',
              background: 'var(--brand-green)', color: '#fff',
              border: 'none', fontSize: 12, cursor: 'pointer',
              display: 'flex', alignItems: 'center', justifyContent: 'center',
              padding: 0, lineHeight: 1,
            }}
          >
            +
          </button>
        </div>
      </div>

      {/* ── Hero Section ──────────────────────────────── */}
      <div style={{ padding: '32px 16px 24px', textAlign: 'center' }}>
        <h1 style={{
          fontFamily: '"Fraunces", Georgia, serif',
          fontSize: 28, fontWeight: 600,
          color: 'var(--brand-ink)',
          margin: '0 0 6px', letterSpacing: '-0.02em',
        }}>
          Your property's price, <span style={{ color: 'var(--brand-green)' }}>proved</span>
        </h1>
        <p className="ui-text" style={{
          fontSize: 14, color: 'var(--brand-muted)',
          margin: '0 auto 24px', maxWidth: 260, lineHeight: 1.5,
        }}>
          Get a free, data-backed valuation in 60 seconds. Powered by HM Land Registry.
        </p>

        <button
          onClick={handleNewValuation}
          style={{
            padding: '16px 40px', borderRadius: 8,
            background: 'var(--brand-dark)', color: 'var(--brand-cream)',
            border: 'none', fontSize: 16, fontWeight: 600, cursor: 'pointer',
            fontFamily: '-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif',
            letterSpacing: '-0.01em',
          }}
        >
          Value a Property
        </button>
      </div>

      {/* ── Quick Stats ───────────────────────────────── */}
      <div style={{ padding: '0 16px 20px' }}>
        <div style={{
          display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10,
        }}>
          <div style={{
            background: 'var(--brand-paper)', border: '1px solid var(--brand-line)',
            borderRadius: 8, padding: '14px', textAlign: 'center',
          }}>
            <div style={{ fontFamily: '"Fraunces", Georgia, serif', fontSize: 20, fontWeight: 600, color: 'var(--brand-green)' }}>
              880K+
            </div>
            <div className="ui-text" style={{ fontSize: 11, color: 'var(--brand-muted)', marginTop: 2 }}>
              Sold records indexed
            </div>
          </div>
          <div style={{
            background: 'var(--brand-paper)', border: '1px solid var(--brand-line)',
            borderRadius: 8, padding: '14px', textAlign: 'center',
          }}>
            <div style={{ fontFamily: '"Fraunces", Georgia, serif', fontSize: 20, fontWeight: 600, color: 'var(--brand-dark)' }}>
              10
            </div>
            <div className="ui-text" style={{ fontSize: 11, color: 'var(--brand-muted)', marginTop: 2 }}>
              Data intelligence tools
            </div>
          </div>
        </div>
      </div>

      {/* ── Recent Activity (minimal) ──────────────────── */}
      {recentPostcode && (
        <div style={{ padding: '0 16px' }}>
          <div className="brand-label" style={{ fontSize: 10, color: 'var(--brand-muted)', letterSpacing: '0.18em', marginBottom: 8 }}>
            RECENT
          </div>
          <div style={{
            background: 'var(--brand-paper)', border: '1px solid var(--brand-line)',
            borderRadius: 8, padding: '12px 14px',
            display: 'flex', alignItems: 'center', gap: 10,
          }}>
            <div style={{
              width: 28, height: 28, borderRadius: 6,
              background: 'var(--brand-dark)', color: 'var(--brand-cream)',
              display: 'flex', alignItems: 'center', justifyContent: 'center',
              fontSize: 12, fontWeight: 600, fontFamily: '"Fraunces", Georgia, serif',
            }}>
              V
            </div>
            <div style={{ flex: 1 }}>
              <div className="ui-text" style={{ fontSize: 13, fontWeight: 500, color: 'var(--brand-ink)' }}>
                Valuation &mdash; {recentPostcode}
              </div>
              <div className="ui-text" style={{ fontSize: 11, color: 'var(--brand-muted)' }}>
                Tap to view full report
              </div>
            </div>
            <button
              onClick={() => navigate('/report')}
              style={{
                padding: '6px 12px', borderRadius: 6,
                background: 'var(--brand-dark)', color: 'var(--brand-cream)',
                border: 'none', fontSize: 11, fontWeight: 500, cursor: 'pointer',
                fontFamily: '-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif',
              }}
            >
              View
            </button>
          </div>
        </div>
      )}

      {/* ── Bottom Info ───────────────────────────────── */}
      <div style={{ padding: '24px 16px' }}>
        <div className="brand-hair" style={{ marginBottom: 12 }} />
        <p className="ui-text" style={{
          fontSize: 11, color: 'var(--brand-muted)', textAlign: 'center', lineHeight: 1.6,
        }}>
          Data sourced from HM Land Registry Price Paid Data, EPC Register, and ONS.
          Honestly is not a surveyor. All figures are indicative.
        </p>
      </div>
    </div>
  );
}
