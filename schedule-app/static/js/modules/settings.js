import { api } from './api.js';
import { escapeHtml } from './utils.js';
import { showKimiAlert } from './modal.js';
import { showToast } from './toast.js';

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
    if (res.error) { await showKimiAlert(res.error); return; }
    showToast('Сохранено', 'success');
    loadSettingsTab();
}

export async function loadExcludedDates() {
    const cont = document.getElementById('excluded-dates-content');
    if (!cont) return;
    cont.innerHTML = '<div class="loading">Загрузка...</div>';
    const data = await api('/api/excluded-dates');
    if (data.error) { cont.innerHTML = '<div style="color:var(--danger)">Ошибка загрузки</div>'; return; }
    let html = '<div style="margin:12px 0"><strong style="font-size:14px">Исключённые даты</strong></div>';
    if (!data.length) {
        html += '<div style="font-size:13px;color:var(--text-secondary);padding:8px 0">Нет исключённых дат</div>';
    } else {
        html += '<div style="display:flex;flex-direction:column;gap:4px">';
        for (const d of data) {
            const label = d.start_date === d.end_date ? d.start_date : `${d.start_date} – ${d.end_date}`;
            html += `<div class="ref-item"><span class="ref-item-name">${escapeHtml(label)}${d.reason ? ' <span style="color:var(--text-secondary)">— ' + escapeHtml(d.reason) + '</span>' : ''}</span>`;
            html += `<div class="ref-item-actions"><button class="btn btn-danger btn-sm" data-action="deleteExcludedDate" data-params='[${d.id}]'>×</button></div></div>`;
        }
        html += '</div>';
    }
    html += '<hr style="margin:16px 0;border:none;border-top:1px solid var(--border)">';
    html += '<div style="font-size:13px;font-weight:600;margin-bottom:8px">Добавить исключение</div>';
    html += '<div class="field-row" style="margin-bottom:8px">';
    html += '<label style="font-size:12px;color:var(--text-secondary);min-width:40px">С</label>';
    html += '<input type="date" id="excl-start" class="input" style="max-width:160px">';
    html += '<label style="font-size:12px;color:var(--text-secondary);min-width:20px">по</label>';
    html += '<input type="date" id="excl-end" class="input" style="max-width:160px">';
    html += '</div>';
    html += '<div class="field-row">';
    html += '<input type="text" id="excl-reason" placeholder="Причина (необязательно)" class="input" style="max-width:300px">';
    html += '<button class="btn btn-primary btn-sm" data-action="addExcludedDate">Добавить</button>';
    html += '</div>';
    cont.innerHTML = html;
}

export async function addExcludedDate() {
    const start = document.getElementById('excl-start');
    const end = document.getElementById('excl-end');
    const reason = document.getElementById('excl-reason');
    if (!start || !start.value || !end || !end.value) { await showKimiAlert('Укажите начальную и конечную дату'); return; }
    const res = await api('/api/excluded-dates', { method: 'POST', body: JSON.stringify({ start_date: start.value, end_date: end.value, reason: (reason ? reason.value : '') }) });
    if (res.error) { await showKimiAlert(res.error); return; }
    loadExcludedDates();
}

export async function deleteExcludedDate(id) {
    await api(`/api/excluded-dates/${id}`, { method: 'DELETE' });
    loadExcludedDates();
}
