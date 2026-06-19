export default function ConfidenceGauge({ score, label }) {
  const pct = Math.min(100, Math.max(0, score || 0));
  let color;
  if (pct >= 80) color = '#15807f';
  else if (pct >= 60) color = '#2aa39a';
  else if (pct >= 40) color = '#d89a32';
  else color = '#c73a3a';

  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
      <div className="gauge-track" style={{ flex: 1 }}>
        <div className="gauge-fill" style={{ width: `${pct}%`, background: color }} />
      </div>
      <span className="ui-text" style={{
        fontSize: 12, fontWeight: 600, color, minWidth: 36, textAlign: 'right',
        fontFamily: '"Fraunces", Georgia, serif',
      }}>
        {pct}%
      </span>
    </div>
  );
}
