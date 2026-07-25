import state from './state.js';
import { DAY_ORDER } from './config.js';
import { escapeHtml, getMonday, addDays, toISODate, getWeekNumber, formatChipRange, formatDateRange, shiftLabel, populateSelect, populateSelectByName } from './utils.js';
import { api } from './api.js';

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

export function openModal(id) {
    document.getElementById('modal-overlay').classList.add('active');
    document.getElementById(id).style.display = '';
}

export function closeModals() {
    document.getElementById('modal-overlay').classList.remove('active');
    document.querySelectorAll('.modal').forEach(m => m.style.display = 'none');
    resetLessonModal();
}

export function showLoginModal() {
    openModal('login-modal');
    const p = document.getElementById('login-password');
    p.value = '';
    p.focus();
}

/* ======================== Carousel ======================== */

function getWeeksList() {
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
    if (!ds) return alert('Выберите дату понедельника');
    if (!gn) return alert('Выберите группу');
    const monday = new Date(ds + 'T00:00:00');
    const days = DAY_ORDER.map((n, i) => ({ day_name: n, date: toISODate(addDays(monday, i)), group_name: gn }));
    const check = await api('/api/validate-week', { method: 'POST', body: JSON.stringify({ group_name: gn, dates: days.map(d => d.date) }) });
    if (!check.ok) { alert(check.warnings.map(w => w.message).join('\n')); return; }
    const res = await api('/api/days/batch', { method: 'POST', body: JSON.stringify({ days }) });
    if (res.error) { alert(res.error); return; }
    closeModals();
    loadScheduleTable();
}

export async function restoreWeek() {
    if (!state.currentMonday) return;
    if (!confirm('Восстановить все удаленные дни и уроки за эту неделю?')) return;
    const m = toISODate(state.currentMonday);
    const res = await api('/api/week/restore?monday=' + m, { method: 'POST' });
    if (res.error) { alert(res.error); return; }
    alert('Восстановлено дней: ' + res.days_restored);
    loadScheduleTable();
}

export async function deleteWeek() {
    if (!state.currentMonday) return;
    if (!confirm('Удалить все дни и уроки за эту неделю?')) return;
    const m = toISODate(state.currentMonday);
    const res = await api('/api/week?monday=' + m, { method: 'DELETE' });
    if (res.error) { alert(res.error); return; }
    alert('Удалено дней: ' + res.days_deleted);
    loadScheduleTable();
}

/* ======================== Schedule Table ======================== */

export async function loadScheduleTable() {
    const cont = document.getElementById('schedule-table-container');
    cont.innerHTML = '<div class="loading">Загрузка...</div>';
    const ms = toISODate(state.currentMonday);
    let data;
    if (state.currentScheduleType === 'group') data = await api(`/api/schedule-table?group=${encodeURIComponent(state.currentScheduleName)}&monday=${ms}`);
    else if (state.currentScheduleType === 'teacher') data = await api(`/api/teacher-schedule-table?teacher_id=${state.currentScheduleId}&monday=${ms}`);
    else if (state.currentScheduleType === 'classroom') data = await api(`/api/classroom-schedule-table?classroom_id=${state.currentScheduleId}&monday=${ms}`);
    if (!data || !data.periods || !data.periods.length || data.week_exists === false) {
        cont.innerHTML = '<div class="no-schedule"><span class="emoji">📅</span><p>Нет расписания на эту неделю</p></div>';
        return;
    }
    cont.innerHTML = renderScheduleTable(data);
}

