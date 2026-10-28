import state from './state.js';
import { api } from './api.js';
import { escapeHtml, populateSelect, populateSelectByName } from './utils.js';
import { confirmModal, showKimiAlert, showKimiPrompt, showKimiSelect, triggerErrorShake, openModal } from './modal.js';
import { showToast } from './toast.js';
import { dispatchEvent, onEvent, REFERENCES_UPDATED, DATA_MUTATED } from './events.js';

const SHIFT_LABELS = { 1: '1 см.', 2: '2 см.' };
const ROOM_TYPE_LABELS = { gym: 'Спортзал', computer: 'Компьютерный', court: 'Зал суда', normal: 'Обычная' };

export async function loadReferences() {
    const refs = await Promise.all([
        api('/api/subjects'), api('/api/teachers'), api('/api/groups'), api('/api/classrooms'), api('/api/specialties'),
    ]);
    const labels = ['subjects', 'teachers', 'groups', 'classrooms', 'specialties'];
    for (let i = 0; i < refs.length; i++) {
        if (refs[i].error) { console.error('loadReferences failed:', labels[i], refs[i].error); return; }
    }
    state.subjectsList = refs[0];
    state.teachersList = refs[1];
    state.groupsList = refs[2];
    state.classroomsList = refs[3];
    state.specialtiesList = refs[4];
    populateGroupSpecialtySelect();
    const tws = await api('/api/teachers');
    if (tws.error) { console.error('loadReferences teachers:', tws.error); }
    else { state.teachersWithSchedule = tws; }
    const cws = await api('/api/classrooms');
    if (cws.error) { console.error('loadReferences classrooms:', cws.error); }
    else { state.classroomsWithSchedule = cws; }
}

export function populateGroupSpecialtySelect() {
    const sel = document.getElementById('ref-groups-specialty');
    if (!sel) return;
    const cur = sel.value;
    sel.innerHTML = '<option value="">Без специальности</option>' + (state.specialtiesList || []).map(s => `<option value="${s.id}">${escapeHtml(s.code + ' — ' + s.name)}</option>`).join('');
    sel.value = cur;
}

export function populateSubjectTeacherSelect() {
    const sel = document.getElementById('ref-subjects-teacher');
    if (!sel) return;
    sel.innerHTML = '<option value="">Без преподавателя</option>' + state.teachersList.map(t => `<option value="${t.id}">${escapeHtml(t.name)}</option>`).join('');
}

export async function renderRefList(endpoint, containerId) {
    const container = document.getElementById(containerId);
    if (!container) return;
    container.innerHTML = '<div class="skeleton skeleton-text"></div><div class="skeleton skeleton-card" style="height:34px"></div><div class="skeleton skeleton-card" style="height:34px;width:90%"></div>';
    const items = await api(`/api/${endpoint}`);
    if (items.error) { container.innerHTML = '<div style="font-size:13px;color:var(--danger)">Ошибка загрузки</div>'; return; }
    if (endpoint === 'subjects') state.subjectsList = items;
    else if (endpoint === 'teachers') state.teachersList = items;
    else if (endpoint === 'groups') state.groupsList = items;
    else if (endpoint === 'classrooms') state.classroomsList = items;
    else if (endpoint === 'specialties') { state.specialtiesList = items; populateGroupSpecialtySelect(); renderSpecialtiesTable(container, items); return; }
    container.innerHTML = items.length ? items.map(i => {
        let extra = '';
        if (endpoint === 'groups') extra = ` <span class="ref-item-tag">${i.course}к.</span>${i.shift ? ` <span class="ref-item-tag">${SHIFT_LABELS[i.shift] || i.shift + ' см.'}</span>` : ''}${i.is_distance ? ' <span class="ref-item-tag tag-distance">Заочн.</span>' : ''}${i.specialty_code ? ` <span class="ref-item-tag tag-specialty">${escapeHtml(i.specialty_code)} · ${escapeHtml(i.specialty_name)}</span>` : ''}`;
        if (endpoint === 'subjects' && i.default_teacher_id) { const t = state.teachersList.find(t => t.id === i.default_teacher_id); if (t) extra += ` <span class="ref-item-tag">${escapeHtml(t.name)}</span>`; }
        if (endpoint === 'subjects' && i.required_room_type) extra += ` <span class="ref-item-tag tag-specialty">${escapeHtml(ROOM_TYPE_LABELS[i.required_room_type] || i.required_room_type)}</span>`;
        if (endpoint === 'classrooms' && i.room_type && i.room_type !== 'normal') extra += ` <span class="ref-item-tag tag-specialty">${escapeHtml(ROOM_TYPE_LABELS[i.room_type] || i.room_type)}</span>`;
        if (endpoint === 'teachers' && i.phone) extra += ` <span class="ref-item-tag tag-phone">${escapeHtml(i.phone)}</span>`;
        if (endpoint === 'specialties') {
            extra += ` <span class="ref-item-tag tag-code">${escapeHtml(i.code)}</span>`;
            if (i.qualification) extra += ` <span class="ref-item-tag tag-phone">${escapeHtml(i.qualification)}</span>`;
        }
        const editFn = endpoint === 'subjects' ? `editSubject(${i.id})` : endpoint === 'teachers' ? `editTeacher(${i.id})` : endpoint === 'classrooms' ? `editClassroom(${i.id})` : endpoint === 'specialties' ? `editSpecialty(${i.id})` : `editGroup(${i.id})`;
        return `<div class="ref-item"><span class="ref-item-name">${escapeHtml(i.name)}${extra}</span><div class="ref-item-actions"><button class="btn btn-ghost btn-xs" onclick="${editFn}">Изменить</button><button type="button" class="btn btn-danger btn-icon btn-sm delete-btn" data-endpoint="${endpoint}" data-id="${i.id}" data-container="${containerId}" aria-label="Удалить">×</button></div></div>`;
    }).join('') : '<div style="font-size:13px;color:var(--text-secondary);padding:4px 0;">Пусто</div>';
}

