---
name: schedule-app
description: Use for any task in the schedule-app Flask project. Covers architecture, key files, test setup, migration chain, UI design system, and conventions. Load this skill at session start to avoid re-scanning the codebase.
---

# schedule-app project reference

## Quick facts
- **Stack**: Flask + SQLite (WAL, `busy_timeout=10s`) + Alembic, ванильный JS (ES-модули, без сборщика),
  экспорт `openpyxl` / `python-docx` / **`reportlab`** (weasyprint не используется).
- **Tests**: `python -m pytest tests/ -q --ignore=tests/e2e` → **304 passed**;
  e2e (`tests/e2e`, Playwright/Chromium) → **5 passed**. Всего **309**.
- **Python**: 3.13, PEP 8 (аннотации типов приветствуются, но исторический код без них).
- **Git**: репозиторий в корне воркспейса; UI-рефакторинг — ветка `ui/modernization`.
  Коммит только после «ок» пользователя (см. `AGENTS.md`).

## Architecture (key files)

| File | Role |
|---|---|
| `app.py` | Flask factory (module-level `app`), CORS, Swagger, APScheduler-бэкапы, старт под `__main__` |
| `routes.py` | **Все** API — 3603 строки, ~84 правила: auth, crud, schedule, days, lessons, export, curriculum, trash, settings, availability, backup/restore, import |
| `utils.py` | `LESSON_SELECT`, `LESSON_SELECT_WITH_DAY`, `_validate_lesson_data()`, `_validate_slot_3d()`, Excel-схемы, `_safe_filename()` |
| `db.py` | `get_db()` (таймер медленных запросов), `run_alembic_upgrade()`, `ensure_curriculum_table()`, `ensure_teacher_tables()`, бэкапы, поиск сирот |
| `config.py` | Конфиг из `.env`, валидация пароля, `SETTINGS` из БД, схема звонков |
| `generator.py` | `generate_schedule()` — жадное размещение по `curriculum`, замены, зеркалирование потоков |
| `schedule_balancer.py` | `weekly_pairs()`, `validate_weekly_load()` |
| `cache.py` | Самописный `TTLCache` (`refs_cache`, TTL 300 c) — не Flask-Caching |
| `static/js/modules/main.js` | Точка входа: `init()`, экспорт ~60 функций в `window`, делегирование `[data-action]` |
| `static/js/modules/api.js` | `api(url, options)` — fetch + CSRF + тосты + `DATA_MUTATED`, таймаут 30 c |
| `static/js/modules/schedule.js` | Рендер таблицы, CRUD уроков, drag&drop, генерация, экспорт |
| `static/js/modules/ui.js` | Главная, карточки, «свободные окна», аналитика, `_clickLesson` |
| `static/js/modules/nav.js` | Карусель недель, добавление/удаление недели, сводка |
| `static/js/modules/references.js` | Админ-панель справочников, импорт Excel |
| `templates/index.html` | SPA-разметка (369 строк), 5 вкладок админки, модалки |

## Database tables
`lessons`, `schedule_days`, `groups_list`, `teachers`, `subjects`, `classrooms_list`,
`excluded_dates`, `lesson_history`, `settings`, `curriculum`, `specialties`,
`teacher_absences`, `teacher_subjects`.

### `lessons` (ключевые колонки)
`id`, `day_id`, `period`, `subject_id`, `teacher_id`, `classroom_id`, `group_id`, `subgroup`,
`deleted_at`, `is_substitution`, `original_teacher_id`, `substitution_reason`.

## Alembic migration chain (linear, single head = `f7g8h9i0j1k2`)
```
32541b42023a (initial)
 → c46c7442d88a (deleted_at)
 → 92ef138d4cfb (indexes)
 → fdb6c2208bbf (phone)
 → 2a9e8f7d6c5b (unique index)
 → 3b8e4f1a2c7d (settings)
 → 4c5d6e7f8a9b (backup_retention)
 → a1b2c3d4e5f6 (substitution fields)
 → b1c2d3e4f5a6 (default_classroom_id)
 → c1d2e3f4a5b6 (teacher_absences/teacher_subjects)
 → df2a1c3b4e5f (is_published)
 → e5f6a7b8c9d0 (specialties)
 → f7g8h9i0j1k2 (curriculum specialty fields) ← HEAD
```
13 ревизий. `curriculum` создаётся **не миграцией**, а `db.ensure_curriculum_table()`.

