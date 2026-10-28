import logging
import math
import random
import time
from datetime import datetime, timedelta
from utils import _validate_slot_3d, is_special_event_subject

logger = logging.getLogger(__name__)

DAY_ORDER = ['Понедельник', 'Вторник', 'Среда', 'Четверг', 'Пятница', 'Суббота']
BELL_SCHEDULE = list(range(1, 9))

MAX_PAIRS_WEEKDAY = 4
MAX_PAIRS_SATURDAY = 3

# Реальные расписания: последняя пара — 7-я (18:25–19:50); 8-ю не ставим.
GENERATOR_MAX_PERIOD = 8
SHIFT2_PERIODS = [3, 4, 5, 6, 7, 8]   # 2-я смена начинается с 13:30
SHIFT2_EXPECTED_START = 4          # ожидаемый старт 2-й смены


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


def _subject_required_room_type(conn, subject_id):
    """Тип аудитории, требуемый предметом (NULL — обычная аудитория)."""
    row = conn.execute(
        "SELECT required_room_type FROM subjects WHERE id = ? AND deleted_at IS NULL",
        (subject_id,)
    ).fetchone()
    value = row["required_room_type"] if row else None
    return value.strip() if isinstance(value, str) and value.strip() else None


def _room_type_matches(room_type, required_room_type):
    """NULL/'normal' — обычная аудитория; спец. предметы ходят только в свой тип."""
    current = (room_type or "").strip()
    if required_room_type:
        return current == required_room_type
    return current in ("", "normal")


def _pick_classroom(conn, subject_id, teacher_id, date_str, period, last_classroom_id,
                    required_room_type=None):
    """Cascade classroom selection с учётом типа аудитории.

    Спец. предметы (физкультура → gym, информатика → computer) ставятся только
    в аудиторию требуемого типа; остальные — в свободную обычную.
    """
    rows = conn.execute(
        "SELECT id, room_type FROM classrooms_list WHERE deleted_at IS NULL "
        "ORDER BY CAST(name AS INTEGER), name"
    ).fetchall()
    candidates = [r["id"] for r in rows if _room_type_matches(r["room_type"], required_room_type)]

    def free(room_id):
        return room_id in candidates and _is_classroom_free(conn, room_id, date_str, period)

    # Preference 1: keep the same room as previous lesson in same day
    if last_classroom_id is not None and free(last_classroom_id):
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
        if t_row and t_row['default_classroom_id'] and free(t_row['default_classroom_id']):
            return t_row['default_classroom_id']
    # Preference 3: teacher's own default classroom
    t_row = conn.execute(
        "SELECT default_classroom_id FROM teachers WHERE id = ? AND deleted_at IS NULL",
        (teacher_id,)
    ).fetchone()
    if t_row and t_row['default_classroom_id'] and free(t_row['default_classroom_id']):
        return t_row['default_classroom_id']
    # Fallback: first free room of the allowed type
    for room_id in candidates:
        if _is_classroom_free(conn, room_id, date_str, period):
            return room_id
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



# ---- Фаза 2: имитация отжига (оптимизация готового черновика) ----

W_TEACHER_GAP_BASE = 10   # окно преподавателя: базовый штраф за разрыв
W_TEACHER_GAP_STEP = 6    # + за каждую «пустую» пару в разрыве
W_GROUP_GAP_BASE = 100    # окно группы: «рваный» день недопустим — штраф выше любого другого
W_GROUP_GAP_STEP = 100    # +100 за каждую пропущенную пару в разрыве
W_GROUP_START = 100       # каждая пустая пара в начале дня (день должен начинаться с 1-й)
W_OVERLOAD = 5            # каждая пара сверх дневного лимита (4 пары подряд — норма)
W_TEACHER_EIGHTH_PAIR = 200  # 8-я пара у преподавателя — только в крайнем случае
OPTIMIZE_ITERATIONS = 1000
OPTIMIZE_TIME_BUDGET = 2.5
ANNEAL_T_START = 8.0
ANNEAL_T_END = 0.5


