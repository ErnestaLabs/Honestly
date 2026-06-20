import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import ProductSheet from '../components/ProductSheet';
import { saveLastAvm, loadLastAvm } from '../utils/tgStorage';

function fmt(n) {
  if (!n) return '\u2014';
  return '\u00a3' + Number(n).toLocaleString('en-GB');
}

const LOCKED_INSIGHTS = [
  {
    id: 'lowball_counter_email',
    title: 'Counter-Offer Analysis',
    teaser: '3 comparable sales within 0.5mi transacted at an average of \u00a3412,000. The subject\u2019s assessed value suggests a 12% gap between offer and market price.',
    preview: 'Comparable set: 3 transactions within 0.5mi / 6mo. Weighted median \u00a3/sqm: \u00a34,120. Subject\u2019s implied value at this rate: \u00a3576,800 vs \u00a3515,000 central. The lowball gap is approximately \u00a361,800.',
    price: 1.49,
  },
  {
    id: 'council_tax_challenger',
    title: 'Council Tax Audit',
    teaser: '12 neighbouring properties within 0.3mi average 128 sqm in Band C. The subject is 140 sqm in Band D \u2014 a potential overpayment of \u00a328/month.',
    preview: 'Neighbour set: 12 properties, avg 128 sqm. Band distribution: 7 in Band C, 3 in Band B, 2 in Band D. Subject: 140 sqm, Band D. Estimated 1991 value at subject\u2019s size: \u00a364,000 (Band C threshold: \u00a368,000). Annual overpayment: \u00a3340.',
    price: 2.99,
  },
  {
    id: 'leasehold_trap_xray',
    title: 'Leasehold Assessment',
    teaser: '87 years remaining. Ground rent escalates above \u00a3250 within 12 years. Mortgage lenders may decline below 80 years.',
    preview: 'Lease term: 125 yrs from 2003. Unexpired: 87 yrs. Ground rent: \u00a3150/yr, doubling every 25 yrs. Estimated Section 42 cost: \u00a312,500\u2013\u00a316,800. Mortgage警戒: <80 yrs triggers lender restrictions. Timeline: ~7 yrs.',
    price: 4.99,
  },
  {
    id: 'planning_permission_oracle',
    title: 'Permitted Development Check',
    teaser: 'Pitched gable roof, non-conservation area. Up to 40m\u00b3 additional volume allowable under PD rules.',
    preview: 'Roof: pitched gable. PD volume limit: 40m\u00b3 (terraced). Conservation area: no. Hip-to-gable extension: PD. Rear dormer: PD subject to 40m\u00b3 limit. Side windows: obscure glazing required. Max ridge: 12m.',
    price: 2.49,
  },
  {
    id: 'gentrification_radar',
    title: 'Area Growth Forecast',
    teaser: 'Price trend: +8.2% YoY. 3 new F&B openings within 0.5mi. Reddit locality chatter up 240% over 6 months.',
    preview: 'YoY price growth: +8.2% (vs SE15 avg +3.1%). 5-yr forecast: +32% (linear). New developments: 2 sites within 0.3mi. Transport: Crossrail 2 proposal 0.4mi. Amenity score: 84/100. Risk: softening macro (-2.8%/yr SE15).',
    price: 2.99,
  },
  {
    id: 'syndicate_street_map',
    title: 'Ownership Intelligence',
    teaser: '2 properties on this street held by offshore entities. One acquired for \u00a3185k in 2004; estimated current value \u00a3720k.',
    preview: '12 Maple Road: BVI-registered owner, bought 2004 \u00a3185k, est. current \u00a3720k (+289%). 8 Maple Road: Hong Kong corp since 1998. 3 properties held 20+ yrs (equity hoarders). Total estimated unmobilised equity: \u00a31.2M.',
    price: 14.99,
  },
];

