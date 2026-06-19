import { useState } from 'react';
import { purchaseProduct } from '../api';

const EMOTION_COLORS = {
  anger: { accent: '#ff453a', label: 'Anger' },
  fomo: { accent: '#ff9f0a', label: 'FOMO' },
  greed: { accent: '#30d158', label: 'Greed' },
  laziness: { accent: '#64d2ff', label: 'Laziness' },
  fear: { accent: '#ffd60a', label: 'Fear' },
};

export default function ProductSheet({ product, valuationContext, onClose, onComplete }) {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [result, setResult] = useState(null);

  if (!product) return null;

  const emotion = EMOTION_COLORS[product.emotion_trigger] || EMOTION_COLORS.anger;
  const priceLabel = product.effective_gbp_price
    ? `£${product.effective_gbp_price.toFixed(2)}`
    : `£${product.gbp_price?.toFixed(2) || '1.49'}`;

  const handlePurchase = async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await purchaseProduct(product.id, valuationContext);
      if (res.ok) {
        window.Telegram?.WebApp?.HapticFeedback?.notificationOccurred?.('success');
        setResult(res);
        onComplete?.(res);
      } else {
        throw new Error(res.error || 'Purchase failed');
      }
    } catch (err) {
      const msg = err.response?.data?.detail?.message || err.message || 'Something went wrong';
      setError(msg);
      window.Telegram?.WebApp?.HapticFeedback?.notificationOccurred?.('error');
      if (err.response?.status === 402) {
        // Insufficient credits - navigate to store
        setTimeout(() => onClose?.('navigate_store'), 1500);
      }
    } finally {
      setLoading(false);
    }
  };

  return (
    <>
      <div className="sheet-backdrop" onClick={loading ? null : () => onClose?.()} />
      <div className="sheet">
        {/* Handle */}
        <div style={{ display: 'flex', justifyContent: 'center', padding: '8px 0 0' }}>
          <div style={{ width: 36, height: 4, borderRadius: 2, background: 'var(--tg-hint)', opacity: 0.5 }} />
        </div>

        <div style={{ padding: '16px 20px 32px' }}>
          {result ? (
            // ── Success state ──────────────────────────────
            <div style={{ textAlign: 'center' }}>
              <div style={{ fontSize: 48, marginBottom: 8 }}>✅</div>
              <h2 style={{ margin: '0 0 4px', fontSize: 18, fontWeight: 600 }}>Purchased!</h2>
              <p style={{ color: 'var(--tg-hint)', fontSize: 14, margin: '0 0 12px' }}>
                Charged £{result.charged_gbp?.toFixed(2)} · £{result.remaining_credits_gbp?.toFixed(2)} remaining
              </p>
              {result.result?.output && (
                <div
                  style={{
                    background: 'var(--tg-secondary-bg)',
                    borderRadius: 12,
                    padding: 16,
                    fontSize: 13,
                    lineHeight: 1.5,
                    textAlign: 'left',
                    maxHeight: 240,
                    overflowY: 'auto',
                    whiteSpace: 'pre-wrap',
                    color: 'var(--tg-text)',
                  }}
                >
                  {typeof result.result.output === 'string'
                    ? result.result.output
                    : JSON.stringify(result.result.output, null, 2)}
                </div>
              )}
              <button
                onClick={() => onClose?.()}
                style={{
                  marginTop: 16,
                  width: '100%',
                  padding: '14px',
                  borderRadius: 12,
                  background: 'var(--tg-button)',
                  color: 'var(--tg-button-text)',
                  border: 'none',
                  fontSize: 16,
                  fontWeight: 600,
                  cursor: 'pointer',
                }}
              >
                Done
              </button>
            </div>
          ) : (
            // ── Purchase confirmation ──────────────────────
            <>
              <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 12 }}>
                <span style={{ fontSize: 24 }}>{product.emotion_trigger === 'anger' ? '😤' : product.emotion_trigger === 'fomo' ? '🔥' : product.emotion_trigger === 'greed' ? '💰' : product.emotion_trigger === 'fear' ? '😰' : '😴'}</span>
                <div>
                  <div style={{ fontSize: 17, fontWeight: 600 }}>{product.name}</div>
                  <div style={{ fontSize: 12, color: emotion.accent, fontWeight: 500, textTransform: 'uppercase' }}>
                    {emotion.label} Trigger
                  </div>
                </div>
              </div>

              <p style={{ fontSize: 14, color: 'var(--tg-hint)', lineHeight: 1.5, margin: '0 0 16px' }}>
                {product.description}
              </p>

              {error && (
                <div style={{
                  background: 'rgba(255,69,58,0.1)',
                  borderRadius: 8,
                  padding: 10,
                  marginBottom: 12,
                  fontSize: 13,
                  color: 'var(--color-anger)',
                }}>
                  {error}
                </div>
              )}

              <button
                onClick={handlePurchase}
                disabled={loading}
                style={{
                  width: '100%',
                  padding: '14px',
                  borderRadius: 12,
                  background: loading ? 'var(--tg-hint)' : emotion.accent,
                  color: '#fff',
                  border: 'none',
                  fontSize: 16,
                  fontWeight: 600,
                  cursor: loading ? 'not-allowed' : 'pointer',
                  opacity: loading ? 0.6 : 1,
                }}
              >
                {loading ? 'Purchasing...' : `Buy Now · ${priceLabel}`}
              </button>

              <button
                onClick={() => onClose?.()}
                style={{
                  width: '100%',
                  padding: '12px',
                  marginTop: 8,
                  background: 'none',
                  border: 'none',
                  fontSize: 14,
                  color: 'var(--tg-hint)',
                  cursor: 'pointer',
                }}
              >
                Cancel
              </button>
            </>
          )}
        </div>
      </div>
    </>
  );
}
