export const _confirmState = { resolver: null };

export function openModal(id) {
    document.getElementById('modal-overlay').classList.add('active');
    document.getElementById(id).style.display = '';
}

export function confirmModal(message) {
    return new Promise(resolve => {
        _confirmState.resolver = resolve;
        document.getElementById('confirm-modal-message').textContent = message;
        document.getElementById('modal-overlay').classList.add('active');
        document.getElementById('confirm-modal').style.display = '';
        document.getElementById('confirm-modal-ok').onclick = () => { _confirmState.resolver = null; try { resolve(true); } finally { window.closeModals(); } };
        document.getElementById('confirm-modal-cancel').onclick = () => { _confirmState.resolver = null; try { resolve(false); } finally { window.closeModals(); } };
    });
}

export function showKimiAlert(message, title) {
    return new Promise(resolve => {
        const overlay = document.getElementById('modal-overlay');
        const existing = document.getElementById('kimi-alert-modal');
        if (existing) existing.remove();

        const modal = document.createElement('div');
        modal.id = 'kimi-alert-modal';
        modal.className = 'modal';
        modal.style.cssText = 'display:';
        modal.innerHTML = `<div class="modal-content"><h2>${title || ''}</h2><p style="text-align:center;margin:8px 0;font-size:14px;line-height:1.5">${message}</p><div class="modal-actions" style="justify-content:center"><button class="btn btn-primary" id="kimi-alert-ok">OK</button></div></div>`;
        document.body.appendChild(modal);
        overlay.classList.add('active');
        modal.style.display = '';

        document.getElementById('kimi-alert-ok').onclick = () => { modal.remove(); overlay.classList.remove('active'); resolve(); };
    });
}

export function showKimiPrompt(message, defaultValue) {
    return new Promise(resolve => {
        const overlay = document.getElementById('modal-overlay');
        const existing = document.getElementById('kimi-prompt-modal');
        if (existing) existing.remove();

        const modal = document.createElement('div');
        modal.id = 'kimi-prompt-modal';
        modal.className = 'modal';
        modal.style.cssText = 'display:';
        modal.innerHTML = `<div class="modal-content"><h2>${message}</h2><input type="text" id="kimi-prompt-input" class="input" value="${(defaultValue || '').replace(/"/g, '&quot;')}" style="margin:8px 0"><div class="modal-actions"><button class="btn btn-ghost" id="kimi-prompt-cancel">Отмена</button><button class="btn btn-primary" id="kimi-prompt-ok">OK</button></div></div>`;
        document.body.appendChild(modal);
        overlay.classList.add('active');
        modal.style.display = '';
        document.getElementById('kimi-prompt-input').focus();
        document.getElementById('kimi-prompt-input').select();

        document.getElementById('kimi-prompt-ok').onclick = () => { const val = document.getElementById('kimi-prompt-input').value; modal.remove(); overlay.classList.remove('active'); resolve(val); };
        document.getElementById('kimi-prompt-cancel').onclick = () => { modal.remove(); overlay.classList.remove('active'); resolve(null); };
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

/* ---- Tooltips ---- */
document.addEventListener('mouseenter', (e) => {
    const el = e.target.closest('[data-tooltip]');
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
    const el = e.target.closest('[data-tooltip]');
    if (!el) return;
    const tip = document.getElementById('_tooltip_el');
    if (tip) {
        tip.classList.remove('is-visible');
        setTimeout(() => { if (tip && !tip.classList.contains('is-visible')) tip.remove(); }, 150);
    }
}, true);
