"""Реальные правила техникума: смены, типы аудиторий, максимум 7 пар.

Основано на выгрузках расписания за 31.08–06.09.2026:
- 1-й курс начинает с 1-й пары (8:30), 4-й курс — со 2-й смены (13:30, пары 3–7);
- спец. аудитории: «Динамо»/«Атмосфера» (спортзал), компьютерные классы, зал суда;
- последняя пара — 7-я (18:25–19:50), 8-ю не ставим.
"""

from datetime import datetime, timedelta

import generator


def _monday(days_ahead=21):
    today = datetime.today().date() + timedelta(days=days_ahead)
    return (today - timedelta(days=today.weekday())).isoformat()


def _setup(conn, name='Тест-группа', course=2, shift=None, subjects=(), rooms=(), is_distance=False):
    """subjects: [(название, required_room_type|None, пар в неделю)], rooms: [(название, room_type|None)]."""
    gid = conn.execute(
        "INSERT INTO groups_list (name, course, shift, is_distance) VALUES (?, ?, ?, ?)",
        (name, course, shift, 1 if is_distance else 0)
    ).lastrowid
    for i, (subject_name, required_type, weekly) in enumerate(subjects):
        teacher_id = conn.execute(
            "INSERT INTO teachers (name) VALUES (?)", (f'Преподаватель {i + 1}',)).lastrowid
        subject_id = conn.execute(
            "INSERT INTO subjects (name, required_room_type) VALUES (?, ?)",
            (subject_name, required_type)).lastrowid
        conn.execute(
            "INSERT INTO curriculum (group_id, subject_id, teacher_id, semester, total_hours, weeks_in_semester) "
            "VALUES (?, ?, ?, 1, ?, 18)",
            (gid, subject_id, teacher_id, 36 * weekly - 35))
    for room_name, room_type in rooms:
        conn.execute(
            "INSERT INTO classrooms_list (name, room_type) VALUES (?, ?)", (room_name, room_type))
    conn.commit()
    return gid


def _lessons(conn, gid, monday, weeks=1):
    """[(date, period, subject_id, classroom_id)] за указанные недели."""
    dates = [
        (datetime.strptime(monday, '%Y-%m-%d') + timedelta(weeks=w, days=d)).strftime('%Y-%m-%d')
        for w in range(weeks) for d in range(6)
    ]
    rows = []
    for date in dates:
        rows.extend(conn.execute(
            "SELECT sd.date, l.period, l.subject_id, l.classroom_id FROM lessons l "
            "JOIN schedule_days sd ON l.day_id = sd.id "
            "WHERE sd.date = ? AND l.group_id = ? AND l.deleted_at IS NULL AND sd.deleted_at IS NULL",
            (date, gid)).fetchall())
    return rows


def test_columns_exist_after_migration(app, db):
    conn = db.get_db()
    assert 'shift' in {r[1] for r in conn.execute("PRAGMA table_info(groups_list)")}
    assert 'room_type' in {r[1] for r in conn.execute("PRAGMA table_info(classrooms_list)")}
    assert 'required_room_type' in {r[1] for r in conn.execute("PRAGMA table_info(subjects)")}


def test_second_shift_never_starts_at_first_second_period(app, db):
    conn = db.get_db()
    gid = _setup(conn, course=2, shift=2,
                 subjects=[('Математика', None, 4)],
                 rooms=[('101', None)])
    monday = _monday()
    res = generator.generate_schedule(conn, gid, 'Тест-группа', 1, monday, 1, optimize=False)
    conn.commit()

    periods = [row['period'] for row in _lessons(conn, gid, monday)]
    assert res['created'] == 4, res
    assert periods, 'нет пар'
    assert min(periods) >= generator.SHIFT2_EXPECTED_START, f'2-я смена раньше 4-й пары: {periods}'
    assert not ({1, 2} & set(periods)), f'2-я смена попала на 1–2 пары: {periods}'


