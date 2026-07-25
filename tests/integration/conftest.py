import os
import sys
import tempfile
import gc

import pytest

os.environ['SCHEDULE_PASSWORD'] = 'TestPass123!'
os.environ['SCHEDULE_SECRET_KEY'] = 'test-secret-key-for-integration'

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

import config
import db as db_module


@pytest.fixture(scope='session')
def app():
    tmp_db = tempfile.NamedTemporaryFile(suffix='.db', delete=False)
    tmp_db.close()
    tmp_backups = tempfile.mkdtemp()

    config.DB_PATH = tmp_db.name
    config.BACKUPS_DIR = tmp_backups
    config.DEBUG = False

    db_module.init_db()

    from app import app as flask_app
    flask_app.testing = True
    flask_app.secret_key = 'test-secret'

    yield flask_app

    for obj in gc.get_objects():
        if isinstance(obj, type(db_module.get_db())):
            try:
                obj.close()
            except:
                pass
    try:
        os.unlink(tmp_db.name)
    except PermissionError:
        pass
    import shutil
    shutil.rmtree(tmp_backups, ignore_errors=True)


@pytest.fixture
def client(app):
    return app.test_client()


def _clean_tables():
    conn = db_module.get_db()
    conn.execute("PRAGMA foreign_keys = OFF")
    tables = ['lesson_history', 'lessons', 'schedule_days', 'groups_list',
              'classrooms_list', 'teachers', 'subjects', 'excluded_dates']
    for t in tables:
        conn.execute(f'DELETE FROM {t}')
    conn.execute("DELETE FROM sqlite_sequence")
    conn.execute("PRAGMA foreign_keys = ON")
    conn.commit()
    conn.close()


@pytest.fixture(autouse=True)
def clean_db():
    _clean_tables()


@pytest.fixture
def admin_csrf(client):
    with client.session_transaction() as sess:
        sess['is_admin'] = True
        sess['csrf_token'] = 'intg-csrf'
    return 'intg-csrf'


@pytest.fixture
def refs(admin_csrf, client):
    csrf = admin_csrf
    h = {'X-CSRF-Token': csrf}

    def _post(url, **kw):
        r = client.post(url, **kw, headers=h)
        assert r.status_code == 201, f'{url} failed: {r.status_code} {r.get_json()}'
        return r
    _post('/api/teachers', json={'name': 'Иванов И.И.'})
    _post('/api/teachers', json={'name': 'Петров П.П.'})
    _post('/api/subjects', json={'name': 'Математика'})
    _post('/api/subjects', json={'name': 'Физика'})
    _post('/api/subjects', json={'name': 'Информатика'})
    _post('/api/classrooms', json={'name': '101'})
    _post('/api/classrooms', json={'name': '202'})
    _post('/api/classrooms', json={'name': '303'})
    _post('/api/groups', json={'name': 'ИС-31', 'course': 3})
    _post('/api/groups', json={'name': 'БО-11', 'course': 1})
    return csrf
