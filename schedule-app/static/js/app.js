/* Изменение №14: финальная чистка */
/* Изменение №15: читаемость свободных окон */
/* Изменение №16: читаемость свободных окон (дни и время) */
/* Изменение №22: стрелка в заголовке, кнопка Назад удалена */
/* Изменение №9: даты словами в каруселях */
let isAdmin = false;
let csrfToken = '';
let bellSchedule = [];
let currentLessonDayId = null;
let currentLessonDate = null;
let currentEditLessonId = null;
let currentLessonDayGroup = '';

let subjectsList = [];
let teachersList = [];
let groupsList = [];
let classroomsList = [];
let teachersWithSchedule = [];
let classroomsWithSchedule = [];

let currentScheduleType = '';
let currentScheduleId = null;
let currentScheduleName = '';
let currentMonday = null;
let lessonsMap = {};

let availMode = 'teacher';
let availMonday = null;
let availSelectedDay = null;
let availData = null;

const MONTHS = [
    'января', 'февраля', 'марта', 'апреля', 'мая', 'июня',
    'июля', 'августа', 'сентября', 'октября', 'ноября', 'декабря'
];
const MONTHS_SHORT = [
    'янв', 'фев', 'мар', 'апр', 'мая', 'июн',
    'июл', 'авг', 'сен', 'окт', 'ноя', 'дек'
];
const WEEKDAYS = [
    'Воскресенье', 'Понедельник', 'Вторник', 'Среда', 'Четверг', 'Пятница', 'Суббота'
];
const DAY_ORDER = ['Понедельник', 'Вторник', 'Среда', 'Четверг', 'Пятница', 'Суббота'];

function escapeHtml(s) {
    if (s == null) return '';
    return String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;').replace(/'/g, '&#39;');
}

async function api(url, options = {}) {
    const headers = { 'Content-Type': 'application/json', ...options.headers };
    if (csrfToken && options.method && options.method !== 'GET') {
        headers['X-CSRF-Token'] = csrfToken;
    }
    const res = await fetch(url, {
        ...options,
        headers,
    });
    const data = await res.json();
    if (res.status === 401) {
        isAdmin = false;
        updateUI();
    }
    return data;
}

function formatDate(dateStr) {
    const d = new Date(dateStr + 'T00:00:00');
    return `${WEEKDAYS[d.getDay()]}, ${d.getDate()} ${MONTHS[d.getMonth()]}`;
}

function formatShortDate(dateStr) {
    const d = new Date(dateStr + 'T00:00:00');
    return `${d.getDate()} ${MONTHS_SHORT[d.getMonth()]}`;
}

function formatDayHeader(dateStr) {
    const d = new Date(dateStr + 'T00:00:00');
    return `${DAY_ORDER[d.getDay() === 0 ? 6 : d.getDay() - 1]}\n${d.getDate()} ${MONTHS_SHORT[d.getMonth()]}`;
}

function getMonday(date) {
    const d = new Date(date);
    const day = d.getDay();
    d.setDate(d.getDate() - day + (day === 0 ? -6 : 1));
    return d;
}

function addDays(date, n) {
    const d = new Date(date);
    d.setDate(d.getDate() + n);
    return d;
}

function toISODate(date) {
    const y = date.getFullYear();
    const m = String(date.getMonth() + 1).padStart(2, '0');
    const d = String(date.getDate()).padStart(2, '0');
    return `${y}-${m}-${d}`;
}

function getWeekNumber(date) {
    const d = new Date(date.getFullYear(), 0, 1);
    const diff = date - d;
    const oneWeek = 7 * 24 * 60 * 60 * 1000;
    return Math.floor(diff / oneWeek) + 1;
}

function formatDateRange(monday) {
    const sat = addDays(monday, 5);
    const fmt = (d) => `${d.getDate()}.${String(d.getMonth() + 1).padStart(2, '0')}`;
    return `${fmt(monday)} – ${fmt(sat)}.${sat.getFullYear()}`;
}

function formatChipRange(monday) {
    const sat = addDays(monday, 5);
    const monDay = monday.getDate();
    const satDay = sat.getDate();
    const monMonth = monday.getMonth();
    const satMonth = sat.getMonth();
    const pfx = monDay === 2 ? 'со' : 'с';
    if (monMonth === satMonth) {
        return `${pfx} ${monDay} по ${satDay} ${MONTHS[monMonth]}`;
    }
    return `${pfx} ${monDay} ${MONTHS[monMonth]} по ${satDay} ${MONTHS[satMonth]}`;
}

function shiftLabel(shift) {
    return ['', '1 смена', '2 смена', '3 смена'][shift] || '';
}

async function loadReferences() {
    [subjectsList, teachersList, groupsList, classroomsList] = await Promise.all([
        api('/api/subjects'),
        api('/api/teachers'),
        api('/api/groups'),
        api('/api/classrooms'),
    ]);
    teachersWithSchedule = await api('/api/teachers-with-schedule');
    classroomsWithSchedule = await api('/api/classrooms-with-schedule');
}

function populateSelect(selectId, items, placeholder) {
    const sel = document.getElementById(selectId);
    sel.innerHTML = `<option value="">${placeholder}</option>` +
        items.map(i => `<option value="${i.id}">${escapeHtml(i.name)}</option>`).join('');
}

function populateSelectByName(selectId, items, placeholder) {
    const sel = document.getElementById(selectId);
    sel.innerHTML = `<option value="">${placeholder}</option>` +
        items.map(i => `<option value="${escapeHtml(i.name)}">${escapeHtml(i.name)}</option>`).join('');
}

async function checkAuth() {
    const data = await api('/api/auth/check');
    isAdmin = data.is_admin;
    if (isAdmin) {
        const tokenData = await api('/api/auth/csrf-token');
        csrfToken = tokenData.csrf_token || '';
    }
    updateUI();
}

function updateUI() {
    const inSchedule = currentScheduleType || document.getElementById('availability-view').style.display !== 'none';
    document.getElementById('btn-login').style.display = isAdmin ? 'none' : '';
    document.getElementById('btn-logout').style.display = isAdmin ? '' : 'none';
    document.getElementById('btn-admin').style.display = isAdmin ? '' : 'none';
    document.getElementById('btn-avail').style.display = isAdmin ? '' : 'none';
    document.getElementById('admin-panel').style.display = (isAdmin && currentScheduleType) ? '' : 'none';
    document.getElementById('print-panel').style.display = currentScheduleType ? '' : 'none';
}

// ---- Navigation ----

function goHome() {
    currentScheduleType = '';
    currentScheduleId = null;
    currentScheduleName = '';
    currentMonday = null;
    document.getElementById('home-view').style.display = '';
    document.getElementById('schedule-view').style.display = 'none';
    document.getElementById('availability-view').style.display = 'none';
    document.getElementById('header-title').textContent = 'Расписание';
    updateUI();
    loadHomePage();
}

function showSchedule(type, id, name) {
    currentScheduleType = type;
    currentScheduleId = id;
    currentScheduleName = name;
    currentMonday = getMonday(new Date());
    document.getElementById('home-view').style.display = 'none';
    document.getElementById('schedule-view').style.display = '';
    document.getElementById('availability-view').style.display = 'none';
    document.getElementById('header-title').textContent = '\u2190 ' + name;
    updateUI();
    renderCarousel();
    loadScheduleTable();
}

