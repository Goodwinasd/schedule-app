import state from './state.js';

/**
 * Универсальный API-клиент с CSRF-защитой
 * @param {string} url
 * @param {object} [options]
 * @returns {Promise<object>}
 */
export async function api(url, options = {}) {
    const headers = { 'Content-Type': 'application/json', ...options.headers };
    if (state.csrfToken && options.method && options.method !== 'GET') {
        headers['X-CSRF-Token'] = state.csrfToken;
    }
    const res = await fetch(url, { ...options, headers });
    const data = await res.json();
    if (res.status === 401) {
        state.isAdmin = false;
        if (window._onUnauthorized) window._onUnauthorized();
    }
    return data;
}
