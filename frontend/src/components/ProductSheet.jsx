import { useState } from 'react';
import { purchaseProduct, createInvoice } from '../api';
import { saveCreditBalance } from '../utils/tgStorage';

export default function ProductSheet({ product, valuationContext, onClose, onComplete }) {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [result, setResult] = useState(null);

  if (!product) return null;

  const credits = product.credits || (product.gbp ? Math.round(product.gbp * 100) : 149);

  const handlePurchase = async () => {
    setLoading(true);
    setError(null);

    try {
      const res = await purchaseProduct(product.id || product.product_id, valuationContext);
      if (res.ok) {
        window.Telegram?.WebApp?.HapticFeedback?.notificationOccurred?.('success');
        setResult(res);
        if (res.remaining_credits_gbp !== undefined) {
          await saveCreditBalance(res.remaining_credits_gbp);
        }
        onComplete?.(res);
        return;
      }
    } catch (err) {
      const detail = err.response?.data?.detail;
      if (err.response?.status === 402) {
        // Insufficient credits — try Stars payment
      } else if (err.response?.status === 403) {
        setError('Requires a higher subscription tier.');
        window.Telegram?.WebApp?.HapticFeedback?.notificationOccurred?.('error');
        setLoading(false);
        return;
      } else {
        setError(detail?.message || err.message || 'Purchase failed');
        window.Telegram?.WebApp?.HapticFeedback?.notificationOccurred?.('error');
        setLoading(false);
        return;
      }
    }

    // Fallback: Telegram invoice
    try {
      const invoice = await createInvoice({ productId: product.id || product.product_id });
      if (!invoice.ok || !invoice.invoice_url) {
        throw new Error(invoice.error || 'Invoice creation failed');
      }
      const tg = window.Telegram?.WebApp;
      if (!tg?.openInvoice) {
        throw new Error('Telegram WebApp.openInvoice not available');
      }
      tg.openInvoice(invoice.invoice_url, async (status) => {
        if (status === 'paid') {
          window.Telegram?.WebApp?.HapticFeedback?.notificationOccurred?.('success');
          try {
            const retry = await purchaseProduct(product.id || product.product_id, valuationContext);
            if (retry.ok) setResult(retry);
            else setResult({ ok: true, remaining_credits_gbp: 'unlocked' });
          } catch {
            setResult({ ok: true, remaining_credits_gbp: 'unlocked' });
          }
        } else if (status === 'cancelled') {
          setError('Payment cancelled');
          window.Telegram?.WebApp?.HapticFeedback?.notificationOccurred?.('warning');
        } else {
          setError('Payment failed. Try again.');
          window.Telegram?.WebApp?.HapticFeedback?.notificationOccurred?.('error');
        }
      });
    } catch (err) {
      setError(err.message || 'Payment failed');
      window.Telegram?.WebApp?.HapticFeedback?.notificationOccurred?.('error');
    } finally {
      setLoading(false);
    }
  };

  return (
    <>
      <div className="sheet-backdrop" onClick={loading ? null : () => onClose?.()} />
      <div className="sheet" style={{ background: 'var(--brand-cream)' }}>
        {/* Handle */}
        <div style={{ display: 'flex', justifyContent: 'center', padding: '10px 0 4px' }}>
          <div style={{ width: 36, height: 4, borderRadius: 2, background: 'var(--brand-line)', opacity: 0.6 }} />
        </div>

        <div style={{ padding: '8px 24px 32px' }}>
          {result ? (
            // ── Success ──────────────────────────────────
            <div style={{ textAlign: 'center', padding: '20px 0' }}>
              <div style={{ fontSize: 56, marginBottom: 12 }}>✅</div>
              <h2 style={{ fontFamily: '"Fraunces", Georgia, serif', fontSize: 22, fontWeight: 600, margin: '0 0 4px' }}>
                Unlocked!
              </h2>
              <p className="ui-text" style={{ color: 'var(--brand-muted)', fontSize: 14, margin: '0 0 16px' }}>
                {result.charged_gbp > 0 ? `Charged \u00a3${result.charged_gbp?.toFixed(2)}` : 'Unlocked via Telegram Stars'}
                {result.remaining_credits_gbp !== undefined && typeof result.remaining_credits_gbp === 'number' &&
                  ` · \u00a3${result.remaining_credits_gbp?.toFixed(2)} remaining`}
              </p>
              {result.result?.output && (
                <div style={{
                  background: 'var(--brand-paper)', borderRadius: 10, padding: 16,
                  fontSize: 13, lineHeight: 1.5, textAlign: 'left',
                  maxHeight: 240, overflowY: 'auto', whiteSpace: 'pre-wrap',
                  border: '1px solid var(--brand-line)',
                }}>
                  {typeof result.result.output === 'string'
                    ? result.result.output
                    : JSON.stringify(result.result.output, null, 2)}
                </div>
              )}
              <button onClick={() => onClose?.()} className="unlock-button" style={{ marginTop: 20, fontSize: 16 }}>
                Done
              </button>
            </div>
          ) : (
            // ── CashApp-style Checkout ───────────────────
            <>
              <p className="brand-label" style={{ textAlign: 'center', fontSize: 9, color: 'var(--brand-muted)', letterSpacing: '0.2em', marginBottom: 4 }}>
                Send Tribute to Unlock
              </p>

              <div style={{ textAlign: 'center', margin: '16px 0' }}>
                <span style={{ fontSize: 36 }}>{product.icon || '😡'}</span>
              </div>

              <h2 style={{
                fontFamily: '"Fraunces", Georgia, serif',
                fontSize: 26, fontWeight: 700,
                textAlign: 'center', margin: '0 0 4px',
                color: 'var(--brand-ink)',
              }}>
                {product.name || 'Unlock Insight'}
              </h2>

              <p className="ui-text" style={{
                textAlign: 'center', color: 'var(--brand-muted)',
                fontSize: 13, margin: '0 0 20px', lineHeight: 1.5,
              }}>
                {product.description || 'Unlock this data insight for the property'}
              </p>

              {/* Big credit amount */}
              <div style={{
                textAlign: 'center',
                background: 'var(--brand-paper)',
                borderRadius: 12,
                padding: '20px',
                border: '1px solid var(--brand-line)',
                marginBottom: 16,
              }}>
                <div className="brand-label" style={{ fontSize: 9, color: 'var(--brand-muted)', marginBottom: 4 }}>
                  Credits Required
                </div>
                <div style={{
                  fontFamily: '"Fraunces", Georgia, serif',
                  fontSize: 38, fontWeight: 700,
                  color: 'var(--brand-green)',
                  lineHeight: 1,
                }}>
                  {credits}
                </div>
                <div className="ui-text" style={{ fontSize: 12, color: 'var(--brand-muted)', marginTop: 4 }}>
                  credits
                </div>
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
                className="unlock-button"
                style={{ fontSize: 17, padding: 18 }}
              >
                {loading ? (
                  <span style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 8 }}>
                    <span style={{ display: 'inline-block', width: 18, height: 18, border: '2px solid var(--brand-cream)', borderTopColor: 'transparent', borderRadius: '50%', animation: 'spin 0.8s linear infinite' }} />
                    Processing...
                  </span>
                ) : (
                  `Unlock Now \u00b7 ${credits} Credits`
                )}
              </button>

              <p className="ui-text" style={{
                textAlign: 'center', color: 'var(--brand-muted)',
                fontSize: 11, marginTop: 12, cursor: 'pointer',
              }} onClick={() => onClose?.()}>
                Not now
              </p>
            </>
          )}
        </div>
      </div>

      {/* Spinner keyframes */}
      <style>{`@keyframes spin { to { transform: rotate(360deg); } }`}</style>
    </>
  );
}