// ---- Week Navigation ----

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

/* Изменение №6: единая логика каруселей */

function renderCarousel() {
    const container = document.getElementById('week-carousel');
    const weeks = getWeeksList();
    const selected = toISODate(currentMonday);
    const todayStr = toISODate(getMonday(new Date()));
    const currentIndex = weeks.findIndex(w => w.date === selected);

    let html = '<div class="carousel-nav">';
    html += `<button class="carousel-arrow carousel-arrow-left${currentIndex <= 0 ? ' disabled' : ''}" id="carousel-arrow-left" onclick="carouselSkip(-1)" title="\u2190 \u043f\u0440\u0435\u0434\u044b\u0434\u0443\u0449\u0430\u044f \u043d\u0435\u0434\u0435\u043b\u044f">\u00ab</button>`;
    html += '<div class="carousel-strip" id="carousel-strip">';
    for (const w of weeks) {
        const cls = w.date === selected ? ' carousel-chip active' : w.date === todayStr ? ' carousel-chip today' : ' carousel-chip';
        html += `<div class="${cls}" data-date="${w.date}" onclick="selectWeekByDate('${w.date}')">
            <span class="chip-week">${w.weekNumber} неделя</span>
            <span class="chip-range">${formatChipRange(w.monday)}</span>
        </div>`;
    }
    html += '</div>';
    html += `<button class="carousel-arrow carousel-arrow-right${currentIndex >= weeks.length - 1 ? ' disabled' : ''}" id="carousel-arrow-right" onclick="carouselSkip(1)" title="\u0441\u043b\u0435\u0434\u0443\u044e\u0449\u0430\u044f \u043d\u0435\u0434\u0435\u043b\u044f \u2192">\u00bb</button>`;
    html += '</div>';
    container.innerHTML = html;
}

function setActiveWeek() {
    const strip = document.getElementById('carousel-strip');
    if (!strip) return;
    const selected = toISODate(currentMonday);
    strip.querySelectorAll('.carousel-chip').forEach(chip => {
        chip.classList.toggle('active', chip.dataset.date === selected);
    });
    const active = strip.querySelector('.carousel-chip.active');
    if (active) {
        const stripRect = strip.getBoundingClientRect();
        const chipRect = active.getBoundingClientRect();
        const offset = chipRect.left - stripRect.left - (stripRect.width / 2) + (chipRect.width / 2);
        strip.scrollBy({ left: offset, behavior: 'smooth' });
    }

    const weeks = getWeeksList();
    const currentIndex = weeks.findIndex(w => w.date === selected);
    const leftArrow = document.getElementById('carousel-arrow-left');
    const rightArrow = document.getElementById('carousel-arrow-right');
    if (leftArrow) leftArrow.classList.toggle('disabled', currentIndex <= 0);
    if (rightArrow) rightArrow.classList.toggle('disabled', currentIndex >= weeks.length - 1);
}

function selectWeekByDate(dateStr) {
    currentMonday = new Date(dateStr + 'T00:00:00');
    setActiveWeek();
    loadScheduleTable();
}

function carouselSkip(weeks) {
    currentMonday = addDays(currentMonday, weeks * 7);
    setActiveWeek();
    loadScheduleTable();
}


// ---- Schedule Table ----

async function loadScheduleTable() {
    const container = document.getElementById('schedule-table-container');
    container.innerHTML = '<div class="loading">Загрузка...</div>';

    let data;
    const mondayStr = toISODate(currentMonday);

    if (currentScheduleType === 'group') {
        data = await api(`/api/schedule-table?group=${encodeURIComponent(currentScheduleName)}&monday=${mondayStr}`);
    } else if (currentScheduleType === 'teacher') {
        data = await api(`/api/teacher-schedule-table?teacher_id=${currentScheduleId}&monday=${mondayStr}`);
    } else if (currentScheduleType === 'classroom') {
        data = await api(`/api/classroom-schedule-table?classroom_id=${currentScheduleId}&monday=${mondayStr}`);
    }

    if (!data || !data.periods || data.periods.length === 0) {
        container.innerHTML = renderNoSchedule();
        return;
    }

    if (data.week_exists === false) {
        container.innerHTML = renderNoSchedule();
        return;
    }

    container.innerHTML = renderScheduleTable(data);
}

function renderNoSchedule() {
    return `<div class="no-schedule">
        <span class="emoji">📅</span>
        <p>Нет расписания на эту неделю</p>
    </div>`;
}

function printSchedule() {
    const title = currentScheduleName;
    const wn = getWeekNumber(currentMonday);
    const range = formatDateRange(currentMonday);
    document.getElementById('print-title').textContent = `${title}`;
    document.getElementById('print-subtitle').textContent = `Неделя ${wn} · ${range}`;

    let style = document.getElementById('print-inline-style');
    if (!style) {
        style = document.createElement('style');
        style.id = 'print-inline-style';
        document.head.appendChild(style);
    }
    style.textContent = `
        @media print {
            body, td, th, .schedule-table, .schedule-table-wrap, main, #schedule-view, #schedule-table-container {
                background: white !important;
                color: black !important;
            }
            td.day-cell {
                background: white !important;
                color: black !important;
            }
            td.day-cell:not(.empty-cell) {
                background: #f0f0f0 !important;
            }
            .lesson-content, .lesson-content .lesson-subject, .lesson-content .lesson-meta {
                color: black !important;
            }
            .lesson-content .lesson-meta {
                color: #333 !important;
            }
            .lesson-subject {
                color: black !important;
            }
            td.day-cell .lesson-content .lesson-subject {
                color: black !important;
                background: transparent !important;
            }
            td.day-cell .lesson-content .lesson-meta {
                color: #333 !important;
                background: transparent !important;
            }
            td.day-cell .lesson-content {
                background: transparent !important;
                color: black !important;
            }
        }
    `;
    window.print();
}

function exportSchedule(format) {
    const monday = toISODate(currentMonday);
    const params = { type: currentScheduleType, name: currentScheduleName, id: currentScheduleId, monday, format };
    console.log('Export params:', params);
    const url = `/api/export?type=${encodeURIComponent(currentScheduleType)}&name=${encodeURIComponent(currentScheduleName)}&id=${encodeURIComponent(currentScheduleId)}&monday=${monday}&format=${format}`;
    fetch(url, { method: 'HEAD' }).then(res => {
        if (!res.ok) {
            return res.json().then(body => {
                alert(body.error || `Ошибка экспорта (${res.status})`);
            }).catch(() => {
                alert(`Ошибка экспорта (${res.status})`);
            });
        }
        const a = document.createElement('a');
        a.href = url;
        a.download = '';
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
    }).catch(err => {
        console.error('Export error:', err);
        alert('Ошибка сети при экспорте');
    });
}

