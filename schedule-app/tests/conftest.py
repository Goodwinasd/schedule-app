import os
import sys
import tempfile
import pytest
import flask

os.environ['SCHEDULE_PASSWORD'] = 'TestPass123!'
os.environ['SCHEDULE_SECRET_KEY'] = 'test-secret-key-for-testing'

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import config
import db as db_module


@pytest.fixture(scope='session')
def app():
    tmp = tempfile.NamedTemporaryFile(suffix='.db', delete=False)
    tmp.close()
    config.DB_PATH = tmp.name
    config.BACKUPS_DIR = tempfile.mkdtemp()
    config.DEBUG = False
    config.HOST = '127.0.0.1'
    config.PORT = 5000

    db_module.init_db()

    from app import app as flask_app
    flask_app.testing = True
    flask_app.secret_key = 'test-secret'

    yield flask_app

    import gc, sqlite3
    for obj in gc.get_objects():
        if isinstance(obj, sqlite3.Connection):
            try:
                obj.close()
            except:
                pass
    try:
        os.unlink(tmp.name)
    except PermissionError:
        pass
    import shutil
    shutil.rmtree(config.BACKUPS_DIR, ignore_errors=True)


@pytest.fixture(autouse=True)
def clean_db_before_test():
    _clean_tables()
    yield


@pytest.fixture
def admin_csrf(client):
    with client.session_transaction() as sess:
        sess['is_admin'] = True
        sess['csrf_token'] = 'test-csrf'
    return 'test-csrf'


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def db():
    yield db_module
    _clean_tables()


def _clean_tables():
    import sqlite3
    try:
        conn = db_module.get_db()
        tables = ['lesson_history', 'lessons', 'schedule_days', 'groups_list',
                  'classrooms_list', 'teachers', 'subjects', 'excluded_dates']
        for t in tables:
            conn.execute(f'DELETE FROM {t}')
        conn.commit()
        conn.close()
    except sqlite3.OperationalError:
        pass


def _seed_refs():
    conn = db_module.get_db()
    conn.execute("INSERT INTO teachers (id, name) VALUES (1, 'Иванов И.И.')")
    conn.execute("INSERT INTO teachers (id, name) VALUES (2, 'Петров П.П.')")
    conn.execute("INSERT INTO subjects (id, name, default_teacher_id) VALUES (1, 'Математика', 1)")
    conn.execute("INSERT INTO subjects (id, name) VALUES (2, 'Физика')")
    conn.execute("INSERT INTO classrooms_list (id, name) VALUES (1, '101')")
    conn.execute("INSERT INTO classrooms_list (id, name) VALUES (2, '202')")
    conn.execute("INSERT INTO groups_list (id, name, course, is_distance) VALUES (1, 'Группа-1', 1, 0)")
    conn.execute("INSERT INTO groups_list (id, name, course, is_distance) VALUES (2, 'Группа-Д', 3, 1)")
    conn.commit()
    conn.close()


def _seed_days():
    conn = db_module.get_db()
    conn.execute("INSERT INTO schedule_days (id, day_name, date, sort_order, group_name) VALUES (1, 'Понедельник', '2026-09-07', 0, 'Группа-1')")
    conn.execute("INSERT INTO schedule_days (id, day_name, date, sort_order, group_name) VALUES (2, 'Вторник', '2026-09-08', 1, 'Группа-1')")
    conn.execute("INSERT INTO schedule_days (id, day_name, date, sort_order, group_name) VALUES (3, 'Понедельник', '2026-09-14', 2, 'Группа-1')")
    conn.commit()
    conn.close()


def _seed_lessons():
    conn = db_module.get_db()
    conn.execute('''INSERT INTO lessons (id, day_id, period, subject_id, teacher_id, classroom_id, group_id)
                    VALUES (1, 1, 1, 1, 1, 1, 1)''')
    conn.execute('''INSERT INTO lessons (id, day_id, period, subject_id, teacher_id, classroom_id, group_id)
                    VALUES (2, 1, 2, 2, 2, 2, 1)''')
    conn.commit()
    conn.close()


@pytest.fixture
def seed_refs():
    _clean_tables()
    _seed_refs()
    yield


@pytest.fixture
def seed_days(seed_refs):
    _seed_days()
    yield


@pytest.fixture
def seed_lessons(seed_days):
    _seed_lessons()
    yield