def _is_friday(date_str):
    try:
        return datetime.strptime(date_str, '%Y-%m-%d').weekday() == 4
    except (TypeError, ValueError):
        return False


def _is_saturday(date_str):
    try:
        return datetime.strptime(date_str, '%Y-%m-%d').weekday() == 5
    except (TypeError, ValueError):
        return False


def _gap_cost(periods, base, step):
    """Штраф за разрывы между парами в один день: gap = пропущенные пары."""
    ordered = sorted(periods)
    total = 0
    for prev, nxt in zip(ordered, ordered[1:]):
        gap = nxt - prev - 1
        if gap > 0:
            total += base + step * gap
    return total


def _calculate_cost(plan, fixed=None, expected_start=1, friday_start=None):
    """Стоимость плана: чем меньше — тем лучше.

    Штрафы: окна преподавателей (сильные), окна групп (средние),
    перегруз дня у группы (слабый). `fixed` — чужие занятия (из БД),
    чтобы окна преподавателя считались по всей его дневной нагрузке.
    `expected_start` — ожидаемый первый период дня (1-я смена — 1, 2-я — 4).
    `friday_start` — для 1-го курса в пятницу разрешён старт со 2-й пары:
    и 1-я, и 2-я пары не штрафуются (более поздний старт — штраф).
    """
    teacher_days, group_days = {}, {}
    for item in list(plan) + list(fixed or []):
        date, period = item.get('date'), item.get('period')
        if date is None or period is None:
            continue
        tid, gid = item.get('teacher_id'), item.get('group_id')
        if tid is not None:
            teacher_days.setdefault((tid, date), set()).add(period)
        if gid is not None:
            group_days.setdefault((gid, date), set()).add(period)

    cost = 0
    for periods in teacher_days.values():
        cost += _gap_cost(periods, W_TEACHER_GAP_BASE, W_TEACHER_GAP_STEP)
        if 8 in periods:
            # 7 пар у преподавателя — норма (бывает и 8, как у Балашовой), но дорого
            cost += W_TEACHER_EIGHTH_PAIR
    for (gid, date), periods in group_days.items():
        cost += _gap_cost(periods, W_GROUP_GAP_BASE, W_GROUP_GAP_STEP)
        first_period = min(periods)
        friday_mode = bool(friday_start and _is_friday(date))
        expected_for_day = friday_start if friday_mode else expected_start
        if first_period > expected_for_day:
            # День должен начинаться с ожидаемой пары (1-я смена — 1, 2-я — 4).
            cost += W_GROUP_START * (first_period - expected_for_day)
        elif first_period < expected_for_day and not friday_mode:
            cost += W_GROUP_START * (expected_for_day - first_period)
        limit = MAX_PAIRS_SATURDAY if _is_saturday(date) else MAX_PAIRS_WEEKDAY
        if len(periods) > limit:
            cost += W_OVERLOAD * (len(periods) - limit)
    return cost


def _occupancy(items):
    """Множества занятых (дата, пара) по преподавателю/аудитории/группе."""
    teachers, classrooms, groups = {}, {}, {}
    for item in items:
        key = (item.get('date'), item.get('period'))
        if item.get('teacher_id') is not None:
            teachers.setdefault(key, set()).add(item['teacher_id'])
        if item.get('classroom_id') is not None:
            classrooms.setdefault(key, set()).add(item['classroom_id'])
        if item.get('group_id') is not None:
            groups.setdefault(key, set()).add(item['group_id'])
    return teachers, classrooms, groups


def _slot_taken(occupancy, date, period, item):
    teachers, classrooms, groups = occupancy
    key = (date, period)
    if item.get('teacher_id') is not None and item['teacher_id'] in teachers.get(key, ()):
        return True
    if item.get('classroom_id') is not None and item['classroom_id'] in classrooms.get(key, ()):
        return True
    if item.get('group_id') is not None and item['group_id'] in groups.get(key, ()):
        return True
    return False


