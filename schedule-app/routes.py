# Изменение №4 (бэкенд-рефакторинг): выделены маршруты в routes.py

import sqlite3
import os
import time
import io
import secrets
import logging
import threading
from datetime import datetime, timedelta
from functools import wraps
from xml.sax.saxutils import escape as _xml_escape

logger = logging.getLogger(__name__)
from flask import Blueprint, jsonify, request, session, send_file, render_template
from werkzeug.security import check_password_hash

from config import (
    SHIFT_LABELS, ADMIN_PASSWORD_HASH, DB_PATH,
    SETTINGS, apply_setting,
    BELL_SCHEDULE_PRESETS, get_bell_schedule, save_bell_schedule,
    TRASH_RETENTION_DAYS,
    LOGIN_CLEANUP_INTERVAL
)
from db import create_backup, prepare_for_restore, verify_db_integrity, find_orphaned_records, cleanup_orphan_schedule_records, get_db, is_date_excluded
from generator import generate_schedule
from utils import _safe_filename, _validate_lesson_data, _validate_lesson_slot, LESSON_SELECT, LESSON_SELECT_WITH_DAY, parse_excel_import, EXCEL_IMPORT_SCHEMAS, EXCEL_IMPORT_TEMPLATE_HEADERS, EXCEL_IMPORT_TEMPLATE_EXAMPLES, parse_date_arg, parse_int_arg, is_special_event_subject
from cache import refs_cache
from schedule_balancer import weekly_pairs, validate_weekly_load

bp = Blueprint('main', __name__)

# Пределы объёма генерации за один запрос: генерация выполняется в одной транзакции
# и блокирует записи остальных пользователей.
MAX_GENERATE_WEEKS = 12          # week_count (произвольный диапазон недель)
MAX_GENERATE_WEEKS_ALIAS = 4     # weeks_count (алиас «на месяц» из UI)


@bp.after_request
def set_charset(response):
    if response.content_type and 'text/html' in response.content_type:
        response.content_type = 'text/html; charset=utf-8'
    elif response.content_type and 'application/json' in response.content_type:
        response.content_type = 'application/json; charset=utf-8'
    if request.path.startswith('/static/'):
        response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
    return response


_login_attempts = {}
_last_cleanup_time = 0
_login_lock = threading.Lock()


def _clean_login_attempts():
    global _last_cleanup_time
    now = time.time()
    if now - _last_cleanup_time < LOGIN_CLEANUP_INTERVAL:
        return
    _last_cleanup_time = now
    expired = [ip for ip, ts in _login_attempts.items() if not ts or now - ts[-1] >= SETTINGS['login_rate_window']]
    for ip in expired:
        _login_attempts.pop(ip, None)


def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get('is_admin'):
            return jsonify({"error": "Unauthorized"}), 401
        return f(*args, **kwargs)
    return decorated


@bp.before_request
def csrf_check():
    if request.method in ('POST', 'PUT', 'DELETE', 'PATCH'):
        if request.path.startswith('/api/'):
            if request.path in ('/api/auth/login', '/api/auth/logout', '/api/auth/check'):
                return
            token = request.headers.get('X-CSRF-Token') or request.headers.get('X-CSRF-TOKEN') or ''
            if token != session.get('csrf_token'):
                return jsonify({"error": "CSRF token missing or invalid"}), 403


@bp.errorhandler(ValueError)
def _handle_bad_value(exc):
    """Некорректный параметр запроса (дата, число) — 400 вместо 500 с трассировкой.

    Раньше `?monday=garbage` или `?teacher_id=abc` валили обработчик исключением
    `datetime.strptime`/`int()` и отдавали 500 Internal Server Error.
    """
    logger.warning("Bad request value: %s", exc)
    return jsonify({"error": "Некорректный формат даты или ID"}), 400


def build_week_dates(monday_str):
    monday = datetime.strptime(monday_str, '%Y-%m-%d').date()
    names = ['Понедельник', 'Вторник', 'Среда', 'Четверг', 'Пятница', 'Суббота']
    return [{'day_name': names[i], 'date': (monday + timedelta(days=i)).isoformat()} for i in range(6)]


def _parse_date(value):
    """Тонкая обёртка над utils.parse_date_arg (None вместо исключения)."""
    return parse_date_arg(value)


def _int_param(raw, default=None):
    """Целое из параметра: default для пустого, None для нечислового."""
    if raw is None or raw == '':
        return default
    return parse_int_arg(raw)


def _bad_monday():
    return jsonify({"error": "Некорректный формат даты или ID"}), 400


def _public_ref(table, rows):
    """Справочник для неавторизованных: только безопасные поля.

    Публично доступные списки раньше отдавали внутренние колонки: phone у
    преподавателей, deleted_at, default_teacher_id. Администратор получает
    полную запись — формам редактирования нужны все поля.
    """
    if session.get('is_admin'):
        return rows
    allowed = {
        'teachers': ('id', 'name'),
        'subjects': ('id', 'name', 'required_room_type'),
        'classrooms_list': ('id', 'name', 'room_type'),
        'specialties': ('id', 'code', 'name', 'qualification'),
        'groups_list': ('id', 'name', 'course', 'is_distance', 'shift', 'specialty_id',
                        'specialty_code', 'specialty_name', 'specialty_qualification'),
    }.get(table)
    if not allowed:
        return rows
    return [{k: row.get(k) for k in allowed if k in row} for row in rows]


def _fetch_group_raw(group_name, monday, published_only=False):
    week_dates = build_week_dates(monday)
    date_list = [d['date'] for d in week_dates]
    conn = get_db()
    placeholders = ','.join('?' * len(date_list))
    sql = (
        f'SELECT * FROM schedule_days WHERE group_name = ? AND deleted_at IS NULL AND date IN ({placeholders})'
        + (' AND is_published = 1' if published_only else '')
        + ' ORDER BY date'
    )
    days = conn.execute(sql, [group_name] + date_list).fetchall()
    day_id_map = {day['date']: day['id'] for day in days}
    day_pub_map = {day['date']: bool(day['is_published']) for day in days}
    for wd in week_dates:
        wd['day_id'] = day_id_map.get(wd['date'])
        wd['is_published'] = day_pub_map.get(wd['date']) if wd['day_id'] else True
    lessons_by_date = {}
    for day in days:
        lessons = conn.execute(
            LESSON_SELECT + ' WHERE l.day_id = ? AND l.deleted_at IS NULL ORDER BY l.period',
            (day['id'],)
        ).fetchall()
        lessons_by_date[day['date']] = {}
        for l in lessons:
            p = l['period']
            if p not in lessons_by_date[day['date']]:
                lessons_by_date[day['date']][p] = []
            lessons_by_date[day['date']][p].append(dict(l))
    conn.close()
    return week_dates, lessons_by_date


def _fetch_entity_raw(entity_table, entity_id, entity_col, monday):
    week_dates = build_week_dates(monday)
    date_list = [d['date'] for d in week_dates]
    conn = get_db()
    placeholders = ','.join('?' * len(date_list))
    sql = f'''
        {LESSON_SELECT_WITH_DAY}
        WHERE l.{entity_col} = ? AND l.subject_id IS NOT NULL AND l.deleted_at IS NULL AND sd.deleted_at IS NULL AND sd.date IN ({placeholders})
        ORDER BY sd.date, l.period
    '''
    params = [entity_id] + date_list
    logger.debug("Export SQL: %s | params: %s", sql.strip().replace('\n', ' '), params)
    rows = conn.execute(sql, params).fetchall()
    logger.debug("Export rows count: %d", len(rows))
    conn.close()
    lessons_by_date_period = {}
    day_id_map = {}
    for r in rows:
        d = r['date']
        p = r['period']
        day_id_map[d] = r['day_id']
        if d not in lessons_by_date_period:
            lessons_by_date_period[d] = {}
        lessons_by_date_period[d][p] = {
            'id': r['id'], 'subject': r['subject_name'], 'teacher': r['teacher_name'],
            'classroom': r['classroom_name'],
            'groups': r['group_name'] or r['groups'],
            'day_id': r['day_id'],
            'group_id': r['group_id'], 'subgroup': r['subgroup']
        }
    for wd in week_dates:
        wd['day_id'] = day_id_map.get(wd['date'])
    return week_dates, lessons_by_date_period


def _build_schedule_periods(week_dates, lessons_by_date_period):
    periods = []
    for b in get_bell_schedule():
        p = b['period']
        lessons = {}
        for wd in week_dates:
            d = wd['date']
            lesson = lessons_by_date_period.get(d, {}).get(p)
            if lesson:
                lessons[d] = [{
                    'id': lesson['id'], 'subject': lesson['subject'], 'teacher': lesson['teacher'],
                    'classroom': lesson['classroom'], 'groups': lesson['groups'],
                    'day_id': lesson['day_id'],
                    'group_id': lesson.get('group_id'), 'subgroup': lesson.get('subgroup')
                }]
            else:
                lessons[d] = []
        periods.append({**b, 'lessons': lessons})
    return periods


def _get_export_data(schedule_type, name, monday, entity_id=None):
    if schedule_type == 'group':
        week_dates, lessons_by_date = _fetch_group_raw(name, monday)
        periods = []
        for b in get_bell_schedule():
            p = b['period']
            lessons = {}
            for wd in week_dates:
                d = wd['date']
                if d in lessons_by_date and p in lessons_by_date[d]:
                    raw_list = lessons_by_date[d][p]
                    lessons[d] = '\n---\n'.join(
                        (f"{l['custom_start_time']}–{l['custom_end_time']}\n" if l['custom_start_time'] else '')
                        + f"{l['subject_name'] or ''}\n{l['teacher_name'] or ''}\n{(l['classroom_name'] or '') + (' / ' + l['classroom_2_name'] if l['classroom_2_name'] else '')}"
                        for l in raw_list
                    )
                else:
                    lessons[d] = ''
            periods.append({**b, 'lessons': lessons})
        return week_dates, periods

    elif schedule_type == 'teacher':
        tid = entity_id
        if not tid:
            logger.warning("Export teacher: no id provided, fallback to name lookup for '%s'", name)
            conn = get_db()
            row = conn.execute(
                "SELECT id FROM teachers WHERE REPLACE(name, ' ', '') LIKE REPLACE(?, ' ', '') || '%'",
                (name,)
            ).fetchone()
            conn.close()
            if not row:
                return build_week_dates(monday), []
            tid = row['id']
        logger.info("Export teacher: id=%d", tid)
        week_dates, ldp = _fetch_entity_raw('teachers', tid, 'teacher_id', monday)
        periods = []
        for b in get_bell_schedule():
            p = b['period']
            lessons = {}
            for wd in week_dates:
                l = ldp.get(wd['date'], {}).get(p)
                lessons[wd['date']] = f"{l['subject'] or ''}\n{l['groups'] or ''}\n{l['classroom'] or ''}" if l else ''
            periods.append({**b, 'lessons': lessons})
        return week_dates, periods

    elif schedule_type == 'classroom':
        cid = entity_id
        if not cid:
            logger.warning("Export classroom: no id provided, fallback to name lookup for '%s'", name)
            conn = get_db()
            row = conn.execute(
                "SELECT id FROM classrooms_list WHERE REPLACE(name, ' ', '') LIKE REPLACE(?, ' ', '') || '%'",
                (name,)
            ).fetchone()
            conn.close()
            if not row:
                return build_week_dates(monday), []
            cid = row['id']
        logger.info("Export classroom: id=%d", cid)
        week_dates, ldp = _fetch_entity_raw('classrooms_list', cid, 'classroom_id', monday)
        periods = []
        for b in get_bell_schedule():
            p = b['period']
            lessons = {}
            for wd in week_dates:
                l = ldp.get(wd['date'], {}).get(p)
                lessons[wd['date']] = f"{l['subject'] or ''}\n{l['teacher'] or ''}\n{l['groups'] or ''}" if l else ''
            periods.append({**b, 'lessons': lessons})
        return week_dates, periods

    return build_week_dates(monday), []


def _export_excel(week_dates, periods, title):
    from openpyxl import Workbook
    from openpyxl.utils import get_column_letter
    from openpyxl.styles import Font, PatternFill, Alignment, Border, Side

    wb = Workbook()
    ws = wb.active
    ws.title = 'Расписание'

    thin = Side(style='thin', color='999999')
    border = Border(left=thin, right=thin, top=thin, bottom=thin)
    header_font = Font(name='Arial', bold=True, size=11)
    header_fill = PatternFill(start_color='D9E2F3', end_color='D9E2F3', fill_type='solid')
    cell_font = Font(name='Arial', size=10)
    wrap = Alignment(wrap_text=True, vertical='top')

    row = 1
    ws.merge_cells(start_row=row, start_column=1, end_row=row, end_column=len(week_dates) + 1)
    title_cell = ws.cell(row=row, column=1, value=title)
    title_cell.font = Font(name='Arial', bold=True, size=14)
    row += 1

    ws.cell(row=row, column=1, value='Пара').font = header_font
    ws.cell(row=row, column=1).fill = header_fill
    ws.cell(row=row, column=1).border = border
    ws.cell(row=row, column=1).alignment = Alignment(horizontal='center')

    for i, wd in enumerate(week_dates):
        d = datetime.strptime(wd['date'], '%Y-%m-%d')
        header_text = f"{wd['day_name']}\n{d.day}.{d.month}"
        cell = ws.cell(row=row, column=i + 2, value=header_text)
        cell.font = header_font
        cell.fill = header_fill
        cell.border = border
        cell.alignment = Alignment(horizontal='center', wrap_text=True)
    row += 1

    last_shift = 0
    for p in periods:
        if p['shift'] != last_shift:
            last_shift = p['shift']
            ws.merge_cells(start_row=row, start_column=1, end_row=row, end_column=len(week_dates) + 1)
            shift_cell = ws.cell(row=row, column=1, value=SHIFT_LABELS[p['shift']])
            shift_cell.font = Font(name='Arial', bold=True, size=10, color='1A5FB4')
            shift_cell.fill = PatternFill(start_color='E0ECFF', end_color='E0ECFF', fill_type='solid')
            shift_cell.alignment = Alignment(horizontal='center')
            for c in range(1, len(week_dates) + 2):
                ws.cell(row=row, column=c).border = border
            row += 1

        time_cell = ws.cell(row=row, column=1, value=f"{p['period']} пара\n{p['start']}–{p['end']}")
        time_cell.font = cell_font
        time_cell.border = border
        time_cell.alignment = Alignment(horizontal='center', vertical='top')

        for i, wd in enumerate(week_dates):
            cell = ws.cell(row=row, column=i + 2, value=p['lessons'].get(wd['date'], ''))
            cell.font = cell_font
            cell.border = border
            cell.alignment = wrap
        row += 1

    ws.column_dimensions['A'].width = 16
    for i in range(len(week_dates)):
        letter = get_column_letter(i + 2)
        ws.column_dimensions[letter].width = 28

    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    return buf


def _export_word(week_dates, periods, title):
    from docx import Document
    from docx.shared import Pt, RGBColor
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    from docx.enum.table import WD_TABLE_ALIGNMENT

    doc = Document()

    style = doc.styles['Normal']
    style.font.name = 'Arial'
    style.font.size = Pt(10)
    style.element.rPr.rFonts.set('{http://schemas.openxmlformats.org/wordprocessingml/2006/main}ascii', 'Arial')
    style.element.rPr.rFonts.set('{http://schemas.openxmlformats.org/wordprocessingml/2006/main}hAnsi', 'Arial')

    heading = doc.add_paragraph()
    heading.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = heading.add_run(title)
    run.bold = True
    run.font.size = Pt(16)

    num_cols = len(week_dates) + 1
    table = doc.add_table(rows=1, cols=num_cols)
    table.style = 'Table Grid'
    table.alignment = WD_TABLE_ALIGNMENT.CENTER

    hdr = table.rows[0]
    hdr.cells[0].text = 'Пара'
    for p in hdr.cells[0].paragraphs:
        for r in p.runs:
            r.bold = True
    for i, wd in enumerate(week_dates):
        d = datetime.strptime(wd['date'], '%Y-%m-%d')
        cell = hdr.cells[i + 1]
        cell.text = f"{wd['day_name']}\n{d.day}.{d.month}"
        for p in cell.paragraphs:
            p.alignment = WD_ALIGN_PARAGRAPH.CENTER
            for r in p.runs:
                r.bold = True

    last_shift = 0
    for p in periods:
        if p['shift'] != last_shift:
            last_shift = p['shift']
            shift_row = table.add_row()
            shift_row.cells[0].merge(shift_row.cells[len(week_dates)])
            shift_row.cells[0].text = SHIFT_LABELS[p['shift']]
            for para in shift_row.cells[0].paragraphs:
                para.alignment = WD_ALIGN_PARAGRAPH.CENTER
                for r in para.runs:
                    r.bold = True
                    r.font.color.rgb = RGBColor(0x1A, 0x5F, 0xB4)

        row_cells = table.add_row().cells
        row_cells[0].text = f"{p['period']} пара\n{p['start']}–{p['end']}"
        for i, wd in enumerate(week_dates):
            row_cells[i + 1].text = p['lessons'].get(wd['date'], '')

    for row in table.rows:
        for cell in row.cells:
            for para in cell.paragraphs:
                para.paragraph_format.space_before = Pt(2)
                para.paragraph_format.space_after = Pt(2)
                for run in para.runs:
                    run.font.size = Pt(9)

    buf = io.BytesIO()
    doc.save(buf)
    buf.seek(0)
    return buf


