"""TDD для Фазы 2 генератора: имитация отжига поверх жадного черновика.

Проверяем чистые функции: они не ходят в БД и работают со списком занятий.
"""

import logging
import time

import generator


def _lesson(date, period, teacher_id=1, classroom_id=1, group_id=1, subject_id=1, lesson_id=None):
    return {
        'id': lesson_id,
        'date': date,
        'period': period,
        'teacher_id': teacher_id,
        'classroom_id': classroom_id,
        'group_id': group_id,
        'subject_id': subject_id,
    }


def _windows_schedule():
    """Окна у преподавателя 1 (пары 1 и 4) и у группы (2 и 6).

    Свободные периоды 3, 5, 7, 8 — оптимизатору есть куда двигаться.
    """
    return [
        _lesson('2026-09-07', 1, teacher_id=1),
        _lesson('2026-09-07', 4, teacher_id=1),
        _lesson('2026-09-08', 2, teacher_id=2),
        _lesson('2026-09-08', 6, classroom_id=2),
    ]


def test_annealing_improves_cost(app):
    plan = _windows_schedule()
    before = generator._calculate_cost(plan)
    optimized = generator._optimize_schedule(plan, seed=42, iterations=600, time_budget=2.0)
    after = generator._calculate_cost(optimized)
    assert len(optimized) == len(plan)
    assert after < before, f'стоимость не улучшилась: {before} -> {after}'


def test_annealing_preserves_hard_constraints(app):
    optimized = generator._optimize_schedule(_windows_schedule(), seed=42, iterations=600)
    slots = set()
    teachers = set()
    classrooms = set()
    for item in optimized:
        slots.add((item['date'], item['period'], item['group_id']))
        teachers.add((item['date'], item['period'], item['teacher_id']))
        classrooms.add((item['date'], item['period'], item['classroom_id']))
    assert len(slots) == len(optimized), 'две пары группы в одном слоте'
    assert len(teachers) == len({(i['date'], i['period'], i['teacher_id']) for i in optimized})
    assert len(classrooms) == len({(i['date'], i['period'], i['classroom_id']) for i in optimized})
    for item in optimized:
        assert 1 <= item['period'] <= 8


def test_annealing_deterministic(app):
    first = generator._optimize_schedule(_windows_schedule(), seed=7, iterations=400)
    second = generator._optimize_schedule(_windows_schedule(), seed=7, iterations=400)
    assert first == second

    other = generator._optimize_schedule(_windows_schedule(), seed=8, iterations=400)
    assert generator._calculate_cost(other) <= generator._calculate_cost(_windows_schedule())


def test_optimize_never_worse_than_draft(app):
    plan = _windows_schedule()
    best = generator._optimize_schedule(plan, seed=3, iterations=500)
    assert generator._calculate_cost(best) <= generator._calculate_cost(plan)


def test_optimize_respects_time_budget(app):
    plan = _windows_schedule()
    started = time.time()
    generator._optimize_schedule(plan, seed=1, iterations=10_000_000, time_budget=0.2)
    elapsed = time.time() - started
    assert elapsed < 2.0, f'отжиг вышел за бюджет: {elapsed:.2f}s'


def test_calculate_cost_counts_fixed_teacher_lessons(app):
    """Окна преподавателя считаются и с учётом его пар в других группах."""
    plan = [_lesson('2026-09-07', 1, teacher_id=1)]
    fixed = [_lesson('2026-09-07', 4, teacher_id=1, group_id=2)]
    assert generator._calculate_cost(plan, fixed=fixed) > generator._calculate_cost(plan)


def test_calculate_cost_penalises_overload(app):
    """Пятая пара в будний день у группы — перегруз."""
    normal = [_lesson('2026-09-07', p) for p in (1, 2, 3, 4)]
    overloaded = [_lesson('2026-09-07', p) for p in (1, 2, 3, 4, 5)]
    assert generator._calculate_cost(overloaded) > generator._calculate_cost(normal)


def test_composite_stream_skipped_and_logged(app, db):
    """Зеркальные группы не двигают пары — и причина видна в логе."""
    conn = db.get_db()
    # _mirror_target_groups ищет группы-части потока («02-0923+11/24»)
    conn.execute("INSERT INTO groups_list (name) VALUES ('02-0923')")
    conn.execute("INSERT INTO groups_list (name) VALUES ('11/24')")
    conn.commit()

    records = []

    class _Capture(logging.Handler):
        def emit(self, record):
            records.append(record)

    handler = _Capture()
    logger = generator.logger
    old_level, old_disabled = logger.level, logger.disabled
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    logger.disabled = False  # pytest может выставлять disabled для логгеров
    try:
        moved = generator._optimize_week(
            conn, 1, '02-0923+11/24', ['2026-09-07'], [1, 2, 3, 4], seed='x', lesson_ids=[1])
    finally:
        logger.removeHandler(handler)
        logger.setLevel(old_level)
        logger.disabled = old_disabled
        conn.close()

    assert moved == 0
    messages = [r.getMessage() for r in records]
    assert any('составной поток' in m and '02-0923' in m for m in messages), messages
