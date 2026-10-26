"""
E2E Smoke-тесты UI (Playwright / pytest-playwright).

Покрывают системную защиту от регрессий рендера:
- «белый экран» (#app пуст),
- «тихие выходы» (console.warn '[UI] Не найден DOM-элемент...'),
- падения рендера (console.error / pageerror),
- срабатывание UI Watchdog (ensureDOMNotEmpty).

Запуск: npm run test:e2e  (== pytest tests/e2e -v)
Требуется: pip install pytest-playwright && playwright install chromium
"""

import pytest

pytest.importorskip('playwright.sync_api', reason='pytest-playwright не установлен')


@pytest.mark.e2e
def test_availability_smoke(page, e2e_server):
    console_msgs = []
    page.on('console', lambda m: console_msgs.append((m.type, m.text)))
    page.on('pageerror', lambda err: console_msgs.append(('pageerror', str(err))))

    health = page.request.get(f'{e2e_server}/api/health')
    assert health.status == 200, health.text()
    assert health.json() == {'status': 'ok', 'db': 'ok'}

    page.goto(f'{e2e_server}/', wait_until='domcontentloaded')

    # 1. #app не пуст — нет «белого экрана»
    assert page.locator('#app').count() == 1, 'Контейнер #app отсутствует в DOM'
    assert page.locator('#app *').count() > 0, '#app пуст — белый экран'

    # 2. Вход администратора (API доступности требует @login_required)
    page.click('#btn-login')
    page.wait_for_selector('#login-modal', state='visible')
    page.fill('#login-password', 'TestPass123!')
    page.click('[data-action="login"]')
    page.wait_for_selector('#login-modal', state='hidden', timeout=5000)

    # 3. Открываем админ-панель и переходим в раздел «Свободные окна»
    page.click('#btn-admin')
    page.wait_for_selector('#references-modal', state='visible', timeout=5000)
    page.click('[data-action="openDashboard"]')
    try:
        page.wait_for_selector('#availability-view', state='visible', timeout=5000)
    except Exception as e:
        dump = page.evaluate("""() => {
            const g = id => document.getElementById(id);
            const v = g('availability-view');
            const r = v.getBoundingClientRect();
            return {
                availDisplay: getComputedStyle(v).display,
                availVisibility: getComputedStyle(v).visibility,
                availRect: {w: r.width, h: r.height},
                appVisibility: getComputedStyle(g('app')).visibility,
                appChildren: g('app') ? g('app').children.length : -1,
                availChildren: v.children.length,
                refsDisplay: getComputedStyle(g('references-modal')).display,
                headerTitle: g('header-title') ? g('header-title').textContent : null,
                domReady: document.readyState
            };
        }""")
        print('DUMP-ON-TIMEOUT:', dump)
        raise

    # 4. Контейнеры получили контент (таблица ИЛИ empty-карточка)
    page.wait_for_function(
        "() => {"
        "  const t = document.getElementById('avail-table-container');"
        "  const a = document.getElementById('avail-analytics');"
        "  return t && a && (t.textContent.trim() !== '' || a.textContent.trim() !== '');"
        "}", timeout=10000)

    table_count = page.locator('#avail-table-container .avail-table').count()
    empty_count = page.locator('#avail-table-container .avail-empty').count()
    assert table_count > 0 or empty_count > 0, \
        'Контейнер #avail-table-container не получил ни таблицу, ни карточку пустого состояния'

    # 4b. «По курсам»: преподаватели без уроков в неделю не исчезают из таблицы
    names_before = set(page.eval_on_selector_all(
        '#avail-table-container .avail-table tbody tr td:first-child',
        'els => els.map(e => e.textContent.trim())',
    ))
    page.click('#btn-avail-group-course')
    page.wait_for_timeout(300)
    names_after = set(page.eval_on_selector_all(
        '#avail-table-container .avail-table tbody tr:not(.avail-course-header) td:first-child',
        'els => els.map(e => e.textContent.trim())',
    ))
    assert names_after == names_before, \
        f'Группировка «По курсам» теряет преподавателей (пропали: {names_before - names_after})'

    # 5. В консоли нет ошибок рендера и сработавших сторожей
    ui_warns = [t for _, t in console_msgs if '[UI] Не найден DOM-элемент' in t]
    hard_errors = [t for kind, t in console_msgs
                   if kind == 'pageerror' or (kind == 'error' and 'Ошибка рендеринга' in t)]
    watchdog = [t for _, t in console_msgs if '[UI Watchdog]' in t]
    assert not ui_warns, f'Тихие выходы из-за отсутствующих DOM-элементов: {ui_warns}'
    assert not hard_errors, f'Критические ошибки консоли: {hard_errors}'
    assert not watchdog, f'UI Watchdog сработал при штатном рендере: {watchdog}'


