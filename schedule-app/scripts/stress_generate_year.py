#!/usr/bin/env python3
"""СТРЕСС-ТЕСТ: наполнение расписания на учебный год 2026–2027 и аудит целостности.

Этапы:
  1. Бэкап БД (data/schedule_backup_pre_stress.db) — выполняется отдельно/гарантируется.
  2. Привязка активных групп к специальностям (равномерно) + построение шаблонных планов.
  3. Авто-заполнение планов групп через apply-specialty-plan (семестры 1 и 2).
  4. Годовая генерация расписания: 36 учебных недель (18 * 2 семестра) для всех групп.
  5. Health Check: PRAGMA integrity_check, orphan-check, 3D-конфликты, замер скорости API.
  6. Итоговый отчёт.

Запуск (из корня проекта):
  python scripts/stress_generate_year.py
"""
import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))

import config
import db as db_module
from db import get_db, find_orphaned_records
from generator import generate_schedule

SEM1_MONDAY = '2026-08-31'
SEM2_MONDAY = '2027-01-04'
WEEKS_PER_SEMESTER = 18  # 36 недель в сумме
YEAR_RANGE = ('2026-01-01', '2027-12-31')

METRICS = {}


# ---------- 2. Привязка групп к специальностям ----------

def link_groups_to_specialties(conn):
    specs = conn.execute("SELECT id FROM specialties WHERE deleted_at IS NULL ORDER BY id").fetchall()
    groups = conn.execute("SELECT id FROM groups_list WHERE deleted_at IS NULL ORDER BY id").fetchall()
    linked = created_templates = 0
    if not specs:
        print('[LINK] Нет активных специальностей — пропуск привязки.')
        return 0
    for i, g in enumerate(groups):
        sid = specs[i % len(specs)]['id']
        conn.execute("UPDATE groups_list SET specialty_id = ? WHERE id = ?", (sid, g['id']))
        linked += 1
    conn.commit()
    print(f'[LINK] Привязано групп к специальностям: {linked}')
    return linked


# ---------- 3. Шаблонные планы + apply-specialty-plan ----------

def _clone_plan(conn, from_gid, to_gid, specialty_id, semester):
    """Скопировать дисциплины/часы из группы-шаблона в группу to_gid (если их ещё нет)."""
    rows = conn.execute('''
        SELECT c.*, s.name AS subject_name, t.name AS teacher_name
        FROM curriculum c
        LEFT JOIN subjects s ON c.subject_id = s.id
        LEFT JOIN teachers t ON c.teacher_id = t.id
        WHERE c.group_id = ? AND c.semester = ?
    ''', (from_gid, semester)).fetchall()
    created = 0
    cycles = ['ООД', 'СГ', 'ОП', 'ПМ', 'МДК']
    controls = ['Экзамен', 'Зачет', 'Диф. зачет']
    for i, r in enumerate(rows):
        existing = conn.execute(
            "SELECT 1 FROM curriculum WHERE group_id = ? AND subject_id = ? AND semester = ?",
            (to_gid, r['subject_id'], semester)).fetchone()
        if existing:
            continue
        conn.execute(
            "INSERT INTO curriculum (group_id, subject_id, teacher_id, semester, total_hours, "
            "weeks_in_semester, specialty_id, cycle, control_form) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (to_gid, r['subject_id'], r['teacher_id'], semester, r['total_hours'],
             r['weeks_in_semester'], specialty_id, cycles[i % len(cycles)], controls[i % len(controls)])
        )
        created += 1
    return created


def build_plans(conn):
    """У каждой специальности есть шаблон (клонируем план группы 1), затем применяем ко всем группам."""
    specs = conn.execute("SELECT id FROM specialties WHERE deleted_at IS NULL ORDER BY id").fetchall()
    groups_by_spec = {}
    for s in specs:
        gs = conn.execute(
            "SELECT id, name FROM groups_list WHERE specialty_id = ? AND deleted_at IS NULL ORDER BY id",
            (s['id'],)).fetchall()
        if gs:
            groups_by_spec[s['id']] = [dict(g) for g in gs]

    # Источник-шаблон: план группы 1 (единственный готовый учебный план)
    source = conn.execute(
        "SELECT id FROM groups_list WHERE id = 1 AND deleted_at IS NULL").fetchone()
    if not source:
        print('[PLAN] Источник-шаблон (группа 1) не найден — пропуск.')
        return 0

    total_created = 0
    for sid, gs in groups_by_spec.items():
        template_gid = gs[0]['id']
        # Убедиться, что у template есть план: при необходимости клонировать с группы 1
        for sem in (1, 2):
            cnt = conn.execute("SELECT COUNT(*) FROM curriculum WHERE group_id = ? AND semester = ?",
                               (template_gid, sem)).fetchone()[0]
            if cnt == 0:
                total_created += _clone_plan(conn, 1, template_gid, sid, sem)
        # Применить план ко всем остальным группам (клон с template)
        for g in gs[1:]:
            for sem in (1, 2):
                total_created += _clone_plan(conn, template_gid, g['id'], sid, sem)
    conn.commit()
    print(f'[PLAN] Построено/скопировано записей учебных планов: {total_created}')
    return total_created


