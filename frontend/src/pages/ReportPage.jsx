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
    credits: 149,
    gbp: 1.49,
    emotion: 'anger',
  },
  {
    id: 'council_tax_challenger',
    emoji: '😡',
    title: 'Council Tax Banding Challenge',
    teaser: 'I compared your EPC and sqm against 12 neighbouring properties. You might be overpaying by \u00a3340/year.',
    credits: 299,
    gbp: 2.99,
    emotion: 'anger',
  },
  {
    id: 'leasehold_trap_xray',
    emoji: '😰',
    title: 'Leasehold Trap X-Ray',
    teaser: 'I found the ground rent clause. If it escalates above \u00a3250/year, your mortgage offer could be revoked.',
    credits: 499,
    gbp: 4.99,
    emotion: 'fear',
  },
  {
    id: 'planning_permission_oracle',
    emoji: '😴',
    title: 'Can I Build Without Permission?',
    teaser: 'Your roof is pitched with a gable end. That means you can add 40 cubic metres under PD rules... probably.',
    credits: 249,
    gbp: 2.49,
    emotion: 'laziness',
  },
  {
    id: 'gentrification_radar',
    emoji: '💰',
    title: 'Gentrification Radar',
    teaser: '3 new cafes opened within 0.5mi in the last 6 months. Reddit chatter is up 240%. Early signal.',
    credits: 299,
    gbp: 2.99,
    emotion: 'greed',
  },
  {
    id: 'syndicate_street_map',
    emoji: '💰',
    title: 'Syndicate Street Map',
    teaser: '2 properties on this street are owned by offshore LLCs. One was bought for \u00a3185k in 2004.',
    credits: 1499,
    gbp: 14.99,
    emotion: 'greed',
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
    // Restore unlocked state from session
    try {
      const raw = sessionStorage.getItem('honestly_unlocked');
      if (raw) setUnlockedIds(new Set(JSON.parse(raw)));
    } catch {}
  }, []);

  const handleUnlockComplete = (res, productId) => {
    const newUnlocked = new Set(unlockedIds);
    newUnlocked.add(productId);
    setUnlockedIds(newUnlocked);
    sessionStorage.setItem('honestly_unlocked', JSON.stringify([...newUnlocked]));
  };

  if (!avmResult) {
    return (
      <div style={{ padding: '40px 16px', textAlign: 'center' }}>
        <div style={{ fontSize: 48, marginBottom: 12 }}>🔍</div>
        <h2 style={{ fontFamily: '"Fraunces", Georgia, serif', fontSize: 22, fontWeight: 600, margin: '0 0 8px' }}>
          No property yet
        </h2>
        <p className="ui-text" style={{ fontSize: 14, color: 'var(--brand-muted)', margin: '0 0 20px' }}>
          Value a property first to see its profile here.
        </p>
        <button
          onClick={() => navigate('/feed')}
          className="unlock-button"
          style={{ width: 'auto', padding: '14px 32px', fontSize: 15 }}
        >
          🔍 Value a Property
        </button>
      </div>
    );
  }

  const avm = avmResult.avm || {};

  const confidencePct = Math.min(100, Math.max(0, avm.confidence_score || 0));
  const gaugeColor = confidencePct >= 80 ? 'var(--brand-green)' : confidencePct >= 60 ? 'var(--brand-terra)' : confidencePct >= 40 ? 'var(--brand-gold)' : '#c73a3a';

  const valuationContext = {
    address: avm.address, postcode: avm.postcode,
    central: avm.central, low: avm.low, high: avm.high,
    confidence_score: avm.confidence_score, confidence_grade: avm.confidence_grade,
    sqm: avm.sqm, epc: avm.epc, type: avm.type, evidence: avm.evidence,
  };

  // Filter to only show products relevant to this property
  const triggers_map = {};
  (avmResult.product_triggers || []).forEach(t => { triggers_map[t.product_id] = t; });

  const relevantPosts = LOCKED_POSTS.filter(p => {
    // Always show all for now — orchestrator relevance scores will filter later
    return true;
  }).slice(0, 6);

  return (
    <div style={{ padding: '0 0 100px' }}>
      {/* ── Profile Header ─────────────────────────────── */}
      <div style={{
        position: 'relative',
        overflow: 'hidden',
        padding: '60px 20px 20px',
        textAlign: 'center',
        background: 'linear-gradient(180deg, var(--brand-dark) 0%, var(--brand-cream) 100%)',
      }}>
        {/* Decorative blurred gradient overlay (like tribute profile bg) */}
        <div style={{
          position: 'absolute', inset: 0,
          background: 'radial-gradient(ellipse at 70% 20%, rgba(21,128,127,0.3) 0%, transparent 60%), radial-gradient(ellipse at 30% 80%, rgba(14,39,71,0.4) 0%, transparent 50%)',
          zIndex: 0,
        }} />

        <div style={{ position: 'relative', zIndex: 1 }}>
          <p className="ui-text" style={{ fontSize: 13, color: 'rgba(246,243,236,0.7)', margin: '0 0 2px' }}>
            📍 {avm.address}
          </p>
          <h1 style={{
            fontFamily: '"Fraunces", Georgia, serif',
            fontSize: 46, fontWeight: 700, margin: '2px 0',
            letterSpacing: '-0.03em', lineHeight: 0.95,
            color: '#f6f3ec',
          }}>
            {formatPrice(avm.central)}
          </h1>
          <p className="ui-text" style={{ fontSize: 12, color: 'rgba(246,243,236,0.5)', margin: '0 0 12px' }}>
            {formatPrice(avm.low)} &ndash; {formatPrice(avm.high)}
          </p>

          <div style={{ maxWidth: 200, margin: '0 auto' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
              <div className="gauge-track" style={{ flex: 1, height: 3, background: 'rgba(246,243,236,0.2)' }}>
                <div className="gauge-fill" style={{ width: `${confidencePct}%`, background: gaugeColor, height: 3 }} />
              </div>
              <span className="ui-text" style={{ fontSize: 10, color: 'rgba(246,243,236,0.6)', minWidth: 30, textAlign: 'right' }}>
                {confidencePct}%
              </span>
            </div>
          </div>

          {/* Stats row */}
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
      </div>

      {/* ── Free Post: AVM Summary ─────────────────────── */}
      <div style={{ padding: '16px' }}>
        <div style={{
          background: 'var(--brand-paper)',
          borderRadius: 12,
          border: '1px solid var(--brand-line)',
          overflow: 'hidden',
        }}>
          <div style={{ padding: '14px 16px', borderBottom: '1px solid var(--brand-line)', display: 'flex', alignItems: 'center', gap: 8 }}>
            <span style={{ fontSize: 16 }}>📄</span>
            <span className="ui-text" style={{ fontWeight: 600, fontSize: 13 }}>Property Valuation</span>
            <span className="brand-label" style={{ marginLeft: 'auto', fontSize: 9, color: 'var(--brand-green)' }}>FREE</span>
          </div>

          {/* 3 strict comparables as the "free post" content */}
          {(avm.evidence || []).slice(0, 3).map((e, i) => (
            <div key={i} style={{
              display: 'flex', justifyContent: 'space-between', alignItems: 'center',
              padding: '10px 16px',
              borderBottom: i < 2 ? '1px solid var(--brand-line)' : 'none',
            }}>
              <div style={{ flex: 1, minWidth: 0 }}>
                <div className="ui-text" style={{ fontSize: 12, fontWeight: 500, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
                  {e.address || 'Unknown'}
                </div>
                <div className="ui-text" style={{ fontSize: 10, color: 'var(--brand-muted)' }}>
                  {e.date ? e.date.slice(0, 7) : ''} · {e.sqm || '?'} sqm
                </div>
              </div>
              <div style={{ fontFamily: '"Fraunces", Georgia, serif', fontSize: 14, fontWeight: 600, color: 'var(--brand-green)' }}>
                {formatPrice(e.price)}
              </div>
            </div>
          ))}

          {(!avm.evidence || avm.evidence.length === 0) && (
            <div className="ui-text" style={{ padding: '16px', fontSize: 12, color: 'var(--brand-muted)', textAlign: 'center' }}>
              No recent sold comparables for this area
            </div>
          )}
        </div>
      </div>

      {/* ── Locked Content Feed ────────────────────────── */}
      <div style={{ padding: '0 16px' }}>
        <div className="brand-label" style={{ fontSize: 10, color: 'var(--brand-muted)', marginBottom: 10, letterSpacing: '0.18em', padding: '0 2px' }}>
          EXCLUSIVE INSIGHTS
        </div>

        <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
          {relevantPosts.map((post) => {
            const isUnlocked = unlockedIds.has(post.id);
            return (
              <div
                key={post.id}
                className="locked-card"
                onClick={() => {
                  if (!isUnlocked) {
                    window.Telegram?.WebApp?.HapticFeedback?.impactOccurred?.('light');
                    setSelectedProduct(post);
                  }
                }}
              >
                {/* Teaser content (always visible) */}
                <div style={{ padding: '14px 16px 0' }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 6 }}>
                    <span style={{ fontSize: 16 }}>{post.emoji}</span>
                    <span className="ui-text" style={{ fontWeight: 600, fontSize: 13 }}>{post.title}</span>
                  </div>
                  <p className="ui-text" style={{ fontSize: 12, color: 'var(--brand-muted)', lineHeight: 1.5, margin: '0 0 10px' }}>
                    {post.teaser}
                  </p>
                </div>

                {/* Blurred locked section */}
                {!isUnlocked ? (
                  <div style={{ position: 'relative', minHeight: 64 }}>
                    <div className="blurred-content" style={{ padding: '0 16px 16px' }}>
                      <div style={{ height: 40, background: 'var(--brand-line)', borderRadius: 6, marginBottom: 6 }} />
                      <div style={{ height: 12, width: '60%', background: 'var(--brand-line)', borderRadius: 3 }} />
                    </div>
                    {/* Lock overlay */}
                    <div className="lock-overlay">
                      <span style={{ fontSize: 28 }}>🔒</span>
                      <button
                        className="tribute-pill"
                        style={{
                          background: 'var(--brand-dark)',
                          color: 'var(--brand-cream)',
                          fontSize: 12,
                          padding: '8px 18px',
                        }}
                        onClick={(e) => {
                          e.stopPropagation();
                          window.Telegram?.WebApp?.HapticFeedback?.impactOccurred?.('light');
                          setSelectedProduct(post);
                        }}
                      >
                        Send {post.credits} Credits to Unlock
                      </button>
                    </div>
                  </div>
                ) : (
                  /* Unlocked content replacement */
                  <div style={{ padding: '0 16px 14px' }}>
                    <div className="brand-label" style={{ fontSize: 9, color: 'var(--brand-green)' }}>✓ UNLOCKED</div>
                    <div style={{
                      height: 40,
                      background: 'rgba(21,128,127,0.08)',
                      borderRadius: 6,
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'center',
                      fontSize: 12,
                      color: 'var(--brand-green)',
                      fontWeight: 500,
                    }}>
                      Content ready &mdash; check your delivery
                    </div>
                  </div>
                )}
              </div>
            );
          })}
        </div>
      </div>

      {/* ── Bottom sheet ────────────────────────────────── */}
      {selectedProduct && (
        <ProductSheet
          product={selectedProduct}
          valuationContext={valuationContext}
          onClose={() => setSelectedProduct(null)}
          onComplete={(res) => {
            handleUnlockComplete(res, selectedProduct.id || selectedProduct.product_id);
            setSelectedProduct(null);
          }}
        />
      )}

      {/* ── Brand footer ──────────────────────────────── */}
      <div className="brand-hair" style={{ margin: '20px 16px 8px' }} />
      <p className="brand-label" style={{ textAlign: 'center', color: 'var(--brand-muted)', fontSize: 9, letterSpacing: '0.18em', padding: '0 16px' }}>
        Honestly · your property's price, proved
      </p>
    </div>
  );
}