export async function addSpecialty() {
    const code = document.getElementById('ref-specialties-code').value.trim();
    const name = document.getElementById('ref-specialties-name').value.trim();
    if (!name) { triggerErrorShake(document.getElementById('ref-specialties-name')); return; }
    if (!code) { triggerErrorShake(document.getElementById('ref-specialties-code')); return; }
    const qualification = document.getElementById('ref-specialties-qualification').value.trim();
    const res = await api('/api/specialties', { method: 'POST', body: JSON.stringify({ code, name, qualification }) });
    if (res.error) { await showKimiAlert(res.error); return; }
    document.getElementById('ref-specialties-code').value = '';
    document.getElementById('ref-specialties-name').value = '';
    document.getElementById('ref-specialties-qualification').value = '';
    showToast('Специальность добавлена', 'success');
    dispatchEvent(REFERENCES_UPDATED);
    await loadSpecialties();
}

export async function editSpecialty(id) {
    const s = state.specialtiesList.find(x => x.id === id);
    if (!s) return;
    const nn = await showKimiPrompt('Название специальности:', s.name);
    if (nn === null || !nn.trim()) return;
    const cc = await showKimiPrompt('Код специальности:', s.code);
    if (cc === null) return;
    const qq = await showKimiPrompt('Направленность / квалификация:', s.qualification || '');
    if (qq === null) return;
    const res = await api(`/api/specialties/${id}`, { method: 'PUT', body: JSON.stringify({ name: nn.trim(), code: cc.trim(), qualification: (qq || '').trim() }) });
    if (res.error) { await showKimiAlert(res.error); return; }
    showToast('Специальность обновлена', 'success');
    dispatchEvent(REFERENCES_UPDATED);
    await loadSpecialties();
}

/** Отрисовка списка специальностей как таблицы (Код | Название | Квалификация).
 *  Вызывается при переключении на вкладку «Специальности». */
export async function loadSpecialties() {
    await renderRefList('specialties', 'ref-specialties');
}

function renderSpecialtiesTable(container, items) {
    if (!items.length) {
        container.innerHTML = '<div style="font-size:13px;color:var(--text-secondary);padding:4px 0;">Специальности не загружены. Нажмите «Добавить» для создания первой записи.</div>';
        return;
    }
    const rows = items.map(i => `
        <tr>
            <td class="ref-table-code">${escapeHtml(i.code)}</td>
            <td>${escapeHtml(i.name)}</td>
            <td>${escapeHtml(i.qualification || '')}</td>
            <td class="ref-table-actions">
                <button class="btn btn-ghost btn-xs" onclick="editSpecialty(${i.id})">Редактировать</button>
                <button type="button" class="btn btn-danger btn-xs delete-btn" data-endpoint="specialties" data-id="${i.id}" data-container="ref-specialties">Удалить</button>
            </td>
        </tr>`).join('');
    container.innerHTML = `<table class="ref-table"><thead><tr><th>Код</th><th>Название</th><th>Квалификация / Направленность</th><th></th></tr></thead><tbody>${rows}</tbody></table>`;
}