def _pdf_safe(value):
    """Экранировать текст для reportlab Paragraph: его содержимое парсится как XML,
    поэтому `&`, `<`, `>` из названий предметов/групп ломают разметку
    (а `<текст>` молча проглатывается как неизвестный тег)."""
    return _xml_escape('' if value is None else str(value))


def _resolve_pdf_font():
    """Найти TTF с поддержкой кириллицы.

    Порядок: PDF_FONT_PATH из окружения → Windows-шрифты → Linux (DejaVu/Liberation/Noto).
    Если ничего не найдено — (None, None) и WARNING: Helvetica кириллицу не покажет.
    """
    font_path = (os.environ.get('PDF_FONT_PATH') or '').strip()
    if not font_path:
        candidates = [
            r'C:\Windows\Fonts\arial.ttf',
            r'C:\Windows\Fonts\segoeui.ttf',
            r'C:\Windows\Fonts\tahoma.ttf',
            '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf',
            '/usr/share/fonts/TTF/DejaVuSans.ttf',
            '/usr/share/fonts/dejavu/DejaVuSans.ttf',
            '/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf',
            '/usr/share/fonts/truetype/noto/NotoSans-Regular.ttf',
        ]
        for candidate in candidates:
            if os.path.exists(candidate):
                font_path = candidate
                break

    if not font_path or not os.path.exists(font_path):
        logger.warning(
            "PDF: не найден шрифт с поддержкой кириллицы — используется Helvetica, "
            "русский текст в PDF может отобразиться некорректно. Задайте PDF_FONT_PATH."
        )
        return None, None

    bold_path = (os.environ.get('PDF_FONT_BOLD_PATH') or '').strip()
    if not bold_path:
        for suffix in ('bd.ttf', '-Bold.ttf', 'Bold.ttf'):
            candidate = font_path[:-4] + suffix
            if os.path.exists(candidate):
                bold_path = candidate
                break
    if not bold_path or not os.path.exists(bold_path):
        bold_path = font_path
    return font_path, bold_path


def _export_pdf(week_dates, periods, title):
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib import colors
    from reportlab.lib.units import cm
    from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont

    font_path, font_bold_path = _resolve_pdf_font()
    if font_path:
        pdfmetrics.registerFont(TTFont('Tahoma', font_path))
        pdfmetrics.registerFont(TTFont('Tahoma-Bold', font_bold_path or font_path))
    font_name = 'Tahoma' if font_path else 'Helvetica'
    font_bold_name = 'Tahoma-Bold' if font_path else 'Helvetica-Bold'

    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=landscape(A4), leftMargin=1.5*cm, rightMargin=1.5*cm,
                            topMargin=1.5*cm, bottomMargin=1.5*cm)

    style_title = ParagraphStyle('Title', fontName=font_bold_name, fontSize=14, alignment=1, spaceAfter=12)
    style_cell = ParagraphStyle('Cell', fontName=font_name, fontSize=8, leading=10)
    style_header = ParagraphStyle('Header', fontName=font_bold_name, fontSize=9, leading=11, alignment=1)

    elements = []
    elements.append(Paragraph(_pdf_safe(title), style_title))
    elements.append(Spacer(1, 0.3*cm))

    header_dates = [(wd['day_name'], datetime.strptime(wd['date'], '%Y-%m-%d')) for wd in week_dates]
    data = [['Пара'] + [f"{_pdf_safe(name)}\n{d.day}.{d.month}" for name, d in header_dates]]

    last_shift = 0
    for p in periods:
        if p['shift'] != last_shift:
            last_shift = p['shift']
            shift_row_data = [Paragraph(f"<b>{_pdf_safe(SHIFT_LABELS[p['shift']])}</b>", style_header)]
            shift_row_data += [''] * len(week_dates)
            data.append(shift_row_data)
        row = [Paragraph(
            f"<b>{p['period']} пара</b><br/>{_pdf_safe(p['start'])}–{_pdf_safe(p['end'])}",
            style_cell,
        )]
        for wd in week_dates:
            text = p['lessons'].get(wd['date'], '')
            row.append(Paragraph(_pdf_safe(text).replace('\n', '<br/>'), style_cell) if text else '')
        data.append(row)

    col_widths = [2.5*cm] + [max(2.2*cm, (landscape(A4)[0] - 4*cm - 2.5*cm) / len(week_dates))] * len(week_dates)
    t = Table(data, colWidths=col_widths, repeatRows=1)

    style_cmds = [
        ('FONTNAME', (0, 0), (-1, 0), font_bold_name),
        ('FONTNAME', (0, 1), (-1, -1), font_name),
        ('FONTSIZE', (0, 0), (-1, 0), 9),
        ('FONTSIZE', (0, 1), (-1, -1), 8),
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#D9E2F3')),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#999999')),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('ALIGN', (0, 0), (-1, 0), 'CENTER'),
        ('TOPPADDING', (0, 0), (-1, -1), 3),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
        ('LEFTPADDING', (0, 0), (-1, -1), 4),
        ('RIGHTPADDING', (0, 0), (-1, -1), 4),
    ]

    row_idx = 1
    last_shift = 0
    for p in periods:
        if p['shift'] != last_shift:
            last_shift = p['shift']
            style_cmds.append(('SPAN', (0, row_idx), (-1, row_idx)))
            style_cmds.append(('BACKGROUND', (0, row_idx), (-1, row_idx), colors.HexColor('#E0ECFF')))
            style_cmds.append(('ALIGN', (0, row_idx), (-1, row_idx), 'CENTER'))
            row_idx += 1
        row_idx += 1

    t.setStyle(TableStyle(style_cmds))
    elements.append(t)
    doc.build(elements)
    buf.seek(0)
    return buf


def _check_dependencies(conn, table, item_id):
    """Check if a reference entity is used in active lessons."""
    col_map = {'subjects': 'subject_id', 'teachers': 'teacher_id', 'classrooms_list': 'classroom_id', 'groups_list': 'group_id'}
    col = col_map.get(table)
    if not col:
        return None
    row = conn.execute(f"SELECT COUNT(*) FROM lessons WHERE {col} = ? AND deleted_at IS NULL", (item_id,)).fetchone()[0]
    return row if row else None


def generic_crud(table, label, order_by='id', extra_fields=None):
    extra_fields = extra_fields or []

    def make_get(label, table, order_by):
        def get_items():
            """Список записей справочника
            ---
            responses:
              200:
                description: Массив объектов справочника
            """
            cache_key = f'ref_list_{table}'
            cached = refs_cache.get(cache_key)
            if cached is not None:
                return jsonify(_public_ref(table, cached))
            conn = get_db()
            items = conn.execute(f"SELECT * FROM {table} WHERE deleted_at IS NULL ORDER BY {order_by}").fetchall()
            conn.close()
            result = [dict(i) for i in items]
            refs_cache.set(cache_key, result)
            return jsonify(_public_ref(table, result))
        get_items.__name__ = f'get_{label}'
        return get_items

    def make_create(label, table, extra_fields):
        @login_required
        def create_item():
            """Создать запись в справочнике
            ---
            parameters:
              - in: body
                name: body
                required: true
                schema:
                  type: object
                  properties:
                    name:
                      type: string
                      description: Название
            responses:
              201:
                description: Созданная запись
              400:
                description: Name required
              409:
                description: Уже существует
            """
            data = request.get_json()
            name = data.get('name', '').strip()
            if not name:
                return jsonify({"error": "Name required"}), 400
            conn = get_db()
            extra_cols = []
            extra_vals = []
            for f in extra_fields:
                if f in data:
                    extra_cols.append(f)
                    extra_vals.append(data[f])
            if table == 'teachers' and 'phone' in data:
                phone = (data['phone'] or '').strip()
                if phone and conn.execute("SELECT 1 FROM teachers WHERE phone = ? AND deleted_at IS NULL", (phone,)).fetchone():
                    conn.close()
                    return jsonify({"error": "Этот номер телефона уже используется другим преподавателем"}), 409
            cols_sql = ', '.join(['name'] + extra_cols)
            placeholders = ', '.join(['?'] * (1 + len(extra_cols)))
            try:
                cursor = conn.execute(f'INSERT INTO {table} ({cols_sql}) VALUES ({placeholders})', [name] + extra_vals)
                conn.commit()
                item_id = cursor.lastrowid
            except sqlite3.IntegrityError:
                conn.close()
                return jsonify({"error": "Уже существует"}), 409
            conn.close()
            result = {"id": item_id, "name": name}
            for f in extra_fields:
                result[f] = data.get(f)
            refs_cache.invalidate_prefix(f'ref_list_{table}')
            return jsonify(result), 201
        create_item.__name__ = f'create_{label}'
        return create_item

    def make_update(label, table, extra_fields):
        @login_required
        def update_item(item_id):
            """Обновить запись в справочнике
            ---
            parameters:
              - in: path
                name: item_id
                type: integer
                required: true
              - in: body
                name: body
                required: true
                schema:
                  type: object
                  properties:
                    name:
                      type: string
            responses:
              200:
                description: success
              400:
                description: Name required
            """
            data = request.get_json()
            name = data.get('name', '').strip()
            if not name:
                return jsonify({"error": "Name required"}), 400
            conn = get_db()
            if table == 'teachers' and 'phone' in data:
                phone = (data['phone'] or '').strip()
                if phone and conn.execute("SELECT 1 FROM teachers WHERE phone = ? AND id != ? AND deleted_at IS NULL", (phone, item_id)).fetchone():
                    conn.close()
                    return jsonify({"error": "Этот номер телефона уже используется другим преподавателем"}), 409
            set_parts = ['name = ?']
            params = [name]
            for f in extra_fields:
                if f in data:
                    set_parts.append(f'{f} = ?')
                    params.append(data[f])
            params.append(item_id)
            conn.execute(f'UPDATE {table} SET {", ".join(set_parts)} WHERE id = ?', params)
            conn.commit()
            conn.close()
            refs_cache.invalidate_prefix(f'ref_list_{table}')
            return jsonify({"success": True})
        update_item.__name__ = f'update_{label}'
        return update_item

    def make_delete(label, table):
        @login_required
        def delete_item(item_id):
            """Мягкое удаление записи из справочника
            ---
            responses:
              200:
                description: success (установлен deleted_at)
              409:
                description: Запись используется в расписании
            """
            conn = get_db()
            count = _check_dependencies(conn, table, item_id)
            if count:
                conn.close()
                labels = {'subjects': 'Предмет', 'teachers': 'Преподаватель', 'classrooms_list': 'Аудитория', 'groups_list': 'Группа'}
                name = labels.get(table, 'Запись')
                return jsonify({"error": f"{name} используется в {count} уроках. Удалите уроки перед удалением {name.lower()}."}), 409
            conn.execute(f"UPDATE {table} SET deleted_at = datetime('now') WHERE id = ? AND deleted_at IS NULL", (item_id,))
            conn.commit()
            conn.close()
            refs_cache.invalidate_prefix(f'ref_list_{table}')
            return jsonify({"success": True})
        delete_item.__name__ = f'delete_{label}'
        return delete_item

    bp.add_url_rule(f'/api/{label}', f'get_{label}', make_get(label, table, order_by), methods=['GET'])
    bp.add_url_rule(f'/api/{label}', f'create_{label}', make_create(label, table, extra_fields), methods=['POST'])
    bp.add_url_rule(f'/api/{label}/<int:item_id>', f'update_{label}', make_update(label, table, extra_fields), methods=['PUT'])
    bp.add_url_rule(f'/api/{label}/<int:item_id>', f'delete_{label}', make_delete(label, table), methods=['DELETE'])


@bp.route('/api/curriculum', methods=['GET'])
@login_required
def get_curriculum():
    group_id = request.args.get('group_id', type=int)
    specialty_id = request.args.get('specialty_id', type=int)
    conn = get_db()
    query = '''SELECT c.*, s.name AS subject_name, t.name AS teacher_name, sp.name AS specialty_name, sp.code AS specialty_code
               FROM curriculum c
               LEFT JOIN subjects s ON c.subject_id = s.id
               LEFT JOIN teachers t ON c.teacher_id = t.id
               LEFT JOIN specialties sp ON c.specialty_id = sp.id'''
    params = []
    where = []
    if group_id:
        where.append('c.group_id = ?')
        params.append(group_id)
    if specialty_id:
        where.append('c.specialty_id = ?')
        params.append(specialty_id)
    if where:
        query += ' WHERE ' + ' AND '.join(where)
    query += ' ORDER BY c.semester, s.name'
    rows = conn.execute(query, params).fetchall()
    conn.close()
    return jsonify([dict(r) for r in rows])


@bp.route('/api/curriculum/progress', methods=['GET'])
@login_required
def curriculum_progress():
    """Progress & pace tracking for a group's semester plan (plan vs actual)."""
    from math import ceil
    group_id = request.args.get('group_id', type=int)
    semester = request.args.get('semester', type=int, default=1)
    current_week = request.args.get('current_week', type=int, default=1)
    total_weeks = request.args.get('total_weeks', type=int, default=16)
    if not group_id:
        return jsonify({"error": "group_id required"}), 400
    if total_weeks <= 0:
        return jsonify({"error": "total_weeks must be positive"}), 400
    conn = get_db()
    rows = conn.execute('''
        SELECT c.*, s.name AS subject_name, t.name AS teacher_name
        FROM curriculum c
        LEFT JOIN subjects s ON c.subject_id = s.id
        LEFT JOIN teachers t ON c.teacher_id = t.id
        WHERE c.group_id = ? AND c.semester = ?
        ORDER BY s.name
    ''', (group_id, semester)).fetchall()
    subjects = []
    for r in rows:
        plan_pairs = max(1, ceil((r['total_hours'] * 1.0) / ((r['weeks_in_semester'] or 18) * 2)))
        total_pairs = plan_pairs * (r['weeks_in_semester'] or 18)
        expected = round((total_pairs / total_weeks) * current_week)
        subjects.append({
            'subject_id': r['subject_id'],
            'name': r['subject_name'] or f"Предмет {r['subject_id']}",
            'teacher_name': r['teacher_name'],
            'plan_pairs': total_pairs,
            'actual_pairs': 0,
            'expected_pairs': expected,
            'percentage': 0,
            'status': 'success',
            'delta_pace': 0,
        })
    # Compute actual pairs properly (subject-aware), percentage and status
    for s in subjects:
        actual = conn.execute('''
            SELECT COUNT(*) FROM lessons l
            JOIN schedule_days sd ON l.day_id = sd.id
            WHERE l.group_id = ? AND l.subject_id = ?
              AND l.deleted_at IS NULL AND sd.deleted_at IS NULL
        ''', (group_id, s['subject_id'])).fetchone()[0]
        s['actual_pairs'] = actual
        s['percentage'] = round((actual / s['plan_pairs']) * 100, 1) if s['plan_pairs'] else 0
        delta = actual - s['expected_pairs']
        s['delta_pace'] = delta
        if actual > s['plan_pairs']:
            s['status'] = 'danger'
        elif abs(delta) <= 1:
            s['status'] = 'success'
        elif delta >= -4:
            s['status'] = 'warning'
        else:
            s['status'] = 'danger'
    conn.close()
    return jsonify({
        'group_id': group_id,
        'semester': semester,
        'current_week': current_week,
        'total_weeks': total_weeks,
        'subjects': subjects,
    })


@bp.route('/api/curriculum', methods=['POST'])
@login_required
def create_curriculum():
    data = request.get_json()
    group_id = data.get('group_id')
    subject_id = data.get('subject_id')
    teacher_id = data.get('teacher_id')
    semester = data.get('semester', 1)
    total_hours = data.get('total_hours', 72)
    weeks_in_semester = data.get('weeks_in_semester', 18)
    if not group_id or not subject_id:
        return jsonify({"error": "group_id and subject_id required"}), 400
    conn = get_db()
    specialty_id = _validated_specialty_id(conn, data.get('specialty_id'))
    cycle = (data.get('cycle') or '').strip() or None
    control_form = (data.get('control_form') or '').strip() or None
    try:
        cursor = conn.execute(
            'INSERT INTO curriculum (group_id, subject_id, teacher_id, semester, total_hours, weeks_in_semester, specialty_id, cycle, control_form) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)',
            (group_id, subject_id, teacher_id, semester, total_hours, weeks_in_semester, specialty_id, cycle, control_form)
        )
        conn.commit()
        item_id = cursor.lastrowid
    except sqlite3.IntegrityError:
        conn.close()
        return jsonify({"error": "Этот предмет уже есть в учебном плане группы"}), 409
    conn.close()
    return jsonify({"id": item_id}), 201


