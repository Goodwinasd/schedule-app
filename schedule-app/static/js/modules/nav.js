import state from './state.js';
import { DAY_ORDER } from './config.js';
import { escapeHtml, toISODate, getMonday, addDays, getWeekNumber, formatChipRange, formatShortDate, populateSelectByName } from './utils.js';
import { api } from './api.js';
import { openModal, confirmModal, showKimiAlert } from './modal.js';
import { loadScheduleTable } from './schedule.js';
import { dispatchEvent, onEvent, SCHEDULE_UPDATED, DATA_MUTATED } from './events.js';

/** Кэш ответов /api/weeks-summary по ключу «url» (год + активные фильтры) */
let _summaryCache = {};

const ICON_CHEVRON_LEFT = '<svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" aria-hidden="true"><path d="M15 18l-6-6 6-6" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/></svg>';
const ICON_CHEVRON_RIGHT = '<svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" aria-hidden="true"><path d="M9 18l6-6-6-6" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/></svg>';

onEvent(SCHEDULE_UPDATED, () => { _summaryCache = {}; });

function _syncYearFromMonday() {
    if (state.currentMonday) state.currentYear = state.currentMonday.getFullYear();
}

function _summaryUrl() {
    const q = ['year=' + state.currentYear];
    if (state.currentScheduleType === 'group' && state.currentScheduleName) {
        q.push('group=' + encodeURIComponent(state.currentScheduleName));
    } else if (state.currentScheduleType === 'teacher' && state.currentScheduleId) {
        q.push('teacher_id=' + state.currentScheduleId);
    } else if (state.currentScheduleType === 'classroom' && state.currentScheduleId) {
        q.push('classroom_id=' + state.currentScheduleId);
    }
    return '/api/weeks-summary?' + q.join('&');
}

async function _fetchActiveMondays() {
    const url = _summaryUrl();
    if (_summaryCache[url] !== undefined) return _summaryCache[url];
    try {
        const data = await api(url);
        _summaryCache[url] = new Set((data && data.active_mondays) || []);
    } catch (e) {
        _summaryCache[url] = new Set();
    }
    return _summaryCache[url];
}

