import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { loadCreditBalance } from '../utils/tgStorage';

export default function FeedPage() {
  const navigate = useNavigate();
  const [balance, setBalance] = useState(0);
  const [recent, setRecent] = useState(null);

  useEffect(() => {
    window.Telegram?.WebApp?.expand?.();
    loadCreditBalance().then(b => setBalance(b || 0));
    try {
      const avm = JSON.parse(sessionStorage.getItem('honestly_last_avm') || '{}');
      if (avm.avm) setRecent(avm.avm);
    } catch {}
  }, []);

  return (
    <div style={{ padding: '0 0 100px' }}>
      {/* Header */}
      <div style={{
        padding: '16px 20px',
        display: 'flex', justifyContent: 'space-between', alignItems: 'center',
        borderBottom: '1px solid var(--brand-line)',
      }}>
        <span style={{ fontFamily: '"Fraunces", Georgia, serif', fontWeight: 600, fontSize: 18, color: 'var(--brand-ink)' }}>
          Honestly
        </span>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <span className="ui-text" style={{ fontSize: 13, color: 'var(--brand-muted)' }}>
            {'\u00a3'}{balance.toFixed(2)}
          </span>
          <button
            onClick={() => navigate('/store')}
            style={{
              width: 22, height: 22, borderRadius: '50%',
              background: 'var(--brand-green)', color: '#fff',
              border: 'none', fontSize: 14, cursor: 'pointer',
              display: 'flex', alignItems: 'center', justifyContent: 'center',
              padding: 0,
            }}
          >
            +
          </button>
        </div>
      </div>

      {/* Hero */}
      <div style={{ padding: '48px 20px 36px', textAlign: 'center' }}>
        <h1 style={{
          fontFamily: '"Fraunces", Georgia, serif',
          fontWeight: 500, fontSize: 30,
          color: 'var(--brand-ink)',
          letterSpacing: '-0.02em',
          lineHeight: 1.15,
          margin: '0 0 12px',
        }}>
          Your property's price,<br />
          <span style={{ color: 'var(--brand-green)' }}>proved</span>
        </h1>
        <p className="ui-text" style={{
          fontSize: 14, color: 'var(--brand-muted)',
          lineHeight: 1.6, margin: '0 auto 28px',
          maxWidth: 260,
        }}>
          Get a free valuation backed by HM Land Registry sold prices. 60 seconds, no sign-up.
        </p>
        <button
          onClick={() => navigate('/')}
          style={{
            padding: '14px 36px', borderRadius: 8,
            background: 'var(--brand-dark)', color: 'var(--brand-cream)',
            border: 'none', fontSize: 15, fontWeight: 500, cursor: 'pointer',
            letterSpacing: '-0.01em',
          }}
        >
          Value a Property
        </button>
      </div>

      {/* Stats */}
      <div style={{ padding: '0 20px', display: 'flex', gap: 10, marginBottom: 24 }}>
        {[
          { n: '880K+', l: 'Sold records' },
          { n: '10', l: 'Data tools' },
          { n: '60s', l: 'Valuation time' },
        ].map(s => (
          <div key={s.l} style={{
            flex: 1, padding: '12px 8px', textAlign: 'center',
            border: '1px solid var(--brand-line)', borderRadius: 8,
          }}>
            <div style={{ fontFamily: '"Fraunces", Georgia, serif', fontSize: 18, fontWeight: 600, color: 'var(--brand-green)' }}>
              {s.n}
            </div>
            <div className="ui-text" style={{ fontSize: 10, color: 'var(--brand-muted)', marginTop: 2 }}>{s.l}</div>
          </div>
        ))}
      </div>

      {/* Recent */}
      {recent && (
        <div style={{ padding: '0 20px' }}>
          <div className="ui-text" style={{ fontSize: 11, color: 'var(--brand-muted)', textTransform: 'uppercase', letterSpacing: '0.12em', marginBottom: 8 }}>
            Recent valuation
          </div>
          <div style={{
            display: 'flex', alignItems: 'center', gap: 12,
            padding: '12px 14px',
            border: '1px solid var(--brand-line)', borderRadius: 8,
          }}>
            <div style={{
              width: 36, height: 36, borderRadius: 8,
              background: 'var(--brand-dark)', color: 'var(--brand-cream)',
              display: 'flex', alignItems: 'center', justifyContent: 'center',
              fontSize: 12, fontWeight: 600,
              fontFamily: '"Fraunces", Georgia, serif',
            }}>
              {'\u00a3'}
            </div>
            <div style={{ flex: 1 }}>
              <div className="ui-text" style={{ fontSize: 13, fontWeight: 500, color: 'var(--brand-ink)' }}>
                {recent.address?.slice(0, 35)}
              </div>
              <div className="ui-text" style={{ fontSize: 11, color: 'var(--brand-muted)' }}>
                {'\u00a3'}{Number(recent.central).toLocaleString('en-GB')}
              </div>
            </div>
            <button
              onClick={() => navigate('/report')}
              style={{
                padding: '6px 14px', borderRadius: 6,
                background: 'var(--brand-dark)', color: 'var(--brand-cream)',
                border: 'none', fontSize: 11, fontWeight: 500, cursor: 'pointer',
              }}
            >
              Open
            </button>
          </div>
        </div>
      )}

      {/* Footer */}
      <div style={{ padding: '24px 20px' }}>
        <div style={{ height: 1, background: 'var(--brand-line)', marginBottom: 10 }} />
        <p className="ui-text" style={{ fontSize: 10, color: 'var(--brand-muted)', lineHeight: 1.6, textAlign: 'center' }}>
          Data from HM Land Registry, EPC Register, and ONS. Automated valuation, not a formal survey.
        </p>
      </div>
    </div>
  );
}