@bp.route('/api/curriculum/apply-specialty-plan', methods=['POST'])
@login_required
def apply_specialty_plan():
    """Скопировать дисциплины и часы из плана специальности группы на текущий семестр.

    Дисциплины берутся из уже существующих записей curriculum других групп той же
    специальности (specialty_id совпадает), что даёт шаблон плана специальности.
    ---
    parameters:
      - in: body
        name: body
        required: true
        schema:
          type: object
          properties:
            group_id:
              type: integer
            semester:
              type: integer
    responses:
      200:
        description: Объект с created, skipped, semester
      400:
        description: group_id required, группа без специальности или план не найден
    """
    group_id = request.args.get('group_id', type=int) or request.get_json().get('group_id')
    semester = request.get_json().get('semester', 1)
    if not group_id:
        return jsonify({"error": "group_id required"}), 400
    conn = get_db()
    group = conn.execute("SELECT id, name, specialty_id FROM groups_list WHERE id = ? AND deleted_at IS NULL", (group_id,)).fetchone()
    if not group:
        conn.close()
        return jsonify({"error": "Группа не найдена"}), 404
    if not group['specialty_id']:
        conn.close()
        return jsonify({"error": "У группы не задана специальность. Сначала назначьте специальность группе."}), 400
    # Шаблон плана специальности: берём план любой группы той же специальности
    template = conn.execute('''
        SELECT c.subject_id, c.teacher_id, c.total_hours, c.weeks_in_semester,
               c.specialty_id, c.cycle, c.control_form, s.name AS subject_name
        FROM curriculum c
        JOIN subjects s ON c.subject_id = s.id
        WHERE c.group_id IN (SELECT id FROM groups_list WHERE specialty_id = ? AND deleted_at IS NULL)
          AND c.semester = ?
        GROUP BY c.subject_id, c.semester
        ORDER BY s.name
    ''', (group['specialty_id'], semester)).fetchall()
    if not template:
        conn.close()
        refs_cache.invalidate_prefix('ref_curriculum')
        return jsonify({"error": f"Нет готового плана специальности для {semester} семестра. Добавьте дисциплины в план хотя бы одной группы этой специальности."}), 400
    created = 0
    skipped = 0
    for row in template:
        existing = conn.execute(
            "SELECT 1 FROM curriculum WHERE group_id = ? AND subject_id = ? AND semester = ?",
            (group_id, row['subject_id'], semester)
        ).fetchone()
        if existing:
            skipped += 1
            continue
        conn.execute(
            'INSERT INTO curriculum (group_id, subject_id, teacher_id, semester, total_hours, weeks_in_semester, specialty_id, cycle, control_form) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)',
            (group_id, row['subject_id'], row['teacher_id'], semester, row['total_hours'], row['weeks_in_semester'], row['specialty_id'], row['cycle'], row['control_form'])
        )
        created += 1
    conn.commit()
    conn.close()
    refs_cache.invalidate_prefix('ref_curriculum')
    return jsonify({"created": created, "skipped": skipped, "semester": semester})


@bp.route('/api/curriculum/<int:item_id>', methods=['DELETE'])
@login_required
def delete_curriculum(item_id):
    conn = get_db()
    conn.execute('DELETE FROM curriculum WHERE id = ?', (item_id,))
    conn.commit()
    conn.close()
    return jsonify({"success": True})


@bp.route('/api/schedule/workload/<int:group_id>')
def workload(group_id):
    """Get workload analysis for a group's current week."""
    monday = request.args.get('monday', '')
    if not monday:
        return jsonify({"error": "monday required"}), 400
    week_dates = [d['date'] for d in build_week_dates(monday)]
    conn = get_db()
    placeholders = ','.join('?' * len(week_dates))
    lessons = conn.execute(
        f"SELECT sd.date, l.period FROM lessons l JOIN schedule_days sd ON l.day_id = sd.id WHERE sd.date IN ({placeholders}) AND sd.group_name = (SELECT name FROM groups_list WHERE id = ?) AND l.deleted_at IS NULL AND sd.deleted_at IS NULL",
        week_dates + [group_id]
    ).fetchall()

    lessons_by_date = {}
    for l in lessons:
        lessons_by_date.setdefault(l['date'], []).append(l)

    validation = validate_weekly_load(lessons_by_date)

    cur = conn.execute(
        "SELECT c.*, s.name AS subject_name FROM curriculum c LEFT JOIN subjects s ON c.subject_id = s.id WHERE c.group_id = ? ORDER BY c.semester",
        (group_id,)
    ).fetchall()
    plan = []
    for c in cur:
        plan.append({
            'subject_name': c['subject_name'],
            'total_hours': c['total_hours'],
            'weekly': weekly_pairs(c['total_hours'], c['weeks_in_semester']),
        })

    conn.close()
    return jsonify({
        'workload': validation,
        'plan': plan,
    })


@bp.route('/')
def index():
    """Главная страница — SPA
    ---
    responses:
      200:
        description: HTML-шаблон страницы
    """
    return render_template('index.html')


@bp.route('/api/bell-schedule')
def bell_schedule():
    """Расписание звонков (актуальное: из settings или базовое)
    ---
    responses:
      200:
        description: Массив периодов с полями period, start, end, shift
    """
    return jsonify(get_bell_schedule())


@bp.route('/api/admin/bell-schedule')
@login_required
def admin_bell_schedule_get():
    """Текущая схема звонков и список готовых пресетов (только для администратора)
    ---
    responses:
      200:
        description: Объект с полями schedule и presets
      401:
        description: Требуется авторизация
    """
    presets = [
        {'id': key, 'name': val['name'], 'description': val.get('description', ''), 'schedule': val['schedule']}
        for key, val in BELL_SCHEDULE_PRESETS.items()
    ]
    return jsonify({'schedule': get_bell_schedule(), 'presets': presets})


@bp.route('/api/admin/bell-schedule', methods=['PUT'])
@login_required
def admin_bell_schedule_put():
    """Сохранить обновлённую схему звонков
    ---
    parameters:
      - in: body
        name: body
        required: true
        schema:
          type: object
          properties:
            schedule:
              type: array
              description: Слоты {period, start, end, shift}
    responses:
      200:
        description: Объект с полем schedule (нормализованный массив)
      400:
        description: Неверный формат времени или структуры
      401:
        description: Требуется авторизация
    """
    data = request.get_json(silent=True) or {}
    slots = data.get('schedule')
    if not isinstance(slots, list):
        return jsonify({"error": "Не передан массив звонков"}), 400
    try:
        norm = save_bell_schedule(slots)
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    return jsonify({"success": True, "schedule": norm})


@bp.route('/api/auth/csrf-token')
def csrf_token():
    """Получить CSRF-токен для защиты форм
    ---
    responses:
      200:
        description: Объект с csrf_token
    """
    if 'csrf_token' not in session:
        session['csrf_token'] = secrets.token_hex(32)
    return jsonify({"csrf_token": session['csrf_token']})


@bp.route('/api/auth/login', methods=['POST'])
def login():
    """Вход администратора по паролю
    ---
    parameters:
      - in: body
        name: body
        required: true
        schema:
          type: object
          properties:
            password:
              type: string
              description: Пароль из .env
    responses:
      200:
        description: Успешный вход, возвращает csrf_token
      401:
        description: Неверный пароль
      429:
        description: Слишком много попыток
    """
    _clean_login_attempts()
    data = request.get_json()
    ip = request.remote_addr
    now = time.time()

    with _login_lock:
        attempts = _login_attempts.get(ip, [])
        attempts = [t for t in attempts if now - t < SETTINGS['login_rate_window']]
        _login_attempts[ip] = attempts

        if len(attempts) >= SETTINGS['login_rate_limit']:
            return jsonify({"error": "Too many attempts. Try later."}), 429

        if data.get('password') and check_password_hash(ADMIN_PASSWORD_HASH, data['password']):
            session['is_admin'] = True
            session['csrf_token'] = secrets.token_hex(32)
            _login_attempts.pop(ip, None)
            return jsonify({"success": True, "csrf_token": session['csrf_token']})

        attempts.append(now)
        _login_attempts[ip] = attempts
    return jsonify({"error": "Wrong password"}), 401


@bp.route('/api/auth/logout', methods=['POST'])
def logout():
    """Выход администратора
    ---
    responses:
      200:
        description: Успешный выход
    """
    session.pop('is_admin', None)
    return jsonify({"success": True})


@bp.route('/api/auth/check')
def check_auth():
    """Проверить статус администратора
    ---
    responses:
      200:
        description: Объект с полем is_admin (bool)
    """
    return jsonify({"is_admin": session.get('is_admin', False)})


@bp.route('/api/settings', methods=['GET'])
@login_required
def get_settings():
    """Получить все настройки
    ---
    responses:
      200:
        description: Объект ключ-значение
    """
    conn = get_db()
    rows = conn.execute('SELECT key, value FROM settings ORDER BY key').fetchall()
    conn.close()
    return jsonify({r['key']: r['value'] for r in rows})


@bp.route('/api/settings/<key>', methods=['PUT'])
@login_required
def update_setting(key):
    """Обновить настройку
    ---
    parameters:
      - in: path
        name: key
        required: true
        type: string
      - in: body
        name: body
        required: true
        schema:
          type: object
          properties:
            value:
              type: string
    responses:
      200:
        description: success
      400:
        description: Неверное значение
      403:
        description: Неверный ключ
    """
    allowed = ('session_lifetime', 'login_rate_limit', 'login_rate_window', 'backup_retention_days')
    if key not in allowed:
        return jsonify({"error": "Unknown setting"}), 403
    data = request.get_json()
    val = data.get('value', '').strip()
    if not val.isdigit() or int(val) < 1:
        return jsonify({"error": "Значение должно быть положительным целым числом"}), 400
    try:
        val = apply_setting(key, val)
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    if key == 'session_lifetime':
        from flask import current_app
        current_app.permanent_session_lifetime = timedelta(seconds=SETTINGS[key])
    return jsonify({"success": True})


@bp.route('/api/check_date')
def check_date():
    """Проверить, является ли дата исключённой (праздник/выходной)
    ---
    parameters:
      - in: query
        name: date
        type: string
        required: true
        description: Дата в формате YYYY-MM-DD
    responses:
      200:
        description: Объект с полями date и excluded (bool)
      400:
        description: date обязателен
    """
    date_str = request.args.get('date', '')
    if not date_str:
        return jsonify({"error": "date parameter required (YYYY-MM-DD)"}), 400
    conn = get_db()
    excluded = is_date_excluded(conn, date_str)
    conn.close()
    return jsonify({"date": date_str, "excluded": excluded})


@bp.route('/api/days', methods=['GET'])
def get_days():
    """Список дней расписания
    ---
    parameters:
      - in: query
        name: group
        type: string
        required: false
        description: Фильтр по группе
    responses:
      200:
        description: Массив дней с вложенными уроками
    """
    group_name = request.args.get('group', '')
    conn = get_db()
    query = 'SELECT * FROM schedule_days WHERE deleted_at IS NULL'
    params = []
    if group_name:
        query += ' AND group_name = ?'
        params.append(group_name)
    query += ' ORDER BY sort_order'
    days = conn.execute(query, params).fetchall()
    result = []
    for day in days:
        lessons = conn.execute(
            LESSON_SELECT + ' WHERE l.day_id = ? AND l.deleted_at IS NULL ORDER BY l.period',
            (day['id'],)
        ).fetchall()
        result.append({
            "id": day['id'],
            "day_name": day['day_name'],
            "date": day['date'],
            "sort_order": day['sort_order'],
            "group_name": day['group_name'],
            "lessons": [dict(l) for l in lessons]
        })
    conn.close()
    return jsonify(result)


@bp.route('/api/teacher-schedule', methods=['GET'])
def get_teacher_schedule():
    """Всё расписание преподавателя (все даты)
    ---
    parameters:
      - in: query
        name: teacher_id
        type: integer
        required: true
        description: ID преподавателя
    responses:
      200:
        description: Массив дней с уроками
    """
    raw_teacher_id = request.args.get('teacher_id', '')
    if not raw_teacher_id:
        return jsonify([])
    teacher_id = _int_param(raw_teacher_id)
    if teacher_id is None:
        return jsonify({"error": "Некорректный формат даты или ID"}), 400
    conn = get_db()
    lessons = conn.execute(
        LESSON_SELECT_WITH_DAY + ' WHERE l.teacher_id = ? AND l.subject_id IS NOT NULL AND l.deleted_at IS NULL ORDER BY sd.sort_order, l.period',
        (teacher_id,)
    ).fetchall()
    conn.close()

    days_map = {}
    for l in lessons:
        day_key = (l['day_name'], l['date'])
        if day_key not in days_map:
            days_map[day_key] = {
                'day_name': l['day_name'],
                'date': l['date'],
                'lessons': []
            }
        days_map[day_key]['lessons'].append({
            'id': l['id'],
            'period': l['period'],
            'subject': l['subject_name'],
            'teacher': l['teacher_name'],
            'classroom': l['classroom_name'],
            'groups': l['group_name'] or l['groups']
        })

    return jsonify(list(days_map.values()))


@bp.route('/api/teachers-with-schedule')
def teachers_with_schedule():
    """Список преподавателей, у которых есть уроки
    ---
    responses:
      200:
        description: Массив объектов {id, name}
    """
    conn = get_db()
    rows = conn.execute('''
        SELECT DISTINCT t.id, t.name
        FROM lessons l
        JOIN teachers t ON l.teacher_id = t.id
        JOIN schedule_days sd ON l.day_id = sd.id
        WHERE l.subject_id IS NOT NULL AND l.deleted_at IS NULL
        ORDER BY t.name
    ''').fetchall()
    conn.close()
    return jsonify([{'id': r['id'], 'name': r['name']} for r in rows])


@bp.route('/api/validate', methods=['POST'])
@login_required
def validate_lesson():
    """Проверить конфликты урока (учитель, аудитория, дубликат)
    ---
    parameters:
      - in: body
        name: body
        required: true
        schema:
          type: object
          properties:
            day_id:
              type: integer
            period:
              type: integer
            teacher_id:
              type: integer
            classroom_id:
              type: integer
            subject_id:
              type: integer
            group_id:
              type: integer
            exclude_lesson_id:
              type: integer
    responses:
      200:
        description: Объект с warnings и blocking
    """
    data = request.get_json()
    day_id = data.get('day_id')
    period = data.get('period')
    teacher_id = data.get('teacher_id')
    classroom_id = data.get('classroom_id')
    subject_id = data.get('subject_id')
    group_id = data.get('group_id')
    subgroup = data.get('subgroup')
    exclude_lesson_id = data.get('exclude_lesson_id')

    if not day_id or not period:
        return jsonify({"warnings": [], "blocking": False})

    conn = get_db()
    day = conn.execute('SELECT * FROM schedule_days WHERE id = ? AND deleted_at IS NULL', (day_id,)).fetchall()
    if not day:
        conn.close()
        return jsonify({"warnings": [], "blocking": False})
    day = day[0]

    conflicts = _validate_lesson_slot(conn, day, period, subject_id=subject_id,
                                      teacher_id=teacher_id, classroom_id=classroom_id,
                                      group_id=group_id, subgroup=subgroup,
                                      exclude_id=exclude_lesson_id)

    warnings = []

    if conflicts['teacher']:
        existing = conflicts['teacher']
        tname = existing[0]['teacher_name'] or ''
        groups = [e['group_name'] or e['groups'] for e in existing]
        warnings.append({
            "type": "teacher_conflict",
            "message": f"Преподаватель {tname} уже занят в {existing[0]['day_name']} на {period}-й паре (группа: {', '.join(groups)})"
        })

    if conflicts['classroom']:
        existing = conflicts['classroom']
        cname = existing[0]['classroom_name'] or ''
        groups = [e['group_name'] or e['groups'] for e in existing]
        warnings.append({
            "type": "classroom_conflict",
            "message": f"Аудитория {cname} уже занята в {existing[0]['day_name']} на {period}-й паре (группа: {', '.join(groups)})"
        })

    if conflicts['duplicate']:
        warnings.append({
            "type": "duplicate",
            "message": "Такой же урок уже добавлен в этот день на эту пару"
        })

    conn.close()
    return jsonify({"warnings": warnings, "blocking": bool(warnings)})


@bp.route('/api/week', methods=['DELETE'])
@login_required
def delete_week():
    """Удалить всю неделю (мягкое удаление)
    ---
    responses:
      200:
        description: Объект с days_deleted
      400:
        description: monday, target_type, target_id обязательны
    """
    monday = request.args.get('monday', '')
    target_type = request.args.get('target_type', '')
    target_id = request.args.get('target_id', '')
    if not monday or not target_type or not target_id:
        return jsonify({"error": "monday, target_type, target_id required"}), 400
    if target_type not in ('group', 'teacher', 'classroom'):
        return jsonify({"error": "target_type must be group, teacher, or classroom"}), 400
    if _parse_date(monday) is None:
        return _bad_monday()
    week_dates = [d['date'] for d in build_week_dates(monday)]
    placeholders = ','.join('?' * len(week_dates))
    warning = None
    groups_affected = 0
    conn = get_db()
    try:
        conn.execute('BEGIN IMMEDIATE')
        if target_type == 'group':
            cur_lessons = conn.execute(
                f"UPDATE lessons SET deleted_at = datetime('now') WHERE deleted_at IS NULL AND COALESCE(is_special_event, 0) = 0 AND day_id IN (SELECT id FROM schedule_days WHERE date IN ({placeholders}) AND group_name = ?)",
                week_dates + [target_id]
            )
            cur_days = conn.execute(
                f"UPDATE schedule_days SET deleted_at = datetime('now') WHERE deleted_at IS NULL AND date IN ({placeholders}) AND group_name = ?",
                week_dates + [target_id]
            )
            # rowcount считает только реально изменённые сейчас строки; прежние
            # COUNT(*) по deleted_at IS NOT NULL включали удалённое ранее.
            affected = max(cur_days.rowcount or 0, 0)
            pairs_affected = max(cur_lessons.rowcount or 0, 0)
        else:
            col = 'teacher_id' if target_type == 'teacher' else 'classroom_id'
            target_pk = _int_param(target_id)
            if target_pk is None:
                conn.rollback()
                return jsonify({"error": "target_id must be an integer"}), 400
            rows = conn.execute(
                f"SELECT l.id, l.day_id, l.group_id FROM lessons l "
                f"JOIN schedule_days sd ON l.day_id = sd.id "
                f"WHERE l.deleted_at IS NULL AND sd.deleted_at IS NULL "
                f"AND l.{col} = ? AND sd.date IN ({placeholders})",
                [target_pk] + week_dates
            ).fetchall()
            ids = [r['id'] for r in rows]
            if ids:
                conn.executemany(
                    "UPDATE lessons SET deleted_at = datetime('now') WHERE id = ? AND deleted_at IS NULL",
                    [(lesson_id,) for lesson_id in ids]
                )
            affected = len({r['day_id'] for r in rows})
            pairs_affected = len(ids)
            groups_affected = len({r['group_id'] for r in rows if r['group_id'] is not None})
            if ids:
                subject = 'преподаватель' if target_type == 'teacher' else 'аудитория'
                warning = (
                    f"Удалены пары всех групп, где задействован {subject} "
                    f"(затронуто групп: {groups_affected}). Расписание других групп изменилось."
                )
        conn.commit()
    finally:
        conn.close()
    payload = {"success": True, "days_deleted": affected, "pairs_deleted": pairs_affected}
    if target_type != 'group':
        payload["groups_affected"] = groups_affected
        if warning:
            payload["warning"] = warning
    return jsonify(payload)


