# Handoff — schedule-app (28.10.2026)

## Состояние
- Ветка: `feat/real-data-analysis-week3`, последний коммит `34549f0` (запушен в origin).
- Git-репозиторий — **в корне воркспейса** (`Default Project`), не в `schedule-app/`.
  Вложенный `.git` в `schedule-app/` устарел (`main` @ `117e0d1`, грязное дерево):
  **не трогать его** — никаких `git add/commit/checkout` из подпапки, иначе форк истории.
  Все коммиты — только через корневой репозиторий.
- Миграции: head `e6a7b8c9d0e1` (16 ревизий), боевая БД мигрирована, бэкапы в `backups/`.
- Тесты: 364 backend (`tests/`) + 7 e2e (`tests/e2e/`) — зелёные.
- Сервер: `scripts/start-site.bat` / `stop-site.bat`, http://127.0.0.1:5000.
- Реальные данные недель 1–5 разобраны: смены, спец. аудитории, ликвид. сессия,
  custom-time мероприятия, курсовые, мягкие штрафы старта, 8-я пара (штраф 200).
- Не закоммичено: папка `docs/ui/buttons/` — правки пользователя, НЕ трогать.

## Следующий шаг: неделя 6 (05.10–11.10)
1. Миграция `f7a8b9c0d1e2` (down_revision `e6a7b8c9d0e1`):
   - `lessons.additional_teachers TEXT NULL` (ФИО через запятую/JSON);
   - `lessons.custom_room_name VARCHAR NULL` (место для выездных мероприятий).
   - Проверить `LESSON_SELECT` в `utils.py` (через `l.*` или явно).
2. API POST/PUT `/api/lessons`: сохранять новые поля; при `event_type='coursework'`
   и пустых `additional_teachers` — warning в ответе (не блокер).
3. UI (модалка пары):
   - «Тип события» += «Консультация» (`consultation`);
   - при «Курсовая» — поле «Дополнительные преподаватели»;
   - при «Вне сетки» — поле «Место» → `custom_room_name`.
   - `collectLessonData`/`editLesson` — новые поля.
4. Генератор: события с `is_special_event=1` или `custom_start_time IS NOT NULL`
   уже не трогаются — консультации/курсовые защищены через UI-флаг.
5. Экспорт Excel: преподаватели = основной + дополнительные; при `custom_room_name`
   выводить его вместо аудитории; время вне сетки уже выводится.
6. Тесты: `test_coursework_has_multiple_teachers`, `test_consultation_is_special_event`,
   `test_week6_constraints` (старты 1 курса Пн–Сб по данным недели 6, 2-я смена 3–7,
   заочка 3–5).
7. Скриншот модалки → `docs/ui/event-modal-week6.png`; обновить AGENTS/README
   (тесты, head миграций); коммит `feat(lessons): consultations, coursework teachers, custom room name`.

## Правила
`AGENTS.md` в `schedule-app/`: не трогать `.env`, `data/`, `backups/`; коммит после «ок»;
токен-экономия; миграции — только с прогоном на пустой БД.
