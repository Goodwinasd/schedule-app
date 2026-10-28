import { api } from './api.js';
import { escapeHtml } from './utils.js';
import { showKimiAlert, confirmModal } from './modal.js';
import { showToast } from './toast.js';
import { showLoader, hideLoader } from './loader.js';
import { dispatchEvent, HOLIDAYS_UPDATED, DATA_MUTATED } from './events.js';
import state from './state.js';
import { refreshScheduleTimeline } from './schedule.js';

let _bellPresets = [];

function toTimeInput(t) {
    if (!t) return '';
    const [h, m] = String(t).split(':');
    return `${(h || '').padStart(2, '0')}:${(m || '00')}`;
}

export async function loadBellScheduleTab() {
    const cont = document.getElementById('bell-schedule-content');
    if (!cont) return;
    const data = await api('/api/admin/bell-schedule', { silent: true });
    if (data.error) { cont.innerHTML = '<div style="color:var(--danger)">Ошибка загрузки расписания звонков</div>'; return; }
    const schedule = Array.isArray(data.schedule) ? data.schedule : [];
    _bellPresets = Array.isArray(data.presets) ? data.presets : [];
    const byPeriod = {};
    for (const s of schedule) byPeriod[s.period] = s;
    let html = '<div style="margin:12px 0"><strong style="font-size:14px">Расписание звонков</strong></div>';
    html += '<div style="font-size:11px;color:var(--text-secondary);margin-bottom:8px">Схема звонков для всех смен. Изменения применяются к сетке расписания после сохранения.</div>';
    html += '<div class="field-row" style="margin-bottom:10px">';
    html += '<label style="font-size:12px;color:var(--text-secondary)">Применить пресет:</label>';
    html += '<select id="bell-preset-select" class="input" style="max-width:280px"><option value="">— выберите пресет —</option>';
    for (const p of _bellPresets) html += `<option value="${escapeHtml(p.id)}">${escapeHtml(p.name)}</option>`;
    html += '</select>';
    html += '<button class="btn btn-ghost btn-sm" data-action="applyBellPreset">Применить</button>';
    html += '</div>';
    html += '<table class="bell-schedule-table" style="border-collapse:collapse;width:100%;max-width:560px;font-size:13px">';
    html += '<thead><tr>';
    html += '<th style="text-align:left;padding:6px 8px;border-bottom:1px solid var(--border)">Пара</th>';
    html += '<th style="text-align:left;padding:6px 8px;border-bottom:1px solid var(--border)">Смена</th>';
    html += '<th style="text-align:left;padding:6px 8px;border-bottom:1px solid var(--border)">Время начала</th>';
    html += '<th style="text-align:left;padding:6px 8px;border-bottom:1px solid var(--border)">Время окончания</th>';
    html += '</tr></thead><tbody>';
    for (let p = 1; p <= 8; p++) {
        const s = byPeriod[p] || {};
        html += `<tr><td style="padding:6px 8px;border-bottom:1px solid var(--border)">${p}-я пара</td>`;
        html += `<td style="padding:6px 8px;border-bottom:1px solid var(--border)"><input type="number" min="1" max="3" class="input bell-shift" data-period="${p}" value="${s.shift || 1}" style="max-width:70px"></td>`;
        html += `<td style="padding:6px 8px;border-bottom:1px solid var(--border)"><input type="time" class="input bell-start" data-period="${p}" value="${toTimeInput(s.start)}" style="max-width:120px"></td>`;
        html += `<td style="padding:6px 8px;border-bottom:1px solid var(--border)"><input type="time" class="input bell-end" data-period="${p}" value="${toTimeInput(s.end)}" style="max-width:120px"></td></tr>`;
    }
    html += '</tbody></table>';
    html += '<div class="field-row" style="margin-top:10px"><button class="btn btn-primary btn-sm" data-action="saveBellSchedule">Сохранить расписание звонков</button></div>';
    cont.innerHTML = html;
}

