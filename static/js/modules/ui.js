import state from './state.js';
import { DAY_ORDER } from './config.js';
import { escapeHtml, getMonday, addDays, toISODate, getWeekNumber, formatChipRange, formatDateRange, shiftLabel, populateSelect, populateSelectByName } from './utils.js';
import { api } from './api.js';
import { openModal, confirmModal, _confirmState } from './modal.js';
import { showToast } from './toast.js';
import { loadReferences, renderRefList, addGroup, editGroup, addSubject, editSubject, editTeacher, editClassroom, advanceCourses, addRefItem, deleteRefItem, restoreRefItem, quickAdd, quickAddGroup, populateSubjectTeacherSelect } from './references.js';
import { loadScheduleTable, printSchedule, exportSchedule, showAddLessonModal, addLesson, editLesson, saveLesson, addSubgroupLesson, deleteCurrentLesson, validateLesson } from './schedule.js';
import { loadTrashTab, restoreTrashItem, purgeTrash } from './trash.js';
import { loadSettingsTab, saveSetting } from './settings.js';
import { renderCarousel, setActiveWeek, selectWeekByDate, carouselSkip, showAddWeekModal, updateWeekPreview, addWeek, restoreWeek, deleteWeek, getWeeksList } from './nav.js';

/* ======================== Navigation ======================== */

export function updateUI() {
    const g = id => document.getElementById(id);
    g('btn-login').style.display = state.isAdmin ? 'none' : '';
    g('btn-logout').style.display = state.isAdmin ? '' : 'none';
    g('btn-admin').style.display = state.isAdmin ? '' : 'none';
    g('btn-avail').style.display = state.isAdmin ? '' : 'none';
    g('admin-panel').style.display = (state.isAdmin && state.currentScheduleType) ? '' : 'none';
    g('print-panel').style.display = state.currentScheduleType ? '' : 'none';
    const cb = g('btn-toggle-conflicts');
    if (cb) cb.style.display = state.isAdmin && state.currentScheduleType ? '' : 'none';
}

export function toggleConflicts() {
    state.showConflicts = !state.showConflicts;
    const cb = document.getElementById('btn-toggle-conflicts');
    if (cb) cb.textContent = state.showConflicts ? '✔ Конфликты' : 'Конфликты';
    loadScheduleTable();
}
window._onUnauthorized = updateUI;

export function goHome() {
    state.currentScheduleType = '';
    state.currentScheduleId = state.currentScheduleName = null;
    state.currentMonday = null;
    ['home-view', 'schedule-view', 'availability-view'].forEach(v => document.getElementById(v).style.display = v === 'home-view' ? '' : 'none');
    document.getElementById('header-title').textContent = 'Расписание';
    updateUI();
    loadHomePage();
}

export function showSchedule(type, id, name) {
    state.currentScheduleType = type;
    state.currentScheduleId = id;
    state.currentScheduleName = name;
    state.currentMonday = getMonday(new Date());
    ['home-view', 'schedule-view', 'availability-view'].forEach(v => document.getElementById(v).style.display = v === 'schedule-view' ? '' : 'none');
    document.getElementById('header-title').textContent = '\u2190 ' + name;
    updateUI();
    renderCarousel();
    loadScheduleTable();
}

export function closeModals() {
    document.getElementById('modal-overlay').classList.remove('active');
    document.querySelectorAll('.modal').forEach(m => m.style.display = 'none');
    if (typeof resetLessonModal === 'function') resetLessonModal();
    if (_confirmState.resolver) { const r = _confirmState.resolver; _confirmState.resolver = null; r(false); }
}

function resetLessonModal() {
    state.currentEditLessonId = null;
    state.currentLessonDate = null;
    document.querySelector('#add-lesson-modal h2').textContent = 'Новый пара';
    const btn = document.getElementById('btn-save-lesson');
    btn.textContent = 'Добавить'; btn.disabled = false; btn.onclick = () => addLesson();
    document.getElementById('validation-warnings').style.display = 'none';
    document.getElementById('btn-delete-lesson').style.display = 'none';
    document.getElementById('btn-add-subgroup').style.display = 'none';
    document.getElementById('lesson-teacher').disabled = false;
}

export function showLoginModal() {
    openModal('login-modal');
    const p = document.getElementById('login-password');
    p.value = '';
    p.focus();
}

/* ======================== Homepage & References ======================== */

