import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import ProductSheet from '../components/ProductSheet';
import { loadLastAvm } from '../utils/tgStorage';

function fmt(n) {
  if (!n) return '\u2014';
  return '\u00a3' + Number(n).toLocaleString('en-GB');
}

const PRODUCTS = [
  { id: 'lowball_counter_email', title: 'Counter-Offer Letter', desc: 'A data-backed email for your estate agent, referencing your sold comparables. Ready to send.', price: 1.49 },
  { id: 'council_tax_challenger', title: 'Council Tax Challenge', desc: 'A formal VOA letter comparing your floor area and EPC against neighbouring bands.', price: 2.99 },
  { id: 'leasehold_trap_xray', title: 'Leasehold Cost Report', desc: 'Section 42 extension cost, ground rent schedule, and lender risk timeline.', price: 4.99 },
  { id: 'planning_permission_oracle', title: 'Development Check', desc: 'Property-specific PD verdict: what you can build, volume limits, and conservation status.', price: 2.49 },
  { id: 'gentrification_radar', title: 'Area Growth Report', desc: '5-year price forecast, development pipeline, transport proposals, and amenity score.', price: 2.99 },
  { id: 'syndicate_street_map', title: 'Ownership Report', desc: 'LLC-held properties, equity hoarders, and off-market targets with mail-merge template.', price: 14.99 },
];