export async function addGroup() {
    const inp = document.getElementById('ref-groups-input');
    const name = inp.value.trim();
    if (!name) { triggerErrorShake(inp); return; }
    const specialtySel = document.getElementById('ref-groups-specialty');
    const specialty_id = specialtySel && specialtySel.value ? parseInt(specialtySel.value) : null;
    const shiftSel = document.getElementById('ref-groups-shift');
    const shift = shiftSel && shiftSel.value ? parseInt(shiftSel.value) : null;
    const res = await api('/api/groups', { method: 'POST', body: JSON.stringify({ name, course: parseInt(document.getElementById('ref-groups-course').value), is_distance: document.getElementById('ref-groups-distance').checked, specialty_id, shift }) });
    if (res.error) { await showKimiAlert(res.error); return; }
    inp.value = ''; document.getElementById('ref-groups-distance').checked = false; if (specialtySel) specialtySel.value = '';
    if (shiftSel) shiftSel.value = '';
    dispatchEvent(REFERENCES_UPDATED);
    renderRefList('groups', 'ref-groups');
}

export async function editGroup(id) {
    const g = state.groupsList.find(g => g.id === id);
    if (!g) return;
    const nn = await showKimiPrompt('Название:', g.name);
    if (nn === null || !nn.trim()) return;
    const nc = await showKimiPrompt('Курс (1-4):', String(g.course));
    if (nc === null) return;
    // confirmModal отдаёт только true/false, поэтому отмену было не отличить от «Очно»,
    // и отмена записывала is_distance: false. Спрашиваем выбором: «Очно» → false, «Заочно» → true,
    // отмена (null) → выходим, ничего не меняя.
    const distOpt = await showKimiSelect('Заочное отделение?', [
        { value: '0', label: 'Очно' },
        { value: '1', label: 'Заочно' },
    ], g.is_distance ? '1' : '0');
    if (distOpt === null) return;
    const dist = distOpt === '1';
    const spOpts = [{ value: '', label: 'Без специальности' }, ...(state.specialtiesList || []).map(s => ({ value: String(s.id), label: `${s.code} — ${s.name}` }))];
    const sp = await showKimiSelect('Специальность:', spOpts, g.specialty_id ? String(g.specialty_id) : '');
    if (sp === null) return;
    const sh = await showKimiSelect('Смена обучения:', [
        { value: '', label: 'Не указана (старт с 1-й пары)' },
        { value: '1', label: '1 смена (с 8:30)' },
        { value: '2', label: '2 смена (с 13:30)' },
    ], g.shift ? String(g.shift) : '');
    if (sh === null) return;
    const res = await api(`/api/groups/${id}`, { method: 'PUT', body: JSON.stringify({ name: nn.trim(), course: parseInt(nc) || g.course, is_distance: dist, specialty_id: sp ? parseInt(sp) : null, shift: sh ? parseInt(sh) : null }) });
    if (res.error) { await showKimiAlert(res.error); return; }
    dispatchEvent(REFERENCES_UPDATED);
    renderRefList('groups', 'ref-groups');
}

export async function addSubject() {
    const inp = document.getElementById('ref-subjects-input');
    const sel = document.getElementById('ref-subjects-teacher');
    const name = inp.value.trim();
    if (!name) { triggerErrorShake(inp); return; }
    const body = { name };
    const roomSel = document.getElementById('ref-subjects-room');
    if (roomSel && roomSel.value) body.required_room_type = roomSel.value;
    if (sel && sel.value) body.default_teacher_id = parseInt(sel.value);
    const res = await api('/api/subjects', { method: 'POST', body: JSON.stringify(body) });
    if (res.error) { await showKimiAlert(res.error); return; }
    inp.value = ''; if (sel) sel.value = ''; if (roomSel) roomSel.value = '';
    dispatchEvent(REFERENCES_UPDATED);
    renderRefList('subjects', 'ref-subjects');
}