export function renderHomePage() {
    const reg = state.groupsList.filter(g => !g.is_distance);
    const dist = state.groupsList.filter(g => g.is_distance);
    const gc = document.getElementById('groups-grid');
    if (!reg.length && !dist.length) { gc.innerHTML = '<div class="empty-grid">Нет групп. Добавьте через справочники.</div>'; }
    else {
        let html = '';
        for (let c = 1; c <= 4; c++) {
            const cg = reg.filter(g => g.course === c);
            if (!cg.length) continue;
            html += `<div class="course-subsection"><h3 class="course-subtitle">Курс ${c}</h3><div class="select-grid">${cg.map(g => makeCard('group', g.id, g.name, 'Расписание группы')).join('')}</div></div>`;
        }
        if (reg.length && !html) html = `<div class="select-grid">${reg.map(g => makeCard('group', g.id, g.name, 'Расписание группы')).join('')}</div>`;
        gc.innerHTML = html;
    }
    const dc = document.getElementById('distance-grid');
    if (dc) dc.innerHTML = dist.length ? `<div class="select-grid">${dist.map(g => makeCard('group', g.id, g.name, 'Расписание группы')).join('')}</div>` : '<div class="empty-grid">Нет заочных групп.</div>';
    document.getElementById('teachers-grid').innerHTML = state.teachersWithSchedule.length ? state.teachersWithSchedule.map(t => makeCard('teacher', t.id, t.name, 'Расписание преподавателя')).join('') : '<div class="empty-grid">Нет преподавателей.</div>';
    document.getElementById('classrooms-grid').innerHTML = state.classroomsWithSchedule.length ? state.classroomsWithSchedule.map(c => makeCard('classroom', c.id, c.name, 'Занятость', 'Ауд. ')).join('') : '<div class="empty-grid">Нет аудиторий.</div>';
}

