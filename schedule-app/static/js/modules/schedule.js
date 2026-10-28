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
    const todayISO = toISODate(new Date());
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
        const isToday = day.date === todayISO;
        const cls = ['col-day'];
        if (exc) cls.push('is-excluded');
        if (isToday) cls.push('is-today');
        if (d.getDay() === 6) cls.push('is-weekend');
        html += `<th class="${cls.join(' ')}">${dn}<span class="day-date">${d.getDate()} ${['янв','фев','мар','апр','мая','июн','июл','авг','сен','окт','ноя','дек'][d.getMonth()]}</span></th>`;
    }
    html += '</tr></thead><tbody>';

    // Excluded date banners
    for (const day of days) {
        const exc = excludedByDate[day.date];
        if (exc) {
            html += `<tr class="shift-row shift-row--notice"><td colspan="${days.length + 1}">Исключение: ${escapeHtml(day.date)} — ${escapeHtml(exc.join('; '))}</td></tr>`;
        }
    }
    let lastShift = 0;
    for (const p of periods) {
        if (p.shift !== lastShift) { lastShift = p.shift; html += `<tr class="shift-row"><td colspan="${days.length + 1}">${shiftLabel(p.shift)}</td></tr>`; }
        html += '<tr data-period-row="' + p.period + '">';
        html += `<td class="time-cell"><span class="period-num">${p.period}</span><span class="period-time">${escapeHtml(p.start)} – ${escapeHtml(p.end)}</span></td>`;
        for (const day of days) {
            const isExcluded = excludedByDate[day.date];
            const isToday = day.date === todayISO;
            const isSaturday = new Date(day.date + 'T00:00:00').getDay() === 6;
            const dayCls = ['day-cell'];
            if (isToday) dayCls.push('is-today');
            if (isSaturday) dayCls.push('is-weekend');
            if (isExcluded) {
                html += `<td class="${dayCls.join(' ')} is-excluded">Отменено</td>`;
                continue;
            }
            const lessons = p.lessons[day.date] || [];
            const busy = lessons.length > 0;
            if (state.currentScheduleType === 'classroom') {
                html += busy
                    ? `<td class="${dayCls.join(' ')} busy-cell">${lessons.map(l => `<div class="lesson-content"><div class="lesson-subject">${escapeHtml(l.subject)}</div><div class="lesson-meta">${escapeHtml(l.teacher)}\n${escapeHtml(l.groups || '')}</div></div>`).join('')}</td>`
                    : `<td class="${dayCls.join(' ')} empty-cell"></td>`;
            } else {
                if (busy) {
                    const inner = lessons.map(l => {
                        state.lessonsMap[l.id] = l;
                        const isSub = l.is_substitution ? true : false;
                        const subCls = isSub ? ' is-substitution' : '';
                        const roomText = (l.classroom || '') + (l.classroom_2 ? ' / ' + l.classroom_2 : '');
                        let meta = state.currentScheduleType === 'group' ? `${escapeHtml(l.teacher)}${roomText ? ' · ауд. ' + escapeHtml(roomText) : ''}${l.groups ? ' · ' + escapeHtml(l.groups) : ''}` : `${escapeHtml(l.groups || '')}${roomText ? ' · ауд. ' + escapeHtml(roomText) : ''}`;
                        if (l.is_special_event) meta += ' · 📌 мероприятие';
                        if (isSub) meta += ' · замена';
                        const oc = canEdit ? ` onclick="editLesson(lessonsMap[${l.id}])"` : '';
                        const drag = canEdit ? ` draggable="true" data-lesson-id="${l.id}" data-day-id="${l.day_id || ''}" data-period="${p.period}"` : '';
                        const conflict = checkConflictsForLesson(l, day.date, p.period);
                        const cCls = conflict ? ' ' + conflict.cls : '';
                        const tip = conflict ? ` title="${escapeHtml(conflict.tooltip)}"` : '';
                        return `<div class="lesson-content${cCls}${subCls}"${oc}${drag}${tip}><div class="lesson-subject">${escapeHtml(l.subject)}</div><div class="lesson-meta">${meta}</div></div>`;
                    }).join('');
                    if (canEdit) dayCls.push('editable-cell');
                    html += `<td class="${dayCls.join(' ')}" data-day-id="${day.day_id || ''}" data-date="${day.date}" data-period="${p.period}">${inner}</td>`;
                } else {
                    const di = day.day_id;
                    let oc = '';
                    if (canEdit && (di || state.currentScheduleType === 'teacher')) {
                        // Порядок параметров: (dayId, period, dayGroup, dateStr, teacherId).
                        // Раньше дата попадала в dayGroup и терялся dateStr — день не определялся.
                        oc = state.currentScheduleType === 'teacher' ? ` onclick="showAddLessonModal(${di || 'null'}, ${p.period}, null, '${day.date}', ${state.currentScheduleId})"` : ` onclick="showAddLessonModal(${di}, ${p.period}, ${state.currentScheduleId})"`;
                    }
                    if (canEdit && (di || state.currentScheduleType === 'teacher')) dayCls.push('addable-cell');
                    html += `<td class="${dayCls.join(' ')} empty-cell" data-day-id="${di || ''}" data-date="${day.date}" data-period="${p.period}"${oc}></td>`;
                }
            }
        }
        html += '</tr>';
    }
    return html + '</tbody></table></div>';
}

