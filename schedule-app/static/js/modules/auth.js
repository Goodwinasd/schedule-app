import state from './state.js';
import { api } from './api.js';
import { updateUI } from './navigation.js';

export async function checkAuth() {
    const data = await api('/api/auth/check');
    state.isAdmin = data.is_admin;
    if (state.isAdmin) {
        const tokenData = await api('/api/auth/csrf-token');
        state.csrfToken = tokenData.csrf_token || '';
    }
    updateUI();
}

export async function login() {
    const data = await api('/api/auth/login', {
        method: 'POST',
        body: JSON.stringify({ password: document.getElementById('login-password').value }),
    });
    if (data.success) {
        state.isAdmin = true;
        state.csrfToken = data.csrf_token || '';
        closeModals();
        updateUI();
    } else {
        window._showKimiAlert && window._showKimiAlert('Неверный пароль');
    }
}

export async function logout() {
    await api('/api/auth/logout', { method: 'POST' });
    state.isAdmin = false;
    state.csrfToken = '';
    updateUI();
}

import { closeModals } from './ui.js';
