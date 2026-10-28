# Изменение №3 (бэкенд-рефакторинг): выделен utils.py

import re
from datetime import datetime

# Экзамены/зачёты ликвидационной сессии: «1.Криминалистика», «2.Криминалистика»,
# «Криминалистика (Экз.ликвид.сесс)» — это разовые события, а не обычные пары.
SPECIAL_EXAM_RE = re.compile(r'^\s*\d+\.|\(\s*\u042d\u043a\u0437\.?\s*\u043b\u0438\u043a\u0432\u0438\u0434', re.IGNORECASE)

# Схемы колонок для импорта справочников из Excel.
# Каждое свойство (name/phone/course/specialty) имеет список допустимых заголовков:
# первый (канонический) используется в скачиваемом шаблоне, остальные — допускаются
# при чтении пользовательских файлов (синонимы).
EXCEL_IMPORT_SCHEMAS = {
    'teachers': {
        'name': ['ФИО преподавателя', 'ФИО', 'Преподаватель', 'Фамилия', 'Имя'],
        'phone': ['Телефон'],
    },
    'classrooms': {
        'name': ['Номер аудитории', 'Аудитория', 'Кабинет', 'Номер'],
    },
    'groups': {
        'name': ['Название группы', 'Группа', 'Название'],
        'course': ['Курс (1-4)', 'Курс'],
        'specialty': ['Код специальности', 'Специальность'],
    },
    'subjects': {
        'name': ['Название предмета', 'Предмет', 'Название'],
    },
}

# Канонические заголовки для генерации шаблонов (строго 1 колонка на свойство).
EXCEL_IMPORT_TEMPLATE_HEADERS = {
    'teachers': ['ФИО преподавателя', 'Телефон'],
    'classrooms': ['Номер аудитории'],
    'groups': ['Название группы', 'Курс (1-4)', 'Код специальности'],
    'subjects': ['Название предмета'],
}

EXCEL_IMPORT_TEMPLATE_EXAMPLES = {
    'teachers': [['Иванов Иван Иванович', '+7-900-000-00-00'], ['Петрова Анна Сергеевна', '']],
    'classrooms': [['101'], ['202']],
    'groups': [['01-01/26', '1', '40.02.04'], ['02-02/26', '2', '38.02.01']],
    'subjects': [['Математика'], ['Русский язык']],
}


def normalize_cell(value):
    """Привести ячейку к строке без лишних пробелов (или None, если пусто)."""
    if value is None:
        return None
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    if isinstance(value, int):
        return str(value)
    text = str(value).strip()
    return text or None


def validate_excel_headers(header_cells, entity_type):
    """Проверить заголовок листа Excel под entity_type. Возвращает (errors: list, col_map: dict).
    col_map.keyed по свойству (name/phone/course/specialty) -> индекс колонки."""
    schema = EXCEL_IMPORT_SCHEMAS.get(entity_type)
    if not schema:
        return [f"Неизвестный тип импорта: {entity_type}"], {}
    col_map = {}
    present = {}
    for idx, raw in enumerate(header_cells):
        key = normalize_cell(raw)
        if key:
            present[key] = idx
    name_aliases = schema.get('name', [])
    for alias in name_aliases:
        if alias in present:
            col_map['name'] = present[alias]
            break
    if col_map.get('name') is None:
        return [f"В файле нет колонки с названием ({', '.join(name_aliases)})."], {}
    for prop in ('phone', 'course', 'specialty'):
        for alias in schema.get(prop, []):
            if alias in present:
                col_map[prop] = present[alias]
                break
    return [], col_map


def parse_excel_import(file_stream, entity_type):
    """Считать .xlsx и вернуть (headers_err, col_map, rows, errors).
    rows — список dict с ключами name/phone/course/specialty_code, уже нормализованные.
    Пустые строки и строки без названия пропускаются."""
    from openpyxl import load_workbook
    try:
        wb = load_workbook(file_stream, data_only=True)
    except Exception as exc:
        return f"Не удалось прочитать файл: {exc}", {}, [], []
    ws = wb.active
    rows_iter = ws.iter_rows(values_only=True)
    try:
        header_row = next(rows_iter, None)
    except StopIteration:
        header_row = None
    if not header_row:
        return "Файл пуст (нет заголовков).", {}, [], []
    hdr_errors, col_map = validate_excel_headers(header_row, entity_type)
    if hdr_errors:
        return hdr_errors[0], {}, [], []

    rows = []
    errors = []
    for r_i, row in enumerate(rows_iter, start=2):  # данные начинаются со 2-й строки
        name = normalize_cell(row[col_map['name']]) if col_map['name'] < len(row) else None
        if not name:
            continue  # пропуск пустых строк
        item = {'name': name, '_row': r_i}
        if col_map.get('phone') is not None and col_map['phone'] < len(row):
            item['phone'] = normalize_cell(row[col_map['phone']])
        if col_map.get('course') is not None and col_map['course'] < len(row):
            item['course'] = normalize_cell(row[col_map['course']])
        if col_map.get('specialty') is not None and col_map['specialty'] < len(row):
            item['specialty_code'] = normalize_cell(row[col_map['specialty']])
        rows.append(item)
    return None, col_map, rows, errors


