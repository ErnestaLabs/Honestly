import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import ProductSheet from '../components/ProductSheet';
import { saveLastAvm, loadLastAvm } from '../utils/tgStorage';

function formatPrice(n) {
  if (!n) return '\u2014';
  return '\u00a3' + Number(n).toLocaleString('en-GB');
}

export default function ReportPage() {
  const navigate = useNavigate();
  const [avmResult, setAvmResult] = useState(null);
  const [selectedService, setSelectedService] = useState(null);

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
      <div style={{ padding: '48px 16px', textAlign: 'center' }}>
        <div style={{ fontFamily: '"Fraunces", Georgia, serif', fontSize: 22, fontWeight: 600, color: 'var(--brand-ink)', marginBottom: 8 }}>
          No valuation yet
        </div>
        <p className="ui-text" style={{ fontSize: 14, color: 'var(--brand-muted)', marginBottom: 24 }}>
          Enter a property address to generate a free valuation report.
        </p>
        <button onClick={() => navigate('/')} className="purchase-button" style={{ width: 'auto', padding: '14px 32px' }}>
          Value a Property
        </button>
      </div>
    );
  }

  const avm = avmResult.avm || {};
  const confidencePct = Math.min(100, Math.max(0, avm.confidence_score || 0));

  const gaugeColor = confidencePct >= 80 ? '#15807f'
    : confidencePct >= 60 ? '#2aa39a'
    : confidencePct >= 40 ? '#d89a32'
    : '#c73a3a';

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

  const today = new Date().toLocaleDateString('en-GB', {
    day: 'numeric', month: 'long', year: 'numeric',
  });

  return (
    <div style={{ padding: '0 0 80px' }}>
      {/* ── Document header ───────────────────────────── */}
      <div style={{ background: 'var(--brand-dark)', padding: '32px 20px 24px' }}>
        <div className="ui-text" style={{
          fontSize: 10, color: 'rgba(246,243,236,0.4)',
          textTransform: 'uppercase', letterSpacing: '0.22em',
          marginBottom: 4,
        }}>
          Valuation Report &middot; {today}
        </div>
        <div style={{ width: 28, height: 2, background: 'rgba(246,243,236,0.2)', marginBottom: 12 }} />

        <p className="ui-text" style={{ fontSize: 13, color: 'rgba(246,243,236,0.6)', margin: '0 0 2px' }}>
          {avm.address}
        </p>
        <h1 style={{
          fontFamily: '"Fraunces", Georgia, serif',
          fontSize: 40, fontWeight: 600,
          color: '#f6f3ec', margin: '0 0 2px',
          letterSpacing: '-0.03em',
        }}>
          {formatPrice(avm.central)}
        </h1>
        <p className="ui-text" style={{ fontSize: 12, color: 'rgba(246,243,236,0.4)', margin: 0 }}>
          Estimated range: {formatPrice(avm.low)} &ndash; {formatPrice(avm.high)}
        </p>
      </div>

      {/* ── Confidence ────────────────────────────────── */}
      <div style={{ padding: '14px 20px', borderBottom: '1px solid var(--brand-line)' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
          <div style={{ flex: 1 }}>
            <div style={{ height: 4, background: 'var(--brand-line)', borderRadius: 2, overflow: 'hidden' }}>
              <div style={{ width: `${confidencePct}%`, height: '100%', background: gaugeColor, borderRadius: 2 }} />
            </div>
          </div>
          <div className="ui-text" style={{ fontSize: 12, fontWeight: 500, color: 'var(--brand-ink)', minWidth: 50, textAlign: 'right' }}>
            {confidencePct}% confidence
          </div>
        </div>
        <div className="ui-text" style={{ fontSize: 11, color: 'var(--brand-muted)', marginTop: 4 }}>
          Based on {avm.n_comps || 0} comparable sales within 0.5 miles
        </div>
      </div>

      {/* ── Property details ──────────────────────────── */}
      <div style={{ padding: '14px 20px', borderBottom: '1px solid var(--brand-line)' }}>
        <div className="brand-label" style={{ fontSize: 9, marginBottom: 8 }}>
          PROPERTY DETAILS
        </div>
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '6px 20px' }}>
          {[
            ['Floor area', avm.sqm ? `${avm.sqm} sqm` : '\u2014'],
            ['EPC rating', avm.epc || '\u2014'],
            ['Type', (avm.type || '\u2014').replace(/_/g, ' ')],
            ['Last sold', avm.last_sold ? formatPrice(avm.last_sold) : '\u2014'],
          ].map(([label, value]) => (
            <div key={label} style={{ display: 'flex', justifyContent: 'space-between', padding: '3px 0' }}>
              <span className="ui-text" style={{ fontSize: 12, color: 'var(--brand-muted)' }}>{label}</span>
              <span className="ui-text" style={{ fontSize: 12, fontWeight: 500, color: 'var(--brand-ink)' }}>{value}</span>
            </div>
          ))}
        </div>
      </div>

      {/* ── Comparable sales ──────────────────────────── */}
      <div style={{ padding: '14px 20px', borderBottom: '1px solid var(--brand-line)' }}>
        <div className="brand-label" style={{ fontSize: 9, marginBottom: 8 }}>
          COMPARABLE SALES
        </div>
        {(avm.evidence || []).slice(0, 5).map((e, i) => (
          <div key={i} style={{
            display: 'flex', justifyContent: 'space-between', alignItems: 'center',
            padding: '7px 0',
            borderTop: i === 0 ? '1px solid var(--brand-line)' : 'none',
            borderBottom: '1px solid var(--brand-line)',
          }}>
            <div style={{ flex: 1 }}>
              <div className="ui-text" style={{ fontSize: 12, fontWeight: 500 }}>{e.address || 'Unknown'}</div>
              <div className="ui-text" style={{ fontSize: 10, color: 'var(--brand-muted)' }}>
                {e.date ? e.date.slice(0, 7) : ''} &middot; {e.sqm || '?'} sqm
              </div>
            </div>
            <div style={{ fontFamily: '"Fraunces", Georgia, serif', fontSize: 15, fontWeight: 600, color: 'var(--brand-green)' }}>
              {formatPrice(e.price)}
            </div>
          </div>
        ))}
        {(!avm.evidence || avm.evidence.length === 0) && (
          <p className="ui-text" style={{ fontSize: 12, color: 'var(--brand-muted)', textAlign: 'center', padding: '16px 0' }}>
            No comparable sales data available for this postcode.
          </p>
        )}
      </div>

      {/* ── Professional Services ─────────────────────── */}
      <div style={{ padding: '16px 20px' }}>
        <div className="brand-label" style={{ fontSize: 9, marginBottom: 8 }}>
          PROFESSIONAL SERVICES
        </div>
        <p className="ui-text" style={{ fontSize: 12, color: 'var(--brand-muted)', marginBottom: 12, lineHeight: 1.5 }}>
          Order additional reports and tools for this property. Delivered instantly.
        </p>

        <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
          {[
            {
              id: 'lowball_counter_email',
              name: 'Counter-Offer Letter',
              desc: 'Professional email to your estate agent with sold evidence',
              price: '\u00a31.49',
            },
            {
              id: 'council_tax_challenger',
              name: 'Council Tax Audit',
              desc: 'Compares your banding to neighbouring properties',
              price: '\u00a32.99',
            },
            {
              id: 'leasehold_trap_xray',
              name: 'Leasehold Assessment',
              desc: 'Section 42 extension cost and ground rent risk analysis',
              price: '\u00a34.99',
            },
            {
              id: 'planning_permission_oracle',
              name: 'Permitted Development Check',
              desc: 'Assess whether your planned works need planning permission',
              price: '\u00a32.49',
            },
          ].map((svc) => (
            <div
              key={svc.id}
              onClick={() => {
                window.Telegram?.WebApp?.HapticFeedback?.impactOccurred?.('light');
                setSelectedService({ ...svc, credits: Math.round(parseFloat(svc.price.replace('\u00a3', '')) * 100), gbp: parseFloat(svc.price.replace('\u00a3', '')) });
              }}
              style={{
                display: 'flex', alignItems: 'center', gap: 10,
                padding: '10px 12px',
                border: '1px solid var(--brand-line)',
                borderRadius: 6,
                cursor: 'pointer',
                background: 'var(--brand-paper)',
              }}
            >
              <div style={{
                width: 28, height: 28, borderRadius: 6,
                background: 'var(--brand-dark)', color: 'var(--brand-cream)',
                display: 'flex', alignItems: 'center', justifyContent: 'center',
                fontSize: 11, fontWeight: 600, flexShrink: 0,
                fontFamily: '"Fraunces", Georgia, serif',
              }}>
                R
              </div>
              <div style={{ flex: 1 }}>
                <div className="ui-text" style={{ fontSize: 12, fontWeight: 500 }}>{svc.name}</div>
                <div className="ui-text" style={{ fontSize: 10, color: 'var(--brand-muted)', marginTop: 1 }}>{svc.desc}</div>
              </div>
              <div style={{
                fontFamily: '"Fraunces", Georgia, serif',
                fontSize: 14, fontWeight: 600, color: 'var(--brand-ink)', flexShrink: 0,
              }}>
                {svc.price}
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* ── Bottom sheet ──────────────────────────────── */}
      {selectedService && (
        <ProductSheet
          product={selectedService}
          valuationContext={valuationContext}
          onClose={() => setSelectedService(null)}
          onComplete={() => setSelectedService(null)}
        />
      )}

      {/* ── Footer ────────────────────────────────────── */}
      <div style={{ padding: '16px 20px' }}>
        <div style={{ height: 1, background: 'var(--brand-line)', marginBottom: 10 }} />
        <p className="ui-text" style={{ fontSize: 10, color: 'var(--brand-muted)', lineHeight: 1.6, textAlign: 'center' }}>
          Data sourced from HM Land Registry Price Paid Data and EPC Register.
          This is an automated valuation, not a formal survey.
        </p>
      </div>
    </div>
  );
}
