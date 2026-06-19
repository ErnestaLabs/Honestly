import { useEffect, useState } from 'react';
import { getCatalog, createInvoice } from '../api';
import { loadCreditBalance, saveCreditBalance, setItem } from '../utils/tgStorage';

export default function StorePage() {
  const [catalog, setCatalog] = useState(null);
  const [creditBalance, setCreditBalance] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [purchasing, setPurchasing] = useState(null); // 'sub_plus' | 'sub_pro' | 'credits_250' | ...

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

      // Load credit balance from CloudStorage (persists across TG restarts)
      const balance = await loadCreditBalance();
      if (balance > 0) setCreditBalance(balance);
    } catch (err) {
      setError(err.message || 'Failed to load store');
    } finally {
      setLoading(false);
    }
  };

  /**
   * Open Telegram's native invoice overlay INSIDE the Mini App.
   * Never opens a deep-link. Never leaves the app.
   */
  const openInvoice = async ({ productId, subTier, creditPackGbp, label }) => {
    setPurchasing(label || productId || subTier);
    setError(null);

    try {
      // Step 1: Backend creates the invoice link
      const invoice = await createInvoice({ productId, subTier, creditPackGbp });
      if (!invoice.ok || !invoice.invoice_url) {
        throw new Error(invoice.error || 'Invoice creation failed');
      }

      // Step 2: Open the native TG invoice overlay
      // Telegram.WebApp.openInvoice(url, callback) shows the payment
      // sheet INSIDE the Mini App. The user never leaves.
      const tg = window.Telegram?.WebApp;
      if (!tg?.openInvoice) {
        throw new Error('Telegram WebApp.openInvoice not available');
      }

      tg.openInvoice(invoice.invoice_url, async (status) => {
        if (status === 'paid') {
          window.Telegram?.WebApp?.HapticFeedback?.notificationOccurred?.('success');

          // Update credit balance in CloudStorage
          if (subTier) {
            // Subscription: set a rough indicator in storage
            await setItem('honestly_tier', subTier);
            // Grant monthly credits immediately
            const monthlyCredit = subTier === 'plus' ? 5.0 : 10.0;
            const newBalance = creditBalance + monthlyCredit;
            setCreditBalance(newBalance);
            await saveCreditBalance(newBalance);
          } else if (creditPackGbp) {
            // Credit top-up: add to balance
            const newBalance = creditBalance + creditPackGbp;
            setCreditBalance(newBalance);
            await saveCreditBalance(newBalance);
          }

          // Reload catalog to refresh tier/prices
          loadStore();
        } else if (status === 'cancelled') {
          window.Telegram?.WebApp?.HapticFeedback?.notificationOccurred?.('warning');
        } else {
          // 'failed' or unknown
          setError('Payment was not completed. Please try again.');
          window.Telegram?.WebApp?.HapticFeedback?.notificationOccurred?.('error');
        }
      });
    } catch (err) {
      const msg = err.message || 'Payment failed';
      setError(msg);
      window.Telegram?.WebApp?.HapticFeedback?.notificationOccurred?.('error');
    } finally {
      setPurchasing(null);
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
      label: 'sub_plus',
      subTier: 'plus',
    },
    {
      name: 'Pro',
      price: '£14.99',
      period: '/mo',
      features: ['Unlimited AVMs', 'Custom branding', 'Advanced maps', '£10 monthly credit'],
      cta: 'Subscribe Pro',
      label: 'sub_pro',
      subTier: 'pro',
    },
  ];

  // ── Credit packs ─────────────────────────────────────
  const creditPacks = [
    { label: 'credits_250', name: 'Starter Pack', credits: 250, gbp: 4.99, icon: '🌱' },
    { label: 'credits_500', name: 'Power Pack', credits: 500, gbp: 9.99, icon: '⚡', popular: true },
    { label: 'credits_1200', name: 'Whale Pack', credits: 1200, gbp: 19.99, icon: '🐋' },
  ];

  return (
    <div style={{ padding: '20px 16px 100px' }}>
      <h1 style={{ fontSize: 24, fontWeight: 700, margin: '0 0 4px' }}>🛒 Store</h1>
      <p style={{ fontSize: 14, color: 'var(--tg-hint)', margin: '0 0 16px' }}>
        Credits unlock micro-upsells. Subscriptions unlock the full ecosystem.
      </p>

      {/* ── Credit Balance (from CloudStorage) ─────────── */}
      <div style={{
        background: 'var(--brand-dark)',
        borderRadius: 8,
        padding: '20px',
        marginBottom: 20,
        color: 'var(--brand-cream)',
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
                position: 'absolute', top: -8, right: 12,
                background: 'var(--tg-button)', color: '#fff',
                fontSize: 10, fontWeight: 700, padding: '2px 8px',
                borderRadius: 6, textTransform: 'uppercase',
              }}>
                Best Value
              </div>
            )}
            <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 8 }}>
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
            {tier.subTier ? (
              <button
                onClick={() => openInvoice({ subTier: tier.subTier, label: tier.label })}
                disabled={purchasing === tier.label}
                style={{
                  width: '100%', padding: '12px', borderRadius: 10,
                  background: purchasing === tier.label ? 'var(--tg-hint)' : 'var(--tg-button)',
                  color: 'var(--tg-button-text)', border: 'none',
                  fontSize: 14, fontWeight: 600, cursor: purchasing ? 'not-allowed' : 'pointer',
                  opacity: purchasing === tier.label ? 0.6 : 1,
                }}
              >
                {purchasing === tier.label ? 'Opening...' : tier.cta}
              </button>
            ) : (
              <div style={{
                width: '100%', padding: '12px', borderRadius: 10,
                background: 'var(--tg-secondary-bg)', color: 'var(--tg-text)',
                border: '1px solid var(--tg-section-separator)',
                fontSize: 14, fontWeight: 600, textAlign: 'center',
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
            borderRadius: 14, padding: '12px 16px',
            display: 'flex', alignItems: 'center', justifyContent: 'space-between',
            border: pack.popular ? '1px solid rgba(48,209,88,0.4)' : '1px solid var(--tg-section-separator)',
          }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
              <span style={{ fontSize: 24 }}>{pack.icon}</span>
              <div>
                <div style={{ fontWeight: 600, fontSize: 14 }}>{pack.name}</div>
                <div style={{ fontSize: 12, color: 'var(--tg-hint)' }}>
                  {pack.credits} credits
                  {pack.popular && <span style={{ color: 'var(--tg-accent)', marginLeft: 6 }}>★ Best value</span>}
                </div>
              </div>
            </div>
            <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
              <div style={{ fontSize: 16, fontWeight: 700 }}>£{pack.gbp.toFixed(2)}</div>
              <button
                onClick={() => openInvoice({ creditPackGbp: pack.gbp, label: pack.label })}
                disabled={purchasing === pack.label}
                style={{
                  padding: purchasing === pack.label ? '8px 12px' : '8px 16px',
                  borderRadius: 8,
                  background: purchasing === pack.label ? 'var(--tg-hint)' : 'var(--tg-button)',
                  color: 'var(--tg-button-text)', border: 'none',
                  fontSize: 13, fontWeight: 600, cursor: purchasing ? 'not-allowed' : 'pointer',
                  opacity: purchasing === pack.label ? 0.6 : 1,
                }}
              >
                {purchasing === pack.label ? '...' : 'Buy'}
              </button>
            </div>
          </div>
        ))}
      </div>

      {/* ── Product Catalog ────────────────────────────── */}
      {catalog?.products?.length > 0 && (
        <>
          <h3 style={{ fontSize: 15, fontWeight: 600, margin: '0 0 10px' }}>
            🛠️ Micro-Upsells
          </h3>
          <p style={{ fontSize: 12, color: 'var(--tg-hint)', margin: '0 0 10px' }}>
            These are triggered automatically when you run a valuation. Buy them from the valuation report.
          </p>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
            {catalog.products.map((p) => (
              <div key={p.id} style={{
                display: 'flex', alignItems: 'center', justifyContent: 'space-between',
                background: 'var(--tg-secondary-bg)', borderRadius: 12,
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