export function applyBellPreset() {
    const sel = document.getElementById('bell-preset-select');
    if (!sel || !sel.value) return;
    const preset = _bellPresets.find(p => p.id === sel.value);
    if (!preset) return;
    for (const s of preset.schedule) {
        const start = document.querySelector(`.bell-start[data-period="${s.period}"]`);
        const end = document.querySelector(`.bell-end[data-period="${s.period}"]`);
        const shift = document.querySelector(`.bell-shift[data-period="${s.period}"]`);
        if (start) start.value = toTimeInput(s.start);
        if (end) end.value = toTimeInput(s.end);
        if (shift) shift.value = s.shift;
    }
}

export async function saveBellSchedule() {
    const starts = document.querySelectorAll('#bell-schedule-content .bell-start');
    if (!starts.length) return;
    const schedule = [];
    for (const inp of starts) {
        const p = parseInt(inp.dataset.period);
        const end = document.querySelector(`.bell-end[data-period="${p}"]`);
        const shift = document.querySelector(`.bell-shift[data-period="${p}"]`);
        schedule.push({ period: p, start: inp.value, end: end ? end.value : '', shift: shift ? parseInt(shift.value) || 1 : 1 });
    }
    const res = await api('/api/admin/bell-schedule', { method: 'PUT', body: JSON.stringify({ schedule }), silent: true });
    if (res.error) { await showKimiAlert(res.error); return; }
    state.bellSchedule = Array.isArray(res.schedule) ? res.schedule : [];
    refreshScheduleTimeline();
    showToast('Расписание звонков сохранено', 'success');
}

export async function loadSettingsTab() {
    showLoader('Настройки');
    const cont = document.getElementById('settings-content');
    cont.innerHTML = '';
    const data = await api('/api/settings');
    hideLoader();
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
    cont.insertAdjacentHTML('beforeend', `
<hr style="margin:20px 0;border:none;border-top:1px solid var(--border)">
<div style="margin:12px 0"><strong style="font-size:14px">Резервное копирование и Восстановление</strong></div>
<div class="field-row" style="margin-bottom:8px">
    <button class="btn btn-primary btn-sm" data-action="downloadBackup">Скачать резервную копию БД</button>
</div>
<div class="field-row" style="margin-bottom:8px">
    <input type="file" id="restore-file-input" accept=".sqlite,.db" style="font-size:13px">
    <button class="btn btn-primary btn-sm" data-action="restoreBackup">Восстановить БД из файла</button>
</div>
<div class="field-row">
    <button class="btn btn-primary btn-sm" data-action="checkOrphans">Проверить целостность БД</button>
</div>
<div id="orphan-result" style="margin-top:8px;font-size:13px"></div>
    `);
}

export async function saveSetting(key) {
    const inp = document.getElementById(`settings-${key}`);
    if (!inp) return;
    const val = inp.value.trim();
    const res = await api(`/api/settings/${key}`, { method: 'PUT', body: JSON.stringify({ value: val }), silent: true });
    if (res.error) { await showKimiAlert(res.error); return; }
    showToast('Сохранено', 'success');
    loadSettingsTab();
}

