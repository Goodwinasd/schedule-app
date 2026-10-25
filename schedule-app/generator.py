import logging
import random
from datetime import datetime, timedelta
from utils import _validate_slot_3d

logger = logging.getLogger(__name__)

DAY_ORDER = ['Понедельник', 'Вторник', 'Среда', 'Четверг', 'Пятница', 'Суббота']
BELL_SCHEDULE = list(range(1, 9))

MAX_PAIRS_WEEKDAY = 4
MAX_PAIRS_SATURDAY = 3


def _max_pairs_per_day(day_idx):
    """Дневной лимит нагрузки группы: будни — до 4 пар, суббота — облегчённый режим до 3 пар."""
    return MAX_PAIRS_SATURDAY if day_idx == 5 else MAX_PAIRS_WEEKDAY


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
        "INSERT INTO schedule_days (day_name, date, group_name, is_published) VALUES (?, ?, ?, 0)",
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


def _mirror_target_groups(conn, group_name):
    """Связанные группы-дублёры для составного потока (маркер '+', например '02-0923+11/24')."""
    if '+' not in group_name:
        return []
    targets = []
    for part in group_name.split('+'):
        part = part.strip()
        if not part or part == group_name:
            continue
        row = conn.execute(
            "SELECT id, name FROM groups_list WHERE name = ? AND deleted_at IS NULL LIMIT 1",
            (part,)
        ).fetchone()
        if row:
            targets.append(row)
    return targets


def _mirror_week_lessons(conn, group_name, placed):
    """Дублирует созданные пары в группы-дублёры составного потока
    с теми же датами, периодами, преподавателями и аудиториями."""
    targets = _mirror_target_groups(conn, group_name)
    if not targets or not placed:
        return 0
    mirrored = 0
    for target in targets:
        for date_str, period, subj_id, teacher_id, classroom_id, is_sub, original_tid in placed:
            conflicts, blocking = _validate_slot_3d(conn, date_str, period, target['id'])
            if blocking:
                continue
            day_id = _get_or_create_day(conn, date_str, target['name'])
            conn.execute('''
                INSERT INTO lessons (day_id, period, subject_id, teacher_id, classroom_id, group_id,
                                     is_substitution, original_teacher_id)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ''', (day_id, period, subj_id, teacher_id, classroom_id, target['id'], int(is_sub), original_tid))
            mirrored += 1
    return mirrored


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
    mirrored = 0
    errors = []

    # Determine course to clamp allowed periods
    group_row = conn.execute(
        "SELECT course FROM groups_list WHERE id = ? AND deleted_at IS NULL", (group_id,)
    ).fetchone()
    is_first_course = group_row is not None and group_row['course'] == 1
    allowed_periods = [1, 2, 3, 4] if is_first_course else list(range(1, 9))

    weeks_dates = [_build_week_dates(
        (datetime.strptime(monday_str, '%Y-%m-%d') + timedelta(weeks=w)).strftime('%Y-%m-%d')
    ) for w in range(week_count)]

    # Build a flat pool of (subject_id, teacher_id, priority) pairs to place each week.
    # priority = pace delta (lower = more behind → scheduled first).
    for wi, week_dates in enumerate(weeks_dates):
        pool = []
        # Compute total semester load for the plan to derive expected pace
        for item in curriculum:
            weeks = item['weeks_in_semester'] or 18
            if wi >= weeks:
                continue
            total_hours = item['total_hours']
            weekly = max(1, (total_hours + weeks * 2 - 1) // (weeks * 2))
            plan_total = weekly * weeks
            # Expected pairs by this week (first wi weeks fully scheduled)
            expected = round((plan_total / weeks) * wi)
            # Actual pairs done for this subject so far (all weeks until now)
            actual = conn.execute('''
                SELECT COUNT(*) FROM lessons l
                JOIN schedule_days sd ON l.day_id = sd.id
                WHERE l.subject_id = ? AND l.group_id = ?
                  AND l.deleted_at IS NULL AND sd.deleted_at IS NULL
                  AND sd.date < ?
            ''', (item['subject_id'], group_id, week_dates[0])).fetchone()[0]
            delta_pace = actual - expected
            # Count existing lessons on the target week
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
                    pool.append((item['subject_id'], item['teacher_id'], delta_pace))

        if not pool:
            continue

        # Prioritise subjects lagging pace (most negative delta first)
        pool.sort(key=lambda x: x[2])

        # Seeded shuffle for controlled week-to-week variation within priority tiers
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

        # Round-robin: distribute pool across 6 days, respecting daily load limits
        # (weekdays ≤ 4 pairs, Saturday ≤ 3 pairs); excess rolls over to days with free capacity
        day_lessons = [[] for _ in range(6)]
        for i, (subj_id, teach_id, _prio) in enumerate(pool):
            for offset in range(6):
                day_idx = day_order[(i + offset) % 6]
                if len(day_lessons[day_idx]) < _max_pairs_per_day(day_idx):
                    day_lessons[day_idx].append((subj_id, teach_id, _prio))
                    break
            else:
                errors.append(f"Неделя {week_dates[0]}: дневные лимиты нагрузки переполнены, пара ({subj_id}) не размещена")

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

        placed = []  # (date, period, subject, teacher, classroom, is_sub, original_teacher) for mirroring
        for day_idx, lessons in enumerate(day_lessons):
            if not lessons:
                continue
            date_str = week_dates[day_idx]
            # 1 сентября — линейка/организационные мероприятия ТОЛЬКО для 1-го курса
            if is_first_course and date_str.endswith('-09-01'):
                continue
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
            # Защита от бесконечного цикла: если одна и та же пара не помещается
            # после большого числа попыток (все периоды заняты), пропускаем её.
            block_attempts = 0
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
                subj_id, primary_tid, _prio = lessons[0]
                actual_tid, original_tid, is_sub = _resolve_teacher_substitution(
                    conn, subj_id, primary_tid, group_id, date_str, period
                )
                if actual_tid is None:
                    subject_name = next((c['subject_name'] or f'#{subj_id}' for c in curriculum if c['subject_id'] == subj_id), f'#{subj_id}')
                    teacher_name = next((c['teacher_name'] or f'#{primary_tid}' for c in curriculum if c['teacher_id'] == primary_tid), f'#{primary_tid}')
                    errors.append(
                        f"Неделя {week_dates[0]}, {date_str}: преподаватель «{teacher_name}» отсутствует, "
                        f"замена по предмету «{subject_name}» не найдена — пара пропущена"
                    )
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
                    placed.append((date_str, period, subj_id, actual_tid, classroom_id, is_sub, original_tid))
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
                    # Если пара бьётся слишком долго — признак заполненного дня:
                    # пропускаем её, а не зависаем в цикле (периоды 1<->2 не совпадают).
                    block_attempts += 1
                    if block_attempts > 40:
                        subj_name_blocked = next((c['subject_name'] for c in curriculum if c['subject_id'] == subj_id), subj_id)
                        errors.append(
                            f"Неделя {week_dates[0]}, {date_str}: не удалось разместить пару "
                            f"«{subj_name_blocked}» — все периоды дня заняты"
                        )
                        lessons.pop(0)
                        placed_in_day += 1
                        block_attempts = 0

        # Post-processing: mirror week's pairs to linked groups of a composite stream (e.g. '02-0923+11/24')
        mirrored += _mirror_week_lessons(conn, group_name, placed)

    return {'created': created, 'mirrored': mirrored, 'errors': errors}