function checkConflictsForLesson(lesson, dayDate, period) {
    if (!state.showConflicts) return null;
    const conflicts = [];
    for (const id of Object.keys(state.lessonsMap)) {
        const other = state.lessonsMap[id];
        if (other.id === lesson.id) continue;
        if (other.period !== period) continue;
        if (other.day_id === lesson.day_id) {
            if (other.teacher_id && other.teacher_id === lesson.teacher_id) {
                conflicts.push({ type: 'error', msg: 'Преподаватель занят в этот период' });
            }
            if (other.classroom_id && other.classroom_id === lesson.classroom_id) {
                conflicts.push({ type: 'error', msg: 'Аудитория занята в этот период' });
            }
            if (other.group_id === lesson.group_id && (other.subgroup || null) === (lesson.subgroup || null)) {
                conflicts.push({ type: 'warning', msg: 'Дублирование урока для группы' });
            }
        }
    }
    if (conflicts.length === 0) return null;
    const hasError = conflicts.some(c => c.type === 'error');
    return { cls: hasError ? 'cell-conflict-error' : 'cell-conflict-warning', tooltip: conflicts.map(c => c.msg).join('; ') };
}

function renderScheduleTable(data) {
    const { days, periods } = data;
    Object.keys(state.lessonsMap).forEach(k => delete state.lessonsMap[k]);
    const canEdit = state.isAdmin && (state.currentScheduleType === 'group' || state.currentScheduleType === 'teacher');
    let html = '<div class="schedule-table-wrap"><table class="schedule-table"><thead><tr><th class="col-time">Пара</th>';
    for (const day of days) {
        const d = new Date(day.date + 'T00:00:00');
        const dn = DAY_ORDER[d.getDay() === 0 ? 6 : d.getDay() - 1];
        html += `<th class="col-day">${dn}<span class="day-date">${d.getDate()} ${['янв','фев','мар','апр','мая','июн','июл','авг','сен','окт','ноя','дек'][d.getMonth()]}</span></th>`;
    }
    html += '</tr></thead><tbody>';
    let lastShift = 0;
    for (const p of periods) {
        if (p.shift !== lastShift) { lastShift = p.shift; html += `<tr class="shift-row"><td colspan="${days.length + 1}">${shiftLabel(p.shift)}</td></tr>`; }
        html += '<tr>';
        html += `<td class="time-cell"><span class="period-num">${p.period}</span>${p.start} – ${p.end}</td>`;
        for (const day of days) {
            const lessons = p.lessons[day.date] || [];
            const busy = lessons.length > 0;
            if (state.currentScheduleType === 'classroom') {
                html += busy ? `<td class="day-cell busy-cell">${lessons.map(l => `<div class="lesson-content"><div class="lesson-subject">${escapeHtml(l.subject)}</div><div class="lesson-meta">${escapeHtml(l.teacher)}\n${escapeHtml(l.groups || '')}</div></div>`).join('')}</td>` : '<td class="day-cell empty-cell"></td>';
            } else {
                if (busy) {
                    const inner = lessons.map(l => {
                        state.lessonsMap[l.id] = l;
                        const meta = state.currentScheduleType === 'group' ? `${escapeHtml(l.teacher)}${l.classroom ? ' · ауд. ' + escapeHtml(l.classroom) : ''}${l.groups ? ' · ' + escapeHtml(l.groups) : ''}` : `${escapeHtml(l.groups || '')}${l.classroom ? ' · ауд. ' + escapeHtml(l.classroom) : ''}`;
                        const oc = canEdit ? ` onclick="editLesson(lessonsMap[${l.id}])"` : '';
                        const conflict = checkConflictsForLesson(l, day.date, p.period);
                        const cCls = conflict ? ' ' + conflict.cls : '';
                        const tip = conflict ? ` title="${escapeHtml(conflict.tooltip)}"` : '';
                        return `<div class="lesson-content${cCls}"${oc}${tip}><div class="lesson-subject">${escapeHtml(l.subject)}</div><div class="lesson-meta">${meta}</div></div>`;
                    }).join('');
                    html += `<td class="day-cell${canEdit ? ' editable-cell' : ''}">${inner}</td>`;
                } else {
                    const di = day.day_id;
                    let oc = '';
                    if (canEdit && (di || state.currentScheduleType === 'teacher')) {
                        oc = state.currentScheduleType === 'teacher' ? ` onclick="showAddLessonModal(${di || 'null'}, ${p.period}, '${day.date}', null, ${state.currentScheduleId})"` : ` onclick="showAddLessonModal(${di}, ${p.period}, ${state.currentScheduleId})"`;
                    }
                    html += `<td class="day-cell empty-cell${canEdit && (di || state.currentScheduleType === 'teacher') ? ' addable-cell' : ''}"${oc}></td>`;
                }
            }
        }
        html += '</tr>';
    }
    return html + '</tbody></table></div>';
}