LESSON_SELECT = '''SELECT l.*, t.name AS teacher_name, s.name AS subject_name,
       c.name AS classroom_name,
       c2.name AS classroom_2_name,
       ot.name AS original_teacher_name,
       CASE WHEN l.subgroup IS NOT NULL THEN gl.name || ' (' || l.subgroup || ')' ELSE gl.name END AS groups
FROM lessons l
LEFT JOIN teachers t ON l.teacher_id = t.id AND t.deleted_at IS NULL
LEFT JOIN subjects s ON l.subject_id = s.id AND s.deleted_at IS NULL
LEFT JOIN classrooms_list c ON l.classroom_id = c.id AND c.deleted_at IS NULL
LEFT JOIN classrooms_list c2 ON l.classroom_id_2 = c2.id AND c2.deleted_at IS NULL
LEFT JOIN groups_list gl ON l.group_id = gl.id AND gl.deleted_at IS NULL
LEFT JOIN teachers ot ON l.original_teacher_id = ot.id AND ot.deleted_at IS NULL'''

LESSON_SELECT_WITH_DAY = '''SELECT l.*, sd.date, sd.group_name, sd.day_name,
       t.name AS teacher_name, s.name AS subject_name,
       c.name AS classroom_name,
       c2.name AS classroom_2_name,
       ot.name AS original_teacher_name,
       CASE WHEN l.subgroup IS NOT NULL THEN gl.name || ' (' || l.subgroup || ')' ELSE gl.name END AS groups
FROM lessons l
JOIN schedule_days sd ON l.day_id = sd.id
LEFT JOIN teachers t ON l.teacher_id = t.id AND t.deleted_at IS NULL
LEFT JOIN subjects s ON l.subject_id = s.id AND s.deleted_at IS NULL
LEFT JOIN classrooms_list c ON l.classroom_id = c.id AND c.deleted_at IS NULL
LEFT JOIN classrooms_list c2 ON l.classroom_id_2 = c2.id AND c2.deleted_at IS NULL
LEFT JOIN groups_list gl ON l.group_id = gl.id AND gl.deleted_at IS NULL
LEFT JOIN teachers ot ON l.original_teacher_id = ot.id AND ot.deleted_at IS NULL'''


def _validate_lesson_slot(conn, day, period, subject_id=None, teacher_id=None,
                          classroom_id=None, group_id=None, subgroup=None, exclude_id=None):
    """Единый поиск конфликтов для слота (day, period).
    Возвращает dict с тремя выборками:
      teacher_conflicts  — уроки, где учитель занят на ту же дату+пару
      classroom_conflicts — уроки, где аудитория занята на ту же дату+пару
      duplicate_conflicts — уроки той же группы+подгруппы в том же дне+паре
    Каждый элемент — полноценная строка (Row), которую потребители
    форматят под свой ответ (например: /api/validate или _validate_lesson_data)."""
    conflicts = {'teacher': [], 'classroom': [], 'duplicate': []}

    if teacher_id:
        existing = conn.execute('''
            SELECT l.*, sd.day_name, sd.date, sd.group_name, t.name AS teacher_name,
                   CASE WHEN l.subgroup IS NOT NULL THEN gl.name || ' (' || l.subgroup || ')' ELSE gl.name END AS groups
            FROM lessons l
            JOIN schedule_days sd ON l.day_id = sd.id
            LEFT JOIN teachers t ON l.teacher_id = t.id
            LEFT JOIN groups_list gl ON l.group_id = gl.id
            WHERE l.teacher_id = ? AND l.period = ? AND sd.date = ?
              AND l.subject_id IS NOT NULL AND l.deleted_at IS NULL AND sd.deleted_at IS NULL
        ''', (teacher_id, period, day['date'])).fetchall()
        if exclude_id:
            existing = [e for e in existing if e['id'] != exclude_id]
        conflicts['teacher'] = existing

    if classroom_id:
        conflicts['classroom'] = conn.execute('''
            SELECT l.*, sd.day_name, sd.date, sd.group_name, c.name AS classroom_name,
                   CASE WHEN l.subgroup IS NOT NULL THEN gl.name || ' (' || l.subgroup || ')' ELSE gl.name END AS groups
            FROM lessons l
            JOIN schedule_days sd ON l.day_id = sd.id
            LEFT JOIN classrooms_list c ON l.classroom_id = c.id
            LEFT JOIN groups_list gl ON l.group_id = gl.id
            WHERE l.classroom_id = ? AND l.period = ? AND sd.date = ?
              AND l.subject_id IS NOT NULL AND l.deleted_at IS NULL AND sd.deleted_at IS NULL
        ''', (classroom_id, period, day['date'])).fetchall()
        if exclude_id:
            existing = [e for e in conflicts['classroom'] if e['id'] != exclude_id]
            conflicts['classroom'] = existing

    if group_id is not None and subject_id:
        existing = conn.execute(
            "SELECT l.* FROM lessons l WHERE l.day_id = ? AND l.period = ? "
            "AND l.subject_id IS NOT NULL AND l.deleted_at IS NULL",
            (day['id'], period)).fetchall()
        if exclude_id:
            existing = [e for e in existing if e['id'] != exclude_id]
        for e in existing:
            if e['group_id'] == group_id and (e['subgroup'] or '') == (subgroup or ''):
                conflicts['duplicate'].append(e)

    return conflicts


