import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import ProductSheet from '../components/ProductSheet';
import { saveLastAvm, loadLastAvm } from '../utils/tgStorage';

function formatPrice(n) {
  if (!n) return '\u2014';
  return '\u00a3' + Number(n).toLocaleString('en-GB');
}

const EMOTION_META = {
  anger: { icon: '😡', label: 'Anger' },
  fomo: { icon: '🔥', label: 'FOMO' },
  greed: { icon: '💰', label: 'Greed' },
  laziness: { icon: '😴', label: 'Laziness' },
  fear: { icon: '😰', label: 'Fear' },
};

export default function ReportPage() {
  const navigate = useNavigate();
  const [avmResult, setAvmResult] = useState(null);
  const [selectedProduct, setSelectedProduct] = useState(null);

  useEffect(() => {
    window.Telegram?.WebApp?.expand?.();
    const load = async () => {
      try {
        const stored = await loadLastAvm();
        if (stored) setAvmResult(stored);
      } catch {}
    };
    load();
  }, []);

  if (!avmResult) {
    return (
      <div style={{ padding: '40px 16px', textAlign: 'center' }}>
        <div style={{ fontSize: 48, marginBottom: 12 }}>🔍</div>
        <h2 style={{ fontFamily: '"Fraunces", Georgia, serif', fontSize: 20, fontWeight: 600, margin: '0 0 8px' }}>
          No property yet
        </h2>
        <p className="ui-text" style={{ fontSize: 14, color: 'var(--brand-muted)', margin: '0 0 20px' }}>
          Value a property first to see its profile here.
        </p>
        <button onClick={() => navigate('/')} className="unlock-button" style={{ width: 'auto', padding: '14px 32px', fontSize: 15 }}>
          🔍 Value a Property
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

  // Build tribute menu items from triggers + add non-triggered products
  const menuItems = triggers.map(t => {
    const meta = EMOTION_META[t.emotion_trigger] || EMOTION_META.anger;
    return {
      id: t.product_id,
      name: t.name || t.product_id?.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase()),
      description: t.reason || 'Unlock this data insight',
      icon: meta.icon,
      emotion: meta.label,
      relevance: t.relevance_score,
      credits: t.effective_gbp_price ? Math.round(t.effective_gbp_price * 100) : 149,
      gbp: t.effective_gbp_price || 1.49,
    };
  });

  // Ensure we always show at least a few items
  const defaultItems = [
    { id: 'lowball_counter_email', name: 'Are They Taking The Piss?', description: 'Generate a data-backed counter-offer email', icon: '😡', emotion: 'Anger', credits: 149, gbp: 1.49 },
    { id: 'council_tax_challenger', name: 'Council Tax Banding Challenge', description: 'Compare your band to neighbours', icon: '😡', emotion: 'Anger', credits: 299, gbp: 2.99 },
    { id: 'planning_permission_oracle', name: 'Can I Build Without Permission?', description: 'Check Permitted Development rules', icon: '😴', emotion: 'Laziness', credits: 249, gbp: 2.49 },
    { id: 'leasehold_trap_xray', name: 'Leasehold Trap X-Ray', description: 'Calculate Section 42 extension cost', icon: '😰', emotion: 'Fear', credits: 499, gbp: 4.99 },
    { id: 'gentrification_radar', name: 'Gentrification Radar', description: '5-year price + sentiment forecast', icon: '💰', emotion: 'Greed', credits: 299, gbp: 2.99 },
  ];

  const allItems = menuItems.length >= 3 ? menuItems : defaultItems;

  const handleSelectProduct = (item) => {
    window.Telegram?.WebApp?.HapticFeedback?.impactOccurred?.('light');
    setSelectedProduct(item);
  };

  const confidencePct = Math.min(100, Math.max(0, avm.confidence_score || 0));
  const gaugeColor = confidencePct >= 80 ? 'var(--brand-green)' : confidencePct >= 60 ? 'var(--brand-terra)' : confidencePct >= 40 ? 'var(--brand-gold)' : '#c73a3a';

  return (
    <div style={{ padding: '0 0 100px' }}>
      {/* ── Profile Header ─────────────────────────────── */}
      <div style={{
        padding: '32px 20px 20px',
        textAlign: 'center',
        borderBottom: '1px solid var(--brand-line)',
      }}>
        <p className="ui-text" style={{ fontSize: 14, color: 'var(--brand-muted)', margin: '0 0 4px' }}>
          📍 {avm.address}
        </p>
        <h1 style={{
          fontFamily: '"Fraunces", Georgia, serif',
          fontSize: 44, fontWeight: 700, margin: '4px 0',
          letterSpacing: '-0.03em', lineHeight: 0.95,
          color: 'var(--brand-ink)',
        }}>
          {formatPrice(avm.central)}
        </h1>
        <p className="ui-text" style={{ fontSize: 13, color: 'var(--brand-muted)', margin: '0 0 12px' }}>
          {formatPrice(avm.low)} &ndash; {formatPrice(avm.high)}
        </p>
        <div style={{ maxWidth: 240, margin: '0 auto 4px' }}>
          <div className="gauge-track" style={{ height: 4 }}>
            <div className="gauge-fill" style={{ width: `${confidencePct}%`, background: gaugeColor, height: 4 }} />
          </div>
        </div>
        <p className="ui-text" style={{ fontSize: 11, color: 'var(--brand-muted)', margin: 0 }}>
          {avm.confidence_score}/100 confidence · {avm.n_comps || 0} comps · {avm.sqm || '?'} sqm
        </p>
      </div>

      {/* ── Property Stats Grid ────────────────────────── */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 0, borderBottom: '1px solid var(--brand-line)', padding: '12px 0' }}>
        {[
          { label: 'SQM', value: avm.sqm || '-' },
          { label: 'EPC', value: avm.epc || '-' },
          { label: 'TYPE', value: (avm.type || '-').slice(0, 6) },
          { label: 'COMPS', value: avm.n_comps || '-' },
        ].map(d => (
          <div key={d.label} style={{ textAlign: 'center' }}>
            <div className="brand-label" style={{ fontSize: 8, color: 'var(--brand-muted)', letterSpacing: '0.15em' }}>
              {d.label}
            </div>
            <div style={{ fontFamily: '"Fraunces", Georgia, serif', fontSize: 15, fontWeight: 600, marginTop: 2 }}>
              {d.value}
            </div>
          </div>
        ))}
      </div>

      {/* ── Tribute Menu: Unlock Data ──────────────────── */}
      <div style={{ padding: '16px 16px 8px' }}>
        <div className="brand-label" style={{ fontSize: 10, color: 'var(--brand-muted)', marginBottom: 2, letterSpacing: '0.18em' }}>
          UNLOCK DATA INSIGHTS
        </div>
      </div>

      <div style={{ padding: '0 16px' }}>
        {allItems.map((item) => (
          <div
            key={item.id}
            className="tribute-row"
            onClick={() => handleSelectProduct(item)}
          >
            <span style={{ fontSize: 20, width: 28, textAlign: 'center' }}>
              {item.icon}
            </span>
            <div style={{ flex: 1, minWidth: 0 }}>
              <div className="ui-text" style={{ fontWeight: 600, fontSize: 13, color: 'var(--brand-ink)' }}>
                {item.name}
              </div>
              <div className="ui-text" style={{ fontSize: 11, color: 'var(--brand-muted)', marginTop: 1 }}>
                {item.description}
              </div>
            </div>
            <button
              className="tribute-pill"
              style={{
                background: 'var(--brand-dark)',
                color: 'var(--brand-cream)',
                flexShrink: 0,
              }}
              onClick={(e) => { e.stopPropagation(); handleSelectProduct(item); }}
            >
              🎁 {item.credits}
            </button>
          </div>
        ))}
      </div>

      {/* ── Evidence / Comps (collapsed) ────────────────── */}
      {avm.evidence?.length > 0 && (
        <div style={{ padding: '16px', marginTop: 8 }}>
          <details>
            <summary className="ui-text" style={{ fontSize: 12, color: 'var(--brand-muted)', cursor: 'pointer', padding: '8px 0' }}>
              📋 Sold evidence ({avm.evidence.length})
            </summary>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 6, marginTop: 8 }}>
              {avm.evidence.slice(0, 5).map((e, i) => (
                <div key={i} style={{ display: 'flex', justifyContent: 'space-between', padding: '6px 0', borderBottom: '1px solid var(--brand-line)' }}>
                  <div className="ui-text" style={{ fontSize: 12, color: 'var(--brand-muted)' }}>
                    {e.address?.slice(0, 30)}...
                  </div>
                  <div style={{ fontFamily: '"Fraunces", Georgia, serif', fontSize: 13, fontWeight: 600 }}>
                    {formatPrice(e.price)}
                  </div>
                </div>
              ))}
            </div>
          </details>
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
          }}
        />
      )}

      {/* ── Footer ─────────────────────────────────────── */}
      <div className="brand-hair" style={{ margin: '16px 16px 8px' }} />
      <p className="brand-label" style={{ textAlign: 'center', color: 'var(--brand-muted)', fontSize: 9, letterSpacing: '0.18em', padding: '0 16px' }}>
        Honestly · your property's price, proved
      </p>
    </div>
  );
}