def _optimize_schedule(plan, seed=None, iterations=OPTIMIZE_ITERATIONS,
                       time_budget=OPTIMIZE_TIME_BUDGET, fixed=None, allowed_periods=None,
                       same_date_only=False, expected_start=1, friday_start=None):
    """Имитация отжига: двигаем пары по периодам в рамках тех же дней.

    Жёсткие ограничения (преподаватель/аудитория/группа) проверяются по
    in-memory индексам занятости: конфликтный ход просто не применяется.
    Детерминированность — за счёт `random.Random(seed)`.
    `same_date_only=True` — свап только между парами одной даты: режим для записи
    в БД, где мы обновляем только `period` и не переносим пары на другие дни.

    Возвращает лучший найденный план (не хуже исходного).
    """
    if not plan:
        return []
    rng = random.Random(seed)
    current = [dict(item) for item in plan]
    fixed = [dict(item) for item in (fixed or [])]
    allowed = sorted(set(allowed_periods) if allowed_periods else {1, 2, 3, 4, 5, 6, 7, 8})
    if len(allowed) < 2:
        return current

    def cost_of(items):
        return _calculate_cost(items, fixed, expected_start=expected_start,
                              friday_start=friday_start)

    current_cost = cost_of(current)
    best = [dict(item) for item in current]
    best_cost = current_cost
    deadline = time.time() + max(0.0, time_budget)
    count = len(current)

    for step in range(iterations):
        if step % 25 == 0 and time.time() >= deadline:
            logger.info("Annealing: остановлен по таймауту на итерации %d (cost=%d)", step, best_cost)
            break
        progress = step / max(1, iterations - 1)
        temperature = ANNEAL_T_START * (ANNEAL_T_END / ANNEAL_T_START) ** progress

        if count >= 2 and rng.random() < 0.6:
            i, j = rng.sample(range(count), 2)
            a, b = current[i], current[j]
            if b['period'] not in allowed or a['period'] not in allowed:
                continue
            if (a['date'], a['period'], a.get('group_id')) == (b['date'], b['period'], b.get('group_id')):
                continue
            if same_date_only and a['date'] != b['date']:
                continue
            rest = [item for k, item in enumerate(current) if k not in (i, j)]
            occupancy = _occupancy(rest + fixed)
            if (_slot_taken(occupancy, b['date'], b['period'], a)
                    or _slot_taken(occupancy, a['date'], a['period'], b)):
                continue
            current[i] = {**a, 'date': b['date'], 'period': b['period']}
            current[j] = {**b, 'date': a['date'], 'period': a['period']}
            new_cost = cost_of(current)
            if new_cost <= current_cost or rng.random() < math.exp(-(new_cost - current_cost) / max(temperature, 1e-9)):
                current_cost = new_cost
                if new_cost < best_cost:
                    best_cost = new_cost
                    best = [dict(item) for item in current]
            else:
                current[i], current[j] = a, b
        else:
            i = rng.randrange(count)
            a = current[i]
            new_period = rng.choice(allowed)
            if new_period == a['period']:
                continue
            rest = [item for k, item in enumerate(current) if k != i]
            occupancy = _occupancy(rest + fixed)
            if _slot_taken(occupancy, a['date'], new_period, a):
                continue
            old_period = a['period']
            current[i] = {**a, 'period': new_period}
            new_cost = cost_of(current)
            if new_cost <= current_cost or rng.random() < math.exp(-(new_cost - current_cost) / max(temperature, 1e-9)):
                current_cost = new_cost
                if new_cost < best_cost:
                    best_cost = new_cost
                    best = [dict(item) for item in current]
            else:
                current[i] = {**a, 'period': old_period}

    return best


