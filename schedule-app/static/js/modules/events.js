export const CURRICULUM_UPDATED = 'curriculumUpdated';
export const HOLIDAYS_UPDATED = 'holidaysUpdated';
export const SCHEDULE_UPDATED = 'scheduleUpdated';
export const REFERENCES_UPDATED = 'referencesUpdated';
export const DATA_MUTATED = 'DATA_MUTATED';

export function dispatchEvent(name, detail = {}) {
    window.dispatchEvent(new CustomEvent(name, { detail }));
}

export function onEvent(name, handler) {
    window.addEventListener(name, handler);
}

export function offEvent(name, handler) {
    window.removeEventListener(name, handler);
}
