import state from './state.js';
import { api } from './api.js';
import { escapeHtml, populateSelect, populateSelectByName } from './utils.js';
import { confirmModal } from './modal.js';

export async function loadReferences() {
    const refs = await Promise.all([
        api('/api/subjects'), api('/api/teachers'), api('/api/groups'), api('/api/classrooms'),
    ]);
    const labels = ['subjects', 'teachers', 'groups', 'classrooms'];
    for (let i = 0; i < refs.length; i++) {
        if (refs[i].error) { console.error('loadReferences failed:', labels[i], refs[i].error); return; }
    }
    state.subjectsList = refs[0];
    state.teachersList = refs[1];
    state.groupsList = refs[2];
    state.classroomsList = refs[3];
    const tws = await api('/api/teachers');
    if (tws.error) { console.error('loadReferences teachers:', tws.error); }
    else { state.teachersWithSchedule = tws; }
    const cws = await api('/api/classrooms');
    if (cws.error) { console.error('loadReferences classrooms:', cws.error); }
    else { state.classroomsWithSchedule = cws; }
}

export function populateSubjectTeacherSelect() {
    const sel = document.getElementById('ref-subjects-teacher');
    if (!sel) return;
    sel.innerHTML = '<option value="">Без преподавателя</option>' + state.teachersList.map(t => `<option value="${t.id}">${escapeHtml(t.name)}</option>`).join('');
}

export async function renderRefList(endpoint, containerId) {
    const items = await api(`/api/${endpoint}`);
    const container = document.getElementById(containerId);
    if (!container) return;
    if (items.error) { container.innerHTML = '<div style="font-size:13px;color:var(--danger)">Ошибка загрузки</div>'; return; }
    if (endpoint === 'subjects') state.subjectsList = items;
    else if (endpoint === 'teachers') state.teachersList = items;
    else if (endpoint === 'groups') state.groupsList = items;
    else if (endpoint === 'classrooms') state.classroomsList = items;
    container.innerHTML = items.length ? items.map(i => {
        let extra = '';
        if (endpoint === 'groups') extra = ` <span class="ref-item-tag">${i.course}к.</span>${i.is_distance ? ' <span class="ref-item-tag tag-distance">Заочн.</span>' : ''}`;
        if (endpoint === 'subjects' && i.default_teacher_id) { const t = state.teachersList.find(t => t.id === i.default_teacher_id); if (t) extra += ` <span class="ref-item-tag">${escapeHtml(t.name)}</span>`; }
        if (endpoint === 'teachers' && i.phone) extra += ` <span class="ref-item-tag tag-phone">${escapeHtml(i.phone)}</span>`;
        const editFn = endpoint === 'subjects' ? `editSubject(${i.id})` : endpoint === 'teachers' ? `editTeacher(${i.id})` : endpoint === 'classrooms' ? `editClassroom(${i.id})` : `editGroup(${i.id})`;
        return `<div class="ref-item"><span class="ref-item-name">${escapeHtml(i.name)}${extra}</span><div class="ref-item-actions"><button class="btn btn-ghost btn-sm" onclick="${editFn}">Изм</button><button class="btn btn-danger btn-sm" onclick="deleteRefItem('${endpoint}',${i.id},'${containerId}')">×</button></div></div>`;
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
    const dist = await confirmModal('Заочное отделение?');
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

export async function editTeacher(id) {
    const t = state.teachersList.find(t => t.id === id);
    if (!t) return;
    const nn = prompt('ФИО преподавателя:', t.name);
    if (nn === null || !nn.trim()) return;
    const tp = prompt('Телефон:', t.phone || '');
    if (tp === null) return;
    const res = await api(`/api/teachers/${id}`, { method: 'PUT', body: JSON.stringify({ name: nn.trim(), phone: tp.trim() }) });
    if (res.error) { alert(res.error); return; }
    renderRefList('teachers', 'ref-teachers');
}

export async function editClassroom(id) {
    const c = state.classroomsList.find(c => c.id === id);
    if (!c) return;
    const nn = prompt('Название аудитории:', c.name);
    if (nn === null || !nn.trim()) return;
    const res = await api(`/api/classrooms/${id}`, { method: 'PUT', body: JSON.stringify({ name: nn.trim() }) });
    if (res.error) { alert(res.error); return; }
    renderRefList('classrooms', 'ref-classrooms');
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
    if (!await confirmModal('Перевести все курсы на +1?\nГруппы 4-го курса будут Удалены.')) return;
    const res = await api('/api/groups/advance-courses', { method: 'POST' });
    if (res.success) { alert(`Готово! Удалено групп: ${res.deleted}`); renderRefList('groups', 'ref-groups'); }
}

export async function addRefItem(endpoint, inputId, containerId) {
    const inp = document.getElementById(inputId);
    const name = inp.value.trim();
    if (!name) return;
    const body = { name };
    if (endpoint === 'teachers') { const phone = document.getElementById('ref-teachers-phone'); if (phone) body.phone = phone.value.trim(); }
    const res = await api(`/api/${endpoint}`, { method: 'POST', body: JSON.stringify(body) });
    if (res.error) { alert(res.error); return; }
    inp.value = '';
    if (endpoint === 'teachers') { const phone = document.getElementById('ref-teachers-phone'); if (phone) phone.value = ''; }
    renderRefList(endpoint, containerId);
}

export async function deleteRefItem(endpoint, id, containerId) {
    if (!await confirmModal('Удалить?\n\nВнимание: запись может использоваться в расписании.')) return;
    const res = await api(`/api/${endpoint}/${id}`, { method: 'DELETE' });
    if (res.error) { alert(res.error); return; }
    if (res.warning) alert(res.warning);
    renderRefList(endpoint, containerId);
}

export async function restoreRefItem(endpoint, id, containerId) {
    if (!await confirmModal('Восстановить запись?')) return;
    const res = await api(`/api/${endpoint}/${id}/restore`, { method: 'POST' });
    if (res.error) { alert(res.error); return; }
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
