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
      <div className="sheet">
        <div style={{ display: 'flex', justifyContent: 'center', padding: '12px 0 4px' }}>
          <div style={{ width: 32, height: 4, borderRadius: 2, background: 'var(--border-glass)' }} />
        </div>
        <div style={{ padding: '8px 24px 32px' }}>
          {done ? (
            <div style={{ textAlign: 'center', padding: '24px 0' }}>
              <div style={{
                width: 48, height: 48, borderRadius: 24,
                background: 'rgba(52,211,153,0.15)', color: 'var(--brand-green)',
                display: 'flex', alignItems: 'center', justifyContent: 'center',
                fontSize: 22, margin: '0 auto 12px',
              }}>
                {'\u2713'}
              </div>
              <h2 className="display" style={{ fontSize: 18, fontWeight: 600, margin: 0, color: 'var(--brand-ink)' }}>
                Unlocked
              </h2>
            </div>
          ) : (
            <>
              <p className="label" style={{ textAlign: 'center', marginBottom: 10 }}>Purchase Report</p>
              <h2 className="display" style={{
                fontSize: 17, fontWeight: 600, textAlign: 'center',
                margin: '0 0 16px', color: 'var(--brand-ink)',
              }}>
                {product.title || product.name || product.id}
              </h2>
              <div className="glass" style={{
                padding: '14px 16px', marginBottom: 16, borderRadius: 12,
                display: 'flex', justifyContent: 'space-between', alignItems: 'center',
              }}>
                <span style={{ fontSize: 12, color: 'var(--brand-muted)' }}>Price</span>
                <span className="display" style={{ fontSize: 18, fontWeight: 600, color: 'var(--brand-green)', letterSpacing: '-0.02em' }}>
                  {'\u00a3'}{price.toFixed(2)}
                </span>
              </div>
              {error && (
                <div style={{
                  background: 'rgba(248,113,113,0.1)', borderRadius: 8, padding: 8,
                  marginBottom: 10, fontSize: 11, color: '#f87171', textAlign: 'center',
                }}>
                  {error}
                </div>
              )}
              <button
                onClick={handlePurchase}
                disabled={loading}
                className="btn-primary"
              >
                {loading ? (
                  <span style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 8 }}>
                    <span style={{
                      display: 'inline-block', width: 14, height: 14,
                      border: '2px solid #0a0a0f', borderTopColor: 'transparent',
                      borderRadius: '50%', animation: 'spin 0.8s linear infinite',
                    }} />
                    Processing
                  </span>
                ) : (
                  `Unlock \u2014 \u00a3${price.toFixed(2)}`
                )}
              </button>
              <p style={{ textAlign: 'center', color: 'var(--brand-muted)', fontSize: 12, marginTop: 12, cursor: 'pointer' }} onClick={() => onClose?.()}>
                Cancel
              </p>
            </>
          )}
        </div>
      </div>
    </>
  );
}