function renderScheduleTable(data) {
    const days = data.days;
    const periods = data.periods;
    lessonsMap = {};
    const canEdit = isAdmin && (currentScheduleType === 'group' || currentScheduleType === 'teacher');

    let html = '<div class="schedule-table-wrap"><table class="schedule-table">';

    html += '<thead><tr>';
    html += '<th class="col-time">Пара</th>';
    for (const day of days) {
        const d = new Date(day.date + 'T00:00:00');
        const dayName = DAY_ORDER[d.getDay() === 0 ? 6 : d.getDay() - 1];
        html += `<th class="col-day">${dayName}<span class="day-date">${d.getDate()} ${MONTHS_SHORT[d.getMonth()]}</span></th>`;
    }
    html += '</tr></thead>';

    html += '<tbody>';
    let lastShift = 0;

    for (const period of periods) {
        if (period.shift !== lastShift) {
            lastShift = period.shift;
            html += `<tr class="shift-row"><td colspan="${days.length + 1}">${shiftLabel(period.shift)}</td></tr>`;
        }

        html += '<tr>';
        html += `<td class="time-cell"><span class="period-num">${period.period}</span>${period.start} – ${period.end}</td>`;

        for (const day of days) {
            const lessons = period.lessons[day.date] || [];
            const isBusy = lessons.length > 0;

            if (currentScheduleType === 'classroom') {
                if (isBusy) {
                    const inner = lessons.map(l => `<div class="lesson-content">
                        <div class="lesson-subject">${escapeHtml(l.subject)}</div>
                        <div class="lesson-meta">${escapeHtml(l.teacher)}\n${escapeHtml(l.groups || '')}</div>
                    </div>`).join('');
                    html += `<td class="day-cell busy-cell">${inner}</td>`;
                } else {
                    html += `<td class="day-cell empty-cell"></td>`;
                }
            } else {
                if (isBusy) {
                    const inner = lessons.map(l => {
                        lessonsMap[l.id] = l;
                        const meta = currentScheduleType === 'group'
                            ? `${escapeHtml(l.teacher)}${l.classroom ? ' \u00b7 ауд. ' + escapeHtml(l.classroom) : ''}${l.groups ? ' \u00b7 ' + escapeHtml(l.groups) : ''}`
                            : `${escapeHtml(l.groups || '')}${l.classroom ? ' \u00b7 ауд. ' + escapeHtml(l.classroom) : ''}`;
                        const onclick = canEdit ? ` onclick="editLesson(lessonsMap[${l.id}])"` : '';
                        return `<div class="lesson-content"${onclick}><div class="lesson-subject">${escapeHtml(l.subject)}</div><div class="lesson-meta">${meta}</div></div>`;
                    }).join('');
                    html += `<td class="day-cell${canEdit ? ' editable-cell' : ''}">${inner}</td>`;
                } else {
                    const dayId = day.day_id;
                    let onclick = '';
                    if (canEdit && (dayId || currentScheduleType === 'teacher')) {
                        if (currentScheduleType === 'teacher') {
                            onclick = ` onclick="showAddLessonModal(${dayId || 'null'}, ${period.period}, '${day.date}', null, ${currentScheduleId})"`;
                        } else {
                            onclick = ` onclick="showAddLessonModal(${dayId}, ${period.period}, ${currentScheduleId})"`;
                        }
                    }
                    html += `<td class="day-cell empty-cell${canEdit && (dayId || currentScheduleType === 'teacher') ? ' addable-cell' : ''}"${onclick}></td>`;
                }
            }
        }
        html += '</tr>';
    }

    html += '</tbody></table></div>';
    return html;
}

// ---- Homepage ----

async function loadHomePage() {
    await loadReferences();
    renderHomePage();
}

function renderHomePage() {
    const groupsContainer = document.getElementById('groups-grid');
    const teachersGrid = document.getElementById('teachers-grid');
    const classroomsGrid = document.getElementById('classrooms-grid');

    const regular = groupsList.filter(g => !g.is_distance);
    const distance = groupsList.filter(g => g.is_distance);

    if (regular.length === 0 && distance.length === 0) {
        groupsContainer.innerHTML = '<div class="empty-grid">\u041d\u0435\u0442 \u0433\u0440\u0443\u043f\u043f. \u0414\u043e\u0431\u0430\u0432\u044c\u0442\u0435 \u0447\u0435\u0440\u0435\u0437 \u0441\u043f\u0440\u0430\u0432\u043e\u0447\u043d\u0438\u043a\u0438.</div>';
    } else {
        let html = '';
        for (let c = 1; c <= 4; c++) {
            const courseGroups = regular.filter(g => g.course === c);
            if (courseGroups.length === 0) continue;
            html += `<div class="course-subsection">
                <h3 class="course-subtitle">\u041a\u0443\u0440\u0441 ${c}</h3>
                <div class="select-grid">${courseGroups.map(g =>
                    `<div class="select-card" onclick="showSchedule('group', ${g.id}, '${escapeHtml(g.name).replace(/'/g, "&#39;")}')">
                        <div class="select-card-title">${escapeHtml(g.name)}</div>
                        <div class="select-card-subtitle">\u0420\u0430\u0441\u043f\u0438\u0441\u0430\u043d\u0438\u0435 \u0433\u0440\u0443\u043f\u043f\u044b</div>
                    </div>`
                ).join('')}</div>
            </div>`;
        }
        if (regular.length > 0 && html === '') {
            html = `<div class="select-grid">${regular.map(g =>
                `<div class="select-card" onclick="showSchedule('group', ${g.id}, '${escapeHtml(g.name).replace(/'/g, "&#39;")}')">
                    <div class="select-card-title">${escapeHtml(g.name)}</div>
                    <div class="select-card-subtitle">\u0420\u0430\u0441\u043f\u0438\u0441\u0430\u043d\u0438\u0435 \u0433\u0440\u0443\u043f\u043f\u044b</div>
                </div>`
            ).join('')}</div>`;
        }
        groupsContainer.innerHTML = html;
    }

    const distContainer = document.getElementById('distance-grid');
    if (distContainer) {
        if (distance.length === 0) {
            distContainer.innerHTML = '<div class="empty-grid">\u041d\u0435\u0442 \u0437\u0430\u043e\u0447\u043d\u044b\u0445 \u0433\u0440\u0443\u043f\u043f.</div>';
        } else {
            distContainer.innerHTML = `<div class="select-grid">${distance.map(g =>
                `<div class="select-card" onclick="showSchedule('group', ${g.id}, '${escapeHtml(g.name).replace(/'/g, "&#39;")}')">
                    <div class="select-card-title">${escapeHtml(g.name)}</div>
                    <div class="select-card-subtitle">\u0420\u0430\u0441\u043f\u0438\u0441\u0430\u043d\u0438\u0435 \u0433\u0440\u0443\u043f\u043f\u044b</div>
                </div>`
            ).join('')}</div>`;
        }
    }

    if (teachersWithSchedule.length === 0) {
        teachersGrid.innerHTML = '<div class="empty-grid">\u041d\u0435\u0442 \u043f\u0440\u0435\u043f\u043e\u0434\u0430\u0432\u0430\u0442\u0435\u043b\u0435\u0439 \u0441 \u0440\u0430\u0441\u043f\u0438\u0441\u0430\u043d\u0438\u0435\u043c.</div>';
    } else {
        teachersGrid.innerHTML = teachersWithSchedule.map(t =>
            `<div class="select-card" onclick="showSchedule('teacher', ${t.id}, '${escapeHtml(t.name).replace(/'/g, "&#39;")}')">
                <div class="select-card-title">${escapeHtml(t.name)}</div>
                <div class="select-card-subtitle">\u0420\u0430\u0441\u043f\u0438\u0441\u0430\u043d\u0438\u0435 \u043f\u0440\u0435\u043f\u043e\u0434\u0430\u0432\u0430\u0442\u0435\u043b\u044f</div>
            </div>`
        ).join('');
    }

    if (classroomsWithSchedule.length === 0) {
        classroomsGrid.innerHTML = '<div class="empty-grid">\u041d\u0435\u0442 \u0430\u0443\u0434\u0438\u0442\u043e\u0440\u0438\u0439 \u0441 \u0437\u0430\u043d\u044f\u0442\u0438\u044f\u043c\u0438.</div>';
    } else {
        classroomsGrid.innerHTML = classroomsWithSchedule.map(c =>
            `<div class="select-card" onclick="showSchedule('classroom', ${c.id}, '${escapeHtml(c.name).replace(/'/g, "&#39;")}')">
                <div class="select-card-title">\u0410\u0443\u0434. ${escapeHtml(c.name)}</div>
                <div class="select-card-subtitle">\u0417\u0430\u043d\u044f\u0442\u043e\u0441\u0442\u044c</div>
            </div>`
        ).join('');
    }
}