function skeletonScheduleGrid() {
    let html = '<div class="schedule-table-wrap"><table class="skeleton-table"><thead><tr><th class="col-time"><span class="skeleton skeleton-text" style="width:70%"></span></th>';
    for (let d = 0; d < 6; d++) {
        html += '<th class="col-day"><span class="skeleton skeleton-text" style="width:75%"></span></th>';
    }
    html += '</tr></thead><tbody>';
    for (let p = 0; p < 8; p++) {
        html += '<tr><td class="time-cell"><span class="skeleton skeleton-text" style="width:55%;margin:2px auto"></span></td>';
        for (let d = 0; d < 6; d++) {
            html += '<td class="day-cell"><div class="skeleton skeleton-card"></div></td>';
        }
        html += '</tr>';
    }
    return html + '</tbody></table></div>';
}

// Токен запроса: ответ на старый клик по неделе не должен перерисовать таблицу поверх нового.
let _loadSeq = 0;

export async function loadScheduleTable() {
    const seq = ++_loadSeq;
    const cont = document.getElementById('schedule-table-container');
    cont.innerHTML = skeletonScheduleGrid();
    const ms = toISODate(state.currentMonday);
    let data;
    if (state.currentScheduleType === 'group') data = await api(`/api/schedule-table?group=${encodeURIComponent(state.currentScheduleName)}&monday=${ms}`);
    else if (state.currentScheduleType === 'teacher') data = await api(`/api/teacher-schedule-table?teacher_id=${state.currentScheduleId}&monday=${ms}`);
    else if (state.currentScheduleType === 'classroom') data = await api(`/api/classroom-schedule-table?classroom_id=${state.currentScheduleId}&monday=${ms}`);
    // Пока ждали ответ, пользователь мог выбрать другую неделю — устаревший ответ отбрасываем.
    if (seq !== _loadSeq) return;
    if (!data || !data.periods || !data.periods.length || data.week_exists === false) {
        const bar = document.getElementById('schedule-status-bar');
        if (bar) bar.style.display = 'none';
        cont.innerHTML = '<div class="no-schedule"><p>Нет расписания на эту неделю</p></div>';
        return;
    }
    // Check excluded dates for this week
    const excluded = await api('/api/excluded-dates');
    if (seq !== _loadSeq) return;
    if (excluded && !excluded.error && excluded.length) {
        data._excluded = excluded;
    }
    lastScheduleData = data;
    cont.innerHTML = renderScheduleTable(data);
    ensureDayTabs(data);
    renderPublishStatus(data);
    loadPlanProgress();
}

function renderPublishStatus(data) {
    const bar = document.getElementById('schedule-status-bar');
    if (!bar) return;
    if (state.currentScheduleType !== 'group' || !data || !Array.isArray(data.days)) {
        bar.style.display = 'none';
        return;
    }
    const days = data.days;
    const published = days.every(d => d.is_published !== false);
    const anyDay = days.some(d => d.day_id != null);
    if (!anyDay) {
        bar.style.display = 'none';
        return;
    }
    const editable = state.isAdmin;
    const actionAttr = editable
        ? 'data-action="toggleWeekPublish"'
        : 'disabled';
    const pubLabel = published ? 'Опубликовано' : 'Опубликовать';
    const draftLabel = published ? 'В черновик' : 'Черновик';
    const group = `
        <div class="publish-group" role="group" aria-label="Статус публикации недели">
            <button type="button" class="btn btn-sm publish-btn publish-published${published ? ' is-active' : ''}" ${actionAttr} data-params='[1]' aria-pressed="${published}" title="Опубликовать неделю">${pubLabel}</button>
            <button type="button" class="btn btn-sm publish-btn publish-draft${published ? '' : ' is-active'}" ${actionAttr} data-params='[0]' aria-pressed="${!published}" title="Перевести неделю в черновик">${draftLabel}</button>
        </div>`;
    bar.innerHTML = `<div class="schedule-status-wrap">${group}</div>`;
    bar.style.display = '';
}

