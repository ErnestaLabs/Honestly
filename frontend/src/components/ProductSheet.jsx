import { useState } from 'react';
import { purchaseProduct, createInvoice } from '../api';
import { saveCreditBalance, loadCreditBalance } from '../utils/tgStorage';

export default function ProductSheet({ product, valuationContext, onClose, onComplete }) {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [result, setResult] = useState(null);
  const [balance, setBalance] = useState(0);

  useState(() => { loadCreditBalance().then(b => setBalance(b || 0)); }, []);

  if (!product) return null;

  const energy = product.energy || Math.round((product.gbp || 1.49) * 100);

  const handlePurchase = async () => {
    setLoading(true);
    setError(null);

    try {
      const res = await purchaseProduct(product.id || product.product_id, valuationContext);
      if (res.ok) {
        window.Telegram?.WebApp?.HapticFeedback?.notificationOccurred?.('success');
        setResult(res);
        if (res.remaining_credits_gbp !== undefined) await saveCreditBalance(res.remaining_credits_gbp);
        onComplete?.(res);
        return;
      }
    } catch (err) {
      const detail = err.response?.data?.detail;
      if (err.response?.status === 402) {
        // Insufficient — fall through to Stars
      } else if (err.response?.status === 403) {
        setError('Requires a higher tier');
        window.Telegram?.WebApp?.HapticFeedback?.notificationOccurred?.('error');
        setLoading(false);
        return;
      } else {
        setError(detail?.message || err.message || 'Failed');
        window.Telegram?.WebApp?.HapticFeedback?.notificationOccurred?.('error');
        setLoading(false);
        return;
      }
    }

    // Stars fallback
    try {
      const invoice = await createInvoice({ productId: product.id || product.product_id });
      if (!invoice.ok || !invoice.invoice_url) throw new Error('Invoice failed');
      const tg = window.Telegram?.WebApp;
      if (!tg?.openInvoice) throw new Error('openInvoice unavailable');
      tg.openInvoice(invoice.invoice_url, async (status) => {
        if (status === 'paid') {
          window.Telegram?.WebApp?.HapticFeedback?.notificationOccurred?.('success');
          try {
            const retry = await purchaseProduct(product.id || product.product_id, valuationContext);
            if (retry.ok) setResult(retry);
            else setResult({ ok: true });
          } catch { setResult({ ok: true }); }
          onComplete?.({ ok: true });
        } else if (status === 'cancelled') {
          setError('Cancelled');
          window.Telegram?.WebApp?.HapticFeedback?.notificationOccurred?.('warning');
        } else {
          setError('Failed');
          window.Telegram?.WebApp?.HapticFeedback?.notificationOccurred?.('error');
        }
        setLoading(false);
      });
    } catch (err) {
      setError(err.message || 'Failed');
      window.Telegram?.WebApp?.HapticFeedback?.notificationOccurred?.('error');
      setLoading(false);
    }
  };

  return (
    <>
      <div className="sheet-backdrop" onClick={loading ? null : () => onClose?.()} />
      <div className="sheet" style={{ background: 'var(--brand-cream)' }}>
        <div style={{ display: 'flex', justifyContent: 'center', padding: '12px 0 4px' }}>
          <div style={{ width: 40, height: 4, borderRadius: 2, background: 'var(--brand-line)', opacity: 0.5 }} />
        </div>

        <div style={{ padding: '4px 24px 36px' }}>
          {result ? (
            <div style={{ textAlign: 'center', padding: '20px 0' }}>
              <div style={{ fontSize: 56, marginBottom: 12 }}>✅</div>
              <h2 style={{ fontFamily: '"Fraunces", Georgia, serif', fontSize: 24, fontWeight: 600, margin: '0 0 4px' }}>
                Unlocked!
              </h2>
              <p className="ui-text" style={{ color: 'var(--brand-muted)', fontSize: 14, marginBottom: 20 }}>
                Your exclusive insight is ready.
              </p>
              <button onClick={() => onClose?.()} className="purchase-button" style={{ fontSize: 16 }}>
                Done
              </button>
            </div>
          ) : (
            <>
              <p className="brand-label" style={{ textAlign: 'center', fontSize: 10, color: 'var(--brand-muted)', letterSpacing: '0.2em', marginBottom: 16 }}>
                Send Tribute to Unlock
              </p>

              <div style={{ textAlign: 'center', marginBottom: 4 }}>
                <div style={{
                  fontFamily: '"Fraunces", Georgia, serif',
                  fontSize: 52, fontWeight: 700, color: 'var(--brand-ink)',
                  lineHeight: 1, marginBottom: 4,
                }}>
                  {energy}
                </div>
                <p className="ui-text" style={{ fontSize: 14, color: 'var(--brand-muted)', margin: 0 }}>Energy</p>
              </div>

              <p className="ui-text" style={{ textAlign: 'center', fontSize: 13, color: 'var(--brand-ink)', fontWeight: 500, margin: '0 0 20px' }}>
                {product.title || product.name || 'Exclusive Insight'}
              </p>

              <div style={{ textAlign: 'center', marginBottom: 20 }}>
                <span className="ui-text" style={{
                  fontSize: 12, color: 'var(--brand-muted)',
                  background: 'var(--brand-paper)', padding: '4px 12px',
                  borderRadius: 999, border: '1px solid var(--brand-line)',
                }}>
                  Balance: {'\u00a3'}{(balance || 0).toFixed(2)} &middot; {(balance * 100) >= energy ? 'Sufficient' : 'Insufficient'}
                </span>
              </div>

              {error && (
                <div className="ui-text" style={{
                  background: 'rgba(199,58,58,0.08)', borderRadius: 8, padding: 10,
                  marginBottom: 12, fontSize: 12, color: '#c73a3a', textAlign: 'center',
                }}>
                  {error}
                </div>
              )}

              <button
                onClick={handlePurchase}
                disabled={loading}
                style={{
                  width: '100%', padding: 18, borderRadius: 12, border: 'none',
                  fontSize: 17, fontWeight: 700, cursor: loading ? 'not-allowed' : 'pointer',
                  fontFamily: '-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif',
                  background: 'linear-gradient(135deg, var(--brand-dark), #1a3a6b)',
                  color: 'var(--brand-cream)',
                  boxShadow: '0 4px 24px rgba(14,39,71,0.35)',
                  opacity: loading ? 0.6 : 1,
                }}
              >
                {loading ? (
                  <span style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 8 }}>
                    <span style={{
                      display: 'inline-block', width: 18, height: 18,
                      border: '2px solid var(--brand-cream)', borderTopColor: 'transparent',
                      borderRadius: '50%', animation: 'spin 0.8s linear infinite',
                    }} />
                    Processing...
                  </span>
                ) : (
                  'Unlock Now \ud83c\udf81'
                )}
              </button>

              <p className="ui-text" style={{
                textAlign: 'center', color: 'var(--brand-muted)',
                fontSize: 12, marginTop: 14, cursor: 'pointer',
              }} onClick={() => onClose?.()}>
                Not now
              </p>
            </>
          )}
        </div>
      </div>

      <style>{`@keyframes spin { to { transform: rotate(360deg); } }`}</style>
    </>
  );
}
