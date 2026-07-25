import os
import sys
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import db as db_module


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