// ---- Auth ----

async function login() {
    const data = await api('/api/auth/login', {
        method: 'POST',
        body: JSON.stringify({ password: document.getElementById('login-password').value }),
    });
    if (data.success) {
        isAdmin = true;
        csrfToken = data.csrf_token || '';
        closeModals();
        updateUI();
    } else alert('\u041d\u0435\u0432\u0435\u0440\u043d\u044b\u0439 \u043f\u0430\u0440\u043e\u043b\u044c');
}

async function logout() {
    await api('/api/auth/logout', { method: 'POST' });
    isAdmin = false;
    csrfToken = '';
    updateUI();
}

// ---- Modals ----

function openModal(id) {
    document.getElementById('modal-overlay').classList.add('active');
    document.getElementById(id).style.display = '';
}

function closeModals() {
    document.getElementById('modal-overlay').classList.remove('active');
    document.querySelectorAll('.modal').forEach(m => m.style.display = 'none');
    resetLessonModal();
}

function showLoginModal() {
    openModal('login-modal');
    document.getElementById('login-password').value = '';
    document.getElementById('login-password').focus();
}

// ---- Week ----

function showAddWeekModal() {
    openModal('add-week-modal');
    populateSelectByName('week-group', groupsList, '\u2014 \u0432\u044b\u0431\u0440\u0430\u0442\u044c \u0433\u0440\u0443\u043f\u043f\u0443 \u2014');
    document.getElementById('week-start-date').value = toISODate(currentMonday || getMonday(new Date()));
    updateWeekPreview();
}

function updateWeekPreview() {
    const dateStr = document.getElementById('week-start-date').value;
    if (!dateStr) return;
    const monday = new Date(dateStr + 'T00:00:00');
    document.getElementById('week-preview').innerHTML = DAY_ORDER.map((name, i) => {
        const d = addDays(monday, i);
        return `<div class="week-preview-day"><span>${name}</span><span>${formatShortDate(toISODate(d))}</span></div>`;
    }).join('');
}

document.addEventListener('DOMContentLoaded', () => {
    const di = document.getElementById('week-start-date');
    if (di) di.addEventListener('change', updateWeekPreview);
});

async function addWeek() {
    const groupName = document.getElementById('week-group').value;
    const dateStr = document.getElementById('week-start-date').value;
    if (!dateStr) return alert('\u0412\u044b\u0431\u0435\u0440\u0438\u0442\u0435 \u0434\u0430\u0442\u0443 \u043f\u043e\u043d\u0435\u0434\u0435\u043b\u044c\u043d\u0438\u043a\u0430');
    if (!groupName) return alert('\u0412\u044b\u0431\u0435\u0440\u0438\u0442\u0435 \u0433\u0440\u0443\u043f\u043f\u0443');

    const monday = new Date(dateStr + 'T00:00:00');
    const days = DAY_ORDER.map((name, i) => ({
        day_name: name,
        date: toISODate(addDays(monday, i)),
        group_name: groupName,
    }));

    const dates = days.map(d => d.date);
    const check = await api('/api/validate-week', {
        method: 'POST',
        body: JSON.stringify({ group_name: groupName, dates }),
    });

    if (!check.ok) {
        const msg = check.warnings.map(w => w.message).join('\n');
        alert(msg);
        return;
    }

    const res = await api('/api/days/batch', { method: 'POST', body: JSON.stringify({ days }) });
    if (res.error) {
        alert(res.error);
        return;
    }
    closeModals();
    loadScheduleTable();
}

async function restoreWeek() {
    if (!currentMonday) return;
    if (!confirm('\u0412\u043e\u0441\u0441\u0442\u0430\u043d\u043e\u0432\u0438\u0442\u044c \u0432\u0441\u0435 \u0443\u0434\u0430\u043b\u0435\u043d\u043d\u044b\u0435 \u0434\u043d\u0438 \u0438 \u0443\u0440\u043e\u043a\u0438 \u0437\u0430 \u044d\u0442\u0443 \u043d\u0435\u0434\u0435\u043b\u044e?')) return;
    const monday = toISODate(currentMonday);
    const res = await api('/api/week/restore?monday=' + monday, { method: 'POST' });
    if (res.error) {
        alert(res.error);
        return;
    }
    alert('\u0412\u043e\u0441\u0441\u0442\u0430\u043d\u043e\u0432\u043b\u0435\u043d\u043e \u0434\u043d\u0435\u0439: ' + res.days_restored);
    loadScheduleTable();
}

async function deleteWeek() {
    if (!currentMonday) return;
    if (!confirm('\u0423\u0434\u0430\u043b\u0438\u0442\u044c \u0432\u0441\u0435 \u0434\u043d\u0438 \u0438 \u0443\u0440\u043e\u043a\u0438 \u0437\u0430 \u044d\u0442\u0443 \u043d\u0435\u0434\u0435\u043b\u044e?')) return;
    const monday = toISODate(currentMonday);
    const res = await api('/api/week?monday=' + monday, { method: 'DELETE' });
    if (res.error) {
        alert(res.error);
        return;
    }
    alert('\u0423\u0434\u0430\u043b\u0435\u043d\u043e \u0434\u043d\u0435\u0439: ' + res.days_deleted);
    loadScheduleTable();
}

// ---- Validation ----

let validationTimeout = null;

