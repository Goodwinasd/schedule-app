let _loadCount = 0;

export function showLoader(label) {
    _loadCount++;
    if (_loadCount > 1) return;
    let overlay = document.getElementById('app-loader-overlay');
    if (!overlay) {
        overlay = document.createElement('div');
        overlay.id = 'app-loader-overlay';
        overlay.innerHTML = '<div class="app-loader"><div class="app-loader-dots"><div class="app-loader-dot"></div><div class="app-loader-dot"></div><div class="app-loader-dot"></div></div><div class="app-loader-label" id="app-loader-label">Загрузка...</div></div>';
        document.body.appendChild(overlay);
    }
    const lbl = document.getElementById('app-loader-label');
    if (lbl) lbl.textContent = label || 'Загрузка...';
    overlay.classList.add('active');
}

export function hideLoader() {
    if (_loadCount > 0) _loadCount--;
    if (_loadCount > 0) return;
    const overlay = document.getElementById('app-loader-overlay');
    if (overlay) overlay.classList.remove('active');
}
