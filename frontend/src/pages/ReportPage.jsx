import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import ProductSheet from '../components/ProductSheet';
import { saveLastAvm, loadLastAvm } from '../utils/tgStorage';

function formatPrice(n) {
  if (!n) return '\u2014';
  return '\u00a3' + Number(n).toLocaleString('en-GB');
}

const PREMIUM_REPORTS = [
  { id: 'lowball_counter_email', title: 'Counter-Offer Letter', subtitle: 'Data-backed negotiation email for your estate agent', price: 1.49 },
  { id: 'council_tax_challenger', title: 'Council Tax Audit', subtitle: 'Band comparison against neighbouring properties', price: 2.99 },
  { id: 'leasehold_trap_xray', title: 'Leasehold Assessment', subtitle: 'Section 42 extension cost and ground rent analysis', price: 4.99 },
  { id: 'planning_permission_oracle', title: 'Permitted Development Check', subtitle: 'Assess what works you can do without planning permission', price: 2.49 },
  { id: 'gentrification_radar', title: 'Area Growth Forecast', subtitle: '5-year price trends and local development signals', price: 2.99 },
  { id: 'syndicate_street_map', title: 'Ownership Intelligence', subtitle: 'LLC-held properties and long-term equity analysis', price: 14.99 },
];

export default function ReportPage() {
  const navigate = useNavigate();
  const [avmResult, setAvmResult] = useState(null);
  const [selectedReport, setSelectedReport] = useState(null);

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
        <div style={{ fontFamily: '"Fraunces", Georgia, serif', fontSize: 22, fontWeight: 500, color: 'var(--brand-ink)' }}>
          No valuation yet
        </div>
        <p className="ui-text" style={{ fontSize: 14, color: 'var(--brand-muted)', marginTop: 8, marginBottom: 24 }}>
          Enter a property address to generate your free report.
        </p>
        <button onClick={() => navigate('/')} className="purchase-button" style={{ width: 'auto', padding: '14px 32px' }}>
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

  const today = new Date().toLocaleDateString('en-GB', { day: 'numeric', month: 'long', year: 'numeric' });

  return (
    <div style={{ padding: '0 0 80px' }}>
      {/* ── Report header ─────────────────────────────── */}
      <div style={{ background: 'var(--brand-dark)', padding: '36px 24px 28px' }}>
        <div className="ui-text" style={{
          fontSize: 10, color: 'rgba(246,243,236,0.4)',
          textTransform: 'uppercase', letterSpacing: '0.2em', marginBottom: 2,
        }}>
          Valuation Report
        </div>
        <div className="ui-text" style={{ fontSize: 10, color: 'rgba(246,243,236,0.3)', marginBottom: 14 }}>
          {today}
        </div>

        <p className="ui-text" style={{ fontSize: 13, color: 'rgba(246,243,236,0.55)', marginBottom: 4 }}>
          {avm.address}
        </p>
        <h1 style={{
          fontFamily: '"Fraunces", Georgia, serif',
          fontWeight: 600, fontSize: 40,
          color: '#f6f3ec', margin: '0 0 2px',
          letterSpacing: '-0.03em',
        }}>
          {formatPrice(avm.central)}
        </h1>
        <p className="ui-text" style={{ fontSize: 12, color: 'rgba(246,243,236,0.4)' }}>
          Range: {formatPrice(avm.low)} &ndash; {formatPrice(avm.high)}
        </p>
      </div>

      {/* ── Confidence + Details ──────────────────────── */}
      <div style={{ padding: '16px 20px', borderBottom: '1px solid var(--brand-line)' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 10 }}>
          <div style={{ flex: 1, height: 4, background: 'var(--brand-line)', borderRadius: 2, overflow: 'hidden' }}>
            <div style={{ width: `${confidencePct}%`, height: '100%', background: gaugeColor, borderRadius: 2 }} />
          </div>
          <span className="ui-text" style={{ fontSize: 12, fontWeight: 500, color: 'var(--brand-ink)', minWidth: 44, textAlign: 'right' }}>
            {confidencePct}%
          </span>
        </div>

        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '4px 20px' }}>
          {[
            ['Floor area', avm.sqm ? `${avm.sqm} sqm` : '\u2014'],
            ['EPC rating', avm.epc || '\u2014'],
            ['Property type', (avm.type || '\u2014').replace(/_/g, ' ')],
            ['Comparables', avm.n_comps ? `${avm.n_comps} sold` : '\u2014'],
          ].map(([l, v]) => (
            <div key={l} style={{ display: 'flex', justifyContent: 'space-between', padding: '4px 0' }}>
              <span className="ui-text" style={{ fontSize: 12, color: 'var(--brand-muted)' }}>{l}</span>
              <span className="ui-text" style={{ fontSize: 12, fontWeight: 500, color: 'var(--brand-ink)' }}>{v}</span>
            </div>
          ))}
        </div>
      </div>

      {/* ── Comparable Sales ──────────────────────────── */}
      {(avm.evidence || []).length > 0 && (
        <div style={{ padding: '16px 20px', borderBottom: '1px solid var(--brand-line)' }}>
          <div className="ui-text" style={{
            fontSize: 10, color: 'var(--brand-muted)', textTransform: 'uppercase',
            letterSpacing: '0.12em', marginBottom: 10,
          }}>
            Comparable Sales
          </div>
          {(avm.evidence || []).slice(0, 5).map((e, i) => (
            <div key={i} style={{
              display: 'flex', justifyContent: 'space-between', padding: '8px 0',
              borderTop: '1px solid var(--brand-line)',
            }}>
              <div>
                <div className="ui-text" style={{ fontSize: 12, fontWeight: 500 }}>{e.address}</div>
                <div className="ui-text" style={{ fontSize: 10, color: 'var(--brand-muted)' }}>
                  {e.date?.slice(0, 7)} &middot; {e.sqm || '?'} sqm
                </div>
              </div>
              <div style={{ fontFamily: '"Fraunces", Georgia, serif', fontSize: 15, fontWeight: 600, color: 'var(--brand-green)' }}>
                {formatPrice(e.price)}
              </div>
            </div>
          ))}
        </div>
      )}

      {/* ── Premium Reports ───────────────────────────── */}
      <div style={{ padding: '16px 20px' }}>
        <div className="ui-text" style={{
          fontSize: 10, color: 'var(--brand-muted)', textTransform: 'uppercase',
          letterSpacing: '0.12em', marginBottom: 2,
        }}>
          Premium Reports
        </div>
        <p className="ui-text" style={{ fontSize: 11, color: 'var(--brand-muted)', marginBottom: 12 }}>
          Additional data reports for this property. Delivered instantly.
        </p>

        {PREMIUM_REPORTS.map((r) => (
          <div
            key={r.id}
            onClick={() => {
              window.Telegram?.WebApp?.HapticFeedback?.impactOccurred?.('light');
              setSelectedReport(r);
            }}
            style={{
              display: 'flex', alignItems: 'center', gap: 10,
              padding: '10px 0',
              borderBottom: '1px solid var(--brand-line)',
              cursor: 'pointer',
            }}
          >
            <div style={{
              width: 28, height: 28, borderRadius: 6,
              background: 'var(--brand-dark)', color: 'var(--brand-cream)',
              display: 'flex', alignItems: 'center', justifyContent: 'center',
              fontSize: 11, fontWeight: 600,
              fontFamily: '"Fraunces", Georgia, serif', flexShrink: 0,
            }}>
              R
            </div>
            <div style={{ flex: 1 }}>
              <div className="ui-text" style={{ fontSize: 12, fontWeight: 500, color: 'var(--brand-ink)' }}>
                {r.title}
              </div>
              <div className="ui-text" style={{ fontSize: 10, color: 'var(--brand-muted)', marginTop: 1 }}>
                {r.subtitle}
              </div>
            </div>
            <div style={{
              fontFamily: '"Fraunces", Georgia, serif',
              fontSize: 14, fontWeight: 600, color: 'var(--brand-ink)', flexShrink: 0,
            }}>
              {'\u00a3'}{r.price.toFixed(2)}
            </div>
          </div>
        ))}
      </div>

      {selectedReport && (
        <ProductSheet
          product={selectedReport}
          valuationContext={valuationContext}
          onClose={() => setSelectedReport(null)}
          onComplete={() => setSelectedReport(null)}
        />
      )}

      <div style={{ padding: '16px 20px' }}>
        <div style={{ height: 1, background: 'var(--brand-line)', marginBottom: 10 }} />
        <p className="ui-text" style={{ fontSize: 10, color: 'var(--brand-muted)', lineHeight: 1.6, textAlign: 'center' }}>
          Data sourced from HM Land Registry Price Paid Data and EPC Register.
        </p>
      </div>
    </div>
  );
}
