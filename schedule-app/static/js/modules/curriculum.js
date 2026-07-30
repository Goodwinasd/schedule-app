import { api } from './api.js';
import { escapeHtml } from './utils.js';
import { showKimiAlert } from './modal.js';
import state from './state.js';
import { dispatchEvent, onEvent, CURRICULUM_UPDATED, DATA_MUTATED } from './events.js';

window.curriculumSemester = 1;

export async function loadCurriculum() {
    const cont = document.getElementById('curriculum-content');
    if (!cont) return;
    cont.innerHTML = '<div class="loading">Загрузка...</div>';

    let html = '<div class="field-row" style="margin-bottom:12px"><label style="font-size:13px;font-weight:600;min-width:60px">Группа:</label>';
    html += '<select id="curriculum-group" class="input" style="max-width:200px" onchange="window.loadCurriculumPlan()">';
    html += '<option value="">— выбрать —</option>';
    for (const g of state.groupsList) {
        html += `<option value="${g.id}">${escapeHtml(g.name)}</option>`;
    }
    html += '</select></div>';

    // Semester tabs
    window.curriculumSemester = window.curriculumSemester || 1;
    html += '<div class="avail-mode-toggle" style="margin-bottom:12px">';
    for (let i = 1; i <= 8; i++) {
        html += `<button class="btn btn-ghost btn-sm ${window.curriculumSemester === i ? 'active' : ''}" onclick="window.selectCurriculumSemester(${i})">${i} сем</button>`;
    }
    html += '</div>';

    html += '<div id="curriculum-plan"></div>';
    cont.innerHTML = html;
}

window.selectCurriculumSemester = function(sem) {
    window.curriculumSemester = sem;
    document.querySelectorAll('#curriculum-content .avail-mode-toggle .btn').forEach((b, i) => {
        b.classList.toggle('active', i + 1 === sem);
    });
    window.loadCurriculumPlan();
};

window.loadCurriculumPlan = async function() {
    const sel = document.getElementById('curriculum-group');
    const groupId = sel ? sel.value : '';
    const cont = document.getElementById('curriculum-plan');
    if (!groupId) { cont.innerHTML = ''; return; }
    cont.innerHTML = '<div class="loading">Загрузка...</div>';
    const data = await api(`/api/curriculum?group_id=${groupId}`);
    if (data.error) { cont.innerHTML = '<div style="color:var(--danger)">Ошибка</div>'; return; }

    const semester = window.curriculumSemester || 1;
    const items = data.filter(item => item.semester === semester);

    let totalHours = 0;
    let totalWeekly = 0;
    let html = '<table class="analytics-table" style="margin-bottom:8px"><tr><th>Предмет</th><th>Преподаватель</th><th>Часов</th><th>Пар/нед</th><th></th></tr>';
    for (const item of items) {
        const weekly = Math.ceil(item.total_hours / ((item.weeks_in_semester || 18) * 2));
        totalHours += item.total_hours;
        totalWeekly += weekly;
        const tname = item.teacher_name || '—';
        html += `<tr><td>${escapeHtml(item.subject_name || '—')}</td><td>${escapeHtml(tname)}</td><td>${item.total_hours}</td><td>${weekly}</td>`;
        html += `<td><button class="btn btn-danger btn-sm" onclick="window.deleteCurriculumItem(${item.id})">×</button></td></tr>`;
    }
    html += '</table>';

    // Summary row
    const overload = totalWeekly > 18;
    html += `<div style="padding:8px 12px;border-radius:8px;font-size:13px;font-weight:600;margin-bottom:12px;background:${overload ? 'rgba(255,69,58,0.12)' : 'rgba(91,140,122,0.12)'};color:${overload ? 'var(--danger)' : 'var(--accent)'}">`;
    html += `📋 Всего: ${totalHours} ч · ${totalWeekly} пар/нед`;
    if (overload) html += ' ⚠️ перегруз (>18)';
    html += '</div>';

    // Add form
    html += '<div style="border-top:1px solid var(--border);padding-top:12px">';
    html += `<div style="font-size:12px;color:var(--text-secondary);margin-bottom:6px">Добавить в <strong>${semester} семестр</strong></div>`;
    html += '<div class="field-row" style="margin-bottom:8px">';
    html += '<select id="curriculum-subject" class="input" style="max-width:200px"><option value="">Предмет</option>';
    for (const s of state.subjectsList) {
        html += `<option value="${s.id}">${escapeHtml(s.name)}</option>`;
    }
    html += '</select>';
    html += '<select id="curriculum-teacher" class="input" style="max-width:180px"><option value="">Преподаватель</option>';
    for (const t of state.teachersList) {
        html += `<option value="${t.id}">${escapeHtml(t.name)}</option>`;
    }
    html += '</select>';
    html += '<input type="number" id="curriculum-hours" class="input" style="max-width:80px" value="72" min="1">';
    html += `<button class="btn btn-primary btn-sm" onclick="window.addCurriculumItem()">Добавить</button>`;
    html += '</div></div>';

    cont.innerHTML = html;
};

window.addCurriculumItem = async function() {
    const groupId = document.getElementById('curriculum-group').value;
    const subjectId = document.getElementById('curriculum-subject').value;
    const teacherId = document.getElementById('curriculum-teacher').value;
    const semester = window.curriculumSemester || 1;
    const hours = document.getElementById('curriculum-hours').value;
    if (!groupId || !subjectId) { await showKimiAlert('Выберите группу и предмет'); return; }
    const res = await api('/api/curriculum', {
        method: 'POST',
        body: JSON.stringify({
            group_id: parseInt(groupId),
            subject_id: parseInt(subjectId),
            teacher_id: teacherId ? parseInt(teacherId) : null,
            semester: parseInt(semester),
            total_hours: parseInt(hours),
        }),
    });
    if (res.error) { await showKimiAlert(res.error); return; }
    document.getElementById('curriculum-subject').value = '';
    document.getElementById('curriculum-teacher').value = '';
    document.getElementById('curriculum-hours').value = '72';
    dispatchEvent(CURRICULUM_UPDATED);
    window.loadCurriculumPlan();
};

window.deleteCurriculumItem = async function(id) {
    await api(`/api/curriculum/${id}`, { method: 'DELETE' });
    dispatchEvent(CURRICULUM_UPDATED);
    window.loadCurriculumPlan();
};

onEvent(DATA_MUTATED, (e) => {
    if (['subjects', 'teachers', 'groups'].includes(e.detail.entity)) {
        const plan = document.getElementById('curriculum-plan');
        if (plan && plan.innerHTML) {
            window.loadCurriculumPlan();
        }
    }
});
