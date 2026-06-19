import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import ProductSheet from '../components/ProductSheet';
import { saveLastAvm, loadLastAvm, saveCreditBalance } from '../utils/tgStorage';

function formatPrice(n) {
  if (!n) return '\u2014';
  return '\u00a3' + Number(n).toLocaleString('en-GB');
}

const ADDITIONAL_REPORTS = [
  {
    id: 'lowball_counter_email',
    title: 'Counter-Offer Letter',
    subtitle: 'Data-backed negotiation email',
    price: 1.49,
    credits: 149,
  },
  {
    id: 'council_tax_challenger',
    title: 'Council Tax Audit',
    subtitle: 'Band comparison vs neighbours',
    price: 2.99,
    credits: 299,
  },
  {
    id: 'leasehold_trap_xray',
    title: 'Leasehold Assessment',
    subtitle: 'Section 42 extension cost analysis',
    price: 4.99,
    credits: 499,
  },
  {
    id: 'planning_permission_oracle',
    title: 'Permitted Development Check',
    subtitle: 'PD rules applicable to this property',
    price: 2.49,
    credits: 249,
  },
  {
    id: 'gentrification_radar',
    title: 'Area Growth Forecast',
    subtitle: '5-year price and sentiment projection',
    price: 2.99,
    credits: 299,
  },
  {
    id: 'syndicate_street_map',
    title: 'Ownership Intelligence',
    subtitle: 'LLC-held properties and equity analysis',
    price: 14.99,
    credits: 1499,
  },
];