export async function editTeacher(id) {
    const t = state.teachersList.find(t => t.id === id);
    if (!t) return;
    const nn = await showKimiPrompt('ФИО преподавателя:', t.name);
    if (nn === null || !nn.trim()) return;
    const tp = await showKimiPrompt('Телефон:', t.phone || '');
    if (tp === null) return;
    const res = await api(`/api/teachers/${id}`, { method: 'PUT', body: JSON.stringify({ name: nn.trim(), phone: tp.trim() }) });
    if (res.error) { await showKimiAlert(res.error); return; }
    dispatchEvent(REFERENCES_UPDATED);
    renderRefList('teachers', 'ref-teachers');
}

export async function editClassroom(id) {
    const c = state.classroomsList.find(c => c.id === id);
    if (!c) return;
    const nn = await showKimiPrompt('Название аудитории:', c.name);
    if (nn === null || !nn.trim()) return;
    const rt = await showKimiSelect('Тип аудитории:', [
        { value: 'normal', label: 'Обычная' },
        { value: 'gym', label: 'Спортзал' },
        { value: 'computer', label: 'Компьютерный класс' },
        { value: 'court', label: 'Зал суда' },
    ], c.room_type || 'normal');
    if (rt === null) return;
    const res = await api(`/api/classrooms/${id}`, { method: 'PUT', body: JSON.stringify({ name: nn.trim(), room_type: rt }) });
    if (res.error) { await showKimiAlert(res.error); return; }
    renderRefList('classrooms', 'ref-classrooms');
}

export async function editSubject(id) {
    const s = state.subjectsList.find(s => s.id === id);
    if (!s) return;
    const nn = await showKimiPrompt('Название предмета:', s.name);
    if (nn === null || !nn.trim()) return;
    const opts = ['Без преподавателя', ...state.teachersList.map((t, i) => `${i + 1}. ${t.name}`)];
    const ts = await showKimiPrompt('Номер преподавателя (или 0 для без преподавателя):\n' + opts.map((o, i) => `  ${i} — ${o}`).join('\n'), s.default_teacher_id ? String(state.teachersList.findIndex(t => t.id === s.default_teacher_id) + 1) : '0');
    if (ts === null) return;
    const ti = parseInt(ts);
    const body = { name: nn.trim() };
    if (!isNaN(ti) && ti > 0 && ti <= state.teachersList.length) body.default_teacher_id = state.teachersList[ti - 1].id;
    else body.default_teacher_id = null;
    const room = await showKimiSelect('Требуемая аудитория:', [
        { value: '', label: 'Любая обычная' },
        { value: 'gym', label: 'Спортзал' },
        { value: 'computer', label: 'Компьютерный класс' },
        { value: 'court', label: 'Зал суда' },
    ], s.required_room_type || '');
    if (room === null) return;
    body.required_room_type = room || null;
    const res = await api(`/api/subjects/${id}`, { method: 'PUT', body: JSON.stringify(body) });
    if (res.error) { await showKimiAlert(res.error); return; }
    dispatchEvent(REFERENCES_UPDATED);
    renderRefList('subjects', 'ref-subjects');
}

export async function advanceCourses() {
    if (!await confirmModal('Перевести все курсы на +1?\nГруппы 4-го курса будут Удалены.')) return;
    const res = await api('/api/groups/advance-courses', { method: 'POST' });
    if (res.success) { await showKimiAlert(`Готово! Удалено групп: ${res.deleted}`); dispatchEvent(REFERENCES_UPDATED); renderRefList('groups', 'ref-groups'); }
}

export function openImportModal(e) {
    if (e && typeof e.preventDefault === 'function') e.preventDefault();
    if (e && typeof e.stopPropagation === 'function') e.stopPropagation();
    const sel = document.getElementById('import-entity-type');
    if (sel) sel.value = 'teachers';
    const file = document.getElementById('import-file');
    if (file) file.value = '';
    const res = document.getElementById('import-result');
    if (res) res.innerHTML = '';
    const modal = document.getElementById('import-modal');
    if (modal) {
        modal.classList.remove('hidden');
        modal.style.setProperty('display', 'flex', 'important');
        modal.style.setProperty('z-index', '99999', 'important');
    }
    const overlay = document.getElementById('modal-overlay');
    if (overlay) overlay.classList.add('active');
}

export function closeImportModal(e) {
    if (e && typeof e.preventDefault === 'function') e.preventDefault();
    if (e && typeof e.stopPropagation === 'function') e.stopPropagation();
    const modal = document.getElementById('import-modal');
    if (modal) {
        modal.classList.add('hidden');
        modal.style.setProperty('display', 'none', 'important');
    }
    const overlay = document.getElementById('modal-overlay');
    if (overlay) overlay.classList.remove('active');
}

