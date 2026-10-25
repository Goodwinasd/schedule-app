import { api } from './api.js';
import { escapeHtml } from './utils.js';
import { confirmModal, showKimiAlert } from './modal.js';
import { showToast } from './toast.js';
import { showLoader, hideLoader } from './loader.js';

export async function loadTrashTab() {
    showLoader('Корзина');
    const data = await api('/api/trash');
    hideLoader();
    const cont = document.getElementById('trash-content');
    if (!cont) return;
    if (data.error) { cont.innerHTML = '<div style="color:var(--danger)">Ошибка загрузки корзины</div>'; return; }

    const items = [
        ...(data.subjects || []).map(i => ({...i, type: 'subjects'})),
        ...(data.teachers || []).map(i => ({...i, type: 'teachers'})),
        ...(data.classrooms || []).map(i => ({...i, type: 'classrooms'})),
        ...(data.groups || []).map(i => ({...i, type: 'groups'})),
        ...(data.specialties || []).map(i => ({...i, type: 'specialties'})),
        ...(data.days || []).map(i => ({...i, type: 'days'})),
        ...(data.lessons || []).map(i => ({...i, type: 'lessons'})),
    ];

    if (!items.length) {
        cont.innerHTML = '<div style="padding:20px;text-align:center;color:var(--text-secondary)">Корзина пуста</div>';
        return;
    }

    let html = '<div class="trash-grid">';
    for (const item of items) {
        const typeLabel = item.type_label || 'Запись';
        const name = item.name || item.day_name || `ID ${item.id}`;
        const ep = item.type === 'days' ? 'days' : item.type === 'lessons' ? 'lessons' : item.type;
        const date = item.deleted_at ? item.deleted_at.slice(0, 10) : '';

        let meta = '';
        // type здесь — из маппинга выше, то есть во множественном числе ('lessons'/'days');
        // сравнение с 'lesson'/'day' не совпадало никогда, поэтому метаданные не выводились
        if (item.type === 'lessons' && item.subject_name) {
            meta = `${item.subject_name} — ${item.day_name || ''} ${item.period ? item.period + '-я пара' : ''}`;
            // date и group_name уже приходят в объекте урока, но в карточку не попадали
            if (item.date) meta += ` · ${item.date}`;
            if (item.teacher_name) meta += ` · ${item.teacher_name}`;
            if (item.classroom_name) meta += ` · ${item.classroom_name}`;
            if (item.groups) meta += ` · ${item.groups}`;
            else if (item.group_name) meta += ` · ${item.group_name}`;
        } else if (item.type === 'days' && item.date) {
            meta = `${item.date} · ${item.group_name || ''}`;
        }

        html += `<div class="trash-card" data-type="${ep}">
            <div class="trash-card-type">${escapeHtml(typeLabel)}</div>
            <div class="trash-card-name">${escapeHtml(name)}</div>`;
        if (meta) html += `<div class="trash-card-meta">${escapeHtml(meta)}</div>`;
        html += `<div class="trash-card-date">${escapeHtml(date)}</div>
            <div class="trash-card-actions">
                <button class="btn btn-ghost btn-sm" onclick="restoreTrashItem('${ep}',${item.id})">↺ Восстановить</button>
            </div>
        </div>`;
    }
    html += '</div>';
    cont.innerHTML = html;
}

export async function restoreTrashItem(endpoint, id) {
    const labels = { days: 'день', lessons: 'пару', teachers: 'преподавателя', subjects: 'предмет', classrooms: 'аудиторию', groups: 'группу', specialties: 'специальность' };
    if (!await confirmModal('Восстановить ' + (labels[endpoint] || 'запись') + '?')) return;
    const url = endpoint === 'days' ? `/api/days/${id}/restore` : endpoint === 'lessons' ? `/api/lessons/${id}/restore` : `/api/${endpoint}/${id}/restore`;
    const res = await api(url, { method: 'POST' });
    if (res.error) { await showKimiAlert(res.error); return; }
    const item = res.item;
    if (item) {
        // Здесь type приходит из /api/.../restore в единственном числе ('lesson'/'day'),
        // в отличие от списочного /api/trash — поэтому сравнения ниже оставлены как были
        if (item.type === 'lesson' && item.subject_name) {
            showToast(`Пара «${item.subject_name}» восстановлена — ${item.day_name}, ${item.date}, ${item.period}-я пара`, 'success');
        } else if (item.type === 'day' && item.day_name) {
            showToast(`День «${item.day_name}» (${item.date}) восстановлен — группа ${item.group_name}`, 'success');
        } else if (item.name) {
            const t = { subjects: 'Предмет', teachers: 'Преподаватель', classrooms: 'Аудитория', groups: 'Группа', specialties: 'Специальность' }[item.type] || 'Запись';
            showToast(`${t} «${item.name}» восстановлен`, 'success');
        }
    }
    loadTrashTab();
}

export async function purgeTrash() {
    if (!await confirmModal('Удалить навсегда записи старше 30 дней?')) return;
    if (!await confirmModal('Это действие необратимо. Продолжить?')) return;
    const res = await api('/api/db/purge-trash', { method: 'POST' });
    if (res.error) { await showKimiAlert(res.error); return; }
    await showKimiAlert('Очищено: ' + Object.values(res.purged || {}).reduce((a, b) => a + b, 0) + ' записей');
    loadTrashTab();
}