export async function loadExcludedDates() {
    const cont = document.getElementById('excluded-dates-content');
    if (!cont) return;
    showLoader('Исключённые даты');
    cont.innerHTML = '';
    const data = await api('/api/excluded-dates');
    hideLoader();
    if (data.error) { cont.innerHTML = '<div style="color:var(--danger)">Ошибка загрузки</div>'; return; }
    let html = '<div style="margin:12px 0"><strong style="font-size:14px">Исключённые даты</strong></div>';
    if (!data.length) {
        html += '<div style="font-size:13px;color:var(--text-secondary);padding:8px 0">Нет исключённых дат</div>';
    } else {
        html += '<div style="display:flex;flex-direction:column;gap:4px">';
        for (const d of data) {
            const label = d.start_date === d.end_date ? d.start_date : `${d.start_date} – ${d.end_date}`;
            html += `<div class="ref-item"><span class="ref-item-name">${escapeHtml(label)}${d.reason ? ' <span style="color:var(--text-secondary)">— ' + escapeHtml(d.reason) + '</span>' : ''}</span>`;
            html += `<div class="ref-item-actions"><button class="btn btn-danger btn-icon btn-sm" data-action="deleteExcludedDate" data-params='[${d.id}]' aria-label="Удалить исключение">×</button></div></div>`;
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
    dispatchEvent(HOLIDAYS_UPDATED);
    loadExcludedDates();
}

export async function deleteExcludedDate(id) {
    await api(`/api/excluded-dates/${id}`, { method: 'DELETE' });
    dispatchEvent(HOLIDAYS_UPDATED);
    loadExcludedDates();
}


export async function downloadBackup() {
    const a = document.createElement('a');
    a.href = '/api/admin/backup/download';
    a.download = '';
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
}


export async function restoreBackup() {
    const fileInput = document.getElementById('restore-file-input');
    if (!fileInput || !fileInput.files || !fileInput.files[0]) {
        await showKimiAlert('Выберите .sqlite или .db файл для восстановления');
        return;
    }
    const file = fileInput.files[0];
    const confirmed = await confirmModal('Восстановление БД из файла заменит все текущие данные. Продолжить?');
    if (!confirmed) return;
    const formData = new FormData();
    formData.append('file', file);
    const res = await fetch('/api/admin/backup/restore', {
        method: 'POST',
        headers: { 'X-CSRF-Token': state.csrfToken || '' },
        body: formData
    });
    const data = await res.json();
    if (data.error) { await showKimiAlert(data.error); return; }
    showToast('База данных восстановлена. Перезагрузка...', 'success');
    fileInput.value = '';
    dispatchEvent(DATA_MUTATED, { action: 'restore' });
    setTimeout(() => window.location.reload(), 1500);
}


export async function checkOrphans() {
    const resultDiv = document.getElementById('orphan-result');
    resultDiv.innerHTML = 'Проверка...';
    const data = await api('/api/admin/db/check-orphans');
    if (data.error) { resultDiv.innerHTML = `<span style="color:var(--danger)">Ошибка: ${escapeHtml(data.error)}</span>`; return; }
    if (data.found === 0) {
        resultDiv.innerHTML = '<span style="color:var(--success)">Сиротские записи не найдены. База данных в порядке.</span>';
        return;
    }
    const detailLessons = data.lessons && data.lessons.length
        ? `<div style="margin-top:4px">Уроков: ${data.lessons.length}</div>`
        : '';
    const detailCurriculum = data.curriculum && data.curriculum.length
        ? `<div style="margin-top:4px">Учебных планов: ${data.curriculum.length}</div>`
        : '';
    resultDiv.innerHTML = `
<div style="color:var(--warning-text)">
    <strong>Найдено ${data.found} устаревших записей.</strong>
    ${detailLessons}${detailCurriculum}
</div>
<div class="field-row" style="margin-top:8px">
    <button class="btn btn-danger btn-sm" data-action="confirmDeleteOrphans">Удалить их</button>
    <button class="btn btn-ghost btn-sm" data-action="clearOrphanResult">Отмена</button>
</div>`;
}


export async function confirmDeleteOrphans() {
    const confirmed = await confirmModal('Удалить все найденные сиротские записи? Это действие необратимо.');
    if (!confirmed) return;
    const res = await api('/api/admin/db/check-orphans', { method: 'POST', body: JSON.stringify({ force: true }) });
    const resultDiv = document.getElementById('orphan-result');
    if (res.error) { resultDiv.innerHTML = `<span style="color:var(--danger)">Ошибка: ${escapeHtml(res.error)}</span>`; return; }
    resultDiv.innerHTML = `<span style="color:var(--success)">Удалено ${res.deleted} сиротских записей.</span>`;
}


export async function clearOrphanResult() {
    const resultDiv = document.getElementById('orphan-result');
    if (resultDiv) resultDiv.innerHTML = '';
}
