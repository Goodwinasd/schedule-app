/**
 * Точка входа приложения
 * Привязывает функции к window для обратной совместимости с onclick-атрибутами в HTML
 * @module main
 */

import state from './state.js';
import { api } from './api.js';
import {
    goHome, showSchedule, showLoginModal, closeModals,
    showAdminPanel, switchAdminTab, openDashboard,
    login, logout,
    showAvailability, selectAvailWeek, availCarouselSkip,
    selectAvailDay, setAvailMode, loadAvailability, updateUI, toggleConflicts,
    toggleAvailHeatmap, toggleAvailGroupByCourse, closeAvailability,
    exportAvailExcel, exportAvailPDF,
    renderAvailTable, _clickLesson, ensureDOMNotEmpty,
} from './ui.js';
import { confirmModal, showKimiAlert } from './modal.js';
import { loadScheduleTable, printSchedule, exportSchedule, smartExportExcel, showAddLessonModal, addLesson, editLesson, saveLesson, addSubgroupLesson, deleteCurrentLesson, validateLesson, generateFromCurriculum, generateMonth, refreshSubstitutionSuggest, pickSubstituteTeacher, toggleWeekPublish, showMoveForm, cancelMove, saveMove, showGenerateModal } from './schedule.js';
import { loadReferences, renderRefList, addGroup, editGroup, addSubject, editSubject, editTeacher, editClassroom, advanceCourses, addRefItem, deleteRefItem, restoreRefItem, quickAdd, quickAddGroup, addSpecialty, editSpecialty, loadSpecialties, openImportModal, closeImportModal, downloadImportTemplate, uploadImportExcel } from './references.js';
import { renderCarousel, setActiveWeek, selectWeekByDate, carouselSkip, showAddWeekModal, updateWeekPreview, addWeek, restoreWeek, deleteWeek, setYear, goToCurrentWeek } from './nav.js';
import { saveSetting, addExcludedDate, deleteExcludedDate, downloadBackup, restoreBackup, checkOrphans, confirmDeleteOrphans, clearOrphanResult, loadBellScheduleTab, applyBellPreset, saveBellSchedule } from './settings.js';
import { restoreTrashItem, purgeTrash } from './trash.js';

/* Привязка к window для onclick-вызовов из HTML */
Object.assign(window, {
    goHome, showSchedule, showLoginModal, closeModals,
    selectWeekByDate, carouselSkip, showAddWeekModal, addWeek, restoreWeek, deleteWeek, setYear, goToCurrentWeek,
    loadScheduleTable, printSchedule, exportSchedule, smartExportExcel,
    showAddLessonModal, addLesson, editLesson, saveLesson, addSubgroupLesson,
deleteCurrentLesson, validateLesson, generateFromCurriculum, generateMonth,
refreshSubstitutionSuggest, pickSubstituteTeacher,
    toggleWeekPublish, showMoveForm, cancelMove, saveMove, showGenerateModal,
    loadReferences, showAdminPanel, renderRefList,
    addGroup, editGroup, addSubject, editSubject, editTeacher, editClassroom, advanceCourses,
    addRefItem, deleteRefItem, restoreRefItem, quickAdd, quickAddGroup, saveSetting,
    addSpecialty, editSpecialty, loadSpecialties,
    openImportModal, closeImportModal, downloadImportTemplate, uploadImportExcel,

    // Гарантированный экспорт в window (для onclick/data-action из HTML)
    openImportModal: openImportModal,
    closeImportModal: closeImportModal,
    downloadImportTemplate: downloadImportTemplate,
    uploadImportExcel: uploadImportExcel,
    login, logout,
    showAvailability, selectAvailWeek, availCarouselSkip,
    selectAvailDay, setAvailMode, loadAvailability, updateUI, toggleConflicts,
    toggleAvailHeatmap, toggleAvailGroupByCourse, closeAvailability,
    exportAvailExcel, exportAvailPDF,
    renderAvailTable, _clickLesson, ensureDOMNotEmpty,
    switchAdminTab, openDashboard, restoreTrashItem, purgeTrash, confirmModal,
    addExcludedDate, deleteExcludedDate,
    downloadBackup, restoreBackup, checkOrphans, confirmDeleteOrphans, clearOrphanResult,
    loadBellScheduleTab, applyBellPreset, saveBellSchedule,
    _showKimiAlert: showKimiAlert,
    toggleTheme,
});

// lessonsMap пересоздаётся при каждой загрузке недели, поэтому в window нужен
// getter: Object.assign копировал ссылку на пустой объект один раз и «залипал».
Object.defineProperty(window, 'lessonsMap', {
    get: () => state.lessonsMap,
    configurable: true,
});

