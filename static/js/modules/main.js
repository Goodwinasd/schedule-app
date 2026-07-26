/**
 * Точка входа приложения
 * Привязывает функции к window для обратной совместимости с onclick-атрибутами в HTML
 * @module main
 */

import state from './state.js';
import { api } from './api.js';
import {
    goHome, showSchedule, showLoginModal, closeModals,
    showAdminPanel, switchAdminTab,
    login, logout,
    showAvailability, selectAvailWeek, availCarouselSkip,
    selectAvailDay, setAvailMode, loadAvailability, updateUI, toggleConflicts,
    toggleAvailHeatmap, toggleAvailGroupByCourse, closeAvailability,
    renderAvailTable, _clickLesson,
} from './ui.js';
import { confirmModal } from './modal.js';
import { loadScheduleTable, printSchedule, exportSchedule, showAddLessonModal, addLesson, editLesson, saveLesson, addSubgroupLesson, deleteCurrentLesson, validateLesson } from './schedule.js';
import { loadReferences, renderRefList, addGroup, editGroup, addSubject, editSubject, editTeacher, editClassroom, advanceCourses, addRefItem, deleteRefItem, restoreRefItem, quickAdd, quickAddGroup } from './references.js';
import { renderCarousel, setActiveWeek, selectWeekByDate, carouselSkip, showAddWeekModal, updateWeekPreview, addWeek, restoreWeek, deleteWeek } from './nav.js';
import { saveSetting, addExcludedDate, deleteExcludedDate } from './settings.js';
import { restoreTrashItem, purgeTrash } from './trash.js';

/* Привязка к window для onclick-вызовов из HTML */
Object.assign(window, {
    goHome, showSchedule, showLoginModal, closeModals,
    selectWeekByDate, carouselSkip, showAddWeekModal, addWeek, restoreWeek, deleteWeek,
    loadScheduleTable, printSchedule, exportSchedule,
    showAddLessonModal, addLesson, editLesson, saveLesson, addSubgroupLesson,
    deleteCurrentLesson, validateLesson,
    loadReferences, showAdminPanel, renderRefList,
    addGroup, editGroup, addSubject, editSubject, editTeacher, editClassroom, advanceCourses,
    addRefItem, deleteRefItem, restoreRefItem, quickAdd, quickAddGroup, saveSetting,
    login, logout,
    showAvailability, selectAvailWeek, availCarouselSkip,
    selectAvailDay, setAvailMode, loadAvailability, updateUI, toggleConflicts,
    toggleAvailHeatmap, toggleAvailGroupByCourse, closeAvailability,
    renderAvailTable, _clickLesson,
    switchAdminTab, restoreTrashItem, purgeTrash, confirmModal,
    addExcludedDate, deleteExcludedDate,
    // Для доступа из inline onclick к lessonsMap в renderScheduleTable
    lessonsMap: state.lessonsMap,
});

/** Делегирование событий для data-action атрибутов */
document.addEventListener('click', e => {
    const el = e.target.closest('[data-action]');
    if (!el) return;
    const action = el.dataset.action;
    const params = el.dataset.params ? JSON.parse(el.dataset.params) : [];
    const fn = window[action];
    if (typeof fn === 'function') {
        e.preventDefault();
        fn(...params);
    }
});

/** Инициализация */
async function init() {
    state.bellSchedule = await api('/api/bell-schedule');
    const data = await api('/api/auth/check');
    state.isAdmin = data.is_admin;
    if (state.isAdmin) {
        const tokenData = await api('/api/auth/csrf-token');
        state.csrfToken = tokenData.csrf_token || '';
    }
    updateUI();
    await loadReferences();
    const { renderHomePage } = await import('./ui.js');
    renderHomePage();
}

init();