export async function downloadImportTemplate() {
    const sel = document.getElementById('import-entity-type');
    const entity = sel ? sel.value : 'teachers';
    try {
        const resp = await fetch(`/api/admin/import/template/${entity}`, {
            headers: state.csrfToken ? { 'X-CSRF-Token': state.csrfToken } : {},
        });
        if (!resp.ok) { const d = await resp.json(); await showKimiAlert(d.error || 'Ошибка скачивания шаблона'); return; }
        const blob = await resp.blob();
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `template_${entity}.xlsx`;
        document.body.appendChild(a);
        a.click();
        setTimeout(() => { document.body.removeChild(a); URL.revokeObjectURL(url); }, 200);
        showToast('Шаблон скачан', 'success');
    } catch (e) {
        await showKimiAlert('Не удалось скачать шаблон');
    }
}

export async function uploadImportExcel() {
    const sel = document.getElementById('import-entity-type');
    const entity = sel ? sel.value : 'teachers';
    const fileInput = document.getElementById('import-file');
    const result = document.getElementById('import-result');
    if (!fileInput.files || !fileInput.files.length) {
        await showKimiAlert('Выберите файл .xlsx');
        return;
    }
    const file = fileInput.files[0];
    if (!/\.xlsx$/i.test(file.name)) {
        await showKimiAlert('Только файлы .xlsx');
        return;
    }
    if (result) result.innerHTML = '<div class="loading">Загрузка...</div>';
    const fd = new FormData();
    fd.append('entity_type', entity);
    fd.append('file', file);
    try {
        const resp = await fetch('/api/admin/import/excel', {
            method: 'POST',
            headers: state.csrfToken ? { 'X-CSRF-Token': state.csrfToken } : {},
            body: fd,
        });
        const data = await resp.json();
        if (!resp.ok) {
            if (result) result.innerHTML = `<div style="color:var(--danger)">${escapeHtml(data.error || 'Ошибка импорта')}</div>`;
            return;
        }
        if (result) {
            let html = `<div style="color:var(--accent);font-weight:600">Импортировано записей: ${data.created}, пропущено: ${data.skipped}</div>`;
            if (data.errors && data.errors.length) {
                html += `<div style="margin-top:6px;color:var(--warning-text,#e6a700)">Предупреждения (${data.errors.length}):<ul style="margin:4px 0 0 16px;font-size:12px">`;
                html += data.errors.slice(0, 10).map(e => `<li>${escapeHtml(e)}</li>`).join('');
                html += '</ul></div>';
            }
            result.innerHTML = html;
        }
        showToast(`Импортировано: ${data.created}, пропущено: ${data.skipped}`, data.created ? 'success' : 'info');
        dispatchEvent(REFERENCES_UPDATED);
        const containerId = { teachers: 'ref-teachers', classrooms: 'ref-classrooms', groups: 'ref-groups', subjects: 'ref-subjects' }[entity];
        if (containerId) {
            await loadReferences();
            renderRefList(entity, containerId);
        }
    } catch (e) {
        if (result) result.innerHTML = '<div style="color:var(--danger)">Ошибка сети при импорте</div>';
    }
}

export async function addRefItem(endpoint, inputId, containerId) {
    const inp = document.getElementById(inputId);
    const name = inp.value.trim();
    if (!name) { triggerErrorShake(inp); return; }
    const body = { name };
    if (endpoint === 'teachers') { const phone = document.getElementById('ref-teachers-phone'); if (phone) body.phone = phone.value.trim(); }
    if (endpoint === 'classrooms') { const rt = document.getElementById('ref-classrooms-type'); if (rt && rt.value) body.room_type = rt.value; }
    const res = await api(`/api/${endpoint}`, { method: 'POST', body: JSON.stringify(body) });
    if (res.error) { await showKimiAlert(res.error); return; }
    inp.value = '';
    if (endpoint === 'teachers') { const phone = document.getElementById('ref-teachers-phone'); if (phone) phone.value = ''; }
    if (endpoint === 'classrooms') { const rt = document.getElementById('ref-classrooms-type'); if (rt) rt.value = 'normal'; }
    dispatchEvent(REFERENCES_UPDATED);
    renderRefList(endpoint, containerId);
}

