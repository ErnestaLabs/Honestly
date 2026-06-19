import { useEffect, useState } from 'react';
import { getVibe, getLeaderboard, getRoom } from '../api';

function formatPrice(n) {
  if (!n) return '—';
  return '£' + Number(n).toLocaleString('en-GB');
}

export default function ArenaPage() {
  const [postcode, setPostcode] = useState(() => {
    // Try to get the postcode from the last AVM
    try {
      const avm = JSON.parse(sessionStorage.getItem('honestly_last_avm') || '{}');
      return avm.avm?.postcode || '';
    } catch { return ''; }
  });
  const [vibe, setVibe] = useState(null);
  const [leaderboard, setLeaderboard] = useState([]);
  const [userRank, setUserRank] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [roomLink, setRoomLink] = useState(null);

  const loadArena = async (pc) => {
    if (!pc || pc.length < 3) return;
    setLoading(true);
    setError(null);
    try {
      const [vibeData, boardData] = await Promise.all([
        getVibe(pc),
        getLeaderboard(pc),
      ]);
      setVibe(vibeData);
      setLeaderboard(boardData.leaderboard || []);
      setUserRank(boardData.user_rank || null);
    } catch (err) {
      setError(err.message || 'Failed to load Arena data');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    window.Telegram?.WebApp?.expand?.();
    loadArena(postcode);
  }, []);

  const handleEnterRoom = async () => {
    if (!postcode) return;
    try {
      const room = await getRoom(postcode);
      if (room.deep_link) {
        setRoomLink(room.deep_link);
        window.open(room.deep_link, '_blank');
        window.Telegram?.WebApp?.HapticFeedback?.impactOccurred?.('medium');
      }
    } catch (err) {
      setError(err.message || 'Room unavailable');
    }
  };

  const vibeColor = vibe?.trend === 'Hot' ? '#ff453a'
    : vibe?.trend === 'Rising' ? '#ff9f0a'
    : vibe?.trend === 'Steady' ? '#30d158'
    : vibe?.trend === 'Cooling' ? '#64d2ff'
    : '#8e8e93';

  return (
    <div style={{ padding: '20px 16px 100px' }}>
      <h1 style={{ fontSize: 24, fontWeight: 700, margin: '0 0 4px' }}>🏟️ Arena</h1>
      <p style={{ fontSize: 14, color: 'var(--tg-hint)', margin: '0 0 16px' }}>
        Daily Vibe Check and leaderboard for your postcode.
      </p>

      {/* Postcode input */}
      <div style={{ display: 'flex', gap: 8, marginBottom: 20 }}>
        <input
          type="text"
          value={postcode}
          onChange={(e) => setPostcode(e.target.value.toUpperCase())}
          placeholder="Enter postcode..."
          style={{
            flex: 1,
            padding: '12px 16px',
            borderRadius: 12,
            border: '1px solid var(--tg-section-separator)',
            background: 'var(--tg-secondary-bg)',
            color: 'var(--tg-text)',
            fontSize: 15,
            outline: 'none',
            textTransform: 'uppercase',
          }}
        />
        <button
          onClick={() => loadArena(postcode)}
          disabled={loading || postcode.length < 3}
          style={{
            padding: '12px 20px',
            borderRadius: 12,
            background: 'var(--tg-button)',
            color: 'var(--tg-button-text)',
            border: 'none',
            fontSize: 14,
            fontWeight: 600,
            cursor: loading || postcode.length < 3 ? 'not-allowed' : 'pointer',
            opacity: loading || postcode.length < 3 ? 0.6 : 1,
          }}
        >
          {loading ? '...' : 'Go'}
        </button>
      </div>

      {error && (
        <div style={{
          background: 'rgba(255,69,58,0.1)',
          borderRadius: 10,
          padding: 10,
          fontSize: 13,
          color: 'var(--color-anger)',
          marginBottom: 16,
        }}>
          {error}
        </div>
      )}

      {/* Vibe Score */}
      {vibe && vibe.vibe_score !== null && (
        <div style={{
          background: 'var(--tg-secondary-bg)',
          borderRadius: 16,
          padding: '20px',
          marginBottom: 16,
          textAlign: 'center',
        }}>
          <div style={{ fontSize: 12, color: 'var(--tg-hint)', textTransform: 'uppercase', letterSpacing: 1, marginBottom: 4 }}>
            Daily Vibe Score
          </div>
          <div style={{ fontSize: 48, fontWeight: 700, color: vibeColor, margin: '4px 0' }}>
            {vibe.vibe_score}
          </div>
          <div style={{ fontSize: 14, fontWeight: 600, color: vibeColor, textTransform: 'uppercase' }}>
            {vibe.trend || 'Unknown'}
          </div>
          <p style={{ fontSize: 12, color: 'var(--tg-hint)', marginTop: 8 }}>
            {vibe.vibe_score >= 80 ? 'The market is on fire in this area.' :
             vibe.vibe_score >= 65 ? 'Things are heating up.' :
             vibe.vibe_score >= 35 ? 'Steady market, normal conditions.' :
             vibe.vibe_score >= 20 ? 'Market cooling - opportunities ahead.' :
             'Cold market - bargain hunting territory.'}
          </p>

          {/* Vibe breakdown */}
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 8, marginTop: 12 }}>
            <div style={{ background: 'var(--tg-bg)', borderRadius: 10, padding: '8px' }}>
              <div style={{ fontSize: 11, color: 'var(--tg-hint)' }}>Momentum</div>
              <div style={{ fontSize: 16, fontWeight: 600 }}>{(vibe.vibe_score * 0.6).toFixed(0)}</div>
            </div>
            <div style={{ background: 'var(--tg-bg)', borderRadius: 10, padding: '8px' }}>
              <div style={{ fontSize: 11, color: 'var(--tg-hint)' }}>Sentiment</div>
              <div style={{ fontSize: 16, fontWeight: 600 }}>{(vibe.vibe_score * 0.4).toFixed(0)}</div>
            </div>
          </div>
        </div>
      )}

      {/* Room Entry */}
      <button
        onClick={handleEnterRoom}
        disabled={!postcode}
        style={{
          width: '100%',
          padding: '16px',
          borderRadius: 14,
          background: !postcode ? 'var(--tg-section-separator)' : 'linear-gradient(135deg, #007aff, #5856d6)',
          color: '#fff',
          border: 'none',
          fontSize: 16,
          fontWeight: 600,
          cursor: !postcode ? 'not-allowed' : 'pointer',
          opacity: !postcode ? 0.5 : 1,
          marginBottom: 20,
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          gap: 8,
        }}
      >
        <span>💬</span>
        Enter {postcode || 'Your'} Room
      </button>

      {/* Leaderboard */}
      <h3 style={{ fontSize: 15, fontWeight: 600, margin: '0 0 10px' }}>
        🏆 Leaderboard — {postcode || 'No postcode'}
      </h3>

      {leaderboard.length === 0 && !loading && (
        <p style={{ fontSize: 13, color: 'var(--tg-hint)' }}>
          No entries yet. Be the first - run a valuation to earn points!
        </p>
      )}

      <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
        {leaderboard.map((entry, i) => {
          const isCurrentUser = entry.user === userRank?.user;
          return (
            <div key={entry.user || i} style={{
              display: 'flex',
              alignItems: 'center',
              gap: 12,
              background: isCurrentUser ? 'rgba(0,122,255,0.08)' : 'var(--tg-secondary-bg)',
              borderRadius: 12,
              padding: '10px 14px',
              border: isCurrentUser ? '1px solid rgba(0,122,255,0.3)' : 'none',
            }}>
              <div style={{
                width: 28,
                height: 28,
                borderRadius: 14,
                background: i === 0 ? '#ffd60a' : i === 1 ? '#c0c0c0' : i === 2 ? '#cd7f32' : 'var(--tg-section-separator)',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                fontSize: 12,
                fontWeight: 700,
                color: i < 3 ? '#000' : 'var(--tg-text)',
              }}>
                {i + 1}
              </div>
              <div style={{ flex: 1, fontWeight: isCurrentUser ? 600 : 400, fontSize: 14 }}>
                {entry.user || 'Anonymous'}
                {isCurrentUser && <span style={{ fontSize: 11, color: 'var(--tg-button)', marginLeft: 6 }}>(you)</span>}
              </div>
              <div style={{ fontWeight: 600, fontSize: 14, color: 'var(--tg-accent)' }}>
                {entry.score || 0} pts
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
