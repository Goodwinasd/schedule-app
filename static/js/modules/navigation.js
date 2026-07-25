import state from './state.js';
import { getMonday, toISODate, addDays, getWeekNumber, formatChipRange, formatDateRange, escapeHtml, shiftLabel, populateSelectByName } from './utils.js';
import { api } from './api.js';
import { loadReferences, renderHomePage } from './crud.js';
import { loadScheduleTable } from './schedule.js';
import { loadAvailability } from './availability.js';

export function updateUI() {
    const inSchedule = state.currentScheduleType || document.getElementById('availability-view').style.display !== 'none';
    const id = (s) => document.getElementById(s);
    id('btn-login').style.display = state.isAdmin ? 'none' : '';
    id('btn-logout').style.display = state.isAdmin ? '' : 'none';
    id('btn-admin').style.display = state.isAdmin ? '' : 'none';
    id('btn-avail').style.display = state.isAdmin ? '' : 'none';
    id('admin-panel').style.display = (state.isAdmin && state.currentScheduleType) ? '' : 'none';
    id('print-panel').style.display = state.currentScheduleType ? '' : 'none';
}

export function goHome() {
    state.currentScheduleType = '';
    state.currentScheduleId = null;
    state.currentScheduleName = '';
    state.currentMonday = null;
    document.getElementById('home-view').style.display = '';
    document.getElementById('schedule-view').style.display = 'none';
    document.getElementById('availability-view').style.display = 'none';
    document.getElementById('header-title').textContent = 'Расписание';
    updateUI();
    loadHomePage();
}

export function showSchedule(type, id, name) {
    state.currentScheduleType = type;
    state.currentScheduleId = id;
    state.currentScheduleName = name;
    state.currentMonday = getMonday(new Date());
    document.getElementById('home-view').style.display = 'none';
    document.getElementById('schedule-view').style.display = '';
    document.getElementById('availability-view').style.display = 'none';
    document.getElementById('header-title').textContent = '\u2190 ' + name;
    updateUI();
    renderCarousel();
    loadScheduleTable();
}

export function openModal(id) {
    document.getElementById('modal-overlay').classList.add('active');
    document.getElementById(id).style.display = '';
}

export function closeModals() {
    document.getElementById('modal-overlay').classList.remove('active');
    document.querySelectorAll('.modal').forEach(m => m.style.display = 'none');
    const { resetLessonModal } = require_lesson_modal();
    if (resetLessonModal) resetLessonModal();
}

function require_lesson_modal() {
    try {
        const m = window._lessonModal;
        return m || {};
    } catch { return {}; }
}

export function showLoginModal() {
    openModal('login-modal');
    document.getElementById('login-password').value = '';
    document.getElementById('login-password').focus();
}

async function loadHomePage() {
    await loadReferences();
    renderHomePage();
}

/** Carousel */
function getWeeksList() {
    const now = new Date();
    const year = now.getFullYear();
    const yearStart = new Date(year, 0, 1);
    const firstMonday = getMonday(yearStart);
    const weeks = [];
    for (let i = 0; i < 54; i++) {
        const mon = addDays(firstMonday, i * 7);
        if (mon.getFullYear() > year) break;
        if (mon.getFullYear() < year) continue;
        weeks.push({ date: toISODate(mon), monday: mon, weekNumber: getWeekNumber(mon) });
    }
    return weeks;
}

export function renderCarousel() {
    const container = document.getElementById('week-carousel');
    const weeks = getWeeksList();
    const selected = toISODate(state.currentMonday);
    const todayStr = toISODate(getMonday(new Date()));
    const currentIndex = weeks.findIndex(w => w.date === selected);
    let html = '<div class="carousel-nav">';
    html += '<button class="carousel-arrow carousel-arrow-left' + (currentIndex <= 0 ? ' disabled' : '') + '" id="carousel-arrow-left" onclick="carouselSkip(-1)" title="\u2190 \u043f\u0440\u0435\u0434\u044b\u0434\u0443\u0449\u0430\u044f \u043d\u0435\u0434\u0435\u043b\u044f">\u00ab</button>';
    html += '<div class="carousel-strip" id="carousel-strip">';
    for (const w of weeks) {
        const cls = w.date === selected ? ' carousel-chip active' : w.date === todayStr ? ' carousel-chip today' : ' carousel-chip';
        html += '<div class="' + cls + '" data-date="' + w.date + '" onclick="selectWeekByDate(\'' + w.date + '\')">';
        html += '<span class="chip-week">' + w.weekNumber + ' \u043d\u0435\u0434\u0435\u043b\u044f</span>';
        html += '<span class="chip-range">' + formatChipRange(w.monday) + '</span></div>';
    }
    html += '</div>';
    html += '<button class="carousel-arrow carousel-arrow-right' + (currentIndex >= weeks.length - 1 ? ' disabled' : '') + '" id="carousel-arrow-right" onclick="carouselSkip(1)" title="\u0441\u043b\u0435\u0434\u0443\u044e\u0449\u0430\u044f \u043d\u0435\u0434\u0435\u043b\u044f \u2192">\u00bb</button>';
    html += '</div>';
    container.innerHTML = html;
}