export function printSchedule() {
    document.getElementById('print-title').textContent = state.currentScheduleName;
    document.getElementById('print-subtitle').textContent = `Неделя ${getWeekNumber(state.currentMonday)} · ${formatDateRange(state.currentMonday)}`;
    let style = document.getElementById('print-inline-style');
    if (!style) { style = document.createElement('style'); style.id = 'print-inline-style'; document.head.appendChild(style); }
    style.textContent = '@media print { body,td,th,.schedule-table,.schedule-table-wrap,main,#schedule-view,#schedule-table-container{background:white!important;color:black!important} td.day-cell{background:white!important;color:black!important} td.day-cell:not(.empty-cell){background:#f0f0f0!important} .lesson-content,.lesson-content .lesson-subject,.lesson-content .lesson-meta{color:black!important} .lesson-content .lesson-meta{color:#333!important} .lesson-subject{color:black!important} td.day-cell .lesson-content .lesson-subject{color:black!important;background:transparent!important} td.day-cell .lesson-content .lesson-meta{color:#333!important;background:transparent!important} td.day-cell .lesson-content{background:transparent!important;color:black!important} }';
    window.print();
}

/* ======================== Export ======================== */

export function exportSchedule(format) {
    const monday = toISODate(state.currentMonday);
    console.log('Export params:', { type: state.currentScheduleType, name: state.currentScheduleName, id: state.currentScheduleId, monday, format });
    const url = `/api/export?type=${encodeURIComponent(state.currentScheduleType)}&name=${encodeURIComponent(state.currentScheduleName)}&id=${encodeURIComponent(state.currentScheduleId)}&monday=${monday}&format=${format}`;
    fetch(url, { method: 'HEAD' }).then(res => {
        if (!res.ok) { return res.json().then(b => alert(b.error || `Ошибка экспорта (${res.status})`)).catch(() => alert(`Ошибка экспорта (${res.status})`)); }
        const a = document.createElement('a'); a.href = url; a.download = ''; document.body.appendChild(a); a.click(); document.body.removeChild(a);
    }).catch(() => alert('Ошибка сети при экспорте'));
}

/* ======================== Lessons ======================== */

export function showAddLessonModal(dayId, period, dayGroup, dateStr, teacherId) {
    state.currentLessonDayId = dayId;
    state.currentLessonDate = dateStr || null;
    state.currentLessonDayGroup = dayGroup || '';
    state.currentEditLessonId = null;
    openModal('add-lesson-modal');
    document.querySelector('#add-lesson-modal h2').textContent = 'Новый урок';
    const sBtn = document.getElementById('btn-save-lesson');
    sBtn.textContent = 'Добавить'; sBtn.disabled = false;
    document.getElementById('validation-warnings').style.display = 'none';
    document.getElementById('btn-delete-lesson').style.display = 'none';
    document.getElementById('btn-add-subgroup').style.display = 'none';
    const sel = document.getElementById('lesson-period');
    sel.innerHTML = state.bellSchedule.map(b => `<option value="${b.period}" ${period && b.period === period ? 'selected' : ''}>${b.period}-я пара (${b.start} - ${b.end})</option>`).join('');
    sel.onchange = () => validateLesson();
    populateSelect('lesson-subject', state.subjectsList, '— выбрать —');
    populateSelect('lesson-teacher', state.teachersList, '— выбрать —');
    populateSelect('lesson-group', state.groupsList, '— выбрать —');
    populateSelect('lesson-classroom', state.classroomsList, '— выбрать —');
    const tf = document.getElementById('lesson-teacher');
    if (state.currentScheduleType === 'teacher' && teacherId) { tf.value = teacherId; tf.disabled = true; document.getElementById('lesson-group').value = ''; }
    else { tf.disabled = false; if (state.currentLessonDayGroup) document.getElementById('lesson-group').value = state.currentLessonDayGroup; }
    document.getElementById('lesson-subject').onchange = function() {
        const sid = parseInt(this.value);
        if (!sid) return;
        const subj = state.subjectsList.find(s => s.id === sid);
        if (subj && subj.default_teacher_id) { const ts = document.getElementById('lesson-teacher'); if (!ts.disabled && !parseInt(ts.value)) ts.value = subj.default_teacher_id; }
        validateLesson();
    };
    document.getElementById('lesson-group').onchange = () => document.getElementById('lesson-subgroup').value = '';
}