export default function ReportPage() {
  const navigate = useNavigate();
  const [data, setData] = useState(null);
  const [selected, setSelected] = useState(null);

  useEffect(() => {
    window.Telegram?.WebApp?.expand?.();
    (async () => {
      try { const s = await loadLastAvm(); if (s) setData(s); } catch {}
    })();
  }, []);

  if (!data) {
    return (
      <div style={{ padding: '48px 20px', textAlign: 'center' }}>
        <div className="glass-elevated" style={{ padding: '32px 20px' }}>
          <p className="label" style={{ marginBottom: 8 }}>No valuation yet</p>
          <p style={{ fontSize: 13, color: 'var(--brand-muted)', marginBottom: 20 }}>
            Run a free valuation first.
          </p>
          <button onClick={() => navigate('/')} className="btn-primary" style={{ width: 'auto', padding: '12px 28px', fontSize: 14 }}>
            Value a Property
          </button>
        </div>
      </div>
    );
  }

  const a = data.avm || {};
  const cp = Math.min(100, Math.max(0, a.confidence_score || 0));
  const gc = cp >= 80 ? '#34d399' : cp >= 60 ? '#2dd4bf' : cp >= 40 ? '#fbbf24' : '#f87171';
  const ctx = {
    address: a.address, postcode: a.postcode, central: a.central,
    low: a.low, high: a.high, confidence_score: a.confidence_score,
    confidence_grade: a.confidence_grade, sqm: a.sqm, epc: a.epc,
    type: a.type, evidence: a.evidence,
  };

  return (
    <div style={{ padding: '0 0 80px' }}>
      {/* ── Header ─────────────────────────────────────── */}
      <div style={{ padding: '28px 20px 20px' }}>
        <p className="label" style={{ marginBottom: 2 }}>Free Valuation Report</p>
        <p style={{ fontSize: 11, color: 'var(--brand-muted)', marginBottom: 14 }}>
          {new Date().toLocaleDateString('en-GB', { day: 'numeric', month: 'short', year: 'numeric' })}
        </p>

        <div className="glass-elevated" style={{ padding: '20px', textAlign: 'center' }}>
          <p style={{ fontSize: 12, color: 'var(--brand-muted)', marginBottom: 6 }}>
            {a.address}
          </p>
          <h1 style={{
            fontFamily: '"Fraunces", Georgia, serif', fontWeight: 600, fontSize: 38,
            color: 'var(--brand-ink)', letterSpacing: '-0.03em', lineHeight: 1,
            margin: '0 0 4px',
          }}>
            {fmt(a.central)}
          </h1>
          <p style={{ fontSize: 12, color: 'var(--brand-muted)', marginBottom: 14 }}>
            {fmt(a.low)} \u2013 {fmt(a.high)}
          </p>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, maxWidth: 200, margin: '0 auto' }}>
            <div className="gauge-track" style={{ flex: 1 }}>
              <div className="gauge-fill" style={{ width: `${cp}%`, background: gc }} />
            </div>
            <span style={{ fontSize: 14, fontWeight: 700, color: gc, letterSpacing: '-0.02em' }}>
              {cp}%
            </span>
          </div>
          <p className="label" style={{ marginTop: 4, fontSize: 9 }}>Confidence</p>
        </div>
      </div>

      {/* ── Stats ──────────────────────────────────────── */}
      <div style={{ padding: '0 20px 14px', display: 'flex', gap: 8 }}>
        {[
          ['SQM', a.sqm || '\u2014'],
          ['EPC', a.epc || '\u2014'],
          ['TYPE', (a.type || '\u2014').slice(0, 4).toUpperCase()],
          ['COMPS', a.n_comps || '\u2014'],
        ].map(([l, v]) => (
          <div key={l} className="glass" style={{ flex: 1, padding: '10px 6px', textAlign: 'center', borderRadius: 12 }}>
            <div className="display" style={{ fontSize: 15, fontWeight: 600 }}>{v}</div>
            <p className="label" style={{ fontSize: 8, marginTop: 2 }}>{l}</p>
          </div>
        ))}
      </div>

      {/* ── Comparables ────────────────────────────────── */}
      <div style={{ padding: '0 20px 14px' }}>
        <p className="label" style={{ marginBottom: 8 }}>Comparable Sales</p>
        {(a.evidence || []).length > 0 ? (
          <div className="glass" style={{ borderRadius: 14, overflow: 'hidden', padding: 0 }}>
            {(a.evidence || []).slice(0, 6).map((e, i) => (
              <div key={i} style={{
                display: 'flex', justifyContent: 'space-between', padding: '10px 14px',
                borderBottom: i < 5 ? '1px solid var(--border-glass)' : 'none',
              }}>
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div style={{ fontSize: 12, fontWeight: 500, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
                    {e.address || 'Unknown'}
                  </div>
                  <p style={{ fontSize: 10, color: 'var(--brand-muted)', marginTop: 1 }}>
                    {e.date?.slice(0, 7) || ''} \u00b7 {e.sqm || '?'} sqm
                  </p>
                </div>
                <div className="display" style={{ fontSize: 14, fontWeight: 600, color: 'var(--brand-green)', marginLeft: 8 }}>
                  {fmt(e.price)}
                </div>
              </div>
            ))}
          </div>
        ) : (
          <div className="glass" style={{ padding: '16px', textAlign: 'center', borderRadius: 14 }}>
            <p style={{ fontSize: 12, color: 'var(--brand-muted)' }}>No comparable sales data for this postcode.</p>
          </div>
        )}
      </div>

      {/* ── Professional Reports ────────────────────────── */}
      <div style={{ padding: '0 20px' }}>
        <p className="label" style={{ marginBottom: 2 }}>Professional Reports</p>
        <p style={{ fontSize: 11, color: 'var(--brand-muted)', marginBottom: 10, lineHeight: 1.5 }}>
          Generated instantly for this property. Each is a complete, actionable document.
        </p>
        {PRODUCTS.map((r) => (
          <div
            key={r.id}
            className="glass"
            style={{
              display: 'flex', alignItems: 'center', gap: 10, marginBottom: 8,
              padding: '10px 12px', borderRadius: 12, cursor: 'pointer',
            }}
            onClick={() => { window.Telegram?.WebApp?.HapticFeedback?.impactOccurred?.('light'); setSelected(r); }}
          >
            <div style={{
              width: 28, height: 28, borderRadius: 8,
              background: 'linear-gradient(135deg, var(--brand-green), #10b981)',
              color: '#0a0a0f',
              display: 'flex', alignItems: 'center', justifyContent: 'center',
              fontSize: 10, fontWeight: 700, flexShrink: 0,
            }}>
              R
            </div>
            <div style={{ flex: 1, minWidth: 0 }}>
              <div style={{ fontSize: 12, fontWeight: 500 }}>{r.title}</div>
              <p style={{ fontSize: 10, color: 'var(--brand-muted)', lineHeight: 1.4, marginTop: 1 }}>
                {r.desc}
              </p>
            </div>
            <div className="display" style={{
              fontSize: 13, fontWeight: 600, color: 'var(--brand-green)', flexShrink: 0,
              letterSpacing: '-0.02em',
            }}>
              {'\u00a3'}{r.price.toFixed(2)}
            </div>
          </div>
        ))}
      </div>

      {selected && (
        <ProductSheet
          product={selected}
          valuationContext={ctx}
          onClose={() => setSelected(null)}
          onComplete={() => setSelected(null)}
        />
      )}

      <div style={{ padding: '20px 20px', textAlign: 'center' }}>
        <div style={{ height: 1, background: 'var(--border-glass)', marginBottom: 10 }} />
        <p style={{ fontSize: 9, color: 'var(--brand-muted)' }}>
          HM Land Registry \u00b7 EPC Register \u00b7 ONS
        </p>
      </div>
    </div>
  );
}
