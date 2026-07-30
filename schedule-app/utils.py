# Изменение №3 (бэкенд-рефакторинг): выделен utils.py

import re

LESSON_SELECT = '''SELECT l.*, t.name AS teacher_name, s.name AS subject_name,
       c.name AS classroom_name,
       ot.name AS original_teacher_name,
       CASE WHEN l.subgroup IS NOT NULL THEN gl.name || ' (' || l.subgroup || ')' ELSE gl.name END AS groups
FROM lessons l
LEFT JOIN teachers t ON l.teacher_id = t.id AND t.deleted_at IS NULL
LEFT JOIN subjects s ON l.subject_id = s.id AND s.deleted_at IS NULL
LEFT JOIN classrooms_list c ON l.classroom_id = c.id AND c.deleted_at IS NULL
LEFT JOIN groups_list gl ON l.group_id = gl.id AND gl.deleted_at IS NULL
LEFT JOIN teachers ot ON l.original_teacher_id = ot.id AND ot.deleted_at IS NULL'''

LESSON_SELECT_WITH_DAY = '''SELECT l.*, sd.date, sd.group_name, sd.day_name,
       t.name AS teacher_name, s.name AS subject_name,
       c.name AS classroom_name,
       ot.name AS original_teacher_name,
       CASE WHEN l.subgroup IS NOT NULL THEN gl.name || ' (' || l.subgroup || ')' ELSE gl.name END AS groups
FROM lessons l
JOIN schedule_days sd ON l.day_id = sd.id
LEFT JOIN teachers t ON l.teacher_id = t.id AND t.deleted_at IS NULL
LEFT JOIN subjects s ON l.subject_id = s.id AND s.deleted_at IS NULL
LEFT JOIN classrooms_list c ON l.classroom_id = c.id AND c.deleted_at IS NULL
LEFT JOIN groups_list gl ON l.group_id = gl.id AND gl.deleted_at IS NULL
LEFT JOIN teachers ot ON l.original_teacher_id = ot.id AND ot.deleted_at IS NULL'''


def _validate_lesson_data(conn, day_id, period, teacher_id, classroom_id, subject_id=None, exclude_id=None, group_id=None, subgroup=None, skip_day_check=False):
    warnings = []
    blocking = False

    if skip_day_check:
        day = conn.execute('SELECT * FROM schedule_days WHERE id = ?', (day_id,)).fetchone()
    else:
        day = conn.execute('SELECT * FROM schedule_days WHERE id = ? AND deleted_at IS NULL', (day_id,)).fetchone()
    if not day:
        return warnings, blocking

    if teacher_id:
        existing = conn.execute('''
            SELECT l.*, sd.day_name, t.name AS teacher_name FROM lessons l
            JOIN schedule_days sd ON l.day_id = sd.id
            LEFT JOIN teachers t ON l.teacher_id = t.id
            WHERE l.teacher_id = ? AND l.period = ? AND sd.date = ? AND l.subject_id IS NOT NULL AND l.deleted_at IS NULL AND sd.deleted_at IS NULL
        ''', (teacher_id, period, day['date'])).fetchall()
        if exclude_id:
            existing = [e for e in existing if e['id'] != exclude_id]
        if existing:
            warnings.append(f"Teacher busy on {existing[0]['day_name']} period {period}")
            blocking = True

    if classroom_id:
        existing = conn.execute('''
            SELECT l.*, sd.day_name, c.name AS classroom_name FROM lessons l
            JOIN schedule_days sd ON l.day_id = sd.id
            LEFT JOIN classrooms_list c ON l.classroom_id = c.id
            WHERE l.classroom_id = ? AND l.period = ? AND sd.date = ? AND l.subject_id IS NOT NULL AND l.deleted_at IS NULL AND sd.deleted_at IS NULL
        ''', (classroom_id, period, day['date'])).fetchall()
        if exclude_id:
            existing = [e for e in existing if e['id'] != exclude_id]
        if existing:
            warnings.append(f"Classroom busy on {existing[0]['day_name']} period {period}")
            blocking = True

    if group_id is not None and subject_id:
        existing = conn.execute('''
            SELECT l.* FROM lessons l
            WHERE l.day_id = ? AND l.period = ? AND l.subject_id IS NOT NULL AND l.deleted_at IS NULL
        ''', (day_id, period)).fetchall()
        if exclude_id:
            existing = [e for e in existing if e['id'] != exclude_id]
        for e in existing:
            e_sub = e['subgroup']
            new_sub = subgroup
            e_gid = e['group_id']
            if e_gid == group_id and (e_sub or '') == (new_sub or ''):
                warnings.append("Duplicate lesson in this cell")
                blocking = True
                break

    return warnings, blocking


def _safe_filename(s):
    return re.sub(r'[\\/:*?"<>|]+', '_', s).strip('_')