@pytest.mark.e2e
def test_export_avail_excel_download(page, e2e_server):
    """Кнопка «Экспорт Excel» реально скачивает .xls-файл с BOM и таблицей."""
    page.goto(f'{e2e_server}/', wait_until='domcontentloaded')
    page.click('#btn-login')
    page.wait_for_selector('#login-modal', state='visible')
    page.fill('#login-password', 'TestPass123!')
    page.click('[data-action="login"]')
    page.wait_for_selector('#login-modal', state='hidden', timeout=5000)
    page.click('#btn-admin')
    page.wait_for_selector('#references-modal', state='visible', timeout=5000)
    page.click('[data-action="openDashboard"]')
    page.wait_for_function(
        "() => document.getElementById('avail-table-container').textContent.trim() !== ''",
        timeout=10000)

    with page.expect_download(timeout=10000) as dl_info:
        page.click('[data-action="exportAvailExcel"]')
    download = dl_info.value
    assert 'Свободные_окна_неделя_' in download.suggested_filename, \
        f'Имя файла не содержит номер недели: {download.suggested_filename}'
    assert download.suggested_filename.endswith('.xls'), download.suggested_filename
    content = open(download.path(), 'rb').read()
    assert content.startswith(b'\xef\xbb\xbf'), 'Файл должен содержать UTF-8 BOM'
    assert b'<table' in content, 'В файле нет HTML-таблицы'


@pytest.mark.e2e
def test_substitution_suggest_widget(page, e2e_server):
    """Виджет «Подобрать замену» в модалке урока: включение замены заполняет
    список свободных преподавателей на пару и позволяет выбрать подменяющего."""
    console_msgs = []
    page.on('console', lambda m: console_msgs.append((m.type, m.text)))
    page.on('pageerror', lambda err: console_msgs.append(('pageerror', str(err))))

    page.goto(f'{e2e_server}/', wait_until='domcontentloaded')
    page.click('#btn-login')
    page.wait_for_selector('#login-modal', state='visible')
    page.fill('#login-password', 'TestPass123!')
    page.click('[data-action="login"]')
    page.wait_for_selector('#login-modal', state='hidden', timeout=5000)

    # Открываем расписание группы с уроками
    page.wait_for_function("() => document.querySelectorAll('#groups-grid a, #groups-grid .select-card, #groups-grid [onclick*=showSchedule]').length > 0", timeout=5000)
    page.eval_on_selector_all('#groups-grid [onclick*=showSchedule]', 'els => els[0].click()')
    page.wait_for_selector('.schedule-table', state='visible', timeout=10000)

    # Открываем модалку редактирования первого урока
    page.click('[onclick*="editLesson"]')
    page.wait_for_selector('#add-lesson-modal', state='visible', timeout=5000)

    # Открываем модалку, загружаем рекомендации (виджет вызывается по кнопке)
    page.check('#lesson-is-substitution')

    # Ждём ответа бэкенда (запрос стартует по клику), затем появления опций в select
    with page.expect_response(
            lambda r: '/api/schedule/substitutions-suggest' in r.url and r.ok,
            timeout=10000) as resp_info:
        page.click('#substitution-suggest-block [data-action="refreshSubstitutionSuggest"]')
    assert resp_info.value.status == 200
    page.wait_for_selector('#lesson-substitution-select option:not([value=""])', state='attached', timeout=10000)
    page.wait_for_function(
        "() => { const s = document.getElementById('lesson-substitution-select'); "
        "return s && s.options.length > 1; }",
        timeout=10000)

    # В списке предложения — select со свободными преподавателями
    sel = page.locator('#lesson-substitution-select')
    opts = sel.locator('option').all_text_contents()
    assert len(opts) > 1, f'Виджет не предлагает ни одного свободного преподавателя: {opts}'

    # Выбранный подменяющий попадает в селект преподавателя
    page.select_option('#lesson-substitution-select', index=1)
    page.wait_for_timeout(100)
    chosen = page.eval_on_selector('#lesson-teacher', 's => s.value')
    assert chosen not in ('', None), 'Подменяющий преподаватель не выбран в селект'

    # Никаких ошибок рендера при работе виджета
    hard_errors = [t for kind, t in console_msgs if kind == 'pageerror']
    assert not hard_errors, f'Критические ошибки при работе виджета: {hard_errors}'


