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