async function validateLesson() {
    clearTimeout(validationTimeout);
    validationTimeout = setTimeout(async () => {
        const dayId = currentLessonDayId;
        const period = parseInt(document.getElementById('lesson-period').value);
        const teacherId = parseInt(document.getElementById('lesson-teacher').value) || null;
        const classroomId = parseInt(document.getElementById('lesson-classroom').value) || null;
        const subjectId = parseInt(document.getElementById('lesson-subject').value) || null;
        const groupId = parseInt(document.getElementById('lesson-group').value) || null;
        const subgroup = parseInt(document.getElementById('lesson-subgroup').value) || null;

        if (!dayId || !period) return;

        const data = await api('/api/validate', {
            method: 'POST',
            body: JSON.stringify({ day_id: dayId, period, teacher_id: teacherId, classroom_id: classroomId, subject_id: subjectId, group_id: groupId, subgroup, exclude_lesson_id: currentEditLessonId }),
        });

        const warningsEl = document.getElementById('validation-warnings');
        const saveBtn = document.getElementById('btn-save-lesson');

        if (data.warnings && data.warnings.length > 0) {
            warningsEl.style.display = '';
            warningsEl.innerHTML = '<div class="validation-warnings">' +
                data.warnings.map(w => `<div class="validation-warning ${w.type === 'duplicate' ? 'warning' : 'error'}">
                    <span class="validation-warning-icon">${w.type === 'duplicate' ? '!' : '!!'}</span>
                    <span>${escapeHtml(w.message)}</span>
                </div>`).join('') + '</div>';

            const hasBlocking = data.warnings.some(w => w.type !== 'duplicate');
            if (saveBtn) {
                saveBtn.disabled = hasBlocking;
                if (hasBlocking) saveBtn.textContent = '\u0415\u0441\u0442\u044c \u043a\u043e\u043d\u0444\u043b\u0438\u043a\u0442';
            }
        } else {
            warningsEl.style.display = 'none';
            warningsEl.innerHTML = '';
            if (saveBtn) {
                saveBtn.disabled = false;
                saveBtn.textContent = currentEditLessonId ? '\u0421\u043e\u0445\u0440\u0430\u043d\u0438\u0442\u044c' : '\u0414\u043e\u0431\u0430\u0432\u0438\u0442\u044c';
            }
        }
    }, 300);
}

// ---- Lessons ----

function showAddLessonModal(dayId, period, dayGroup, dateStr, teacherId) {
    currentLessonDayId = dayId;
    currentLessonDate = dateStr || null;
    currentLessonDayGroup = dayGroup || '';
    currentEditLessonId = null;
    openModal('add-lesson-modal');

    document.querySelector('#add-lesson-modal h2').textContent = '\u041d\u043e\u0432\u044b\u0439 \u0443\u0440\u043e\u043a';
    document.getElementById('btn-save-lesson').textContent = '\u0414\u043e\u0431\u0430\u0432\u0438\u0442\u044c';
    document.getElementById('btn-save-lesson').disabled = false;
    document.getElementById('validation-warnings').style.display = 'none';
    document.getElementById('btn-delete-lesson').style.display = 'none';
    document.getElementById('btn-add-subgroup').style.display = 'none';

    const select = document.getElementById('lesson-period');
    select.innerHTML = bellSchedule.map(b =>
        `<option value="${b.period}" ${period && b.period === period ? 'selected' : ''}>${b.period}-\u044f \u043f\u0430\u0440\u0430 (${b.start} - ${b.end})</option>`
    ).join('');
    select.onchange = () => validateLesson();

    populateSelect('lesson-subject', subjectsList, '\u2014 \u0432\u044b\u0431\u0440\u0430\u0442\u044c \u2014');
    populateSelect('lesson-teacher', teachersList, '\u2014 \u0432\u044b\u0431\u0440\u0430\u0442\u044c \u2014');
    populateSelect('lesson-group', groupsList, '\u2014 \u0432\u044b\u0431\u0440\u0430\u0442\u044c \u2014');
    populateSelect('lesson-classroom', classroomsList, '\u2014 \u0432\u044b\u0431\u0440\u0430\u0442\u044c \u2014');

    var teacherField = document.getElementById('lesson-teacher');
    var groupLabel = document.querySelector('#add-lesson-modal .field-label[for="lesson-group"]');
    if (!groupLabel) {
        var labels = document.querySelectorAll('#add-lesson-modal .field-label');
        for (var i = 0; i < labels.length; i++) {
            if (labels[i].textContent === '\u0413\u0440\u0443\u043f\u043f\u0430' || labels[i].innerText === '\u0413\u0440\u0443\u043f\u043f\u0430') {
                groupLabel = labels[i];
                break;
            }
        }
    }

    if (currentScheduleType === 'teacher' && teacherId) {
        teacherField.value = teacherId;
        teacherField.disabled = true;
        document.getElementById('lesson-group').value = '';
    } else {
        teacherField.disabled = false;
        if (currentLessonDayGroup) {
            document.getElementById('lesson-group').value = currentLessonDayGroup;
        }
    }

    document.getElementById('lesson-subject').onchange = function() {
        const subjectId = parseInt(this.value);
        if (!subjectId) return;
        const subject = subjectsList.find(s => s.id === subjectId);
        if (subject && subject.default_teacher_id) {
            const teacherSelect = document.getElementById('lesson-teacher');
            const current = parseInt(teacherSelect.value);
            if (!teacherSelect.disabled && !current) teacherSelect.value = subject.default_teacher_id;
        }
        validateLesson();
    };

    document.getElementById('lesson-group').onchange = function() {
        document.getElementById('lesson-subgroup').value = '';
    };
}

async function addLesson() {
    const period = parseInt(document.getElementById('lesson-period').value);
    const subjectId = parseInt(document.getElementById('lesson-subject').value) || null;
    const teacherId = parseInt(document.getElementById('lesson-teacher').value) || null;
    const classroomId = parseInt(document.getElementById('lesson-classroom').value) || null;
    const groupId = parseInt(document.getElementById('lesson-group').value) || null;
    const subgroup = parseInt(document.getElementById('lesson-subgroup').value) || null;

    // Если day_id нет (teacher-режим, пустая ячейка) — сначала создаём день
    let dayId = currentLessonDayId;
    if (!dayId && currentLessonDate && groupId) {
        const dayNames = ['Понедельник', 'Вторник', 'Среда', 'Четверг', 'Пятница', 'Суббота'];
        const d = new Date(currentLessonDate + 'T00:00:00');
        const dayName = dayNames[d.getDay() === 0 ? 6 : d.getDay() - 1];
        const groupObj = groupsList.find(g => g.id === groupId);
        const groupName = groupObj ? groupObj.name : '';
        const dayRes = await api('/api/days', {
            method: 'POST',
            body: JSON.stringify({ day_name: dayName, date: currentLessonDate, group_name: groupName }),
        });
        if (dayRes.error) {
            alert(dayRes.error);
            return;
        }
        dayId = dayRes.id;
    }

    if (!dayId) {
        alert('Не удалось определить день для урока');
        return;
    }

    const res = await api(`/api/days/${dayId}/lessons`, {
        method: 'POST',
        body: JSON.stringify({ period, subject_id: subjectId, teacher_id: teacherId, classroom_id: classroomId, group_id: groupId, subgroup }),
    });
    if (res.error) {
        const warningsEl = document.getElementById('validation-warnings');
        warningsEl.style.display = '';
        warningsEl.innerHTML = '<div class="validation-warnings">' +
            (res.warnings || []).map(w => `<div class="validation-warning error">
                <span class="validation-warning-icon">!!</span><span>${escapeHtml(w)}</span>
            </div>`).join('') + '</div>';
        return;
    }
    closeModals();
    loadScheduleTable();
}