@pytest.mark.e2e
def test_drag_drop_lesson_move(page, e2e_server):
    """Drag-and-Drop: админ перетаскивает пару в другую ячейку сетки.

    Проверяет полный контракт фичи:
    - карточки пар получают draggable=true (только для админа),
    - drop отправляет PUT /api/lessons/<id> с day_id и period,
    - при 200 карточка остаётся в новой ячейке (Optimistic UI),
    - при 409 карточка возвращается в исходную ячейку (rollback),
    - в любом случае показывается тост (успех или предупреждение).
    """
    pageerrors = []
    page.on('pageerror', lambda err: pageerrors.append(str(err)))

    page.goto(f'{e2e_server}/', wait_until='domcontentloaded')
    page.click('#btn-login')
    page.wait_for_selector('#login-modal', state='visible')
    page.fill('#login-password', 'TestPass123!')
    page.click('[data-action="login"]')
    page.wait_for_selector('#login-modal', state='hidden', timeout=5000)

    # Открываем расписание группы с уроками (та же группа, что в других smoke-тестах)
    page.wait_for_function("() => document.querySelectorAll('#groups-grid a, #groups-grid .select-card, #groups-grid [onclick*=showSchedule]').length > 0", timeout=5000)
    page.eval_on_selector_all('#groups-grid [onclick*=showSchedule]', 'els => els[0].click()')
    page.wait_for_selector('.schedule-table', state='visible', timeout=10000)
    page.wait_for_function(
        "() => document.querySelectorAll('.lesson-content[draggable=\"true\"]').length > 0",
        timeout=10000)

    # Выбираем источник и цель: пустая ячейка в другом дне (иначе — любая ячейка другого дня)
    plan = page.evaluate("""() => {
        const cards = [...document.querySelectorAll('.lesson-content[draggable="true"]')];
        if (!cards.length) return null;
        const card = cards[0];
        const srcDay = card.dataset.dayId;
        const cells = [...document.querySelectorAll('td.day-cell[data-day-id]')]
            .filter(c => c.dataset.dayId && c.dataset.dayId !== srcDay);
        if (!cells.length) return null;
        const target = (cells.find(c => c.classList.contains('empty-cell')) || cells[0]);
        return {
            lessonId: parseInt(card.dataset.lessonId),
            srcDay: srcDay,
            srcPeriod: parseInt(card.dataset.period),
            dstDay: target.dataset.dayId,
            dstPeriod: parseInt(target.dataset.period)
        };
    }""")
    assert plan, 'Не удалось подобрать пару «карточка → ячейка другого дня»'

    with page.expect_response(
            lambda r: r.request.method == 'PUT' and '/api/lessons/' in r.url,
            timeout=10000) as resp_info:
        page.drag_and_drop(
            f'.lesson-content[draggable="true"][data-lesson-id="{plan["lessonId"]}"]',
            f'td.day-cell[data-day-id="{plan["dstDay"]}"][data-period="{plan["dstPeriod"]}"]')
    resp = resp_info.value
    assert resp.status in (200, 409), f'Неожиданный статус PUT: {resp.status}'

    body = resp.request.post_data_json
    assert int(body['day_id']) == int(plan['dstDay']), body
    assert int(body['period']) == int(plan['dstPeriod']), body

    # UI-состояние после дропа
    src_sel = f'td.day-cell[data-day-id="{plan["srcDay"]}"][data-period="{plan["srcPeriod"]}"]'
    dst_sel = f'td.day-cell[data-day-id="{plan["dstDay"]}"][data-period="{plan["dstPeriod"]}"]'
    card_sel = f'.lesson-content[data-lesson-id="{plan["lessonId"]}"]'
    if resp.status == 200:
        assert page.locator(f'{dst_sel} {card_sel}').count() >= 1, \
            'Карточка не осталась в новой ячейке после успешного перемещения'
        assert page.locator(f'{src_sel} {card_sel}').count() == 0, \
            'Карточка не удалилась из исходной ячейки после перемещения'
    else:
        assert page.locator(f'{src_sel} {card_sel}').count() >= 1, \
            'При конфликте карточка не вернулась в исходную ячейку'
        assert page.locator(f'{dst_sel} {card_sel}').count() == 0, \
            'При конфликте карточка осталась в чужой ячейке'

    # Тост: успех или предупреждение о конфликте
    page.wait_for_timeout(200)
    toasts = ' '.join(page.locator('#toast-container .toast').all_text_contents())
    if resp.status == 200:
        assert 'Пара перемещена' in toasts, f'Нет тоста «Пара перемещена»: {toasts}'
    else:
        assert any(k in toasts for k in ('занят', 'busy', 'Duplicate', 'Conflict', 'дублиру')), \
            f'Нет предупреждающего тоста при конфликте: {toasts}'

    assert not pageerrors, f'Критические ошибки при drag-and-drop: {pageerrors}'


