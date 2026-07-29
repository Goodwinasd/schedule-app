# Graph Report - .  (2026-07-26)

## Corpus Check
- Corpus is ~24,307 words - fits in a single context window. You may not need a graph.

## Summary
- 487 nodes · 1003 edges · 50 communities (27 shown, 23 thin omitted)
- Extraction: 100% EXTRACTED · 0% INFERRED · 0% AMBIGUOUS · INFERRED: 1 edges (avg confidence: 0.85)
- Token cost: 0 input · 0 output

## Community Hubs (Navigation)
- Frontend UI Module
- Utility Config
- Schedule Tests
- Database Layer
- API Routes
- Validation Tests
- Auth Tests
- Availability Module
- Export Integration Tests
- DB Helpers
- Lesson CRUD Tests
- Test Fixtures
- Subjects CRUD Tests
- Days CRUD Tests
- Cache Layer
- Auth Frontend
- Classrooms CRUD Tests
- Groups CRUD Tests
- Teachers CRUD Tests
- CI and Docker
- Conflict Tests
- Settings Tests
- App Bootstrap
- test_schedule_flow.py
- opencode.json
- full_test.py
- graphify.js
- Docker Compose
- advance_courses()
- classrooms_with_schedule()
- create_lesson()
- delete_day()
- delete_group()
- get_groups()
- get_trash()
- Восстановить мягко удалённый день     --
- Восстановить мягко удалённый урок     --
- SPA Frontend

## God Nodes (most connected - your core abstractions)
1. `api()` - 48 edges
2. `get_db()` - 44 edges
3. `toISODate()` - 28 edges
4. `loadScheduleTable()` - 25 edges
5. `escapeHtml()` - 21 edges
6. `confirmModal()` - 16 edges
7. `renderRefList()` - 16 edges
8. `getMonday()` - 16 edges
9. `addDays()` - 16 edges
10. `_validate_lesson_data()` - 14 edges

## Surprising Connections (you probably didn't know these)
- `_cleanup_old_deleted()` --calls--> `get_db()`  [EXTRACTED]
  schedule-app/app.py → schedule-app/db.py
- `CI Pipeline` --references--> `Test Dependencies`  [EXTRACTED]
  .github/workflows/ci.yml → schedule-app/requirements-dev.txt
- `CI Pipeline` --references--> `Production Dependencies`  [EXTRACTED]
  .github/workflows/ci.yml → schedule-app/requirements.txt
- `_get_retention_days()` --calls--> `get_db()`  [EXTRACTED]
  schedule-app/app.py → schedule-app/db.py
- `advance_courses()` --calls--> `get_db()`  [EXTRACTED]
  schedule-app/routes.py → schedule-app/db.py

## Import Cycles
- None detected.

## Communities (50 total, 23 thin omitted)

### Community 0 - "Frontend UI Module"
Cohesion: 0.10
Nodes (70): api(), init(), confirmModal(), _confirmState, addGroup(), addRefItem(), addSubject(), advanceCourses() (+62 more)

### Community 1 - "Utility Config"
Cohesion: 0.13
Nodes (42): DAY_ORDER, MONTHS, MONTHS_SHORT, WEEKDAYS, openModal(), addWeek(), carouselSkip(), deleteWeek() (+34 more)

### Community 2 - "Schedule Tests"
Cohesion: 0.05
Nodes (9): TestAvailability, TestCheckDate, TestClassroomsWithSchedule, TestExport, TestScheduleTable, TestTeacherSchedule, TestTeachersWithSchedule, TestTrash (+1 more)

### Community 3 - "Database Layer"
Cohesion: 0.06
Nodes (31): get_db(), create_day(), create_days_batch(), create_group(), db_health(), delete_lesson(), generic_crud(), get_days() (+23 more)

### Community 4 - "API Routes"
Cohesion: 0.09
Nodes (22): bell_schedule(), check_auth(), _clean_login_attempts(), csrf_token(), _export_excel(), _export_pdf(), export_schedule(), _export_word() (+14 more)

