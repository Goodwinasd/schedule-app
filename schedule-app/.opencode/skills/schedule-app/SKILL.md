---
name: schedule-app
description: Use for any task in the schedule-app Flask project. Covers architecture, key files, test setup, migration chain, recent work, and conventions. Load this skill at session start to avoid re-scanning the codebase.
---

# schedule-app project reference

## Quick facts
- **Stack**: Flask + SQLite (+ Alembic migrations), vanilla JS frontend, openpyxl/python-docx/weasyprint exports
- **Tests**: `pytest tests/ -v` — 144 tests, all pass
- **Git**: 5 commits, last = `5e5aae5`. DO NOT commit unless told.
- **Python**: 3.13, PEP 8, type hints required

## Architecture (key files)

| File | Role |
|---|---|
| `app.py` | Flask factory, blueprints, error handlers |
| `routes.py` | All API routes (~2600 lines). Groups: auth, crud (subjects/teachers/classrooms/groups/days/lessons), schedule, export, curriculum, trash, settings, availability, backup/restore |
| `utils.py` | SQL constants (`LESSON_SELECT`, `LESSON_SELECT_WITH_DAY`), `_validate_lesson_data()`, `safe_filename()` |
| `db.py` | `get_db()`, `run_alembic_upgrade()`, `close_db()`, `ensure_curriculum_table()` |
| `config.py` | All config with env overrides |
| `generator.py` | `generate_schedule()` — reads `curriculum`, skips `excluded_dates`, writes to `lessons` |
| `cache.py` | Flask-caching setup (simple cache) |
| `static/js/modules/schedule.js` | All schedule CRUD + `generateFromCurriculum()` + `renderScheduleTable()` |
| `static/js/modules/main.js` | Entry point, imports all modules, attaches to `window` |
| `static/js/modules/api.js` | `apiRequest()` + `DATA_MUTATED` event bus |
| `static/js/modules/nav.js` | Tab navigation |
| `templates/index.html` | Single-page app HTML |

## Database tables
`lessons`, `schedule_days`, `groups_list`, `teachers`, `subjects`, `classrooms_list`, `excluded_dates`, `lesson_history`, `settings`, `curriculum`

### `lessons` columns (key ones)
- `id`, `day_id`, `period`, `subject_id`, `teacher_id`, `classroom_id`, `group_id`
- `deleted_at` (soft-delete), `is_substitution` (bool, default 0), `original_teacher_id` (FK teachers, nullable), `substitution_reason` (text)

## Alembic migration chain (linear, single head)
```
32541b42023a (initial)
  → c46c7442d88a (deleted_at)
    → 92ef138d4cfb (indexes)
      → fdb6c2208bbf (phone)
        → 2a9e8f7d6c5b (unique index)
          → 3b8e4f1a2c7d (settings)
            → 4c5d6e7f8a9b (backup_retention)
              → a1b2c3d4e5f6 (substitution fields) ← HEAD
```
All revisions in `migrations/versions/`.

## Event bus pattern
Frontend uses `DATA_MUTATED` custom event (`api.js`). After any DB write, dispatch `window.dispatchEvent(new CustomEvent('DATA_MUTATED'))`. All UI components listen for it and refresh.

## CSRF / Auth
- Admin check: `session.get('is_admin')`
- CSRF: `session['csrf_token']` — required on all write endpoints (`POST/PUT/DELETE`), checked via `request.headers.get('X-CSRF-Token')`
- Rate limiting on login (settings: `login_rate_limit`, `login_rate_window`)

## Soft-delete pattern
- Tables use `deleted_at DATETIME` (nullable)
- Routes filter `WHERE deleted_at IS NULL` by default
- Delete sets `deleted_at = datetime.utcnow()`
- Restore sets `deleted_at = NULL` with conflict detection
- Week delete cascades to lessons

## Key patterns
- `_validate_lesson_data(day_id, period, subject_id, teacher_id, classroom_id, group_id, exclude_id=None)`: returns `(conflict_type or None)`
- `POST /api/schedule/generate`: body `{group_id, semester, year}` → `{created: int, errors: [...]}`
- `GET /api/schedule/substitutions-suggest`: query `date, period, teacher_id` → `{available: [{id, name}]}`
- All export endpoints: `POST /api/export/<format>` with body `{group_id|teacher_id|classroom_id, week_offset?}`

## Test setup
- `conftest.py`: session-scoped temp DB, `run_alembic_upgrade()` on setup, auto-clean between tests
- Fixtures: `seed_refs` (teachers 1,2; subjects 1,2; groups 1,2), `seed_days` (3 days), `seed_lessons` (2 lessons)

## Known dead code (removed, don't recreate)
- `schedule-app/seed_*.py` (3 files)
- `static/js/modules/auth.js`, `static/js/modules/navigation.js`
- `@cached` decorator from `cache.py`

## Settings defaults (inserted by `_clean_tables()`)
```sql
session_lifetime=3600, login_rate_limit=5, login_rate_window=300, backup_retention_days=30
```

## CSS variables for styling
`--warning-bg`, `--warning-text` used for substitution row highlighting.

## Recent feature: auto-generator + substitutions
- `generator.py`: `generate_schedule()` reads `curriculum` by `(group_id, semester)`, computes `weekly_pairs`, places into available slots, excludes holidays from `excluded_dates`. Reuses `_validate_lesson_data()`.
- `routes.py`: `POST /api/schedule/generate` + `GET /api/schedule/substitutions-suggest` (reuses availability join logic)
- `utils.py`: `LESSON_SELECT` / `LESSON_SELECT_WITH_DAY` have `LEFT JOIN teachers ot ON l.original_teacher_id = ot.id`, selecting `ot.name AS original_teacher_name`
- Frontend: `generateFromCurriculum()` in `schedule.js`, button in admin-panel, checkbox+fields in lesson-modal
- `main.js` exports `generateFromCurriculum` to `window`

## Token-saving rules
1. Do NOT read files already described here — use this skill instead.
2. Do NOT glob/grep for structure — use this table.
3. Return only diffs, not full files.
4. After editing Python → `pytest tests/ -v`. Lock step.
