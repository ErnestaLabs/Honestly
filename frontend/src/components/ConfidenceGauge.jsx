export default function ConfidenceGauge({ score, label }) {
  const pct = Math.min(100, Math.max(0, score || 0));
  let color;
  if (pct >= 80) color = '#30d158';
  else if (pct >= 60) color = '#64d2ff';
  else if (pct >= 40) color = '#ff9f0a';
  else color = '#ff453a';

  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
      <div className="gauge-track" style={{ flex: 1 }}>
        <div
          className="gauge-fill"
          style={{ width: `${pct}%`, background: color }}
        />
      </div>
      <span style={{ fontSize: 13, fontWeight: 600, color, minWidth: 40, textAlign: 'right' }}>
        {pct}%
      </span>
    </div>
  );
}
