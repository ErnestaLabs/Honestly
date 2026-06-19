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
    btn.color = '#007aff';
    btn.textColor = '#ffffff';

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

  // ── Auto-focus on mount ──────────────────────────────
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
        // Store the full result in CloudStorage (survives TG background kills)
        await saveLastAvm(result);
        window.Telegram?.WebApp?.HapticFeedback?.notificationOccurred?.('success');
        // Also save credit balance if available
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
    <div style={{ padding: '20px 16px 100px', display: 'flex', flexDirection: 'column', gap: 16 }}>
      <div style={{ textAlign: 'center', marginTop: 20 }}>
        <div style={{ fontSize: 48, marginBottom: 4 }}>🏠</div>
        <h1 style={{ fontSize: 26, fontWeight: 700, margin: '0 0 4px' }}>
          What's your property worth?
        </h1>
        <p style={{ fontSize: 14, color: 'var(--tg-hint)', margin: 0 }}>
          Backed by HM Land Registry sold evidence. Free, no sign-up required.
        </p>
      </div>

      <div style={{ position: 'relative', marginTop: 8 }}>
        <input
          ref={inputRef}
          type="text"
          value={address}
          onChange={(e) => setAddress(e.target.value)}
          onKeyDown={(e) => e.key === 'Enter' && handleValuate()}
          placeholder="Enter address or postcode..."
          style={{
            width: '100%',
            padding: '16px 16px 16px 48px',
            borderRadius: 14,
            border: '1px solid var(--tg-section-separator)',
            background: 'var(--tg-secondary-bg)',
            color: 'var(--tg-text)',
            fontSize: 16,
            outline: 'none',
            boxSizing: 'border-box',
          }}
        />
        <span style={{
          position: 'absolute',
          left: 14,
          top: '50%',
          transform: 'translateY(-50%)',
          fontSize: 20,
        }}>
          📍
        </span>
      </div>

      {error && (
        <div style={{
          background: 'rgba(255,69,58,0.1)',
          borderRadius: 12,
          padding: 12,
          fontSize: 13,
          color: 'var(--color-anger)',
          lineHeight: 1.5,
        }}>
          {error}
        </div>
      )}

      {/* Features list */}
      <div style={{ marginTop: 8, display: 'flex', flexDirection: 'column', gap: 10 }}>
        {[
          { icon: '📊', text: 'AVM valuation with strict HM Land Registry comparables' },
          { icon: '📄', text: 'Beautiful report with PDF download and share link' },
          { icon: '🏆', text: 'Daily Arena leaderboard for your postcode' },
          { icon: '🚀', text: 'Micro-upsells: counter-offer letters, planning checks, and more' },
        ].map((feat, i) => (
          <div key={i} style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
            <span style={{ fontSize: 18 }}>{feat.icon}</span>
            <span style={{ fontSize: 14, color: 'var(--tg-text)' }}>{feat.text}</span>
          </div>
        ))}
      </div>

      {/* Mobile fallback button (hidden when TG MainButton is available) */}
      <button
        id="valuate-fallback-btn"
        onClick={handleValuate}
        disabled={loading || address.trim().length < 5}
        style={{
          display: window.Telegram?.WebApp?.MainButton ? 'none' : 'block',
          width: '100%',
          padding: '16px',
          borderRadius: 14,
          background: loading ? 'var(--tg-hint)' : 'var(--tg-button)',
          color: 'var(--tg-button-text)',
          border: 'none',
          fontSize: 17,
          fontWeight: 600,
          cursor: loading || address.trim().length < 5 ? 'not-allowed' : 'pointer',
          opacity: loading || address.trim().length < 5 ? 0.6 : 1,
          marginTop: 8,
        }}
      >
        {loading ? 'Valuing...' : 'Value My Property'}
      </button>
    </div>
  );
}