@bp.route('/api/week/restore', methods=['POST'])
@login_required
def restore_week():
    """Восстановить удалённую неделю
    ---
    responses:
      200:
        description: Объект с days_restored
      400:
        description: monday, target_type, target_id обязательны
    """
    monday = request.args.get('monday', '')
    target_type = request.args.get('target_type', '')
    target_id = request.args.get('target_id', '')
    if not monday or not target_type or not target_id:
        return jsonify({"error": "monday, target_type, target_id required"}), 400
    if target_type not in ('group', 'teacher', 'classroom'):
        return jsonify({"error": "target_type must be group, teacher, or classroom"}), 400
    week_dates = [d['date'] for d in build_week_dates(monday)]
    placeholders = ','.join('?' * len(week_dates))
    conn = get_db()
    try:
        conn.execute('BEGIN IMMEDIATE')
        if target_type == 'group':
            conn.execute(
                f"UPDATE lessons SET deleted_at = NULL WHERE deleted_at IS NOT NULL AND day_id IN (SELECT id FROM schedule_days WHERE date IN ({placeholders}) AND group_name = ?)",
                week_dates + [target_id]
            )
            conn.execute(
                f"UPDATE schedule_days SET deleted_at = NULL WHERE deleted_at IS NOT NULL AND date IN ({placeholders}) AND group_name = ?",
                week_dates + [target_id]
            )
            affected = conn.execute(
                f"SELECT COUNT(*) FROM schedule_days WHERE date IN ({placeholders}) AND group_name = ? AND deleted_at IS NULL",
                week_dates + [target_id]
            ).fetchone()[0]
        else:
            col = 'teacher_id' if target_type == 'teacher' else 'classroom_id'
            conn.execute(
                f"UPDATE lessons SET deleted_at = NULL WHERE deleted_at IS NOT NULL AND {col} = ? AND day_id IN (SELECT id FROM schedule_days WHERE date IN ({placeholders}))",
                [int(target_id)] + week_dates
            )
            affected = conn.execute(
                f"SELECT COUNT(*) FROM lessons WHERE deleted_at IS NULL AND {col} = ? AND day_id IN (SELECT id FROM schedule_days WHERE date IN ({placeholders}))",
                [int(target_id)] + week_dates
            ).fetchone()[0]
        conn.commit()
    finally:
        conn.close()
    return jsonify({"success": True, "days_restored": affected})


@bp.route('/api/validate-week', methods=['POST'])
@login_required
def validate_week():
    """Проверить, есть ли уже расписание на указанные даты
    ---
    parameters:
      - in: body
        name: body
        required: true
        schema:
          type: object
          properties:
            group_name:
              type: string
            dates:
              type: array
              items:
                type: string
    responses:
      200:
        description: Объект с ok (bool) и warnings
    """
    data = request.get_json()
    group_name = data.get('group_name', '')
    dates = data.get('dates', [])

    if not group_name or not dates:
        return jsonify({"ok": True, "warnings": []})

    conn = get_db()
    warnings = []

    placeholders = ','.join('?' * len(dates))
    existing = conn.execute(
        f'SELECT * FROM schedule_days WHERE group_name = ? AND deleted_at IS NULL AND date IN ({placeholders})',
        [group_name] + dates
    ).fetchall()

    if existing:
        existing_dates = [e['date'] for e in existing]
        warnings.append({
            "type": "week_exists",
            "message": f"У группы {group_name} уже есть расписание на даты: {', '.join(existing_dates)}. Удалите старую неделю перед добавлением новой."
        })

    conn.close()
    return jsonify({"ok": len(warnings) == 0, "warnings": warnings})


@bp.route('/api/days', methods=['POST'])
@login_required
def create_day():
    """Создать один день расписания
    ---
    parameters:
      - in: body
        name: body
        required: true
        schema:
          type: object
          properties:
            day_name:
              type: string
            date:
              type: string
            group_name:
              type: string
    responses:
      201:
        description: Созданный день
    """
    data = request.get_json(silent=True) or {}
    day_name = (data.get('day_name') or '').strip()
    date_str = (data.get('date') or '').strip()
    if not day_name or not date_str:
        return jsonify({"error": "day_name и date обязательны"}), 400
    if _parse_date(date_str) is None:
        return jsonify({"error": "date must be YYYY-MM-DD"}), 400
    conn = get_db()
    max_order = conn.execute('SELECT COALESCE(MAX(sort_order), -1) FROM schedule_days').fetchone()[0]
    cursor = conn.execute(
        'INSERT INTO schedule_days (day_name, date, sort_order, group_name, is_published) VALUES (?, ?, ?, ?, 0)',
        (day_name, date_str, max_order + 1, data.get('group_name', ''))
    )
    day_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return jsonify({"id": day_id}), 201


@bp.route('/api/days/batch', methods=['POST'])
@login_required
def create_days_batch():
    """Создать неделю расписания (6 дней)
    ---
    parameters:
      - in: body
        name: body
        required: true
        schema:
          type: object
          properties:
            days:
              type: array
              items:
                type: object
                properties:
                  day_name:
                    type: string
                  date:
                    type: string
                  group_name:
                    type: string
    responses:
      201:
        description: Массив ids созданных дней
      400:
        description: Нет дней
      409:
        description: Уже есть расписание на эти даты
    """
    data = request.get_json(silent=True) or {}
    days = data.get('days', [])
    if not days:
        return jsonify({"error": "Нет дней"}), 400
    for idx, d in enumerate(days):
        if not isinstance(d, dict) or not d.get('day_name') or not d.get('date'):
            return jsonify({"error": f"День №{idx + 1}: нужны day_name и date"}), 400
        if _parse_date(d['date']) is None:
            return jsonify({"error": f"День №{idx + 1}: date must be YYYY-MM-DD"}), 400

    group_name = days[0].get('group_name', '')
    dates = [d['date'] for d in days]

    conn = get_db()

    placeholders = ','.join('?' * len(dates))
    existing = conn.execute(
        f'SELECT date FROM schedule_days WHERE group_name = ? AND deleted_at IS NULL AND date IN ({placeholders})',
        [group_name] + dates
    ).fetchall()

    if existing:
        existing_dates = [e['date'] for e in existing]
        conn.close()
        return jsonify({
            "error": f"У группы {group_name} уже есть расписание на даты: {', '.join(existing_dates)}"
        }), 409

    max_order = conn.execute('SELECT COALESCE(MAX(sort_order), -1) FROM schedule_days').fetchone()[0]
    ids = []
    for i, d in enumerate(days):
        cursor = conn.execute(
            'INSERT INTO schedule_days (day_name, date, sort_order, group_name, is_published) VALUES (?, ?, ?, ?, 0)',
            (d['day_name'], d['date'], max_order + 1 + i, d.get('group_name', ''))
        )
        ids.append(cursor.lastrowid)
    conn.commit()
    conn.close()
    return jsonify({"ids": ids}), 201


@bp.route('/api/days/<int:day_id>', methods=['PUT'])
@login_required
def update_day(day_id):
    """Обновить день расписания
    ---
    parameters:
      - in: path
        name: day_id
        type: integer
        required: true
      - in: body
        name: body
        required: true
        schema:
          type: object
          properties:
            day_name:
              type: string
            date:
              type: string
    responses:
      200:
        description: success
    """
    data = request.get_json(silent=True) or {}
    day_name = (data.get('day_name') or '').strip()
    date_str = (data.get('date') or '').strip()
    if not day_name or not date_str:
        return jsonify({"error": "day_name и date обязательны"}), 400
    if _parse_date(date_str) is None:
        return jsonify({"error": "date must be YYYY-MM-DD"}), 400
    conn = get_db()
    conn.execute(
        'UPDATE schedule_days SET day_name = ?, date = ? WHERE id = ?',
        (day_name, date_str, day_id)
    )
    conn.commit()
    conn.close()
    return jsonify({"success": True})


@bp.route('/api/days/<int:day_id>', methods=['DELETE'])
@login_required
def delete_day(day_id):
    """Мягкое удаление дня и его уроков
    ---
    parameters:
      - in: path
        name: day_id
        type: integer
        required: true
    responses:
      200:
        description: success
    """
    conn = get_db()
    conn.execute("UPDATE schedule_days SET deleted_at = datetime('now') WHERE id = ? AND deleted_at IS NULL", (day_id,))
    # deleted_at IS NULL обязателен: без него повторное удаление дня перезаписывало
    # время удаления у уже удалённых уроков, и корзина/автоочистка считали их заново.
    conn.execute("UPDATE lessons SET deleted_at = datetime('now') WHERE day_id = ? AND deleted_at IS NULL AND COALESCE(is_special_event, 0) = 0", (day_id,))
    conn.commit()
    conn.close()
    return jsonify({"success": True})


@bp.route('/api/days/<int:day_id>/toggle-publish', methods=['POST'])
@login_required
def toggle_day_publish(day_id):
    """Переключить статус публикации дня (день ↔ черновик)
    ---
    parameters:
      - in: path
        name: day_id
        type: integer
        required: true
    responses:
      200:
        description: {id, is_published} — новый статус
      404:
        description: День не найден
    """
    conn = get_db()
    row = conn.execute(
        "SELECT is_published FROM schedule_days WHERE id = ? AND deleted_at IS NULL", (day_id,)
    ).fetchone()
    if not row:
        conn.close()
        return jsonify({"error": "День не найден"}), 404
    new_status = 0 if row['is_published'] else 1
    conn.execute("UPDATE schedule_days SET is_published = ? WHERE id = ?", (new_status, day_id))
    conn.commit()
    conn.close()
    return jsonify({"id": day_id, "is_published": bool(new_status)})


@bp.route('/api/week/publish', methods=['POST'])
@login_required
def publish_week():
    """Установить статус публикации всей недели группы
    ---
    parameters:
      - in: body
        name: body
        required: true
        schema:
          type: object
          properties:
            group_name:
              type: string
            monday:
              type: string
            is_published:
              type: boolean
    responses:
      200:
        description: {success, is_published}
      400:
        description: Не указана группа или дата
    """
    data = request.get_json() or {}
    group_name = (data.get('group_name') or '').strip()
    monday = (data.get('monday') or '').strip()
    if not group_name or not monday:
        return jsonify({"error": "Не указаны group_name и monday"}), 400
    is_published = 1 if data.get('is_published', True) else 0
    week_dates = build_week_dates(monday)
    dates = [d['date'] for d in week_dates]
    conn = get_db()
    placeholders = ','.join('?' * len(dates))
    conn.execute(
        f"UPDATE schedule_days SET is_published = ? "
        f"WHERE group_name = ? AND deleted_at IS NULL AND date IN ({placeholders})",
        [is_published, group_name] + dates
    )
    conn.commit()
    conn.close()
    message = "Неделя опубликована" if is_published else "Неделя переведена в черновик"
    return jsonify({"success": True, "message": message, "is_published": is_published})


@bp.route('/api/days/<int:day_id>/restore', methods=['POST'])
@login_required
def restore_day(day_id):
    """Восстановить мягко удалённый день
    ---
    parameters:
      - in: path
        name: day_id
        type: integer
        required: true
    responses:
      200:
        description: success
      409:
        description: Конфликт при восстановлении
    """
    conn = get_db()
    day = conn.execute("SELECT id, day_name, date, group_name FROM schedule_days WHERE id = ?", (day_id,)).fetchone()
    if not day:
        conn.close()
        return jsonify({"error": "Day not found"}), 404

    try:
        conn.execute('BEGIN IMMEDIATE')
        lessons = conn.execute(
            "SELECT id, day_id, period, teacher_id, classroom_id, subject_id, group_id, subgroup FROM lessons WHERE day_id = ? AND deleted_at IS NOT NULL",
            (day_id,)
        ).fetchall()

        conflict_warnings = []
        for l in lessons:
            ws, blocking = _validate_lesson_data(conn, l['day_id'], l['period'], l['teacher_id'], l['classroom_id'],
                                                  subject_id=l['subject_id'], group_id=l['group_id'], subgroup=l['subgroup'],
                                                  skip_day_check=True)
            if blocking:
                conflict_warnings.extend(ws)

        if conflict_warnings:
            conn.rollback()
            conn.close()
            return jsonify({"error": "Конфликт при восстановлении дня", "warnings": conflict_warnings}), 409

        conn.execute("UPDATE schedule_days SET deleted_at = NULL WHERE id = ?", (day_id,))
        conn.execute("UPDATE lessons SET deleted_at = NULL WHERE day_id = ? AND deleted_at IS NOT NULL", (day_id,))
        conn.commit()
    finally:
        conn.close()

    return jsonify({
        "success": True,
        "item": {
            "type": "day",
            "day_name": day['day_name'],
            "date": day['date'],
            "group_name": day['group_name'],
        }
    })


@bp.route('/api/days/<int:day_id>/lessons', methods=['POST'])
@login_required
def create_lesson(day_id):
    """Создать урок в дне расписания
    ---
    parameters:
      - in: path
        name: day_id
        type: integer
        required: true
      - in: body
        name: body
        required: true
        schema:
          type: object
          properties:
            period:
              type: integer
            subject_id:
              type: integer
            teacher_id:
              type: integer
            classroom_id:
              type: integer
            group_id:
              type: integer
            subgroup:
              type: integer
    responses:
      201:
        description: Созданный урок
      400:
        description: Invalid period
      409:
        description: Conflict detected
    """
    data = request.get_json()
    conn = get_db()
    try:
        conn.execute('BEGIN IMMEDIATE')

        teacher_id = data.get('teacher_id')
        classroom_id = data.get('classroom_id')
        subject_id = data.get('subject_id')
        period = data.get('period')
        if not period or period not in range(1, 9):
            conn.rollback()
            return jsonify({"error": "Invalid period (must be 1-8)"}), 400
        group_id = data.get('group_id')
        subgroup = data.get('subgroup')
        is_substitution = bool(data.get('is_substitution', False))
        original_teacher_id = data.get('original_teacher_id')
        substitution_reason = data.get('substitution_reason')
        classroom_id_2 = data.get('classroom_id_2')
        custom_start_time = (data.get('custom_start_time') or None)
        custom_end_time = (data.get('custom_end_time') or None)
        event_type = (data.get('event_type') or None)
        is_special_event = _auto_special_event(conn, subject_id, data.get('is_special_event'))
        if custom_start_time:
            is_special_event = 1

        warnings, blocking = _validate_lesson_data(conn, day_id, period, teacher_id, classroom_id, subject_id, group_id=group_id, subgroup=subgroup)
        if blocking:
            conn.rollback()
            return jsonify({"error": "Conflict detected", "warnings": warnings}), 409

        cursor = conn.execute(
            'INSERT INTO lessons (day_id, period, subject_id, teacher_id, classroom_id, classroom_id_2, group_id, subgroup, is_substitution, original_teacher_id, substitution_reason, is_special_event, custom_start_time, custom_end_time, event_type) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)',
            (day_id, period, subject_id, teacher_id, classroom_id, classroom_id_2, group_id, subgroup, int(is_substitution), original_teacher_id, substitution_reason, is_special_event, custom_start_time, custom_end_time, event_type)
        )
        lesson_id = cursor.lastrowid
        conn.commit()
        return jsonify({"id": lesson_id}), 201
    finally:
        conn.close()


