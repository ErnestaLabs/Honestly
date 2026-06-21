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
  { id: 'gentrification_radar', title: 'Area Growth Report', desc: '5-year price forecast, development pipeline, and amenity score.', price: 2.99 },
  { id: 'syndicate_street_map', title: 'Ownership Report', desc: 'LLC-held properties and off-market targets with mail-merge template.', price: 14.99 },
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
      <div style={{ padding: '48px 20px', textAlign: 'center', background: 'var(--bg-muted)', minHeight: '100vh' }}>
        <div className="card" style={{ padding: '32px 20px' }}>
          <p className="section-label" style={{ marginBottom: 8 }}>No valuation yet</p>
          <p style={{ fontSize: 14, color: 'var(--text-secondary)', marginBottom: 20 }}>
            Run a free valuation first.
          </p>
          <button onClick={() => navigate('/')} className="btn-primary">
            Value a Property
          </button>
        </div>
      </div>
    );
  }

  const a = data.avm || {};
  const cp = Math.min(100, Math.max(0, a.confidence_score || 0));
  const gc = cp >= 80 ? '#15807f' : cp >= 60 ? '#2aa39a' : cp >= 40 ? '#d97706' : '#dc2626';
  const ctx = {
    address: a.address, postcode: a.postcode, central: a.central,
    low: a.low, high: a.high, confidence_score: a.confidence_score,
    confidence_grade: a.confidence_grade, sqm: a.sqm, epc: a.epc,
    type: a.type, evidence: a.evidence,
  };

  return (
    <div style={{ background: 'var(--bg-muted)', minHeight: '100vh', paddingBottom: 80 }}>
      {/* ── Header Card ────────────────────────────────── */}
      <div style={{ padding: '20px 16px 12px' }}>
        <div className="card" style={{ padding: '20px', textAlign: 'center' }}>
          <p className="section-label" style={{ marginBottom: 2 }}>Free Valuation Report</p>
          <p style={{ fontSize: 12, color: 'var(--text-tertiary)', marginBottom: 14 }}>
            {new Date().toLocaleDateString('en-GB', { day: 'numeric', month: 'short', year: 'numeric' })}
          </p>
          <p style={{ fontSize: 13, color: 'var(--text-secondary)', marginBottom: 4 }}>
            {a.address}
          </p>
          <h1 className="display" style={{
            fontWeight: 600, fontSize: 36,
            color: 'var(--brand)', letterSpacing: '-0.03em', lineHeight: 1,
            margin: '0 0 4px',
          }}>
            {fmt(a.central)}
          </h1>
          <p style={{ fontSize: 13, color: 'var(--text-secondary)', marginBottom: 14 }}>
            {fmt(a.low)} \u2013 {fmt(a.high)}
          </p>
          <div className="gauge-track" style={{ maxWidth: 200, margin: '0 auto' }}>
            <div className="gauge-fill" style={{ width: `${cp}%`, background: gc }} />
          </div>
          <p style={{ fontSize: 11, color: 'var(--text-tertiary)', marginTop: 4 }}>{cp}% confidence</p>
        </div>
      </div>

      {/* ── Stats Row ──────────────────────────────────── */}
      <div style={{ padding: '0 16px 12px', display: 'flex', gap: 8 }}>
        {[
          ['SQM', a.sqm || '\u2014'],
          ['EPC', a.epc || '\u2014'],
          ['TYPE', (a.type || '\u2014').slice(0, 4).toUpperCase()],
          ['COMPS', a.n_comps || '\u2014'],
        ].map(([l, v]) => (
          <div key={l} className="stat-card" style={{ flex: 1 }}>
            <div className="display" style={{ fontSize: 15, fontWeight: 600, color: 'var(--text-primary)' }}>{v}</div>
            <p style={{ fontSize: 10, color: 'var(--text-tertiary)', marginTop: 2 }}>{l}</p>
          </div>
        ))}
      </div>

      {/* ── Comparables ────────────────────────────────── */}
      <div style={{ padding: '0 16px 12px' }}>
        <p className="section-label">Comparable sales</p>
        {(a.evidence || []).length > 0 ? (
          <div className="card" style={{ overflow: 'hidden', padding: 0 }}>
            {(a.evidence || []).slice(0, 6).map((e, i) => (
              <div key={i} style={{
                display: 'flex', justifyContent: 'space-between', padding: '10px 14px',
                borderBottom: i < 5 ? '1px solid var(--border-light)' : 'none',
              }}>
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div style={{ fontSize: 12, fontWeight: 500, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
                    {e.address || 'Unknown'}
                  </div>
                  <p style={{ fontSize: 10, color: 'var(--text-tertiary)', marginTop: 1 }}>
                    {e.date?.slice(0, 7) || ''} \u00b7 {e.sqm || '?'} sqm
                  </p>
                </div>
                <div className="display" style={{ fontSize: 14, fontWeight: 600, color: 'var(--brand)', marginLeft: 8 }}>
                  {fmt(e.price)}
                </div>
              </div>
            ))}
          </div>
        ) : (
          <div className="card" style={{ padding: '16px', textAlign: 'center' }}>
            <p style={{ fontSize: 13, color: 'var(--text-secondary)' }}>No comparable sales data for this postcode.</p>
          </div>
        )}
      </div>

      {/* ── Professional Reports ────────────────────────── */}
      <div style={{ padding: '0 16px' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 8 }}>
          <p className="section-label" style={{ margin: 0 }}>Professional reports</p>
        </div>
        <p style={{ fontSize: 12, color: 'var(--text-secondary)', marginBottom: 10, lineHeight: 1.4 }}>
          Generated instantly for this property. Each is a complete, actionable document.
        </p>
        {PRODUCTS.map((r) => (
          <div
            key={r.id}
            className="card"
            style={{
              display: 'flex', alignItems: 'center', gap: 10, marginBottom: 8,
              padding: '10px 12px', cursor: 'pointer',
            }}
            onClick={() => { window.Telegram?.WebApp?.HapticFeedback?.impactOccurred?.('light'); setSelected(r); }}
          >
            <div style={{
              width: 28, height: 28, borderRadius: 7,
              background: 'var(--brand-light)', color: 'var(--brand)',
              display: 'flex', alignItems: 'center', justifyContent: 'center',
              fontSize: 10, fontWeight: 700, flexShrink: 0,
            }}>
              R
            </div>
            <div style={{ flex: 1, minWidth: 0 }}>
              <div style={{ fontSize: 12, fontWeight: 600, color: 'var(--text-primary)' }}>{r.title}</div>
              <p style={{ fontSize: 10, color: 'var(--text-secondary)', lineHeight: 1.4, marginTop: 1 }}>
                {r.desc}
              </p>
            </div>
            <div className="display" style={{
              fontSize: 13, fontWeight: 600, color: 'var(--brand)', flexShrink: 0,
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

      <div style={{ padding: '20px 16px', textAlign: 'center' }}>
        <p style={{ fontSize: 10, color: 'var(--text-tertiary)' }}>
          HM Land Registry \u00b7 EPC Register \u00b7 ONS
        </p>
      </div>
    </div>
  );
}
