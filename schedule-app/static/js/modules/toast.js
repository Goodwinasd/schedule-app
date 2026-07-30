export function showToast(message, type) {
    let container = document.getElementById('toast-container');
    if (!container) { container = document.createElement('div'); container.id = 'toast-container'; document.body.appendChild(container); }
    const t = document.createElement('div');
    t.className = 'toast toast-' + (type || 'info');
    t.textContent = message;
    t.onclick = () => { t.style.opacity = '0'; setTimeout(() => t.remove(), 300); };
    container.appendChild(t);
    setTimeout(() => { if (t.parentNode) { t.style.opacity = '0'; setTimeout(() => t.remove(), 300); } }, 4000);
}

export function alertError(msg) { showToast(msg, 'error'); }
export function alertSuccess(msg) { showToast(msg, 'success'); }
