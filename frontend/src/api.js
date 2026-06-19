import axios from 'axios';

const BASE = import.meta.env.VITE_API_BASE || 'https://usehonestly.co.uk';

const api = axios.create({
  baseURL: `${BASE}/api`,
  timeout: 30000,
  headers: { 'Content-Type': 'application/json' },
});

// Inject auth token from Telegram user data
api.interceptors.request.use((config) => {
  try {
    const tg = window.Telegram?.WebApp;
    const userId = tg?.initDataUnsafe?.user?.id || 'anonymous';
    // Tier is stored in sessionStorage after initial load
    const tier = sessionStorage.getItem('honestly_tier') || 'free';
    config.headers.Authorization = `Bearer ${userId}:${tier}`;
  } catch {
    config.headers.Authorization = 'Bearer anonymous:free';
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