async function collectLessonData() {
    return {
        period: parseInt(document.getElementById('lesson-period').value),
        subject_id: parseInt(document.getElementById('lesson-subject').value) || null,
        teacher_id: parseInt(document.getElementById('lesson-teacher').value) || null,
        classroom_id: parseInt(document.getElementById('lesson-classroom').value) || null,
        group_id: parseInt(document.getElementById('lesson-group').value) || null,
        subgroup: parseInt(document.getElementById('lesson-subgroup').value) || null,
    };
}

export async function addLesson() {
    const d = await collectLessonData();
    let dayId = state.currentLessonDayId;
    if (!dayId && state.currentLessonDate && d.group_id) {
        const dayNames = ['Понедельник', 'Вторник', 'Среда', 'Четверг', 'Пятница', 'Суббота'];
        const dt = new Date(state.currentLessonDate + 'T00:00:00');
        const dn = dayNames[dt.getDay() === 0 ? 6 : dt.getDay() - 1];
        const go = state.groupsList.find(g => g.id === d.group_id);
        const dayRes = await api('/api/days', { method: 'POST', body: JSON.stringify({ day_name: dn, date: state.currentLessonDate, group_name: go ? go.name : '' }) });
        if (dayRes.error) { alert(dayRes.error); return; }
        dayId = dayRes.id;
    }
    if (!dayId) { alert('Не удалось определить день для урока'); return; }
    const res = await api(`/api/days/${dayId}/lessons`, { method: 'POST', body: JSON.stringify(d) });
    if (res.error) {
        const el = document.getElementById('validation-warnings');
        el.style.display = '';
        el.innerHTML = '<div class="validation-warnings">' + (res.warnings || []).map(w => `<div class="validation-warning error"><span class="validation-warning-icon">!!</span><span>${escapeHtml(w)}</span></div>`).join('') + '</div>';
        return;
    }
    closeModals();
    loadScheduleTable();
}

export function editLesson(lesson) {
    state.currentLessonDayId = lesson.day_id || null;
    state.currentEditLessonId = lesson.id;
    openModal('add-lesson-modal');
    document.querySelector('#add-lesson-modal h2').textContent = 'Редактировать урок';
    const sBtn = document.getElementById('btn-save-lesson');
    sBtn.textContent = 'Сохранить'; sBtn.disabled = false;
    document.getElementById('validation-warnings').style.display = 'none';
    document.getElementById('btn-delete-lesson').style.display = '';
    document.getElementById('btn-add-subgroup').style.display = '';
    const sel = document.getElementById('lesson-period');
    sel.innerHTML = state.bellSchedule.map(b => `<option value="${b.period}" ${b.period === lesson.period ? 'selected' : ''}>${b.period}-я пара (${b.start} - ${b.end})</option>`).join('');
    populateSelect('lesson-subject', state.subjectsList, '— выбрать —');
    populateSelect('lesson-teacher', state.teachersList, '— выбрать —');
    populateSelect('lesson-group', state.groupsList, '— выбрать —');
    populateSelect('lesson-classroom', state.classroomsList, '— выбрать —');
    ['subject', 'teacher', 'classroom', 'group'].forEach(f => document.getElementById(`lesson-${f}`).value = lesson[`${f}_id`] || '');
    document.getElementById('lesson-subgroup').value = lesson.subgroup || '';
    document.getElementById('lesson-teacher').disabled = state.currentScheduleType === 'teacher';
    document.getElementById('btn-save-lesson').onclick = () => saveLesson(lesson.id);
}