export default function ReportPage() {
  const navigate = useNavigate();
  const [avmResult, setAvmResult] = useState(null);
  const [selectedReport, setSelectedReport] = useState(null);
  const [purchasedIds, setPurchasedIds] = useState(new Set());

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
      const raw = sessionStorage.getItem('honestly_purchased');
      if (raw) setPurchasedIds(new Set(JSON.parse(raw)));
    } catch {}
  }, []);

  const handlePurchaseComplete = (res, reportId) => {
    const updated = new Set(purchasedIds);
    updated.add(reportId);
    setPurchasedIds(updated);
    sessionStorage.setItem('honestly_purchased', JSON.stringify([...updated]));
    setSelectedReport(null);
  };

  if (!avmResult) {
    return (
      <div style={{ padding: '40px 16px', textAlign: 'center' }}>
        <div style={{ fontFamily: '"Fraunces", Georgia, serif', fontSize: 22, fontWeight: 600, margin: '0 0 8px', color: 'var(--brand-ink)' }}>
          No report yet
        </div>
        <p className="ui-text" style={{ fontSize: 14, color: 'var(--brand-muted)', margin: '0 0 20px' }}>
          Value a property first to generate the assessment.
        </p>
        <button
          onClick={() => navigate('/feed')}
          style={{
            padding: '14px 32px', borderRadius: 8,
            background: 'var(--brand-dark)', color: 'var(--brand-cream)',
            border: 'none', fontSize: 15, fontWeight: 600, cursor: 'pointer',
            fontFamily: '-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif',
          }}
        >
          New Valuation
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

  return (
    <div style={{ padding: '0 0 100px' }}>
      {/* ── Certificate Header ────────────────────────── */}
      <div style={{
        background: 'var(--brand-dark)',
        padding: '36px 20px 24px',
        textAlign: 'center',
      }}>
        <div className="brand-label" style={{ fontSize: 9, color: 'rgba(246,243,236,0.5)', letterSpacing: '0.22em', marginBottom: 2 }}>
          PROPERTY VALUATION CERTIFICATE
        </div>
        <div className="brand-hair" style={{ background: 'rgba(246,243,236,0.12)', margin: '8px auto', width: 40 }} />
        <p className="ui-text" style={{ fontSize: 13, color: 'rgba(246,243,236,0.6)', margin: '8px 0 4px' }}>
          {avm.address}
        </p>
        <h1 style={{
          fontFamily: '"Fraunces", Georgia, serif',
          fontSize: 42, fontWeight: 600,
          color: '#f6f3ec',
          margin: '4px 0', letterSpacing: '-0.03em',
        }}>
          {formatPrice(avm.central)}
        </h1>
        <p className="ui-text" style={{ fontSize: 13, color: 'rgba(246,243,236,0.5)', margin: '0 0 14px' }}>
          Valuation range: {formatPrice(avm.low)} \u2013 {formatPrice(avm.high)}
        </p>

        <div style={{ maxWidth: 240, margin: '0 auto' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            <div style={{ flex: 1, height: 4, background: 'rgba(246,243,236,0.15)', borderRadius: 2, overflow: 'hidden' }}>
              <div style={{ width: `${confidencePct}%`, height: '100%', background: gaugeColor, borderRadius: 2 }} />
            </div>
            <span className="ui-text" style={{ fontSize: 11, color: 'rgba(246,243,236,0.6)', minWidth: 32, textAlign: 'right' }}>
              {confidencePct}%
            </span>
          </div>
        </div>
        <p className="ui-text" style={{ fontSize: 11, color: 'rgba(246,243,236,0.45)', margin: '4px 0 0' }}>
          Confidence score
        </p>
      </div>

      {/* ── Property Details ──────────────────────────── */}
      <div style={{ display: 'flex', borderBottom: '1px solid var(--brand-line)' }}>
        {[
          { label: 'FLOOR AREA', value: avm.sqm ? `${avm.sqm} sqm` : '\u2014' },
          { label: 'EPC RATING', value: avm.epc || '\u2014' },
          { label: 'TYPE', value: (avm.type || '\u2014').toUpperCase() },
          { label: 'COMPS', value: avm.n_comps || '\u2014' },
        ].map((d, i) => (
          <div key={d.label} style={{
            flex: 1, padding: '12px 8px', textAlign: 'center',
            borderRight: i < 3 ? '1px solid var(--brand-line)' : 'none',
          }}>
            <div style={{ fontFamily: '"Fraunces", Georgia, serif', fontSize: 16, fontWeight: 600, color: 'var(--brand-ink)' }}>
              {d.value}
            </div>
            <div className="brand-label" style={{ fontSize: 8, color: 'var(--brand-muted)', letterSpacing: '0.15em', marginTop: 2 }}>
              {d.label}
            </div>
          </div>
        ))}
      </div>

      {/* ── Comparable Sales ──────────────────────────── */}
      {(avm.evidence || []).length > 0 && (
        <div style={{ padding: '16px' }}>
          <div className="brand-label" style={{ fontSize: 10, color: 'var(--brand-muted)', letterSpacing: '0.18em', marginBottom: 10 }}>
            COMPARABLE SALES EVIDENCE
          </div>
          <div style={{ border: '1px solid var(--brand-line)', borderRadius: 8, overflow: 'hidden' }}>
            {(avm.evidence || []).slice(0, 5).map((e, i) => (
              <div key={i} style={{
                display: 'flex', justifyContent: 'space-between', alignItems: 'center',
                padding: '10px 14px',
                background: i % 2 === 0 ? 'var(--brand-paper)' : 'transparent',
                borderBottom: i < 4 ? '1px solid var(--brand-line)' : 'none',
              }}>
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div className="ui-text" style={{ fontSize: 12, fontWeight: 500, color: 'var(--brand-ink)' }}>
                    {e.address || 'Unknown'}
                  </div>
                  <div className="ui-text" style={{ fontSize: 10, color: 'var(--brand-muted)', marginTop: 1 }}>
                    {e.date ? e.date.slice(0, 7) : ''} &middot; {e.sqm || '?'} sqm
                  </div>
                </div>
                <div style={{ fontFamily: '"Fraunces", Georgia, serif', fontSize: 15, fontWeight: 600, color: 'var(--brand-green)' }}>
                  {formatPrice(e.price)}
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* ── Additional Reports ────────────────────────── */}
      <div style={{ padding: '0 16px' }}>
        <div className="brand-hair" style={{ marginBottom: 14 }} />
        <div className="brand-label" style={{ fontSize: 10, color: 'var(--brand-muted)', letterSpacing: '0.18em', marginBottom: 10 }}>
          ADDITIONAL REPORTS
        </div>

        <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
          {ADDITIONAL_REPORTS.map((report) => {
            const purchased = purchasedIds.has(report.id);
            return (
              <div
                key={report.id}
                onClick={() => {
                  if (!purchased) {
                    window.Telegram?.WebApp?.HapticFeedback?.impactOccurred?.('light');
                    setSelectedReport(report);
                  }
                }}
                style={{
                  display: 'flex', alignItems: 'center', gap: 12,
                  padding: '12px 14px',
                  background: purchased ? 'rgba(21,128,127,0.04)' : 'var(--brand-paper)',
                  border: `1px solid ${purchased ? 'rgba(21,128,127,0.2)' : 'var(--brand-line)'}`,
                  borderRadius: 8,
                  cursor: purchased ? 'default' : 'pointer',
                  transition: 'all 0.15s ease',
                }}
              >
                <div style={{
                  width: 32, height: 32, borderRadius: 8,
                  background: purchased ? 'rgba(21,128,127,0.1)' : 'var(--brand-dark)',
                  display: 'flex', alignItems: 'center', justifyContent: 'center',
                  color: purchased ? 'var(--brand-green)' : 'var(--brand-cream)',
                  fontSize: 14, fontWeight: 600, flexShrink: 0,
                  fontFamily: '"Fraunces", Georgia, serif',
                }}>
                  {purchased ? '\u2713' : 'R'}
                </div>
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div className="ui-text" style={{ fontSize: 13, fontWeight: 500, color: purchased ? 'var(--brand-green)' : 'var(--brand-ink)' }}>
                    {report.title}
                    {purchased && <span className="brand-label" style={{ fontSize: 8, color: 'var(--brand-green)', marginLeft: 6, letterSpacing: '0.1em' }}>PURCHASED</span>}
                  </div>
                  <div className="ui-text" style={{ fontSize: 11, color: 'var(--brand-muted)', marginTop: 1 }}>
                    {report.subtitle}
                  </div>
                </div>
                <div style={{
                  fontFamily: '"Fraunces", Georgia, serif',
                  fontSize: 14, fontWeight: 600,
                  color: purchased ? 'var(--brand-green)' : 'var(--brand-ink)',
                  flexShrink: 0,
                }}>
                  {purchased ? '\u2714' : `\u00a3${report.price.toFixed(2)}`}
                </div>
              </div>
            );
          })}
        </div>
      </div>

      {/* ── Bottom sheet ──────────────────────────────── */}
      {selectedReport && (
        <ProductSheet
          product={selectedReport}
          valuationContext={valuationContext}
          onClose={() => setSelectedReport(null)}
          onComplete={(res) => handlePurchaseComplete(res, selectedReport.id)}
        />
      )}

      {/* ── Footer ────────────────────────────────────── */}
      <div className="brand-hair" style={{ margin: '24px 16px 8px' }} />
      <p className="brand-label" style={{ textAlign: 'center', color: 'var(--brand-muted)', fontSize: 9, letterSpacing: '0.18em', padding: '0 16px' }}>
        Honestly &middot; your property's price, proved
      </p>
    </div>
  );
}
