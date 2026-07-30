import state from './state.js';
import { DAY_ORDER } from './config.js';
import { escapeHtml, toISODate, getMonday, addDays, getWeekNumber, formatChipRange, formatShortDate, populateSelectByName } from './utils.js';
import { api } from './api.js';
import { openModal, confirmModal, showKimiAlert } from './modal.js';
import { loadScheduleTable } from './schedule.js';
import { dispatchEvent, SCHEDULE_UPDATED } from './events.js';

export function getWeeksList() {
    const now = new Date(), year = now.getFullYear();
    const fm = getMonday(new Date(year, 0, 1));
    const weeks = [];
    for (let i = 0; i < 54; i++) {
        const mon = addDays(fm, i * 7);
        if (mon.getFullYear() > year) break;
        if (mon.getFullYear() < year) continue;
        weeks.push({ date: toISODate(mon), monday: mon, weekNumber: getWeekNumber(mon) });
    }
    return weeks;
}

export function renderCarousel() {
    const cont = document.getElementById('week-carousel');
    const weeks = getWeeksList();
    const sel = toISODate(state.currentMonday);
    const today = toISODate(getMonday(new Date()));
    const idx = weeks.findIndex(w => w.date === sel);
    let html = '<div class="carousel-nav">';
    html += `<button class="carousel-arrow carousel-arrow-left${idx <= 0 ? ' disabled' : ''}" id="carousel-arrow-left" onclick="carouselSkip(-1)" title="← предыдущая неделя">«</button>`;
    html += '<div class="carousel-strip" id="carousel-strip">';
    for (const w of weeks) {
        const cls = w.date === sel ? ' carousel-chip active' : w.date === today ? ' carousel-chip today' : ' carousel-chip';
        html += `<div class="${cls}" data-date="${w.date}" onclick="selectWeekByDate('${w.date}')"><span class="chip-week">${w.weekNumber} неделя</span><span class="chip-range">${formatChipRange(w.monday)}</span></div>`;
    }
    html += '</div>';
    html += `<button class="carousel-arrow carousel-arrow-right${idx >= weeks.length - 1 ? ' disabled' : ''}" id="carousel-arrow-right" onclick="carouselSkip(1)" title="следующая неделя →">»</button></div>`;
    cont.innerHTML = html;
}

export function setActiveWeek() {
    const strip = document.getElementById('carousel-strip');
    if (!strip) return;
    const sel = toISODate(state.currentMonday);
    strip.querySelectorAll('.carousel-chip').forEach(c => c.classList.toggle('active', c.dataset.date === sel));
    const active = strip.querySelector('.carousel-chip.active');
    if (active) {
        const sr = strip.getBoundingClientRect(), cr = active.getBoundingClientRect();
        strip.scrollBy({ left: cr.left - sr.left - sr.width / 2 + cr.width / 2, behavior: 'smooth' });
    }
    const weeks = getWeeksList();
    const idx = weeks.findIndex(w => w.date === sel);
    ['carousel-arrow-left', 'carousel-arrow-right'].forEach((id, i) => {
        const el = document.getElementById(id);
        if (el) el.classList.toggle('disabled', i === 0 ? idx <= 0 : idx >= weeks.length - 1);
    });
}

export function selectWeekByDate(dateStr) {
    state.currentMonday = new Date(dateStr + 'T00:00:00');
    setActiveWeek();
    loadScheduleTable();
}

export function carouselSkip(n) {
    state.currentMonday = addDays(state.currentMonday, n * 7);
    setActiveWeek();
    loadScheduleTable();
}

export function showAddWeekModal() {
    openModal('add-week-modal');
    populateSelectByName('week-group', state.groupsList, '— выбрать группу —');
    const sel = document.getElementById('week-group');
    if (state.currentScheduleType === 'group' && state.currentScheduleName) {
        sel.value = state.currentScheduleName;
        sel.disabled = true;
    } else {
        sel.disabled = false;
    }
    document.getElementById('week-start-date').value = toISODate(state.currentMonday || getMonday(new Date()));
    updateWeekPreview();
    document.addEventListener('DOMContentLoaded', () => {
        const di = document.getElementById('week-start-date');
        if (di) di.addEventListener('change', updateWeekPreview);
    });
}

export function updateWeekPreview() {
    const ds = document.getElementById('week-start-date').value;
    if (!ds) return;
    const monday = new Date(ds + 'T00:00:00');
    document.getElementById('week-preview').innerHTML = DAY_ORDER.map((n, i) => {
        const d = addDays(monday, i);
        return `<div class="week-preview-day"><span>${n}</span><span>${formatShortDate(toISODate(d))}</span></div>`;
    }).join('');
}

export async function addWeek() {
    const gn = document.getElementById('week-group').value;
    const ds = document.getElementById('week-start-date').value;
    if (!ds) { await showKimiAlert('Выберите дату понедельника'); return; }
    if (!gn) { await showKimiAlert('Выберите группу'); return; }
    const monday = new Date(ds + 'T00:00:00');
    const days = DAY_ORDER.map((n, i) => ({ day_name: n, date: toISODate(addDays(monday, i)), group_name: gn }));
    const check = await api('/api/validate-week', { method: 'POST', body: JSON.stringify({ group_name: gn, dates: days.map(d => d.date) }) });
    if (!check.ok) { await showKimiAlert(check.warnings.map(w => w.message).join('\n')); return; }
    const res = await api('/api/days/batch', { method: 'POST', body: JSON.stringify({ days }) });
    if (res.error) { await showKimiAlert(res.error); return; }
    window.closeModals();
    dispatchEvent(SCHEDULE_UPDATED);
    loadScheduleTable();
}

function _weekTargetParams() {
    if (!state.currentScheduleType || !state.currentScheduleId) return '';
    if (state.currentScheduleType === 'group') {
        return '&target_type=group&target_id=' + encodeURIComponent(state.currentScheduleName);
    } else if (state.currentScheduleType === 'teacher') {
        return '&target_type=teacher&target_id=' + state.currentScheduleId;
    } else if (state.currentScheduleType === 'classroom') {
        return '&target_type=classroom&target_id=' + state.currentScheduleId;
    }
    return '';
}

export async function restoreWeek() {
    if (!state.currentMonday) return;
    if (!await confirmModal('Восстановить все удаленные дни и пары за эту неделю?')) return;
    const m = toISODate(state.currentMonday);
    const params = _weekTargetParams();
    if (!params) { await showKimiAlert('Сначала откройте расписание'); return; }
    const res = await api('/api/week/restore?monday=' + m + params, { method: 'POST' });
    if (res.error) { await showKimiAlert(res.error); return; }
    await showKimiAlert('Восстановлено дней: ' + res.days_restored);
    dispatchEvent(SCHEDULE_UPDATED);
    loadScheduleTable();
}

export async function deleteWeek() {
    if (!state.currentMonday) return;
    if (!await confirmModal('Удалить все дни и пары за эту неделю?')) return;
    const m = toISODate(state.currentMonday);
    const params = _weekTargetParams();
    if (!params) { await showKimiAlert('Сначала откройте расписание'); return; }
    const res = await api('/api/week?monday=' + m + params, { method: 'DELETE' });
    if (res.error) { await showKimiAlert(res.error); return; }
    await showKimiAlert('Удалено дней: ' + res.days_deleted);
    loadScheduleTable();
}
