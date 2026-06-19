import { useState, useEffect, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import { valuate } from '../api';
import { saveLastAvm, saveCreditBalance } from '../utils/tgStorage';

export default function ValuatePage() {
  const [address, setAddress] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const inputRef = useRef(null);
  const navigate = useNavigate();

  // ── Telegram MainButton ──────────────────────────────
  useEffect(() => {
    const tg = window.Telegram?.WebApp;
    if (!tg) return;

    const btn = tg.MainButton;
    btn.setText('Value My Property');
    btn.color = '#0e2747';
    btn.textColor = '#f6f3ec';

    const handler = () => handleValuate();
    btn.onClick(handler);

    return () => {
      btn.offClick(handler);
      btn.hide();
    };
  }, [address]);

  useEffect(() => {
    const tg = window.Telegram?.WebApp;
    if (!tg) return;
    if (address.trim().length >= 5 && !loading) {
      tg.MainButton.show();
    } else {
      tg.MainButton.hide();
    }
  }, [address, loading]);

  useEffect(() => {
    window.Telegram?.WebApp?.expand?.();
    setTimeout(() => inputRef.current?.focus(), 300);
  }, []);

  const handleValuate = async () => {
    if (!address.trim() || loading) return;
    setLoading(true);
    setError(null);
    try {
      const result = await valuate(address.trim());
      if (result.ok && result.avm?.ok) {
        await saveLastAvm(result);
        window.Telegram?.WebApp?.HapticFeedback?.notificationOccurred?.('success');
        if (result.credit_balance_gbp !== undefined) {
          await saveCreditBalance(result.credit_balance_gbp);
        }
        navigate('/report', { state: { avmResult: result } });
      } else {
        throw new Error(result.avm?.error || 'Valuation failed');
      }
    } catch (err) {
      const msg = err.response?.data?.detail?.message
        || err.response?.data?.detail?.error
        || err.message
        || 'Valuation failed. Check the address and try again.';
      setError(msg);
      window.Telegram?.WebApp?.HapticFeedback?.notificationOccurred?.('error');
    } finally {
      setLoading(false);
      window.Telegram?.WebApp?.MainButton?.hide();
    }
  };

  return (
    <div style={{ padding: '20px 16px 100px' }}>
      {/* ── Brand header ──────────────────────────────── */}
      <div style={{ textAlign: 'center', marginTop: 16, marginBottom: 24 }}>
        <img
          src="/logo-wordmark.png"
          alt="Honestly"
          style={{ height: 28, margin: '0 auto 8px', opacity: 0.9 }}
          onError={(e) => { e.target.style.display = 'none'; }}
        />
        <div className="brand-label" style={{ color: 'var(--brand-muted)', marginBottom: 12 }}>
          Property Valuation · HM Land Registry
        </div>
        <h1 style={{
          fontFamily: '"Fraunces", Georgia, "Times New Roman", serif',
          fontSize: 28,
          fontWeight: 600,
          lineHeight: 1.04,
          letterSpacing: '-0.02em',
          margin: '0 0 6px',
          color: 'var(--brand-ink)',
        }}>
          What's your property worth?
        </h1>
        <p style={{
          fontFamily: '-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif',
          fontSize: 14,
          color: 'var(--brand-muted)',
          lineHeight: 1.5,
          margin: 0,
          maxWidth: 280,
          marginLeft: 'auto',
          marginRight: 'auto',
        }}>
          Backed by HM Land Registry sold evidence. Free, no sign-up.
        </p>
      </div>

      {/* ── Search input ──────────────────────────────── */}
      <div style={{ position: 'relative', marginBottom: 20 }}>
        <input
          ref={inputRef}
          type="text"
          value={address}
          onChange={(e) => setAddress(e.target.value)}
          onKeyDown={(e) => e.key === 'Enter' && handleValuate()}
          placeholder="Enter address or postcode..."
          className="ui-text"
          style={{
            width: '100%',
            padding: '16px 16px 16px 48px',
            borderRadius: 8,
            border: '1px solid var(--brand-line)',
            background: 'var(--brand-paper)',
            color: 'var(--brand-ink)',
            fontSize: 15,
            outline: 'none',
            boxSizing: 'border-box',
            boxShadow: '0 1px 2px rgba(14, 39, 71, 0.05)',
          }}
        />
        <span style={{
          position: 'absolute', left: 14, top: '50%',
          transform: 'translateY(-50%)', fontSize: 18,
        }}>
          📍
        </span>
      </div>

      {error && (
        <div className="brand-card" style={{
          padding: 12, marginBottom: 16,
          borderColor: 'var(--color-anger)',
          fontSize: 13, color: 'var(--color-anger)',
          lineHeight: 1.5,
        }}>
          {error}
        </div>
      )}

      {/* ── Features ──────────────────────────────────── */}
      <div style={{ display: 'flex', flexDirection: 'column', gap: 10, marginBottom: 24 }}>
        {[
          { icon: '📊', text: 'AVM valuation with strict HM Land Registry comparables' },
          { icon: '📄', text: 'Beautiful report with PDF download and share link' },
          { icon: '🏆', text: 'Daily Arena leaderboard for your postcode' },
          { icon: '🚀', text: 'Micro-upsells: counter-offer letters, planning checks, and more' },
        ].map((feat, i) => (
          <div key={i} style={{
            display: 'flex', alignItems: 'center', gap: 12,
            padding: '10px 12px',
            background: 'var(--brand-paper)',
            borderRadius: 8,
            border: '1px solid var(--brand-line)',
          }}>
            <span style={{ fontSize: 16 }}>{feat.icon}</span>
            <span className="ui-text" style={{ fontSize: 13, color: 'var(--brand-ink)' }}>
              {feat.text}
            </span>
          </div>
        ))}
      </div>

      {/* ── CTA ───────────────────────────────────────── */}
      <button
        id="valuate-fallback-btn"
        onClick={handleValuate}
        disabled={loading || address.trim().length < 5}
        className="brand-cta"
        style={{
          width: '100%',
          display: window.Telegram?.WebApp?.MainButton ? 'none' : 'block',
          fontSize: 16,
          padding: '16px 24px',
        }}
      >
        {loading ? 'Valuing...' : 'Value My Property'}
      </button>

      {/* ── Brand footer ──────────────────────────────── */}
      <div className="brand-hair" style={{ margin: '24px 0 12px' }} />
      <p className="brand-label" style={{
        textAlign: 'center', color: 'var(--brand-muted)',
        fontSize: 10, letterSpacing: '0.18em',
      }}>
        Honestly · your property's price, proved
      </p>
    </div>
  );
}
