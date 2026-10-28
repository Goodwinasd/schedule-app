import { escapeHtml } from './utils.js';

export const _confirmState = { resolver: null };

/**
 * Статические модалки размечены в index.html без ARIA, поэтому атрибуты
 * доставляем в момент открытия — разметку за пределами модуля не трогаем.
 */
function _applyDialogA11y(root) {
    if (!root) return;
    const dialog = root.querySelector('.modal-content') || root;
    if (!dialog.hasAttribute('role')) dialog.setAttribute('role', 'dialog');
    dialog.setAttribute('aria-modal', 'true');
}

export function openModal(id) {
    document.getElementById('modal-overlay').classList.add('active');
    const el = document.getElementById(id);
    el.style.display = '';
    _applyDialogA11y(el);
}

export function confirmModal(message) {
    return new Promise(resolve => {
        _confirmState.resolver = resolve;
        document.getElementById('confirm-modal-message').textContent = message;
        document.getElementById('modal-overlay').classList.add('active');
        const confirmEl = document.getElementById('confirm-modal');
        confirmEl.style.display = '';
        _applyDialogA11y(confirmEl);
        document.getElementById('confirm-modal-ok').onclick = () => { _confirmState.resolver = null; resolve(true); _closeConfirmOnly(); };
        document.getElementById('confirm-modal-cancel').onclick = () => { _confirmState.resolver = null; resolve(false); _closeConfirmOnly(); };
        // Фокус на основном действии: Enter срабатывает сразу, без «табания» по модалке
        document.getElementById('confirm-modal-ok').focus();
    });
}

function _closeConfirmOnly() {
    const overlay = document.getElementById('modal-overlay');
    const confirmEl = document.getElementById('confirm-modal');
    if (confirmEl) confirmEl.style.display = 'none';
    const anyModalOpen = document.querySelectorAll('.modal:not(#confirm-modal):not([style*="display: none"])');
    if (anyModalOpen.length === 0) {
        overlay.classList.remove('active');
    }
    const cm = document.getElementById('checkmark-anim');
    if (cm) cm.setAttribute('data-state', 'out');
}

export function showKimiAlert(message, title) {
    return new Promise(resolve => {
        const overlay = document.getElementById('modal-overlay');
        const existing = document.getElementById('kimi-alert-modal');
        // Не просто выкидываем старую модалку: её Esc-слушатель и промис остались бы висеть
        if (existing && typeof existing._kimiDismiss === 'function') existing._kimiDismiss();
        else if (existing) existing.remove();

        const modal = document.createElement('div');
        modal.id = 'kimi-alert-modal';
        modal.className = 'modal modal-narrow';
        modal.style.cssText = 'display:';
        // title/message приходят из ответов API — в innerHTML их можно только экранированными
        modal.innerHTML = `<div class="modal-content"><h2>${escapeHtml(title)}</h2><p class="modal-message">${escapeHtml(message)}</p><div class="modal-actions"><button class="btn btn-primary" id="kimi-alert-ok">OK</button></div></div>`;
        document.body.appendChild(modal);
        overlay.classList.add('active');
        modal.style.display = '';
        _applyDialogA11y(modal);

        const okBtn = document.getElementById('kimi-alert-ok');
        const close = () => {
            document.removeEventListener('keydown', onKey);
            modal._kimiDismiss = null;
            modal.remove();
            overlay.classList.remove('active');
            resolve();
        };
        // Esc разрешает промис так же, как OK: иначе ожидающий вызывающий код повиснет
        const onKey = e => { if (e.key === 'Escape' || e.key === 'Esc') close(); };
        modal._kimiDismiss = close;
        okBtn.onclick = close;
        document.addEventListener('keydown', onKey);
        okBtn.focus();
    });
}

export function showKimiPrompt(message, defaultValue) {
    return new Promise(resolve => {
        const overlay = document.getElementById('modal-overlay');
        const existing = document.getElementById('kimi-prompt-modal');
        // См. showKimiAlert: снимаем старый Esc-слушатель и разрешаем его промис
        if (existing && typeof existing._kimiDismiss === 'function') existing._kimiDismiss();
        else if (existing) existing.remove();

        const modal = document.createElement('div');
        modal.id = 'kimi-prompt-modal';
        modal.className = 'modal modal-narrow';
        modal.style.cssText = 'display:';
        // Значение по умолчанию тоже может прийти из БД — escapeHtml закрывает и кавычки, и <>&
        modal.innerHTML = `<div class="modal-content"><h2>${escapeHtml(message)}</h2><input type="text" id="kimi-prompt-input" class="input kimi-input" value="${escapeHtml(defaultValue || '')}"><div class="modal-actions"><button class="btn btn-ghost" id="kimi-prompt-cancel">Отмена</button><button class="btn btn-primary" id="kimi-prompt-ok">OK</button></div></div>`;
        document.body.appendChild(modal);
        overlay.classList.add('active');
        modal.style.display = '';
        _applyDialogA11y(modal);

        const input = document.getElementById('kimi-prompt-input');
        input.focus();
        input.select();

        const close = val => {
            document.removeEventListener('keydown', onKey);
            modal._kimiDismiss = null;
            modal.remove();
            overlay.classList.remove('active');
            resolve(val);
        };
        // Esc = «Отмена»: промис должен разрешиться, иначе вызывающий код зависнет
        const onKey = e => { if (e.key === 'Escape' || e.key === 'Esc') close(null); };
        modal._kimiDismiss = () => close(null);
        document.addEventListener('keydown', onKey);

        document.getElementById('kimi-prompt-ok').onclick = () => close(document.getElementById('kimi-prompt-input').value);
        document.getElementById('kimi-prompt-cancel').onclick = () => close(null);
    });
}