/**
 * Мобильный переключатель дней (<=768px). Добавляет табы над таблицей и ставит
 * на контейнер data-view-day="N"; CSS показывает только колонку времени и день N.
 * DOM таблицы (tr/td) не перестраивается — меняется только атрибут.
 */
function ensureDayTabs(data) {
    const cont = document.getElementById('schedule-table-container');
    if (!cont || !data || !Array.isArray(data.days)) return;
    const wrap = cont.querySelector('.schedule-table-wrap');
    if (!wrap) return;

    let tabs = document.getElementById('mobile-day-tabs');
    if (!tabs) {
        tabs = document.createElement('div');
        tabs.id = 'mobile-day-tabs';
        tabs.className = 'mobile-day-tabs';
        tabs.setAttribute('role', 'tablist');
        tabs.setAttribute('aria-label', 'День недели');
        cont.insertBefore(tabs, wrap);
    }

    const days = data.days;
    const todayIso = toISODate(new Date());
    const todayIdx = days.findIndex(d => d.date === todayIso);
    const saved = parseInt(wrap.dataset.viewDay || '', 10);
    const active = saved >= 1 && saved <= days.length ? saved : (todayIdx >= 0 ? todayIdx + 1 : 1);

    tabs.innerHTML = days.map((d, i) => {
        const num = i + 1;
        const short = (d.day_name || '').slice(0, 2) || ['Пн', 'Вт', 'Ср', 'Чт', 'Пт', 'Сб'][i] || '';
        const date = d.date ? `${d.date.slice(8, 10)}.${d.date.slice(5, 7)}` : '';
        const isToday = d.date === todayIso ? ' is-today' : '';
        const on = num === active;
        return `<button type="button" class="mobile-day-tab${on ? ' active' : ''}${isToday}" data-day-index="${num}" role="tab" aria-selected="${on}" aria-pressed="${on}">${escapeHtml(short)}<span class="mobile-day-date">${escapeHtml(date)}</span></button>`;
    }).join('');

    wrap.dataset.viewDay = String(active);
}

// Один делегированный обработчик на все табы: переключаем атрибут и активный класс.
document.addEventListener('click', (e) => {
    const tab = e.target.closest('.mobile-day-tab');
    if (!tab) return;
    const wrap = document.querySelector('.schedule-table-wrap');
    if (!wrap) return;
    wrap.dataset.viewDay = tab.dataset.dayIndex;
    tab.parentElement.querySelectorAll('.mobile-day-tab').forEach(t => {
        const on = t === tab;
        t.classList.toggle('active', on);
        t.setAttribute('aria-selected', String(on));
        t.setAttribute('aria-pressed', String(on));
    });
});

export async function toggleWeekPublish(publish) {
    if (state.currentScheduleType !== 'group' || !state.currentScheduleName || !state.currentMonday) {
        showToast('Сначала откройте расписание группы', 'info');
        return;
    }
    const bar = document.getElementById('schedule-status-bar');
    const activeBtn = bar && bar.querySelector('[data-action="toggleWeekPublish"].is-active');
    if (activeBtn) {
        const current = JSON.parse(activeBtn.dataset.params)[0];
        if (current === publish) {
            showToast(publish ? 'Неделя уже опубликована' : 'Неделя уже в черновике', 'info');
            return;
        }
    }
    const monday = toISODate(state.currentMonday);
    const res = await api('/api/week/publish', {
        method: 'POST',
        body: JSON.stringify({ group_name: state.currentScheduleName, monday, is_published: publish ? 1 : 0 }),
    });
    if (res.error) { await showKimiAlert(res.error); return; }
    showToast(res.message || (res.is_published ? 'Неделя опубликована' : 'Неделя переведена в черновик'), 'success');
    dispatchEvent(SCHEDULE_UPDATED);
    loadScheduleTable();
}

