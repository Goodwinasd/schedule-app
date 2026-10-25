"""Раскладка пар по дням — по метрикам реальных расписаний 1 курса.

Эталон (9 групп, неделя 26.10–01.11.2026): будни в среднем 3.2 пары (3–4),
суббота легче — 2 пары, занятия начинаются с 1-й пары, разрывов внутри дня нет.
"""

from datetime import datetime, timedelta

import generator


def _monday(days_ahead=21):
    today = datetime.today().date() + timedelta(days=days_ahead)
    return (today - timedelta(days=today.weekday())).isoformat()


def _setup_group(conn, name='Тест-группа', subjects=6, hours=90, course=1):
    gid = conn.execute("INSERT INTO groups_list (name, course) VALUES (?, ?)", (name, course)).lastrowid
    for i in range(subjects):
        teacher = conn.execute("INSERT INTO teachers (name) VALUES (?)", (f'Преподаватель {i + 1}',)).lastrowid
        subject = conn.execute("INSERT INTO subjects (name) VALUES (?)", (f'Предмет {i + 1}',)).lastrowid
        conn.execute("INSERT INTO classrooms_list (name) VALUES (?)", (f'Каб-{i + 1}',))
        conn.execute(
            "INSERT INTO curriculum (group_id, subject_id, teacher_id, semester, total_hours, weeks_in_semester) "
            "VALUES (?, ?, ?, 1, ?, 18)", (gid, subject, teacher, hours))
    conn.commit()
    return gid


def _periods_by_day(conn, gid, monday):
    result = []
    for d in range(6):
        date = (datetime.strptime(monday, '%Y-%m-%d') + timedelta(days=d)).strftime('%Y-%m-%d')
        result.append([r[0] for r in conn.execute(
            "SELECT l.period FROM lessons l JOIN schedule_days sd ON l.day_id = sd.id "
            "WHERE sd.date = ? AND l.group_id = ? AND l.deleted_at IS NULL AND sd.deleted_at IS NULL "
            "ORDER BY l.period", (date, gid))])
    return result


def test_weekdays_three_four_saturday_two(app, db):
    conn = db.get_db()
    gid = _setup_group(conn)
    monday = _monday()
    res = generator.generate_schedule(conn, gid, 'Тест-группа', 1, monday, 1, optimize=False)
    conn.commit()

    days = _periods_by_day(conn, gid, monday)
    counts = [len(p) for p in days]
    assert res['created'] == 18, res
    assert 3 <= min(counts[:5]), f'будний день с недобором: {counts}'
    assert max(counts[:5]) <= 4, counts
    assert counts[5] == 2, f'суббота должна быть легче: {counts}'

    for periods in days:
        assert periods, 'пустой учебный день'
        assert periods[0] == 1, f'день должен начинаться с 1-й пары: {periods}'
        assert periods == list(range(1, len(periods) + 1)), f'дыры внутри дня: {periods}'


def test_small_plan_has_no_saturday(app, db):
    conn = db.get_db()
    gid = _setup_group(conn, subjects=4, hours=54)   # 2 пары/предмет → 8 пар в неделю
    monday = _monday()
    res = generator.generate_schedule(conn, gid, 'Тест-группа', 1, monday, 1, optimize=False)
    conn.commit()

    counts = [len(p) for p in _periods_by_day(conn, gid, monday)]
    assert res['created'] == 8, res
    assert counts[5] == 0, f'при малом плане суббота не нужна: {counts}'
    assert sum(counts[:5]) == 8, counts


def test_topup_moves_pairs_instead_of_dropping(app, db):
    """Занятый понедельник не должен «съедать» пары: они переезжают на другие дни."""
    conn = db.get_db()
    gid = _setup_group(conn)
    monday = _monday()

    day_id = conn.execute(
        "INSERT INTO schedule_days (day_name, date, group_name) VALUES ('Понедельник', ?, 'Тест-группа')",
        (monday,)).lastrowid
    other_teacher = conn.execute("INSERT INTO teachers (name) VALUES ('Занятый преподаватель')").lastrowid
    other_subject = conn.execute("INSERT INTO subjects (name) VALUES ('Занятый предмет')").lastrowid
    other_room = conn.execute("INSERT INTO classrooms_list (name) VALUES ('Занятый каб')").lastrowid
    for period in (1, 2, 3, 4):
        conn.execute(
            "INSERT INTO lessons (day_id, period, subject_id, teacher_id, classroom_id, group_id) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (day_id, period, other_subject, other_teacher, other_room, gid))
    conn.commit()

    res = generator.generate_schedule(conn, gid, 'Тест-группа', 1, monday, 1, optimize=False)
    conn.commit()

    counts = [len(p) for p in _periods_by_day(conn, gid, monday)]
    assert res['created'] == 18, res
    assert not res['errors'], res['errors']
    # понедельник занят чужими парами, остальные дни добрали нагрузку
    assert counts[0] == 4, counts
    assert sum(counts[1:]) == 18, counts