export async function saveLesson(lessonId) {
    const d = await collectLessonData();
    const res = await api(`/api/lessons/${lessonId}`, { method: 'PUT', body: JSON.stringify(d) });
    if (res.error) {
        const el = document.getElementById('validation-warnings');
        el.style.display = '';
        el.innerHTML = '<div class="validation-warnings">' + (res.warnings || []).map(w => `<div class="validation-warning error"><span class="validation-warning-icon">!!</span><span>${escapeHtml(w)}</span></div>`).join('') + '</div>';
        return;
    }
    closeModals();
    loadScheduleTable();
}

export function addSubgroupLesson() {
    const d = document.getElementById('lesson-period');
    closeModals();
    setTimeout(() => showAddLessonModal(state.currentLessonDayId, parseInt(d.value), parseInt(document.getElementById('lesson-group').value) || null), 100);
}

export async function deleteCurrentLesson() {
    if (!state.currentEditLessonId) return;
    if (!confirm('Удалить урок?')) return;
    await api(`/api/lessons/${state.currentEditLessonId}`, { method: 'DELETE' });
    closeModals();
    loadScheduleTable();
}

function resetLessonModal() {
    state.currentEditLessonId = null;
    state.currentLessonDate = null;
    document.querySelector('#add-lesson-modal h2').textContent = 'Новый урок';
    const btn = document.getElementById('btn-save-lesson');
    btn.textContent = 'Добавить'; btn.disabled = false; btn.onclick = addLesson;
    document.getElementById('validation-warnings').style.display = 'none';
    document.getElementById('btn-delete-lesson').style.display = 'none';
    document.getElementById('btn-add-subgroup').style.display = 'none';
    document.getElementById('lesson-teacher').disabled = false;
}

function renderWarnings(el, warnings) {
    el.style.display = '';
    el.innerHTML = '<div class="validation-warnings">' + warnings.map(w => `<div class="validation-warning ${w.type === 'duplicate' ? 'warning' : 'error'}"><span class="validation-warning-icon">${w.type === 'duplicate' ? '!' : '!!'}</span><span>${escapeHtml(w.message)}</span></div>`).join('') + '</div>';
}

export function validateLesson() {
    clearTimeout(state.validationTimeout);
    state.validationTimeout = setTimeout(async () => {
        const dayId = state.currentLessonDayId;
        const d = await collectLessonData();
        if (!dayId || !d.period) return;
        const data = await api('/api/validate', { method: 'POST', body: JSON.stringify({ day_id: dayId, ...d, exclude_lesson_id: state.currentEditLessonId }) });
        const el = document.getElementById('validation-warnings');
        const btn = document.getElementById('btn-save-lesson');
        if (data.warnings && data.warnings.length) {
            renderWarnings(el, data.warnings);
            const blocking = data.warnings.some(w => w.type !== 'duplicate');
            if (btn) { btn.disabled = blocking; if (blocking) btn.textContent = 'Есть конфликт'; }
        } else {
            el.style.display = 'none'; el.innerHTML = '';
            if (btn) { btn.disabled = false; btn.textContent = state.currentEditLessonId ? 'Сохранить' : 'Добавить'; }
        }
    }, 300);
}

/* ======================== Homepage & References ======================== */

export async function loadReferences() {
    [state.subjectsList, state.teachersList, state.groupsList, state.classroomsList] = await Promise.all([
        api('/api/subjects'), api('/api/teachers'), api('/api/groups'), api('/api/classrooms'),
    ]);
    state.teachersWithSchedule = await api('/api/teachers');
    state.classroomsWithSchedule = await api('/api/classrooms');
}

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
}

function populateSubjectTeacherSelect() {
    const sel = document.getElementById('ref-subjects-teacher');
    if (!sel) return;
    sel.innerHTML = '<option value="">Без преподавателя</option>' + state.teachersList.map(t => `<option value="${t.id}">${escapeHtml(t.name)}</option>`).join('');
}

