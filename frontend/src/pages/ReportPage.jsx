import { useEffect, useState } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';
import ConfidenceGauge from '../components/ConfidenceGauge';
import ProductSheet from '../components/ProductSheet';

const EMOTION_STYLES = {
  anger: { bg: 'rgba(255,69,58,0.08)', accent: '#ff453a', icon: '😤', label: 'Anger' },
  fomo: { bg: 'rgba(255,159,10,0.08)', accent: '#ff9f0a', icon: '🔥', label: 'FOMO' },
  greed: { bg: 'rgba(48,209,88,0.08)', accent: '#30d158', icon: '💰', label: 'Greed' },
  laziness: { bg: 'rgba(100,210,255,0.08)', accent: '#64d2ff', icon: '😴', label: 'Laziness' },
  fear: { bg: 'rgba(255,214,10,0.08)', accent: '#ffd60a', icon: '😰', label: 'Fear' },
};

function formatPrice(n) {
  if (!n) return '—';
  return '£' + Number(n).toLocaleString('en-GB');
}

export default function ReportPage() {
  const location = useLocation();
  const navigate = useNavigate();
  const [avmResult, setAvmResult] = useState(null);
  const [selectedProduct, setSelectedProduct] = useState(null);

  useEffect(() => {
    window.Telegram?.WebApp?.expand?.();
    // Try state first, then sessionStorage
    const data = location.state?.avmResult || (() => {
      try {
        return JSON.parse(sessionStorage.getItem('honestly_last_avm'));
      } catch { return null; }
    })();
    if (data) setAvmResult(data);
  }, []);

  if (!avmResult) {
    return (
      <div style={{ padding: '40px 16px', textAlign: 'center' }}>
        <div style={{ fontSize: 48, marginBottom: 12 }}>🔍</div>
        <h2 style={{ fontSize: 18, fontWeight: 600, margin: '0 0 8px' }}>No valuation yet</h2>
        <p style={{ fontSize: 14, color: 'var(--tg-hint)', margin: '0 0 20px' }}>
          Value a property first to see your report here.
        </p>
        <button
          onClick={() => navigate('/')}
          style={{
            padding: '14px 32px',
            borderRadius: 12,
            background: 'var(--tg-button)',
            color: 'var(--tg-button-text)',
            border: 'none',
            fontSize: 16,
            fontWeight: 600,
            cursor: 'pointer',
          }}
        >
          Value a Property
        </button>
      </div>
    );
  }

  const avm = avmResult.avm || {};
  const triggers = avmResult.product_triggers || [];

  // Build valuation context for product purchases
  const valuationContext = {
    address: avm.address,
    postcode: avm.postcode,
    central: avm.central,
    low: avm.low,
    high: avm.high,
    confidence_score: avm.confidence_score,
    confidence_grade: avm.confidence_grade,
    sqm: avm.sqm,
    epc: avm.epc,
    type: avm.type,
    evidence: avm.evidence,
  };

  return (
    <div style={{ padding: '0 0 100px' }}>
      {/* ── Hero value ──────────────────────────────────── */}
      <div style={{
        background: 'linear-gradient(180deg, var(--tg-secondary-bg) 0%, var(--tg-bg) 100%)',
        padding: '32px 20px 24px',
        textAlign: 'center',
      }}>
        <p style={{ fontSize: 13, color: 'var(--tg-hint)', margin: '0 0 4px', textTransform: 'uppercase', letterSpacing: 1 }}>
          Assessed Value
        </p>
        <h1 style={{ fontSize: 40, fontWeight: 700, margin: '0 0 4px', letterSpacing: -1 }}>
          {formatPrice(avm.central)}
        </h1>
        <p style={{ fontSize: 14, color: 'var(--tg-hint)', margin: '0 0 12px' }}>
          Range: {formatPrice(avm.low)} - {formatPrice(avm.high)}
        </p>

        {/* Confidence gauge */}
        <div style={{ maxWidth: 300, margin: '0 auto' }}>
          <ConfidenceGauge score={avm.confidence_score} label={avm.confidence_grade} />
        </div>
        <p style={{ fontSize: 13, color: 'var(--tg-hint)', margin: '4px 0 0' }}>
          Confidence: {avm.confidence_grade} ({avm.confidence_score}/100)
        </p>

        {/* Address */}
        <p style={{ fontSize: 14, margin: '12px 0 0' }}>
          📍 {avm.address}
        </p>
      </div>

      {/* ── Property details ────────────────────────────── */}
      <div style={{ padding: '16px 20px' }}>
        <div style={{
          display: 'grid',
          gridTemplateColumns: '1fr 1fr',
          gap: 12,
        }}>
          {[
            { label: 'Floor Area', value: avm.sqm ? `${avm.sqm} sqm` : '—' },
            { label: 'EPC Rating', value: avm.epc || '—' },
            { label: 'Property Type', value: avm.type || '—' },
            { label: 'Comparables', value: avm.n_comps ? `${avm.n_comps} sold` : '—' },
          ].map((d) => (
            <div key={d.label} style={{
              background: 'var(--tg-secondary-bg)',
              borderRadius: 12,
              padding: '12px',
              textAlign: 'center',
            }}>
              <div style={{ fontSize: 11, color: 'var(--tg-hint)', textTransform: 'uppercase', letterSpacing: 0.5 }}>
                {d.label}
              </div>
              <div style={{ fontSize: 16, fontWeight: 600, marginTop: 4 }}>{d.value}</div>
            </div>
          ))}
        </div>
      </div>

      {/* ── Strict comparables ──────────────────────────── */}
      {avm.evidence?.length > 0 && (
        <div style={{ padding: '0 20px 16px' }}>
          <h3 style={{ fontSize: 15, fontWeight: 600, margin: '0 0 10px' }}>
            Sold Comparables ({avm.evidence.length})
          </h3>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
            {avm.evidence.slice(0, 5).map((e, i) => (
              <div key={i} style={{
                display: 'flex',
                justifyContent: 'space-between',
                alignItems: 'center',
                background: 'var(--tg-secondary-bg)',
                borderRadius: 10,
                padding: '10px 12px',
                fontSize: 13,
              }}>
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div style={{ fontWeight: 500, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
                    {e.address || 'Unknown'}
                  </div>
                  <div style={{ color: 'var(--tg-hint)', fontSize: 11 }}>
                    {e.date ? e.date.slice(0, 7) : ''} · {e.sqm || '?'} sqm
                  </div>
                </div>
                <div style={{ fontWeight: 600, fontSize: 14, marginLeft: 8 }}>
                  {formatPrice(e.price)}
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* ── Emotional product triggers ──────────────────── */}
      {triggers.length > 0 && (
        <div style={{ padding: '0 20px' }}>
          <h3 style={{ fontSize: 15, fontWeight: 600, margin: '0 0 10px', display: 'flex', alignItems: 'center', gap: 6 }}>
            <span>⚡</span> Recommended for this property
          </h3>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
            {triggers.map((t, i) => {
              const style = EMOTION_STYLES[t.emotion_trigger] || EMOTION_STYLES.anger;
              const priceLabel = t.effective_gbp_price
                ? `£${t.effective_gbp_price.toFixed(2)}`
                : '';

              return (
                <div
                  key={t.product_id}
                  className="product-card"
                  onClick={() => setSelectedProduct(t)}
                  style={{
                    background: style.bg,
                    borderColor: style.accent + '40',
                    padding: '12px 14px',
                  }}
                >
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                      <span style={{ fontSize: 20 }}>{style.icon}</span>
                      <div>
                        <div style={{ fontWeight: 600, fontSize: 14 }}>{t.name || t.product_id?.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase())}</div>
                        <div style={{ fontSize: 11, color: style.accent, textTransform: 'uppercase', fontWeight: 500 }}>
                          {style.label} · {t.relevance_score}% match
                        </div>
                      </div>
                    </div>
                    <div style={{ textAlign: 'right' }}>
                      <div style={{ fontWeight: 700, fontSize: 15, color: style.accent }}>{priceLabel}</div>
                      <div style={{ fontSize: 11, color: 'var(--tg-hint)' }}>Tap to buy</div>
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      )}

      {/* ── Bottom sheet for purchase ───────────────────── */}
      {selectedProduct && (
        <ProductSheet
          product={selectedProduct}
          valuationContext={valuationContext}
          onClose={(action) => {
            setSelectedProduct(null);
            if (action === 'navigate_store') navigate('/store');
          }}
          onComplete={(res) => {
            // Update the stored AVM result with any new data
            const current = JSON.parse(sessionStorage.getItem('honestly_last_avm') || '{}');
            sessionStorage.setItem('honestly_last_avm', JSON.stringify({ ...current, last_purchase: res }));
          }}
        />
      )}
    </div>
  );
}
