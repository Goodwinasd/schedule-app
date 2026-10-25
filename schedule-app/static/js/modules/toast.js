function removeSoon(t) {
    t.style.opacity = '0';
    setTimeout(() => t.remove(), 300);
}

export function showToast(message, type) {
    let container = document.getElementById('toast-container');
    if (!container) { container = document.createElement('div'); container.id = 'toast-container'; document.body.appendChild(container); }
    const cls = 'toast toast-' + (type || 'info');
    for (const existing of container.children) {
        if (existing.textContent === message && existing.className === cls) {
            clearTimeout(Number(existing.dataset.timer) || 0);
            existing.style.opacity = '1';
            existing.dataset.timer = String(setTimeout(() => removeSoon(existing), 4000));
            return;
        }
    }
    const t = document.createElement('div');
    t.className = cls;
    t.textContent = message;
    t.onclick = () => removeSoon(t);
    container.appendChild(t);
    while (container.children.length > 2) {
        container.firstElementChild.remove();
    }
    t.dataset.timer = String(setTimeout(() => removeSoon(t), 4000));
}

export function alertError(msg) { showToast(msg, 'error'); }
export function alertSuccess(msg) { showToast(msg, 'success'); }