def _optimize_week(conn, group_id, group_name, week_dates, allowed_periods, seed,
                   lesson_ids=None, expected_start=1, friday_start=None):
    """Отжиг для уже созданной недели: меняем только `period` (day_id не трогаем).

    Составные потоки (группы с «+») пропускаем: их пары зеркалируются в другие
    группы, и перестановка одной стороны рассинхронизировала бы дубли.
    """
    if not lesson_ids:
        return 0
    mirror_targets = _mirror_target_groups(conn, group_name)
    if mirror_targets:
        logger.info(
            "Annealing skipped for %s %s: составной поток, зеркальные группы (%s) — "
            "перестановка одной стороны рассинхронизировала бы дубли",
            group_name, week_dates[0], ', '.join(t['name'] for t in mirror_targets),
        )
        return 0
    placeholders = ','.join('?' * len(week_dates))
    ids_clause = ','.join('?' * len(lesson_ids))
    rows = conn.execute(f"""
        SELECT l.id, sd.date, l.period, l.subject_id, l.teacher_id, l.classroom_id, l.group_id
        FROM lessons l
        JOIN schedule_days sd ON l.day_id = sd.id
        WHERE l.group_id = ? AND sd.date IN ({placeholders}) AND l.id IN ({ids_clause})
          AND COALESCE(l.is_special_event, 0) = 0
          AND l.deleted_at IS NULL AND sd.deleted_at IS NULL
    """, [group_id] + list(week_dates) + list(lesson_ids)).fetchall()
    if len(rows) < 2:
        return 0
    fixed_rows = conn.execute(f"""
        SELECT sd.date, l.period, l.teacher_id, l.classroom_id, l.group_id
        FROM lessons l
        JOIN schedule_days sd ON l.day_id = sd.id
        WHERE sd.date IN ({placeholders}) AND l.group_id != ?
          AND l.deleted_at IS NULL AND sd.deleted_at IS NULL
    """, list(week_dates) + [group_id]).fetchall()

    plan = [dict(row) for row in rows]
    fixed = [dict(row) for row in fixed_rows]
    before = _calculate_cost(plan, fixed, expected_start=expected_start, friday_start=friday_start)
    optimized = _optimize_schedule(plan, seed=seed, fixed=fixed, allowed_periods=allowed_periods,
                                   same_date_only=True, expected_start=expected_start,
                                   friday_start=friday_start)
    after = _calculate_cost(optimized, fixed, expected_start=expected_start, friday_start=friday_start)

    original_period = {item['id']: item['period'] for item in plan}
    moved = 0
    for item in optimized:
        if item['period'] != original_period.get(item['id']):
            conn.execute('UPDATE lessons SET period = ? WHERE id = ?', (item['period'], item['id']))
            moved += 1
    logger.info("Annealing %s %s: cost %d -> %d, moved %d", group_name, week_dates[0], before, after, moved)
    return moved


