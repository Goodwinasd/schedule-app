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
