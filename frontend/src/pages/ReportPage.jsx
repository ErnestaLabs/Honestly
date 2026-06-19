import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import ProductSheet from '../components/ProductSheet';
import { saveLastAvm, loadLastAvm } from '../utils/tgStorage';

function formatPrice(n) {
  if (!n) return '\u2014';
  return '\u00a3' + Number(n).toLocaleString('en-GB');
}

const LOCKED_POSTS = [
  {
    id: 'lowball_counter_email',
    emoji: '😡',
    title: 'Are They Taking The Piss?',
    teaser: 'I analysed the lowball offer against 3 sold comparables on this street... the gap is bigger than they think.',
    energy: 149,
    gbp: 1.49,
    emotion: 'anger',
    preview: 'Your agent received an offer of £350,000. Based on 3 strict comparables (avg £412,000), the property is undervalued by approximately £62,000. The counter-offer should start at £405,000.',
  },
  {
    id: 'council_tax_challenger',
    emoji: '😡',
    title: 'Council Tax Banding Challenge',
    teaser: 'I compared your EPC and sqm against 12 neighbouring properties. You might be overpaying by \u00a3340/year.',
    energy: 299,
    gbp: 2.99,
    emotion: 'anger',
    preview: 'Your property (140 sqm, Band D) vs 12 neighbours: avg 128 sqm, Band C. 7 similar-sized properties are in lower bands. Estimated overpayment: £28/month.',
  },
  {
    id: 'leasehold_trap_xray',
    emoji: '😰',
    title: 'Leasehold Trap X-Ray',
    teaser: 'I found the ground rent clause. If it escalates above \u00a3250/year, your mortgage offer could be revoked.',
    energy: 499,
    gbp: 4.99,
    emotion: 'fear',
    preview: 'Lease: 87 years remaining. Ground rent: £150/yr, doubling every 25 years. Estimated Section 42 extension cost: £12,500. Mortgage risk if lease drops below 80 years.',
  },
  {
    id: 'planning_permission_oracle',
    emoji: '😴',
    title: 'Can I Build Without Permission?',
    teaser: 'Your roof is pitched with a gable end. That means you can add 40 cubic metres under PD rules... probably.',
    energy: 249,
    gbp: 2.49,
    emotion: 'laziness',
    preview: 'Roof type: pitched gable. PD volume limit: 40m\u00b3. Loft conversion: LIKELY PD. Conservation area: No. Hip-to-gable extension: also PD. Max ridge height: 12m.',
  },
  {
    id: 'gentrification_radar',
    emoji: '💰',
    title: 'Gentrification Radar',
    teaser: '3 new cafes opened within 0.5mi in the last 6 months. Reddit chatter is up 240%. Early signal.',
    energy: 299,
    gbp: 2.99,
    emotion: 'greed',
    preview: 'Price trend: +8.2% YoY. 5-yr forecast: +32%. New developments: 2 within 0.3mi. Transport: Crossrail 2 proposed 0.4mi. Amenity score: 84/100.',
  },
  {
    id: 'syndicate_street_map',
    emoji: '💰',
    title: 'Syndicate Street Map',
    teaser: '2 properties on this street are owned by offshore LLCs. One was bought for \u00a3185k in 2004.',
    energy: 1499,
    gbp: 14.99,
    emotion: 'greed',
    preview: '12 Maple Road — bought 2004 \u00a3185k, current est. \u00a3720k. Owner: BVI-registered entity. 8 Maple Road — owned by Hong Kong Corp since 1998. Equity hoarders: 3 properties held 20+ years.',
  },
];