def test_second_shift_periods_within_three_eight(app, db):
    conn = db.get_db()
    gid = _setup(conn, course=2, shift=2,
                 subjects=[(f'Предмет {i + 1}', None, 3) for i in range(6)],
                 rooms=[('101', None)])
    monday = _monday()
    generator.generate_schedule(conn, gid, 'Тест-группа', 1, monday, 1, optimize=False)
    conn.commit()

    rows = _lessons(conn, gid, monday)
    periods = [row['period'] for row in rows]
    assert rows and len(rows) == 18, len(rows)
    assert max(periods) <= generator.GENERATOR_MAX_PERIOD == 8, f'вышли за 8-ю пару: {sorted(set(periods))}'
    assert all(3 <= p <= 8 for p in periods), f'периоды вне 3–8: {sorted(set(periods))}'


def test_gym_subject_goes_only_to_gym_room(app, db):
    conn = db.get_db()
    gid = _setup(conn, course=2,
                 subjects=[('Физическая культура', 'gym', 2)],
                 rooms=[('101', None), ('Динамо', 'gym')])
    gym_id = conn.execute("SELECT id FROM classrooms_list WHERE name = 'Динамо'").fetchone()['id']
    monday = _monday()
    generator.generate_schedule(conn, gid, 'Тест-группа', 1, monday, 1, optimize=False)
    conn.commit()

    rows = _lessons(conn, gid, monday)
    assert rows, 'нет пар'
    assert all(row['classroom_id'] == gym_id for row in rows), [
        (row['period'], row['classroom_id']) for row in rows]


def test_required_room_without_suitable_room_not_placed_in_ordinary(app, db):
    conn = db.get_db()
    gid = _setup(conn, course=2,
                 subjects=[('Физическая культура', 'gym', 2)],
                 rooms=[('101', None), ('102', None)])
    monday = _monday()
    res = generator.generate_schedule(conn, gid, 'Тест-группа', 1, monday, 1, optimize=False)
    conn.commit()

    rows = _lessons(conn, gid, monday)
    assert res['created'] == 0, res
    assert not rows, 'физкультуру поставили в обычную аудиторию'
    assert res['errors'], 'ожидали понятную ошибку о нехватке аудитории'


def test_cost_uses_shift_expected_start(app):
    def cost(*periods):
        return generator._calculate_cost(
            [{'date': '2026-09-07', 'period': p, 'group_id': 2, 'teacher_id': p} for p in periods],
            expected_start=generator.SHIFT2_EXPECTED_START)

    assert cost(4, 5, 6) == 0
    assert cost(3, 4) == generator.W_GROUP_START          # раньше ожидаемого на пару
    assert cost(4) == 0


def test_first_shift_still_starts_at_first_period(app, db):
    """1-я смена стартует с 1-й пары; в пятницу допустим старт со 2-й (правило недели 3)."""
    conn = db.get_db()
    gid = _setup(conn, course=1, shift=1,
                 subjects=[('Математика', None, 3)],
                 rooms=[('101', None)])
    monday = _monday()
    generator.generate_schedule(conn, gid, 'Тест-группа', 1, monday, 1, optimize=False)
    conn.commit()

    rows = _lessons(conn, gid, monday)
    assert rows
    for row in rows:
        weekday = datetime.strptime(row['date'], '%Y-%m-%d').weekday()
        if weekday == 4:                       # пятница: 1-я или 2-я пара
            assert row['period'] in (1, 2), row['period']
        else:
            assert row['period'] == 1, f'{row["date"]}: старт с {row["period"]}-й пары'


def test_teacher_eighth_pair_is_expensive(app):
    """7 пар у преподавателя — норма, 8-я допустима, но дорого (как у Балашовой)."""
    def cost(count):
        return generator._calculate_cost([
            {'date': '2026-09-07', 'period': p, 'group_id': 1, 'teacher_id': 1}
            for p in range(1, count + 1)
        ])

    week = cost(7)
    eight = cost(8)
    assert week == generator.W_OVERLOAD * 3          # (7 - 4) пары перегруза
    assert eight == generator.W_OVERLOAD * 4 + generator.W_TEACHER_EIGHTH_PAIR
    assert eight - week == generator.W_OVERLOAD + generator.W_TEACHER_EIGHTH_PAIR