## UI design system (с 2026-10)
`static/css/style.css` (3048 строк) работает на токенах:
- палитра/типографика/отступы/радиусы/тени — `:root`, тёмная тема — `[data-theme="dark"]`;
- исторические имена (`--bg`, `--surface`, `--text`, `--accent`, `--border`, `--radius`) — **алиасы** на `--color-*`/`--accent-*`;
- `!important` допустим только в `@media print`, `prefers-reduced-motion`, мобильных фиксах;
- инлайн-стили запрещены, кроме `style="display:none"` (JS ставит `style.display=''`);
  для остального — утилиты в конце файла (`.mw-*`, `.spacer-*`, `.checkbox-row`, `.hint-text`, `.divider`, `.panel-pad`, `.text-sm`);
- шаг отступов 4px (`--space-1..12`), высоты контролов 32/36/40, радиусы 6/12/16/20;
- замена преподавателя — класс `.is-substitution` (не инлайн-стиль).

## Event bus pattern
`api()` после успешной мутации сам шлёт `DATA_MUTATED` (маппинг URL → entity в `api.js`).
Слушатели: `schedule.js`, `references.js`, `curriculum.js`, `ui.js`. Для запросов мимо `api()`
(например, `DELETE /api/schedule/clear-week`) событие надо отправлять вручную.

## CSRF / Auth
- Админ: `session['is_admin']`; все write-эндпоинты под `@login_required`.
- CSRF: `session['csrf_token']`, заголовок `X-CSRF-Token`; исключения — `/api/auth/*`.
- Лимит логина: `login_rate_limit`/`login_rate_window` из `settings`, ключ — IP.
- Публичные (без авторизации) GET: справочники (без `phone`/`deleted_at`), расписание группы/преподавателя/аудитории, `/api/export`. Массовый `type=all` — только админ.

## Soft-delete pattern
- `deleted_at DATETIME` + фильтры `WHERE deleted_at IS NULL`;
- удаление пишет `datetime('now')` **только если `deleted_at IS NULL`** (иначе теряется исходная метка);
- восстановление — с проверкой конфликтов; удаление недели каскадит в уроки.

## Key API facts
- `POST /api/schedule/generate` — `{group_id, semester, monday, week_count|weeks_count}` → `{created, errors}`.
- `GET /api/schedule/substitutions-suggest?date&period` → `{available: [{id, name}]}`.
- `GET /api/export?type=group|teacher|classroom&name&monday&format=xlsx|docx|pdf`.
- `GET /api/schedule/export/excel?type=group|teacher|classroom|all&id&start_date` (`all` — админ).
- `PUT /api/lessons/<id>` — частичное обновление: отсутствующие поля сохраняются.
- Кривые даты/числа → **400** (`_parse_date`, `_int_param`, обработчик `ValueError`).

## Test setup
- `tests/conftest.py`: session-scoped temp DB + `run_alembic_upgrade()`, очистка таблиц
  перед каждым тестом, сброс `refs_cache`, защита «не чистить не-temp БД».
- Фикстуры: `seed_refs` (2 преподавателя/предмета/группы, 2 аудитории), `seed_days` (3 дня), `seed_lessons` (2 урока).
- `tests/test_regressions.py` — регрессии аудита (частичный PUT, `deleted_at`, публичные поля, 400, restore).
- e2e запускает свой сервер на порту 5055 с копией `data/schedule.db`.

## Known dead code (removed, don't recreate)
- `schedule-app/seed_*.py`; `static/js/modules/auth.js`, `navigation.js`; `@cached` из `cache.py`.

## Settings defaults (вставляет `_clean_tables()` и миграция `4c5d6e7f8a9b`)
```sql
session_lifetime=3600, login_rate_limit=5, login_rate_window=300, backup_retention_days=30
```
`session_lifetime` фактически **не влияет** на cookie (сессия не помечается `permanent`).

## Token-saving rules
1. Не перечитывать файлы, описанные здесь.
2. Не сканировать структуру — использовать таблицу выше.
3. Возвращать только диффы, не целые файлы.
4. После правок Python — `pytest tests/ -q --ignore=tests/e2e`; после UI — e2e + скриншоты.