export async function loadPlanProgress() {
    const box = document.getElementById('plan-progress-box');
    if (!box) return;
    if (state.currentScheduleType !== 'group' || !state.currentScheduleId) {
        box.style.display = 'none';
        return;
    }
    const monday = toISODate(state.currentMonday);
    const weekNum = getWeekNumber(state.currentMonday);
    box.style.display = '';
    const data = await api(`/api/curriculum/progress?group_id=${state.currentScheduleId}&semester=1&current_week=${weekNum}&total_weeks=16`);
    if (!data || data.error || !data.subjects) {
        box.innerHTML = '<div class="plan-progress-empty">План семестра не найден для этой группы</div>';
        return;
    }
    const weekNumber = data.current_week || weekNum || 6;
    const totalWeeks = data.total_weeks || 16;
    let html = `<div class="plan-progress-header">
        <h3>Выполнение плана семестра</h3>
        <p class="plan-progress-subtitle">
            Расчёт нагрузки к <b>${weekNum}-й неделе</b> из ${totalWeeks}.
            Показывает, успевает ли группа вычитать программу или есть отставание от графика.
        </p>
    </div>`;
    for (const s of data.subjects) {
        const pct = Math.min(s.percentage, 100);
        let badge = '';
        let badgeClass = 'badge-success';
        if (s.actual_pairs > s.expected_pairs) {
            badgeClass = 'badge-info';
            badge = `Опережаем график на +${s.actual_pairs - s.expected_pairs} пар${plural(s.actual_pairs - s.expected_pairs)}`;
        } else if (s.status === 'danger' && s.delta_pace < -4) {
            badgeClass = 'badge-danger';
            badge = `Сильное отставание (-${-s.delta_pace} пар)`;
        } else if (s.status === 'warning') {
            badgeClass = 'badge-warning';
            badge = `Отстаём от темпа на ${-s.delta_pace} пар${plural(-s.delta_pace)}`;
        } else {
            badge = 'Идём по графику';
        }
        const statusClass = s.status === 'danger' ? 'status-danger' : s.status === 'warning' ? 'status-warning' : 'status-success';
        const lag = s.delta_pace < 0;
        const tip = `По учебному плану на весь семестр положено ${s.plan_pairs} пар. ` +
            `К ${weekNum}-й неделе должно быть проведено около ${s.expected_pairs} пар. ` +
            `По факту в расписании стоит ${s.actual_pairs} пар. ` +
            (s.delta_pace === 0 ? 'Предмет идёт точно по плану.' :
                lag ? `Отставание составляет ${-s.delta_pace} пар${plural(-s.delta_pace)} (рекомендуется добавить этот предмет при генерации следующих недель).`
                     : `Опережение составляет ${s.delta_pace} пар${plural(s.delta_pace)}.`);
        html += `<div class="plan-card" title="${escapeHtml(tip)}">
            <div class="plan-card-title">${escapeHtml(s.name)} ${s.teacher_name ? '(' + escapeHtml(s.teacher_name) + ')' : ''}</div>
            <div class="plan-card-stats">
                <div class="plan-stat"><span class="plan-stat-label">Проведено (факт)</span><span class="plan-stat-value">${s.actual_pairs} пар${plural(s.actual_pairs)}</span></div>
                <div class="plan-stat"><span class="plan-stat-label">Норма к ${weekNum}-й неделе</span><span class="plan-stat-value">${s.expected_pairs} пар${plural(s.expected_pairs)}</span></div>
                <div class="plan-stat"><span class="plan-stat-label">Всего на семестр</span><span class="plan-stat-value">${s.plan_pairs} пар${plural(s.plan_pairs)}</span></div>
            </div>
            <div class="plan-progress-bar"><span class="${statusClass}" style="width:${pct}%"></span></div>
            <span class="badge ${badgeClass}">${badge}</span>
        </div>`;
    }
    box.innerHTML = html;
}

function plural(n) {
    const a = Math.abs(n) % 100;
    const b = a % 10;
    if (a > 10 && a < 20) return '';
    if (b > 1 && b < 5) return 'ы';
    if (b === 1) return 'у';
    return '';
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
    // Ссылка удаляется сразу; повторный removeChild в таймере падал с NotFoundError на каждом экспорте.
    const a = document.createElement('a'); a.href = url; a.download = ''; document.body.appendChild(a); a.click(); document.body.removeChild(a);
}

export function smartExportExcel() {
    if (!state.currentScheduleType || !state.currentScheduleId || !state.currentMonday) {
        showToast('Сначала откройте расписание группы, преподавателя или аудитории', 'info');
        return;
    }
    const monday = toISODate(state.currentMonday);
    const url = `/api/schedule/export/excel?type=${encodeURIComponent(state.currentScheduleType)}&id=${state.currentScheduleId}&start_date=${monday}`;
    // Ссылка удаляется сразу; повторный removeChild в таймере падал с NotFoundError на каждом экспорте.
    const a = document.createElement('a'); a.href = url; a.download = ''; document.body.appendChild(a); a.click(); document.body.removeChild(a);
}

/** Предупреждение о парах, которые не удалось разместить (коллизии/нет замены). */
function _generationWarning(res) {
    const errors = Array.isArray(res.errors) ? res.errors : [];
    if (!errors.length) return '';
    const shown = errors.slice(0, 3).map(e => `• ${e}`).join('\n');
    const more = errors.length > 3 ? `\n…и ещё ${errors.length - 3}` : '';
    return `\n\n⚠️ Не удалось разместить пар: ${errors.length}\n${shown}${more}`;
}

/** Галочка «Оптимизировать» в модалке генерации (по умолчанию включена). */
function _generateOptimizeFlag() {
    const box = document.getElementById('generate-optimize');
    return box ? box.checked : true;
}

