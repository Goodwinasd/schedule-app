import logging
import random
from datetime import datetime, timedelta
from db import get_db
from utils import _validate_lesson_data, _validate_slot_3d

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


def _is_classroom_free(conn, classroom_id, date_str, period):
    row = conn.execute('''
        SELECT 1 FROM lessons l
        JOIN schedule_days sd ON l.day_id = sd.id
        WHERE l.classroom_id = ? AND sd.date = ? AND l.period = ?
          AND l.deleted_at IS NULL AND sd.deleted_at IS NULL
          AND l.classroom_id IS NOT NULL
        LIMIT 1
    ''', (classroom_id, date_str, period)).fetchone()
    return row is None


def _pick_classroom(conn, subject_id, teacher_id, date_str, period, last_classroom_id):
    """Cascade classroom selection: subject default -> same as last (min hopping) -> first free general."""
    # Preference 1: keep the same room as previous lesson in same day (room hopping minimisation)
    if last_classroom_id is not None:
        if _is_classroom_free(conn, last_classroom_id, date_str, period):
            return last_classroom_id
    # Preference 2: subject-level default teacher's classroom
    row = conn.execute(
        'SELECT default_teacher_id FROM subjects WHERE id = ? AND deleted_at IS NULL',
        (subject_id,)
    ).fetchone()
    if row and row['default_teacher_id']:
        t_row = conn.execute(
            "SELECT default_classroom_id FROM teachers WHERE id = ? AND deleted_at IS NULL",
            (row['default_teacher_id'],)
        ).fetchone()
        if t_row and t_row['default_classroom_id']:
            if _is_classroom_free(conn, t_row['default_classroom_id'], date_str, period):
                return t_row['default_classroom_id']
    # Preference 3: teacher's own default classroom
    t_row = conn.execute(
        "SELECT default_classroom_id FROM teachers WHERE id = ? AND deleted_at IS NULL",
        (teacher_id,)
    ).fetchone()
    if t_row and t_row['default_classroom_id']:
        if _is_classroom_free(conn, t_row['default_classroom_id'], date_str, period):
            return t_row['default_classroom_id']
    # Fallback: first free classroom
    classrooms = conn.execute(
        "SELECT id FROM classrooms_list WHERE deleted_at IS NULL ORDER BY CAST(name AS INTEGER), name"
    ).fetchall()
    for c in classrooms:
        if _is_classroom_free(conn, c['id'], date_str, period):
            return c['id']
    return None


def _is_teacher_on_absence(conn, teacher_id, date_str):
    row = conn.execute('''
        SELECT 1 FROM teacher_absences
        WHERE teacher_id = ? AND start_date <= ? AND end_date >= ?
        LIMIT 1
    ''', (teacher_id, date_str, date_str)).fetchone()
    return row is not None


