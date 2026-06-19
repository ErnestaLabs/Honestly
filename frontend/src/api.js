/**
 * api.js — Honestly API client.
 *
 * SECURITY: The frontend NEVER dictates the user's tier.
 * The auth interceptor only passes the Telegram user_id (or initData in production).
 * The backend resolves the tier server-side via Redis on every request.
 */
import axios from 'axios';

const BASE = import.meta.env.VITE_API_BASE || 'https://usehonestly.co.uk';

const api = axios.create({
  baseURL: `${BASE}/api`,
  timeout: 30000,
  headers: { 'Content-Type': 'application/json' },
});

// Inject auth: only user_id. NO tier information is passed.
// The backend resolves the tier server-side.
api.interceptors.request.use((config) => {
  try {
    const tg = window.Telegram?.WebApp;
    const userId = tg?.initDataUnsafe?.user?.id || 'anonymous';
    // Bearer token contains ONLY the user_id. No tier.
    // In production, we could pass the full initData string for server-side validation.
    config.headers.Authorization = `Bearer ${userId}`;
  } catch {
    config.headers.Authorization = 'Bearer anonymous';
  }
  return config;
});

// ── Valuation ──────────────────────────────────────────
export async function valuate(address, { beds, sqm, ptype, finish } = {}) {
  const { data } = await api.post('/v1/properties/valuate', {
    address,
    user_id: String(window.Telegram?.WebApp?.initDataUnsafe?.user?.id || ''),
    beds: beds || null,
    sqm: sqm || null,
    ptype: ptype || null,
    finish: finish || 'average',
  });
  return data;
}

// ── Products ───────────────────────────────────────────
export async function getCatalog() {
  const { data } = await api.get('/v1/products/catalog');
  return data;
}

export async function purchaseProduct(productId, valuationContext) {
  const { data } = await api.post('/v1/products/purchase', {
    user_id: String(window.Telegram?.WebApp?.initDataUnsafe?.user?.id || ''),
    product_id: productId,
    valuation_context: valuationContext,
  });
  return data;
}

// ── Invoice (native Telegram payment overlay) ──────────
export async function createInvoice({ productId, subTier, creditPackGbp } = {}) {
  const { data } = await api.post('/v1/payments/create_invoice', {
    user_id: String(window.Telegram?.WebApp?.initDataUnsafe?.user?.id || ''),
    product_id: productId || null,
    sub_tier: subTier || null,
    credit_pack_gbp: creditPackGbp || null,
  });
  return data;
}

// ── Arena ──────────────────────────────────────────────
export async function getVibe(postcode) {
  const { data } = await api.get(`/v1/arena/vibe/${encodeURIComponent(postcode)}`);
  return data;
}

export async function getLeaderboard(postcode, limit = 10) {
  const { data } = await api.get(`/v1/arena/leaderboard/${encodeURIComponent(postcode)}`, {
    params: { limit },
  });
  return data;
}

export async function getRoom(postcode) {
  const { data } = await api.get(`/v1/rooms/${encodeURIComponent(postcode)}`);
  return data;
}

export default api;