export function showKimiSelect(title, options, defaultValue) {
    return new Promise(resolve => {
        const overlay = document.getElementById('modal-overlay');
        const existing = document.getElementById('kimi-select-modal');
        // См. showKimiAlert: иначе старый Esc-слушатель и его промис остаются висеть
        if (existing && typeof existing._kimiDismiss === 'function') existing._kimiDismiss();
        else if (existing) existing.remove();

        // label/value — данные из БД: selected сравниваем ДО экранирования, в разметку кладём уже безопасное
        const optsHtml = (options || []).map(o =>
            `<option value="${escapeHtml(o.value)}"${String(o.value) === String(defaultValue ?? '') ? ' selected' : ''}>${escapeHtml(o.label)}</option>`
        ).join('');
        const modal = document.createElement('div');
        modal.id = 'kimi-select-modal';
        modal.className = 'modal modal-narrow';
        modal.style.cssText = 'display:';
        modal.innerHTML = `<div class="modal-content"><h2>${escapeHtml(title)}</h2><select id="kimi-select-input" class="input kimi-input">${optsHtml}</select><div class="modal-actions"><button class="btn btn-ghost" id="kimi-select-cancel">Отмена</button><button class="btn btn-primary" id="kimi-select-ok">OK</button></div></div>`;
        document.body.appendChild(modal);
        overlay.classList.add('active');
        modal.style.display = '';
        _applyDialogA11y(modal);

        const selectEl = document.getElementById('kimi-select-input');
        selectEl.focus();

        const close = val => {
            document.removeEventListener('keydown', onKey);
            modal._kimiDismiss = null;
            modal.remove();
            overlay.classList.remove('active');
            resolve(val);
        };
        // Esc = «Отмена»: иначе промис останется неразрешённым
        const onKey = e => { if (e.key === 'Escape' || e.key === 'Esc') close(null); };
        modal._kimiDismiss = () => close(null);
        document.addEventListener('keydown', onKey);

        document.getElementById('kimi-select-ok').onclick = () => close(selectEl.value);
        document.getElementById('kimi-select-cancel').onclick = () => close(null);
    });
}

export function triggerErrorShake(inputElement) {
    if (!inputElement) return;
    inputElement.classList.remove('is-shaking');
    void inputElement.offsetWidth;
    inputElement.classList.add('is-error', 'is-shaking');
    setTimeout(() => {
        inputElement.classList.remove('is-shaking');
    }, 400);
}

document.addEventListener('input', (e) => {
    if (e.target.classList && e.target.classList.contains('is-error')) {
        e.target.classList.remove('is-error');
    }
});

/* Escape закрывает текущую модалку. Confirm и kimi-модалки вешают свой обработчик
   (им нужно разрешить промис), статические закрываем тем же путём, что и клик по
   оверлею — через window.closeModals (ui.js), импорт из ui.js дал бы цикл. */
document.addEventListener('keydown', (e) => {
    if (e.key !== 'Escape' && e.key !== 'Esc') return;
    // Закрытая, но не удалённая kimi-модалка (клик по оверлею зовёт closeModals) не должна глушить Escape
    const kimiOpen = ['kimi-alert-modal', 'kimi-prompt-modal', 'kimi-select-modal'].some(id => {
        const el = document.getElementById(id);
        return el && el.style.display !== 'none';
    });
    if (kimiOpen) return;
    const confirmEl = document.getElementById('confirm-modal');
    if (confirmEl && confirmEl.style.display !== 'none' && _confirmState.resolver) {
        const r = _confirmState.resolver;
        _confirmState.resolver = null;
        _closeConfirmOnly();
        r(false);
        return;
    }
    const anyOpen = Array.from(document.querySelectorAll('.modal')).some(m => m.style.display !== 'none');
    if (anyOpen && typeof window.closeModals === 'function') window.closeModals();
});

/* ---- Tooltips ---- */
document.addEventListener('mouseenter', (e) => {
    const el = e.target && e.target.closest ? e.target.closest('[data-tooltip]') : null;
    if (!el) return;
    const text = el.dataset.tooltip;
    if (!text) return;
    let tip = document.getElementById('_tooltip_el');
    if (!tip) {
        tip = document.createElement('div');
        tip.id = '_tooltip_el';
        tip.className = 't-tooltip';
        document.body.appendChild(tip);
    }
    tip.textContent = text;
    const rect = el.getBoundingClientRect();
    tip.style.left = Math.min(rect.left + rect.width / 2 - tip.offsetWidth / 2, window.innerWidth - tip.offsetWidth - 8) + 'px';
    tip.style.top = (rect.bottom + 6) + 'px';
    requestAnimationFrame(() => tip.classList.add('is-visible'));
}, true);

document.addEventListener('mouseleave', (e) => {
    const el = e.target && e.target.closest ? e.target.closest('[data-tooltip]') : null;
    if (!el) return;
    const tip = document.getElementById('_tooltip_el');
    if (tip) {
        tip.classList.remove('is-visible');
        setTimeout(() => { if (tip && !tip.classList.contains('is-visible')) tip.remove(); }, 150);
    }
}, true);