/** Делегирование событий для data-action атрибутов */
document.addEventListener('click', e => {
    const el = e.target.closest('[data-action]');
    if (!el) return;
    const action = el.dataset.action;
    if (action === 'openImportModal') {
        e.preventDefault();
        openImportModal(e);
        return;
    }
    // JSON.parse на кривом data-атрибуте бросал исключение и ломал весь клик.
    let params = [];
    if (el.dataset.params) {
        try {
            params = JSON.parse(el.dataset.params);
        } catch {
            params = [];
        }
    }
    const fn = window[action];
    if (typeof fn === 'function') {
        e.preventDefault();
        fn(...params);
    }
});

/** Выпадающие меню (dropdowns): открытие по триггеру, закрытие вне меню, по Escape и после выбора пункта */
document.addEventListener('click', e => {
    const toggle = e.target.closest('[data-dropdown-toggle]');
    const inside = e.target.closest('.dropdown');
    const menuItem = e.target.closest('.dropdown-menu');
    const openList = document.querySelectorAll('.dropdown.open');
    if (toggle && !toggle.closest('.dropdown').classList.contains('open')) {
        openList.forEach(d => d.classList.remove('open'));
        toggle.closest('.dropdown').classList.add('open');
    } else if (menuItem || (!toggle && !inside)) {
        openList.forEach(d => d.classList.remove('open'));
    }
});

document.addEventListener('keydown', e => {
    if (e.key === 'Escape') {
        document.querySelectorAll('.dropdown.open').forEach(d => d.classList.remove('open'));
        return;
    }
    // Кликабельные div'ы с data-action не работали с клавиатуры: Enter/Space
    // должны вести себя как клик, иначе интерфейс недоступен без мыши.
    if (e.key !== 'Enter' && e.key !== ' ') return;
    const el = e.target.closest('[data-action]');
    if (!el) return;
    if (['BUTTON', 'A', 'INPUT', 'SELECT', 'TEXTAREA'].includes(el.tagName)) return;
    e.preventDefault();
    el.click();
});

/** Theme Management */
function initTheme() {
    let theme = localStorage.getItem('theme');
    if (!theme) {
        theme = window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
    }
    document.documentElement.setAttribute('data-theme', theme);
    const btn = document.getElementById('btn-theme');
    if (btn) btn.textContent = theme === 'dark' ? '☀️ Светлая тема' : '🌙 Тёмная тема';
}

export function toggleTheme() {
    const html = document.documentElement;
    const next = html.getAttribute('data-theme') === 'dark' ? 'light' : 'dark';
    html.setAttribute('data-theme', next);
    localStorage.setItem('theme', next);
    const btn = document.getElementById('btn-theme');
    if (btn) btn.textContent = next === 'dark' ? '☀️ Светлая тема' : '🌙 Тёмная тема';
}

/** Инициализация */
async function init() {
    initTheme();
    const importBtn = document.getElementById('btn-import-excel');
    if (importBtn) {
        importBtn.addEventListener('click', (e) => {
            e.preventDefault();
            console.log('Direct click: openImportModal triggered');
            openImportModal(e);
        });
    }
    try {
        state.bellSchedule = await api('/api/bell-schedule');
        if (!Array.isArray(state.bellSchedule)) state.bellSchedule = [];
    } catch (error) {
        console.error('Ошибка загрузки расписания звонков:', error);
        state.bellSchedule = [];
    }
    let auth = {};
    try {
        auth = await api('/api/auth/check');
    } catch (error) {
        console.error('Ошибка проверки авторизации:', error);
    }
    state.isAdmin = !!auth.is_admin;
    if (state.isAdmin) {
        try {
            const tokenData = await api('/api/auth/csrf-token');
            state.csrfToken = tokenData.csrf_token || '';
        } catch (error) {
            console.error('Ошибка получения CSRF-токена:', error);
        }
    }
    updateUI();
    try {
        await loadReferences();
    } catch (error) {
        console.error('Ошибка загрузки справочников:', error);
    }
    const { renderHomePage } = await import('./ui.js');
    renderHomePage();
}

window.addEventListener('error', e => {
    if (e.message) console.error('[Глобальная ошибка]', e.message, e.filename, e.lineno, e.colno);
});

window.addEventListener('unhandledrejection', e => {
    console.error('[Необработанный промис]', e.reason);
});

window.showToast = function(message, type) {
    const existing = document.querySelector('.t-toast');
    if (existing) existing.remove();
    const toast = document.createElement('div');
    toast.className = 't-toast' + (type ? ' ' + type : '');
    toast.textContent = message;
    document.body.appendChild(toast);
    void toast.offsetWidth;
    toast.classList.add('is-visible');
    setTimeout(() => {
        toast.classList.remove('is-visible');
        toast.classList.add('is-hiding');
        setTimeout(() => toast.remove(), 150);
    }, 3000);
};

// init() асинхронный: без обработчика любая ошибка внутри давала «белый экран»
// с записью только в консоль.
init().catch(error => {
    console.error('Ошибка инициализации приложения:', error);
    if (window.showToast) window.showToast('Не удалось загрузить приложение', 'error');
});
