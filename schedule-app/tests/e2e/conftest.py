import datetime
import os
import shutil
import socket
import sqlite3
import subprocess
import sys
import tempfile
import time

import pytest

pytest.importorskip('playwright.sync_api', reason='pytest-playwright не установлен')

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
E2E_PORT = 5055
BASE_URL = f'http://127.0.0.1:{E2E_PORT}'

WEEKDAY_NAMES = ['Понедельник', 'Вторник', 'Среда', 'Четверг', 'Пятница', 'Суббота']


def pytest_configure(config):
    config.addinivalue_line('markers', 'e2e: E2E-тесты интерфейса (Playwright)')


def _wait_ready(timeout=45):
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with socket.create_connection(('127.0.0.1', E2E_PORT), timeout=1):
                return
        except OSError:
            time.sleep(0.3)
    raise RuntimeError(f'E2E-сервер не поднялся на {BASE_URL}')


def _current_monday():
    today = datetime.date.today()
    return today - datetime.timedelta(days=today.weekday())


def _ensure_ref(conn, table, name):
    row = conn.execute(f'SELECT id FROM {table} WHERE name = ?', (name,)).fetchone()
    if row is not None:
        return row['id']
    cur = conn.execute(f'INSERT INTO {table} (name) VALUES (?)', (name,))
    return cur.lastrowid


def _seed_fixture_schedule(db_path):
    """Детерминированно наполняет копию БД расписанием на текущую неделю
    для первой в списке группы, чтобы виджет замены и грид расписания
    гарантированно имели данные независимо от состояния рабочей БД."""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        gid = _ensure_ref(conn, 'groups_list', '01-09/25')
        tid = _ensure_ref(conn, 'teachers', 'Иванов И.И.')
        sid = _ensure_ref(conn, 'subjects', 'Математика')
        cid = _ensure_ref(conn, 'classrooms_list', '101')

        monday = _current_monday()
        name = '01-09/25'
        day_id = None
        for i in range(6):
            date_str = (monday + datetime.timedelta(days=i)).isoformat()
            conn.execute(
                'DELETE FROM schedule_days WHERE group_name = ? AND date = ?',
                (name, date_str))
            cur = conn.execute(
                'INSERT INTO schedule_days (day_name, date, sort_order, group_name) VALUES (?, ?, ?, ?)',
                (WEEKDAY_NAMES[i], date_str, i, name)
            )
            if i == 0:
                day_id = cur.lastrowid

        if day_id is not None:
            conn.execute(
                'DELETE FROM lessons WHERE day_id = ? AND deleted_at IS NULL',
                (day_id,))
            conn.execute(
                'INSERT INTO lessons (day_id, period, subject_id, teacher_id, classroom_id, group_id) VALUES (?, ?, ?, ?, ?, ?)',
                (day_id, 1, sid, tid, cid, gid)
            )
        conn.commit()
    finally:
        conn.close()


@pytest.fixture(scope='session')
def e2e_server():
    """Поднимает Flask-приложение на отдельном порту с временной копией рабочей БД."""
    tmp = tempfile.mkdtemp(prefix='e2e_')
    data_dir = os.path.join(tmp, 'data')
    os.makedirs(data_dir, exist_ok=True)
    src = os.path.join(PROJECT_ROOT, 'data', 'schedule.db')
    env = dict(os.environ)
    env.update({
        'SCHEDULE_DATA_DIR': data_dir,
        'SCHEDULE_BACKUPS_DIR': os.path.join(tmp, 'backups'),
        'SCHEDULE_PASSWORD': 'TestPass123!',
        'SCHEDULE_SECRET_KEY': 'e2e-secret-key',
        'FLASK_HOST': '127.0.0.1',
        'FLASK_PORT': str(E2E_PORT),
        'FLASK_DEBUG': '0',
        'PYTHONUNBUFFERED': '1',
    })
    if os.path.exists(src):
        shutil.copy2(src, os.path.join(data_dir, 'schedule.db'))
        # Копия боевой БД может быть на старой ревизии — догоняем миграции,
        # иначе запросы с новыми колонками (classroom_id_2) падают.
        subprocess.run(
            [sys.executable, '-c', 'from db import run_alembic_upgrade; run_alembic_upgrade()'],
            cwd=PROJECT_ROOT, env=env, check=True, capture_output=True)
        _seed_fixture_schedule(os.path.join(data_dir, 'schedule.db'))
    runner = (
        'from app import app; '
        f"app.run(host='127.0.0.1', port={E2E_PORT}, use_reloader=False, threaded=True)"
    )
    proc = subprocess.Popen([sys.executable, '-c', runner], cwd=PROJECT_ROOT, env=env)
    try:
        _wait_ready()
        yield BASE_URL
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()
        shutil.rmtree(tmp, ignore_errors=True)