# ---------- 4. Годовая генерация ----------

def _monday_add(monday_str, weeks):
    d = __import__('datetime').date.fromisoformat(monday_str)
    return (d + __import__('datetime').timedelta(weeks=weeks)).isoformat()


def generate_year(conn):
    """Поквартальная генерация по одному учебному блоку с промежуточным COMMIT.
    Генерируем по несколько недель за вызов (небольшой батч) для устойчивости."""
    groups = conn.execute("SELECT id, name, specialty_id FROM groups_list WHERE deleted_at IS NULL ORDER BY id").fetchall()
    grand_created = 0
    grand_errors = 0
    no_plan_groups = []
    for g in groups:
        gid, gname = g['id'], g['name']
        has_plan = conn.execute("SELECT 1 FROM curriculum WHERE group_id = ? LIMIT 1", (gid,)).fetchone()
        if not has_plan:
            no_plan_groups.append(gname)
            continue
        for sem, start in ((1, SEM1_MONDAY), (2, SEM2_MONDAY)):
            for chunk in range(0, WEEKS_PER_SEMESTER, 3):
                monday = _monday_add(start, chunk)
                res = generate_schedule(conn, gid, gname, sem, monday, 3)
                grand_created += res['created']
                grand_errors += len(res['errors'])
                conn.commit()
        print(f'[GEN] {gname}: создано за год — {grand_created - METRICS.get("_mark", 0)}', flush=True)
        METRICS['_mark'] = grand_created
    print(f'[GEN] Всего создано уроков: {grand_created}; ошибок генератора: {grand_errors}; '
          f'групп без плана: {len(no_plan_groups)}')
    METRICS['lessons_created'] = grand_created
    METRICS['gen_errors'] = grand_errors
    METRICS['groups_no_plan'] = len(no_plan_groups)
    return grand_created


# ---------- 5. Health Check ----------

def _3d_conflicts(conn):
    rows = conn.execute('''
        SELECT l1.id AS id1, l2.id AS id2, sd.date, l1.period,
               t1.name AS c1, t2.name AS c2
        FROM lessons l1 JOIN lessons l2 ON l1.id < l2.id
        JOIN schedule_days sd ON l1.day_id = sd.id
        LEFT JOIN teachers t1 ON l1.teacher_id = t1.id
        LEFT JOIN teachers t2 ON l2.teacher_id = t2.id
        WHERE l1.day_id = l2.day_id AND l1.period = l2.period
          AND l1.deleted_at IS NULL AND l2.deleted_at IS NULL
          AND (l1.teacher_id = l2.teacher_id OR l1.classroom_id = l2.classroom_id
               OR (l1.group_id = l2.group_id AND (l1.subgroup IS NULL OR l1.subgroup = l2.subgroup)))
    ''').fetchall()
    return rows


def _db_size():
    return os.path.getsize(config.DB_PATH)


def measure_api_latency():
    """Замер времени ответа ключевых API через Flask test-client."""
    from app import app
    app.config['TESTING'] = True
    client = app.test_client()
    with client.session_transaction() as sess:
        sess['is_admin'] = True
        sess['csrf_token'] = 'stress-test'
    conn = get_db()
    g = conn.execute("SELECT id, name FROM groups_list WHERE deleted_at IS NULL ORDER BY id LIMIT 1").fetchone()
    conn.close()
    group_name = g['name']
    targets = [
        ('schedule-table', f'/api/schedule-table?group={group_name}&monday={SEM1_MONDAY}'),
        ('availability', f'/api/availability?monday={SEM1_MONDAY}'),
        ('weeks-summary', f'/api/weeks-summary?year=2026'),
    ]
    results = {}
    for name, url in targets:
        # прогрев (1 запрос), затем 3 замера
        client.get(url)
        times = []
        for _ in range(3):
            t0 = time.perf_counter()
            r = client.get(url)
            elapsed_ms = (time.perf_counter() - t0) * 1000
            times.append(elapsed_ms)
            if r.status_code != 200:
                print(f'  [LAT] {name} status={r.status_code}')
        avg = sum(times) / len(times)
        results[name] = {'avg_ms': round(avg, 2), 'runs_ms': [round(t, 2) for t in times]}
    return results