export function showGenerateModal() {
    if (state.currentScheduleType !== 'group' || !state.currentScheduleId) {
        showKimiAlert('Сначала откройте расписание группы');
        return;
    }
    const box = document.getElementById('generate-optimize');
    if (box) box.checked = true;   // каждый раз по умолчанию включена
    openModal('generate-modal');
}

export async function generateFromCurriculum() {
    if (state.currentScheduleType !== 'group' || !state.currentScheduleId) {
        await showKimiAlert('Сначала откройте расписание группы');
        return;
    }
    const optimize = _generateOptimizeFlag();
    const groupId = state.currentScheduleId;
    const monday = toISODate(state.currentMonday);
    window.closeModals();
    showLoader('Собираем расписание по учебному плану...');
    const res = await api('/api/schedule/generate', {
        method: 'POST',
        body: JSON.stringify({ group_id: groupId, semester: 1, monday, week_count: 18, optimize }),
    });
    hideLoader();
    if (res.error) { await showKimiAlert(res.error); return; }
    const warning = _generationWarning(res);
    if (warning) {
        await showKimiAlert(`✅ Создано пар: ${res.created}${warning}`);
    } else {
        showToast(`Создано пар: ${res.created}`, 'success');
    }
    dispatchEvent(SCHEDULE_UPDATED);
    loadScheduleTable();
}