### Community 5 - "Validation Tests"
Cohesion: 0.15
Nodes (5): TestLessonSelectConstants, TestSafeFilename, TestValidateLessonData, _safe_filename(), _validate_lesson_data()

### Community 6 - "Auth Tests"
Cohesion: 0.11
Nodes (5): TestCheckAuth, TestCsrfProtection, TestCsrfToken, TestLogin, TestLogout

### Community 7 - "Availability Module"
Cohesion: 0.14
Nodes (17): availability(), _build_schedule_periods(), build_week_dates(), classroom_schedule_table(), delete_week(), _fetch_entity_raw(), _fetch_group_raw(), _get_export_data() (+9 more)

### Community 8 - "Export Integration Tests"
Cohesion: 0.17
Nodes (6): Проверка корзины и очистки., Экспорт с реальными данными + проверка содержимого., Проверка /api/availability с уроками., TestAvailabilityIntegration, TestExportIntegration, TestTrashIntegration

### Community 9 - "DB Helpers"
Cohesion: 0.22
Nodes (7): is_date_excluded(), Connection subclass that logs slow queries., Применить все неприменённые миграции через Alembic.     Используется в productio, run_alembic_upgrade(), _TimedConnection, check_date(), Проверить, является ли дата исключённой (праздник/выходной)     ---     paramete

### Community 11 - "Test Fixtures"
Cohesion: 0.27
Nodes (4): clean_db_before_test(), _clean_tables(), db(), _seed_refs()

### Community 15 - "Auth Frontend"
Cohesion: 0.39
Nodes (7): checkAuth(), login(), logout(), goHome(), loadHomePage(), updateUI(), closeModals()

### Community 19 - "CI and Docker"
Cohesion: 0.29
Nodes (7): CI Pipeline, GitHub Actions, Environment Variables, Test Dependencies, Alembic, APScheduler, Production Dependencies

### Community 22 - "App Bootstrap"
Cohesion: 0.53
Nodes (5): _cleanup_old_backups(), _cleanup_old_deleted(), _get_retention_days(), _maybe_create_backup(), _run_backup_tasks()

### Community 24 - "opencode.json"
Cohesion: 0.50
Nodes (3): plugin, $schema, .opencode/plugins/graphify.js

## Knowledge Gaps
- **10 isolated node(s):** `$schema`, `.opencode/plugins/graphify.js`, `GitHub Actions`, `Docker Setup`, `Environment Variables` (+5 more)
  These have ≤1 connection - possible missing edges or undocumented components.
- **23 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `get_db()` connect `Database Layer` to `API Routes`, `advance_courses()`, `classrooms_with_schedule()`, `Availability Module`, `create_lesson()`, `DB Helpers`, `delete_day()`, `delete_group()`, `get_groups()`, `get_trash()`, `Восстановить мягко удалённый день     --`, `Восстановить мягко удалённый урок     --`, `App Bootstrap`?**
  _High betweenness centrality (0.019) - this node is a cross-community bridge._
- **Why does `_validate_lesson_data()` connect `Validation Tests` to `Database Layer`, `API Routes`, `create_lesson()`, `Восстановить мягко удалённый день     --`, `Восстановить мягко удалённый урок     --`?**
  _High betweenness centrality (0.014) - this node is a cross-community bridge._
- **Why does `_safe_filename()` connect `Validation Tests` to `API Routes`?**
  _High betweenness centrality (0.008) - this node is a cross-community bridge._
- **What connects `$schema`, `.opencode/plugins/graphify.js`, `GitHub Actions` to the rest of the system?**
  _10 weakly-connected nodes found - possible documentation gaps or missing edges._
- **Should `Frontend UI Module` be split into smaller, more focused modules?**
  _Cohesion score 0.09525316455696202 - nodes in this community are weakly interconnected._
- **Should `Utility Config` be split into smaller, more focused modules?**
  _Cohesion score 0.1322849213691027 - nodes in this community are weakly interconnected._
- **Should `Schedule Tests` be split into smaller, more focused modules?**
  _Cohesion score 0.046511627906976744 - nodes in this community are weakly interconnected._