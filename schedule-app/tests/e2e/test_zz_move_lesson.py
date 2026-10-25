"""E2E: перенос урока через модалку.

Актуально для тач-устройств: HTML5 drag&drop на iOS/Android не работает,
поэтому перенос делается формой «день + пара» и частичным PUT.
Файл назван test_zz_*, чтобы выполняться после остальных e2e: он меняет данные.
"""

import datetime

import pytest

pytest.importorskip('playwright.sync_api', reason='pytest-playwright не установлен')


def _monday_iso():
    today = datetime.date.today()
    return (today - datetime.timedelta(days=today.weekday())).isoformat()


def _login(page, base_url):
    page.goto(f'{base_url}/', wait_until='domcontentloaded')
    page.click('#btn-login')
    page.fill('#login-password', 'TestPass123!')
    page.click('[data-action="login"]')
    page.wait_for_selector('#login-modal', state='hidden')


def _open_group_schedule(page, base_url):
    groups = page.request.get(f'{base_url}/api/groups').json()
    gid = next(g['id'] for g in groups if g['name'] == '01-09/25')
    page.evaluate('(id) => window.showSchedule("group", id, "01-09/25")', gid)
    page.wait_for_selector('.schedule-table')


def _lesson_day_index(page, base_url):
    """Индекс дня недели, где сейчас есть урок (на мобильном видна только одна колонка)."""
    data = page.request.get(f'{base_url}/api/schedule-table',
                            params={'group': '01-09/25', 'monday': _monday_iso()}).json()
    days = data['days']
    for row in data['periods']:
        for date, lessons in row['lessons'].items():
            if lessons:
                for i, day in enumerate(days):
                    if day['date'] == date:
                        return i
    return 0


def _open_edit_modal(page, base_url):
    idx = _lesson_day_index(page, base_url)
    tabs = page.locator('.mobile-day-tab')
    if tabs.count() and tabs.first.is_visible():
        page.locator(f'.mobile-day-tab[data-day-index="{idx + 1}"]').first.click()
        page.wait_for_timeout(400)
    page.wait_for_selector('.schedule-table .lesson-content', timeout=10000)
    page.locator('.schedule-table .lesson-content').first.click()
    page.wait_for_selector('#add-lesson-modal', state='visible')


@pytest.mark.e2e
def test_move_lesson_via_modal(page, e2e_server):
    _login(page, e2e_server)
    _open_group_schedule(page, e2e_server)
    _open_edit_modal(page, e2e_server)

    page.click('#btn-move-lesson')
    page.wait_for_selector('#move-lesson-block', state='visible')
    page.select_option('#move-day', index=1)      # Вторник
    page.select_option('#move-period', '3')       # 3-я пара
    page.click('[data-action="saveMove"]')
    page.wait_for_selector('#add-lesson-modal', state='hidden')
    page.wait_for_timeout(1200)

    data = page.request.get(f'{e2e_server}/api/schedule-table',
                            params={'group': '01-09/25', 'monday': _monday_iso()}).json()
    monday = next(d['date'] for d in data['days'] if d['day_name'] == 'Понедельник')
    tuesday = next(d['date'] for d in data['days'] if d['day_name'] == 'Вторник')

    def lessons_on(period, date):
        row = next(p for p in data['periods'] if p['period'] == period)
        return row['lessons'].get(date, [])

    assert not lessons_on(1, monday), 'урок остался на старом месте (Пн, 1 пара)'
    assert any(l.get('subject') == 'Математика' for l in lessons_on(3, tuesday)), \
        'урок не переехал на Вт, 3 пару'


@pytest.mark.e2e
def test_move_form_fits_mobile(page, e2e_server):
    page.set_viewport_size({'width': 390, 'height': 844})
    _login(page, e2e_server)
    _open_group_schedule(page, e2e_server)
    _open_edit_modal(page, e2e_server)

    page.click('#btn-move-lesson')
    page.wait_for_selector('#move-lesson-block', state='visible')
    form = page.locator('#move-lesson-block')
    box = form.bounding_box()
    assert box is not None and box['x'] >= 0
    assert box['x'] + box['width'] <= 390 + 1, 'форма переноса выходит за экран'
    assert page.locator('#move-day').is_visible()
    assert page.locator('#move-period').is_visible()
    assert page.locator('[data-action="saveMove"]').is_visible()

    # Отмена скрывает форму и не отправляет запрос
    page.click('[data-action="cancelMove"]')
    assert not form.is_visible()