@bp.route('/api/lessons/<int:lesson_id>', methods=['PUT'])
@login_required
def update_lesson(lesson_id):
    """Обновить урок (сохраняет историю изменений)
    ---
    parameters:
      - in: path
        name: lesson_id
        type: integer
        required: true
      - in: body
        name: body
        required: true
        schema:
          type: object
          properties:
            day_id:
              type: integer
            period:
              type: integer
            subject_id:
              type: integer
            teacher_id:
              type: integer
            classroom_id:
              type: integer
            group_id:
              type: integer
    responses:
      200:
        description: success
      404:
        description: Lesson not found
      409:
        description: Conflict detected
    """
    data = request.get_json()
    conn = get_db()
    try:
        conn.execute('BEGIN IMMEDIATE')

        existing = conn.execute('SELECT * FROM lessons WHERE id = ? AND deleted_at IS NULL', (lesson_id,)).fetchone()
        if not existing:
            conn.rollback()
            return jsonify({"error": "Lesson not found"}), 404

        def _field(name):
            """Значение из тела, если оно там есть; иначе — текущее (поддержка частичного PUT).

            Раньше отсутствующие в теле поля записывались как NULL: запрос «только
            day_id/period» (drag-and-drop) обнулял предмет, преподавателя и аудиторию.
            """
            return data[name] if name in data else existing[name]

        teacher_id = _field('teacher_id')
        classroom_id = _field('classroom_id')
        subject_id = _field('subject_id')
        group_id = _field('group_id')
        subgroup = _field('subgroup')
        day_id = data.get('day_id', existing['day_id'])
        period = data.get('period', existing['period'])
        is_substitution = bool(_field('is_substitution'))
        original_teacher_id = _field('original_teacher_id')
        substitution_reason = _field('substitution_reason')
        classroom_id_2 = _field('classroom_id_2')
        custom_start_time = _field('custom_start_time')
        custom_end_time = _field('custom_end_time')
        event_type = _field('event_type')
        is_special_event = _auto_special_event(conn, subject_id, _field('is_special_event'))
        if custom_start_time and not is_special_event:
            is_special_event = 1

        if not day_id or not period or period not in range(1, 9):
            conn.rollback()
            return jsonify({"error": "Invalid day_id or period (period must be 1-8)"}), 400

        target_day = conn.execute(
            'SELECT id FROM schedule_days WHERE id = ? AND deleted_at IS NULL', (day_id,)
        ).fetchone()
        if not target_day:
            conn.rollback()
            return jsonify({"error": "Day not found"}), 404

        warnings, blocking = _validate_lesson_data(conn, day_id, period, teacher_id, classroom_id, subject_id, exclude_id=lesson_id, group_id=group_id, subgroup=subgroup)
        if blocking:
            conn.rollback()
            return jsonify({"error": "Conflict detected", "warnings": warnings}), 409

        conn.execute(
            'INSERT INTO lesson_history (lesson_id, old_subject_id, old_teacher_id, old_classroom_id, old_group_id, old_subgroup) VALUES (?, ?, ?, ?, ?, ?)',
            (lesson_id, existing['subject_id'], existing['teacher_id'], existing['classroom_id'], existing['group_id'], existing['subgroup'])
        )

        conn.execute(
            'UPDATE lessons SET day_id = ?, period = ?, subject_id = ?, teacher_id = ?, classroom_id = ?, classroom_id_2 = ?, group_id = ?, subgroup = ?, is_substitution = ?, original_teacher_id = ?, substitution_reason = ?, is_special_event = ?, custom_start_time = ?, custom_end_time = ?, event_type = ? WHERE id = ?',
            (day_id, period, subject_id, teacher_id, classroom_id, classroom_id_2, group_id, subgroup,
             int(is_substitution),
             original_teacher_id,
             substitution_reason,
             is_special_event,
             custom_start_time,
             custom_end_time,
             event_type,
             lesson_id)
        )
        conn.commit()
        return jsonify({"success": True})
    finally:
        conn.close()


@bp.route('/api/lessons/<int:lesson_id>', methods=['DELETE'])
@login_required
def delete_lesson(lesson_id):
    """Мягкое удаление урока
    ---
    parameters:
      - in: path
        name: lesson_id
        type: integer
        required: true
    responses:
      200:
        description: success
    """
    conn = get_db()
    lesson = conn.execute(LESSON_SELECT + ' WHERE l.id = ? AND l.deleted_at IS NULL', (lesson_id,)).fetchone()
    if not lesson:
        conn.close()
        return jsonify({"error": "Lesson not found"}), 404

    conn.execute(
        "INSERT INTO lesson_history (lesson_id, old_subject_id, old_teacher_id, old_classroom_id, old_group_id, old_subgroup) VALUES (?, ?, ?, ?, ?, ?)",
        (lesson_id, lesson['subject_id'], lesson['teacher_id'], lesson['classroom_id'], lesson['group_id'], lesson['subgroup'])
    )
    conn.execute("UPDATE lessons SET deleted_at = datetime('now') WHERE id = ?", (lesson_id,))
    conn.commit()
    conn.close()
    return jsonify({"success": True})


@bp.route('/api/lessons/<int:lesson_id>/restore', methods=['POST'])
@login_required
def restore_lesson(lesson_id):
    """Восстановить мягко удалённый урок
    ---
    parameters:
      - in: path
        name: lesson_id
        type: integer
        required: true
    responses:
      200:
        description: success
      409:
        description: Конфликт при восстановлении
    """
    conn = get_db()
    lesson = conn.execute(LESSON_SELECT_WITH_DAY + ' WHERE l.id = ?', (lesson_id,)).fetchone()
    if not lesson:
        conn.close()
        return jsonify({"error": "Lesson not found"}), 404

    day_id = lesson['day_id']
    period = lesson['period']
    teacher_id = lesson['teacher_id']
    classroom_id = lesson['classroom_id']
    subject_id = lesson['subject_id']
    group_id = lesson['group_id']
    subgroup = lesson['subgroup']

    # День мог уехать в корзину: восстановленный урок стал бы «невидимым»
    # (активен, но нигде не отображается). Требуем сначала восстановить день.
    day_row = conn.execute(
        'SELECT deleted_at FROM schedule_days WHERE id = ?', (day_id,)
    ).fetchone()
    if not day_row:
        conn.close()
        return jsonify({"error": "День урока не найден"}), 404
    if day_row['deleted_at'] is not None:
        conn.close()
        return jsonify({
            "error": "День этого урока удалён. Сначала восстановите день из корзины.",
            "warnings": ["День урока находится в корзине"],
        }), 409

    warnings, blocking = _validate_lesson_data(conn, day_id, period, teacher_id, classroom_id, subject_id=subject_id, group_id=group_id, subgroup=subgroup)
    if blocking:
        conn.close()
        return jsonify({"error": "Конфликт при восстановлении", "warnings": warnings}), 409

    conn.execute("UPDATE lessons SET deleted_at = NULL WHERE id = ?", (lesson_id,))
    conn.commit()
    conn.close()
    return jsonify({
        "success": True,
        "item": {
            "type": "lesson",
            "subject_name": lesson['subject_name'],
            "teacher_name": lesson['teacher_name'],
            "day_name": lesson['day_name'],
            "date": lesson['date'],
            "period": lesson['period'],
            "group_name": lesson['group_name'],
        }
    })


@bp.route('/api/trash')
@login_required
def get_trash():
    """Корзина — мягко удалённые дни и уроки за последние {TRASH_RETENTION_DAYS} дней
    ---
    responses:
      200:
        description: Объект с массивами days и lessons
    """
    conn = get_db()
    retention_param = f'-{TRASH_RETENTION_DAYS} days'
    deleted_days = conn.execute('''
        SELECT d.id, d.day_name, d.date, d.group_name, d.deleted_at,
               'День' AS type_label
        FROM schedule_days d
        WHERE d.deleted_at IS NOT NULL AND d.deleted_at >= datetime('now', ?)
        ORDER BY d.deleted_at DESC
    ''', (retention_param,)).fetchall()
    deleted_lessons = conn.execute(
        "SELECT l.id, l.period, l.deleted_at, sd.day_name, sd.date, sd.group_name,"
        " s.name AS subject_name, t.name AS teacher_name, c.name AS classroom_name,"
        " CASE WHEN l.subgroup IS NOT NULL THEN gl.name || ' (' || l.subgroup || ')' ELSE gl.name END AS groups,"
        " 'Урок' AS type_label"
        " FROM lessons l"
        " JOIN schedule_days sd ON l.day_id = sd.id"
        " LEFT JOIN teachers t ON l.teacher_id = t.id"
        " LEFT JOIN subjects s ON l.subject_id = s.id"
        " LEFT JOIN classrooms_list c ON l.classroom_id = c.id"
        " LEFT JOIN groups_list gl ON l.group_id = gl.id"
        " WHERE l.deleted_at IS NOT NULL AND l.deleted_at >= datetime('now', ?) ORDER BY l.deleted_at DESC",
        (retention_param,)
    ).fetchall()
    deleted_refs = {}
    type_labels = {'subjects': 'Предмет', 'teachers': 'Преподаватель', 'classrooms': 'Аудитория', 'groups': 'Группа', 'specialties': 'Специальность'}
    for table, label in [('subjects', 'subjects'), ('teachers', 'teachers'), ('classrooms_list', 'classrooms'), ('groups_list', 'groups'), ('specialties', 'specialties')]:
        rows = conn.execute(f"SELECT id, name, deleted_at, '{type_labels[label]}' AS type_label FROM {table} WHERE deleted_at IS NOT NULL AND deleted_at >= datetime('now', ?) ORDER BY deleted_at DESC", (retention_param,)).fetchall()
        deleted_refs[label] = [dict(r) for r in rows]
    conn.close()
    return jsonify({
        "days": [dict(d) for d in deleted_days],
        "lessons": [dict(l) for l in deleted_lessons],
        **deleted_refs,
    })


@bp.route('/api/classrooms-with-schedule')
def classrooms_with_schedule():
    """Список аудиторий, в которых есть занятия
    ---
    responses:
      200:
        description: Массив объектов {id, name}
    """
    conn = get_db()
    rows = conn.execute('''
        SELECT DISTINCT c.id, c.name
        FROM lessons l
        JOIN classrooms_list c ON l.classroom_id = c.id
        JOIN schedule_days sd ON l.day_id = sd.id
        WHERE l.subject_id IS NOT NULL AND l.deleted_at IS NULL
        ORDER BY CAST(c.name AS INTEGER), c.name
    ''').fetchall()
    conn.close()
    return jsonify([{'id': r['id'], 'name': r['name']} for r in rows])


@bp.route('/api/schedule-table')
def schedule_table():
    """Расписание группы на неделю
    ---
    parameters:
      - in: query
        name: group
        type: string
        required: true
        description: Название группы
      - in: query
        name: monday
        type: string
        required: true
        description: Дата понедельника (YYYY-MM-DD)
    responses:
      200:
        description: Объект с days (массив дней) и periods (массив пар с уроками)
    """
    group_name = request.args.get('group', '')
    monday = request.args.get('monday', '')
    if not group_name or not monday:
        return jsonify({'days': [], 'periods': []})
    if _parse_date(monday) is None:
        return _bad_monday()

    is_admin = bool(session.get('is_admin'))
    week_dates, lessons_by_date = _fetch_group_raw(group_name, monday, published_only=not is_admin)

    periods = []
    for b in get_bell_schedule():
        p = b['period']
        lessons = {}
        for wd in week_dates:
            d = wd['date']
            if d in lessons_by_date and p in lessons_by_date[d]:
                raw_list = lessons_by_date[d][p]
                lessons[d] = [{
                    'id': l['id'], 'subject': l['subject_name'], 'teacher': l['teacher_name'],
                    'classroom': l['classroom_name'], 'classroom_2': l['classroom_2_name'],
                    'is_special_event': bool(l['is_special_event']), 'groups': l['groups'],
                    'custom_start_time': l['custom_start_time'], 'custom_end_time': l['custom_end_time'],
                    'event_type': l['event_type'],
                    'day_id': l['day_id'],
                    'subject_id': l['subject_id'], 'teacher_id': l['teacher_id'],
                    'classroom_id': l['classroom_id'],
                    'group_id': l['group_id'], 'subgroup': l['subgroup']
                } for l in raw_list]
            else:
                lessons[d] = []
        periods.append({**b, 'lessons': lessons})

    return jsonify({'days': week_dates, 'periods': periods, 'week_exists': bool(lessons_by_date)})


@bp.route('/api/teacher-schedule-table')
def teacher_schedule_table():
    """Расписание преподавателя на неделю
    ---
    parameters:
      - in: query
        name: teacher_id
        type: integer
        required: true
        description: ID преподавателя
      - in: query
        name: monday
        type: string
        required: true
        description: Дата понедельника (YYYY-MM-DD)
    responses:
      200:
        description: Объект с days и periods
    """
    teacher_id = request.args.get('teacher_id', '')
    monday = request.args.get('monday', '')
    if not teacher_id or not monday:
        return jsonify({'days': [], 'periods': []})
    teacher_id = _int_param(teacher_id)
    if teacher_id is None:
        return jsonify({"error": "Некорректный формат даты или ID"}), 400
    if _parse_date(monday) is None:
        return _bad_monday()

    week_dates, lessons_by_date_period = _fetch_entity_raw('teachers', teacher_id, 'teacher_id', monday)

    return jsonify({'days': week_dates, 'periods': _build_schedule_periods(week_dates, lessons_by_date_period)})


@bp.route('/api/classroom-schedule-table')
def classroom_schedule_table():
    """Занятость аудитории на неделю
    ---
    parameters:
      - in: query
        name: classroom_id
        type: integer
        required: true
        description: ID аудитории
      - in: query
        name: monday
        type: string
        required: true
        description: Дата понедельника (YYYY-MM-DD)
    responses:
      200:
        description: Объект с days и periods
    """
    classroom_id = request.args.get('classroom_id', '')
    monday = request.args.get('monday', '')
    if not classroom_id or not monday:
        return jsonify({'days': [], 'periods': []})
    classroom_id = _int_param(classroom_id)
    if classroom_id is None:
        return jsonify({"error": "Некорректный формат даты или ID"}), 400
    if _parse_date(monday) is None:
        return _bad_monday()

    week_dates, lessons_by_date_period = _fetch_entity_raw('classrooms_list', classroom_id, 'classroom_id', monday)

    return jsonify({'days': week_dates, 'periods': _build_schedule_periods(week_dates, lessons_by_date_period)})


generic_crud('subjects', 'subjects', 'name', extra_fields=['default_teacher_id', 'required_room_type'])
generic_crud('teachers', 'teachers', 'name', extra_fields=['phone'])
generic_crud('classrooms_list', 'classrooms', 'CAST(name AS INTEGER), name', extra_fields=['room_type'])


@bp.route('/api/specialties', methods=['GET'])
def get_specialties():
    """Список специальностей (только активные)
    ---
    responses:
      200:
        description: Массив объектов {id, code, name, qualification}
    """
    cached = refs_cache.get('ref_list_specialties')
    if cached is not None:
        return jsonify(_public_ref('specialties', cached))
    conn = get_db()
    items = conn.execute("SELECT * FROM specialties WHERE deleted_at IS NULL ORDER BY code, name").fetchall()
    conn.close()
    result = [dict(i) for i in items]
    refs_cache.set('ref_list_specialties', result)
    return jsonify(_public_ref('specialties', result))


def _auto_special_event(conn, subject_id, requested):
    """Экзамены ликвид. сессии («1.Криминалистика», «(Экз.ликвид.сесс)»)
    автоматически становятся разовыми событиями — генератор их не трогает."""
    if requested:
        return 1
    if not subject_id:
        return 0
    row = conn.execute('SELECT name FROM subjects WHERE id = ?', (subject_id,)).fetchone()
    return 1 if row and is_special_event_subject(row['name']) else 0


def _validated_shift(value):
    """Смена группы: 1 или 2; None — прежняя логика генератора (старт с 1-й пары)."""
    if value in (None, '', 0, '0'):
        return None
    try:
        shift = int(value)
    except (TypeError, ValueError):
        return None
    return shift if shift in (1, 2) else None


def _validated_specialty_id(conn, raw):
    """Валидация specialty_id: вернуть int или None (если не передан / пустой / несуществующий)."""
    if raw is None:
        return None
    try:
        sid = int(raw)
    except (TypeError, ValueError):
        return None
    if sid <= 0:
        return None
    row = conn.execute("SELECT 1 FROM specialties WHERE id = ? AND deleted_at IS NULL", (sid,)).fetchone()
    return sid if row else None


@bp.route('/api/specialties', methods=['POST'])
@login_required
def create_specialty():
    """Создать специальность
    ---
    parameters:
      - in: body
        name: body
        required: true
        schema:
          type: object
          properties:
            code:
              type: string
            name:
              type: string
            qualification:
              type: string
    responses:
      201:
        description: Созданная специальность
      400:
        description: Name required или Code required
      409:
        description: Уже существует
    """
    data = request.get_json()
    name = (data.get('name') or '').strip()
    if not name:
        return jsonify({"error": "Name required"}), 400
    code = (data.get('code') or '').strip()
    if not code:
        return jsonify({"error": "Code required"}), 400
    qualification = (data.get('qualification') or '').strip()
    conn = get_db()
    duplicate = conn.execute(
        "SELECT id FROM specialties WHERE code = ? AND name = ? AND deleted_at IS NULL",
        (code, name)
    ).fetchone()
    if duplicate:
        conn.close()
        return jsonify({"error": "Специальность с таким кодом и названием уже существует"}), 409
    try:
        cursor = conn.execute(
            "INSERT INTO specialties (code, name, qualification) VALUES (?, ?, ?)",
            (code, name, qualification)
        )
        conn.commit()
        item_id = cursor.lastrowid
    except sqlite3.IntegrityError:
        conn.close()
        return jsonify({"error": "Уже существует"}), 409
    conn.close()
    refs_cache.invalidate_prefix('ref_list_specialties')
    return jsonify({"id": item_id, "code": code, "name": name, "qualification": qualification}), 201