function editLesson(lesson) {
    currentLessonDayId = lesson.day_id || null;
    currentEditLessonId = lesson.id;
    openModal('add-lesson-modal');

    document.querySelector('#add-lesson-modal h2').textContent = '\u0420\u0435\u0434\u0430\u043a\u0442\u0438\u0440\u043e\u0432\u0430\u0442\u044c \u0443\u0440\u043e\u043a';
    document.getElementById('btn-save-lesson').textContent = '\u0421\u043e\u0445\u0440\u0430\u043d\u0438\u0442\u044c';
    document.getElementById('btn-save-lesson').disabled = false;
    document.getElementById('validation-warnings').style.display = 'none';
    document.getElementById('btn-delete-lesson').style.display = '';
    document.getElementById('btn-add-subgroup').style.display = '';

    const select = document.getElementById('lesson-period');
    select.innerHTML = bellSchedule.map(b =>
        `<option value="${b.period}" ${b.period === lesson.period ? 'selected' : ''}>${b.period}-\u044f \u043f\u0430\u0440\u0430 (${b.start} - ${b.end})</option>`
    ).join('');

    populateSelect('lesson-subject', subjectsList, '\u2014 \u0432\u044b\u0431\u0440\u0430\u0442\u044c \u2014');
    populateSelect('lesson-teacher', teachersList, '\u2014 \u0432\u044b\u0431\u0440\u0430\u0442\u044c \u2014');
    populateSelect('lesson-group', groupsList, '\u2014 \u0432\u044b\u0431\u0440\u0430\u0442\u044c \u2014');
    populateSelect('lesson-classroom', classroomsList, '\u2014 \u0432\u044b\u0431\u0440\u0430\u0442\u044c \u2014');

    document.getElementById('lesson-subject').value = lesson.subject_id || '';
    document.getElementById('lesson-teacher').value = lesson.teacher_id || '';
    document.getElementById('lesson-classroom').value = lesson.classroom_id || '';
    document.getElementById('lesson-group').value = lesson.group_id || '';
    document.getElementById('lesson-subgroup').value = lesson.subgroup || '';

    if (currentScheduleType === 'teacher') {
        document.getElementById('lesson-teacher').disabled = true;
    } else {
        document.getElementById('lesson-teacher').disabled = false;
    }

    document.getElementById('btn-save-lesson').onclick = () => saveLesson(lesson.id);
}

async function saveLesson(lessonId) {
    const groupId = parseInt(document.getElementById('lesson-group').value) || null;
    const subgroup = parseInt(document.getElementById('lesson-subgroup').value) || null;
    const res = await api(`/api/lessons/${lessonId}`, {
        method: 'PUT',
        body: JSON.stringify({
            subject_id: parseInt(document.getElementById('lesson-subject').value) || null,
            teacher_id: parseInt(document.getElementById('lesson-teacher').value) || null,
            classroom_id: parseInt(document.getElementById('lesson-classroom').value) || null,
            group_id: groupId,
            subgroup,
        }),
    });
    if (res.error) {
        const warningsEl = document.getElementById('validation-warnings');
        warningsEl.style.display = '';
        warningsEl.innerHTML = '<div class="validation-warnings">' +
            (res.warnings || []).map(w => `<div class="validation-warning error">
                <span class="validation-warning-icon">!!</span><span>${escapeHtml(w)}</span>
            </div>`).join('') + '</div>';
        return;
    }
    closeModals();
    loadScheduleTable();
}

function addSubgroupLesson() {
    const period = document.getElementById('lesson-period').value;
    const groupId = parseInt(document.getElementById('lesson-group').value) || null;
    const dayId = currentLessonDayId;
    closeModals();
    setTimeout(() => {
        showAddLessonModal(dayId, parseInt(period), groupId);
    }, 100);
}

async function deleteCurrentLesson() {
    if (!currentEditLessonId) return;
    if (!confirm('Удалить урок?')) return;
    await api(`/api/lessons/${currentEditLessonId}`, { method: 'DELETE' });
    closeModals();
    loadScheduleTable();
}

function resetLessonModal() {
    currentEditLessonId = null;
    currentLessonDate = null;
    document.querySelector('#add-lesson-modal h2').textContent = '\u041d\u043e\u0432\u044b\u0439 \u0443\u0440\u043e\u043a';
    const btn = document.getElementById('btn-save-lesson');
    btn.textContent = '\u0414\u043e\u0431\u0430\u0432\u0438\u0442\u044c';
    btn.disabled = false;
    btn.onclick = addLesson;
    document.getElementById('validation-warnings').style.display = 'none';
    document.getElementById('btn-delete-lesson').style.display = 'none';
    document.getElementById('btn-add-subgroup').style.display = 'none';
    document.getElementById('lesson-teacher').disabled = false;
}

// ---- References ----

function showAdminPanel() {
    openModal('references-modal');
    renderRefList('subjects', 'ref-subjects');
    renderRefList('teachers', 'ref-teachers');
    renderRefList('groups', 'ref-groups');
    renderRefList('classrooms', 'ref-classrooms');
    populateSubjectTeacherSelect();
}

function populateSubjectTeacherSelect() {
    const sel = document.getElementById('ref-subjects-teacher');
    if (!sel) return;
    sel.innerHTML = '<option value="">Без преподавателя</option>' +
        teachersList.map(t => `<option value="${t.id}">${escapeHtml(t.name)}</option>`).join('');
}

async function renderRefList(endpoint, containerId) {
    const items = await api(`/api/${endpoint}`);
    const container = document.getElementById(containerId);
    if (endpoint === 'subjects') subjectsList = items;
    if (endpoint === 'teachers') teachersList = items;
    if (endpoint === 'groups') groupsList = items;
    if (endpoint === 'classrooms') classroomsList = items;

    container.innerHTML = items.length === 0
        ? '<div style="font-size:13px;color:var(--text-secondary);padding:4px 0;">\u041f\u0443\u0441\u0442\u043e</div>'
        : items.map(i => {
            let extra = '';
            if (endpoint === 'groups') {
                extra = ` <span class="ref-item-tag">${i.course}\u043a.</span>${i.is_distance ? ' <span class="ref-item-tag tag-distance">\u0417\u0430\u043e\u0447\u043d.</span>' : ''}`;
            }
            if (endpoint === 'subjects' && i.default_teacher_id) {
                const teacher = teachersList.find(t => t.id === i.default_teacher_id);
                if (teacher) {
                    extra += ` <span class="ref-item-tag">${escapeHtml(teacher.name)}</span>`;
                }
            }
            return `<div class="ref-item">
                <span class="ref-item-name">${escapeHtml(i.name)}${extra}</span>
                <div class="ref-item-actions">
                    <button class="btn btn-ghost btn-sm" onclick="${endpoint === 'subjects' ? `editSubject(${i.id})` : `editGroup(${i.id})`}">\u0418\u0437\u043c</button>
                    <button class="btn btn-danger btn-sm" onclick="deleteRefItem('${endpoint}',${i.id},'${containerId}')">\u00d7</button>
                </div>
            </div>`;
        }).join('');
}

async function addGroup() {
    const input = document.getElementById('ref-groups-input');
    const name = input.value.trim();
    if (!name) return;
    const course = parseInt(document.getElementById('ref-groups-course').value);
    const is_distance = document.getElementById('ref-groups-distance').checked;
    const res = await api('/api/groups', { method: 'POST', body: JSON.stringify({ name, course, is_distance }) });
    if (res.error) { alert(res.error); return; }
    input.value = '';
    document.getElementById('ref-groups-distance').checked = false;
    renderRefList('groups', 'ref-groups');
}