export async function deleteRefItem(endpoint, id, containerId) {
    if (!await confirmModal('Удалить запись?')) return;
    const res = await api(`/api/${endpoint}/${id}`, { method: 'DELETE', silent: true });
    if (res.error) {
        await showKimiAlert(res.error);
        return;
    }
    showToast('Запись удалена', 'success');
    dispatchEvent(REFERENCES_UPDATED);
    renderRefList(endpoint, containerId);
}

document.addEventListener('click', async (e) => {
    const btn = e.target.closest('.delete-btn');
    if (!btn) return;
    e.preventDefault();
    e.stopPropagation();
    const endpoint = btn.dataset.endpoint;
    const id = btn.dataset.id;
    const containerId = btn.dataset.container;
    if (!endpoint || !id) return;
    await deleteRefItem(endpoint, id, containerId);
});

export async function restoreRefItem(endpoint, id, containerId) {
    if (!await confirmModal('Восстановить запись?')) return;
    const res = await api(`/api/${endpoint}/${id}/restore`, { method: 'POST' });
    if (res.error) { await showKimiAlert(res.error); return; }
    dispatchEvent(REFERENCES_UPDATED);
    renderRefList(endpoint, containerId);
}

export async function quickAdd(endpoint, selectId) {
    const name = await showKimiPrompt('Введите название:');
    if (!name || !name.trim()) return;
    const res = await api(`/api/${endpoint}`, { method: 'POST', body: JSON.stringify({ name: name.trim() }) });
    await loadReferences();
    dispatchEvent(REFERENCES_UPDATED);
    const lists = { subjects: state.subjectsList, teachers: state.teachersList, classrooms: state.classroomsList };
    populateSelect(selectId, lists[endpoint] || [], '— выбрать —');
    document.getElementById(selectId).value = res.id || '';
}

export async function quickAddGroup() {
    const name = await showKimiPrompt('Номер группы:');
    if (!name || !name.trim()) return;
    const res = await api('/api/groups', { method: 'POST', body: JSON.stringify({ name: name.trim(), course: 1, is_distance: false }) });
    if (res.error) { await showKimiAlert(res.error); return; }
    await loadReferences();
    dispatchEvent(REFERENCES_UPDATED);
    populateSelectByName('week-group', state.groupsList, '— выбрать группу —');
    document.getElementById('week-group').value = name.trim();
}

const ENTITY_SELECTS = {
    teachers: ['lesson-teacher', 'curriculum-teacher', 'ref-subjects-teacher'],
    subjects: ['lesson-subject', 'curriculum-subject'],
    groups:   ['lesson-group', 'curriculum-group', 'week-group'],
    classrooms: ['lesson-classroom'],
};

async function refetchEntity(entity) {
    const data = await api(`/api/${entity}`, { silent: true });
    if (data.error) return;
    if (entity === 'teachers') {
        state.teachersList = data;
        const tws = await api('/api/teachers', { silent: true });
        if (!tws.error) state.teachersWithSchedule = tws;
    } else if (entity === 'subjects') {
        state.subjectsList = data;
    } else if (entity === 'groups') {
        state.groupsList = data;
    } else if (entity === 'classrooms') {
        state.classroomsList = data;
        const cws = await api('/api/classrooms', { silent: true });
        if (!cws.error) state.classroomsWithSchedule = cws;
    } else if (entity === 'specialties') {
        state.specialtiesList = data;
        populateGroupSpecialtySelect();
    }
}

function refreshSelects(entity) {
    const list = entity === 'teachers' ? state.teachersList
        : entity === 'subjects' ? state.subjectsList
        : entity === 'groups' ? state.groupsList
        : entity === 'classrooms' ? state.classroomsList
        : null;
    if (!list) return;
    const ids = ENTITY_SELECTS[entity] || [];
    for (const id of ids) {
        const sel = document.getElementById(id);
        if (!sel) continue;
        const cur = sel.value;
        const useName = id === 'week-group';
        if (useName) {
            populateSelectByName(id, list, sel.options[0]?.text || '— выбрать —');
        } else {
            populateSelect(id, list, sel.options[0]?.text || '— выбрать —');
        }
        if (cur && Array.from(sel.options).some(o => o.value === cur)) {
            sel.value = cur;
        } else if (!useName && cur) {
            sel.value = '';
        }
    }
}

onEvent(DATA_MUTATED, (e) => {
    const { entity } = e.detail;
    if (['teachers', 'subjects', 'groups', 'classrooms', 'specialties'].includes(entity)) {
        refetchEntity(entity).then(() => refreshSelects(entity));
    }
});
