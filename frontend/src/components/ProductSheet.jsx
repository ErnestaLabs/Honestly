import { useState } from 'react';
import { purchaseProduct, createInvoice } from '../api';
import { saveCreditBalance } from '../utils/tgStorage';

export default function ProductSheet({ product, valuationContext, onClose, onComplete }) {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [done, setDone] = useState(false);

  if (!product) return null;
  const price = product.price || 1.49;

  const handlePurchase = async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await purchaseProduct(product.id, valuationContext);
      if (res.ok) {
        window.Telegram?.WebApp?.HapticFeedback?.notificationOccurred?.('success');
        setDone(true);
        if (res.remaining_credits_gbp !== undefined) await saveCreditBalance(res.remaining_credits_gbp);
        setTimeout(() => onComplete?.(res), 1000);
        return;
      }
    } catch (err) {
      if (err.response?.status === 402) {
        // Fall through to Stars
      } else if (err.response?.status === 403) {
        setError('Requires higher subscription tier');
        window.Telegram?.WebApp?.HapticFeedback?.notificationOccurred?.('error');
        setLoading(false); return;
      } else {
        setError(err.response?.data?.detail?.message || err.message || 'Failed');
        window.Telegram?.WebApp?.HapticFeedback?.notificationOccurred?.('error');
        setLoading(false); return;
      }
    }
    // Stars fallback
    try {
      const invoice = await createInvoice({ productId: product.id });
      if (!invoice.ok || !invoice.invoice_url) throw new Error('Invoice failed');
      const tg = window.Telegram?.WebApp;
      if (!tg?.openInvoice) throw new Error('openInvoice unavailable');
      tg.openInvoice(invoice.invoice_url, (status) => {
        if (status === 'paid') {
          window.Telegram?.WebApp?.HapticFeedback?.notificationOccurred?.('success');
          setDone(true);
          setTimeout(() => onComplete?.({ ok: true }), 1000);
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
        <div style={{ display: 'flex', justifyContent: 'center', padding: '10px 0 4px' }}>
          <div style={{ width: 32, height: 3, borderRadius: 2, background: 'var(--brand-line)', opacity: 0.5 }} />
        </div>
        <div style={{ padding: '8px 24px 28px' }}>
          {done ? (
            <div style={{ textAlign: 'center', padding: '24px 0' }}>
              <div style={{
                width: 48, height: 48, borderRadius: 24,
                background: 'rgba(21,128,127,0.1)', color: 'var(--brand-green)',
                display: 'flex', alignItems: 'center', justifyContent: 'center',
                fontSize: 22, margin: '0 auto 12px',
              }}>
                {'\u2713'}
              </div>
              <h2 style={{ fontFamily: '"Fraunces", Georgia, serif', fontSize: 18, fontWeight: 600, margin: 0, color: 'var(--brand-ink)' }}>
                Purchased
              </h2>
            </div>
          ) : (
            <>
              <p className="ui-text" style={{ fontSize: 11, color: 'var(--brand-muted)', textTransform: 'uppercase', letterSpacing: '0.12em', textAlign: 'center', marginBottom: 14 }}>
                Purchase Report
              </p>
              <h2 style={{
                fontFamily: '"Fraunces", Georgia, serif',
                fontSize: 18, fontWeight: 600, textAlign: 'center',
                margin: '0 0 16px', color: 'var(--brand-ink)',
              }}>
                {product.title || product.name || product.id}
              </h2>
              <div style={{
                background: 'var(--brand-paper)', border: '1px solid var(--brand-line)',
                borderRadius: 8, padding: '14px 16px', marginBottom: 16,
                display: 'flex', justifyContent: 'space-between', alignItems: 'center',
              }}>
                <span className="ui-text" style={{ fontSize: 12, color: 'var(--brand-muted)' }}>Price</span>
                <span style={{ fontFamily: '"Fraunces", Georgia, serif', fontSize: 18, fontWeight: 600, color: 'var(--brand-ink)' }}>
                  {'\u00a3'}{price.toFixed(2)}
                </span>
              </div>
              {error && (
                <div className="ui-text" style={{
                  background: 'rgba(199,58,58,0.08)', borderRadius: 6, padding: 8,
                  marginBottom: 10, fontSize: 11, color: '#c73a3a', textAlign: 'center',
                }}>
                  {error}
                </div>
              )}
              <button
                onClick={handlePurchase}
                disabled={loading}
                className="purchase-button"
              >
                {loading ? (
                  <span style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 8 }}>
                    <span style={{
                      display: 'inline-block', width: 14, height: 14,
                      border: '2px solid var(--brand-cream)', borderTopColor: 'transparent',
                      borderRadius: '50%', animation: 'spin 0.8s linear infinite',
                    }} />
                    Processing
                  </span>
                ) : (
                  `Purchase \u2014 \u00a3${price.toFixed(2)}`
                )}
              </button>
              <p className="ui-text" style={{ textAlign: 'center', color: 'var(--brand-muted)', fontSize: 12, marginTop: 12, cursor: 'pointer' }} onClick={() => onClose?.()}>
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