export async function renderRefList(endpoint, containerId) {
    const items = await api(`/api/${endpoint}`);
    const container = document.getElementById(containerId);
    if (endpoint === 'subjects') state.subjectsList = items;
    else if (endpoint === 'teachers') state.teachersList = items;
    else if (endpoint === 'groups') state.groupsList = items;
    else if (endpoint === 'classrooms') state.classroomsList = items;
    container.innerHTML = items.length ? items.map(i => {
        let extra = '';
        if (endpoint === 'groups') extra = ` <span class="ref-item-tag">${i.course}к.</span>${i.is_distance ? ' <span class="ref-item-tag tag-distance">Заочн.</span>' : ''}`;
        if (endpoint === 'subjects' && i.default_teacher_id) { const t = state.teachersList.find(t => t.id === i.default_teacher_id); if (t) extra += ` <span class="ref-item-tag">${escapeHtml(t.name)}</span>`; }
        return `<div class="ref-item"><span class="ref-item-name">${escapeHtml(i.name)}${extra}</span><div class="ref-item-actions"><button class="btn btn-ghost btn-sm" onclick="${endpoint === 'subjects' ? `editSubject(${i.id})` : `editGroup(${i.id})`}">Изм</button><button class="btn btn-danger btn-sm" onclick="deleteRefItem('${endpoint}',${i.id},'${containerId}')">×</button></div></div>`;
    }).join('') : '<div style="font-size:13px;color:var(--text-secondary);padding:4px 0;">Пусто</div>';
}

export async function addGroup() {
    const inp = document.getElementById('ref-groups-input');
    const name = inp.value.trim();
    if (!name) return;
    const res = await api('/api/groups', { method: 'POST', body: JSON.stringify({ name, course: parseInt(document.getElementById('ref-groups-course').value), is_distance: document.getElementById('ref-groups-distance').checked }) });
    if (res.error) { alert(res.error); return; }
    inp.value = ''; document.getElementById('ref-groups-distance').checked = false;
    renderRefList('groups', 'ref-groups');
}

export async function editGroup(id) {
    const g = state.groupsList.find(g => g.id === id);
    if (!g) return;
    const nn = prompt('Название:', g.name);
    if (nn === null || !nn.trim()) return;
    const nc = prompt('Курс (1-4):', g.course);
    if (nc === null) return;
    const dist = confirm('Заочное отделение?');
    const res = await api(`/api/groups/${id}`, { method: 'PUT', body: JSON.stringify({ name: nn.trim(), course: parseInt(nc) || g.course, is_distance: dist }) });
    if (res.error) { alert(res.error); return; }
    renderRefList('groups', 'ref-groups');
}

export async function addSubject() {
    const inp = document.getElementById('ref-subjects-input');
    const sel = document.getElementById('ref-subjects-teacher');
    const name = inp.value.trim();
    if (!name) return;
    const body = { name };
    if (sel && sel.value) body.default_teacher_id = parseInt(sel.value);
    const res = await api('/api/subjects', { method: 'POST', body: JSON.stringify(body) });
    if (res.error) { alert(res.error); return; }
    inp.value = ''; if (sel) sel.value = '';
    renderRefList('subjects', 'ref-subjects');
}

export async function editSubject(id) {
    const s = state.subjectsList.find(s => s.id === id);
    if (!s) return;
    const nn = prompt('Название предмета:', s.name);
    if (nn === null || !nn.trim()) return;
    const opts = ['Без преподавателя', ...state.teachersList.map((t, i) => `${i + 1}. ${t.name}`)];
    const ts = prompt('Номер преподавателя (или 0 для без преподавателя):\n' + opts.map((o, i) => `  ${i} — ${o}`).join('\n'), s.default_teacher_id ? state.teachersList.findIndex(t => t.id === s.default_teacher_id) + 1 : 0);
    if (ts === null) return;
    const ti = parseInt(ts);
    const body = { name: nn.trim() };
    if (ti > 0 && ti <= state.teachersList.length) body.default_teacher_id = state.teachersList[ti - 1].id;
    else body.default_teacher_id = null;
    const res = await api(`/api/subjects/${id}`, { method: 'PUT', body: JSON.stringify(body) });
    if (res.error) { alert(res.error); return; }
    renderRefList('subjects', 'ref-subjects');
}