async function editGroup(id) {
    const group = groupsList.find(g => g.id === id);
    if (!group) return;
    const newName = prompt('\u041d\u0430\u0437\u0432\u0430\u043d\u0438\u0435:', group.name);
    if (newName === null || !newName.trim()) return;
    const newCourse = prompt('\u041a\u0443\u0440\u0441 (1-4):', group.course);
    if (newCourse === null) return;
    const course = parseInt(newCourse) || group.course;
    const dist = confirm('\u0417\u0430\u043e\u0447\u043d\u043e\u0435 \u043e\u0442\u0434\u0435\u043b\u0435\u043d\u0438\u0435?');
    const res = await api(`/api/groups/${id}`, { method: 'PUT', body: JSON.stringify({ name: newName.trim(), course, is_distance: dist }) });
    if (res.error) { alert(res.error); return; }
    renderRefList('groups', 'ref-groups');
}

async function addSubject() {
    const input = document.getElementById('ref-subjects-input');
    const sel = document.getElementById('ref-subjects-teacher');
    const name = input.value.trim();
    if (!name) return;
    const body = { name };
    if (sel && sel.value) body.default_teacher_id = parseInt(sel.value);
    const res = await api('/api/subjects', { method: 'POST', body: JSON.stringify(body) });
    if (res.error) { alert(res.error); return; }
    input.value = '';
    if (sel) sel.value = '';
    renderRefList('subjects', 'ref-subjects');
}

async function editSubject(id) {
    const subject = subjectsList.find(s => s.id === id);
    if (!subject) return;
    const newName = prompt('Название предмета:', subject.name);
    if (newName === null || !newName.trim()) return;
    const teacherOptions = ['Без преподавателя', ...teachersList.map((t, i) => `${i + 1}. ${t.name}`)];
    const teacherStr = prompt('Номер преподавателя (или 0 для без преподавателя):\n' + teacherOptions.map((o, i) => `  ${i} — ${o}`).join('\n'), subject.default_teacher_id ? (() => { const idx = teachersList.findIndex(t => t.id === subject.default_teacher_id); return idx >= 0 ? idx + 1 : 0; })() : 0);
    if (teacherStr === null) return;
    const teacherIdx = parseInt(teacherStr);
    const body = { name: newName.trim() };
    if (teacherIdx > 0 && teacherIdx <= teachersList.length) {
        body.default_teacher_id = teachersList[teacherIdx - 1].id;
    } else {
        body.default_teacher_id = null;
    }
    const res = await api(`/api/subjects/${id}`, { method: 'PUT', body: JSON.stringify(body) });
    if (res.error) { alert(res.error); return; }
    renderRefList('subjects', 'ref-subjects');
}

async function advanceCourses() {
    if (!confirm('\u041f\u0435\u0440\u0435\u0432\u0435\u0441\u0442\u0438 \u0432\u0441\u0435 \u043a\u0443\u0440\u0441\u044b \u043d\u0430 +1?\n\u0413\u0440\u0443\u043f\u043f\u044b 4-\u0433\u043e \u043a\u0443\u0440\u0441\u0430 \u0431\u0443\u0434\u0443\u0442 \u0423\u0434\u0430\u043b\u0435\u043d\u044b.')) return;
    const res = await api('/api/groups/advance-courses', { method: 'POST' });
    if (res.success) {
        alert(`\u0413\u043e\u0442\u043e\u0432\u043e! \u0423\u0434\u0430\u043b\u0435\u043d\u043e \u0433\u0440\u0443\u043f\u043f: ${res.deleted}`);
        renderRefList('groups', 'ref-groups');
    }
}

async function addRefItem(endpoint, inputId, containerId) {
    const input = document.getElementById(inputId);
    const name = input.value.trim();
    if (!name) return;
    const res = await api(`/api/${endpoint}`, { method: 'POST', body: JSON.stringify({ name }) });
    if (res.error) { alert(res.error); return; }
    input.value = '';
    renderRefList(endpoint, containerId);
}

async function editRefItem(endpoint, id, oldName, containerId) {
    const newName = prompt('\u041d\u0430\u0437\u0432\u0430\u043d\u0438\u0435:', oldName);
    if (newName === null || !newName.trim()) return;
    await api(`/api/${endpoint}/${id}`, { method: 'PUT', body: JSON.stringify({ name: newName.trim() }) });
    renderRefList(endpoint, containerId);
}

async function deleteRefItem(endpoint, id, containerId) {
    if (!confirm('\u0423\u0434\u0430\u043b\u0438\u0442\u044c?')) return;
    await api(`/api/${endpoint}/${id}`, { method: 'DELETE' });
    renderRefList(endpoint, containerId);
}

async function quickAdd(endpoint, selectId) {
    const name = prompt('\u0412\u0432\u0435\u0434\u0438\u0442\u0435 \u043d\u0430\u0437\u0432\u0430\u043d\u0438\u0435:');
    if (!name || !name.trim()) return;
    const res = await api(`/api/${endpoint}`, { method: 'POST', body: JSON.stringify({ name: name.trim() }) });
    await loadReferences();
    const list = endpoint === 'subjects' ? subjectsList : endpoint === 'teachers' ? teachersList : endpoint === 'classrooms' ? classroomsList : groupsList;
    populateSelect(selectId, list, '\u2014 \u0432\u044b\u0431\u0440\u0430\u0442\u044c \u2014');
    document.getElementById(selectId).value = res.id || '';
}

async function quickAddGroup() {
    const name = prompt('\u041d\u043e\u043c\u0435\u0440 \u0433\u0440\u0443\u043f\u043f\u044b:');
    if (!name || !name.trim()) return;
    const res = await api('/api/groups', { method: 'POST', body: JSON.stringify({ name: name.trim(), course: 1, is_distance: false }) });
    if (res.error) { alert(res.error); return; }
    await loadReferences();
    populateSelectByName('week-group', groupsList, '\u2014 \u0432\u044b\u0431\u0440\u0430\u0442\u044c \u0433\u0440\u0443\u043f\u043f\u0443 \u2014');
    document.getElementById('week-group').value = name.trim();
}

// ---- Availability ----

function showAvailability() {
    document.getElementById('home-view').style.display = 'none';
    document.getElementById('schedule-view').style.display = 'none';
    document.getElementById('availability-view').style.display = '';
    document.getElementById('header-title').textContent = '← Свободные окна';
    availMonday = getMonday(new Date());
    updateUI();
    renderAvailCarousel();
    loadAvailability();
}

/* Изменение №5: исправлена карусель свободных окон */

