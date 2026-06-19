/**
 * tgStorage.js — Telegram CloudStorage wrapper.
 *
 * Telegram Mini Apps are frequently killed in the background.
 * sessionStorage is wiped on cold restarts.
 * CloudStorage is native to TG and survives across sessions.
 *
 * This module provides a simple async get/set/remove API
 * that degrades gracefully to sessionStorage when CloudStorage
 * is unavailable (e.g. running in a browser outside Telegram).
 */

function isAvailable() {
  return !!(window.Telegram?.WebApp?.CloudStorage);
}

function warn(method, err) {
  console.warn(`[tgStorage] ${method} fallback:`, err?.message || err);
}

/**
 * Set an item in CloudStorage (or sessionStorage fallback).
 * @returns {Promise<void>}
 */
export function setItem(key, value) {
  return new Promise((resolve) => {
    try {
      const str = typeof value === 'string' ? value : JSON.stringify(value);
      if (isAvailable()) {
        window.Telegram.WebApp.CloudStorage.setItem(key, str, () => resolve());
      } else {
        sessionStorage.setItem(`honestly_${key}`, str);
        resolve();
      }
    } catch (err) {
      warn('setItem', err);
      resolve();
    }
  });
}

/**
 * Get an item from CloudStorage (or sessionStorage fallback).
 * @returns {Promise<string|null>}
 */
export function getItem(key) {
  return new Promise((resolve) => {
    try {
      if (isAvailable()) {
        window.Telegram.WebApp.CloudStorage.getItem(key, (err, value) => {
          if (err) {
            warn('getItem', err);
            resolve(null);
          } else {
            resolve(value ?? null);
          }
        });
      } else {
        resolve(sessionStorage.getItem(`honestly_${key}`));
      }
    } catch (err) {
      warn('getItem', err);
      resolve(null);
    }
  });
}

/**
 * Remove an item from CloudStorage (or sessionStorage fallback).
 * @returns {Promise<void>}
 */
export function removeItem(key) {
  return new Promise((resolve) => {
    try {
      if (isAvailable()) {
        window.Telegram.WebApp.CloudStorage.removeItem(key, () => resolve());
      } else {
        sessionStorage.removeItem(`honestly_${key}`);
        resolve();
      }
    } catch (err) {
      warn('removeItem', err);
      resolve();
    }
  });
}

/**
 * Convenience: save the last AVM result.
 */
export async function saveLastAvm(avmResult) {
  await setItem('last_avm', JSON.stringify(avmResult));
}

/**
 * Convenience: load the last AVM result.
 * @returns {Promise<object|null>}
 */
export async function loadLastAvm() {
  const raw = await getItem('last_avm');
  if (!raw) return null;
  try {
    return JSON.parse(raw);
  } catch {
    return null;
  }
}

/**
 * Convenience: save credit balance.
 */
export async function saveCreditBalance(gbp) {
  await setItem('credit_balance', String(gbp));
}

/**
 * Convenience: load credit balance.
 * @returns {Promise<number>}
 */
export async function loadCreditBalance() {
  const raw = await getItem('credit_balance');
  if (raw === null || raw === undefined) return 0;
  const n = parseFloat(raw);
  return isNaN(n) ? 0 : n;
}