export async function advanceCourses() {
    if (!confirm('Перевести все курсы на +1?\nГруппы 4-го курса будут Удалены.')) return;
    const res = await api('/api/groups/advance-courses', { method: 'POST' });
    if (res.success) { alert(`Готово! Удалено групп: ${res.deleted}`); renderRefList('groups', 'ref-groups'); }
}

export async function addRefItem(endpoint, inputId, containerId) {
    const inp = document.getElementById(inputId);
    const name = inp.value.trim();
    if (!name) return;
    const res = await api(`/api/${endpoint}`, { method: 'POST', body: JSON.stringify({ name }) });
    if (res.error) { alert(res.error); return; }
    inp.value = '';
    renderRefList(endpoint, containerId);
}

export async function deleteRefItem(endpoint, id, containerId) {
    if (!confirm('Удалить?\n\nВнимание: запись может использоваться в расписании.')) return;
    const res = await api(`/api/${endpoint}/${id}`, { method: 'DELETE' });
    if (res.error) {
        alert(res.error);
        return;
    }
    if (res.warning) alert(res.warning);
    renderRefList(endpoint, containerId);
}

export async function restoreRefItem(endpoint, id, containerId) {
    if (!confirm('Восстановить запись?')) return;
    const res = await api(`/api/${endpoint}/${id}/restore`, { method: 'POST' });
    if (res.error) {
        alert(res.error);
        return;
    }
    renderRefList(endpoint, containerId);
}

export async function quickAdd(endpoint, selectId) {
    const name = prompt('Введите название:');
    if (!name || !name.trim()) return;
    const res = await api(`/api/${endpoint}`, { method: 'POST', body: JSON.stringify({ name: name.trim() }) });
    await loadReferences();
    const lists = { subjects: state.subjectsList, teachers: state.teachersList, classrooms: state.classroomsList };
    populateSelect(selectId, lists[endpoint] || [], '— выбрать —');
    document.getElementById(selectId).value = res.id || '';
}

