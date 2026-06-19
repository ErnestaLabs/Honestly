import { useEffect, useState } from 'react';
import { getCatalog } from '../api';

export default function StorePage() {
  const [catalog, setCatalog] = useState(null);
  const [creditBalance, setCreditBalance] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

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

      // Try to read current credit balance from last AVM result
      try {
        const avm = JSON.parse(sessionStorage.getItem('honestly_last_avm') || '{}');
        if (avm.last_purchase?.remaining_credits_gbp !== undefined) {
          setCreditBalance(avm.last_purchase.remaining_credits_gbp);
        }
      } catch {}
    } catch (err) {
      setError(err.message || 'Failed to load store');
    } finally {
      setLoading(false);
    }
  };

  const handleSendInvoice = (payload) => {
    // The Mini App sends an invoice via the Telegram bot
    // This requires the bot to handle the sendInvoice call
    // For now, we open a deep link to the bot with the product data
    const botUsername = 'HonestlyAVMBot';

    const productPayload = typeof payload === 'string' ? payload : JSON.stringify(payload);
    const link = `https://t.me/${botUsername}?start=${encodeURIComponent(productPayload)}`;

    try {
      window.Telegram?.WebApp?.HapticFeedback?.impactOccurred?.('medium');
      window.open(link, '_blank');
    } catch {
      window.location.href = link;
    }
  };

  // ── Subscriptions ────────────────────────────────────
  const tiers = [
    {
      name: 'Free',
      price: '£0',
      features: ['1 AVM per day', 'Read-only rooms', 'Standard ads'],
      cta: 'Current Plan',
      ctaStyle: { background: 'var(--tg-secondary-bg)', color: 'var(--tg-text)' },
    },
    {
      name: 'Plus',
      price: '£4.99',
      period: '/mo',
      features: ['3 AVMs per day', 'Room posting', 'Ad-free', '£5 monthly credit'],
      cta: 'Subscribe Plus',
      highlight: true,
      payload: JSON.stringify({ type: 'sub_plus', tier: 'plus', gbp: 4.99 }),
    },
    {
      name: 'Pro',
      price: '£14.99',
      period: '/mo',
      features: ['Unlimited AVMs', 'Custom branding', 'Advanced maps', '£10 monthly credit'],
      cta: 'Subscribe Pro',
      payload: JSON.stringify({ type: 'sub_pro', tier: 'pro', gbp: 14.99 }),
    },
  ];

  // ── Credit packs ─────────────────────────────────────
  const creditPacks = [
    { label: 'Starter Pack', credits: 250, gbp: 4.99, icon: '🌱' },
    { label: 'Power Pack', credits: 500, gbp: 9.99, icon: '⚡', popular: true },
    { label: 'Whale Pack', credits: 1200, gbp: 19.99, icon: '🐋' },
  ];

  return (
    <div style={{ padding: '20px 16px 100px' }}>
      <h1 style={{ fontSize: 24, fontWeight: 700, margin: '0 0 4px' }}>🛒 Store</h1>
      <p style={{ fontSize: 14, color: 'var(--tg-hint)', margin: '0 0 16px' }}>
        Credits unlock micro-upsells. Subscriptions unlock the full ecosystem.
      </p>

      {/* ── Credit Balance ─────────────────────────────── */}
      <div style={{
        background: 'linear-gradient(135deg, #007aff, #5856d6)',
        borderRadius: 16,
        padding: '20px',
        marginBottom: 20,
        color: '#fff',
      }}>
        <div style={{ fontSize: 12, opacity: 0.8, textTransform: 'uppercase', letterSpacing: 1 }}>
          Your Credit Balance
        </div>
        <div style={{ fontSize: 36, fontWeight: 700, margin: '4px 0' }}>
          £{creditBalance.toFixed(2)}
        </div>
        <div style={{ fontSize: 12, opacity: 0.7 }}>
          {creditBalance > 0
            ? `Enough for ${Math.floor(creditBalance / 1.49)} products`
            : 'Top up to unlock micro-upsells'}
        </div>
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

      {/* ── Subscriptions ──────────────────────────────── */}
      <h3 style={{ fontSize: 15, fontWeight: 600, margin: '0 0 10px' }}>
        📦 Subscriptions
      </h3>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 12, marginBottom: 24 }}>
        {tiers.map((tier) => (
          <div key={tier.name} style={{
            background: tier.highlight
              ? 'linear-gradient(135deg, rgba(0,122,255,0.12), rgba(88,86,214,0.12))'
              : 'var(--tg-secondary-bg)',
            borderRadius: 14,
            padding: '14px 16px',
            border: tier.highlight ? '1px solid rgba(0,122,255,0.4)' : '1px solid var(--tg-section-separator)',
            position: 'relative',
          }}>
            {tier.highlight && (
              <div style={{
                position: 'absolute',
                top: -8,
                right: 12,
                background: 'var(--tg-button)',
                color: '#fff',
                fontSize: 10,
                fontWeight: 700,
                padding: '2px 8px',
                borderRadius: 6,
                textTransform: 'uppercase',
              }}>
                Best Value
              </div>
            )}

            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 8 }}>
              <div>
                <div style={{ fontSize: 17, fontWeight: 600 }}>{tier.name}</div>
                <div style={{ fontSize: 24, fontWeight: 700, marginTop: 2 }}>
                  {tier.price}<span style={{ fontSize: 13, fontWeight: 400, color: 'var(--tg-hint)' }}>{tier.period || ''}</span>
                </div>
              </div>
            </div>

            <ul style={{ margin: '0 0 12px', padding: 0, listStyle: 'none' }}>
              {tier.features.map((f, i) => (
                <li key={i} style={{ fontSize: 13, color: 'var(--tg-hint)', padding: '2px 0', display: 'flex', alignItems: 'center', gap: 6 }}>
                  <span style={{ color: 'var(--tg-accent)' }}>✓</span> {f}
                </li>
              ))}
            </ul>

            {tier.payload && (
              <button
                onClick={() => handleSendInvoice(tier.payload)}
                style={{
                  width: '100%',
                  padding: '12px',
                  borderRadius: 10,
                  background: 'var(--tg-button)',
                  color: 'var(--tg-button-text)',
                  border: 'none',
                  fontSize: 14,
                  fontWeight: 600,
                  cursor: 'pointer',
                }}
              >
                {tier.cta}
              </button>
            )}
            {!tier.payload && (
              <div style={{
                width: '100%',
                padding: '12px',
                borderRadius: 10,
                background: 'var(--tg-secondary-bg)',
                color: 'var(--tg-text)',
                border: '1px solid var(--tg-section-separator)',
                fontSize: 14,
                fontWeight: 600,
                textAlign: 'center',
              }}>
                {tier.cta}
              </div>
            )}
          </div>
        ))}
      </div>

      {/* ── Credit Packs ───────────────────────────────── */}
      <h3 style={{ fontSize: 15, fontWeight: 600, margin: '0 0 10px' }}>
        ⚡ Credit Packs
      </h3>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 10, marginBottom: 24 }}>
        {creditPacks.map((pack) => (
          <div key={pack.label} style={{
            background: pack.popular
              ? 'linear-gradient(135deg, rgba(48,209,88,0.1), rgba(0,122,255,0.1))'
              : 'var(--tg-secondary-bg)',
            borderRadius: 14,
            padding: '12px 16px',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            border: pack.popular ? '1px solid rgba(48,209,88,0.4)' : '1px solid var(--tg-section-separator)',
          }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
              <span style={{ fontSize: 24 }}>{pack.icon}</span>
              <div>
                <div style={{ fontWeight: 600, fontSize: 14 }}>{pack.label}</div>
                <div style={{ fontSize: 12, color: 'var(--tg-hint)' }}>
                  {pack.credits} credits
                  {pack.popular && <span style={{ color: 'var(--tg-accent)', marginLeft: 6 }}>★ Best value</span>}
                </div>
              </div>
            </div>
            <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
              <div style={{ fontSize: 16, fontWeight: 700 }}>£{pack.gbp.toFixed(2)}</div>
              <button
                onClick={() => handleSendInvoice(JSON.stringify({ type: `credits_${pack.credits}`, gbp: pack.gbp }))}
                style={{
                  padding: '8px 16px',
                  borderRadius: 8,
                  background: 'var(--tg-button)',
                  color: 'var(--tg-button-text)',
                  border: 'none',
                  fontSize: 13,
                  fontWeight: 600,
                  cursor: 'pointer',
                }}
              >
                Buy
              </button>
            </div>
          </div>
        ))}
      </div>

      {/* ─── Product Catalog (from orchestrator) ────────── */}
      {catalog?.products?.length > 0 && (
        <>
          <h3 style={{ fontSize: 15, fontWeight: 600, margin: '0 0 10px' }}>
            🛠️ Micro-Upsells
          </h3>
          <p style={{ fontSize: 12, color: 'var(--tg-hint)', margin: '0 0 10px' }}>
            These are triggered automatically when you run a valuation. Buy them individually with credits.
          </p>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
            {catalog.products.map((p) => (
              <div key={p.id} style={{
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'space-between',
                background: 'var(--tg-secondary-bg)',
                borderRadius: 12,
                padding: '10px 14px',
              }}>
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div style={{ fontWeight: 500, fontSize: 13 }}>{p.name}</div>
                  <div style={{ fontSize: 11, color: 'var(--tg-hint)', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
                    {p.description?.slice(0, 60)}...
                  </div>
                </div>
                <div style={{ fontSize: 14, fontWeight: 600, color: 'var(--tg-button)', marginLeft: 8 }}>
                  £{p.effective_gbp_price?.toFixed(2) || p.gbp_price?.toFixed(2)}
                </div>
              </div>
            ))}
          </div>
        </>
      )}
    </div>
  );
}
