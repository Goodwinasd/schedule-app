/**
 * Точка входа приложения
 * Привязывает функции к window для обратной совместимости с onclick-атрибутами в HTML
 * @module main
 */

import state from './state.js';
import { api } from './api.js';
import {
    goHome, showSchedule, showLoginModal, closeModals,
    selectWeekByDate, carouselSkip, showAddWeekModal, addWeek, restoreWeek, deleteWeek,
    loadScheduleTable, printSchedule, exportSchedule,
    showAddLessonModal, addLesson, editLesson, saveLesson, addSubgroupLesson,
    deleteCurrentLesson, validateLesson,
    loadReferences, showAdminPanel, renderRefList,
    addGroup, editGroup, addSubject, editSubject, advanceCourses,
    addRefItem, deleteRefItem, quickAdd, quickAddGroup,
    login, logout,
    showAvailability, selectAvailWeek, availCarouselSkip,
    selectAvailDay, setAvailMode, loadAvailability, updateUI, toggleConflicts,
} from './ui.js';

/* Привязка к window для onclick-вызовов из HTML */
Object.assign(window, {
    goHome, showSchedule, showLoginModal, closeModals,
    selectWeekByDate, carouselSkip, showAddWeekModal, addWeek, restoreWeek, deleteWeek,
    loadScheduleTable, printSchedule, exportSchedule,
    showAddLessonModal, addLesson, editLesson, saveLesson, addSubgroupLesson,
    deleteCurrentLesson, validateLesson,
    loadReferences, showAdminPanel, renderRefList,
    addGroup, editGroup, addSubject, editSubject, advanceCourses,
    addRefItem, deleteRefItem, quickAdd, quickAddGroup,
    login, logout,
    showAvailability, selectAvailWeek, availCarouselSkip,
    selectAvailDay, setAvailMode, loadAvailability, updateUI, toggleConflicts,
    // Для доступа из inline onclick к lessonsMap в renderScheduleTable
    lessonsMap: state.lessonsMap,
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