function renderAvailCarousel() {
    const container = document.getElementById('avail-carousel');
    const weeks = getWeeksList();
    const selected = toISODate(availMonday);
    const todayStr = toISODate(getMonday(new Date()));
    const currentIndex = weeks.findIndex(w => w.date === selected);

    let html = '<div class="carousel-nav">';
    html += `<button class="carousel-arrow carousel-arrow-left${currentIndex <= 0 ? ' disabled' : ''}" id="avail-arrow-left" onclick="availCarouselSkip(-1)" title="\u2190 \u043f\u0440\u0435\u0434\u044b\u0434\u0443\u0449\u0430\u044f \u043d\u0435\u0434\u0435\u043b\u044f">\u00ab</button>`;
    html += '<div class="carousel-strip" id="avail-carousel-strip">';
    for (const w of weeks) {
        const cls = w.date === selected ? ' carousel-chip active' : w.date === todayStr ? ' carousel-chip today' : ' carousel-chip';
        html += `<div class="${cls}" data-date="${w.date}" onclick="selectAvailWeek('${w.date}')">
            <span class="chip-week">${w.weekNumber} неделя</span>
            <span class="chip-range">${formatChipRange(w.monday)}</span>
        </div>`;
    }
    html += '</div>';
    html += `<button class="carousel-arrow carousel-arrow-right${currentIndex >= weeks.length - 1 ? ' disabled' : ''}" id="avail-arrow-right" onclick="availCarouselSkip(1)" title="\u0441\u043b\u0435\u0434\u0443\u044e\u0449\u0430\u044f \u043d\u0435\u0434\u0435\u043b\u044f \u2192">\u00bb</button>`;
    html += '</div>';
    container.innerHTML = html;
}

function availSetActiveWeek() {
    const strip = document.getElementById('avail-carousel-strip');
    if (!strip) return;
    const selected = toISODate(availMonday);
    strip.querySelectorAll('.carousel-chip').forEach(chip => {
        chip.classList.toggle('active', chip.dataset.date === selected);
    });
    const active = strip.querySelector('.carousel-chip.active');
    if (active) {
        const stripRect = strip.getBoundingClientRect();
        const chipRect = active.getBoundingClientRect();
        const offset = chipRect.left - stripRect.left - (stripRect.width / 2) + (chipRect.width / 2);
        strip.scrollBy({ left: offset, behavior: 'smooth' });
    }

    const weeks = getWeeksList();
    const currentIndex = weeks.findIndex(w => w.date === selected);
    const leftArrow = document.getElementById('avail-arrow-left');
    const rightArrow = document.getElementById('avail-arrow-right');
    if (leftArrow) leftArrow.classList.toggle('disabled', currentIndex <= 0);
    if (rightArrow) rightArrow.classList.toggle('disabled', currentIndex >= weeks.length - 1);
}

function selectAvailWeek(dateStr) {
    availMonday = new Date(dateStr + 'T00:00:00');
    availSelectedDay = null;
    availSetActiveWeek();
    loadAvailability();
}

function availCarouselSkip(n) {
    availMonday = addDays(availMonday, n * 7);
    availSelectedDay = null;
    availSetActiveWeek();
    loadAvailability();
}

async function loadAvailability() {
    const monday = toISODate(availMonday);
    availData = await api(`/api/availability?monday=${monday}`);
    renderAvailDayTabs();
    renderAvailTable();
}

function renderAvailDayTabs() {
    const container = document.getElementById('avail-day-tabs');
    if (!availData) return;
    let html = `<div class="avail-day-tab ${!availSelectedDay ? 'active' : ''}" onclick="selectAvailDay(null)">Вся неделя</div>`;
    for (const d of availData.days) {
        const active = availSelectedDay === d.date ? ' active' : '';
        const short = DAY_ORDER.indexOf(d.day_name) >= 0 ? d.day_name.substring(0, 2) + ' ' + formatShortDate(d.date) : d.day_name;
        html += `<div class="avail-day-tab${active}" onclick="selectAvailDay('${d.date}')">${short}</div>`;
    }
    container.innerHTML = html;
}

function selectAvailDay(date) {
    availSelectedDay = date;
    renderAvailDayTabs();
    renderAvailTable();
}

function setAvailMode(mode) {
    availMode = mode;
    document.getElementById('avail-mode-teacher').classList.toggle('active', mode === 'teacher');
    document.getElementById('avail-mode-classroom').classList.toggle('active', mode === 'classroom');
    renderAvailTable();
}

function renderAvailTable() {
    if (!availData) return;
    const container = document.getElementById('avail-table-container');
    const freeOnly = document.getElementById('avail-free-only').checked;
    const showAll = document.getElementById('avail-show-all-periods').checked;

    const days = availSelectedDay
        ? availData.days.filter(d => d.date === availSelectedDay)
        : availData.days;

    const periods = showAll ? availData.periods : availData.periods.filter(p => p.period <= 6);

    const rows = availMode === 'teacher' ? availData.teachers : availData.classrooms;
    const busyMap = availMode === 'teacher' ? availData.teacher_busy : availData.classroom_busy;

    let html = '<table class="avail-table"><thead><tr><th>' + (availMode === 'teacher' ? 'Преподаватель' : 'Аудитория') + '</th>';
    const todayStr = toISODate(new Date());
    for (const d of days) {
        const isToday = d.date === todayStr;
        const todayCls = isToday ? ' avail-header-today' : '';
        for (let pi = 0; pi < periods.length; pi++) {
            const p = periods[pi];
            const sep = pi === 0 ? ' day-sep-left' : '';
            const cls = todayCls + sep;
            html += `<th class="${cls}"><div class="avail-day-label">${d.day_name}</div><div class="avail-period-label">${p.start}</div></th>`;
        }
    }
    html += '<th>Своб. пар</th></tr></thead><tbody>';

    for (const row of rows) {
        const rowBusy = busyMap[String(row.id)] || {};
        let hasFree = false;
        let freeCount = 0;
        const cells = [];
        for (let di = 0; di < days.length; di++) {
            const d = days[di];
            for (let pi = 0; pi < periods.length; pi++) {
                const p = periods[pi];
                const key = `${d.date}_${p.period}`;
                const info = rowBusy[key];
                const sep = pi === 0 ? ' day-sep-left' : '';
                const dayCls = ` day-${di % 2}`;
                if (info) {
                    const typeBadge = info.lesson_type
                        ? `<span class="lesson-type-badge lesson-type-${escapeHtml(info.lesson_type)}">${escapeHtml(info.lesson_type)}</span>`
                        : '';
                    let busyHtml = `<td class="avail-cell-busy${sep}"><div class="avail-busy-inner">`;
                    busyHtml += `<div class="busy-time">${p.start} \u2013 ${p.end}</div>`;
                    busyHtml += `<div class="busy-subject">${typeBadge}${escapeHtml(info.subject)}</div>`;
                    if (info.teacher) busyHtml += `<div class="busy-teacher">${escapeHtml(info.teacher)}</div>`;
                    if (info.classroom) busyHtml += `<div class="busy-classroom">\u0430\u0443\u0434. ${escapeHtml(info.classroom)}</div>`;
                    busyHtml += '</div></td>';
                    cells.push(busyHtml);
                } else {
                    hasFree = true;
                    freeCount++;
                    cells.push(`<td class="avail-cell-free${sep}${dayCls}">свободен</td>`);
                }
            }
        }
        if (freeOnly && !hasFree) continue;
        html += `<tr><td>${escapeHtml(row.name)}</td>${cells.join('')}<td class="avail-summary">${freeCount}</td></tr>`;
    }

    html += '</tbody></table>';
    container.innerHTML = html || '<div style="padding:20px;color:var(--text-secondary)">Все заняты</div>';
}

// ---- Init ----

async function init() {
    bellSchedule = await api('/api/bell-schedule');
    await checkAuth();
    loadHomePage();
}

document.getElementById('login-password').addEventListener('keydown', e => {
    if (e.key === 'Enter') login();
});

init();