def _validate_lesson_data(conn, day_id, period, teacher_id, classroom_id, subject_id=None,
                          exclude_id=None, group_id=None, subgroup=None, skip_day_check=False):
    warnings = []
    blocking = False

    if skip_day_check:
        day = conn.execute('SELECT * FROM schedule_days WHERE id = ?', (day_id,)).fetchone()
    else:
        day = conn.execute('SELECT * FROM schedule_days WHERE id = ? AND deleted_at IS NULL', (day_id,)).fetchone()
    if not day:
        return warnings, blocking

    conflicts = _validate_lesson_slot(conn, day, period, subject_id=subject_id,
                                      teacher_id=teacher_id, classroom_id=classroom_id,
                                      group_id=group_id, subgroup=subgroup, exclude_id=exclude_id)

    if conflicts['teacher']:
        warnings.append(f"Teacher busy on {conflicts['teacher'][0]['day_name']} period {period}")
        blocking = True

    if conflicts['classroom']:
        warnings.append(f"Classroom busy on {conflicts['classroom'][0]['day_name']} period {period}")
        blocking = True

    if conflicts['duplicate']:
        warnings.append("Duplicate lesson in this cell")
        blocking = True

    return warnings, blocking


def _validate_slot_3d(conn, date_str, period, group_id, teacher_id=None, classroom_id=None, exclude_lesson_id=None):
    """Strict 3D collision check for a slot (date, period):
    group free / teacher free / classroom free. Any overlap blocks the slot."""
    conflicts = []
    blocking = False
    if group_id is not None:
        row = conn.execute('''
            SELECT 1 FROM lessons l JOIN schedule_days sd ON l.day_id = sd.id
            WHERE sd.date = ? AND l.period = ? AND l.group_id = ?
              AND l.subject_id IS NOT NULL AND l.deleted_at IS NULL AND sd.deleted_at IS NULL
              AND (? IS NULL OR l.id != ?)
            LIMIT 1
        ''', (date_str, period, group_id, exclude_lesson_id, exclude_lesson_id)).fetchone()
        if row:
            conflicts.append('group')
            blocking = True
    if teacher_id:
        row = conn.execute('''
            SELECT 1 FROM lessons l JOIN schedule_days sd ON l.day_id = sd.id
            WHERE sd.date = ? AND l.period = ? AND l.teacher_id = ?
              AND l.subject_id IS NOT NULL AND l.deleted_at IS NULL AND sd.deleted_at IS NULL
              AND (? IS NULL OR l.id != ?)
            LIMIT 1
        ''', (date_str, period, teacher_id, exclude_lesson_id, exclude_lesson_id)).fetchone()
        if row:
            conflicts.append('teacher')
            blocking = True
    if classroom_id:
        row = conn.execute('''
            SELECT 1 FROM lessons l JOIN schedule_days sd ON l.day_id = sd.id
            WHERE sd.date = ? AND l.period = ? AND l.classroom_id = ?
              AND l.subject_id IS NOT NULL AND l.deleted_at IS NULL AND sd.deleted_at IS NULL
              AND (? IS NULL OR l.id != ?)
            LIMIT 1
        ''', (date_str, period, classroom_id, exclude_lesson_id, exclude_lesson_id)).fetchone()
        if row:
            conflicts.append('classroom')
            blocking = True
    return conflicts, blocking


def is_special_event_subject(name):
    """Название предмета похоже на экзамен ликвидационной сессии."""
    return bool(name and SPECIAL_EXAM_RE.search(str(name)))


def _safe_filename(s):
    return re.sub(r'[\\/:*?"<>|]+', '_', s).strip('_')


def parse_date_arg(value):
    """Разобрать дату `YYYY-MM-DD` из параметра запроса.

    Возвращает `datetime.date` или `None`, если формат неверный. Нужна, чтобы
    эндпоинты отвечали 400 вместо 500 (раньше `strptime` бросал исключение).
    """
    try:
        return datetime.strptime(str(value), '%Y-%m-%d').date()
    except (TypeError, ValueError):
        return None


def parse_int_arg(value):
    """Разобрать целое из параметра запроса; `None`, если значение не число."""
    if value is None or value == '':
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None