export async function quickAddGroup() {
    const name = prompt('Номер группы:');
    if (!name || !name.trim()) return;
    const res = await api('/api/groups', { method: 'POST', body: JSON.stringify({ name: name.trim(), course: 1, is_distance: false }) });
    if (res.error) { alert(res.error); return; }
    await loadReferences();
    populateSelectByName('week-group', state.groupsList, '— выбрать группу —');
    document.getElementById('week-group').value = name.trim();
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

export function showAvailability() {
    document.getElementById('home-view').style.display = 'none';
    document.getElementById('schedule-view').style.display = 'none';
    document.getElementById('availability-view').style.display = '';
    document.getElementById('header-title').textContent = '← Свободные окна';
    state.availMonday = getMonday(new Date());
    updateUI();
    renderAvailCarousel();
    loadAvailability();
}

function renderAvailCarousel() {
    const cont = document.getElementById('avail-carousel');
    const weeks = getWeeksList();
    const sel = toISODate(state.availMonday);
    const today = toISODate(getMonday(new Date()));
    const idx = weeks.findIndex(w => w.date === sel);
    let html = '<div class="carousel-nav">';
    html += `<button class="carousel-arrow carousel-arrow-left${idx <= 0 ? ' disabled' : ''}" id="avail-arrow-left" onclick="availCarouselSkip(-1)" title="← предыдущая неделя">«</button>`;
    html += '<div class="carousel-strip" id="avail-carousel-strip">';
    for (const w of weeks) {
        const cls = w.date === sel ? ' carousel-chip active' : w.date === today ? ' carousel-chip today' : ' carousel-chip';
        html += `<div class="${cls}" data-date="${w.date}" onclick="selectAvailWeek('${w.date}')"><span class="chip-week">${w.weekNumber} неделя</span><span class="chip-range">${formatChipRange(w.monday)}</span></div>`;
    }
    html += '</div>';
    html += `<button class="carousel-arrow carousel-arrow-right${idx >= weeks.length - 1 ? ' disabled' : ''}" id="avail-arrow-right" onclick="availCarouselSkip(1)" title="следующая неделя →">»</button></div>`;
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

export function selectAvailWeek(dateStr) {
    state.availMonday = new Date(dateStr + 'T00:00:00');
    state.availSelectedDay = null;
    availSetActiveWeek();
    loadAvailability();
}

export function availCarouselSkip(n) {
    state.availMonday = addDays(state.availMonday, n * 7);
    state.availSelectedDay = null;
    availSetActiveWeek();
    loadAvailability();
}

export async function loadAvailability() {
    state.availData = await api(`/api/availability?monday=${toISODate(state.availMonday)}`);
    renderAvailDayTabs();
    renderAvailTable();
}

function renderAvailDayTabs() {
    const cont = document.getElementById('avail-day-tabs');
    if (!state.availData) return;
    let html = `<div class="avail-day-tab ${!state.availSelectedDay ? 'active' : ''}" onclick="selectAvailDay(null)">Вся неделя</div>`;
    for (const d of state.availData.days) {
        const a = state.availSelectedDay === d.date ? ' active' : '';
        const short = d.day_name;
        html += `<div class="avail-day-tab${a}" onclick="selectAvailDay('${d.date}')">${short}</div>`;
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

function renderAvailTable() {
    if (!state.availData) return;
    const cont = document.getElementById('avail-table-container');
    const freeOnly = document.getElementById('avail-free-only').checked;
    const showAll = document.getElementById('avail-show-all-periods').checked;
    const days = state.availSelectedDay ? state.availData.days.filter(d => d.date === state.availSelectedDay) : state.availData.days;
    const periods = showAll ? state.availData.periods : state.availData.periods.filter(p => p.period <= 6);
    const rows = state.availMode === 'teacher' ? state.availData.teachers : state.availData.classrooms;
    const busyMap = state.availMode === 'teacher' ? state.availData.teacher_busy : state.availData.classroom_busy;
    let html = '<table class="avail-table"><thead><tr><th>' + (state.availMode === 'teacher' ? 'Преподаватель' : 'Аудитория') + '</th>';
    const todayStr = toISODate(new Date());
    for (const d of days) {
        const isToday = d.date === todayStr;
        for (let pi = 0; pi < periods.length; pi++) {
            const p = periods[pi];
            html += `<th class="${isToday ? ' avail-header-today' : ''}${pi === 0 ? ' day-sep-left' : ''}"><div class="avail-day-label">${d.day_name}</div><div class="avail-period-label">${p.start}</div></th>`;
        }
    }
    html += '<th>Своб. пар</th></tr></thead><tbody>';
    for (const row of rows) {
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
                    cells.push(`<td class="avail-cell-busy${pi === 0 ? ' day-sep-left' : ''}"><div class="avail-busy-inner"><div class="busy-time">${p.start} – ${p.end}</div><div class="busy-subject">${escapeHtml(info.subject)}</div>${info.teacher ? '<div class="busy-teacher">' + escapeHtml(info.teacher) + '</div>' : ''}${info.classroom ? '<div class="busy-classroom">ауд. ' + escapeHtml(info.classroom) + '</div>' : ''}</div></td>`);
                } else { freeCount++; cells.push(`<td class="avail-cell-free${pi === 0 ? ' day-sep-left' : ''} day-${di % 2}">свободен</td>`); }
            }
        }
        if (freeOnly && !freeCount) continue;
        html += `<tr><td>${escapeHtml(row.name)}</td>${cells.join('')}<td class="avail-summary">${freeCount}</td></tr>`;
    }
    html += '</tbody></table>';
    cont.innerHTML = html || '<div style="padding:20px;color:var(--text-secondary)">Все заняты</div>';
}
