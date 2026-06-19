import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { getCatalog, createInvoice } from '../api';
import { loadCreditBalance, saveCreditBalance, setItem } from '../utils/tgStorage';

export default function DiscoverPage() {
  const navigate = useNavigate();
  const [catalog, setCatalog] = useState(null);
  const [creditBalance, setCreditBalance] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [purchasing, setPurchasing] = useState(null);

  useEffect(() => {
    window.Telegram?.WebApp?.expand?.();
    loadStore();
  }, []);

  const loadStore = async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await getCatalog();
      setCatalog(data);
      const balance = await loadCreditBalance();
      if (balance > 0) setCreditBalance(balance);
    } catch (err) {
      setError(err.message || 'Failed to load store');
    } finally {
      setLoading(false);
    }
  };

  const openInvoice = async ({ subTier, creditPackGbp, label }) => {
    setPurchasing(label);
    setError(null);
    try {
      const invoice = await createInvoice({ subTier, creditPackGbp });
      if (!invoice.ok || !invoice.invoice_url) throw new Error(invoice.error || 'Invoice creation failed');
      const tg = window.Telegram?.WebApp;
      if (!tg?.openInvoice) throw new Error('Telegram WebApp.openInvoice not available');
      tg.openInvoice(invoice.invoice_url, async (status) => {
        if (status === 'paid') {
          window.Telegram?.WebApp?.HapticFeedback?.notificationOccurred?.('success');
          if (subTier) {
            const monthlyCredit = subTier === 'plus' ? 5.0 : 10.0;
            const newBalance = creditBalance + monthlyCredit;
            setCreditBalance(newBalance);
            await saveCreditBalance(newBalance);
          } else if (creditPackGbp) {
            const newBalance = creditBalance + creditPackGbp;
            setCreditBalance(newBalance);
            await saveCreditBalance(newBalance);
          }
          loadStore();
        } else if (status === 'cancelled') {
          window.Telegram?.WebApp?.HapticFeedback?.notificationOccurred?.('warning');
        } else {
          setError('Payment not completed');
          window.Telegram?.WebApp?.HapticFeedback?.notificationOccurred?.('error');
        }
      });
    } catch (err) {
      setError(err.message || 'Payment failed');
      window.Telegram?.WebApp?.HapticFeedback?.notificationOccurred?.('error');
    } finally {
      setPurchasing(null);
    }
  };

  const emotionGroups = {
    anger: { icon: '😡', label: 'Anger', products: [] },
    fomo: { icon: '🔥', label: 'FOMO', products: [] },
    greed: { icon: '💰', label: 'Greed', products: [] },
    laziness: { icon: '😴', label: 'Laziness', products: [] },
    fear: { icon: '😰', label: 'Fear', products: [] },
  };

  const allProducts = catalog?.products || [];
  allProducts.forEach(p => {
    const g = emotionGroups[p.emotion_trigger];
    if (g) g.products.push(p);
  });

  const creditPacks = [
    { label: 'credits_250', name: 'Starter Pack', credits: 250, gbp: 4.99 },
    { label: 'credits_500', name: 'Power Pack', credits: 500, gbp: 9.99, popular: true },
    { label: 'credits_1200', name: 'Whale Pack', credits: 1200, gbp: 19.99 },
  ];

  return (
    <div style={{ padding: '0 0 100px' }}>
      {/* ── Credit Balance Hero ────────────────────────── */}
      <div style={{ padding: '20px 16px', background: 'var(--brand-dark)', color: 'var(--brand-cream)' }}>
        <div className="brand-label" style={{ fontSize: 9, opacity: 0.6, letterSpacing: '0.2em', marginBottom: 2 }}>
          YOUR CREDITS
        </div>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <div style={{ fontFamily: '"Fraunces", Georgia, serif', fontSize: 32, fontWeight: 700 }}>
            {'\u00a3'}{creditBalance.toFixed(2)}
          </div>
          <div style={{ display: 'flex', gap: 8 }}>
            {creditPacks.map(p => (
              <button
                key={p.label}
                onClick={() => openInvoice({ creditPackGbp: p.gbp, label: p.label })}
                disabled={purchasing === p.label}
                className="tribute-pill"
                style={{
                  background: p.popular ? 'var(--brand-green)' : 'rgba(246,243,236,0.15)',
                  color: 'var(--brand-cream)',
                  fontSize: 11,
                }}
              >
                {'\u00a3'}{p.gbp.toFixed(2)}
              </button>
            ))}
          </div>
        </div>
      </div>

      {error && (
        <div className="ui-text" style={{
          background: 'rgba(199,58,58,0.08)', borderRadius: 8, padding: 10,
          margin: '12px 16px', fontSize: 12, color: '#c73a3a',
        }}>
          {error}
        </div>
      )}

      {/* ── Products by Emotion ────────────────────────── */}
      <div style={{ padding: '16px' }}>
        {Object.entries(emotionGroups).map(([key, group]) => {
          if (group.products.length === 0) return null;
          return (
            <div key={key} style={{ marginBottom: 20 }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 8 }}>
                <span style={{ fontSize: 16 }}>{group.icon}</span>
                <span className="brand-label" style={{ fontSize: 10, color: 'var(--brand-muted)', letterSpacing: '0.18em' }}>
                  {group.label}
                </span>
              </div>
              <div style={{ display: 'flex', flexDirection: 'column', gap: 0 }}>
                {group.products.map(p => (
                  <div key={p.id} className="tribute-row" onClick={() => navigate('/report')}>
                    <span style={{ fontSize: 16, width: 24 }}>{group.icon}</span>
                    <div style={{ flex: 1 }}>
                      <div className="ui-text" style={{ fontSize: 13, fontWeight: 500 }}>{p.name}</div>
                      <div className="ui-text" style={{ fontSize: 11, color: 'var(--brand-muted)' }}>
                        {p.description?.slice(0, 60)}
                      </div>
                    </div>
                    <div style={{ fontFamily: '"Fraunces", Georgia, serif', fontSize: 14, fontWeight: 600, color: 'var(--brand-dark)' }}>
                      {'\u00a3'}{p.effective_gbp_price?.toFixed(2) || p.gbp_price?.toFixed(2)}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          );
        })}
      </div>

      {/* ── Subscriptions (Patreon-style) ──────────────── */}
      <div style={{ padding: '0 16px 16px' }}>
        <div className="brand-hair" style={{ marginBottom: 16 }} />
        <div className="brand-label" style={{ fontSize: 10, color: 'var(--brand-muted)', letterSpacing: '0.18em', marginBottom: 10 }}>
          SUPPORT THE PLATFORM
        </div>

        {[
          {
            tier: 'plus', name: 'Honestly Plus', price: '\u00a34.99/mo',
            features: ['3 AVMs/day', 'Room posting', 'Ad-free', '\u00a35 monthly credit'],
          },
          {
            tier: 'pro', name: 'Honestly Pro', price: '\u00a314.99/mo',
            features: ['Unlimited AVMs', 'Custom branding', 'Advanced maps', '\u00a310 monthly credit'],
            highlight: true,
          },
        ].map(sub => (
          <div key={sub.tier} style={{
            background: sub.highlight ? 'linear-gradient(135deg, var(--brand-dark), #1a3a6b)' : 'var(--brand-paper)',
            borderRadius: 10,
            padding: '14px 16px',
            marginBottom: 10,
            border: sub.highlight ? 'none' : '1px solid var(--brand-line)',
            color: sub.highlight ? 'var(--brand-cream)' : 'var(--brand-ink)',
          }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 6 }}>
              <div style={{ fontFamily: '"Fraunces", Georgia, serif', fontWeight: 600, fontSize: 16 }}>
                {sub.name}
              </div>
              <div style={{ fontFamily: '"Fraunces", Georgia, serif', fontWeight: 700, fontSize: 15, color: sub.highlight ? 'var(--brand-gold)' : 'var(--brand-green)' }}>
                {sub.price}
              </div>
            </div>
            <ul style={{ margin: '0 0 10px', padding: 0, listStyle: 'none' }}>
              {sub.features.map((f, i) => (
                <li key={i} className="ui-text" style={{
                  fontSize: 12, padding: '1px 0',
                  color: sub.highlight ? 'rgba(246,243,236,0.7)' : 'var(--brand-muted)',
                }}>
                  ✓ {f}
                </li>
              ))}
            </ul>
            <button
              onClick={() => openInvoice({ subTier: sub.tier, label: `sub_${sub.tier}` })}
              disabled={purchasing === `sub_${sub.tier}`}
              className="tribute-pill"
              style={{
                width: '100%', justifyContent: 'center', padding: '10px',
                background: sub.highlight ? 'var(--brand-green)' : 'var(--brand-dark)',
                color: 'var(--brand-cream)', fontSize: 13,
              }}
            >
              {purchasing === `sub_${sub.tier}` ? '...' : `Subscribe ${sub.tier === 'plus' ? 'Plus' : 'Pro'}`}
            </button>
          </div>
        ))}
      </div>
    </div>
  );
}
