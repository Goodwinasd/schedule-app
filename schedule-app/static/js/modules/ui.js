import state from './state.js';
import { escapeHtml, getMonday, addDays, toISODate, formatChipRange } from './utils.js';
import { api } from './api.js';
import { openModal, _confirmState, showKimiAlert } from './modal.js';
import { showToast } from './toast.js';
import { loadReferences, renderRefList, populateSubjectTeacherSelect, populateGroupSpecialtySelect, loadSpecialties } from './references.js';
import { loadScheduleTable, addLesson } from './schedule.js';
import { loadTrashTab } from './trash.js';
import { loadSettingsTab, loadExcludedDates, loadBellScheduleTab } from './settings.js';
import { renderCarousel, getWeeksList } from './nav.js';
import { showLoader, hideLoader } from './loader.js';
import { loadCurriculum } from './curriculum.js';
import { onEvent, CURRICULUM_UPDATED, SCHEDULE_UPDATED, HOLIDAYS_UPDATED, REFERENCES_UPDATED, DATA_MUTATED } from './events.js';

function refreshAnalyticsIfVisible() {
    const availView = document.getElementById('availability-view');
    if (availView && availView.style.display !== 'none') {
        loadAvailability();
    }
}
onEvent(CURRICULUM_UPDATED, refreshAnalyticsIfVisible);
onEvent(SCHEDULE_UPDATED, refreshAnalyticsIfVisible);
onEvent(HOLIDAYS_UPDATED, refreshAnalyticsIfVisible);
onEvent(REFERENCES_UPDATED, refreshAnalyticsIfVisible);
onEvent(DATA_MUTATED, refreshAnalyticsIfVisible);

/* ======================== Navigation ======================== */

