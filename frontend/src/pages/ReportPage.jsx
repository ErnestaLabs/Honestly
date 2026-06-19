import { useEffect, useState } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';
import ConfidenceGauge from '../components/ConfidenceGauge';
import ProductSheet from '../components/ProductSheet';
import { saveLastAvm, loadLastAvm, saveCreditBalance } from '../utils/tgStorage';

const EMOTION_STYLES = {
  anger: { bg: 'rgba(199,58,58,0.06)', accent: '#c73a3a', icon: '😤', label: 'Anger' },
  fomo: { bg: 'rgba(216,154,50,0.06)', accent: '#d89a32', icon: '🔥', label: 'FOMO' },
  greed: { bg: 'rgba(21,128,127,0.06)', accent: '#15807f', icon: '💰', label: 'Greed' },
  laziness: { bg: 'rgba(34,158,217,0.06)', accent: '#229ED9', icon: '😴', label: 'Laziness' },
  fear: { bg: 'rgba(212,160,23,0.06)', accent: '#d4a017', icon: '😰', label: 'Fear' },
};

function formatPrice(n) {
  if (!n) return '\u2014';
  return '\u00a3' + Number(n).toLocaleString('en-GB');
}

export default function ReportPage() {
  const location = useLocation();
  const navigate = useNavigate();
  const [avmResult, setAvmResult] = useState(null);
  const [selectedProduct, setSelectedProduct] = useState(null);

  useEffect(() => {
    window.Telegram?.WebApp?.expand?.();
    const loadData = async () => {
      const stateData = location.state?.avmResult;
      if (stateData) {
        setAvmResult(stateData);
        await saveLastAvm(stateData);
        return;
      }
      const stored = await loadLastAvm();
      if (stored) setAvmResult(stored);
    };
    loadData();
  }, []);

  if (!avmResult) {
    return (
      <div style={{ padding: '40px 16px', textAlign: 'center' }}>
        <div style={{ fontSize: 48, marginBottom: 12 }}>🔍</div>
        <h2 style={{
          fontFamily: '"Fraunces", Georgia, serif',
          fontSize: 20, fontWeight: 600, margin: '0 0 8px',
          letterSpacing: '-0.02em',
        }}>
          No valuation yet
        </h2>
        <p className="ui-text" style={{ fontSize: 14, color: 'var(--brand-muted)', margin: '0 0 20px' }}>
          Value a property first to see your report here.
        </p>
        <button
          onClick={() => navigate('/')}
          className="brand-cta"
          style={{ fontSize: 15, padding: '14px 32px' }}
        >
          Value a Property
        </button>
      </div>
    );
  }

  const avm = avmResult.avm || {};
  const triggers = avmResult.product_triggers || [];

  const valuationContext = {
    address: avm.address, postcode: avm.postcode,
    central: avm.central, low: avm.low, high: avm.high,
    confidence_score: avm.confidence_score, confidence_grade: avm.confidence_grade,
    sqm: avm.sqm, epc: avm.epc, type: avm.type, evidence: avm.evidence,
  };

  return (
    <div style={{ padding: '0 0 100px' }}>
      {/* ── Hero: Glass panel with big value ───────────── */}
      <div style={{
        background: 'linear-gradient(180deg, var(--brand-paper) 0%, var(--brand-cream) 100%)',
        padding: '28px 20px 24px',
        textAlign: 'center',
        borderBottom: '1px solid var(--brand-line)',
      }}>
        <div className="brand-label" style={{ color: 'var(--brand-muted)', marginBottom: 4, fontSize: 10 }}>
          Assessed Value
        </div>
        <h1 style={{
          fontFamily: '"Fraunces", Georgia, serif',
          fontSize: 42, fontWeight: 600, margin: '0 0 4px',
          letterSpacing: '-0.03em', lineHeight: 0.95,
          color: 'var(--brand-ink)',
        }}>
          {formatPrice(avm.central)}
        </h1>
        <p className="ui-text" style={{
          fontSize: 14, color: 'var(--brand-muted)', margin: '0 0 14px',
        }}>
          Range: {formatPrice(avm.low)} &ndash; {formatPrice(avm.high)}
        </p>

        <div style={{ maxWidth: 280, margin: '0 auto' }}>
          <ConfidenceGauge score={avm.confidence_score} label={avm.confidence_grade} />
        </div>
        <p className="ui-text" style={{ fontSize: 12, color: 'var(--brand-muted)', margin: '4px 0 0' }}>
          Confidence: {avm.confidence_grade} ({avm.confidence_score}/100)
        </p>
        <p className="ui-text" style={{
          fontSize: 13, margin: '14px 0 0', color: 'var(--brand-muted)',
        }}>
          📍 {avm.address}
        </p>
      </div>

      {/* ── Property details grid (brand cards) ────────── */}
      <div style={{ padding: '16px 16px' }}>
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10 }}>
          {[
            { label: 'Floor Area', value: avm.sqm ? `${avm.sqm} sqm` : '\u2014' },
            { label: 'EPC Rating', value: avm.epc || '\u2014' },
            { label: 'Property Type', value: avm.type || '\u2014' },
            { label: 'Comparables', value: avm.n_comps ? `${avm.n_comps} sold` : '\u2014' },
          ].map((d) => (
            <div key={d.label} className="brand-card" style={{ padding: '12px', textAlign: 'center' }}>
              <div className="brand-label" style={{ fontSize: 9, color: 'var(--brand-muted)', marginBottom: 4 }}>
                {d.label}
              </div>
              <div className="ui-text" style={{
                fontSize: 15, fontWeight: 600, color: 'var(--brand-ink)',
                fontFamily: '"Fraunces", Georgia, serif',
              }}>
                {d.value}
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* ── Strict comparables ──────────────────────────── */}
      {avm.evidence?.length > 0 && (
        <div style={{ padding: '0 16px 16px' }}>
          <h3 style={{
            fontFamily: '"Fraunces", Georgia, serif',
            fontSize: 15, fontWeight: 600, margin: '0 0 10px',
            letterSpacing: '-0.02em',
          }}>
            Sold Comparables ({avm.evidence.length})
          </h3>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
            {avm.evidence.slice(0, 5).map((e, i) => (
              <div key={i} className="brand-card" style={{
                display: 'flex', justifyContent: 'space-between', alignItems: 'center',
                padding: '10px 12px',
              }}>
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div className="ui-text" style={{ fontWeight: 500, fontSize: 13, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
                    {e.address || 'Unknown'}
                  </div>
                  <div className="ui-text" style={{ color: 'var(--brand-muted)', fontSize: 11 }}>
                    {e.date ? e.date.slice(0, 7) : ''} · {e.sqm || '?'} sqm
                  </div>
                </div>
                <div className="ui-text" style={{
                  fontWeight: 600, fontSize: 14, marginLeft: 8,
                  fontFamily: '"Fraunces", Georgia, serif',
                  color: 'var(--brand-green)',
                }}>
                  {formatPrice(e.price)}
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* ── Emotional product triggers ──────────────────── */}
      {triggers.length > 0 && (
        <div style={{ padding: '0 16px' }}>
          <h3 style={{
            fontFamily: '"Fraunces", Georgia, serif',
            fontSize: 15, fontWeight: 600, margin: '0 0 10px',
            letterSpacing: '-0.02em',
            display: 'flex', alignItems: 'center', gap: 6,
          }}>
            <span>⚡</span> Recommended for this property
          </h3>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
            {triggers.map((t) => {
              const style = EMOTION_STYLES[t.emotion_trigger] || EMOTION_STYLES.anger;
              const priceLabel = t.effective_gbp_price ? `\u00a3${t.effective_gbp_price.toFixed(2)}` : '';
              return (
                <div
                  key={t.product_id}
                  className="product-card"
                  onClick={() => setSelectedProduct(t)}
                  style={{ background: style.bg, borderColor: style.accent + '30', padding: '12px 14px' }}
                >
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                      <span style={{ fontSize: 18 }}>{style.icon}</span>
                      <div>
                        <div className="ui-text" style={{ fontWeight: 600, fontSize: 13 }}>
                          {t.name || t.product_id?.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase())}
                        </div>
                        <div className="ui-text" style={{ fontSize: 10, color: style.accent, textTransform: 'uppercase', fontWeight: 500, letterSpacing: '0.05em' }}>
                          {style.label} · {t.relevance_score}% match
                        </div>
                      </div>
                    </div>
                    <div style={{ textAlign: 'right' }}>
                      <div style={{ fontWeight: 600, fontSize: 14, color: style.accent, fontFamily: '"Fraunces", Georgia, serif' }}>
                        {priceLabel}
                      </div>
                      <div className="ui-text" style={{ fontSize: 10, color: 'var(--brand-muted)' }}>Tap to buy</div>
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      )}

      {/* ── Bottom sheet ────────────────────────────────── */}
      {selectedProduct && (
        <ProductSheet
          product={selectedProduct}
          valuationContext={valuationContext}
          onClose={(action) => {
            setSelectedProduct(null);
            if (action === 'navigate_store') navigate('/store');
          }}
          onComplete={async (res) => {
            const current = await loadLastAvm() || {};
            current.last_purchase = res;
            await saveLastAvm(current);
            if (res.remaining_credits_gbp !== undefined && typeof res.remaining_credits_gbp === 'number') {
              await saveCreditBalance(res.remaining_credits_gbp);
            }
          }}
        />
      )}

      {/* ── Brand footer ──────────────────────────────── */}
      <div className="brand-hair" style={{ margin: '16px 16px 8px' }} />
      <p className="brand-label" style={{
        textAlign: 'center', color: 'var(--brand-muted)',
        fontSize: 10, letterSpacing: '0.18em', padding: '0 16px',
      }}>
        Honestly · your property's price, proved
      </p>
    </div>
  );
}
