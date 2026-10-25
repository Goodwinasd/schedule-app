import state from './state.js';
import { showToast } from './toast.js';
import { dispatchEvent, DATA_MUTATED } from './events.js';

/** Успех этих запросов не озвучиваем тостом: они идут фоном (проверки, вход). */
const SILENT_OK_PREFIXES = ['/api/validate', '/api/auth/'];

function entityFromUrl(url) {
    const path = new URL(url, location.origin).pathname.replace(/^\/api\//, '');
    const base = path.split('/')[0];
    const map = {
        teachers:'teachers', subjects:'subjects', groups:'groups',
        classrooms:'classrooms', curriculum:'curriculum', specialties:'specialties',
        days:'schedule', lessons:'schedule', week:'schedule',
        'excluded-dates':'holidays',
    };
    return map[base] || null;
}

function actionFromMethod(method) {
    return { POST:'create', PUT:'update', PATCH:'update', DELETE:'delete' }[method] || null;
}

function isBackgroundSuccess(url) {
    const path = new URL(url, location.origin).pathname;
    return SILENT_OK_PREFIXES.some(prefix => path.startsWith(prefix));
}

function messageFor(res, data) {
    if (data && typeof data === 'object' && data.error) return String(data.error);
    if (res.status === 401) return 'Нужен вход администратора';
    if (res.status === 403) return 'Сессия истекла — обновите страницу';
    if (res.status === 413) return 'Слишком большой запрос';
    if (res.status >= 500) return `Ошибка сервера (${res.status})`;
    return `Ошибка запроса (${res.status})`;
}

/**
 * Обёртка над fetch: JSON, CSRF-заголовок, уведомления и шина DATA_MUTATED.
 *
 * Возвращает разобранный ответ либо `{ error }`. Исключения наружу не бросаем:
 * весь вызывающий код уже проверяет `data.error`, а необработанный reject
 * (например на HTML-странице ошибки вместо JSON) оставлял лоадер навсегда.
 */
export async function api(url, options = {}) {
    const method = (options.method || 'GET').toUpperCase();
    const headers = { ...options.headers };
    if (options.body && !headers['Content-Type']) headers['Content-Type'] = 'application/json';
    if (state.csrfToken && method !== 'GET') headers['X-CSRF-Token'] = state.csrfToken;

    // Без таймаута зависший запрос держал лоадер бесконечно.
    const controller = new AbortController();
    const timeoutMs = options.timeoutMs || 30000;
    const timer = setTimeout(() => controller.abort(), timeoutMs);

    let res;
    try {
        res = await fetch(url, { ...options, headers, signal: controller.signal });
    } catch (err) {
        clearTimeout(timer);
        const message = err && err.name === 'AbortError'
            ? `Сервер не ответил за ${Math.round(timeoutMs / 1000)} с`
            : 'Нет связи с сервером';
        if (!options.silent) showToast(message, 'error');
        return { error: message };
    }
    clearTimeout(timer);

    let data = null;
    const contentType = res.headers.get('Content-Type') || '';
    if (contentType.includes('application/json')) {
        try {
            data = await res.json();
        } catch {
            data = null;
        }
    }

    if (res.status === 401) {
        state.isAdmin = false;
        if (window._onUnauthorized) window._onUnauthorized();
    }

    if (!res.ok) {
        const message = messageFor(res, data);
        // 401 на фоновом GET — норма: публичная страница обращается к админским
        // эндпоинтам (например, /api/curriculum для прогресса плана). Тост здесь
        // превращался в красную плашку «Unauthorized» у обычного посетителя.
        const silentError = res.status === 401 && method === 'GET';
        if (!options.silent && !silentError) showToast(message, 'error');
        return { error: message, status: res.status };
    }

    if (!options.silent && method !== 'GET' && !isBackgroundSuccess(url)) {
        showToast('Успешно сохранено', 'success');
    }

    if (method !== 'GET') {
        const entity = entityFromUrl(url);
        const action = actionFromMethod(method);
        if (entity && action) {
            dispatchEvent(DATA_MUTATED, { entity, action });
        }
    }

    return data === null ? {} : data;
}