export function updateUI() {
    const g = id => document.getElementById(id);
    g('btn-login').style.display = state.isAdmin ? 'none' : '';
    g('btn-logout').style.display = state.isAdmin ? '' : 'none';
    g('btn-admin').style.display = state.isAdmin ? '' : 'none';
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

export async function goHome() {
    state.currentScheduleType = '';
    state.currentScheduleId = state.currentScheduleName = null;
    state.currentMonday = null;
    ['home-view', 'schedule-view', 'availability-view'].forEach(v => document.getElementById(v).style.display = v === 'home-view' ? '' : 'none');
    document.getElementById('header-title').textContent = 'Расписание';
    updateUI();
    await loadReferences();
    renderHomePage();
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
    const adminContent = document.querySelector('#references-modal .modal-content.t-modal');
    if (adminContent) {
        adminContent.classList.remove('is-open');
        adminContent.classList.add('is-closing');
        setTimeout(() => {
            adminContent.classList.remove('is-closing');
            document.getElementById('modal-overlay').classList.remove('active');
            document.querySelectorAll('.modal').forEach(m => m.style.display = 'none');
        }, 150);
    } else {
        document.getElementById('modal-overlay').classList.remove('active');
        document.querySelectorAll('.modal').forEach(m => m.style.display = 'none');
    }
    if (typeof resetLessonModal === 'function') resetLessonModal();
    if (_confirmState.resolver) { const r = _confirmState.resolver; _confirmState.resolver = null; r(false); }
    const cm = document.getElementById('checkmark-anim');
    if (cm) cm.setAttribute('data-state', 'out');
}

function resetLessonModal() {
    state.currentEditLessonId = null;
    state.currentLessonDate = null;
    document.querySelector('#add-lesson-modal h2').textContent = 'Новый пара';
    const btn = document.getElementById('btn-save-lesson');
    btn.textContent = 'Добавить'; btn.disabled = false;
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
    p.onkeydown = (e) => { if (e.key === 'Enter') login(); };
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
    const adminContent = document.querySelector('#references-modal .modal-content.t-modal');
    if (adminContent) {
        adminContent.classList.remove('is-closing');
        void adminContent.offsetWidth;
        adminContent.classList.add('is-open');
    }
    ['subjects', 'teachers', 'groups', 'classrooms'].forEach(e => renderRefList(e, `ref-${e}`));
    populateSubjectTeacherSelect();
    populateGroupSpecialtySelect();
    document.querySelectorAll('.admin-tab-content').forEach(c => c.classList.remove('active'));
    document.querySelectorAll('.admin-tab').forEach(t => t.classList.remove('active'));
    _restoreAdminTabOrder();
    const first = document.querySelector('.admin-tab');
    if (first) first.classList.add('active');
    const firstContent = document.getElementById('admin-tab-' + (first ? first.dataset.tab : 'refs'));
    if (firstContent) firstContent.classList.add('active');
    const cm = document.getElementById('checkmark-anim');
    if (cm) requestAnimationFrame(() => cm.setAttribute('data-state', 'in'));
}

function _restoreAdminTabOrder() {
    const container = document.getElementById('admin-tabs');
    if (!container) return;
    const order = localStorage.getItem('admin_tabs_order');
    const tabs = container.querySelectorAll('.admin-tab');
    if (order) {
        try {
            const ids = JSON.parse(order);
            const tabMap = {};
            tabs.forEach(t => { tabMap[t.dataset.tab] = t; });
            ids.forEach(id => { if (tabMap[id]) container.appendChild(tabMap[id]); });
        } catch (e) {}
    }
    tabs.forEach(tab => {
        // showAdminPanel зовёт _restoreAdminTabOrder при каждом открытии, поэтому без флага
        // слушатели накапливались бы и один drop обрабатывался бы N раз
        if (tab.dataset.dragBound === '1') return;
        tab.dataset.dragBound = '1';
        tab.addEventListener('dragstart', _onTabDragStart);
        tab.addEventListener('dragend', _onTabDragEnd);
        tab.addEventListener('dragover', _onTabDragOver);
        tab.addEventListener('drop', _onTabDrop);
    });
}

function _onTabDragStart(e) {
    e.dataTransfer.effectAllowed = 'move';
    e.dataTransfer.setData('text/plain', e.target.dataset.tab);
    e.target.classList.add('dragging');
}

function _onTabDragEnd(e) {
    e.target.classList.remove('dragging');
    document.querySelectorAll('.admin-tab.drag-over').forEach(t => t.classList.remove('drag-over'));
}

function _onTabDragOver(e) {
    e.preventDefault();
    e.dataTransfer.dropEffect = 'move';
    document.querySelectorAll('.admin-tab.drag-over').forEach(t => t.classList.remove('drag-over'));
    e.currentTarget.classList.add('drag-over');
}

function _onTabDrop(e) {
    e.preventDefault();
    const fromTab = e.dataTransfer.getData('text/plain');
    const toTab = e.currentTarget.dataset.tab;
    if (fromTab === toTab) return;
    const container = document.getElementById('admin-tabs');
    const fromEl = container.querySelector(`[data-tab="${fromTab}"]`);
    const toEl = container.querySelector(`[data-tab="${toTab}"]`);
    if (!fromEl || !toEl) return;
    container.insertBefore(fromEl, toEl.nextSibling);
    document.querySelectorAll('.admin-tab.drag-over').forEach(t => t.classList.remove('drag-over'));
    const ids = Array.from(container.querySelectorAll('.admin-tab')).map(t => t.dataset.tab);
    localStorage.setItem('admin_tabs_order', JSON.stringify(ids));
}

export function switchAdminTab(tab) {
    const adminContent = document.querySelector('#references-modal .modal-content.t-modal');
    const current = document.querySelector('.admin-tab-content.tab-content.active');
    if (current) current.classList.add('is-animating-out');
    setTimeout(() => {
        document.querySelectorAll('.admin-tab-content').forEach(c => c.classList.remove('active', 'is-animating-out'));
        document.querySelectorAll('.admin-tab').forEach(t => t.classList.remove('active'));
        const tabBtn = document.querySelector(`.admin-tab[data-tab="${tab}"]`);
        if (tabBtn) tabBtn.classList.add('active');
        const content = document.getElementById(`admin-tab-${tab}`);
        if (content) {
            content.classList.add('active', 'is-animating-in');
            void content.offsetWidth;
            content.classList.remove('is-animating-in');
        }
    if (tab === 'trash') loadTrashTab();
    if (tab === 'system') { loadHealthTab(); loadSettingsTab(); loadExcludedDates(); loadBellScheduleTab(); }
    if (tab === 'curriculum') loadCurriculum();
    if (tab === 'specialties') loadSpecialties();
    if (adminContent) {
            requestAnimationFrame(() => {
                adminContent.style.height = adminContent.scrollHeight + 'px';
            });
            setTimeout(() => { adminContent.style.height = ''; }, 250);
        }
    }, 150);
}

export function openDashboard() {
    closeModals();
    showAvailability();
}

async function loadHealthTab() {
    showLoader('Диагностика БД');
    const cont = document.getElementById('db-health-content');
    cont.innerHTML = '';
    const data = await api('/api/db/health');
    hideLoader();
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
    else await showKimiAlert('Неверный пароль');
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
    // Каркас раздела показываем ДО загрузки данных — элементы управления видны всегда
    document.getElementById('home-view').style.display = 'none';
    document.getElementById('schedule-view').style.display = 'none';
    document.getElementById('availability-view').style.display = '';
    document.getElementById('header-title').textContent = '← Свободные окна';
    updateUI();
    try {
        renderAvailCarousel();
        await loadAvailability();
    } catch (error) {
        console.error('Ошибка рендеринга Свободных окон:', error);
        const cont = document.getElementById('avail-table-container');
        if (cont) cont.innerHTML = '<div class="avail-empty">Не удалось загрузить данные доступности. Обновите страницу или попробуйте позже.</div>';
        else console.warn('[UI] Не найден DOM-элемент #avail-table-container для вывода сообщения об ошибке');
    }
}

function renderAvailCarousel() {
    const cont = document.getElementById('avail-carousel');
    if (!cont) {
        console.warn('[UI] Не найден DOM-элемент #avail-carousel для рендеринга карусели недель');
        return;
    }
    const chevL = '<svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" aria-hidden="true"><path d="M15 18l-6-6 6-6" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/></svg>';
    const chevR = '<svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" aria-hidden="true"><path d="M9 18l6-6-6-6" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/></svg>';
    const weeks = getWeeksList();
    const sel = toISODate(state.availMonday);
    const today = toISODate(getMonday(new Date()));
    const idx = weeks.findIndex(w => w.date === sel);
    let html = '<div class="carousel-nav">';
    html += `<button class="carousel-arrow carousel-arrow-left${idx <= 0 ? ' disabled' : ''}" id="avail-arrow-left" data-action="availCarouselSkip" data-params="[-1]" title="← предыдущая неделя" aria-label="Предыдущая неделя">${chevL}</button>`;
    html += '<div class="carousel-strip" id="avail-carousel-strip">';
    for (const w of weeks) {
        const cls = w.date === sel ? ' carousel-chip active' : w.date === today ? ' carousel-chip today' : ' carousel-chip';
        html += `<div class="${cls}" data-date="${w.date}" data-action="selectAvailWeek" data-params='["${w.date}"]'><span class="chip-week">${w.weekNumber} неделя</span><span class="chip-range">${formatChipRange(w.monday)}</span></div>`;
    }
    html += '</div>';
    html += `<button class="carousel-arrow carousel-arrow-right${idx >= weeks.length - 1 ? ' disabled' : ''}" id="avail-arrow-right" data-action="availCarouselSkip" data-params="[1]" title="следующая неделя →" aria-label="Следующая неделя">${chevR}</button></div>`;
    cont.innerHTML = html;
}

function availSetActiveWeek() {
    const strip = document.getElementById('avail-carousel-strip');
    if (!strip) {
        console.warn('[UI] Не найден DOM-элемент #avail-carousel-strip для подсветки активной недели');
        return;
    }
    const sel = toISODate(state.availMonday);
    strip.querySelectorAll('.carousel-chip').forEach(c => c.classList.toggle('active', c.dataset.date === sel));
    // Прокрутка строго по границам целых карточек
    const chips = Array.from(strip.querySelectorAll('.carousel-chip'));
    const idx = chips.findIndex(c => c.classList.contains('active'));
    if (idx < 0) return;
    const gap = 8;
    const perView = Math.max(1, Math.floor((strip.clientWidth + gap) / (chips[0].offsetWidth + gap)));
    const target = chips[Math.floor(idx / perView) * perView];
    if (target && Math.abs(strip.scrollLeft - target.offsetLeft) > 2) {
        strip.scrollTo({ left: target.offsetLeft, behavior: 'smooth' });
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
    try {
        const tCont = document.getElementById('avail-table-container');
        const aCont = document.getElementById('avail-analytics');
        const skel = '<div class="avail-skeleton"><div class="skeleton skeleton-text" style="width:45%"></div><div class="skeleton skeleton-card"></div><div class="skeleton skeleton-card"></div><div class="skeleton skeleton-card"></div></div>';
        if (tCont) tCont.innerHTML = skel;
        if (aCont) aCont.innerHTML = '<div class="avail-skeleton"><div class="skeleton skeleton-text" style="width:60%"></div><div class="skeleton skeleton-card"></div></div>';
        const data = await api(_availUrl());
        if (!data || typeof data !== 'object') {
            state.availData = {};
            showToast('Пустой ответ сервера', 'error');
            renderAnalytics();
            renderAvailTable();
            return;
        }
        state.availData = data;
        if (state.availData.error) {
            showToast('Ошибка загрузки данных доступности', 'error');
            return;
        }
        const busyCount = Object.values(state.availData.teacher_busy || {}).reduce((s, m) => s + Object.keys(m).length, 0)
            + Object.values(state.availData.classroom_busy || {}).reduce((s, m) => s + Object.keys(m).length, 0);
        if (!busyCount) {
            showToast('На эту неделю расписания нет — сгенерируйте его', 'info');
        }
        _populateAvailGroups();
        renderAvailDayTabs();
        renderAnalytics();
        renderCharts();
        renderAvailTable();
    } catch (error) {
        console.error('Ошибка рендеринга Свободных окон:', error);
        const cont = document.getElementById('avail-table-container');
        if (cont) cont.innerHTML = '<div class="avail-empty">Не удалось загрузить данные доступности. Обновите страницу или попробуйте позже.</div>';
        else console.warn('[UI] Не найден DOM-элемент #avail-table-container для вывода сообщения об ошибке');
        const aCont = document.getElementById('avail-analytics');
        if (aCont) aCont.innerHTML = '<div class="avail-empty">Не удалось загрузить аналитику.</div>';
    } finally {
        _availWatchdog();
    }
}

/**
 * UI Watchdog — сторожевой предохранитель рендера.
 * Если контейнер остался пустым (в т.ч. содержит только пустые обёртки),
 * фиксирует ошибку в консоли и принудительно отрисовывает fallback-карточку.
 */
export function ensureDOMNotEmpty(containerId, fallbackMessage) {
    const cont = document.getElementById(containerId);
    if (!cont) {
        console.error(`[UI Watchdog] Контейнер #${containerId} не найден в DOM!`);
        return false;
    }
    if (!cont.innerHTML.trim() || !cont.textContent.trim()) {
        console.error(`[UI Watchdog] Контейнер #${containerId} остался пустым после рендера!`);
        cont.innerHTML = `<div class="ui-watchdog-fallback avail-empty"><div class="ui-watchdog-title">${fallbackMessage || 'Интерфейс не получил данных для отображения.'}</div><button class="btn btn-sm" onclick="loadAvailability()">Повторить запрос</button></div>`;
        return false;
    }
    return true;
}

function _availWatchdog() {
    ensureDOMNotEmpty('avail-table-container', 'Не удалось отобразить таблицу доступности.');
    ensureDOMNotEmpty('avail-analytics', 'Не удалось отобразить аналитику.');
}

function renderAnalytics() {
    const cont = document.getElementById('avail-analytics');
    if (!cont) {
        console.warn('[UI] Не найден DOM-элемент #avail-analytics для рендеринга аналитики');
        return;
    }
    if (!state.availData) return;
    try {
        const d = state.availData;

        if (!Object.keys(d.teacher_stats || {}).length
            && !Object.keys(d.classroom_stats || {}).length
            && !Object.keys(d.group_lesson_count || {}).length) {
            cont.innerHTML = '<div class="analytics-section"><h3 class="analytics-title">📊 Аналитика нагрузки</h3><div class="avail-empty">Нет данных для отображения. Сначала сгенерируйте расписание на выбранную неделю.</div></div>';
            return;
        }

        let html = '<div class="analytics-section"><h3 class="analytics-title">📊 Аналитика нагрузки</h3><div class="analytics-grid">';

        // Teacher stats — top 5
        const teachers = Object.values(d.teacher_stats || {}).sort((a, b) => b.total - a.total).slice(0, 5);
        if (teachers.length) {
            html += '<div class="analytics-card"><div class="analytics-card-header">👨‍🏫 Преподаватели</div><div class="analytics-card-body">';
            html += '<table class="analytics-table"><tr><th>Преподаватель</th><th>Пар</th><th>Своб.</th><th>Загрузка</th></tr>';
            for (const t of teachers) {
                html += `<tr><td>${escapeHtml(t.name)}</td><td>${t.total}</td><td>${t.free}</td><td><div class="load-bar"><div class="load-bar-fill" style="width:${Math.min(t.load_pct, 100)}%"></div><span>${t.load_pct}%</span></div></td></tr>`;
            }
            html += '</table></div></div>';
        }

        // Classroom stats — top 5
        const rooms = Object.values(d.classroom_stats || {}).sort((a, b) => b.total - a.total).slice(0, 5);
        if (rooms.length) {
            html += '<div class="analytics-card"><div class="analytics-card-header">🏫 Аудитории (топ)</div><div class="analytics-card-body">';
            html += '<table class="analytics-table"><tr><th>Аудитория</th><th>Пар</th><th>Своб.</th><th>Загрузка</th></tr>';
            for (const r of rooms) {
                html += `<tr><td>${escapeHtml(r.name)}</td><td>${r.total}</td><td>${r.free}</td><td><div class="load-bar"><div class="load-bar-fill" style="width:${Math.min(r.load_pct, 100)}%"></div><span>${r.load_pct}%</span></div></td></tr>`;
            }
            html += '</table></div></div>';
        }

        // Group lesson count
        const groups = Object.values(d.group_lesson_count || {}).sort((a, b) => b.lessons - a.lessons);
        if (groups.length) {
            html += '<div class="analytics-card"><div class="analytics-card-header">📚 Группы</div><div class="analytics-card-body">';
            html += '<table class="analytics-table"><tr><th>Группа</th><th>Пар</th></tr>';
            for (const g of groups) {
                html += `<tr><td>${escapeHtml(g.name)}</td><td>${g.lessons}</td></tr>`;
            }
            html += '</table></div></div>';
        }

        html += '</div></div>';
        cont.innerHTML = html;
    } catch (error) {
        console.error('Ошибка рендеринга Аналитики:', error);
        cont.innerHTML = '<div class="analytics-section"><h3 class="analytics-title">📊 Аналитика нагрузки</h3><div class="avail-empty">Не удалось отобразить аналитику.</div></div>';
    }
    ensureDOMNotEmpty('avail-analytics', 'Не удалось отобразить аналитику.');
}

function _populateAvailGroups() {
    const sel = document.getElementById('avail-group-filter');
    if (!sel) {
        console.warn('[UI] Не найден DOM-элемент #avail-group-filter для наполнения списка групп');
        return;
    }
    if (!state.availData) return;
    const groups = Array.isArray(state.availData.groups) ? state.availData.groups : [];
    const cur = sel.value;
    // Имена/идентификаторы групп приходят из БД — в атрибуты и текст только через escapeHtml
    sel.innerHTML = '<option value="">Все группы</option>' + groups.map(g => `<option value="${escapeHtml(g.id)}">${escapeHtml(g.name)}</option>`).join('');
    sel.value = cur;
}

function renderAvailDayTabs() {
    const cont = document.getElementById('avail-day-tabs');
    if (!cont) {
        console.warn('[UI] Не найден DOM-элемент #avail-day-tabs для рендеринга вкладок дней');
        return;
    }
    if (!state.availData) return;
    const days = Array.isArray(state.availData.days) ? state.availData.days : [];
    const todayStr = toISODate(new Date());
    let html = `<div class="avail-day-tab ${!state.availSelectedDay ? 'active' : ''}" data-action="selectAvailDay" data-params="[null]">Вся неделя</div>`;
    for (const d of days) {
        const a = state.availSelectedDay === d.date ? ' active' : '';
        const t = d.date === todayStr ? ' today' : '';
        // day_name/date — из ответа API, экранируем и текст, и значение атрибута
        html += `<div class="avail-day-tab${a}${t}" data-action="selectAvailDay" data-params='["${escapeHtml(d.date)}"]'>${escapeHtml(d.day_name)}</div>`;
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
    if (!state.availData) { showToast('Сначала откройте раздел доступности', 'info'); return; }
    const modeLabel = state.availMode === 'teacher' ? 'Преподаватель' : 'Аудитория';
    const days = state.availSelectedDay ? state.availData.days.filter(d => d.date === state.availSelectedDay) : state.availData.days;
    const showAll = document.getElementById('avail-show-all-periods').checked;
    const periods = showAll ? state.availData.periods : state.availData.periods.filter(p => p.period <= 6);
    const rows = state.availMode === 'teacher' ? state.availData.teachers : state.availData.classrooms;
    const busyMap = state.availMode === 'teacher' ? state.availData.teacher_busy : state.availData.classroom_busy;
    const esc = s => String(s ?? '').replace(/[<>&]/g, c => ({ '<': '&lt;', '>': '&gt;', '&': '&amp;' }[c]));

    let html = '<html xmlns:o="urn:schemas-microsoft-com:office:office" xmlns:x="urn:schemas-microsoft-com:office:excel" xmlns="http://www.w3.org/TR/REC-html40"><head><meta charset="UTF-8"><!--[if gte mso 9]><xml><x:ExcelWorkbook><x:ExcelWorksheets><x:ExcelWorksheet><x:Name>'; 
    html += 'Свободные окна';
    html += '</x:Name><x:WorksheetOptions><x:DisplayGridlines/></x:WorksheetOptions></x:ExcelWorksheet></x:ExcelWorksheets></x:ExcelWorkbook></xml><![endif]--></head><body><table border="1">';

    let head = `<tr><th>${modeLabel}</th>`;
    for (const d of days) {
        for (const p of periods) {
            head += `<th>${esc(d.day_name)} ${p.period}-я пара<br>${esc(p.start)} – ${esc(p.end)}</th>`;
        }
    }
    head += '<th>Своб. пар</th></tr>';
    html += head;

    for (const row of rows) {
        const rb = busyMap[String(row.id)] || {};
        let rowHtml = `<tr><td>${esc(row.name)}</td>`;
        let freeCount = 0;
        for (const d of days) {
            for (const p of periods) {
                const info = rb[`${d.date}_${p.period}`];
                if (info) {
                    const parts = [info.subject];
                    if (info.group) parts.push('группа: ' + info.group);
                    if (info.teacher) parts.push(info.teacher);
                    if (info.classroom) parts.push('ауд. ' + info.classroom);
                    let label = parts.join(' | ');
                    if (info.is_sub) label += ' (ЗАМЕНА' + (info.original_teacher ? ' за: ' + info.original_teacher : '') + ')';
                    rowHtml += `<td>${esc(label)}</td>`;
                } else {
                    freeCount++;
                    rowHtml += '<td></td>';
                }
            }
        }
        rowHtml += `<td>${freeCount}</td></tr>`;
        html += rowHtml;
    }
    html += '</table></body></html>';

    const sel = toISODate(state.availMonday);
    const weeks = getWeeksList();
    const w = weeks.find(x => x.date === sel);
    const num = w ? w.weekNumber : '1';
    const blob = new Blob(['\ufeff', html], { type: 'application/vnd.ms-excel;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `Свободные_окна_неделя_${num}.xls`;
    document.body.appendChild(a);
    a.click();
    setTimeout(() => { document.body.removeChild(a); URL.revokeObjectURL(url); }, 200);
    showToast('Экспорт подготовлен', 'success');
}

export function exportAvailPDF() {
    if (!state.availData) { showToast('Сначала откройте раздел доступности', 'info'); return; }
    window.print();
}

export function closeAvailability() {
    _destroyCharts();
    document.getElementById('availability-view').style.display = 'none';
    document.getElementById('home-view').style.display = '';
    document.getElementById('header-title').textContent = 'Расписание';
    updateUI();
}

/** Тематические цвета графиков (тёмная/светлая темы приложения). */
function _chartTheme() {
    const dark = document.documentElement.getAttribute('data-theme') === 'dark';
    return dark ? {
        grid: 'rgba(255,255,255,0.08)',
        ticks: 'rgba(229,231,235,0.92)',
        legend: 'rgba(229,231,235,0.92)',
        tooltipBg: 'rgba(15,23,42,0.95)',
        tooltipBorder: 'rgba(34,197,94,0.35)',
    } : {
        grid: 'rgba(0,0,0,0.07)',
        ticks: 'rgba(75,85,99,0.95)',
        legend: 'rgba(17,24,39,0.92)',
        tooltipBg: 'rgba(17,24,39,0.92)',
        tooltipBorder: 'rgba(59,130,246,0.35)',
    };
}

function _destroyCharts() {
    if (window.teachersChart) { window.teachersChart.destroy(); window.teachersChart = null; }
    if (window.classroomsChart) { window.classroomsChart.destroy(); window.classroomsChart = null; }
}

function _truncateLabel(name, len = 16) {
    return name && name.length > len ? name.slice(0, len - 1) + '…' : name;
}

/** Отрисовка графиков аналитики доступности (Chart.js). */
export function renderCharts() {
    const host = document.getElementById('avail-charts');
    if (!host) return;
    if (typeof Chart === 'undefined') return;
    _destroyCharts();
    const d = state.availData;
    if (!d) return;

    const teachers = Object.values(d.teacher_stats || {})
        .sort((a, b) => b.load_pct - a.load_pct)
        .slice(0, 10);
    const rooms = Object.values(d.classroom_stats || {});
    const topRooms = rooms.slice().sort((a, b) => b.load_pct - a.load_pct);

    if (!teachers.length && !rooms.length) {
        host.style.display = 'none';
        return;
    }
    host.style.display = '';

    const th = _chartTheme();

    // График 1: загрузка преподавателей (bar, топ-10)
    const tCanvas = document.getElementById('teachers-load-chart');
    if (tCanvas && teachers.length) {
        window.teachersChart = new Chart(tCanvas, {
            type: 'bar',
            data: {
                labels: teachers.map(t => _truncateLabel(t.name)),
                datasets: [{
                    label: 'Загрузка, %',
                    data: teachers.map(t => t.load_pct),
                    backgroundColor: teachers.map((_, i) => (i < 3 ? '#22c55e' : i < 7 ? '#3b82f6' : '#f97316')),
                    borderRadius: 8,
                    maxBarThickness: 42,
                }],
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: { display: false },
                    tooltip: {
                        backgroundColor: th.tooltipBg,
                        borderColor: th.tooltipBorder,
                        borderWidth: 1,
                        titleColor: '#ffffff',
                        bodyColor: '#e5e7eb',
                        callbacks: {
                            afterLabel: (ctx) => {
                                const t = teachers[ctx.dataIndex];
                                return `Пар: ${t.total} · Свободно: ${t.free}`;
                            },
                        },
                    },
                },
                scales: {
                    x: { ticks: { color: th.ticks, maxRotation: 45, minRotation: 20 }, grid: { display: false } },
                    y: {
                        beginAtZero: true,
                        max: 100,
                        ticks: { color: th.ticks, callback: v => v + '%' },
                        grid: { color: th.grid },
                    },
                },
            },
        });
    } else if (tCanvas) {
        tCanvas.style.display = 'none';
    }

    // График 2: занятость аудиторий (doughnut, топ-10)
    const cCanvas = document.getElementById('classrooms-load-chart');
    if (cCanvas && topRooms.length) {
        window.classroomsChart = new Chart(cCanvas, {
            type: 'doughnut',
            data: {
                labels: topRooms.map(r => _truncateLabel(r.name)),
                datasets: [{
                    label: 'Занятость аудиторий',
                    data: topRooms.map(r => r.total),
                    backgroundColor: ['#22c55e', '#3b82f6', '#f97316', '#06b6d4', '#a855f7', '#eab308', '#22c55e', '#3b82f6', '#f97316', '#06b6d4'],
                    borderColor: (document.documentElement.getAttribute('data-theme') === 'dark') ? 'rgba(15,23,42,1)' : '#ffffff',
                    borderWidth: 2,
                }],
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                cutout: '62%',
                plugins: {
                    legend: { position: 'right', labels: { color: th.legend, boxWidth: 12, font: { size: 11 } } },
                    tooltip: {
                        backgroundColor: th.tooltipBg,
                        borderColor: th.tooltipBorder,
                        borderWidth: 1,
                        titleColor: '#ffffff',
                        bodyColor: '#e5e7eb',
                        callbacks: {
                            label: (ctx) => {
                                const r = topRooms[ctx.dataIndex];
                                return ` ${r.name}: ${r.total} пар (${r.load_pct}%)`;
                            },
                        },
                    },
                },
            },
        });
    } else if (cCanvas) {
        cCanvas.style.display = 'none';
    }
}

export function _clickLesson(info, date, period) {
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

export function renderAvailTable() {
    const cont = document.getElementById('avail-table-container');
    if (!cont) {
        console.warn('[UI] Не найден DOM-элемент #avail-table-container для рендеринга таблицы');
        return;
    }
    if (!state.availData) return;
    try {
        const freeOnly = document.getElementById('avail-free-only').checked;
        const showAll = document.getElementById('avail-show-all-periods').checked;
        const isHeatmap = state.availHeatmap;
        const groupByCourse = state.availGroupByCourse && state.availMode === 'teacher';
        const days = state.availSelectedDay ? state.availData.days.filter(d => d.date === state.availSelectedDay) : state.availData.days;
        const periods = showAll ? state.availData.periods : state.availData.periods.filter(p => p.period <= 6);
        const rows = state.availMode === 'teacher' ? state.availData.teachers : state.availData.classrooms;
        const busyMap = state.availMode === 'teacher' ? state.availData.teacher_busy : state.availData.classroom_busy;
        const todayStr = toISODate(new Date());

        if (!rows || !rows.length) {
            cont.innerHTML = '<div class="avail-empty">Нет данных для отображения. Сначала сгенерируйте расписание на выбранную неделю.</div>';
            return;
        }

        let html = '<table class="avail-table"><thead><tr><th>' + (state.availMode === 'teacher' ? 'Преподаватель' : 'Аудитория') + '</th>';
        for (const d of days) {
            const isToday = d.date === todayStr;
            for (let pi = 0; pi < periods.length; pi++) {
                const p = periods[pi];
                // Время звонков приходит из БД (таблица bell_schedule) — экранируем оба поля
                html += `<th class="${isToday ? ' avail-header-today' : ''}${pi === 0 ? ' day-sep-left' : ''}"><div class="avail-day-label">${escapeHtml(d.day_name)}</div><div class="avail-period-label">${escapeHtml(p.start)}</div></th>`;
            }
        }
        html += '<th>Своб. пар</th></tr></thead><tbody>';

        if (groupByCourse && state.availData.all_courses) {
            const byCourse = new Map();
            const noCourse = [];
            for (const row of rows) {
                const rowCourses = (Array.isArray(row.courses) ? row.courses : [])
                    .filter(c => state.availData.all_courses.includes(c));
                if (!rowCourses.length) {
                    noCourse.push(row);
                } else {
                    for (const c of rowCourses) {
                        if (!byCourse.has(c)) byCourse.set(c, []);
                        byCourse.get(c).push(row);
                    }
                }
            }
            for (const course of state.availData.all_courses) {
                const courseRows = byCourse.get(course) || [];
                if (!courseRows.length) continue;
                html += `<tr class="avail-course-header"><td colspan="${days.length * periods.length + 2}">${course} курс</td></tr>`;
                for (const row of courseRows) html += _availRow(row, busyMap, days, periods, freeOnly, isHeatmap);
            }
            if (noCourse.length) {
                html += `<tr class="avail-course-header"><td colspan="${days.length * periods.length + 2}">Без нагрузки</td></tr>`;
                for (const row of noCourse) html += _availRow(row, busyMap, days, periods, freeOnly, isHeatmap);
            }
        } else {
            for (const row of rows) html += _availRow(row, busyMap, days, periods, freeOnly, isHeatmap);
        }

        html += '</tbody></table>';
        if (isHeatmap) html += '<div class="avail-legend" style="margin-top:8px;font-size:12px"><span style="background:#4CAF50;color:#fff;padding:2px 8px;border-radius:4px;margin-right:4px">свободно</span> <span style="background:#F44336;color:#fff;padding:2px 8px;border-radius:4px;margin-right:4px">занято</span></div>';
        cont.innerHTML = html || '<div style="padding:20px;color:var(--text-secondary)">Все заняты</div>';
    } catch (error) {
        console.error('Ошибка рендеринга Свободных окон:', error);
        cont.innerHTML = '<div class="avail-empty">Не удалось отобразить таблицу доступности.</div>';
    }
    ensureDOMNotEmpty('avail-table-container', 'Не удалось отобразить таблицу доступности.');
}

function _availRow(row, busyMap, days, periods, freeOnly, isHeatmap) {
    const rb = busyMap[String(row.id)] || {};
    const allPeriods = (state.availData && Array.isArray(state.availData.periods)) ? state.availData.periods : periods;
    const dayCounts = {};
    for (const d of days) {
        let cnt = 0;
        for (const p of allPeriods) {
            if (rb[`${d.date}_${p.period}`]) cnt++;
        }
        dayCounts[d.date] = cnt;
    }
    let freeCount = 0;
    const cells = [];
    for (let di = 0; di < days.length; di++) {
        const d = days[di];
        const limit = di === 5 ? 3 : 4;
        const isOverload = dayCounts[d.date] > limit;
        const overloadCls = isOverload ? ' day-overload' : '';
        for (let pi = 0; pi < periods.length; pi++) {
            const p = periods[pi];
            const key = `${d.date}_${p.period}`;
            const info = rb[key];
            if (info) {
                // Без inline-JS: данные уходят в data-* (их читает делегирование [data-action]
                // из main.js) — JSON.stringify(info) в атрибуте ломался кавычками из БД
                const nav = state.availMode === 'teacher' && info.teacher_id
                    ? ` data-action="_clickLesson" data-params="${escapeHtml(JSON.stringify([{ teacher_id: info.teacher_id, teacher: info.teacher || '' }, d.date, p.period]))}"`
                    : '';
                if (isHeatmap) {
                    const bg = info.is_sub ? '#FF9800' : '#F44336';
                    const tip = `${escapeHtml(info.subject)} · ${escapeHtml(info.group)}${info.is_sub ? ' · Замена за: ' + escapeHtml(info.original_teacher || '—') : ''}`;
                    cells.push(`<td class="avail-cell-busy${pi === 0 ? ' day-sep-left' : ''}${overloadCls}"${nav} title="${tip}" style="background:${bg};color:#fff;cursor:${nav ? 'pointer' : ''};padding:2px;font-size:11px;text-align:center">${escapeHtml(info.subject)}</td>`);
                } else {
                    const subBadge = info.is_sub ? `<span class="busy-sub-badge" title="Замена за: ${escapeHtml(info.original_teacher || '—')}">Зам</span>` : '';
                    const subTitle = info.is_sub ? ` title="Замена за: ${escapeHtml(info.original_teacher || '—')}"` : '';
                    cells.push(`<td class="avail-cell-busy${pi === 0 ? ' day-sep-left' : ''}${overloadCls}"${nav}${subTitle} style="cursor:${nav ? 'pointer' : ''}"><div class="avail-busy-inner"><div class="busy-time">${escapeHtml(p.start)} – ${escapeHtml(p.end)}</div><div class="busy-subject">${escapeHtml(info.subject)}${subBadge}</div>${info.teacher ? '<div class="busy-teacher">' + escapeHtml(info.teacher) + '</div>' : ''}${info.classroom ? '<div class="busy-classroom">ауд. ' + escapeHtml(info.classroom) + '</div>' : ''}</div></td>`);
                }
            } else {
                freeCount++;
                if (isHeatmap) {
                    cells.push(`<td class="avail-cell-free${pi === 0 ? ' day-sep-left' : ''}${overloadCls} day-${di % 2}" style="background:#4CAF50;color:#fff;font-size:11px;text-align:center">свободно</td>`);
                } else {
                    cells.push(`<td class="avail-cell-free${pi === 0 ? ' day-sep-left' : ''}${overloadCls} day-${di % 2}">свободен</td>`);
                }
            }
        }
    }
    if (freeOnly && !freeCount) return '';
    return `<tr><td>${escapeHtml(row.name)}</td>${cells.join('')}<td class="avail-summary">${freeCount}</td></tr>`;
}


