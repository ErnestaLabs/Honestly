import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import ProductSheet from '../components/ProductSheet';
import { loadLastAvm } from '../utils/tgStorage';

function fmt(n) {
  if (!n) return '\u2014';
  return '\u00a3' + Number(n).toLocaleString('en-GB');
}

const PRODUCTS = [
  {
    id: 'lowball_counter_email',
    title: 'Counter-Offer Letter',
    desc: 'A professionally worded, data-backed email for your estate agent, referencing your specific sold comparables. Ready to send.',
    price: 1.49,
  },
  {
    id: 'council_tax_challenger',
    title: 'Council Tax Challenge Letter',
    desc: 'A formal VOA challenge letter comparing your property\u2019s floor area and EPC against neighbouring bands. Print and post.',
    price: 2.99,
  },
  {
    id: 'leasehold_trap_xray',
    title: 'Leasehold Cost Report',
    desc: 'Your Section 42 extension cost estimate, ground rent escalation schedule, and mortgage lender risk timeline.',
    price: 4.99,
  },
  {
    id: 'planning_permission_oracle',
    title: 'Permitted Development Assessment',
    desc: 'A property-specific PD verdict: what you can build, volume limits, conservation area status, and roof analysis.',
    price: 2.49,
  },
  {
    id: 'gentrification_radar',
    title: 'Area Growth Report',
    desc: '5-year price forecast, local development pipeline, transport proposals, and amenity score for this postcode.',
    price: 2.99,
  },
  {
    id: 'syndicate_street_map',
    title: 'Ownership Intelligence Report',
    desc: 'LLC-held properties on your street, equity hoarders, and off-market acquisition targets. With mail-merge template.',
    price: 14.99,
  },
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
        <div style={{ fontFamily: '"Fraunces", Georgia, serif', fontSize: 22, fontWeight: 500, color: 'var(--brand-ink)', marginBottom: 8 }}>
          No valuation yet
        </div>
        <p className="ui-text" style={{ fontSize: 13, color: 'var(--brand-muted)', marginBottom: 24 }}>
          Run a free valuation first.
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
          Free Valuation Report
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

      {/* ALL comparables - free, full picture */}
      <div style={{ padding: '14px 20px', borderBottom: '1px solid var(--brand-line)' }}>
        <div className="ui-text" style={{ fontSize: 9, color: 'var(--brand-muted)', textTransform: 'uppercase', letterSpacing: '0.12em', marginBottom: 8 }}>
          Comparable sales evidence
        </div>
        {(a.evidence || []).length > 0 ? (
          (a.evidence || []).slice(0, 6).map((e, i) => (
            <div key={i} style={{
              display: 'flex', justifyContent: 'space-between', padding: '6px 0',
              borderTop: '1px solid var(--brand-line)',
            }}>
              <div style={{ flex: 1, minWidth: 0 }}>
                <div className="ui-text" style={{ fontSize: 11, fontWeight: 500, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
                  {e.address || 'Unknown'}
                </div>
                <div className="ui-text" style={{ fontSize: 9, color: 'var(--brand-muted)' }}>
                  {e.date?.slice(0, 7) || ''} \u00b7 {e.sqm || '?'} sqm
                </div>
              </div>
              <div style={{ fontFamily: '"Fraunces", Georgia, serif', fontSize: 14, fontWeight: 600, color: 'var(--brand-green)', marginLeft: 8 }}>
                {fmt(e.price)}
              </div>
            </div>
          ))
        ) : (
          <p className="ui-text" style={{ fontSize: 11, color: 'var(--brand-muted)', textAlign: 'center', padding: '12px 0' }}>
            No comparable sales data for this postcode.
          </p>
        )}
      </div>

      {/* Professional deliverables */}
      <div style={{ padding: '14px 20px' }}>
        <div className="ui-text" style={{ fontSize: 9, color: 'var(--brand-muted)', textTransform: 'uppercase', letterSpacing: '0.12em', marginBottom: 2 }}>
          Professional reports
        </div>
        <p className="ui-text" style={{ fontSize: 10, color: 'var(--brand-muted)', marginBottom: 10, lineHeight: 1.5 }}>
          Generated instantly for this property. Each is a complete, actionable document.
        </p>
        {PRODUCTS.map((r) => (
          <div
            key={r.id}
            onClick={() => { window.Telegram?.WebApp?.HapticFeedback?.impactOccurred?.('light'); setSelected(r); }}
            style={{
              display: 'flex', gap: 10, padding: '10px 0',
              borderBottom: '1px solid var(--brand-line)',
              cursor: 'pointer', alignItems: 'center',
            }}
          >
            <div style={{
              width: 28, height: 28, borderRadius: 4,
              background: 'var(--brand-dark)', color: 'var(--brand-cream)',
              display: 'flex', alignItems: 'center', justifyContent: 'center',
              fontSize: 10, fontWeight: 600, flexShrink: 0,
              fontFamily: '"Fraunces", Georgia, serif',
            }}>
              R
            </div>
            <div style={{ flex: 1, minWidth: 0 }}>
              <div className="ui-text" style={{ fontSize: 11, fontWeight: 500, color: 'var(--brand-ink)' }}>
                {r.title}
              </div>
              <div className="ui-text" style={{ fontSize: 9, color: 'var(--brand-muted)', lineHeight: 1.4, marginTop: 1 }}>
                {r.desc}
              </div>
            </div>
            <div style={{
              fontFamily: '"Fraunces", Georgia, serif', fontSize: 13, fontWeight: 600,
              color: 'var(--brand-ink)', flexShrink: 0,
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

      <div style={{ padding: '8px 20px' }}>
        <div style={{ height: 1, background: 'var(--brand-line)', marginBottom: 8 }} />
        <p className="ui-text" style={{ fontSize: 8, color: 'var(--brand-muted)', textAlign: 'center' }}>
          HM Land Registry \u00b7 EPC Register \u00b7 ONS
        </p>
      </div>
    </div>
  );
}
