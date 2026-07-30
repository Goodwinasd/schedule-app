import logging
from datetime import datetime, timedelta
from db import get_db
from utils import _validate_lesson_data

logger = logging.getLogger(__name__)

DAY_ORDER = ['Понедельник', 'Вторник', 'Среда', 'Четверг', 'Пятница', 'Суббота']
BELL_SCHEDULE = list(range(1, 9))


def _build_week_dates(monday_str):
    monday = datetime.strptime(monday_str, '%Y-%m-%d').date()
    return [(monday + timedelta(days=i)).isoformat() for i in range(6)]


def _get_or_create_day(conn, date_str, group_name):
    row = conn.execute(
        "SELECT id FROM schedule_days WHERE date = ? AND group_name = ? AND deleted_at IS NULL",
        (date_str, group_name)
    ).fetchone()
    if row:
        return row['id']
    day_name = DAY_ORDER[datetime.strptime(date_str, '%Y-%m-%d').weekday()]
    cur = conn.execute(
        "INSERT INTO schedule_days (day_name, date, group_name) VALUES (?, ?, ?)",
        (day_name, date_str, group_name)
    )
    return cur.lastrowid


def _is_holiday(conn, date_str):
    row = conn.execute(
        "SELECT 1 FROM excluded_dates WHERE start_date <= ? AND end_date >= ? LIMIT 1",
        (date_str, date_str)
    ).fetchone()
    return row is not None


def generate_schedule(conn, group_id, group_name, semester, monday_str, week_count):
    curriculum = conn.execute('''
        SELECT c.*, s.name AS subject_name, t.name AS teacher_name
        FROM curriculum c
        LEFT JOIN subjects s ON c.subject_id = s.id
        LEFT JOIN teachers t ON c.teacher_id = t.id
        WHERE c.group_id = ? AND c.semester = ?
    ''', (group_id, semester)).fetchall()

    if not curriculum:
        return {'created': 0, 'errors': ['No curriculum found for this group/semester']}

    created = 0
    errors = []
    weeks_dates = [_build_week_dates(
        (datetime.strptime(monday_str, '%Y-%m-%d') + timedelta(weeks=w)).strftime('%Y-%m-%d')
    ) for w in range(week_count)]

    for item in curriculum:
        total_hours = item['total_hours']
        weeks = item['weeks_in_semester'] or 18
        weekly_pairs = max(1, (total_hours + weeks * 2 - 1) // (weeks * 2))

        teacher_id = item['teacher_id']
        subject_id = item['subject_id']
        classroom_id = None

        for wi, week_dates in enumerate(weeks_dates):
            if wi >= weeks:
                break
            pairs_placed = 0
            for date_str in week_dates:
                if pairs_placed >= weekly_pairs:
                    break
                if _is_holiday(conn, date_str):
                    continue
                day_id = _get_or_create_day(conn, date_str, group_name)
                for period in BELL_SCHEDULE:
                    if pairs_placed >= weekly_pairs:
                        break
                    warnings, blocking = _validate_lesson_data(
                        conn, day_id, period,
                        teacher_id=teacher_id,
                        classroom_id=classroom_id,
                        subject_id=subject_id,
                        group_id=group_id,
                        subgroup=None,
                        skip_day_check=True
                    )
                    if not blocking:
                        conn.execute('''
                            INSERT INTO lessons (day_id, period, subject_id, teacher_id, classroom_id, group_id)
                            VALUES (?, ?, ?, ?, ?, ?)
                        ''', (day_id, period, subject_id, teacher_id, classroom_id, group_id))
                        created += 1
                        pairs_placed += 1

    return {'created': created, 'errors': errors}