def health_check(conn):
    print('\n===== HEALTH CHECK =====')
    # 1. integrity_check
    t0 = time.perf_counter()
    integrity = conn.execute("PRAGMA integrity_check").fetchone()[0]
    integrity_ms = (time.perf_counter() - t0) * 1000
    print(f'[H] PRAGMA integrity_check: {integrity}  ({integrity_ms:.1f} ms)')

    # 2. orphan-check
    orphans = find_orphaned_records()
    total_orphans = len(orphans['lessons']) + len(orphans['curriculum'])
    print(f'[H] Сиротских записей (lessons): {len(orphans["lessons"])}; (curriculum): {len(orphans["curriculum"])}')

    # 3. 3D-конфликты
    conflicts = _3d_conflicts(conn)
    print(f'[H] 3D-конфликтов (одинаковый преподаватель/кабинет/группа на одной паре): {len(conflicts)}')

    # 4. Латенси API (< 200 ms)
    latency = measure_api_latency()
    for name, d in latency.items():
        ok = 'OK' if d['avg_ms'] < 200 else 'SLOW'
        print(f'[H] API {name}: {d["avg_ms"]} ms ({ok}) {d["runs_ms"]}')

    METRICS['integrity'] = integrity
    METRICS['orphans'] = total_orphans
    METRICS['conflicts'] = len(conflicts)
    METRICS['api_latency'] = latency
    return integrity == 'ok' and total_orphans == 0 and len(conflicts) == 0


def final_report():
    print('\n===== ИТОГОВЫЙ ОТЧЁТ =====')
    conn = get_db()
    lessons = conn.execute("SELECT COUNT(*) FROM lessons WHERE deleted_at IS NULL").fetchone()[0]
    days = conn.execute("SELECT COUNT(*) FROM schedule_days WHERE deleted_at IS NULL").fetchone()[0]
    groups = conn.execute("SELECT COUNT(*) FROM groups_list WHERE deleted_at IS NULL").fetchone()[0]
    curriculum = conn.execute("SELECT COUNT(*) FROM curriculum").fetchone()[0]
    conn.close()

    print(f'Всего активных пар/уроков на год: {lessons}')
    print(f'Учебных дней (schedule_days): {days}')
    print(f'Активных групп: {groups}')
    print(f'Записей учебных планов (curriculum): {curriculum}')
    print(f'Даты года: {SEM1_MONDAY} — {SEM2_MONDAY} (+ {WEEKS_PER_SEMESTER*2} учебных недель)')
    print(f'Размер БД: {_db_size()} байт ({_db_size()/1024:.1f} КБ)')
    lat = METRICS.get('api_latency', {})
    avg_all = [d['avg_ms'] for d in lat.values()]
    print(f'Среднее время отклика API: {sum(avg_all)/len(avg_all):.2f} ms  ' +
          ('(в пределах лимита <200ms)' if avg_all and max(avg_all) < 200 else '(превышен лимит 200ms)'))
    print(f"Integrity check: {METRICS.get('integrity')}")
    print(f'Сиротских записей: {METRICS.get("orphans", 0)}')
    print(f'3D-конфликтов: {METRICS.get("conflicts", 0)}')


def main():
    print(f'Бэкап перед стресс-тестом: data/schedule_backup_pre_stress.db '
          f'({"OK" if os.path.exists("data/schedule_backup_pre_stress.db") else "MISSING"})')
    t_start = time.perf_counter()
    conn = get_db()
    print('\n== Этап 2: привязка групп к специальностям ==')
    link_groups_to_specialties(conn)
    print('\n== Этап 3: авто-заполнение учебных планов ==')
    build_plans(conn)
    print('\n== Этап 4: годовая генерация расписания 2026–2027 (36 недель) ==')
    generate_year(conn)
    print('\n== Этап 5/6: проверки и отчёт ==')
    healthy = health_check(conn)
    final_report()
    conn.close()
    elapsed = time.perf_counter() - t_start
    print(f'\nОбщее время выполнения: {elapsed:.1f} с')
    METRICS['healthy'] = healthy
    METRICS['elapsed_s'] = round(elapsed, 1)


if __name__ == '__main__':
    main()
