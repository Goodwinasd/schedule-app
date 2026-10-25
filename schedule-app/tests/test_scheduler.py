import pytest
from datetime import datetime

# --- Временные заглушки тестируемых функций (или импорт из сервиса бэкенда) ---

def validate_daily_load(pairs_count: int, is_saturday: bool = False) -> bool:
    max_limit = 3 if is_saturday else 4
    return 0 <= pairs_count <= max_limit

def is_special_holiday(date_obj: datetime, is_first_course: bool = True) -> bool:
    return is_first_course and date_obj.month == 9 and date_obj.day == 1

def mirror_group_schedule(schedule_items: list, target_group_id: str) -> list:
    mirrored = []
    for item in schedule_items:
        copied = item.copy()
        copied["group_id"] = target_group_id
        mirrored.append(copied)
    return mirrored


# --- Набор юнит-тестов ---

def test_validate_daily_load_normal_days():
    assert validate_daily_load(3, is_saturday=False) is True
    assert validate_daily_load(4, is_saturday=False) is True
    assert validate_daily_load(5, is_saturday=False) is False

def test_validate_daily_load_saturday():
    assert validate_daily_load(2, is_saturday=True) is True
    assert validate_daily_load(3, is_saturday=True) is True
    assert validate_daily_load(4, is_saturday=True) is False

def test_september_first_holiday():
    sept_1 = datetime(2025, 9, 1)
    sept_2 = datetime(2025, 9, 2)
    # 1-й курс, 1 сентября — линейка (пар нет)
    assert is_special_holiday(sept_1, is_first_course=True) is True
    # 2-й курс и старше, 1 сентября — обычные пары
    assert is_special_holiday(sept_1, is_first_course=False) is False
    # 1-й курс, 2 сентября — обычные пары
    assert is_special_holiday(sept_2, is_first_course=True) is False

def test_group_mirroring():
    base_schedule = [{"day": "Понедельник", "pair_num": 1, "subject": "Математика"}]
    target_group = "02-0923+1124"
    result = mirror_group_schedule(base_schedule, target_group)

    assert len(result) == 1
    assert result[0]["group_id"] == target_group
    assert result[0]["subject"] == "Математика"


# --- Юнит-тесты эвристик generator.py ---

import sqlite3
from generator import _max_pairs_per_day, _is_holiday, _mirror_week_lessons, _mirror_target_groups


def _mem_db():
    conn = sqlite3.connect(':memory:')
    conn.row_factory = sqlite3.Row
    conn.execute("CREATE TABLE excluded_dates (id INTEGER PRIMARY KEY, start_date TEXT, end_date TEXT)")
    conn.execute("CREATE TABLE groups_list (id INTEGER PRIMARY KEY, name TEXT, deleted_at TEXT)")
    conn.execute("CREATE TABLE schedule_days (id INTEGER PRIMARY KEY, day_name TEXT, date TEXT, group_name TEXT, deleted_at TEXT, is_published INTEGER NOT NULL DEFAULT 0)")
    conn.execute("""CREATE TABLE lessons (
        id INTEGER PRIMARY KEY, day_id INTEGER, period INTEGER, subject_id INTEGER,
        teacher_id INTEGER, classroom_id INTEGER, group_id INTEGER,
        is_substitution INTEGER DEFAULT 0, original_teacher_id INTEGER, deleted_at TEXT)""")
    return conn


def test_generator_daily_load_limits():
    for day_idx in range(5):
        assert _max_pairs_per_day(day_idx) == 4, f"weekday {day_idx} must allow 4 pairs"
    assert _max_pairs_per_day(5) == 3, "Saturday must be limited to 3 pairs"


def test_generator_september_first_is_not_global_holiday():
    conn = _mem_db()
    try:
        # _is_holiday работает только с excluded_dates: 1 сентября НЕ является
        # глобальным праздником (старшие курсы в этот день учатся)
        assert _is_holiday(conn, '2025-09-01') is False
    finally:
        conn.close()


def test_generator_holiday_from_excluded_dates():
    conn = _mem_db()
    try:
        conn.execute("INSERT INTO excluded_dates (start_date, end_date) VALUES ('2025-11-03', '2025-11-05')")
        conn.commit()
        assert _is_holiday(conn, '2025-11-04') is True
        assert _is_holiday(conn, '2025-11-06') is False
    finally:
        conn.close()


def test_generator_mirror_target_groups():
    conn = _mem_db()
    try:
        conn.execute("INSERT INTO groups_list (id, name) VALUES (1, '02-0923+11/24')")
        conn.execute("INSERT INTO groups_list (id, name) VALUES (2, '11/24')")
        conn.commit()
        targets = _mirror_target_groups(conn, '02-0923+11/24')
        assert len(targets) == 1
        assert targets[0]['id'] == 2
        assert _mirror_target_groups(conn, 'Группа-1') == []
    finally:
        conn.close()


def test_generator_mirror_week_lessons():
    conn = _mem_db()
    try:
        conn.execute("INSERT INTO groups_list (id, name) VALUES (1, '02-0923+11/24')")
        conn.execute("INSERT INTO groups_list (id, name) VALUES (2, '11/24')")
        conn.commit()
        placed = [
            ('2026-09-07', 1, 5, 10, 20, True, 11),
            ('2026-09-07', 2, 6, 10, 20, False, None),
        ]
        mirrored = _mirror_week_lessons(conn, '02-0923+11/24', placed)
        assert mirrored == 2
        rows = conn.execute("SELECT * FROM lessons").fetchall()
        assert len(rows) == 2
        for r in rows:
            assert r['group_id'] == 2
            assert r['period'] in (1, 2)
            assert r['teacher_id'] == 10
            assert r['classroom_id'] == 20
        assert any(r['is_substitution'] == 1 and r['original_teacher_id'] == 11 for r in rows)
        assert _mirror_week_lessons(conn, 'Группа-1', placed) == 0
    finally:
        conn.close()


def test_generator_mirror_skips_conflicted_slot():
    conn = _mem_db()
    try:
        conn.execute("INSERT INTO groups_list (id, name) VALUES (1, '02-0923+11/24')")
        conn.execute("INSERT INTO groups_list (id, name) VALUES (2, '11/24')")
        conn.execute("INSERT INTO schedule_days (id, day_name, date, group_name) VALUES (1, 'Понедельник', '2026-09-07', '11/24')")
        conn.execute("""INSERT INTO lessons (day_id, period, subject_id, teacher_id, classroom_id, group_id)
                        VALUES (1, 1, 99, 10, 20, 2)""")
        conn.commit()
        placed = [('2026-09-07', 1, 5, 10, 20, False, None)]
        mirrored = _mirror_week_lessons(conn, '02-0923+11/24', placed)
        assert mirrored == 0, "mirror must not duplicate into an already-busy group slot"
    finally:
        conn.close()
