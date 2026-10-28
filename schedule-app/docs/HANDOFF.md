# Handoff — schedule-app (28.10.2026)

## Состояние
- Ветка: `feat/real-data-analysis-week3` (запушена в origin). Верхушка ветки — коммит
  недели 6 `feat(lessons): consultations, coursework teachers, custom room name`;
  перед ним `046c36e` (HANDOFF с заметкой про вложенный `.git`).
- Git-репозиторий — **в корне воркспейса** (`Default Project`), не в `schedule-app/`.
  Вложенный `.git` в `schedule-app/` устарел (`main` @ `117e0d1`, грязное дерево):
  **не трогать его** — никаких `git add/commit/checkout` из подпапки, иначе форк истории.
  Все коммиты — только через корневой репозиторий.
- Миграции: head `f7a8b9c0d1e2` (17 ревизий); `upgrade head` на пустой БД прогнан — ок.
- Тесты: 367 backend (`tests/`) + 7 e2e (`tests/e2e/`) — зелёные.
  Оговорка: полный прогон backend+e2e в одном процессе pytest изредка падает на
  `TestBackupRestore::test_restore_finishes_without_server_error` (EINVAL на temp-пути
  с 8.3-именем) — воспроизводится и на HEAD, к изменениям недели 6 отношения не имеет;
  backend и e2e отдельно зелёные.
- Сервер: `scripts/start-site.bat` / `stop-site.bat`, http://127.0.0.1:5000.
- Реальные данные недель 1–6 разобраны: смены, спец. аудитории, ликвид. сессия,
  custom-time мероприятия, курсовые, мягкие штрафы старта, 8-я пара (штраф 200).
- Не закоммичено: папка `docs/ui/buttons/` — правки пользователя, НЕ трогать.
  `docs/ui/event-modal-week6.png` — скриншот модалки, не коммитится (`docs/ui/*.png`).

## Неделя 6 — реализовано
1. Миграция `f7a8b9c0d1e2` (down_revision `e6a7b8c9d0e1`): `lessons.additional_teachers TEXT`,
   `lessons.custom_room_name VARCHAR` (`LESSON_SELECT` уже через `l.*` — правок не требовал).
2. API POST/PUT `/api/lessons`: новые поля сохраняются, частичный PUT их не затирает;
   при `event_type='coursework'` без доп. преподавателей — warning (не блокер);
   `consultation`/`coursework` автоматически получают `is_special_event=1`.
3. UI модалки: тип события «Консультация»; поле «Дополнительные преподаватели» при «Курсовая»;
   поле «Место» при «Вне сетки»; карточка пары показывает место и доп. преподавателей.
4. Экспорт Excel: преподаватель + дополнительные, `custom_room_name` вместо аудитории,
   время вне сетки сохраняется.
5. Тесты: 374 (367 backend + 7 e2e); новые — `tests/test_week6.py` (3 шт.:
   coursework teachers, consultation special event, week6 constraints).
6. Скриншот модалки: `docs/ui/event-modal-week6.png`.
7. Обновлены `AGENTS.md` / `README.md` (число тестов, head миграций, правила недели 6).

## Дальше
Неделя 7: разбор реальных данных (12.10–18.10), при необходимости — миграции и правила
генератора, тесты по той же схеме (API-раундтрип + экспорт), UI-скриншоты.

## Правила
`AGENTS.md` в `schedule-app/`: не трогать `.env`, `data/`, `backups/`; коммит после «ок»;
токен-экономия; миграции — только с прогоном на пустой БД.
