import { api } from './api.js';
import { escapeHtml } from './utils.js';
import { confirmModal } from './modal.js';
import { showToast } from './toast.js';

/* ======================== Trash ======================== */

export async function loadTrashTab() {
    const data = await api('/api/trash');
    if (data.error) { document.getElementById('trash-refs').innerHTML = '<div style="color:var(--danger)">Ошибка загрузки корзины</div>'; return; }
    const refs = document.getElementById('trash-refs');
    if (refs) refs.innerHTML = renderTrashSection('Справочники', [
        ...(data.subjects || []).map(i => ({...i, type: 'subjects'})),
        ...(data.teachers || []).map(i => ({...i, type: 'teachers'})),
        ...(data.classrooms || []).map(i => ({...i, type: 'classrooms'})),
        ...(data.groups || []).map(i => ({...i, type: 'groups'})),
    ]);
    const days = document.getElementById('trash-days');
    if (days) days.innerHTML = renderTrashSection('Дни', (data.days || []).map(i => ({...i, type: 'days'})));
    const lessons = document.getElementById('trash-lessons');
    if (lessons) lessons.innerHTML = renderTrashSection('Пары', (data.lessons || []).map(i => ({...i, type: 'lessons'})));
}

function renderTrashSection(title, items) {
    if (!items.length) return `<div style="margin:8px 0;font-size:13px;color:var(--text-secondary)">${title}: пусто</div>`;
    let html = `<div style="margin:8px 0"><strong>${title}</strong> (${items.length})</div>`;
    for (const item of items) {
        const name = item.name || item.day_name || `ID ${item.id}`;
        const date = item.deleted_at ? item.deleted_at.slice(0, 10) : '';
        const ep = item.type === 'days' ? 'days' : item.type === 'lessons' ? 'lessons' : item.type;
        html += `<div class="trash-item"><span class="trash-label">${escapeHtml(name)}</span><span class="trash-date">${date}</span>`;
        html += `<button class="btn btn-ghost btn-sm" onclick="restoreTrashItem('${ep}',${item.id})">\u21BA</button>`;
        html += '</div>';
    }
    return html;
}

export async function restoreTrashItem(endpoint, id) {
    const labels = { days: 'день', lessons: 'пару', teachers: 'преподавателя', subjects: 'предмет', classrooms: 'аудиторию', groups: 'группу' };
    if (!await confirmModal('Восстановить ' + (labels[endpoint] || 'запись') + '?')) return;
    const url = endpoint === 'days' ? `/api/days/${id}/restore` : endpoint === 'lessons' ? `/api/lessons/${id}/restore` : `/api/${endpoint}/${id}/restore`;
    const res = await api(url, { method: 'POST' });
    if (res.error) { alert(res.error); return; }
    const item = res.item;
    if (item) {
        if (item.type === 'lesson' && item.subject_name) {
            showToast(`Пара «${item.subject_name}» восстановлена — ${item.day_name}, ${item.date}, ${item.period}-я пара`, 'success');
        } else if (item.type === 'day' && item.day_name) {
            showToast(`День «${item.day_name}» (${item.date}) восстановлен — группа ${item.group_name}`, 'success');
        } else if (item.name) {
            const t = { subjects: 'Предмет', teachers: 'Преподаватель', classrooms: 'Аудитория', groups: 'Группа' }[item.type] || 'Запись';
            showToast(`${t} «${item.name}» восстановлен`, 'success');
        }
    }
    loadTrashTab();
}

export async function purgeTrash() {
    if (!await confirmModal('Удалить навсегда записи старше 30 дней?')) return;
    if (!await confirmModal('Это действие необратимо. Продолжить?')) return;
    const res = await api('/api/db/purge-trash', { method: 'POST' });
    if (res.error) { alert(res.error); return; }
    alert('Очищено: ' + Object.values(res.purged || {}).reduce((a, b) => a + b, 0) + ' записей');
    loadTrashTab();
}
