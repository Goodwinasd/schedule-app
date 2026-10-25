import { WEEKDAYS, MONTHS, MONTHS_SHORT } from './config.js';

/** @param {*} s */
export function escapeHtml(s) {
    if (s == null) return '';
    return String(s).replace(/[&<>"']/g, ch => ({ '&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'})[ch]);
}

export function formatDate(dateStr) {
    const d = new Date(dateStr + 'T00:00:00');
    return `${WEEKDAYS[d.getDay()]}, ${d.getDate()} ${MONTHS[d.getMonth()]}`;
}

export function formatShortDate(dateStr) {
    const d = new Date(dateStr + 'T00:00:00');
    return `${d.getDate()} ${MONTHS_SHORT[d.getMonth()]}`;
}

export function getMonday(date) {
    const d = new Date(date);
    const day = d.getDay();
    d.setDate(d.getDate() - day + (day === 0 ? -6 : 1));
    return d;
}

export function addDays(date, n) {
    const d = new Date(date);
    d.setDate(d.getDate() + n);
    return d;
}

export function toISODate(date) {
    return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, '0')}-${String(date.getDate()).padStart(2, '0')}`;
}

export function getWeekNumber(date) {
    return Math.floor((date - new Date(date.getFullYear(), 0, 1)) / (7 * 86400000)) + 1;
}

export function formatDateRange(monday) {
    const sat = addDays(monday, 5);
    const f = d => `${d.getDate()}.${String(d.getMonth() + 1).padStart(2, '0')}`;
    return `${f(monday)} – ${f(sat)}.${sat.getFullYear()}`;
}

export function formatChipRange(monday) {
    const sat = addDays(monday, 5);
    const md = monday.getDate(), ms = monday.getMonth(), sd = sat.getDate(), ss = sat.getMonth();
    const pfx = md === 2 ? 'со' : 'с';
    return ms === ss ? `${pfx} ${md} по ${sd} ${MONTHS[ms]}` : `${pfx} ${md} ${MONTHS[ms]} по ${sd} ${MONTHS[ss]}`;
}

export function shiftLabel(shift) {
    return ['', '1 смена', '2 смена', '3 смена'][shift] || '';
}

export function populateSelect(selId, items, placeholder) {
    const sel = document.getElementById(selId);
    sel.innerHTML = `<option value="">${escapeHtml(placeholder)}</option>` + items.map(i => `<option value="${i.id}">${escapeHtml(i.name)}</option>`).join('');
}

export function populateSelectByName(selId, items, placeholder) {
    const sel = document.getElementById(selId);
    sel.innerHTML = `<option value="">${escapeHtml(placeholder)}</option>` + items.map(i => `<option value="${escapeHtml(i.name)}">${escapeHtml(i.name)}</option>`).join('');
}

export function showConfirmModal(title, message, confirmText = 'Подтвердить', isDanger = true) {
    return new Promise((resolve) => {
        const existing = document.getElementById('custom-confirm-modal');
        if (existing) existing.remove();

        const overlay = document.createElement('div');
        overlay.id = 'custom-confirm-modal';
        overlay.style.cssText = `
            position: fixed; inset: 0; background: rgba(0, 0, 0, 0.5);
            display: flex; align-items: center; justify-content: center; z-index: 9999;
            animation: fadeIn 0.2s ease;
        `;

        overlay.innerHTML = `
            <div style="
                background: var(--bg-card, #fff); padding: 24px; border-radius: 12px;
                max-width: 400px; width: 90%; box-shadow: 0 10px 25px rgba(0,0,0,0.2);
                font-family: inherit; color: var(--text-main, #333);
            ">
                <h3 style="margin: 0 0 12px 0; font-size: 18px; font-weight: 600;">${escapeHtml(title)}</h3>
                <p style="margin: 0 0 20px 0; font-size: 14px; color: var(--text-muted, #666); line-height: 1.5;">${escapeHtml(message)}</p>
                <div style="display: flex; gap: 10px; justify-content: flex-end;">
                    <button id="modal-cancel" style="
                        padding: 8px 16px; border: 1px solid var(--border-color, #ccc); background: transparent;
                        border-radius: 6px; cursor: pointer; font-weight: 500;
                    ">Отмена</button>
                    <button id="modal-ok" style="
                        padding: 8px 16px; border: none; background: ${isDanger ? '#dc3545' : 'var(--accent, #0d6efd)'};
                        color: white; border-radius: 6px; cursor: pointer; font-weight: 500;
                    ">${escapeHtml(confirmText)}</button>
                </div>
            </div>
        `;

        document.body.appendChild(overlay);

        const close = (result) => {
            overlay.remove();
            resolve(result);
        };

        overlay.querySelector('#modal-ok').onclick = () => close(true);
        overlay.querySelector('#modal-cancel').onclick = () => close(false);
        overlay.onclick = (e) => { if (e.target === overlay) close(false); };
    });
}

window.showConfirmModal = showConfirmModal;