@bp.route('/api/specialties/<int:item_id>', methods=['PUT'])
@login_required
def update_specialty(item_id):
    """Обновить специальность
    ---
    responses:
      200:
        description: success
      400:
        description: Name required или Code required
      409:
        description: Уже существует
    """
    data = request.get_json()
    name = (data.get('name') or '').strip()
    if not name:
        return jsonify({"error": "Name required"}), 400
    code = (data.get('code') or '').strip()
    if not code:
        return jsonify({"error": "Code required"}), 400
    qualification = (data.get('qualification') or '').strip()
    conn = get_db()
    item = conn.execute("SELECT id FROM specialties WHERE id = ? AND deleted_at IS NULL", (item_id,)).fetchone()
    if not item:
        conn.close()
        return jsonify({"error": "Not found"}), 404
    duplicate = conn.execute(
        "SELECT id FROM specialties WHERE code = ? AND name = ? AND id != ? AND deleted_at IS NULL",
        (code, name, item_id)
    ).fetchone()
    if duplicate:
        conn.close()
        return jsonify({"error": "Специальность с таким кодом и названием уже существует"}), 409
    conn.execute(
        "UPDATE specialties SET code = ?, name = ?, qualification = ? WHERE id = ?",
        (code, name, qualification, item_id)
    )
    conn.commit()
    conn.close()
    refs_cache.invalidate_prefix('ref_list_specialties')
    return jsonify({"success": True})


@bp.route('/api/specialties/<int:item_id>', methods=['DELETE'])
@login_required
def delete_specialty(item_id):
    """Мягко удалить специальность
    ---
    responses:
      200:
        description: success
      409:
        description: Специальность используется группами
    """
    conn = get_db()
    used = conn.execute(
        "SELECT COUNT(*) FROM groups_list WHERE specialty_id = ? AND deleted_at IS NULL",
        (item_id,)
    ).fetchone()[0]
    if used:
        conn.close()
        return jsonify({"error": f"Специальность привязана к {used} группе(ам). Сначала отвяжите группы."}), 409
    conn.execute("UPDATE specialties SET deleted_at = datetime('now') WHERE id = ? AND deleted_at IS NULL", (item_id,))
    conn.commit()
    conn.close()
    refs_cache.invalidate_prefix('ref_list_specialties')
    return jsonify({"success": True})


def _make_restore(table, label):
    @login_required
    def restore_item(item_id):
        conn = get_db()
        item = conn.execute(f"SELECT id, name FROM {table} WHERE id = ?", (item_id,)).fetchone()
        if not item:
            conn.close()
            return jsonify({"error": "Not found"}), 404
        if table == 'teachers':
            phone = conn.execute("SELECT phone FROM teachers WHERE id = ? AND deleted_at IS NOT NULL", (item_id,)).fetchone()
            if phone and phone['phone'] and phone['phone'].strip():
                existing = conn.execute("SELECT 1 FROM teachers WHERE phone = ? AND id != ? AND deleted_at IS NULL", (phone['phone'].strip(), item_id)).fetchone()
                if existing:
                    conn.close()
                    return jsonify({"error": "Этот номер телефона уже используется другим преподавателем"}), 409
        conn.execute(f"UPDATE {table} SET deleted_at = NULL WHERE id = ?", (item_id,))
        conn.commit()
        conn.close()
        refs_cache.invalidate_prefix(f'ref_list_{table}')
        return jsonify({"success": True, "item": {"type": label, "name": item['name']}})
    restore_item.__name__ = f'restore_{label}'
    bp.add_url_rule(f'/api/{label}/<int:item_id>/restore', f'restore_{label}', restore_item, methods=['POST'])


_make_restore('subjects', 'subjects')
_make_restore('teachers', 'teachers')
_make_restore('classrooms_list', 'classrooms')
_make_restore('specialties', 'specialties')


@bp.route('/api/groups', methods=['GET'])
def get_groups():
    """Список групп
    ---
    responses:
      200:
        description: Массив групп с полями id, name, course, is_distance
    """
    cached = refs_cache.get('ref_list_groups_list')
    if cached is not None:
        return jsonify(_public_ref('groups_list', cached))
    conn = get_db()
    items = conn.execute("""
        SELECT gl.*, sp.code AS specialty_code, sp.name AS specialty_name, sp.qualification AS specialty_qualification
        FROM groups_list gl
        LEFT JOIN specialties sp ON gl.specialty_id = sp.id
        WHERE gl.deleted_at IS NULL ORDER BY gl.course, gl.name
    """).fetchall()
    conn.close()
    result = [dict(i) for i in items]
    refs_cache.set('ref_list_groups_list', result)
    return jsonify(_public_ref('groups_list', result))


@bp.route('/api/groups', methods=['POST'])
@login_required
def create_group():
    """Создать группу
    ---
    parameters:
      - in: body
        name: body
        required: true
        schema:
          type: object
          properties:
            name:
              type: string
            course:
              type: integer
            is_distance:
              type: boolean
    responses:
      201:
        description: Созданная группа
      400:
        description: Name required или группа уже существует
    """
    data = request.get_json()
    name = data.get('name', '').strip()
    if not name:
        return jsonify({"error": "Name required"}), 400
    course = data.get('course', 1)
    is_distance = 1 if data.get('is_distance') else 0
    shift = _validated_shift(data.get('shift'))
    conn = get_db()
    specialty_id = _validated_specialty_id(conn, data.get('specialty_id'))
    active = conn.execute("SELECT id FROM groups_list WHERE LOWER(name) = LOWER(?) AND deleted_at IS NULL", (name,)).fetchone()
    if active:
        conn.close()
        return jsonify({"error": "Группа с таким названием уже существует"}), 400
    deleted = conn.execute("SELECT id, course, is_distance FROM groups_list WHERE LOWER(name) = LOWER(?) AND deleted_at IS NOT NULL", (name,)).fetchone()
    if deleted:
        conn.execute("UPDATE groups_list SET deleted_at = NULL, course = ?, is_distance = ?, specialty_id = ?, shift = ? WHERE id = ?", (course, is_distance, specialty_id, shift, deleted['id']))
        conn.commit()
        conn.close()
        refs_cache.invalidate_prefix('ref_list_groups_list')
        return jsonify({"id": deleted['id'], "name": name, "course": course, "is_distance": is_distance, "shift": shift, "specialty_id": specialty_id, "restored": True}), 200
    try:
        cursor = conn.execute(
            'INSERT INTO groups_list (name, course, is_distance, specialty_id, shift) VALUES (?, ?, ?, ?, ?)',
            (name, course, is_distance, specialty_id, shift)
        )
        conn.commit()
        item_id = cursor.lastrowid
    except sqlite3.IntegrityError:
        conn.close()
        return jsonify({"error": "Уже существует"}), 409
    conn.close()
    refs_cache.invalidate_prefix('ref_list_groups_list')
    return jsonify({"id": item_id, "name": name, "course": course, "is_distance": is_distance, "shift": shift, "specialty_id": specialty_id}), 201


@bp.route('/api/groups/<int:item_id>', methods=['PUT'])
@login_required
def update_group(item_id):
    """Обновить группу
    ---
    parameters:
      - in: path
        name: item_id
        type: integer
        required: true
      - in: body
        name: body
        required: true
        schema:
          type: object
          properties:
            name:
              type: string
            course:
              type: integer
            is_distance:
              type: boolean
    responses:
      200:
        description: success
      400:
        description: Name required или дубликат
    """
    data = request.get_json()
    name = data.get('name', '').strip()
    if not name:
        return jsonify({"error": "Name required"}), 400
    course = data.get('course', 1)
    is_distance = 1 if data.get('is_distance') else 0
    shift = _validated_shift(data.get('shift'))
    conn = get_db()
    specialty_id = _validated_specialty_id(conn, data.get('specialty_id'))
    existing = conn.execute(
        "SELECT id FROM groups_list WHERE LOWER(name) = LOWER(?) AND id != ?",
        (name, item_id)
    ).fetchone()
    if existing:
        conn.close()
        return jsonify({"error": "Группа с таким названием уже существует"}), 400
    conn.execute(
        'UPDATE groups_list SET name = ?, course = ?, is_distance = ?, specialty_id = ?, shift = ? WHERE id = ?',
        (name, course, is_distance, specialty_id, shift, item_id)
    )
    conn.commit()
    conn.close()
    refs_cache.invalidate_prefix('ref_list_groups_list')
    return jsonify({"success": True})


@bp.route('/api/groups/<int:item_id>', methods=['DELETE'])
@login_required
def delete_group(item_id):
    """Удалить группу
    ---
    responses:
      200:
        description: success
      409:
        description: Группа используется в расписании
    """
    conn = get_db()
    count = _check_dependencies(conn, 'groups_list', item_id)
    if count:
        conn.close()
        return jsonify({"error": f"Группа используется в {count} уроках. Удалите уроки перед удалением группы."}), 409
    conn.execute("UPDATE groups_list SET deleted_at = datetime('now') WHERE id = ? AND deleted_at IS NULL", (item_id,))
    conn.commit()
    conn.close()
    refs_cache.invalidate_prefix('ref_list_groups_list')
    return jsonify({"success": True})


@bp.route('/api/groups/<int:item_id>/restore', methods=['POST'])
@login_required
def restore_group(item_id):
    conn = get_db()
    item = conn.execute("SELECT id, name FROM groups_list WHERE id = ?", (item_id,)).fetchone()
    if not item:
        conn.close()
        return jsonify({"error": "Not found"}), 404
    conn.execute("UPDATE groups_list SET deleted_at = NULL WHERE id = ?", (item_id,))
    conn.commit()
    conn.close()
    refs_cache.invalidate_prefix('ref_list_groups_list')
    return jsonify({"success": True, "item": {"type": "group", "name": item['name']}})


@bp.route('/api/groups/advance-courses', methods=['POST'])
@login_required
def advance_courses():
    """Перевести все группы на следующий курс (+1), удалить 4-й курс
    ---
    responses:
      200:
        description: Объект с полем deleted (количество удалённых групп)
    """
    conn = get_db()
    deleted = conn.execute("UPDATE groups_list SET deleted_at = datetime('now') WHERE course = 4 AND deleted_at IS NULL").rowcount
    conn.execute('UPDATE groups_list SET course = course + 1 WHERE course < 4 AND deleted_at IS NULL')
    conn.commit()
    conn.close()
    refs_cache.invalidate_prefix('ref_list_groups_list')
    return jsonify({"success": True, "deleted": deleted})