def _distribute_day_targets(total, day_offset=0):
    """Сколько пар ставить в каждый день недели (Пн..Сб).

    Ориентир — реальные расписания 1 курса: будни в среднем 3.2 пары (3–4),
    суббота легче — 2 пары. Поздний старт и «окна» в будни не закладываем.
    """
    targets = [0] * 6
    if total <= 0:
        return targets
    sat_target = 2 if total >= 17 else (1 if total >= 16 else 0)
    weekday_total = min(5 * MAX_PAIRS_WEEKDAY, total - min(sat_target, MAX_PAIRS_SATURDAY))
    per = min(MAX_PAIRS_WEEKDAY, weekday_total // 5)
    targets = [per] * 5 + [0]
    # Остаток раскидываем по одному дню, со сдвигом по неделе — иначе при малом
    # плане все пары недели падают на понедельник.
    remainder = weekday_total - 5 * per
    offset = day_offset % 5
    for i in range(remainder):
        targets[(i + offset) % 5] += 1
    targets[5] = max(0, min(MAX_PAIRS_SATURDAY, total - sum(targets[:5])))
    return targets


def generate_schedule(conn, group_id, group_name, semester, monday_str, week_count,
                      optimize=True, seed=None):
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
    opt_seed = seed if seed is not None else f"{group_id}_{monday_str}_{semester}"

    # Determine course to clamp allowed periods
    group_row = conn.execute(
        "SELECT course, shift FROM groups_list WHERE id = ? AND deleted_at IS NULL", (group_id,)
    ).fetchone()
    is_first_course = group_row is not None and group_row['course'] == 1
    group_shift = group_row['shift'] if group_row is not None and 'shift' in group_row.keys() else None
    if group_shift == 2:
        # 2-я смена: занятия с 13:30, пары 3–7, ожидаемый старт — 4-я пара
        allowed_periods = [p for p in SHIFT2_PERIODS if p <= GENERATOR_MAX_PERIOD]
        expected_start = SHIFT2_EXPECTED_START
    elif is_first_course:
        allowed_periods = [1, 2, 3, 4]
        expected_start = 1
    else:
        allowed_periods = list(range(1, GENERATOR_MAX_PERIOD + 1))
        expected_start = 1
    # 1-й курс в пятницу может начинать со 2-й пары (часы/окна) — это не штраф.
    friday_start = 2 if (is_first_course and group_shift != 2) else None

    weeks_dates = [_build_week_dates(
        (datetime.strptime(monday_str, '%Y-%m-%d') + timedelta(weeks=w)).strftime('%Y-%m-%d')
    ) for w in range(week_count)]

    # Build a flat pool of (subject_id, teacher_id, priority) pairs to place each week.
    # priority = pace delta (lower = more behind → scheduled first).
    for wi, week_dates in enumerate(weeks_dates):
        pool = []
        # Compute total semester load for the plan to derive expected pace
        for item in curriculum:
            # Экзамены ликвид. сессии («1.Криминалистика», «(Экз.ликвид.сесс)»)
            # не генерируем: это разовые мероприятия, их ставят вручную.
            if is_special_event_subject(item['subject_name']):
                continue
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

        # Раскладка по дням: будни 3–4 пары со старта с 1-й пары, суббота — 2 пары.
        # Реальные расписания (9 групп 1 курса): будни 3.2 в среднем, суббота 2, разрывов нет.
        day_targets = _distribute_day_targets(len(pool), day_offset=iso_week % 5)
        day_lessons = [[] for _ in range(6)]
        day_cursor = 0
        for item in pool:
            for _ in range(6):
                if len(day_lessons[day_cursor]) < day_targets[day_cursor]:
                    day_lessons[day_cursor].append(item)
                    day_cursor = (day_cursor + 1) % 6
                    break
                day_cursor = (day_cursor + 1) % 6
            else:
                subj_id = item[0]
                errors.append(f"Неделя {week_dates[0]}: дневные лимиты нагрузки переполнены, пара ({subj_id}) не размещена")

        placed = []  # (date, period, subject, teacher, classroom, is_sub, original_teacher) for mirroring
        created_ids = []  # id только что созданных пар — их и оптимизируем
        unplaced = []  # (subject_id, teacher_id): доберём в свободные слоты (top-up)

        def try_place(date_str, day_id, period, subj_id, primary_tid):
            """Поставить пару в конкретный слот; True при успехе (жёсткие ограничения соблюдены)."""
            actual_tid, original_tid, is_sub = _resolve_teacher_substitution(
                conn, subj_id, primary_tid, group_id, date_str, period
            )
            if actual_tid is None:
                return False
            required_room = _subject_required_room_type(conn, subj_id)
            classroom_id = _pick_classroom(conn, subj_id, actual_tid, date_str, period, None,
                                           required_room_type=required_room)
            # Спец. предмет без свободной аудитории нужного типа не ставим в обычную
            if required_room and classroom_id is None:
                return False
            conflicts, blocking = _validate_slot_3d(
                conn, date_str, period, group_id,
                teacher_id=actual_tid, classroom_id=classroom_id,
            )
            if blocking:
                return False
            cur = conn.execute('''
                INSERT INTO lessons (day_id, period, subject_id, teacher_id, classroom_id, group_id,
                                     is_substitution, original_teacher_id)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ''', (day_id, period, subj_id, actual_tid, classroom_id, group_id,
                  int(is_sub), original_tid))
            created_ids.append(cur.lastrowid)
            placed.append((date_str, period, subj_id, actual_tid, classroom_id, is_sub, original_tid))
            return True

        for day_idx, lessons in enumerate(day_lessons):
            if not lessons:
                continue
            date_str = week_dates[day_idx]
            if (is_first_course and date_str.endswith('-09-01')) or _is_holiday(conn, date_str):
                continue  # праздник/линейка: пары этой недели не переносим
            day_id = _get_or_create_day(conn, date_str, group_name)
            max_period = max(allowed_periods) if allowed_periods else 8
            queue = list(lessons)
            day_start = friday_start if (friday_start and _is_friday(date_str)) else expected_start
            period = day_start if allowed_periods else 1
            while queue and period <= max_period:
                subj_id, primary_tid, _prio = queue[0]
                if try_place(date_str, day_id, period, subj_id, primary_tid):
                    created += 1
                    queue.pop(0)
                    period += 1
                else:
                    period += 1
            # всё, что не влезло в день, досадим в другие дни (top-up), а не выбросим
            unplaced.extend((s, t) for s, t, _ in queue)

        # Шаг 2 (top-up): при коллизиях не теряем пары — ищем свободный слот в других
        # днях (сначала недогруженные будни, затем суббота).
        for subj_id, primary_tid in unplaced:
            placed_ok = False
            for day_idx in sorted(range(6), key=lambda d: (len(day_lessons[d]), d)):
                date_str = week_dates[day_idx]
                if (is_first_course and date_str.endswith('-09-01')) or _is_holiday(conn, date_str):
                    continue
                limit = _max_pairs_per_day(day_idx)
                if len(day_lessons[day_idx]) >= limit:
                    continue
                day_id = _get_or_create_day(conn, date_str, group_name)
                # Сначала ожидаемые периоды (2-я смена — с 4-й пары), затем остальные
                period_order = sorted(
                    [p for p in allowed_periods if p >= expected_start]
                    + [p for p in allowed_periods if p < expected_start]
                ) if allowed_periods else list(range(1, GENERATOR_MAX_PERIOD + 1))
                for period in period_order:
                    if try_place(date_str, day_id, period, subj_id, primary_tid):
                        created += 1
                        day_lessons[day_idx].append((subj_id, primary_tid, 0))
                        placed_ok = True
                        break
                if placed_ok:
                    break
            if not placed_ok:
                subj_name = next((c['subject_name'] for c in curriculum if c['subject_id'] == subj_id), subj_id)
                reason = 'все свободные слоты заняты (преподаватель/аудитория)'
                if _is_teacher_on_absence(conn, primary_tid, week_dates[0]):
                    reason = 'преподаватель отсутствует, замена не найдена'
                errors.append(
                    f"Неделя {week_dates[0]}: пара «{subj_name}» пропущена — {reason}"
                )

        # Фаза 2: оптимизация недели (окна/перегруз). Ошибка оптимизации не валит генерацию.
        if optimize:
            try:
                _optimize_week(conn, group_id, group_name, week_dates, allowed_periods,
                               f"{opt_seed}_{wi}", lesson_ids=created_ids,
                               expected_start=expected_start, friday_start=friday_start)
            except Exception:
                logger.exception("Annealing failed for %s %s — kept draft", group_name, week_dates[0])

        # Post-processing: mirror week's pairs to linked groups of a composite stream (e.g. '02-0923+11/24')
        mirrored += _mirror_week_lessons(conn, group_name, placed)

    return {'created': created, 'mirrored': mirrored, 'errors': errors}
