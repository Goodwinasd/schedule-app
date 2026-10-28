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


def _setup(conn, name='Тест-группа', course=2, shift=None, subjects=(), rooms=()):
    """subjects: [(название, required_room_type|None, пар в неделю)], rooms: [(название, room_type|None)]."""
    gid = conn.execute(
        "INSERT INTO groups_list (name, course, shift) VALUES (?, ?, ?)", (name, course, shift)
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


def test_second_shift_uses_periods_up_to_seven_not_eight(app, db):
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
    assert max(periods) == generator.GENERATOR_MAX_PERIOD, f'ожидали 7-ю пару: {sorted(set(periods))}'
    assert all(3 <= p <= 7 for p in periods), f'периоды вне 3–7: {sorted(set(periods))}'
    assert 8 not in periods, '8-я пара не должна ставиться'


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
    conn = db.get_db()
    gid = _setup(conn, course=1, shift=1,
                 subjects=[('Математика', None, 3)],
                 rooms=[('101', None)])
    monday = _monday()
    generator.generate_schedule(conn, gid, 'Тест-группа', 1, monday, 1, optimize=False)
    conn.commit()

    periods = [row['period'] for row in _lessons(conn, gid, monday)]
    assert periods and set(periods) == {1}, f'1-я смена должна начинать с 1-й пары: {periods}'