def _resolve_teacher_substitution(conn, subject_id, primary_teacher_id, group_id, date_str, period):
    """If the planned teacher is unavailable (sick/absence), find a substitute.
    Returns (teacher_id, original_teacher_id, is_substitution) or (None, None, False)."""
    if not _is_teacher_on_absence(conn, primary_teacher_id, date_str):
        return primary_teacher_id, None, False
    # Find substitutes qualified for this subject
    subs = conn.execute('''
        SELECT ts.teacher_id FROM teacher_subjects ts
        JOIN teachers t ON ts.teacher_id = t.id AND t.deleted_at IS NULL
        WHERE ts.subject_id = ? AND ts.teacher_id != ?
    ''', (subject_id, primary_teacher_id)).fetchall()
    for s in subs:
        tid = s['teacher_id']
        if _is_teacher_on_absence(conn, tid, date_str):
            continue
        conflicts, blocking = _validate_slot_3d(conn, date_str, period, group_id, teacher_id=tid)
        if not blocking:
            return tid, primary_teacher_id, True
    return None, None, False


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
    from math import ceil

    # Determine course to clamp allowed periods
    group_row = conn.execute(
        "SELECT course FROM groups_list WHERE id = ? AND deleted_at IS NULL", (group_id,)
    ).fetchone()
    is_first_course = group_row is not None and group_row['course'] == 1
    allowed_periods = [1, 2, 3, 4] if is_first_course else list(range(1, 9))

    weeks_dates = [_build_week_dates(
        (datetime.strptime(monday_str, '%Y-%m-%d') + timedelta(weeks=w)).strftime('%Y-%m-%d')
    ) for w in range(week_count)]

    # Build a flat pool of (subject_id, teacher_id) pairs to place each week
    # across ALL curriculum items for this group, then distribute round-robin
    for wi, week_dates in enumerate(weeks_dates):
        # Collect all pairs needed for this week, deducting existing ones
        pool = []
        for item in curriculum:
            weeks = item['weeks_in_semester'] or 18
            if wi >= weeks:
                continue
            total_hours = item['total_hours']
            weekly = max(1, (total_hours + weeks * 2 - 1) // (weeks * 2))
            # Count existing lessons for this subject on this week
            existing = conn.execute('''
                SELECT COUNT(*) FROM lessons l
                JOIN schedule_days sd ON l.day_id = sd.id
                WHERE l.subject_id = ? AND l.group_id = ?
                  AND sd.date IN ({})
                  AND l.deleted_at IS NULL AND sd.deleted_at IS NULL
            '''.format(','.join('?' * len(week_dates))),
                [item['subject_id'], group_id] + week_dates
            ).fetchone()[0]
            remaining = weekly - existing
            if remaining > 0:
                for _ in range(remaining):
                    pool.append((item['subject_id'], item['teacher_id']))

        if not pool:
            continue

        # Seeded shuffle for controlled week-to-week variation
        monday_date = datetime.strptime(week_dates[0], '%Y-%m-%d')
        iso_year, iso_week, _ = monday_date.isocalendar()
        seed_str = f"{iso_year}_{iso_week}_{group_id}"
        rng = random.Random(seed_str)
        rng.shuffle(pool)

        # Even/odd week rotation: flip day order for even weeks
        is_even = (iso_week % 2 == 0)
        if is_even:
            # Reverse day priority — heavy subjects shift to later days
            day_order = [5, 4, 3, 2, 1, 0]
        else:
            day_order = [0, 1, 2, 3, 4, 5]

        # Round-robin: distribute pool across 6 days
        # Day assignment cycles through day_order, wrapping by modulo 6
        day_lessons = [[] for _ in range(6)]
        for i, (subj_id, teach_id) in enumerate(pool):
            day_lessons[day_order[i % 6]].append((subj_id, teach_id))

        # Controlled Shift Drift: choose start period per day (seeded, weighted)
        def pick_start_period(day_idx):
            d_seed = f"{iso_year}_{iso_week}_{group_id}_day{day_idx}"
            drng = random.Random(d_seed)
            roll = drng.random()
            if is_first_course:
                # 80% -> 1, 20% -> 2 (never evening)
                return 1 if roll < 0.8 else 2
            if roll < 0.7:
                return 1
            elif roll < 0.9:
                return 2
            else:
                return drng.choice([4, 5])

        for day_idx, lessons in enumerate(day_lessons):
            if not lessons:
                continue
            date_str = week_dates[day_idx]
            if _is_holiday(conn, date_str):
                continue
            day_id = _get_or_create_day(conn, date_str, group_name)
            # Number of lessons to place in this day (a contiguous block)
            block_count = len(lessons)
            start_period = pick_start_period(day_idx)
            last_classroom_id = None
            # Sequential block from start_period (Fallback: drop to earlier/window-safe slots on collision)
            period = start_period
            placed_in_day = 0
            while lessons and placed_in_day < block_count:
                if period > 8:
                    # Ran out of periods; fallback to earliest free slot 1..8
                    # (continuity sacrificed only at day end near max load)
                    if is_first_course:
                        period = 1
                        if any(p >= 5 for p in allowed_periods):
                            period = allowed_periods[0]
                    else:
                        period = 1
                subj_id, primary_tid = lessons[0]
                actual_tid, original_tid, is_sub = _resolve_teacher_substitution(
                    conn, subj_id, primary_tid, group_id, date_str, period
                )
                if actual_tid is None:
                    lessons.pop(0)  # no substitute — skip this pair
                    placed_in_day += 1
                    continue
                classroom_id = _pick_classroom(conn, subj_id, actual_tid, date_str, period, last_classroom_id)
                conflicts, blocking = _validate_slot_3d(
                    conn, date_str, period, group_id,
                    teacher_id=actual_tid, classroom_id=classroom_id
                )
                if not blocking:
                    conn.execute('''
                        INSERT INTO lessons (day_id, period, subject_id, teacher_id, classroom_id, group_id,
                                             is_substitution, original_teacher_id)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    ''', (day_id, period, subj_id, actual_tid, classroom_id, group_id,
                          int(is_sub), original_tid))
                    created += 1
                    last_classroom_id = classroom_id
                    lessons.pop(0)
                    placed_in_day += 1
                    period += 1
                else:
                    # Fallback: try earliest free slot of the day (window-safe rollback)
                    fallback_period = 1
                    if is_first_course:
                        fallback_period = allowed_periods[0]
                    if fallback_period != period:
                        period = fallback_period
                    else:
                        period += 1  # advance to avoid infinite loop

    return {'created': created, 'errors': errors}