export async function generateMonth() {
    if (state.currentScheduleType !== 'group' || !state.currentScheduleId) {
        await showKimiAlert('Сначала откройте расписание группы');
        return;
    }
    const optimize = _generateOptimizeFlag();
    const groupId = state.currentScheduleId;
    const monday = toISODate(state.currentMonday);
    window.closeModals();
    showLoader('Собираем расписание на 4 недели...');
    const res = await api('/api/schedule/generate', {
        method: 'POST',
        body: JSON.stringify({ group_id: groupId, semester: 1, monday, weeks_count: 4, optimize }),
    });
    hideLoader();
    if (res.error) { await showKimiAlert(res.error); return; }
    await showKimiAlert(
        '✅ Месячный план успешно сгенерирован!\n\n' +
        `• Обработано недель: ${res.weeks_processed}\n` +
        `• Всего создано занятий: ${res.created}\n` +
        '• Отстающие дисциплины сбалансированы' + _generationWarning(res)
    );
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
    document.getElementById('btn-move-lesson').style.display = 'none';
    document.getElementById('move-lesson-block').style.display = 'none';
    document.getElementById('move-lesson-divider').style.display = 'none';
    const sel = document.getElementById('lesson-period');
    sel.innerHTML = state.bellSchedule.map(b => `<option value="${b.period}" ${period && b.period === period ? 'selected' : ''}>${b.period}-я пара (${escapeHtml(b.start)} - ${escapeHtml(b.end)})</option>`).join('');
    sel.onchange = () => validateLesson();
    populateSelect('lesson-subject', state.subjectsList, '— выбрать —');
    populateSelect('lesson-teacher', state.teachersList, '— выбрать —');
    populateSelect('lesson-group', state.groupsList, '— выбрать —');
    populateSelect('lesson-classroom', state.classroomsList, '— выбрать —');
    populateSelect('lesson-classroom-2', state.classroomsList, '— не нужна —');
    const specialBox = document.getElementById('lesson-is-special-event');
    if (specialBox) specialBox.checked = false;
    const specialFields = document.getElementById('special-event-fields');
    if (specialFields) specialFields.style.display = 'none';
    const room2 = document.getElementById('lesson-classroom-2');
    if (room2) room2.value = '';
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
    const subSel = document.getElementById('lesson-substitution-select');
    if (subSel) { subSel.innerHTML = '<option value="">— выберите заменяющего —</option>'; }
    const subNote = document.getElementById('substitution-note');
    if (subNote) subNote.textContent = '';
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
        classroom_id_2: parseInt(document.getElementById('lesson-classroom-2')?.value) || null,
        is_special_event: !!document.getElementById('lesson-is-special-event')?.checked,
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
    document.getElementById('btn-move-lesson').style.display = '';
    document.getElementById('move-lesson-block').style.display = 'none';
    document.getElementById('move-lesson-divider').style.display = 'none';
    const sel = document.getElementById('lesson-period');
    sel.innerHTML = state.bellSchedule.map(b => `<option value="${b.period}" ${b.period === lesson.period ? 'selected' : ''}>${b.period}-я пара (${escapeHtml(b.start)} - ${escapeHtml(b.end)})</option>`).join('');
    populateSelect('lesson-subject', state.subjectsList, '— выбрать —');
    populateSelect('lesson-teacher', state.teachersList, '— выбрать —');
    populateSelect('lesson-group', state.groupsList, '— выбрать —');
    populateSelect('lesson-classroom', state.classroomsList, '— выбрать —');
    populateSelect('lesson-classroom-2', state.classroomsList, '— не нужна —');
    ['subject', 'teacher', 'classroom', 'group'].forEach(f => document.getElementById(`lesson-${f}`).value = lesson[`${f}_id`] || '');
    const room2El = document.getElementById('lesson-classroom-2');
    if (room2El) room2El.value = lesson.classroom_id_2 || '';
    const specialEl = document.getElementById('lesson-is-special-event');
    const isSpecial = !!lesson.is_special_event;
    if (specialEl) specialEl.checked = isSpecial;
    const specialFieldsEl = document.getElementById('special-event-fields');
    if (specialFieldsEl) specialFieldsEl.style.display = isSpecial ? '' : 'none';
    document.getElementById('lesson-subgroup').value = lesson.subgroup || '';
    document.getElementById('lesson-teacher').disabled = state.currentScheduleType === 'teacher';
    populateSelect('lesson-original-teacher', state.teachersList, '— не указан —');
    const isSub = lesson.is_substitution ? true : false;
    document.getElementById('lesson-is-substitution').checked = isSub;
    document.getElementById('substitution-fields').style.display = isSub ? '' : 'none';
    document.getElementById('lesson-substitution-reason').value = lesson.substitution_reason || '';
    document.getElementById('lesson-original-teacher').value = lesson.original_teacher_id || '';
    const subSel = document.getElementById('lesson-substitution-select');
    if (subSel) subSel.innerHTML = '<option value="">— выберите заменяющего —</option>';
    if (isSub) refreshSubstitutionSuggest();
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

/* ---- Мобильный перенос урока ----
   На тач-устройствах HTML5 drag&drop не работает, поэтому перенос доступен
   через мини-форму в модалке: день + пара → частичный PUT (остальные поля целы). */

function _fillMoveSelects() {
    const shortDays = { 'Понедельник': 'Пн', 'Вторник': 'Вт', 'Среда': 'Ср', 'Четверг': 'Чт', 'Пятница': 'Пт', 'Суббота': 'Сб' };
    const daySel = document.getElementById('move-day');
    const perSel = document.getElementById('move-period');
    const days = (lastScheduleData && Array.isArray(lastScheduleData.days) ? lastScheduleData.days : [])
        .filter(d => d.day_id);
    daySel.innerHTML = days.map(d => {
        const date = d.date ? `${d.date.slice(8, 10)}.${d.date.slice(5, 7)}` : '';
        const label = `${shortDays[d.day_name] || (d.day_name || '').slice(0, 2)} ${date}`.trim();
        return `<option value="${d.day_id}"${d.day_id === state.currentLessonDayId ? ' selected' : ''}>${escapeHtml(label)}</option>`;
    }).join('');
    const periods = (Array.isArray(state.bellSchedule) && state.bellSchedule.length)
        ? state.bellSchedule.map(b => b.period)
        : Array.from({ length: 8 }, (_, i) => i + 1);
    const currentPeriod = parseInt(document.getElementById('lesson-period').value, 10) || null;
    perSel.innerHTML = periods.map(p =>
        `<option value="${p}"${p === currentPeriod ? ' selected' : ''}>${p}-я пара</option>`).join('');
}

export function showMoveForm() {
    if (!state.currentEditLessonId) {
        showToast('Сначала сохраните урок', 'info');
        return;
    }
    const hasDays = lastScheduleData && Array.isArray(lastScheduleData.days)
        && lastScheduleData.days.some(d => d.day_id);
    if (!hasDays) {
        showToast('Нет данных о днях этой недели', 'info');
        return;
    }
    _fillMoveSelects();
    const block = document.getElementById('move-lesson-block');
    block.style.display = '';
    document.getElementById('move-lesson-divider').style.display = '';
    // На телефоне модалка выше экрана — прокручиваем к форме, чтобы её было видно.
    block.scrollIntoView({ block: 'nearest', behavior: 'smooth' });
}

export function cancelMove() {
    document.getElementById('move-lesson-block').style.display = 'none';
    document.getElementById('move-lesson-divider').style.display = 'none';
}

export async function saveMove() {
    const lessonId = state.currentEditLessonId;
    if (!lessonId) return;
    const dayId = parseInt(document.getElementById('move-day').value, 10);
    const period = parseInt(document.getElementById('move-period').value, 10);
    if (!dayId || !period) {
        showToast('Выберите день и пару', 'error');
        return;
    }
    // Частичный PUT: subject/teacher/classroom/subgroup/замена остаются прежними
    const res = await api(`/api/lessons/${lessonId}`, {
        method: 'PUT',
        body: JSON.stringify({ day_id: dayId, period }),
    });
    if (res.error) {
        const el = document.getElementById('validation-warnings');
        el.style.display = '';
        el.innerHTML = '<div class="validation-warnings"><div class="validation-warning error">'
            + `<span class="validation-warning-icon">!!</span><span>${escapeHtml(res.error)}</span></div></div>`;
        return;
    }
    window.closeModals();
    dispatchEvent(SCHEDULE_UPDATED);
    await loadScheduleTable();
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

export async function refreshSubstitutionSuggest() {
    const sel = document.getElementById('lesson-substitution-select');
    if (!sel) return;
    const note = document.getElementById('substitution-note');
    if (note) note.textContent = '';
    const prev = sel.value;
    sel.innerHTML = '<option value="">— выберите заменяющего —</option>';
    const dayId = state.currentLessonDayId;
    const dateStr = state.currentLessonDate || null;
    const periodEl = document.getElementById('lesson-period');
    const period = periodEl ? parseInt(periodEl.value) : null;
    const teacherEl = document.getElementById('lesson-teacher');
    const excludeTeacherId = teacherEl && teacherEl.value ? parseInt(teacherEl.value) : undefined;
    const canResolve = (dayId || dateStr) && period;
    if (!canResolve) {
        if (note) note.textContent = 'Выберите день и пару, чтобы подобрать замену';
        return;
    }
    const params = new URLSearchParams();
    if (dateStr) params.set('date', dateStr);
    else params.set('day_id', dayId);
    if (period) params.set('period', period);
    if (excludeTeacherId) params.set('exclude_teacher_id', excludeTeacherId);
    const res = await api(`/api/schedule/substitutions-suggest?${params}`);
    const available = (res && !res.error && Array.isArray(res.available)) ? res.available : [];
    if (!available.length) {
        if (note) note.textContent = 'Свободных преподавателей на эту пару нет';
        return;
    }
    available.forEach(t => {
        const o = document.createElement('option');
        o.value = t.id;
        o.textContent = t.name;
        sel.appendChild(o);
    });
    if ([...sel.options].some(o => o.value === prev)) sel.value = prev;
}

export function pickSubstituteTeacher(teacherId) {
    const id = parseInt(teacherId);
    const tf = document.getElementById('lesson-teacher');
    const origSel = document.getElementById('lesson-original-teacher');
    if (!id) { if (tf) tf.value = ''; if (origSel) origSel.value = ''; validateLesson(); return; }
    if (tf) {
        const prevId = parseInt(tf.value);
        tf.value = id;
        tf.disabled = false;
        // Если основной (заменяемый) преподаватель ещё не выбран — им становится тот, кто был в поле до переключения
        if (origSel && !parseInt(origSel.value) && prevId && prevId !== id) origSel.value = prevId;
    }
    const reason = document.getElementById('lesson-substitution-reason');
    if (reason && !reason.value.trim()) reason.value = 'Замена';
    validateLesson();
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
        // silent: проверка идёт на каждое нажатие клавиши — тост «Успешно сохранено» был бы спамом.
        const data = await api('/api/validate', { method: 'POST', body: JSON.stringify({ day_id: dayId, ...d, exclude_lesson_id: state.currentEditLessonId }), silent: true });
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

/* ---------- Drag-and-Drop (перетаскивание пар мышкой) ---------- */

let lastScheduleData = null;
let activeDrag = null;

function bindScheduleDragAndDrop() {
    const cont = document.getElementById('schedule-table-container');
    if (!cont || cont.dataset.dndBound) return;
    cont.dataset.dndBound = '1';
    cont.addEventListener('dragstart', onCardDragStart);
    cont.addEventListener('dragend', onCardDragEnd);
    cont.addEventListener('dragover', onCellDragOver);
    cont.addEventListener('dragenter', onCellDragEnter);
    cont.addEventListener('dragleave', onCellDragLeave);
    cont.addEventListener('drop', onCellDrop);
}

function isLessonCard(el) {
    return el && el.classList && el.classList.contains('lesson-content') && el.getAttribute('draggable') === 'true';
}

function closestCell(el) {
    return el && el.closest ? el.closest('td.day-cell') : null;
}

function onCardDragStart(e) {
    const card = e.target.closest ? e.target.closest('.lesson-content[draggable="true"]') : null;
    if (!card) return;
    const payload = {
        lesson_id: parseInt(card.dataset.lessonId),
        source_day_id: parseInt(card.dataset.dayId) || null,
        source_period: parseInt(card.dataset.period) || null,
    };
    activeDrag = { card, payload };
    e.dataTransfer.effectAllowed = 'move';
    try { e.dataTransfer.setData('text/plain', JSON.stringify(payload)); } catch (_) { /* noop */ }
    card.classList.add('dragging');
}

function clearDragHover() {
    document.querySelectorAll('#schedule-table-container td.day-cell.drag-hover').forEach(c => c.classList.remove('drag-hover'));
}

function onCardDragEnd() {
    const card = activeDrag && activeDrag.card;
    if (card) card.classList.remove('dragging');
    activeDrag = null;
    clearDragHover();
}

function onCellDragOver(e) {
    if (!activeDrag) return;
    const cell = closestCell(e.target);
    if (!cell || !cell.dataset.dayId) return;
    e.preventDefault();
    e.dataTransfer.dropEffect = 'move';
    cell.classList.add('drag-hover');
}

function onCellDragEnter(e) {
    if (!activeDrag) return;
    const cell = closestCell(e.target);
    if (!cell || !cell.dataset.dayId) return;
    e.preventDefault();
    cell.classList.add('drag-hover');
}

function onCellDragLeave(e) {
    const cell = closestCell(e.target);
    if (!cell || !activeDrag) return;
    if (e.relatedTarget && cell.contains(e.relatedTarget)) return;
    cell.classList.remove('drag-hover');
}

function onCellDrop(e) {
    if (!activeDrag) return;
    const cell = closestCell(e.target);
    clearDragHover();
    if (!cell || !cell.dataset.dayId) return;
    e.preventDefault();

    let payload = activeDrag.payload;
    try {
        const raw = e.dataTransfer && e.dataTransfer.getData('text/plain');
        if (raw) {
            const parsed = JSON.parse(raw);
            if (parsed && parsed.lesson_id) payload = parsed;
        }
    } catch (_) { /* keep stored payload */ }

    const targetDayId = parseInt(cell.dataset.dayId) || null;
    const targetPeriod = parseInt(cell.dataset.period) || null;
    if (!payload.lesson_id || !targetDayId || !targetPeriod) return;
    if (payload.source_day_id === targetDayId && payload.source_period === targetPeriod) return;

    const card = activeDrag.card;
    activeDrag = null;
    if (card) card.classList.remove('dragging');
    moveLesson(payload.lesson_id, payload.source_period, targetDayId, targetPeriod, cell.dataset.date);
}

async function moveLesson(lessonId, sourcePeriod, targetDayId, targetPeriod, targetDate) {
    if (!lastScheduleData) return;
    const backup = JSON.parse(JSON.stringify(lastScheduleData));

    let moved = null;
    for (const p of lastScheduleData.periods) {
        if (p.period !== sourcePeriod) continue;
        for (const date of Object.keys(p.lessons)) {
            const arr = p.lessons[date];
            const idx = arr.findIndex(l => l.id === lessonId);
            if (idx !== -1) {
                moved = arr.splice(idx, 1)[0];
                break;
            }
        }
    }
    if (!moved) return;

    const targetPeriodObj = lastScheduleData.periods.find(p => p.period === targetPeriod);
    if (!targetPeriodObj) return;
    if (!targetPeriodObj.lessons[targetDate]) targetPeriodObj.lessons[targetDate] = [];
    moved.day_id = targetDayId;
    moved.period = targetPeriod;
    targetPeriodObj.lessons[targetDate].push(moved);

    const cont = document.getElementById('schedule-table-container');
    cont.innerHTML = renderScheduleTable(lastScheduleData);
    ensureDayTabs(lastScheduleData);

    const res = await api(`/api/lessons/${lessonId}`, {
        method: 'PUT',
        body: JSON.stringify({ day_id: targetDayId, period: targetPeriod }),
        silent: true,
    });
    if (res.error) {
        lastScheduleData = backup;
        cont.innerHTML = renderScheduleTable(backup);
        ensureDayTabs(backup);
        const cell = cont.querySelector(`td.day-cell[data-day-id="${targetDayId}"][data-period="${targetPeriod}"]`);
        if (cell) {
            cell.classList.add('drop-error');
            setTimeout(() => cell.classList.remove('drop-error'), 1200);
        }
        showToast((res.warnings && res.warnings.length ? res.warnings.join('; ') : res.error), 'warning');
        return;
    }
    showToast('Пара перемещена', 'success');
}

export function refreshScheduleTimeline() {
    const rows = document.querySelectorAll('tr[data-period-row]');
    const byPeriod = {};
    for (const s of (state.bellSchedule || [])) byPeriod[s.period] = s;
    for (const tr of rows) {
        const p = parseInt(tr.getAttribute('data-period-row'));
        const s = byPeriod[p];
        const cell = tr.querySelector('.time-cell');
        if (!cell || !s) continue;
        cell.innerHTML = `<span class="period-num">${s.period}</span>${escapeHtml(s.start)} – ${escapeHtml(s.end)}`;
    }
}

bindScheduleDragAndDrop();
