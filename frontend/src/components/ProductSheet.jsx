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
        setTimeout(() => onComplete?.(res), 800);
        return;
      }
    } catch (err) {
      if (err.response?.status === 402) {
        // Fall through to Stars
      } else if (err.response?.status === 403) {
        setError('Requires higher tier');
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
          setTimeout(() => onComplete?.({ ok: true }), 800);
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
          <div style={{ width: 28, height: 3, borderRadius: 2, background: 'var(--brand-line)', opacity: 0.4 }} />
        </div>
        <div style={{ padding: '4px 24px 24px' }}>
          {done ? (
            <div style={{ textAlign: 'center', padding: '20px 0' }}>
              <div style={{
                width: 44, height: 44, borderRadius: 22,
                background: 'rgba(21,128,127,0.1)', color: 'var(--brand-green)',
                display: 'flex', alignItems: 'center', justifyContent: 'center',
                fontSize: 20, margin: '0 auto 10px',
              }}>
                {'\u2713'}
              </div>
              <h2 style={{ fontFamily: '"Fraunces", Georgia, serif', fontSize: 17, fontWeight: 600, margin: 0, color: 'var(--brand-ink)' }}>
                Unlocked
              </h2>
            </div>
          ) : (
            <>
              <p className="ui-text" style={{ fontSize: 10, color: 'var(--brand-muted)', textTransform: 'uppercase', letterSpacing: '0.12em', textAlign: 'center', marginBottom: 10 }}>
                Unlock insight
              </p>
              <h2 style={{
                fontFamily: '"Fraunces", Georgia, serif',
                fontSize: 17, fontWeight: 600, textAlign: 'center',
                margin: '0 0 14px', color: 'var(--brand-ink)',
              }}>
                {product.title || product.name || product.id}
              </h2>
              <div style={{
                background: 'var(--brand-paper)', border: '1px solid var(--brand-line)',
                borderRadius: 6, padding: '12px 14px', marginBottom: 14,
                display: 'flex', justifyContent: 'space-between', alignItems: 'center',
              }}>
                <span className="ui-text" style={{ fontSize: 11, color: 'var(--brand-muted)' }}>Price</span>
                <span style={{ fontFamily: '"Fraunces", Georgia, serif', fontSize: 17, fontWeight: 600, color: 'var(--brand-ink)' }}>
                  {'\u00a3'}{price.toFixed(2)}
                </span>
              </div>
              {error && (
                <div className="ui-text" style={{
                  background: 'rgba(199,58,58,0.08)', borderRadius: 4, padding: 8,
                  marginBottom: 10, fontSize: 11, color: '#c73a3a', textAlign: 'center',
                }}>
                  {error}
                </div>
              )}
              <button
                onClick={handlePurchase}
                disabled={loading}
                style={{
                  width: '100%', padding: 13, borderRadius: 6, border: 'none',
                  fontSize: 14, fontWeight: 500, cursor: loading ? 'not-allowed' : 'pointer',
                  background: 'var(--brand-dark)', color: 'var(--brand-cream)',
                  opacity: loading ? 0.6 : 1,
                }}
              >
                {loading ? 'Processing\u2026' : `Unlock \u2014 \u00a3${price.toFixed(2)}`}
              </button>
              <p className="ui-text" style={{ textAlign: 'center', color: 'var(--brand-muted)', fontSize: 11, marginTop: 10, cursor: 'pointer' }} onClick={() => onClose?.()}>
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
