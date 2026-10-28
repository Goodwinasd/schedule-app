import { api } from './api.js';
import { escapeHtml } from './utils.js';
import { showKimiAlert } from './modal.js';
import state from './state.js';
import { dispatchEvent, onEvent, CURRICULUM_UPDATED, DATA_MUTATED } from './events.js';

window.curriculumSemester = 1;

const CYCLES = ['ООД', 'СГ', 'ОП', 'ПМ', 'МДК'];
const CONTROL_BADGES = { 'Экзамен': 'Э', 'Зачет': 'Зач', 'Диф. зачет': 'ДЗ' };

function controlBadge(form) {
    if (!form) return '';
    const label = CONTROL_BADGES[form] || escapeHtml(form);
    const cls = form.includes('Экзамен') ? 'badge-exam' : form.includes('Диф') ? 'badge-diff' : 'badge-zach';
    return `<span class="cur-control-badge ${cls}">${label}</span>`;
}

export async function loadCurriculum() {
    const cont = document.getElementById('curriculum-content');
    if (!cont) return;
    cont.innerHTML = '<div class="loading">Загрузка...</div>';

    let html = '<div class="field-row" style="margin-bottom:12px"><label style="font-size:13px;font-weight:600;min-width:60px">Группа:</label>';
    html += '<select id="curriculum-group" class="input" style="max-width:220px" onchange="window.loadCurriculumPlan()">';
    html += '<option value="">— выбрать —</option>';
    for (const g of state.groupsList) {
        const suffix = g.specialty_name ? ` · ${escapeHtml(g.specialty_code || '')} ${escapeHtml(g.specialty_name)}` : '';
        html += `<option value="${g.id}">${escapeHtml(g.name)}${suffix}</option>`;
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

window.applySpecialtyPlan = async function() {
    const groupId = document.getElementById('curriculum-group').value;
    if (!groupId) { await showKimiAlert('Выберите группу'); return; }
    const semester = window.curriculumSemester || 1;
    const res = await api(`/api/curriculum/apply-specialty-plan`, {
        method: 'POST',
        body: JSON.stringify({ group_id: parseInt(groupId), semester: parseInt(semester) }),
    });
    if (res.error) { await showKimiAlert(res.error); return; }
    await showKimiAlert(`План специальности применён: добавлено предметов — ${res.created}, пропущено (уже есть) — ${res.skipped}.`);
    dispatchEvent(CURRICULUM_UPDATED);
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

    // Кнопка «Заполнить из плана специальности»
    const group = state.groupsList.find(g => String(g.id) === String(groupId));
    let applyBtn = '';
    if (group && group.specialty_id) {
        applyBtn = `<button class="btn btn-outline-accent btn-sm" onclick="window.applySpecialtyPlan()">Заполнить из плана специальности</button>`;
    }

    // Группировка по циклам
    const byCycle = {};
    for (const item of items) {
        const cycle = item.cycle || '—';
        (byCycle[cycle] = byCycle[cycle] || []).push(item);
    }
    const orderedCycles = CYCLES.filter(c => byCycle[c]);
    const otherCycles = Object.keys(byCycle).filter(c => !CYCLES.includes(c)).sort();
    const cycleKeys = [...orderedCycles, ...otherCycles];

    let totalHours = 0;
    let totalWeekly = 0;
    const itemsForSummary = [];
    let html = '';

    for (const cycle of cycleKeys) {
        const groupItems = byCycle[cycle];
        for (const item of groupItems) {
            const weekly = Math.ceil(item.total_hours / ((item.weeks_in_semester || 18) * 2));
            totalHours += item.total_hours;
            totalWeekly += weekly;
            itemsForSummary.push(item);
        }
        html += `<div class="cur-cycle-block">
            <div class="cur-cycle-title">${escapeHtml(cycle)}</div>
            <table class="analytics-table" style="margin-bottom:10px">
                <thead><tr><th>Предмет</th><th>Преподаватель</th><th>Часов</th><th>Пар/нед</th><th>Контроль</th><th></th></tr></thead>
                <tbody>`;
        for (const item of groupItems) {
            const weekly = Math.ceil(item.total_hours / ((item.weeks_in_semester || 18) * 2));
            const tname = item.teacher_name || '—';
            html += `<tr><td>${escapeHtml(item.subject_name || '—')}</td><td>${escapeHtml(tname)}</td><td>${item.total_hours}</td><td>${weekly}</td>`;
            html += `<td>${controlBadge(item.control_form)}</td>`;
            html += `<td><button class="btn btn-danger btn-icon btn-sm" onclick="window.deleteCurriculumItem(${item.id})" aria-label="Удалить дисциплину">×</button></td></tr>`;
        }
        html += '</tbody></table></div>';
    }

    if (!items.length) {
        html = '<div style="font-size:13px;color:var(--text-secondary);padding:8px 0;">Дисциплины на этот семестр не добавлены.</div>';
    }

    html += `<div style="margin-bottom:12px">${applyBtn}</div>`;

    // Summary row
    if (items.length) {
        const overload = totalWeekly > 18;
        html += `<div style="padding:8px 12px;border-radius:8px;font-size:13px;font-weight:600;margin-bottom:12px;background:${overload ? 'rgba(255,69,58,0.12)' : 'rgba(91,140,122,0.12)'};color:${overload ? 'var(--danger)' : 'var(--accent)'}">`;
        html += `Всего: ${totalHours} ч · ${totalWeekly} пар/нед`;
        if (overload) html += ' ⚠️ перегруз (>18)';
        html += '</div>';
    }

    // Add form
    html += '<div style="border-top:1px solid var(--border);padding-top:12px">';
    html += `<div style="font-size:12px;color:var(--text-secondary);margin-bottom:6px">Добавить в <strong>${semester} семестр</strong></div>`;
    html += '<div class="field-row" style="margin-bottom:8px;">';
    html += '<select id="curriculum-subject" class="input" style="max-width:190px"><option value="">Предмет</option>';
    for (const s of state.subjectsList) {
        html += `<option value="${s.id}">${escapeHtml(s.name)}</option>`;
    }
    html += '</select>';
    html += '<select id="curriculum-teacher" class="input" style="max-width:170px"><option value="">Преподаватель</option>';
    for (const t of state.teachersList) {
        html += `<option value="${t.id}">${escapeHtml(t.name)}</option>`;
    }
    html += '</select>';
    html += '<select id="curriculum-cycle" class="input" style="max-width:90px">';
    html += '<option value="">Цикл</option><option>ООД</option><option>СГ</option><option>ОП</option><option>ПМ</option><option>МДК</option>';
    html += '</select>';
    html += '<select id="curriculum-control" class="input" style="max-width:120px">';
    html += '<option value="">Контроль</option><option>Экзамен</option><option>Зачет</option><option>Диф. зачет</option>';
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
    const cycle = document.getElementById('curriculum-cycle')?.value || '';
    const control = document.getElementById('curriculum-control')?.value || '';
    if (!groupId || !subjectId) { await showKimiAlert('Выберите группу и предмет'); return; }
    const res = await api('/api/curriculum', {
        method: 'POST',
        body: JSON.stringify({
            group_id: parseInt(groupId),
            subject_id: parseInt(subjectId),
            teacher_id: teacherId ? parseInt(teacherId) : null,
            semester: parseInt(semester),
            total_hours: parseInt(hours),
            cycle: cycle || null,
            control_form: control || null,
        }),
    });
    if (res.error) { await showKimiAlert(res.error); return; }
    document.getElementById('curriculum-subject').value = '';
    document.getElementById('curriculum-teacher').value = '';
    if (document.getElementById('curriculum-cycle')) document.getElementById('curriculum-cycle').value = '';
    if (document.getElementById('curriculum-control')) document.getElementById('curriculum-control').value = '';
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