def test_special_event_not_touched_by_generator(app, db):
    """Разовое мероприятие остаётся на месте: генератор его не двигает и не удаляет."""
    conn = db.get_db()
    gid = _setup(conn, course=2, shift=1,
                 subjects=[('Математика', None, 3)],
                 rooms=[('101', None)])
    monday = _monday()
    day_id = conn.execute(
        "INSERT INTO schedule_days (day_name, date, group_name) VALUES ('Понедельник', ?, 'Тест-группа')",
        (monday,)).lastrowid
    special_id = conn.execute(
        "INSERT INTO lessons (day_id, period, subject_id, teacher_id, classroom_id, group_id, is_special_event) "
        "VALUES (?, 7, NULL, NULL, NULL, ?, 1)", (day_id, gid)).lastrowid
    conn.commit()

    generator.generate_schedule(conn, gid, 'Тест-группа', 1, monday, 1, optimize=True)
    conn.commit()

    row = conn.execute(
        "SELECT period, is_special_event, deleted_at FROM lessons WHERE id = ?", (special_id,)).fetchone()
    assert row is not None, 'мероприятие удалено генератором'
    assert row['period'] == 7, 'мероприятие переставили'
    assert row['is_special_event'] == 1
    assert row['deleted_at'] is None


def test_distance_groups_respect_their_shift(app, db):
    """Заочники тоже делятся на смены: 1-я — пары 1–4, 2-я — пары 3–8."""
    conn = db.get_db()
    monday = _monday()

    first = _setup(conn, name='01-11/26', course=1, shift=1, is_distance=True,
                   subjects=[('Математика-01', None, 3)], rooms=[('101', None)])
    generator.generate_schedule(conn, first, '01-11/26', 1, monday, 1, optimize=False)
    conn.commit()
    row_db = conn.execute("SELECT shift, is_distance FROM groups_list WHERE id = ?", (first,)).fetchone()
    assert row_db['shift'] == 1 and row_db['is_distance'] == 1, '01-11/26: смена/заочка не сохранены'
    first_rows = _lessons(conn, first, monday)
    assert first_rows, 'заочка 1-й смены не сгенерирована'
    for row in first_rows:
        weekday = datetime.strptime(row['date'], '%Y-%m-%d').weekday()
        expected = (1, 2) if weekday == 4 else (1,)
        assert row['period'] in expected, f'заочка 1-й смены, {row["date"]}: {row["period"]}'

    second = _setup(conn, name='01-11/25', course=2, shift=2, is_distance=True,
                    subjects=[('Математика-02', None, 3)], rooms=[('102', None)])
    generator.generate_schedule(conn, second, '01-11/25', 1, monday, 1, optimize=False)
    conn.commit()
    second_periods = [row['period'] for row in _lessons(conn, second, monday)]
    assert second_periods and min(second_periods) >= 4, f'заочка 2-й смены: {second_periods}'


def test_cost_friday_allows_first_or_second_start(app):
    friday = '2026-09-18'
    def cost(period):
        return generator._calculate_cost(
            [{'date': friday, 'period': period, 'group_id': 1, 'teacher_id': 1}],
            expected_start=1, friday_start=2)
    assert cost(1) == 0, 'в пятницу 1-я пара — допустимый старт'
    assert cost(2) == 0, 'в пятницу 2-я пара — тоже без штрафа'
    assert cost(3) == generator.W_GROUP_START


def test_first_course_friday_can_start_second_period(app, db):
    """1-й курс в пятницу может начинать со 2-й пары; в остальные дни — с 1-й."""
    conn = db.get_db()
    gid = _setup(conn, course=1, shift=1,
                 subjects=[(f'Предмет {i + 1}', None, 3) for i in range(6)],
                 rooms=[('101', None)])
    monday = _monday()
    generator.generate_schedule(conn, gid, 'Тест-группа', 1, monday, 1, optimize=True)
    conn.commit()

    rows = _lessons(conn, gid, monday)
    by_date = {}
    for row in rows:
        by_date.setdefault(row['date'], []).append(row['period'])
    assert len(by_date) == 6, by_date
    for date, periods in by_date.items():
        weekday = datetime.strptime(date, '%Y-%m-%d').weekday()
        first = min(periods)
        if weekday == 4:                        # пятница
            assert first in (1, 2), f'пятница началась с {first}-й пары'
        else:
            assert first == 1, f'{date}: старт с {first}-й пары'