export function setActiveWeek() {
    const strip = document.getElementById('carousel-strip');
    if (!strip) return;
    const selected = toISODate(state.currentMonday);
    strip.querySelectorAll('.carousel-chip').forEach(chip => {
        chip.classList.toggle('active', chip.dataset.date === selected);
    });
    const active = strip.querySelector('.carousel-chip.active');
    if (active) {
        const stripRect = strip.getBoundingClientRect();
        const chipRect = active.getBoundingClientRect();
        strip.scrollBy({ left: chipRect.left - stripRect.left - (stripRect.width / 2) + (chipRect.width / 2), behavior: 'smooth' });
    }
    const weeks = getWeeksList();
    const currentIndex = weeks.findIndex(w => w.date === selected);
    const la = document.getElementById('carousel-arrow-left');
    const ra = document.getElementById('carousel-arrow-right');
    if (la) la.classList.toggle('disabled', currentIndex <= 0);
    if (ra) ra.classList.toggle('disabled', currentIndex >= weeks.length - 1);
}

export function selectWeekByDate(dateStr) {
    state.currentMonday = new Date(dateStr + 'T00:00:00');
    setActiveWeek();
    loadScheduleTable();
}

export function carouselSkip(weeks) {
    state.currentMonday = addDays(state.currentMonday, weeks * 7);
    setActiveWeek();
    loadScheduleTable();
}

export function showAddWeekModal() {
    openModal('add-week-modal');
    populateSelectByName('week-group', state.groupsList, '\u2014 \u0432\u044b\u0431\u0440\u0430\u0442\u044c \u0433\u0440\u0443\u043f\u043f\u0443 \u2014');
    document.getElementById('week-start-date').value = toISODate(state.currentMonday || getMonday(new Date()));
    updateWeekPreview();
}

export function updateWeekPreview() {
    const dateStr = document.getElementById('week-start-date').value;
    if (!dateStr) return;
    const monday = new Date(dateStr + 'T00:00:00');
    const { DAY_ORDER } = require('./config.js');
    const { addDays, formatShortDate, toISODate } = require('./utils.js');
    document.getElementById('week-preview').innerHTML = DAY_ORDER.map((name, i) => {
        const d = addDays(monday, i);
        return '<div class="week-preview-day"><span>' + name + '</span><span>' + formatShortDate(toISODate(d)) + '</span></div>';
    }).join('');
}

export async function addWeek() {
    const groupName = document.getElementById('week-group').value;
    const dateStr = document.getElementById('week-start-date').value;
    if (!dateStr) return alert('\u0412\u044b\u0431\u0435\u0440\u0438\u0442\u0435 \u0434\u0430\u0442\u0443 \u043f\u043e\u043d\u0435\u0434\u0435\u043b\u044c\u043d\u0438\u043a\u0430');
    if (!groupName) return alert('\u0412\u044b\u0431\u0435\u0440\u0438\u0442\u0435 \u0433\u0440\u0443\u043f\u043f\u0443');
    const { DAY_ORDER } = require('./config.js');
    const monday = new Date(dateStr + 'T00:00:00');
    const days = DAY_ORDER.map((name, i) => ({
        day_name: name, date: toISODate(addDays(monday, i)), group_name: groupName,
    }));
    const dates = days.map(d => d.date);
    const check = await api('/api/validate-week', {
        method: 'POST', body: JSON.stringify({ group_name: groupName, dates }),
    });
    if (!check.ok) {
        alert(check.warnings.map(w => w.message).join('\n'));
        return;
    }
    const res = await api('/api/days/batch', { method: 'POST', body: JSON.stringify({ days }) });
    if (res.error) { alert(res.error); return; }
    closeModals();
    loadScheduleTable();
}

export async function restoreWeek() {
    if (!state.currentMonday) return;
    if (!confirm('\u0412\u043e\u0441\u0441\u0442\u0430\u043d\u043e\u0432\u0438\u0442\u044c \u0432\u0441\u0435 \u0443\u0434\u0430\u043b\u0435\u043d\u043d\u044b\u0435 \u0434\u043d\u0438 \u0438 \u0443\u0440\u043e\u043a\u0438 \u0437\u0430 \u044d\u0442\u0443 \u043d\u0435\u0434\u0435\u043b\u044e?')) return;
    const monday = toISODate(state.currentMonday);
    const res = await api('/api/week/restore?monday=' + monday, { method: 'POST' });
    if (res.error) { alert(res.error); return; }
    alert('\u0412\u043e\u0441\u0441\u0442\u0430\u043d\u043e\u0432\u043b\u0435\u043d\u043e \u0434\u043d\u0435\u0439: ' + res.days_restored);
    loadScheduleTable();
}

export async function deleteWeek() {
    if (!state.currentMonday) return;
    if (!confirm('\u0423\u0434\u0430\u043b\u0438\u0442\u044c \u0432\u0441\u0435 \u0434\u043d\u0438 \u0438 \u0443\u0440\u043e\u043a\u0438 \u0437\u0430 \u044d\u0442\u0443 \u043d\u0435\u0434\u0435\u043b\u044e?')) return;
    const monday = toISODate(state.currentMonday);
    const res = await api('/api/week?monday=' + monday, { method: 'DELETE' });
    if (res.error) { alert(res.error); return; }
    alert('\u0423\u0434\u0430\u043b\u0435\u043d\u043e \u0434\u043d\u0435\u0439: ' + res.days_deleted);
    loadScheduleTable();
}

document.addEventListener('DOMContentLoaded', () => {
    const di = document.getElementById('week-start-date');
    if (di) di.addEventListener('change', updateWeekPreview);
});
