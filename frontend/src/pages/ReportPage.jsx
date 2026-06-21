import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import ProductSheet from '../components/ProductSheet';
import { loadLastAvm } from '../utils/tgStorage';

function fmt(n) {
  if (!n) return '\u2014';
  return '\u00a3' + Number(n).toLocaleString('en-GB');
}

const PRODUCTS = [
  { id: 'lowball_counter_email', title: 'Are They Taking The Piss?', desc: 'Counter-offer email', price: 1.49 },
  { id: 'council_tax_challenger', title: 'Council Tax Challenge', desc: 'Band comparison letter', price: 2.99 },
  { id: 'leasehold_trap_xray', title: 'Leasehold Cost Report', desc: 'Section 42 extension estimate', price: 4.99 },
  { id: 'planning_permission_oracle', title: 'Development Check', desc: 'PD rules for this property', price: 2.49 },
  { id: 'gentrification_radar', title: 'Area Growth Report', desc: '5-year forecast', price: 2.99 },
  { id: 'syndicate_street_map', title: 'Ownership Report', desc: 'LLC map + mail-merge', price: 14.99 },
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
      <div style={{ minHeight: '100vh', background: '#f8fafb', padding: '48px 16px', textAlign: 'center' }}>
        <div className="card-premium" style={{ maxWidth: 448, margin: '0 auto' }}>
          <span className="label-upper">No valuation yet</span>
          <p style={{ fontSize: 14, color: '#64748b', marginTop: 12, marginBottom: 20 }}>
            Run a free valuation first.
          </p>
          <button onClick={() => navigate('/')} className="btn-primary" style={{ padding: '12px 28px', fontSize: 14 }}>
            Value a Property
          </button>
        </div>
      </div>
    );
  }

  const a = data.avm || {};
  const cp = Math.min(100, Math.max(0, a.confidence_score || 0));
  const gaugeColor = cp >= 80 ? '#15807f' : cp >= 60 ? '#2aa39a' : cp >= 40 ? '#fbbf24' : '#ef4444';
  const gradeText = cp >= 80 ? 'Strong' : cp >= 60 ? 'Good' : cp >= 40 ? 'Fair' : 'Low';
  const ctx = {
    address: a.address, postcode: a.postcode, central: a.central,
    low: a.low, high: a.high, confidence_score: a.confidence_score,
    confidence_grade: a.confidence_grade, sqm: a.sqm, epc: a.epc,
    type: a.type, evidence: a.evidence,
  };

  return (
    <div style={{ minHeight: '100vh', background: '#f8fafb', paddingBottom: 80 }}>
      <div style={{ maxWidth: 448, margin: '0 auto', padding: '24px 16px' }}>

        {/* ── The Premium AVM Card ────────────────────── */}
        <div className="card-premium">
          {/* Address & Context */}
          <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', textAlign: 'center' }}>
            <span className="label-upper">Assessed Market Value</span>
            <h1 style={{ marginTop: 12, fontSize: 14, fontWeight: 500, color: '#64748b' }}>
              {a.address}
            </h1>
            <p style={{ marginTop: 16, fontSize: 60, fontWeight: 700, letterSpacing: '-0.05em', color: '#0f172a' }}>
              {fmt(a.central)}
            </p>
            <p style={{ marginTop: 8, fontSize: 14, fontWeight: 500, color: '#94a3b8' }}>
              {fmt(a.low)} \u2013 {fmt(a.high)}
            </p>
          </div>

          {/* Confidence Gauge */}
          <div style={{ marginTop: 32 }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 8 }}>
              <span className="label-upper">Confidence</span>
              <span style={{ fontSize: 12, fontWeight: 700, color: '#334155' }}>
                {gradeText} ({cp}/100)
              </span>
            </div>
            <div className="gauge-track">
              <div className="gauge-fill" style={{ width: `${cp}%`, background: gaugeColor }} />
            </div>
          </div>

          {/* Separator */}
          <div style={{ margin: '32px 0', height: 1, width: '100%', background: '#f1f5f9' }} />

          {/* Comparable Sales */}
          <div style={{ marginBottom: 16 }}>
            <span className="label-upper" style={{ marginBottom: 12, display: 'block' }}>Comparable Sales</span>
            {(a.evidence || []).length > 0 ? (
              (a.evidence || []).slice(0, 6).map((e, i) => (
                <div key={i} style={{
                  display: 'flex', justifyContent: 'space-between', padding: '8px 0',
                  borderTop: '1px solid #f1f5f9',
                }}>
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <div style={{ fontSize: 13, fontWeight: 500, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
                      {e.address || 'Unknown'}
                    </div>
                    <p style={{ fontSize: 11, color: '#94a3b8', marginTop: 1 }}>
                      {e.date?.slice(0, 7) || ''} \u00b7 {e.sqm || '?'} sqm
                    </p>
                  </div>
                  <div className="display" style={{ fontSize: 14, fontWeight: 600, color: '#0f172a', marginLeft: 8 }}>
                    {fmt(e.price)}
                  </div>
                </div>
              ))
            ) : (
              <p style={{ fontSize: 13, color: '#94a3b8', textAlign: 'center', padding: '12px 0' }}>
                No comparable sales data
              </p>
            )}
          </div>

          {/* Separator */}
          <div style={{ margin: '16px 0', height: 1, width: '100%', background: '#f1f5f9' }} />

          {/* Locked Upsells */}
          <div className="label-upper" style={{ marginBottom: 12 }}>Professional Reports</div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
            {PRODUCTS.map((r) => (
              <div
                key={r.id}
                className="upsell-row"
                onClick={() => { window.Telegram?.WebApp?.HapticFeedback?.impactOccurred?.('light'); setSelected(r); }}
              >
                <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                  <span style={{ fontSize: 18 }}>{['😡','😡','😰','😴','💰','💰'][PRODUCTS.indexOf(r)]}</span>
                  <div>
                    <p style={{ fontSize: 13, fontWeight: 600, color: '#1e293b' }}>{r.title}</p>
                    <p style={{ fontSize: 11, color: '#94a3b8' }}>{r.desc}</p>
                  </div>
                </div>
                <button
                  className="btn-primary"
                  onClick={(e) => { e.stopPropagation(); window.Telegram?.WebApp?.HapticFeedback?.impactOccurred?.('light'); setSelected(r); }}
                >
                  {'\u00a3'}{r.price.toFixed(2)}
                </button>
              </div>
            ))}
          </div>
        </div>

      </div>

      {selected && (
        <ProductSheet
          product={selected}
          valuationContext={ctx}
          onClose={() => setSelected(null)}
          onComplete={() => setSelected(null)}
        />
      )}

      <div style={{ padding: '24px 16px', textAlign: 'center' }}>
        <p style={{ fontSize: 10, color: '#94a3b8' }}>
          HM Land Registry \u00b7 EPC Register \u00b7 ONS
        </p>
      </div>
    </div>
  );
}
