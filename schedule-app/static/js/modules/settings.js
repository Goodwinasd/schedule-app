import { api } from './api.js';
import { escapeHtml } from './utils.js';

export async function loadSettingsTab() {
    const cont = document.getElementById('settings-content');
    cont.innerHTML = '<div class="loading">Загрузка...</div>';
    const data = await api('/api/settings');
    if (data.error) { cont.innerHTML = '<div style="color:var(--danger)">Ошибка загрузки настроек</div>'; return; }
    const labels = { session_lifetime: 'Время сессии (сек)', login_rate_limit: 'Лимит попыток входа', login_rate_window: 'Окно попыток входа (сек)', backup_retention_days: 'Хранение бэкапов (дней)' };
    const descs = { session_lifetime: 'Через сколько секунд сессия администратора истекает', login_rate_limit: 'Максимум неудачных попыток входа до блокировки', login_rate_window: 'Время в секундах, за которое считаются попытки', backup_retention_days: 'Сколько дней хранить автоматические бэкапы БД' };
    let html = '';
    for (const [key, label] of Object.entries(labels)) {
        const val = data[key] || '';
        html += `<div style="margin:12px 0"><label style="display:block;font-size:13px;font-weight:600;margin-bottom:2px">${label}</label>`;
        html += `<div style="font-size:11px;color:var(--text-secondary);margin-bottom:4px">${descs[key]}</div>`;
        html += `<div class="field-row"><input type="text" id="settings-${key}" value="${escapeHtml(val)}" class="input" style="max-width:120px">`;
        html += `<button class="btn btn-primary btn-sm" data-action="saveSetting" data-params='["${escapeHtml(key)}"]'>Сохранить</button></div></div>`;
    }
    cont.innerHTML = html;
}

export async function saveSetting(key) {
    const inp = document.getElementById(`settings-${key}`);
    if (!inp) return;
    const val = inp.value.trim();
    const res = await api(`/api/settings/${key}`, { method: 'PUT', body: JSON.stringify({ value: val }) });
    if (res.error) { alert(res.error); return; }
    alert('Сохранено');
    loadSettingsTab();
}
