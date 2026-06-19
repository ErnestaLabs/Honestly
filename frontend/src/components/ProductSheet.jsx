import { useState } from 'react';
import { purchaseProduct, createInvoice } from '../api';
import { saveCreditBalance, loadCreditBalance } from '../utils/tgStorage';

export default function ProductSheet({ product, valuationContext, onClose, onComplete }) {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [result, setResult] = useState(null);
  const [balance, setBalance] = useState(0);

  useState(() => {
    loadCreditBalance().then(b => setBalance(b || 0));
  }, []);

  if (!product) return null;

  const price = product.price || product.gbp || 1.49;

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
        // Insufficient credits - fall through
      } else if (err.response?.status === 403) {
        setError('Requires a higher subscription tier');
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
      if (!invoice.ok || !invoice.invoice_url) throw new Error(invoice.error || 'Invoice failed');
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
          setError('Payment cancelled');
          window.Telegram?.WebApp?.HapticFeedback?.notificationOccurred?.('warning');
        } else {
          setError('Payment failed');
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
        <div style={{ display: 'flex', justifyContent: 'center', padding: '12px 0 4px' }}>
          <div style={{ width: 32, height: 3, borderRadius: 2, background: 'var(--brand-line)', opacity: 0.5 }} />
        </div>

        <div style={{ padding: '8px 24px 32px' }}>
          {result ? (
            <div style={{ textAlign: 'center', padding: '20px 0' }}>
              <div style={{
                width: 48, height: 48, borderRadius: 24,
                background: 'rgba(21,128,127,0.1)', color: 'var(--brand-green)',
                display: 'flex', alignItems: 'center', justifyContent: 'center',
                fontSize: 24, margin: '0 auto 12px',
              }}>
                {'\u2713'}
              </div>
              <h2 style={{ fontFamily: '"Fraunces", Georgia, serif', fontSize: 20, fontWeight: 600, margin: '0 0 4px', color: 'var(--brand-ink)' }}>
                Report Purchased
              </h2>
              <p className="ui-text" style={{ color: 'var(--brand-muted)', fontSize: 13, margin: '0 0 20px' }}>
                {result.charged_gbp > 0 ? `Charged \u00a3${result.charged_gbp.toFixed(2)}` : 'Unlocked via Telegram Stars'}
              </p>
              <button
                onClick={() => onClose?.()}
                className="purchase-button"
                style={{ fontSize: 15, padding: 14 }}
              >
                Done
              </button>
            </div>
          ) : (
            <>
              <div style={{ textAlign: 'center', marginBottom: 20 }}>
                <div style={{
                  width: 40, height: 40, borderRadius: 8,
                  background: 'var(--brand-dark)', color: 'var(--brand-cream)',
                  display: 'flex', alignItems: 'center', justifyContent: 'center',
                  fontSize: 16, fontWeight: 600, margin: '0 auto 10px',
                  fontFamily: '"Fraunces", Georgia, serif',
                }}>
                  R
                </div>
                <h2 style={{
                  fontFamily: '"Fraunces", Georgia, serif',
                  fontSize: 20, fontWeight: 600, margin: '0 0 4px',
                  color: 'var(--brand-ink)',
                }}>
                  {product.title || product.name || 'Additional Report'}
                </h2>
                <p className="ui-text" style={{ color: 'var(--brand-muted)', fontSize: 12, margin: 0 }}>
                  {product.subtitle || 'Purchase this report'}
                </p>
              </div>

              <div style={{
                background: 'var(--brand-paper)', border: '1px solid var(--brand-line)',
                borderRadius: 8, padding: '16px', marginBottom: 16,
                display: 'flex', justifyContent: 'space-between', alignItems: 'center',
              }}>
                <div>
                  <div className="ui-text" style={{ fontSize: 12, color: 'var(--brand-muted)' }}>
                    Price
                  </div>
                  <div style={{
                    fontFamily: '"Fraunces", Georgia, serif',
                    fontSize: 22, fontWeight: 700, color: 'var(--brand-ink)',
                    marginTop: 2,
                  }}>
                    {'\u00a3'}{price.toFixed(2)}
                  </div>
                </div>
                <div style={{ textAlign: 'right' }}>
                  <div className="ui-text" style={{ fontSize: 12, color: 'var(--brand-muted)' }}>
                    Your balance
                  </div>
                  <div className="ui-text" style={{ fontSize: 13, fontWeight: 500, color: balance >= price ? 'var(--brand-green)' : 'var(--brand-muted)', marginTop: 2 }}>
                    {'\u00a3'}{(balance || 0).toFixed(2)}
                    {balance >= price ? ' \u2714' : ''}
                  </div>
                </div>
              </div>

              {error && (
                <div className="ui-text" style={{
                  background: 'rgba(199,58,58,0.08)', borderRadius: 6, padding: 10,
                  marginBottom: 12, fontSize: 12, color: '#c73a3a', textAlign: 'center',
                }}>
                  {error}
                </div>
              )}

              <button
                onClick={handlePurchase}
                disabled={loading}
                className="purchase-button"
                style={{ fontSize: 15, padding: 16 }}
              >
                {loading ? (
                  <span style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 8 }}>
                    <span style={{
                      display: 'inline-block', width: 16, height: 16,
                      border: '2px solid var(--brand-cream)', borderTopColor: 'transparent',
                      borderRadius: '50%', animation: 'spin 0.8s linear infinite',
                    }} />
                    Processing...
                  </span>
                ) : (
                  `Purchase Report \u2014 \u00a3${price.toFixed(2)}`
                )}
              </button>

              <p className="ui-text" style={{
                textAlign: 'center', color: 'var(--brand-muted)',
                fontSize: 12, marginTop: 14, cursor: 'pointer',
              }} onClick={() => onClose?.()}>
                Cancel
              </p>
            </>
          )}
        </div>
      </div>

      <style>{`@keyframes spin { to { transform: rotate(360deg); } }`}</style>
    </>
  );
}