function makeCard(type, id, name, subtitle, prefix = '') {
    const safe = escapeHtml(name).replace(/'/g, "&#39;");
    return `<div class="select-card" onclick="showSchedule('${type}', ${id}, '${safe}')"><div class="select-card-title">${prefix}${safe}</div><div class="select-card-subtitle">${subtitle}</div></div>`;
}

export function showAdminPanel() {
    openModal('references-modal');
    ['subjects', 'teachers', 'groups', 'classrooms'].forEach(e => renderRefList(e, `ref-${e}`));
    populateSubjectTeacherSelect();
    document.querySelectorAll('.admin-tab-content').forEach(c => c.classList.remove('active'));
    document.querySelectorAll('.admin-tab').forEach(t => t.classList.remove('active'));
    const first = document.querySelector('.admin-tab');
    if (first) first.classList.add('active');
    const firstContent = document.getElementById('admin-tab-refs');
    if (firstContent) firstContent.classList.add('active');
}

export function switchAdminTab(tab) {
    document.querySelectorAll('.admin-tab-content').forEach(c => c.classList.remove('active'));
    document.querySelectorAll('.admin-tab').forEach(t => t.classList.remove('active'));
    const tabBtn = document.querySelector(`.admin-tab[data-tab="${tab}"]`);
    if (tabBtn) tabBtn.classList.add('active');
    const content = document.getElementById(`admin-tab-${tab}`);
    if (content) content.classList.add('active');
    if (tab === 'trash') loadTrashTab();
    if (tab === 'system') { loadHealthTab(); loadSettingsTab(); }
}

async function loadHealthTab() {
    const cont = document.getElementById('db-health-content');
    cont.innerHTML = '<div class="loading">Загрузка...</div>';
    const data = await api('/api/db/health');
    if (data.error) { cont.innerHTML = '<div style="color:var(--danger)">Ошибка загрузки диагностики</div>'; return; }
    let html = `<div style="margin:8px 0;font-size:13px"><strong>Целостность БД:</strong> ${escapeHtml(data.integrity_check)}</div>`;
    html += '<table class="ref-table"><tr><th>Таблица</th><th>Всего</th><th>Удалено</th></tr>';
    for (const [t, info] of Object.entries(data.tables)) {
        html += `<tr><td>${t}</td><td>${info.total}</td><td>${info.deleted}</td></tr>`;
    }
    html += '</table>';
    if (data.conflicts && data.conflicts.length) {
        html += `<div style="margin:8px 0;color:#c62828"><strong>Конфликты (${data.conflicts.length}):</strong></div><table class="ref-table"><tr><th>ID1</th><th>ID2</th><th>Дата</th><th>Пара</th></tr>`;
        for (const c of data.conflicts) {
            html += `<tr><td>${c.id1}</td><td>${c.id2}</td><td>${c.date || ''}</td><td>${c.period}</td></tr>`;
        }
        html += '</table>';
    } else {
        html += '<div style="margin:8px 0;color:#2e7d32;font-size:13px">Конфликтов не найдено</div>';
    }
    if (data.orphaned_lessons && data.orphaned_lessons.length) {
        html += `<div style="margin:8px 0;color:#e65100"><strong>Сиротские пары (${data.orphaned_lessons.length}):</strong> ID: ${data.orphaned_lessons.map(l => l.id).join(', ')}</div>`;
    } else {
        html += '<div style="margin:8px 0;color:#2e7d32;font-size:13px">Сиротских пар нет</div>';
    }
    cont.innerHTML = html;
}

/* ======================== Auth ======================== */

export async function login() {
    const data = await api('/api/auth/login', { method: 'POST', body: JSON.stringify({ password: document.getElementById('login-password').value }) });
    if (data.success) { state.isAdmin = true; state.csrfToken = data.csrf_token || ''; closeModals(); updateUI(); }
    else alert('Неверный пароль');
}

export async function logout() {
    await api('/api/auth/logout', { method: 'POST' });
    state.isAdmin = false; state.csrfToken = '';
    updateUI();
}

/* ======================== Availability ======================== */

export async function showAvailability() {
    state.availMonday = getMonday(new Date());
    state.availGroupById = null;
    state.availHeatmap = false;
    state.availGroupByCourse = false;
    renderAvailCarousel();
    await loadAvailability();
    document.getElementById('home-view').style.display = 'none';
    document.getElementById('schedule-view').style.display = 'none';
    document.getElementById('availability-view').style.display = '';
    document.getElementById('header-title').textContent = '← Свободные окна';
    updateUI();
}

function renderAvailCarousel() {
    const cont = document.getElementById('avail-carousel');
    const weeks = getWeeksList();
    const sel = toISODate(state.availMonday);
    const today = toISODate(getMonday(new Date()));
    const idx = weeks.findIndex(w => w.date === sel);
    let html = '<div class="carousel-nav">';
    html += `<button class="carousel-arrow carousel-arrow-left${idx <= 0 ? ' disabled' : ''}" id="avail-arrow-left" data-action="availCarouselSkip" data-params="[-1]" title="← предыдущая неделя">«</button>`;
    html += '<div class="carousel-strip" id="avail-carousel-strip">';
    for (const w of weeks) {
        const cls = w.date === sel ? ' carousel-chip active' : w.date === today ? ' carousel-chip today' : ' carousel-chip';
        html += `<div class="${cls}" data-date="${w.date}" data-action="selectAvailWeek" data-params='["${w.date}"]'><span class="chip-week">${w.weekNumber} неделя</span><span class="chip-range">${formatChipRange(w.monday)}</span></div>`;
    }
    html += '</div>';
    html += `<button class="carousel-arrow carousel-arrow-right${idx >= weeks.length - 1 ? ' disabled' : ''}" id="avail-arrow-right" data-action="availCarouselSkip" data-params="[1]" title="следующая неделя →">»</button></div>`;
    cont.innerHTML = html;
}

function availSetActiveWeek() {
    const strip = document.getElementById('avail-carousel-strip');
    if (!strip) return;
    const sel = toISODate(state.availMonday);
    strip.querySelectorAll('.carousel-chip').forEach(c => c.classList.toggle('active', c.dataset.date === sel));
    const active = strip.querySelector('.carousel-chip.active');
    if (active) {
        const sr = strip.getBoundingClientRect(), cr = active.getBoundingClientRect();
        strip.scrollBy({ left: cr.left - sr.left - sr.width / 2 + cr.width / 2, behavior: 'smooth' });
    }
}

export async function selectAvailWeek(dateStr) {
    state.availMonday = new Date(dateStr + 'T00:00:00');
    state.availSelectedDay = null;
    availSetActiveWeek();
    await loadAvailability();
}

export async function availCarouselSkip(n) {
    state.availMonday = addDays(state.availMonday, n * 7);
    state.availSelectedDay = null;
    availSetActiveWeek();
    await loadAvailability();
}

function _availUrl() {
    let url = `/api/availability?monday=${toISODate(state.availMonday)}`;
    const gid = document.getElementById('avail-group-filter');
    if (gid && gid.value) url += `&group_id=${gid.value}`;
   	return url;
}

export async function loadAvailability() {
    state.availData = await api(_availUrl());
    if (state.availData.error) {
        showToast('Ошибка загрузки данных доступности', 'error');
        return;
    }
    _populateAvailGroups();
    renderAvailDayTabs();
    renderAvailTable();
}

function _populateAvailGroups() {
    const sel = document.getElementById('avail-group-filter');
    if (!sel || !state.availData.groups) return;
    const cur = sel.value;
    sel.innerHTML = '<option value="">Все группы</option>' + state.availData.groups.map(g => `<option value="${g.id}">${g.name}</option>`).join('');
    sel.value = cur;
}

function renderAvailDayTabs() {
    const cont = document.getElementById('avail-day-tabs');
    if (!state.availData) return;
    const todayStr = toISODate(new Date());
    let html = `<div class="avail-day-tab ${!state.availSelectedDay ? 'active' : ''}" data-action="selectAvailDay" data-params="[null]">Вся неделя</div>`;
    for (const d of state.availData.days) {
        const a = state.availSelectedDay === d.date ? ' active' : '';
        const t = d.date === todayStr ? ' today' : '';
        html += `<div class="avail-day-tab${a}${t}" data-action="selectAvailDay" data-params='["${d.date}"]'>${d.day_name}</div>`;
    }
    cont.innerHTML = html;
}

export function selectAvailDay(date) {
    state.availSelectedDay = date;
    renderAvailDayTabs();
    renderAvailTable();
}

export function setAvailMode(mode) {
    state.availMode = mode;
    document.getElementById('avail-mode-teacher').classList.toggle('active', mode === 'teacher');
    document.getElementById('avail-mode-classroom').classList.toggle('active', mode === 'classroom');
    renderAvailTable();
}

export function toggleAvailHeatmap() {
    if (!state.availData) { showToast('Сначала откройте раздел доступности', 'info'); return; }
    state.availHeatmap = !state.availHeatmap;
    document.getElementById('btn-avail-heatmap').classList.toggle('active', state.availHeatmap);
    renderAvailTable();
}

export function toggleAvailGroupByCourse() {
    if (!state.availData) { showToast('Сначала откройте раздел доступности', 'info'); return; }
    state.availGroupByCourse = !state.availGroupByCourse;
    document.getElementById('btn-avail-group-course').classList.toggle('active', state.availGroupByCourse);
    renderAvailTable();
}

export function exportAvailExcel() {
    showToast('Экспорт в Excel пока в разработке', 'info');
}

export function exportAvailPDF() {
    showToast('Экспорт в PDF пока в разработке', 'info');
}

export function closeAvailability() {
    document.getElementById('availability-view').style.display = 'none';
    document.getElementById('home-view').style.display = '';
    document.getElementById('header-title').textContent = 'Расписание';
    updateUI();
}

function _clickLesson(info, date, period) {
    if (!info || !info.teacher_id) return;
    const m = new Date(date + 'T00:00:00');
    const monday = getMonday(m);
    state.currentScheduleType = 'teacher';
    state.currentScheduleId = info.teacher_id;
    state.currentScheduleName = info.teacher;
    state.currentMonday = monday;
    document.getElementById('availability-view').style.display = 'none';
    document.getElementById('schedule-view').style.display = '';
    document.getElementById('header-title').textContent = '\u2190 ' + info.teacher;
    updateUI();
    renderCarousel();
    loadScheduleTable();
}

function renderAvailTable() {
    if (!state.availData) return;
    const cont = document.getElementById('avail-table-container');
    const freeOnly = document.getElementById('avail-free-only').checked;
    const showAll = document.getElementById('avail-show-all-periods').checked;
    const isHeatmap = state.availHeatmap;
    const groupByCourse = state.availGroupByCourse && state.availMode === 'teacher';
    const days = state.availSelectedDay ? state.availData.days.filter(d => d.date === state.availSelectedDay) : state.availData.days;
    const periods = showAll ? state.availData.periods : state.availData.periods.filter(p => p.period <= 6);
    const rows = state.availMode === 'teacher' ? state.availData.teachers : state.availData.classrooms;
    const busyMap = state.availMode === 'teacher' ? state.availData.teacher_busy : state.availData.classroom_busy;
    const todayStr = toISODate(new Date());

    let html = '<table class="avail-table"><thead><tr><th>' + (state.availMode === 'teacher' ? 'Преподаватель' : 'Аудитория') + '</th>';
    for (const d of days) {
        const isToday = d.date === todayStr;
        for (let pi = 0; pi < periods.length; pi++) {
            const p = periods[pi];
            html += `<th class="${isToday ? ' avail-header-today' : ''}${pi === 0 ? ' day-sep-left' : ''}"><div class="avail-day-label">${d.day_name}</div><div class="avail-period-label">${p.start}</div></th>`;
        }
    }
    html += '<th>Своб. пар</th></tr></thead><tbody>';

    if (groupByCourse && state.availData.all_courses) {
        for (const course of state.availData.all_courses) {
            const courseRows = rows.filter(r => r.courses && r.courses.includes(course));
            if (!courseRows.length) continue;
            html += `<tr class="avail-course-header"><td colspan="${days.length * periods.length + 2}">${course} курс</td></tr>`;
            for (const row of courseRows) html += _availRow(row, busyMap, days, periods, freeOnly, isHeatmap);
        }
    } else {
        for (const row of rows) html += _availRow(row, busyMap, days, periods, freeOnly, isHeatmap);
    }

    html += '</tbody></table>';
    if (isHeatmap) html += '<div class="avail-legend" style="margin-top:8px;font-size:12px"><span style="background:#4CAF50;color:#fff;padding:2px 8px;border-radius:4px;margin-right:4px">свободно</span> <span style="background:#F44336;color:#fff;padding:2px 8px;border-radius:4px;margin-right:4px">занято</span></div>';
    cont.innerHTML = html || '<div style="padding:20px;color:var(--text-secondary)">Все заняты</div>';
}

function _availRow(row, busyMap, days, periods, freeOnly, isHeatmap) {
    const rb = busyMap[String(row.id)] || {};
    let freeCount = 0;
    const cells = [];
    for (let di = 0; di < days.length; di++) {
        const d = days[di];
        for (let pi = 0; pi < periods.length; pi++) {
            const p = periods[pi];
            const key = `${d.date}_${p.period}`;
            const info = rb[key];
            if (info) {
                const nav = state.availMode === 'teacher' && info.teacher_id ? ` onclick="_clickLesson(${JSON.stringify(info).replace(/"/g, '&quot;')}, '${d.date}', ${p.period})"` : '';
                if (isHeatmap) {
                    cells.push(`<td class="avail-cell-busy${pi === 0 ? ' day-sep-left' : ''}"${nav} title="${escapeHtml(info.subject)} · ${escapeHtml(info.group)}" style="background:#F44336;color:#fff;cursor:${nav ? 'pointer' : ''};padding:2px;font-size:11px;text-align:center">${escapeHtml(info.subject)}</td>`);
                } else {
                    cells.push(`<td class="avail-cell-busy${pi === 0 ? ' day-sep-left' : ''}"${nav} style="cursor:${nav ? 'pointer' : ''}"><div class="avail-busy-inner"><div class="busy-time">${p.start} – ${p.end}</div><div class="busy-subject">${escapeHtml(info.subject)}</div>${info.teacher ? '<div class="busy-teacher">' + escapeHtml(info.teacher) + '</div>' : ''}${info.classroom ? '<div class="busy-classroom">ауд. ' + escapeHtml(info.classroom) + '</div>' : ''}</div></td>`);
                }
            } else {
                freeCount++;
                if (isHeatmap) {
                    cells.push(`<td class="avail-cell-free${pi === 0 ? ' day-sep-left' : ''} day-${di % 2}" style="background:#4CAF50;color:#fff;font-size:11px;text-align:center">свободно</td>`);
                } else {
                    cells.push(`<td class="avail-cell-free${pi === 0 ? ' day-sep-left' : ''} day-${di % 2}">свободен</td>`);
                }
            }
        }
    }
    if (freeOnly && !freeCount) return '';
    return `<tr><td>${escapeHtml(row.name)}</td>${cells.join('')}<td class="avail-summary">${freeCount}</td></tr>`;
}

export { openModal, confirmModal };
export { loadReferences, renderRefList, addGroup, editGroup, addSubject, editSubject, editTeacher, editClassroom, advanceCourses, addRefItem, deleteRefItem, restoreRefItem, quickAdd, quickAddGroup };
export { loadScheduleTable, printSchedule, exportSchedule, showAddLessonModal, addLesson, editLesson, saveLesson, addSubgroupLesson, deleteCurrentLesson, validateLesson };
export { loadTrashTab, restoreTrashItem, purgeTrash };
export { loadSettingsTab, saveSetting };
export { renderCarousel, setActiveWeek, selectWeekByDate, carouselSkip, showAddWeekModal, updateWeekPreview, addWeek, restoreWeek, deleteWeek };
