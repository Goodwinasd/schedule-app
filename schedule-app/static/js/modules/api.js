import state from './state.js';
import { showToast } from './toast.js';
import { dispatchEvent, DATA_MUTATED } from './events.js';

function entityFromUrl(url) {
    const path = new URL(url, location.origin).pathname.replace(/^\/api\//, '');
    const base = path.split('/')[0];
    const map = {
        teachers:'teachers', subjects:'subjects', groups:'groups',
        classrooms:'classrooms', curriculum:'curriculum',
        days:'schedule', lessons:'schedule', week:'schedule',
        'excluded-dates':'holidays',
    };
    return map[base] || null;
}

function actionFromMethod(method) {
    return { POST:'create', PUT:'update', PATCH:'update', DELETE:'delete' }[method] || null;
}

export async function api(url, options = {}) {
    const headers = { 'Content-Type': 'application/json', ...options.headers };
    if (state.csrfToken && options.method && options.method !== 'GET') {
        headers['X-CSRF-Token'] = state.csrfToken;
    }
    const res = await fetch(url, { ...options, headers });
    const data = await res.json();
    if (res.status === 401) {
        state.isAdmin = false;
        if (window._onUnauthorized) window._onUnauthorized();
    }
    if (!options.silent && res.ok && options.method && options.method !== 'GET') {
        if (!data.error) showToast('Успешно сохранено', 'success');
    }
    if (res.ok && options.method && options.method !== 'GET') {
        const entity = entityFromUrl(url);
        const action = actionFromMethod(options.method);
        if (entity && action) {
            dispatchEvent(DATA_MUTATED, { entity, action });
        }
    }
    return data;
}