@bp.route('/api/export')
def export_schedule():
    """Экспорт расписания в файл (xlsx/docx/pdf)
    ---
    parameters:
      - in: query
        name: type
        type: string
        enum: [group, teacher, classroom]
        required: true
        description: Тип расписания
      - in: query
        name: name
        type: string
        required: true
        description: Название группы / имя преподавателя / номер аудитории
      - in: query
        name: id
        type: integer
        required: false
        description: ID преподавателя/аудитории (для teacher/classroom)
      - in: query
        name: monday
        type: string
        required: true
        description: Дата понедельника (YYYY-MM-DD)
      - in: query
        name: format
        type: string
        enum: [xlsx, docx, pdf]
        required: true
        description: Формат файла
    responses:
      200:
        description: Файл расписания
      400:
        description: Отсутствуют параметры или неверный формат
      404:
        description: Нет данных для экспорта
    """
    schedule_type = request.args.get('type', '')
    name = request.args.get('name', '')
    entity_id = request.args.get('id', '')
    monday = request.args.get('monday', '')
    fmt = request.args.get('format', '')

    if not all([schedule_type, name, monday, fmt]):
        return jsonify({"error": "Missing parameters"}), 400
    if fmt not in ('xlsx', 'docx', 'pdf'):
        return jsonify({"error": "Invalid format"}), 400
    if _parse_date(monday) is None:
        return _bad_monday()

    if schedule_type in ('teacher', 'classroom') and entity_id:
        try:
            entity_id = int(entity_id)
        except (ValueError, TypeError):
            entity_id = None

    week_dates, periods = _get_export_data(schedule_type, name, monday, entity_id)

    has_data = any(
        p['lessons'].get(d['date'], '') if isinstance(p['lessons'].get(d['date'], ''), str)
        else len(p['lessons'].get(d['date'], [])) > 0
        for p in periods for d in week_dates
    )
    logger.info("Export %s '%s'(id=%s) week %s: periods=%d, has_data=%s",
                schedule_type, name, entity_id, monday, len(periods), has_data)
    if not has_data:
        return jsonify({"error": "No schedule data"}), 404

    sat = datetime.strptime(week_dates[-1]['date'], '%Y-%m-%d')
    mon = datetime.strptime(week_dates[0]['date'], '%Y-%m-%d')
    date_range = f"{mon.day:02d}.{mon.month:02d}–{sat.day:02d}.{sat.month:02d}"

    type_labels = {'group': 'Группа', 'teacher': 'Преподаватель', 'classroom': 'Аудитория'}
    title = f"Расписание — {type_labels.get(schedule_type, '')} {name}, неделя {date_range}"
    safe_name = _safe_filename(f"raspisanie_{name}_{date_range}")

    if fmt == 'xlsx':
        buf = _export_excel(week_dates, periods, title)
        return send_file(buf, as_attachment=True, download_name=f"{safe_name}.xlsx",
                         mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    elif fmt == 'docx':
        buf = _export_word(week_dates, periods, title)
        return send_file(buf, as_attachment=True, download_name=f"{safe_name}.docx",
                         mimetype='application/vnd.openxmlformats-officedocument.wordprocessingml.document')
    elif fmt == 'pdf':
        buf = _export_pdf(week_dates, periods, title)
        return send_file(buf, as_attachment=True, download_name=f"{safe_name}.pdf",
                         mimetype='application/pdf')


@bp.route('/api/schedule/export/excel', endpoint='schedule_export_excel')
def schedule_export_excel():
    """Умный экспорт расписания в Excel с автоподстройкой под разрезы.
    Поддерживает group, teacher, classroom и сводный all (по всем группам).
    Переиспользует LESSON_SELECT_WITH_DAY и _fetch_entity_raw."""
    schedule_type = request.args.get('type', 'group')
    entity_id = request.args.get('id', type=int)
    start_date = request.args.get('start_date', '')
    end_date = request.args.get('end_date', '')
    # Массовая выгрузка (лист на каждую группу) — самая тяжёлая операция экспорта
    # и единственная, что отдаёт расписание всех групп сразу: только для админа.
    if schedule_type == 'all' and not session.get('is_admin'):
        return jsonify({"error": "Массовый экспорт доступен только администратору"}), 401
    if start_date and _parse_date(start_date) is None:
        return jsonify({"error": "start_date must be YYYY-MM-DD"}), 400
    if end_date and _parse_date(end_date) is None:
        return jsonify({"error": "end_date must be YYYY-MM-DD"}), 400

    from openpyxl import Workbook
    from openpyxl.utils import get_column_letter
    from openpyxl.styles import Font, PatternFill, Alignment, Border, Side

    thin = Side(style='thin', color='999999')
    border = Border(left=thin, right=thin, top=thin, bottom=thin)
    header_font = Font(name='Arial', bold=True, size=11)
    header_fill = PatternFill(start_color='D9E2F3', end_color='D9E2F3', fill_type='solid')
    cell_font = Font(name='Arial', size=10)
    wrap = Alignment(wrap_text=True, vertical='top')

    conn = get_db()
    try:
        if schedule_type == 'all':
            rows = conn.execute(
                "SELECT id, name FROM groups_list WHERE deleted_at IS NULL ORDER BY course, name"
            ).fetchall()
            entity_list = [dict(r) for r in rows] if rows else []
            if not entity_list:
                return jsonify({"error": "Нет групп для экспорта"}), 404
            if not start_date:
                from datetime import date, timedelta
                today = date.today()
                start_date = (today - timedelta(days=today.weekday())).isoformat()
            wb = Workbook()
            wb.remove(wb.active)
            for group in entity_list:
                week_dates, periods = _get_export_data('group', group['name'], start_date)
                ws = wb.create_sheet(title=_safe_filename(group['name'])[:31])
                _write_excel_sheet(ws, week_dates, periods,
                                   f"Группа {group['name']}", header_font, header_fill, cell_font, border, wrap)
            buf = io.BytesIO()
            wb.save(buf)
            buf.seek(0)
            return send_file(buf, as_attachment=True, download_name='raspisanie_vse_gruppy.xlsx',
                             mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')

        if schedule_type == 'group':
            if not entity_id:
                return jsonify({"error": "id required for group export"}), 400
            row = conn.execute(
                "SELECT name FROM groups_list WHERE id = ? AND deleted_at IS NULL", (entity_id,)
            ).fetchone()
            if not row:
                return jsonify({"error": "Group not found"}), 404
            name = row['name']
            monday = start_date or _find_nearest_monday(conn, name)
            title = f"Расписание — Группа {name}"
        elif schedule_type == 'teacher':
            if not entity_id:
                return jsonify({"error": "id required for teacher export"}), 400
            row = conn.execute(
                "SELECT name FROM teachers WHERE id = ? AND deleted_at IS NULL", (entity_id,)
            ).fetchone()
            if not row:
                return jsonify({"error": "Teacher not found"}), 404
            name = row['name']
            monday = start_date or _find_nearest_monday(conn, entity_id, 'teacher')
            title = f"Расписание — Преподаватель {name}"
        elif schedule_type == 'classroom':
            if not entity_id:
                return jsonify({"error": "id required for classroom export"}), 400
            row = conn.execute(
                "SELECT name FROM classrooms_list WHERE id = ? AND deleted_at IS NULL", (entity_id,)
            ).fetchone()
            if not row:
                return jsonify({"error": "Classroom not found"}), 404
            name = row['name']
            monday = start_date or _find_nearest_monday(conn, entity_id, 'classroom')
            title = f"Расписание — Аудитория {name}"
        else:
            return jsonify({"error": "Invalid type"}), 400

        week_dates, periods = _get_export_data(schedule_type, name, monday,
                                                entity_id=entity_id if schedule_type != 'group' else None)

        wb = Workbook()
        ws = wb.active
        ws.title = 'Расписание'
        _write_excel_sheet(ws, week_dates, periods, title, header_font, header_fill, cell_font, border, wrap)
        safe_name = _safe_filename(f"raspisanie_{name}_{week_dates[0]['date']}")
        buf = io.BytesIO()
        wb.save(buf)
        buf.seek(0)
        return send_file(buf, as_attachment=True, download_name=f"{safe_name}.xlsx",
                         mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    finally:
        conn.close()


def _find_nearest_monday(conn, entity_ref, entity_type='group'):
    """Найти ближайший понедельник, на который есть расписание для entity."""
    if entity_type == 'group':
        row = conn.execute(
            "SELECT date FROM schedule_days WHERE group_name = ? AND deleted_at IS NULL ORDER BY date DESC LIMIT 1",
            (entity_ref,)
        ).fetchone()
    elif entity_type == 'teacher':
        row = conn.execute(
            "SELECT sd.date FROM lessons l JOIN schedule_days sd ON l.day_id = sd.id "
            "WHERE l.teacher_id = ? AND l.subject_id IS NOT NULL AND l.deleted_at IS NULL AND sd.deleted_at IS NULL "
            "ORDER BY sd.date DESC LIMIT 1",
            (entity_ref,)
        ).fetchone()
    elif entity_type == 'classroom':
        row = conn.execute(
            "SELECT sd.date FROM lessons l JOIN schedule_days sd ON l.day_id = sd.id "
            "WHERE l.classroom_id = ? AND l.subject_id IS NOT NULL AND l.deleted_at IS NULL AND sd.deleted_at IS NULL "
            "ORDER BY sd.date DESC LIMIT 1",
            (entity_ref,)
        ).fetchone()
    else:
        row = None
    if row:
        from datetime import datetime, timedelta
        dt = datetime.strptime(row['date'], '%Y-%m-%d')
        monday = dt - timedelta(days=dt.weekday())
        return monday.strftime('%Y-%m-%d')
    import datetime as dt_mod
    today = dt_mod.date.today()
    monday = today - dt_mod.timedelta(days=today.weekday())
    return monday.isoformat()


def _write_excel_sheet(ws, week_dates, periods, title, header_font, header_fill, cell_font, border, wrap):
    from openpyxl.styles import Font, Alignment, PatternFill
    from openpyxl.utils import get_column_letter
    row = 1
    ws.merge_cells(start_row=row, start_column=1, end_row=row, end_column=len(week_dates) + 1)
    title_cell = ws.cell(row=row, column=1, value=title)
    title_cell.font = Font(name='Arial', bold=True, size=14)
    row += 1

    ws.cell(row=row, column=1, value='Пара').font = header_font
    ws.cell(row=row, column=1).fill = header_fill
    ws.cell(row=row, column=1).border = border
    ws.cell(row=row, column=1).alignment = Alignment(horizontal='center')

    for i, wd in enumerate(week_dates):
        d = datetime.strptime(wd['date'], '%Y-%m-%d')
        header_text = f"{wd['day_name']}\n{d.day}.{d.month}"
        cell = ws.cell(row=row, column=i + 2, value=header_text)
        cell.font = header_font
        cell.fill = header_fill
        cell.border = border
        cell.alignment = Alignment(horizontal='center', wrap_text=True)
    row += 1

    last_shift = 0
    for p in periods:
        if p['shift'] != last_shift:
            last_shift = p['shift']
            ws.merge_cells(start_row=row, start_column=1, end_row=row, end_column=len(week_dates) + 1)
            shift_cell = ws.cell(row=row, column=1, value=SHIFT_LABELS[p['shift']])
            shift_cell.font = Font(name='Arial', bold=True, size=10, color='1A5FB4')
            shift_cell.fill = PatternFill(start_color='E0ECFF', end_color='E0ECFF', fill_type='solid')
            shift_cell.alignment = Alignment(horizontal='center')
            for c in range(1, len(week_dates) + 2):
                ws.cell(row=row, column=c).border = border
            row += 1

        time_cell = ws.cell(row=row, column=1, value=f"{p['period']} пара\n{p['start']}–{p['end']}")
        time_cell.font = cell_font
        time_cell.border = border
        time_cell.alignment = Alignment(horizontal='center', vertical='top')

        for i, wd in enumerate(week_dates):
            cell = ws.cell(row=row, column=i + 2, value=p['lessons'].get(wd['date'], ''))
            cell.font = cell_font
            cell.border = border
            cell.alignment = wrap
        row += 1

    ws.column_dimensions['A'].width = 16
    for i in range(len(week_dates)):
        letter = get_column_letter(i + 2)
        ws.column_dimensions[letter].width = 28


@bp.route('/api/availability')
@login_required
def availability():
    """Свободные окна преподавателей и аудиторий
    ---
    parameters:
      - in: query
        name: monday
        type: string
        required: true
        description: Дата понедельника (YYYY-MM-DD)
      - in: query
        name: group_id
        type: integer
        required: false
        description: Фильтр по группе
    responses:
      200:
        description: Объект с days, periods, teachers, classrooms, teacher_busy, classroom_busy
      400:
        description: monday обязателен
    """
    monday = request.args.get('monday', '')
    group_id_filter = request.args.get('group_id', type=int)
    if not monday:
        return jsonify({"error": "monday required"}), 400

    week_dates = build_week_dates(monday)
    date_list = [wd['date'] for wd in week_dates]
    placeholders = ','.join('?' * len(date_list))

    conn = get_db()
    try:
        query = f'''
            SELECT l.period, sd.date, sd.day_name,
                   t.name AS teacher_name, l.teacher_id,
                   c.name AS classroom_name, l.classroom_id,
                   g.name AS group_name, l.group_id, g.course,
                   s.name AS subject_name, l.subject_id,
                   l.is_substitution, l.original_teacher_id,
                   ot.name AS original_teacher_name
            FROM lessons l
            JOIN schedule_days sd ON l.day_id = sd.id
            LEFT JOIN teachers t ON l.teacher_id = t.id AND t.deleted_at IS NULL
            LEFT JOIN teachers ot ON l.original_teacher_id = ot.id AND ot.deleted_at IS NULL
            LEFT JOIN classrooms_list c ON l.classroom_id = c.id AND c.deleted_at IS NULL
            LEFT JOIN groups_list g ON l.group_id = g.id AND g.deleted_at IS NULL
            LEFT JOIN subjects s ON l.subject_id = s.id AND s.deleted_at IS NULL
            WHERE sd.date IN ({placeholders})
              AND l.subject_id IS NOT NULL
              AND l.deleted_at IS NULL AND sd.deleted_at IS NULL
        '''
        params = date_list[:]
        if group_id_filter:
            query += ' AND l.group_id = ?'
            params.append(group_id_filter)
        lessons = conn.execute(query, params).fetchall()

        all_teachers = conn.execute('SELECT id, name FROM teachers WHERE deleted_at IS NULL ORDER BY name').fetchall()
        all_classrooms = conn.execute('SELECT id, name FROM classrooms_list WHERE deleted_at IS NULL ORDER BY CAST(name AS INTEGER), name').fetchall()
        all_groups = conn.execute('SELECT id, name, course FROM groups_list WHERE deleted_at IS NULL ORDER BY course, name').fetchall()

        teacher_busy = {}
        classroom_busy = {}
        teacher_courses = {}
        all_courses_set = set()

        for l in lessons:
            key = (l['date'], l['period'])
            t_id = l['teacher_id']
            c_id = l['classroom_id']
            course = l['course']
            info = {'group': l['group_name'], 'subject': l['subject_name'], 'teacher': l['teacher_name'], 'classroom': l['classroom_name'], 'teacher_id': t_id, 'classroom_id': c_id}
            if l['is_substitution']:
                info['is_sub'] = True
                if l['original_teacher_name']:
                    info['original_teacher'] = l['original_teacher_name']
            if t_id and l['teacher_name']:
                teacher_busy.setdefault(t_id, {})[key] = info
                teacher_courses.setdefault(t_id, set()).add(course)
                all_courses_set.add(course)
            if c_id and l['classroom_name']:
                classroom_busy.setdefault(c_id, {})[key] = info

        periods = [{'period': b['period'], 'start': b['start'], 'end': b['end']} for b in get_bell_schedule()]

        teachers_out = []
        for t in all_teachers:
            td = {'id': t['id'], 'name': t['name']}
            courses = sorted(c for c in teacher_courses.get(t['id'], []) if c is not None)
            if courses:
                td['courses'] = courses
            teachers_out.append(td)

        teacher_stats = {}
        for t in all_teachers:
            busy = teacher_busy.get(t['id'], {})
            total = len(busy)
            free = len(periods) * len(week_dates) - total
            teacher_stats[t['id']] = {'name': t['name'], 'total': total, 'free': free, 'load_pct': round(total / max(len(periods) * len(week_dates), 1) * 100, 1)}

        classroom_stats = {}
        for c in all_classrooms:
            busy = classroom_busy.get(c['id'], {})
            total = len(busy)
            free = len(periods) * len(week_dates) - total
            classroom_stats[c['id']] = {'name': c['name'], 'total': total, 'free': free, 'load_pct': round(total / max(len(periods) * len(week_dates), 1) * 100, 1)}

        group_lesson_count = {}
        for l in lessons:
            gid = l['group_id']
            gname = l['group_name']
            if gid and gname:
                group_lesson_count.setdefault(gid, {'name': gname, 'lessons': 0})['lessons'] += 1

        return jsonify({
            'days': week_dates,
            'periods': periods,
            'teachers': teachers_out,
            'classrooms': [{'id': c['id'], 'name': c['name']} for c in all_classrooms],
            'groups': [{'id': g['id'], 'name': g['name'], 'course': g['course']} for g in all_groups],
            'all_courses': sorted(c for c in all_courses_set if c is not None),
            'teacher_busy': {str(k): {f"{dk[0]}_{dk[1]}": v for dk, v in dv.items()} for k, dv in teacher_busy.items()},
            'classroom_busy': {str(k): {f"{dk[0]}_{dk[1]}": v for dk, v in dv.items()} for k, dv in classroom_busy.items()},
            'teacher_stats': teacher_stats,
            'classroom_stats': classroom_stats,
            'group_lesson_count': {str(k): v for k, v in group_lesson_count.items()},
        })
    finally:
        conn.close()





@bp.route('/api/excluded-dates', methods=['GET'])
def get_excluded_dates():
    """Список всех исключённых дат
    ---
    responses:
      200:
        description: Массив объектов {id, start_date, end_date, reason, created_at}
    """
    conn = get_db()
    rows = conn.execute('SELECT * FROM excluded_dates ORDER BY start_date DESC').fetchall()
    conn.close()
    return jsonify([dict(r) for r in rows])


@bp.route('/api/excluded-dates', methods=['POST'])
@login_required
def create_excluded_date():
    """Создать исключение даты
    ---
    parameters:
      - in: body
        name: body
        required: true
        schema:
          type: object
          properties:
            start_date:
              type: string
            end_date:
              type: string
            reason:
              type: string
    responses:
      201:
        description: Созданная запись
      400:
        description: start_date и end_date обязательны
    """
    data = request.get_json()
    start_date = (data.get('start_date') or '').strip()
    end_date = (data.get('end_date') or '').strip()
    if not start_date or not end_date:
        return jsonify({"error": "start_date and end_date required"}), 400
    reason = (data.get('reason', '') or '').strip()
    conn = get_db()
    cursor = conn.execute(
        'INSERT INTO excluded_dates (start_date, end_date, reason) VALUES (?, ?, ?)',
        (start_date, end_date, reason)
    )
    conn.commit()
    item_id = cursor.lastrowid
    conn.close()
    refs_cache.invalidate_prefix('excluded_dates')
    return jsonify({"id": item_id, "start_date": start_date, "end_date": end_date, "reason": reason}), 201


@bp.route('/api/excluded-dates/<int:item_id>', methods=['DELETE'])
@login_required
def delete_excluded_date(item_id):
    """Удалить исключение даты
    ---
    responses:
      200:
        description: success
      404:
        description: Not found
    """
    conn = get_db()
    cur = conn.execute('DELETE FROM excluded_dates WHERE id = ?', (item_id,))
    conn.commit()
    deleted = cur.rowcount
    conn.close()
    if not deleted:
        return jsonify({"error": "Not found"}), 404
    refs_cache.invalidate_prefix('excluded_dates')
    return jsonify({"success": True})


@bp.route('/api/db/health')
@login_required
def db_health():
    conn = get_db()
    integrity = conn.execute("PRAGMA integrity_check").fetchone()[0]
    tables_info = {}
    with_deleted = {'schedule_days', 'lessons', 'subjects', 'teachers', 'groups_list', 'classrooms_list', 'specialties'}
    for t in ['schedule_days', 'lessons', 'subjects', 'teachers', 'groups_list', 'classrooms_list', 'specialties', 'excluded_dates', 'lesson_history']:
        total = conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
        d = conn.execute(f"SELECT COUNT(*) FROM {t} WHERE deleted_at IS NOT NULL").fetchone()[0] if t in with_deleted else 0
        tables_info[t] = {"total": total, "deleted": d}
    conflicts = conn.execute('''
        SELECT l1.id AS id1, l2.id AS id2, sd.date, l1.period,
               t1.name AS t1n, t2.name AS t2n
        FROM lessons l1 JOIN lessons l2 ON l1.id < l2.id
        JOIN schedule_days sd ON l1.day_id = sd.id
        LEFT JOIN teachers t1 ON l1.teacher_id = t1.id
        LEFT JOIN teachers t2 ON l2.teacher_id = t2.id
        WHERE l1.day_id = l2.day_id AND l1.period = l2.period
          AND l1.deleted_at IS NULL AND l2.deleted_at IS NULL
          AND (l1.teacher_id = l2.teacher_id OR l1.classroom_id = l2.classroom_id
               OR (l1.group_id = l2.group_id AND (l1.subgroup IS NULL OR l1.subgroup = l2.subgroup)))
    ''').fetchall()
    orphaned = []
    for t, col in [('subjects','subject_id'),('teachers','teacher_id'),('classrooms_list','classroom_id'),('groups_list','group_id')]:
        rows = conn.execute(f"SELECT l.id FROM lessons l LEFT JOIN {t} r ON l.{col}=r.id WHERE l.{col} IS NOT NULL AND r.id IS NULL AND l.deleted_at IS NULL").fetchall()
        orphaned.extend([dict(r) for r in rows])
    conn.close()
    return jsonify({"integrity_check": integrity, "tables": tables_info, "conflicts": [dict(r) for r in conflicts], "orphaned_lessons": orphaned})


@bp.route('/api/db/purge-trash', methods=['POST'])
@login_required
def purge_trash():
    conn = get_db()
    result = {}
    for t in ['lessons', 'schedule_days', 'subjects', 'teachers', 'groups_list', 'classrooms_list', 'specialties']:
        cnt = conn.execute(f"DELETE FROM {t} WHERE deleted_at IS NOT NULL AND deleted_at < datetime('now', ?)", (f'-{TRASH_RETENTION_DAYS} days',)).rowcount
        if cnt:
            result[t] = cnt
    conn.execute("DELETE FROM lesson_history WHERE changed_at < datetime('now', ?)", (f'-{TRASH_RETENTION_DAYS} days',))
    conn.commit()
    conn.close()
    refs_cache.invalidate_prefix('ref_list_')
    return jsonify({"purged": result})


@bp.route('/api/admin/backup/download', methods=['GET'])
@login_required
def admin_backup_download():
    """Скачать резервную копию БД"""
    db_path = DB_PATH
    if not os.path.exists(db_path):
        logger.error("Backup download failed: DB file not found at %s", db_path)
        return jsonify({"error": "Файл базы данных не найден"}), 404
    try:
        return send_file(db_path, as_attachment=True,
                         download_name=f'schedule_backup_{datetime.now().strftime("%Y-%m-%d_%H-%M")}.db')
    except Exception:
        logger.exception("Backup download failed for %s", db_path)
        return jsonify({"error": "Не удалось скачать резервную копию"}), 500


@bp.route('/api/admin/backup/restore', methods=['POST'])
@login_required
def admin_backup_restore():
    if 'file' not in request.files:
        return jsonify({"error": "No file uploaded"}), 400
    f = request.files['file']
    if f.filename == '':
        return jsonify({"error": "Empty filename"}), 400
    if not (f.filename.endswith('.sqlite') or f.filename.endswith('.db')):
        return jsonify({"error": "Only .sqlite or .db files allowed"}), 400
    create_backup()
    prepare_for_restore()
    f.save(DB_PATH)
    for ext in ('-wal', '-shm'):
        p = DB_PATH + ext
        if os.path.exists(p):
            try:
                os.remove(p)
            except OSError:
                pass
    ok, err = verify_db_integrity()
    if not ok:
        logger.error("Restored DB integrity check failed: %s", err)
        return jsonify({"error": f"Restored database is corrupt: {err}"}), 500
    # После подмены файла БД кэш справочников невалиден целиком: invalidate() есть
    # в cache.py, а прежний вызов invalidate_all() падал с AttributeError уже после
    # того, как файл был записан поверх рабочей БД.
    refs_cache.invalidate()
    logger.info("Database restored from uploaded file: %s — integrity OK", f.filename)
    return jsonify({"success": True, "message": "База данных восстановлена и проверена. Страница будет перезагружена."})


@bp.route('/api/admin/db/check-orphans', methods=['GET', 'POST'])
@login_required
def admin_check_orphans():
    if request.method == 'POST':
        body = request.get_json(silent=True) or {}
        force = body.get('force', False)
        result = cleanup_orphan_schedule_records(force_delete=force)
        return jsonify(result)
    orphans = find_orphaned_records()
    total = len(orphans['lessons']) + len(orphans['curriculum'])
    return jsonify({"found": total, "lessons": orphans['lessons'], "curriculum": orphans['curriculum']})


@bp.route('/api/admin/import/template/<entity_type>')
@login_required
def admin_import_template(entity_type):
    """Скачать образцовый .xlsx-шаблон для импорта справочника.
    ---
    parameters:
      - in: path
        name: entity_type
        type: string
        enum: [teachers, classrooms, groups, subjects]
        required: true
    responses:
      200:
        description: Файл .xlsx с заголовками и примером строки
    """
    from openpyxl import Workbook
    from openpyxl.utils import get_column_letter
    from openpyxl.styles import Font, PatternFill, Alignment
    valid = {'teachers': 'Преподаватели', 'classrooms': 'Кабинеты', 'groups': 'Группы', 'subjects': 'Предметы'}
    if entity_type not in valid:
        return jsonify({"error": "Unknown entity_type"}), 400
    header_cols = EXCEL_IMPORT_TEMPLATE_HEADERS[entity_type]
    examples = EXCEL_IMPORT_TEMPLATE_EXAMPLES[entity_type]

    wb = Workbook()
    ws = wb.active
    ws.title = valid[entity_type]
    ws.append(header_cols)
    bold = Font(bold=True, color='1F2937', size=11)
    fill = PatternFill(start_color='E5E7EB', end_color='E5E7EB', fill_type='solid')
    center = Alignment(horizontal='left', vertical='center')
    for cell in ws[1]:
        cell.font = bold
        cell.fill = fill
        cell.alignment = center
    for ex in examples:
        ws.append(ex)
    # Разумные ширины колонок
    for i, col in enumerate(header_cols, start=1):
        width = max(14, min(34, 12 + len(col)))
        ws.column_dimensions[get_column_letter(i)].width = width
    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    return send_file(buf, as_attachment=True, download_name=f"template_{entity_type}.xlsx",
                     mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')


@bp.route('/api/admin/import/excel', methods=['POST'])
@login_required
def admin_import_excel():
    """Универсальный импорт справочника из .xlsx.
    ---
    consumes:
      - multipart/form-data
    parameters:
      - in: formData
        name: file
        type: file
        required: true
      - in: formData
        name: entity_type
        type: string
        enum: [teachers, classrooms, groups, subjects]
        required: true
    responses:
      200:
        description: {created, skipped, errors}
      400:
        description: Ошибка файла/заголовков/типа
    """
    entity_type = request.form.get('entity_type', '').strip()
    if entity_type not in EXCEL_IMPORT_SCHEMAS:
        return jsonify({"error": "Unknown entity_type"}), 400
    if 'file' not in request.files:
        return jsonify({"error": "No file uploaded"}), 400
    f = request.files['file']
    if not f.filename or not f.filename.lower().endswith('.xlsx'):
        return jsonify({"error": "Только файлы .xlsx"}), 400

    parse_error, _col_map, rows, _parse_errors = parse_excel_import(f.stream, entity_type)
    if parse_error:
        # заголовки не совпали или файл не прочитался — валидный .xlsx, но не тот формат
        return jsonify({"error": parse_error, "created": 0, "skipped": 0, "errors": [parse_error]}), 400

    conn = get_db()
    created = 0
    skipped = 0
    errors = []
    seen = set()

    tbls = {'teachers': 'teachers', 'classrooms': 'classrooms_list',
            'groups': 'groups_list', 'subjects': 'subjects'}

    for item in rows:
        name = item['name']
        # Пропуск дубликатов внутри файла (по нормализованному имени)
        lname = name.strip().lower()
        if lname in seen:
            skipped += 1
            continue
        seen.add(lname)
        # Проверка существующих активных записей (пропуск дублей базы)
        dup = conn.execute(
            f"SELECT 1 FROM {tbls[entity_type]} WHERE LOWER(name) = LOWER(?) AND deleted_at IS NULL LIMIT 1",
            (name,)
        ).fetchone()
        if dup:
            skipped += 1
            continue
        if entity_type == 'teachers':
            phone = (item.get('phone') or '').strip() or None
            conn.execute("INSERT INTO teachers (name, phone) VALUES (?, ?)", (name, phone))
            created += 1
        elif entity_type == 'classrooms':
            conn.execute("INSERT INTO classrooms_list (name) VALUES (?)", (name,))
            created += 1
        elif entity_type == 'subjects':
            conn.execute("INSERT INTO subjects (name) VALUES (?)", (name,))
            created += 1
        elif entity_type == 'groups':
            course = 1
            if item.get('course') is not None:
                try:
                    course = int(float(item['course']))
                except (TypeError, ValueError):
                    errors.append(f"Строка {item['_row']}: неверный курс «{item.get('course')}» — берём 1")
                    course = 1
            specialty_id = None
            if item.get('specialty_code'):
                sp = conn.execute(
                    "SELECT id FROM specialties WHERE code = ? AND deleted_at IS NULL ORDER BY id LIMIT 1",
                    (item['specialty_code'],)
                ).fetchone()
                if sp:
                    specialty_id = sp['id']
                else:
                    errors.append(f"Строка {item['_row']}: специальность «{item['specialty_code']}» не найдена — группа без специальности")
            is_distance = 1 if (item.get('форма обучения') or '').lower() in ('заочно', 'заочн', 'заочная') else 0
            conn.execute(
                "INSERT INTO groups_list (name, course, specialty_id, is_distance) VALUES (?, ?, ?, ?)",
                (name, course, specialty_id, is_distance))
            created += 1

    conn.commit()
    conn.close()
    refs_cache.invalidate_prefix('ref_list_')
    return jsonify({"created": created, "skipped": skipped, "errors": errors})


@bp.route('/api/schedule/generate', methods=['POST'])
@login_required
def schedule_generate():
    body = request.get_json(silent=True) or {}
    group_id = body.get('group_id')
    semester = body.get('semester', 1)
    monday = body.get('monday', '')
    week_count = body.get('week_count', 1)
    # weeks_count = alias for batch/monthly generation (max 4)
    weeks_count = body.get('weeks_count')
    if weeks_count:
        try:
            week_count = min(max(int(weeks_count), 1), MAX_GENERATE_WEEKS_ALIAS)
        except (TypeError, ValueError):
            return jsonify({"error": "weeks_count должен быть целым числом"}), 400
    else:
        try:
            week_count = int(week_count or 1)
        except (TypeError, ValueError):
            return jsonify({"error": "week_count должен быть целым числом"}), 400
        if week_count < 1:
            week_count = 1
        elif week_count > MAX_GENERATE_WEEKS:
            # Генерация идёт в одной транзакции и блокирует записи: ограничиваем объём.
            return jsonify({
                "error": f"Слишком много недель за один запрос: {week_count} > {MAX_GENERATE_WEEKS}. "
                         f"Генерируйте порциями по {MAX_GENERATE_WEEKS} недель."
            }), 400
    if not group_id or not monday:
        return jsonify({"error": "group_id and monday required"}), 400
    conn = get_db()
    group = conn.execute("SELECT id, name FROM groups_list WHERE id = ? AND deleted_at IS NULL", (group_id,)).fetchone()
    if not group:
        conn.close()
        return jsonify({"error": "Group not found"}), 404
    result = generate_schedule(conn, group_id, group['name'], semester, monday, week_count,
                              optimize=bool(body.get('optimize', True)), seed=body.get('seed'))
    conn.commit()
    conn.close()
    refs_cache.invalidate_prefix('ref_list_')
    logger.info("Generator created %d lessons for group %s semester %d weeks=%d", result['created'], group['name'], semester, week_count)
    return jsonify({
        "created": result['created'],
        "errors": result['errors'],
        "weeks_processed": week_count,
    })


@bp.route('/api/schedule/substitutions-suggest', methods=['GET'])
@login_required
def substitutions_suggest():
    """Find available teachers for a substitution on a given day and period.
    Reuses the same availability model as /api/availability — finds teachers
    who are NOT busy at the given date+period."""
    date_str = request.args.get('date', '')
    period = request.args.get('period', type=int)
    exclude_teacher_id = request.args.get('exclude_teacher_id', type=int)
    if not date_str:
        day_id = request.args.get('day_id', type=int)
        if day_id:
            conn0 = get_db()
            day_row = conn0.execute('SELECT date FROM schedule_days WHERE id = ?', (day_id,)).fetchone()
            conn0.close()
            if day_row:
                date_str = day_row['date']
    if not date_str or not period:
        return jsonify({"error": "date and period required"}), 400
    conn = get_db()
    busy_ids = set()
    busy_rows = conn.execute('''
        SELECT DISTINCT l.teacher_id FROM lessons l
        JOIN schedule_days sd ON l.day_id = sd.id
        WHERE sd.date = ? AND l.period = ? AND l.deleted_at IS NULL AND sd.deleted_at IS NULL
          AND l.teacher_id IS NOT NULL AND l.subject_id IS NOT NULL
    ''', (date_str, period)).fetchall()
    for r in busy_rows:
        busy_ids.add(r['teacher_id'])
    # Teachers who ALREADY stand as substitutes in other lessons at this date+period
    # are never eligible candidates — even if exclude_teacher_id would otherwise
    # re-admit the currently-being-edited teacher.
    substituting_ids = set()
    sub_rows = conn.execute('''
        SELECT DISTINCT l.teacher_id FROM lessons l
        JOIN schedule_days sd ON l.day_id = sd.id
        WHERE sd.date = ? AND l.period = ?
          AND l.is_substitution = 1
          AND l.deleted_at IS NULL AND sd.deleted_at IS NULL
          AND l.teacher_id IS NOT NULL
    ''', (date_str, period)).fetchall()
    for r in sub_rows:
        substituting_ids.add(r['teacher_id'])
    if exclude_teacher_id and exclude_teacher_id not in substituting_ids:
        busy_ids.discard(exclude_teacher_id)
    teachers = conn.execute('''
        SELECT id, name FROM teachers
        WHERE deleted_at IS NULL ORDER BY name
    ''').fetchall()
    conn.close()
    available = [{'id': t['id'], 'name': t['name']} for t in teachers if t['id'] not in busy_ids and t['id'] not in substituting_ids]
    return jsonify({"available": available})


@bp.route('/api/schedule/clear-week', methods=['DELETE'])
@login_required
def clear_week_group():
    """Очистить расписание строго одной группы на указанную неделю (6 дней, Пн–Сб).
    group_id — обязателен; удаление затрагивает ТОЛЬКО переданную группу.
    ---
    parameters:
      - in: query
        name: start_date
        type: string
        required: true
        description: Дата понедельника (YYYY-MM-DD)
      - in: query
        name: group_id
        type: integer
        required: true
        description: ID группы, чью неделю очищаем
    responses:
      200:
        description: Объект с deleted_count (число удалённых пар) только для этой группы
      400:
        description: start_date и/или group_id обязательны
    """
    group_id_param = request.args.get('group_id')
    if not group_id_param and request.is_json:
        group_id_param = (request.get_json(silent=True) or {}).get('group_id')
    if not group_id_param or not str(group_id_param).isdigit():
        return jsonify({"error": "Строго обязателен корректный числовой group_id"}), 400
    group_id = int(group_id_param)
    start_date = request.args.get('start_date', '')
    if not start_date:
        return jsonify({"error": "start_date required"}), 400
    week_dates = [d['date'] for d in build_week_dates(start_date)]
    placeholders = ','.join('?' * len(week_dates))
    # Mirror the exact JOIN/WHERE used by the reading endpoint: filter via schedule_days.
    # group_id is resolved to group_name once; lessons are then selected through sd.group_name
    # (matches /api/schedule-table which filters sd.group_name = ?).
    conn = get_db()
    try:
        conn.execute('BEGIN IMMEDIATE')
        cur = conn.execute(
            f"""UPDATE lessons SET deleted_at = datetime('now')
                WHERE deleted_at IS NULL AND id IN (
                    SELECT l.id FROM lessons l
                    JOIN schedule_days sd ON l.day_id = sd.id
                    WHERE sd.date IN ({placeholders})
                      AND sd.group_name = (SELECT name FROM groups_list WHERE id = ?)
                )""",
            week_dates + [group_id]
        )
        deleted_count = cur.rowcount
        # Safeguard: if a single group unexpectedly has >36 pairs in a week, log it but still perform
        # the scoped operation (isolation is guaranteed by sd.group_name + week dates). This prevents
        # Kill-Switch from ever blocking a legitimate delete for the currently-open week.
        if deleted_count > 36:
            logger.warning("Clear-week for group_id=%s modified %d lessons (anomalously high) — proceeding scoped", group_id, deleted_count)
        # Soft-delete this group's days on this week
        conn.execute(
            "UPDATE schedule_days SET deleted_at = datetime('now') WHERE deleted_at IS NULL AND date IN ({p}) AND group_name = (SELECT name FROM groups_list WHERE id = ?)".format(p=placeholders),
            week_dates + [group_id]
        )
        conn.commit()
    finally:
        conn.close()
    return jsonify({"success": True, "deleted_count": deleted_count})


@bp.route('/api/schedule/restore-week', methods=['POST'])
@login_required
def restore_week_group():
    """Восстановить неделю СТРОГО одной группы (group_id) за 7 дней (start_date...start_date+6).
    Никогда не касается других групп или соседних недель.
    ---
    responses:
      200:
        description: Объект с restored_count (число восстановленных пар только этой группы)
      400:
        description: start_date и/или group_id обязательны
    """
    group_id_param = request.args.get('group_id')
    if not group_id_param and request.is_json:
        group_id_param = (request.get_json(silent=True) or {}).get('group_id')
    if not group_id_param or not str(group_id_param).isdigit():
        return jsonify({"error": "Строго обязателен корректный числовой group_id"}), 400
    group_id = int(group_id_param)
    start_date = request.args.get('start_date', '')
    if not start_date:
        return jsonify({"error": "start_date required"}), 400
    week_dates = [d['date'] for d in build_week_dates(start_date)]
    placeholders = ','.join('?' * len(week_dates))
    # Mirror reading-endpoint JOIN/WHERE: filter via schedule_days.group_name.
    conn = get_db()
    try:
        conn.execute('BEGIN IMMEDIATE')
        cur = conn.execute(
            f"""UPDATE lessons SET deleted_at = NULL
                WHERE deleted_at IS NOT NULL AND id IN (
                    SELECT l.id FROM lessons l
                    JOIN schedule_days sd ON l.day_id = sd.id
                    WHERE sd.date IN ({placeholders})
                      AND sd.group_name = (SELECT name FROM groups_list WHERE id = ?)
                )""",
            week_dates + [group_id]
        )
        restored_count = cur.rowcount
        # Safeguard: log anomaly but never block restore for the currently-open week.
        if restored_count > 36:
            logger.warning("Restore-week for group_id=%s restored %d lessons (anomalously high) — proceeding scoped", group_id, restored_count)
        conn.execute(
            "UPDATE schedule_days SET deleted_at = NULL WHERE deleted_at IS NOT NULL AND date IN ({p}) AND group_name = (SELECT name FROM groups_list WHERE id = ?)".format(p=placeholders),
            week_dates + [group_id]
        )
        conn.commit()
    finally:
        conn.close()
    return jsonify({"success": True, "restored_count": restored_count})


@bp.route('/api/weeks-summary')
def weeks_summary():
    """Список активных недель года: понедельники недель, где есть хотя бы одна активная пара

    Параметры:
      year — год (по умолчанию текущий)
      group — имя группы (опционально)
      teacher_id — ID преподавателя (опционально)
      classroom_id — ID аудитории (опционально)
    ---
    responses:
      200:
        description: Объект {year, active_mondays} — массив дат понедельников YYYY-MM-DD
      400:
        description: year вне диапазона 2000–2100
    """
    year = request.args.get('year', type=int, default=datetime.now().year)
    if not year or year < 2000 or year > 2100:
        return jsonify({"error": "year must be between 2000 and 2100"}), 400

    sql = '''
        SELECT DISTINCT sd.date
        FROM lessons l
        JOIN schedule_days sd ON l.day_id = sd.id
        WHERE l.deleted_at IS NULL AND sd.deleted_at IS NULL
          AND sd.date >= ? AND sd.date <= ?
    '''
    params = [f'{year}-01-01', f'{year}-12-31']

    group_name = (request.args.get('group') or '').strip()
    teacher_id = request.args.get('teacher_id', type=int)
    classroom_id = request.args.get('classroom_id', type=int)
    if group_name:
        sql += ' AND sd.group_name = ?'
        params.append(group_name)
    if teacher_id:
        sql += ' AND l.teacher_id = ?'
        params.append(teacher_id)
    if classroom_id:
        sql += ' AND l.classroom_id = ?'
        params.append(classroom_id)

    conn = get_db()
    rows = conn.execute(sql, params).fetchall()
    conn.close()

    mondays = set()
    for r in rows:
        d = datetime.strptime(r['date'], '%Y-%m-%d').date()
        monday = (d - timedelta(days=d.weekday())).isoformat()
        if monday.startswith(f'{year}-'):
            mondays.add(monday)

    return jsonify({"year": year, "active_mondays": sorted(mondays)})