export default function ReportPage() {
  const navigate = useNavigate();
  const [avmResult, setAvmResult] = useState(null);
  const [selectedProduct, setSelectedProduct] = useState(null);
  const [unlockedIds, setUnlockedIds] = useState(new Set());

  useEffect(() => {
    window.Telegram?.WebApp?.expand?.();
    const load = async () => {
      try {
        const stored = await loadLastAvm();
        if (stored) setAvmResult(stored);
      } catch {}
    };
    load();
    try {
      const raw = sessionStorage.getItem('honestly_unlocked');
      if (raw) setUnlockedIds(new Set(JSON.parse(raw)));
    } catch {}
  }, []);

  const handleUnlockComplete = (res, productId) => {
    const updated = new Set(unlockedIds);
    updated.add(productId);
    setUnlockedIds(updated);
    sessionStorage.setItem('honestly_unlocked', JSON.stringify([...updated]));
  };

  if (!avmResult) {
    return (
      <div style={{ padding: '48px 16px', textAlign: 'center' }}>
        <div style={{ fontFamily: '"Fraunces", Georgia, serif', fontSize: 22, fontWeight: 600, color: 'var(--brand-ink)', marginBottom: 8 }}>
          No property yet
        </div>
        <p className="ui-text" style={{ fontSize: 14, color: 'var(--brand-muted)', marginBottom: 24 }}>
          Value a property first to see its exclusive data insights.
        </p>
        <button onClick={() => navigate('/feed')} className="purchase-button" style={{ width: 'auto', padding: '14px 32px' }}>
          Value a Property
        </button>
      </div>
    );
  }

  const avm = avmResult.avm || {};
  const confidencePct = Math.min(100, Math.max(0, avm.confidence_score || 0));
  const gaugeColor = confidencePct >= 80 ? '#15807f' : confidencePct >= 60 ? '#2aa39a' : confidencePct >= 40 ? '#d89a32' : '#c73a3a';

  const valuationContext = {
    address: avm.address, postcode: avm.postcode,
    central: avm.central, low: avm.low, high: avm.high,
    confidence_score: avm.confidence_score, confidence_grade: avm.confidence_grade,
    sqm: avm.sqm, epc: avm.epc, type: avm.type, evidence: avm.evidence,
  };

  const relevantPosts = LOCKED_POSTS.slice(0, 6);

  return (
    <div style={{ padding: '0 0 100px' }}>
      {/* ── Profile Header ─────────────────────────────── */}
      <div style={{
        padding: '36px 20px 20px',
        textAlign: 'center',
        background: 'linear-gradient(180deg, var(--brand-dark) 0%, var(--brand-cream) 100%)',
      }}>
        <p className="ui-text" style={{ fontSize: 13, color: 'rgba(246,243,236,0.6)', marginBottom: 2 }}>
          📍 {avm.address}
        </p>
        <h1 style={{
          fontFamily: '"Fraunces", Georgia, serif',
          fontSize: 44, fontWeight: 700, margin: '2px 0',
          letterSpacing: '-0.03em', lineHeight: 0.95,
          color: '#f6f3ec',
        }}>
          {formatPrice(avm.central)}
        </h1>
        <p className="ui-text" style={{ fontSize: 12, color: 'rgba(246,243,236,0.5)', marginBottom: 12 }}>
          {formatPrice(avm.low)} &ndash; {formatPrice(avm.high)}
        </p>

        <div style={{ maxWidth: 200, margin: '0 auto' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
            <div style={{ flex: 1, height: 3, background: 'rgba(246,243,236,0.2)', borderRadius: 2, overflow: 'hidden' }}>
              <div style={{ width: `${confidencePct}%`, height: '100%', background: gaugeColor }} />
            </div>
            <span className="ui-text" style={{ fontSize: 10, color: 'rgba(246,243,236,0.6)' }}>
              {confidencePct}%
            </span>
          </div>
        </div>

        <div style={{ display: 'flex', justifyContent: 'center', gap: 24, marginTop: 14 }}>
          {[
            { label: 'SQM', value: avm.sqm || '-' },
            { label: 'EPC', value: avm.epc || '-' },
            { label: 'COMPS', value: avm.n_comps || '-' },
          ].map(d => (
            <div key={d.label} style={{ textAlign: 'center' }}>
              <div style={{ fontFamily: '"Fraunces", Georgia, serif', fontSize: 18, fontWeight: 700, color: '#f6f3ec' }}>
                {d.value}
              </div>
              <div className="brand-label" style={{ fontSize: 8, color: 'rgba(246,243,236,0.5)', letterSpacing: '0.15em' }}>
                {d.label}
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* ── Free Post: Valuation Summary ──────────────── */}
      <div style={{ padding: '16px' }}>
        <div style={{
          background: 'var(--brand-paper)', borderRadius: 12,
          border: '1px solid var(--brand-line)', overflow: 'hidden',
        }}>
          <div style={{
            padding: '14px 16px', borderBottom: '1px solid var(--brand-line)',
            display: 'flex', alignItems: 'center', gap: 8,
          }}>
            <span style={{ fontSize: 16 }}>📄</span>
            <span className="ui-text" style={{ fontWeight: 600, fontSize: 13 }}>Property Valuation</span>
            <span className="brand-label" style={{ marginLeft: 'auto', fontSize: 9, color: 'var(--brand-green)' }}>FREE</span>
          </div>
          {(avm.evidence || []).slice(0, 3).map((e, i) => (
            <div key={i} style={{
              display: 'flex', justifyContent: 'space-between', padding: '10px 16px',
              borderBottom: i < 2 ? '1px solid var(--brand-line)' : 'none',
            }}>
              <div>
                <div className="ui-text" style={{ fontSize: 12, fontWeight: 500 }}>{e.address}</div>
                <div className="ui-text" style={{ fontSize: 10, color: 'var(--brand-muted)' }}>
                  {e.date?.slice(0, 7)} · {e.sqm} sqm
                </div>
              </div>
              <div style={{ fontFamily: '"Fraunces", Georgia, serif', fontSize: 14, fontWeight: 600, color: 'var(--brand-green)' }}>
                {formatPrice(e.price)}
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* ── Locked Content Feed ────────────────────────── */}
      <div style={{ padding: '0 16px' }}>
        <div className="brand-label" style={{ fontSize: 10, color: 'var(--brand-muted)', marginBottom: 10, padding: '0 2px' }}>
          EXCLUSIVE INSIGHTS
        </div>

        <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
          {relevantPosts.map((post) => {
            const isUnlocked = unlockedIds.has(post.id);
            return (
              <div
                key={post.id}
                onClick={() => {
                  if (!isUnlocked) {
                    window.Telegram?.WebApp?.HapticFeedback?.impactOccurred?.('light');
                    setSelectedProduct(post);
                  }
                }}
                style={{
                  position: 'relative', borderRadius: 12, overflow: 'hidden',
                  background: 'var(--brand-paper)',
                  border: `1px solid ${isUnlocked ? 'rgba(21,128,127,0.3)' : 'var(--brand-line)'}`,
                  cursor: isUnlocked ? 'default' : 'pointer',
                }}
              >
                {/* Teaser */}
                <div style={{ padding: '14px 16px 0' }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 6 }}>
                    <span style={{ fontSize: 16 }}>{post.emoji}</span>
                    <span className="ui-text" style={{ fontWeight: 600, fontSize: 13 }}>{post.title}</span>
                  </div>
                  <p className="ui-text" style={{ fontSize: 12, color: 'var(--brand-muted)', lineHeight: 1.5, margin: '0 0 10px' }}>
                    {post.teaser}
                  </p>
                </div>

                {!isUnlocked ? (
                  <div style={{ position: 'relative', minHeight: 72 }}>
                    {/* Blurred data preview */}
                    <div style={{
                      filter: 'blur(8px)', WebkitFilter: 'blur(8px)',
                      pointerEvents: 'none', userSelect: 'none',
                      padding: '0 16px 14px',
                      fontSize: 11, lineHeight: 1.6, color: 'var(--brand-ink)',
                      fontFamily: '-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif',
                    }}>
                      {post.preview}
                    </div>
                    {/* Lock overlay */}
                    <div style={{
                      position: 'absolute', inset: 0,
                      display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', gap: 6,
                      background: 'rgba(246,243,236,0.2)', backdropFilter: 'blur(2px)',
                    }}>
                      <span style={{ fontSize: 28 }}>🔒</span>
                      <button
                        className="tribute-pill"
                        onClick={(e) => { e.stopPropagation(); setSelectedProduct(post); }}
                      >
                        Send {post.energy} Energy to Unlock
                      </button>
                    </div>
                  </div>
                ) : (
                  <div style={{ padding: '0 16px 14px' }}>
                    <div className="brand-label" style={{ fontSize: 9, color: 'var(--brand-green)' }}>✓ UNLOCKED</div>
                    <div className="ui-text" style={{ fontSize: 11, lineHeight: 1.6, color: 'var(--brand-ink)', marginTop: 4 }}>
                      {post.preview}
                    </div>
                  </div>
                )}
              </div>
            );
          })}
        </div>
      </div>

      {selectedProduct && (
        <ProductSheet
          product={selectedProduct}
          valuationContext={valuationContext}
          onClose={() => setSelectedProduct(null)}
          onComplete={(res) => {
            handleUnlockComplete(res, selectedProduct.id);
            setSelectedProduct(null);
          }}
        />
      )}

      <div style={{ height: 1, background: 'var(--brand-line)', margin: '24px 16px 8px' }} />
      <p className="brand-label" style={{ textAlign: 'center', color: 'var(--brand-muted)', fontSize: 9, padding: '0 16px' }}>
        Honestly · your property's price, proved
      </p>
    </div>
  );
}
