import state from './state.js';
import { DAY_ORDER } from './config.js';
import { escapeHtml, toISODate, getWeekNumber, getMonday, addDays, formatDateRange, formatChipRange, shiftLabel, populateSelect } from './utils.js';
import { api } from './api.js';
import { openModal, confirmModal, showKimiAlert } from './modal.js';
import { showToast } from './toast.js';
import { showLoader, hideLoader } from './loader.js';
import { dispatchEvent, onEvent, SCHEDULE_UPDATED, DATA_MUTATED, CURRICULUM_UPDATED } from './events.js';

function checkConflictsForLesson(lesson, dayDate, period) {
    if (!state.showConflicts) return null;
    const conflicts = [];
    for (const id of Object.keys(state.lessonsMap)) {
        const other = state.lessonsMap[id];
        if (other.id === lesson.id) continue;
        if (other.period !== period) continue;
        if (other.day_id === lesson.day_id) {
            if (other.teacher_id && other.teacher_id === lesson.teacher_id) conflicts.push({ type: 'error', msg: 'Преподаватель занят в этот период' });
            if (other.classroom_id && other.classroom_id === lesson.classroom_id) conflicts.push({ type: 'error', msg: 'Аудитория занята в этот период' });
            if (other.group_id === lesson.group_id && (other.subgroup || null) === (lesson.subgroup || null)) conflicts.push({ type: 'warning', msg: 'Дублирование пары для группы' });
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

    // Build excluded dates lookup
    const excludedByDate = {};
    if (data._excluded) {
        for (const ex of data._excluded) {
            const start = new Date(ex.start_date + 'T00:00:00');
            const end = new Date(ex.end_date + 'T00:00:00');
            for (const day of days) {
                const d = new Date(day.date + 'T00:00:00');
                if (d >= start && d <= end) {
                    if (!excludedByDate[day.date]) excludedByDate[day.date] = [];
                    excludedByDate[day.date].push(ex.reason || 'Праздничный день');
                }
            }
        }
    }

    let html = '<div class="schedule-table-wrap"><table class="schedule-table"><thead><tr><th class="col-time">Пара</th>';
    for (const day of days) {
        const d = new Date(day.date + 'T00:00:00');
        const dn = DAY_ORDER[d.getDay() === 0 ? 6 : d.getDay() - 1];
        const exc = excludedByDate[day.date];
        const excCls = exc ? ' style="background:var(--warning-bg);color:var(--warning-text)"' : '';
        html += `<th class="col-day"${excCls}>${dn}<span class="day-date">${d.getDate()} ${['янв','фев','мар','апр','мая','июн','июл','авг','сен','окт','ноя','дек'][d.getMonth()]}</span></th>`;
    }
    html += '</tr></thead><tbody>';

    // Excluded date banners
    for (const day of days) {
        const exc = excludedByDate[day.date];
        if (exc) {
            html += `<tr class="shift-row"><td colspan="${days.length + 1}" style="background:var(--warning-bg);color:var(--warning-text);font-size:12px;padding:8px;text-align:center">🚩 ${day.date} — ${exc.join('; ')}</td></tr>`;
        }
    }
    let lastShift = 0;
    for (const p of periods) {
        if (p.shift !== lastShift) { lastShift = p.shift; html += `<tr class="shift-row"><td colspan="${days.length + 1}">${shiftLabel(p.shift)}</td></tr>`; }
        html += '<tr>';
        html += `<td class="time-cell"><span class="period-num">${p.period}</span>${p.start} – ${p.end}</td>`;
        for (const day of days) {
            const isExcluded = excludedByDate[day.date];
            if (isExcluded) {
                html += `<td class="day-cell" style="background:var(--warning-bg);text-align:center;font-size:11px;color:var(--warning-text)">🚩 отменено</td>`;
                continue;
            }
            const lessons = p.lessons[day.date] || [];
            const busy = lessons.length > 0;
            if (state.currentScheduleType === 'classroom') {
                html += busy ? `<td class="day-cell busy-cell">${lessons.map(l => `<div class="lesson-content"><div class="lesson-subject">${escapeHtml(l.subject)}</div><div class="lesson-meta">${escapeHtml(l.teacher)}\n${escapeHtml(l.groups || '')}</div></div>`).join('')}</td>` : '<td class="day-cell empty-cell"></td>';
            } else {
                if (busy) {
                    const inner = lessons.map(l => {
                        state.lessonsMap[l.id] = l;
                        const isSub = l.is_substitution ? true : false;
                        const subCls = isSub ? ' lesson-substitution' : '';
                        let meta = state.currentScheduleType === 'group' ? `${escapeHtml(l.teacher)}${l.classroom ? ' · ауд. ' + escapeHtml(l.classroom) : ''}${l.groups ? ' · ' + escapeHtml(l.groups) : ''}` : `${escapeHtml(l.groups || '')}${l.classroom ? ' · ауд. ' + escapeHtml(l.classroom) : ''}`;
                        if (isSub) meta += ' 🔄 замена';
                        const oc = canEdit ? ` onclick="editLesson(lessonsMap[${l.id}])"` : '';
                        const conflict = checkConflictsForLesson(l, day.date, p.period);
                        const cCls = conflict ? ' ' + conflict.cls : '';
                        const tip = conflict ? ` title="${escapeHtml(conflict.tooltip)}"` : '';
                        return `<div class="lesson-content${cCls}${subCls}"${oc}${tip} style="${isSub ? 'background:var(--warning-bg);color:var(--warning-text)' : ''}"><div class="lesson-subject">${escapeHtml(l.subject)}</div><div class="lesson-meta">${meta}</div></div>`;
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

export async function loadScheduleTable() {
    showLoader('Загрузка расписания');
    const cont = document.getElementById('schedule-table-container');
    cont.innerHTML = '';
    const ms = toISODate(state.currentMonday);
    let data;
    if (state.currentScheduleType === 'group') data = await api(`/api/schedule-table?group=${encodeURIComponent(state.currentScheduleName)}&monday=${ms}`);
    else if (state.currentScheduleType === 'teacher') data = await api(`/api/teacher-schedule-table?teacher_id=${state.currentScheduleId}&monday=${ms}`);
    else if (state.currentScheduleType === 'classroom') data = await api(`/api/classroom-schedule-table?classroom_id=${state.currentScheduleId}&monday=${ms}`);
    if (!data || !data.periods || !data.periods.length || data.week_exists === false) {
        hideLoader();
        cont.innerHTML = '<div class="no-schedule"><span class="emoji">📅</span><p>Нет расписания на эту неделю</p></div>';
        return;
    }
    // Check excluded dates for this week
    const excluded = await api('/api/excluded-dates');
    if (excluded && !excluded.error && excluded.length) {
        data._excluded = excluded;
    }
    cont.innerHTML = renderScheduleTable(data);
    hideLoader();
}

export function printSchedule() {
    document.getElementById('print-title').textContent = state.currentScheduleName;
    document.getElementById('print-subtitle').textContent = `Неделя ${getWeekNumber(state.currentMonday)} · ${formatDateRange(state.currentMonday)}`;
    window.print();
}

export function exportSchedule(format) {
    if (!state.currentScheduleType || !state.currentMonday) {
        showToast('Сначала откройте расписание', 'info');
        return;
    }
    const monday = toISODate(state.currentMonday);
    const url = `/api/export?type=${encodeURIComponent(state.currentScheduleType)}&name=${encodeURIComponent(state.currentScheduleName)}&id=${encodeURIComponent(state.currentScheduleId)}&monday=${monday}&format=${format}`;
    const a = document.createElement('a'); a.href = url; a.download = ''; document.body.appendChild(a); a.click(); document.body.removeChild(a);
    setTimeout(() => document.body.removeChild(a), 1000);
}

export function smartExportExcel() {
    if (!state.currentScheduleType || !state.currentScheduleId || !state.currentMonday) {
        showToast('Сначала откройте расписание группы, преподавателя или аудитории', 'info');
        return;
    }
    const monday = toISODate(state.currentMonday);
    const url = `/api/schedule/export/excel?type=${encodeURIComponent(state.currentScheduleType)}&id=${state.currentScheduleId}&start_date=${monday}`;
    const a = document.createElement('a'); a.href = url; a.download = ''; document.body.appendChild(a); a.click(); document.body.removeChild(a);
    setTimeout(() => document.body.removeChild(a), 1000);
}

export async function generateFromCurriculum() {
    if (!state.currentScheduleType === 'group' || !state.currentScheduleId) {
        await showKimiAlert('Сначала откройте расписание группы');
        return;
    }
    const groupId = state.currentScheduleId;
    const monday = toISODate(state.currentMonday);
    const semester = await confirmModal('Сгенерировать расписание для группы на основе учебного плана?');
    if (!semester) return;
    const res = await api('/api/schedule/generate', {
        method: 'POST',
        body: JSON.stringify({ group_id: groupId, semester: 1, monday, week_count: 18 }),
    });
    if (res.error) { await showKimiAlert(res.error); return; }
    showToast(`Создано пар: ${res.created}`, 'success');
    dispatchEvent(SCHEDULE_UPDATED);
    loadScheduleTable();
}

export function showAddLessonModal(dayId, period, dayGroup, dateStr, teacherId) {
    state.currentLessonDayId = dayId;
    state.currentLessonDate = dateStr || null;
    state.currentLessonDayGroup = dayGroup || '';
    state.currentEditLessonId = null;
    openModal('add-lesson-modal');
    document.querySelector('#add-lesson-modal h2').textContent = 'Новый пара';
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
    document.getElementById('lesson-is-substitution').checked = false;
    document.getElementById('substitution-fields').style.display = 'none';
    document.getElementById('lesson-substitution-reason').value = '';
    populateSelect('lesson-original-teacher', state.teachersList, '— не указан —');
}

async function collectLessonData() {
    const isSub = document.getElementById('lesson-is-substitution').checked;
    return {
        period: parseInt(document.getElementById('lesson-period').value),
        subject_id: parseInt(document.getElementById('lesson-subject').value) || null,
        teacher_id: parseInt(document.getElementById('lesson-teacher').value) || null,
        classroom_id: parseInt(document.getElementById('lesson-classroom').value) || null,
        group_id: parseInt(document.getElementById('lesson-group').value) || null,
        subgroup: parseInt(document.getElementById('lesson-subgroup').value) || null,
        is_substitution: isSub,
        original_teacher_id: isSub ? (parseInt(document.getElementById('lesson-original-teacher').value) || null) : null,
        substitution_reason: isSub ? (document.getElementById('lesson-substitution-reason').value || null) : null,
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
        if (dayRes.error) { await showKimiAlert(dayRes.error); return; }
        dayId = dayRes.id;
    }
    if (!dayId) { await showKimiAlert('Не удалось определить день для пары'); return; }
    const res = await api(`/api/days/${dayId}/lessons`, { method: 'POST', body: JSON.stringify(d) });
    if (res.error) {
        const el = document.getElementById('validation-warnings');
        el.style.display = '';
        el.innerHTML = '<div class="validation-warnings">' + (res.warnings || []).map(w => `<div class="validation-warning error"><span class="validation-warning-icon">!!</span><span>${escapeHtml(w)}</span></div>`).join('') + '</div>';
        return;
    }
    window.closeModals();
    dispatchEvent(SCHEDULE_UPDATED);
    loadScheduleTable();
}

export function editLesson(lesson) {
    state.currentLessonDayId = lesson.day_id || null;
    state.currentEditLessonId = lesson.id;
    openModal('add-lesson-modal');
    document.querySelector('#add-lesson-modal h2').textContent = 'Редактировать пара';
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
    populateSelect('lesson-original-teacher', state.teachersList, '— не указан —');
    const isSub = lesson.is_substitution ? true : false;
    document.getElementById('lesson-is-substitution').checked = isSub;
    document.getElementById('substitution-fields').style.display = isSub ? '' : 'none';
    document.getElementById('lesson-substitution-reason').value = lesson.substitution_reason || '';
    document.getElementById('lesson-original-teacher').value = lesson.original_teacher_id || '';
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
    window.closeModals();
    dispatchEvent(SCHEDULE_UPDATED);
    loadScheduleTable();
}

export function addSubgroupLesson() {
    const d = document.getElementById('lesson-period');
    window.closeModals();
    setTimeout(() => showAddLessonModal(state.currentLessonDayId, parseInt(d.value), parseInt(document.getElementById('lesson-group').value) || null), 100);
}

export async function deleteCurrentLesson() {
    const lessonId = state.currentEditLessonId;
    if (!lessonId) return;
    if (!await confirmModal('Удалить пара?')) return;
    const res = await api(`/api/lessons/${lessonId}`, { method: 'DELETE' });
    if (res.error) { await showKimiAlert(res.error); return; }
    window.closeModals();
    dispatchEvent(SCHEDULE_UPDATED);
    loadScheduleTable();
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

onEvent(DATA_MUTATED, (e) => {
    if (['curriculum', 'holidays', 'groups', 'teachers', 'subjects', 'classrooms'].includes(e.detail.entity)) {
        const sv = document.getElementById('schedule-view');
        if (sv && sv.style.display !== 'none') {
            loadScheduleTable();
        }
    }
});