export function getWeeksList(year = state.currentYear) {
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

/** Подпись диапазона недели: на телефоне длинный текст («с 3 по 8 августа») не влезает в чип. */
function _chipRange(monday) {
    if (!window.matchMedia('(max-width: 768px)').matches) return formatChipRange(monday);
    const sat = addDays(monday, 5);
    const mon = ['янв', 'фев', 'мар', 'апр', 'мая', 'июн', 'июл', 'авг', 'сен', 'окт', 'ноя', 'дек'];
    const m1 = mon[monday.getMonth()], m2 = mon[sat.getMonth()];
    return m1 === m2
        ? `${monday.getDate()}–${sat.getDate()} ${m1}`
        : `${monday.getDate()} ${m1} – ${sat.getDate()} ${m2}`;
}

export async function renderCarousel() {
    const cont = document.getElementById('week-carousel');
    if (!cont) return;
    _syncYearFromMonday();
    const year = state.currentYear;
    const weeks = getWeeksList(year);
    const sel = toISODate(state.currentMonday);
    const today = toISODate(getMonday(new Date()));
    const idx = weeks.findIndex(w => w.date === sel);
    const cy = new Date().getFullYear();
    let maxYear = parseInt(localStorage.getItem('schedule_max_year'), 10);
    if (!maxYear || maxYear < cy - 1) maxYear = cy + 1;
    maxYear = Math.min(maxYear, cy + 25);
    const years = [];
    for (let y = cy - 1; y <= maxYear; y++) years.push(y);
    if (!years.includes(year)) years.push(year);
    years.sort((a, b) => a - b);

    let html = '<div class="carousel-nav">';
    html += `<button class="carousel-arrow carousel-arrow-left${idx <= 0 ? ' disabled' : ''}" id="carousel-arrow-left" onclick="carouselSkip(-1)" title="← предыдущая неделя" aria-label="Предыдущая неделя">${ICON_CHEVRON_LEFT}</button>`;
    html += '<div class="carousel-strip" id="carousel-strip">';
    for (const w of weeks) {
        const cls = w.date === sel ? ' carousel-chip active' : w.date === today ? ' carousel-chip today' : ' carousel-chip';
        const nowCls = w.date === today ? ' current-week' : '';
        html += `<div class="${cls}${nowCls}" data-date="${w.date}" onclick="selectWeekByDate('${w.date}')"><span class="chip-week">${w.weekNumber} неделя</span><span class="chip-range">${_chipRange(w.monday)}</span><span class="chip-indicator" data-week="${w.date}">○ Пустая</span></div>`;
    }
    html += '</div>';
    html += `<button class="carousel-arrow carousel-arrow-right${idx >= weeks.length - 1 ? ' disabled' : ''}" id="carousel-arrow-right" onclick="carouselSkip(1)" title="следующая неделя →" aria-label="Следующая неделя">${ICON_CHEVRON_RIGHT}</button>`;
    html += `<select id="carousel-year" class="carousel-year" onchange="setYear(this.value)" title="Год">`;
    for (const y of years) html += `<option value="${y}"${y === year ? ' selected' : ''}>${y}</option>`;
    html += '<option value="add_year">+ Добавить год</option>';
    if (year > cy + 1) html += `<option value="delete_year">🗑️ Удалить текущий год (${year})</option>`;
    html += '</select>';
    html += `<button class="btn btn-ghost btn-sm btn-today" onclick="goToCurrentWeek()" title="Перейти к текущей неделе">📅 Сегодня</button>`;
    html += '</div>';
    cont.innerHTML = html;

    const active = await _fetchActiveMondays();
    if (state.currentYear !== year) return;
    const strip = document.getElementById('carousel-strip');
    if (!strip) return;
    strip.querySelectorAll('.chip-indicator').forEach(el => {
        const filled = active.has(el.dataset.week);
        el.textContent = filled ? '● Заполнена' : '○ Пустая';
        el.classList.toggle('filled', filled);
    });
    _scrollActiveChipIntoView();
}

export function setActiveWeek() {
    const strip = document.getElementById('carousel-strip');
    if (!strip) return;
    const sel = toISODate(state.currentMonday);
    strip.querySelectorAll('.carousel-chip').forEach(c => c.classList.toggle('active', c.dataset.date === sel));
    const weeks = getWeeksList(state.currentYear);
    const idx = weeks.findIndex(w => w.date === sel);
    ['carousel-arrow-left', 'carousel-arrow-right'].forEach((id, i) => {
        const el = document.getElementById(id);
        if (el) el.classList.toggle('disabled', i === 0 ? idx <= 0 : idx >= weeks.length - 1);
    });
    _scrollActiveChipIntoView();
}

/** Метрики карусели: сколько целых карточек помещается в видимую область. */
function _carouselMetrics() {
    const strip = document.getElementById('carousel-strip');
    const chip = strip && strip.querySelector('.carousel-chip');
    if (!strip || !chip) return { perView: 8 };
    const gap = 8;
    const step = chip.offsetWidth + gap;
    const perView = Math.max(1, Math.floor((strip.clientWidth + gap) / step));
    return { perView };
}

/** Прокрутка строго по границам целых карточек, чтобы не было «срезанных» недель. */
function _scrollActiveChipIntoView() {
    const strip = document.getElementById('carousel-strip');
    if (!strip) return;
    const chips = Array.from(strip.querySelectorAll('.carousel-chip'));
    const idx = chips.findIndex(c => c.classList.contains('active'));
    if (idx < 0) return;
    const { perView } = _carouselMetrics();
    const pageStart = Math.floor(idx / perView) * perView;
    const targetChip = chips[pageStart];
    if (!targetChip) return;
    const target = targetChip.offsetLeft;
    if (Math.abs(strip.scrollLeft - target) > 2) {
        strip.scrollTo({ left: target, behavior: 'smooth' });
    }
}

export function selectWeekByDate(dateStr) {
    state.currentMonday = new Date(dateStr + 'T00:00:00');
    _syncYearFromMonday();
    setActiveWeek();
    loadScheduleTable();
}

export function carouselSkip(n) {
    const weeks = getWeeksList(state.currentYear);
    const sel = toISODate(state.currentMonday);
    let idx = weeks.findIndex(w => w.date === sel);
    if (idx === -1) {
        state.currentMonday = new Date((n > 0 ? weeks[0] : weeks[weeks.length - 1]).date + 'T00:00:00');
        setActiveWeek();
        loadScheduleTable();
        return;
    }
    // Прокрутка строго на целую «страницу» карточек (без срезанных недель)
    const step = _carouselMetrics().perView;
    idx += step * n;
    if (idx < 0) {
        state.currentYear -= 1;
        const w2 = getWeeksList(state.currentYear);
        state.currentMonday = new Date(w2[w2.length - 1].date + 'T00:00:00');
        renderCarousel();
    } else if (idx >= weeks.length) {
        state.currentYear += 1;
        const w2 = getWeeksList(state.currentYear);
        state.currentMonday = new Date(w2[0].date + 'T00:00:00');
        renderCarousel();
    } else {
        state.currentMonday = addDays(state.currentMonday, step * n * 7);
        setActiveWeek();
    }
    loadScheduleTable();
}

function showConfirmModal(title, message, confirmText = 'Удалить', isDanger = true) {
    return window.showConfirmModal(title, message, confirmText, isDanger);
}

export async function setYear(value) {
    if (value === 'delete_year') {
        const cy = new Date().getFullYear();
        if (state.currentYear <= cy + 1) {
            alert('Базовый системный год нельзя удалить.');
            const sel = document.getElementById('carousel-year');
            if (sel) sel.value = String(state.currentYear);
            return;
        }
        const year = state.currentYear;
        let data;
        try {
            data = await api(`/api/weeks-summary?year=${year}`);
        } catch (e) {
            const sel = document.getElementById('carousel-year');
            if (sel) sel.value = String(state.currentYear);
            return;
        }
        const active = (data && data.active_mondays) || [];
        const sel = document.getElementById('carousel-year');
        if (active.length > 0) {
            alert(`Нельзя удалить ${year} год, так как в нём есть расписание! Сначала очистите все недели этого года.`);
            if (sel) sel.value = String(state.currentYear);
            return;
        }
        const confirmed = await showConfirmModal(
            `Удаление года (${year})`,
            `Вы действительно хотите удалить пустой ${year} год из списка?`,
            'Удалить',
            true
        );
        if (!confirmed) {
            if (sel) sel.value = String(state.currentYear);
            return;
        }
        localStorage.setItem('schedule_max_year', String(year - 1));
        _summaryCache = {};
        state.currentYear = year - 1;
        const weeks = getWeeksList(state.currentYear);
        if (weeks.length) state.currentMonday = new Date(weeks[0].date + 'T00:00:00');
        renderCarousel();
        loadScheduleTable();
        return;
    }
    if (value === 'add_year') {
        const cy = new Date().getFullYear();
        const maxYear = parseInt(localStorage.getItem('schedule_max_year'), 10) || (cy + 1);
        const newYear = maxYear + 1;
        localStorage.setItem('schedule_max_year', String(newYear));
        state.currentYear = newYear;
        const weeks = getWeeksList(newYear);
        if (weeks.length) state.currentMonday = new Date(weeks[0].date + 'T00:00:00');
        renderCarousel();
        loadScheduleTable();
        return;
    }
    const year = parseInt(value, 10);
    if (!year || year === state.currentYear) return;
    state.currentYear = year;
    const weeks = getWeeksList(year);
    const cur = toISODate(state.currentMonday);
    if (!weeks.some(w => w.date === cur) && weeks.length) {
        state.currentMonday = new Date(weeks[0].date + 'T00:00:00');
    }
    renderCarousel();
    loadScheduleTable();
}

export function goToCurrentWeek() {
    const today = getMonday(new Date());
    state.currentMonday = today;
    state.currentYear = today.getFullYear();
    renderCarousel();
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
    const dateInput = document.getElementById('week-start-date');
    dateInput.value = toISODate(state.currentMonday || getMonday(new Date()));
    // DOMContentLoaded здесь никогда не срабатывал (страница уже загружена), поэтому превью не обновлялось.
    // onchange перезаписываем, чтобы повторные открытия модалки не копили слушатели.
    dateInput.onchange = updateWeekPreview;
    updateWeekPreview();
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
    // Для группы — строго изолированный по group_id эндпоинт
    if (state.currentScheduleType === 'group') {
        const gid = parseInt(state.currentScheduleId, 10);
        if (!Number.isInteger(gid) || gid <= 0) { await showKimiAlert('Ошибка: не выбрана группа'); return; }
        console.log('[restore-week] url:', `/api/schedule/restore-week?start_date=${m}&group_id=${gid}`);
        const res = await api('/api/schedule/restore-week?start_date=' + m + '&group_id=' + gid, { method: 'POST' });
        if (res.error) { await showKimiAlert(res.error); return; }
        await showKimiAlert('Неделя успешно восстановлена. Восстановлено занятий (пар): ' + res.restored_count);
        dispatchEvent(SCHEDULE_UPDATED);
        loadScheduleTable();
        return;
    }
    const params = _weekTargetParams();
    if (!params) { await showKimiAlert('Сначала откройте расписание'); return; }
    const res = await api('/api/week/restore?monday=' + m + params, { method: 'POST' });
    if (res.error) { await showKimiAlert(res.error); return; }
    await showKimiAlert('Неделя успешно восстановлена. Восстановлено занятий (пар): ' + (res.pairs_restored ?? res.days_restored));
    dispatchEvent(SCHEDULE_UPDATED);
    loadScheduleTable();
}

export async function deleteWeek() {
    if (!state.currentMonday) return;
    if (!await confirmModal('Удалить все дни и пары за эту неделю?')) return;
    const m = toISODate(state.currentMonday);
    // Для группы используем строго изолированный по group_id эндпоинт
    if (state.currentScheduleType === 'group') {
        const gid = parseInt(state.currentScheduleId, 10);
        if (!Number.isInteger(gid) || gid <= 0) { await showKimiAlert('Ошибка: не выбрана группа'); return; }
        console.log('[clear-week] url:', `/api/schedule/clear-week?start_date=${m}&group_id=${gid}`);
        const res = await api('/api/schedule/clear-week?start_date=' + m + '&group_id=' + gid, { method: 'DELETE' });
        if (res.error) { await showKimiAlert(res.error); return; }
        await showKimiAlert('Неделя очищена. Удалено занятий (пар): ' + res.deleted_count);
        // clear-week не сопоставлен в api.js, поэтому событие шлём вручную —
        // иначе метка «● Заполнена» в карусели остаётся старой.
        dispatchEvent(DATA_MUTATED, { action: 'delete' });
        // На DATA_MUTATED карусель никто не перерисовывает: сбрасываем кэш сводки и обновляем метку сами.
        _summaryCache = {};
        renderCarousel();
        loadScheduleTable();
        return;
    }
    const params = _weekTargetParams();
    if (!params) { await showKimiAlert('Сначала откройте расписание'); return; }
    const res = await api('/api/week?monday=' + m + params, { method: 'DELETE' });
    if (res.error) { await showKimiAlert(res.error); return; }
    await showKimiAlert('Неделя очищена. Удалено занятий (пар): ' + (res.pairs_deleted ?? res.days_deleted));
    loadScheduleTable();
}