export default function ReportPage() {
  const navigate = useNavigate();
  const [data, setData] = useState(null);
  const [selected, setSelected] = useState(null);
  const [unlocked, setUnlocked] = useState(new Set());

  useEffect(() => {
    window.Telegram?.WebApp?.expand?.();
    (async () => {
      try { const s = await loadLastAvm(); if (s) setData(s); } catch {}
      try {
        const r = sessionStorage.getItem('honestly_unlocked');
        if (r) setUnlocked(new Set(JSON.parse(r)));
      } catch {}
    })();
  }, []);

  const handleUnlock = (res, id) => {
    const u = new Set(unlocked);
    u.add(id);
    setUnlocked(u);
    sessionStorage.setItem('honestly_unlocked', JSON.stringify([...u]));
    setSelected(null);
  };

  if (!data) {
    return (
      <div style={{ padding: '48px 20px', textAlign: 'center' }}>
        <div style={{ fontFamily: '"Fraunces", Georgia, serif', fontSize: 22, fontWeight: 500, color: 'var(--brand-ink)', marginBottom: 8 }}>
          No property data
        </div>
        <p className="ui-text" style={{ fontSize: 13, color: 'var(--brand-muted)', marginBottom: 24 }}>
          Run a valuation to access property insights.
        </p>
        <button onClick={() => navigate('/')} style={{
          padding: '12px 28px', borderRadius: 6,
          background: 'var(--brand-dark)', color: 'var(--brand-cream)',
          border: 'none', fontSize: 14, fontWeight: 500, cursor: 'pointer',
        }}>
          Value a Property
        </button>
      </div>
    );
  }

  const a = data.avm || {};
  const cp = Math.min(100, Math.max(0, a.confidence_score || 0));
  const gc = cp >= 80 ? '#15807f' : cp >= 60 ? '#2aa39a' : cp >= 40 ? '#d89a32' : '#c73a3a';

  const ctx = {
    address: a.address, postcode: a.postcode, central: a.central,
    low: a.low, high: a.high, confidence_score: a.confidence_score,
    confidence_grade: a.confidence_grade, sqm: a.sqm, epc: a.epc,
    type: a.type, evidence: a.evidence,
  };

  return (
    <div style={{ padding: '0 0 80px' }}>
      {/* Header */}
      <div style={{ background: 'var(--brand-dark)', padding: '32px 20px 20px' }}>
        <div className="ui-text" style={{ fontSize: 9, color: 'rgba(246,243,236,0.35)', textTransform: 'uppercase', letterSpacing: '0.18em', marginBottom: 1 }}>
          Property Report
        </div>
        <div className="ui-text" style={{ fontSize: 9, color: 'rgba(246,243,236,0.2)', marginBottom: 10 }}>
          {new Date().toLocaleDateString('en-GB', { day: 'numeric', month: 'short', year: 'numeric' })}
        </div>
        <p className="ui-text" style={{ fontSize: 11, color: 'rgba(246,243,236,0.5)', marginBottom: 4 }}>
          {a.address}
        </p>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-end' }}>
          <div>
            <h1 style={{
              fontFamily: '"Fraunces", Georgia, serif', fontWeight: 600, fontSize: 34,
              color: '#f6f3ec', margin: 0, letterSpacing: '-0.03em',
            }}>
              {fmt(a.central)}
            </h1>
            <p className="ui-text" style={{ fontSize: 11, color: 'rgba(246,243,236,0.35)', marginTop: 1 }}>
              {fmt(a.low)} \u2013 {fmt(a.high)}
            </p>
          </div>
          <div style={{ textAlign: 'right' }}>
            <div className="ui-text" style={{ fontSize: 9, color: 'rgba(246,243,236,0.35)', textTransform: 'uppercase' }}>Confidence</div>
            <div style={{ fontFamily: '"Fraunces", Georgia, serif', fontSize: 18, fontWeight: 600, color: gc, marginTop: 1 }}>
              {cp}%
            </div>
          </div>
        </div>
      </div>

      {/* Stats strip */}
      <div style={{ display: 'flex', borderBottom: '1px solid var(--brand-line)' }}>
        {[
          ['SQM', a.sqm || '\u2014'],
          ['EPC', a.epc || '\u2014'],
          ['TYPE', (a.type || '\u2014').slice(0, 4).toUpperCase()],
          ['COMPS', a.n_comps || '\u2014'],
        ].map(([l, v], i) => (
          <div key={l} style={{
            flex: 1, padding: '8px 4px', textAlign: 'center',
            borderRight: i < 3 ? '1px solid var(--brand-line)' : 'none',
          }}>
            <div style={{ fontFamily: '"Fraunces", Georgia, serif', fontSize: 14, fontWeight: 600 }}>{v}</div>
            <div className="ui-text" style={{ fontSize: 7, color: 'var(--brand-muted)', textTransform: 'uppercase', letterSpacing: '0.12em' }}>{l}</div>
          </div>
        ))}
      </div>

      {/* Free data: comparables */}
      {(a.evidence || []).length > 0 && (
        <div style={{ padding: '12px 20px', borderBottom: '1px solid var(--brand-line)' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 6 }}>
            <div className="ui-text" style={{ fontSize: 9, color: 'var(--brand-muted)', textTransform: 'uppercase', letterSpacing: '0.12em' }}>
              Sold comparables
            </div>
            <div className="ui-text" style={{ fontSize: 8, color: 'var(--brand-green)', textTransform: 'uppercase', letterSpacing: '0.1em', fontWeight: 500 }}>
              Free
            </div>
          </div>
          {(a.evidence || []).slice(0, 3).map((e, i) => (
            <div key={i} style={{ display: 'flex', justifyContent: 'space-between', padding: '5px 0', borderTop: '1px solid var(--brand-line)' }}>
              <div className="ui-text" style={{ fontSize: 10, color: 'var(--brand-ink)' }}>
                {e.address?.slice(0, 30)}
              </div>
              <div style={{ fontFamily: '"Fraunces", Georgia, serif', fontSize: 12, fontWeight: 600, color: 'var(--brand-green)' }}>
                {fmt(e.price)}
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Locked insights */}
      <div style={{ padding: '14px 20px' }}>
        <div className="ui-text" style={{
          fontSize: 9, color: 'var(--brand-muted)', textTransform: 'uppercase',
          letterSpacing: '0.12em', marginBottom: 10,
        }}>
          Exclusive data insights
        </div>

        {LOCKED_INSIGHTS.map((ins) => {
          const isUnlocked = unlocked.has(ins.id);
          return (
            <div
              key={ins.id}
              onClick={() => { if (!isUnlocked) { window.Telegram?.WebApp?.HapticFeedback?.impactOccurred?.('light'); setSelected(ins); }}}
              style={{
                marginBottom: 10,
                borderRadius: 6,
                border: `1px solid ${isUnlocked ? 'rgba(21,128,127,0.3)' : 'var(--brand-line)'}`,
                overflow: 'hidden',
                cursor: isUnlocked ? 'default' : 'pointer',
                background: isUnlocked ? 'rgba(21,128,127,0.03)' : 'var(--brand-paper)',
              }}
            >
              {/* Teaser */}
              <div style={{ padding: '10px 12px' }}>
                <div className="ui-text" style={{
                  fontSize: 11, fontWeight: 600, color: 'var(--brand-ink)', marginBottom: 3,
                }}>
                  {ins.title}
                </div>
                <div className="ui-text" style={{ fontSize: 10, color: 'var(--brand-muted)', lineHeight: 1.5 }}>
                  {ins.teaser}
                </div>
              </div>

              {/* Blurred preview + overlay */}
              {!isUnlocked ? (
                <div style={{ position: 'relative', borderTop: '1px solid var(--brand-line)' }}>
                  <div style={{
                    filter: 'blur(6px)', WebkitFilter: 'blur(6px)',
                    padding: '10px 12px',
                    pointerEvents: 'none', userSelect: 'none',
                  }}>
                    <div className="ui-text" style={{ fontSize: 10, lineHeight: 1.6, color: 'var(--brand-ink)' }}>
                      {ins.preview}
                    </div>
                  </div>
                  <div style={{
                    position: 'absolute', inset: 0,
                    display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 8,
                    background: 'linear-gradient(rgba(246,243,236,0.1), rgba(246,243,236,0.3))',
                  }}>
                    <span style={{ fontSize: 16 }}>🔒</span>
                    <span className="ui-text" style={{
                      fontSize: 11, fontWeight: 500, color: 'var(--brand-ink)',
                      padding: '6px 14px',
                      border: '1px solid var(--brand-line)',
                      borderRadius: 4,
                      background: 'var(--brand-paper)',
                    }}>
                      Unlock \u2014 \u00a3{ins.price.toFixed(2)}
                    </span>
                  </div>
                </div>
              ) : (
                /* Revealed content */
                <div style={{ borderTop: '1px solid rgba(21,128,127,0.2)', padding: '10px 12px' }}>
                  <div className="ui-text" style={{ fontSize: 9, color: 'var(--brand-green)', textTransform: 'uppercase', letterSpacing: '0.1em', marginBottom: 4 }}>
                    \u2713 Unlocked
                  </div>
                  <div className="ui-text" style={{ fontSize: 10, lineHeight: 1.6, color: 'var(--brand-ink)' }}>
                    {ins.preview}
                  </div>
                </div>
              )}
            </div>
          );
        })}
      </div>

      {selected && (
        <ProductSheet
          product={selected}
          valuationContext={ctx}
          onClose={() => setSelected(null)}
          onComplete={(res) => handleUnlock(res, selected.id)}
        />
      )}

      <div style={{ padding: '8px 20px' }}>
        <div style={{ height: 1, background: 'var(--brand-line)', marginBottom: 8 }} />
        <p className="ui-text" style={{ fontSize: 8, color: 'var(--brand-muted)', textAlign: 'center' }}>
          HM Land Registry \u00b7 EPC Register \u00b7 ONS
        </p>
      </div>
    </div>
  );
}