@pytest.mark.e2e
def test_watchdog_fills_emptied_container(page, e2e_server):
    console_errors = []
    page.on('console', lambda m: console_errors.append(m.text) if m.type == 'error' else None)

    page.goto(f'{e2e_server}/', wait_until='domcontentloaded')
    page.click('#btn-login')
    page.wait_for_selector('#login-modal', state='visible')
    page.fill('#login-password', 'TestPass123!')
    page.click('[data-action="login"]')
    page.wait_for_selector('#login-modal', state='hidden', timeout=5000)
    page.click('#btn-admin')
    page.wait_for_selector('#references-modal', state='visible', timeout=5000)
    page.click('[data-action="openDashboard"]')
    page.wait_for_function(
        "() => document.getElementById('avail-table-container').textContent.trim() !== ''",
        timeout=10000)

    # Искусственно очищаем контейнер таблицы и вызываем Watchdog напрямую
    page.evaluate(
        "() => {"
        "  const c = document.getElementById('avail-table-container');"
        "  c.innerHTML = '';"
        "  window.ensureDOMNotEmpty('avail-table-container', 'Не удалось отобразить таблицу доступности.');"
        "}")

    fallback = page.locator('#avail-table-container .ui-watchdog-fallback')
    assert fallback.count() == 1, 'UI Watchdog не восстановил очищенный контейнер'
    assert 'Повторить запрос' in fallback.inner_text(), \
        'Fallback-карточка не содержит кнопки «Повторить запрос»'
    assert any('[UI Watchdog] Контейнер #avail-table-container остался пустым' in e for e in console_errors), \
        f'Watchdog не зафиксировал ошибку в консоли: {console_errors}'
