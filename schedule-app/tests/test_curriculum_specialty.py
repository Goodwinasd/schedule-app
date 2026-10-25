"""Unit-тесты: поля специальности/цикла/контроля в учебных планах и авто-заполнение плана."""
import pytest


@pytest.fixture
def spec_and_groups(client, admin_csrf):
    """Создать специальность и две группы на ней, вернуть словарь с id."""
    h = {'X-CSRF-Token': admin_csrf}
    sp = client.post('/api/specialties', json={'code': '40.02.04', 'name': 'Юриспруденция', 'qualification': 'Юрист'},
                     headers=h).get_json()
    g1 = client.post('/api/groups', json={'name': 'ЮР-21', 'specialty_id': sp['id']}, headers=h).get_json()
    g2 = client.post('/api/groups', json={'name': 'ЮР-22', 'specialty_id': sp['id']}, headers=h).get_json()
    return {'specialty': sp, 'group_a': g1, 'group_b': g2, 'h': h}


class TestCurriculumSpecialtyFields:
    def test_create_with_cycle_and_control(self, client, seed_refs, admin_csrf):
        sp = client.post('/api/specialties', json={'code': '40.02.04', 'name': 'Юриспруденция'},
                         headers={'X-CSRF-Token': admin_csrf}).get_json()
        resp = client.post('/api/curriculum', json={
            'group_id': 1, 'subject_id': 1, 'semester': 1, 'total_hours': 72,
            'specialty_id': sp['id'], 'cycle': 'ОП', 'control_form': 'Экзамен',
        }, headers={'X-CSRF-Token': admin_csrf})
        assert resp.status_code == 201
        items = client.get('/api/curriculum?group_id=1', headers={'X-CSRF-Token': admin_csrf}).get_json()
        row = next(i for i in items if i['subject_id'] == 1)
        assert row['specialty_id'] == sp['id']
        assert row['cycle'] == 'ОП'
        assert row['control_form'] == 'Экзамен'
        assert row['specialty_code'] == '40.02.04'
        assert row['specialty_name'] == 'Юриспруденция'

    def test_create_without_optional_fields(self, client, seed_refs, admin_csrf):
        resp = client.post('/api/curriculum', json={
            'group_id': 1, 'subject_id': 1, 'semester': 1, 'total_hours': 36,
        }, headers={'X-CSRF-Token': admin_csrf})
        assert resp.status_code == 201
        items = client.get('/api/curriculum?group_id=1', headers={'X-CSRF-Token': admin_csrf}).get_json()
        row = next(i for i in items if i['subject_id'] == 1)
        assert row['specialty_id'] is None
        assert row['cycle'] is None
        assert row['control_form'] is None

    def test_filter_by_specialty(self, client, seed_refs, admin_csrf):
        h = {'X-CSRF-Token': admin_csrf}
        sp = client.post('/api/specialties', json={'code': '38.02.01', 'name': 'Экономика'},
                         headers=h).get_json()
        client.post('/api/curriculum', json={'group_id': 1, 'subject_id': 1, 'semester': 1,
                                             'specialty_id': sp['id']}, headers=h)
        client.post('/api/curriculum', json={'group_id': 1, 'subject_id': 2, 'semester': 1},
                    headers=h)
        items = client.get(f"/api/curriculum?specialty_id={sp['id']}", headers=h).get_json()
        assert len(items) == 1
        assert items[0]['subject_id'] == 1


class TestApplySpecialtyPlan:
    def test_apply_copies_template(self, client, seed_refs, spec_and_groups):
        h = spec_and_groups['h']
        sp = spec_and_groups['specialty']
        ga = spec_and_groups['group_a']['id']
        gb = spec_and_groups['group_b']['id']
        # Шаблон плана: две дисциплины на группе A
        client.post('/api/curriculum', json={'group_id': ga, 'subject_id': 1, 'semester': 1,
                                             'total_hours': 72, 'specialty_id': sp['id'],
                                             'cycle': 'ОП', 'control_form': 'Экзамен'}, headers=h)
        client.post('/api/curriculum', json={'group_id': ga, 'subject_id': 2, 'semester': 1,
                                             'total_hours': 36, 'specialty_id': sp['id'],
                                             'cycle': 'СГ', 'control_form': 'Зачет'}, headers=h)
        resp = client.post('/api/curriculum/apply-specialty-plan?group_id=' + str(gb),
                           json={'semester': 1}, headers=h)
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['created'] == 2
        items = client.get(f'/api/curriculum?group_id={gb}', headers=h).get_json()
        assert len(items) == 2
        rows = {i['subject_id']: i for i in items}
        assert rows[1]['total_hours'] == 72
        assert rows[1]['cycle'] == 'ОП'
        assert rows[1]['control_form'] == 'Экзамен'
        assert rows[1]['specialty_id'] == sp['id']
        assert rows[2]['cycle'] == 'СГ'
        assert rows[2]['control_form'] == 'Зачет'

    def test_apply_skips_existing(self, client, seed_refs, spec_and_groups):
        h = spec_and_groups['h']
        sp = spec_and_groups['specialty']
        ga = spec_and_groups['group_a']['id']
        gb = spec_and_groups['group_b']['id']
        client.post('/api/curriculum', json={'group_id': ga, 'subject_id': 1, 'semester': 1,
                                             'total_hours': 72, 'specialty_id': sp['id']}, headers=h)
        client.post('/api/curriculum', json={'group_id': ga, 'subject_id': 2, 'semester': 1,
                                             'total_hours': 36, 'specialty_id': sp['id']}, headers=h)
        # У группы B уже есть дисциплина 1
        client.post('/api/curriculum', json={'group_id': gb, 'subject_id': 1, 'semester': 1,
                                             'total_hours': 50}, headers=h)
        resp = client.post('/api/curriculum/apply-specialty-plan?group_id=' + str(gb),
                           json={'semester': 1}, headers=h)
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['created'] == 1
        assert data['skipped'] == 1
        items = client.get(f'/api/curriculum?group_id={gb}', headers=h).get_json()
        assert len(items) == 2

    def test_apply_group_without_specialty_errors(self, client, seed_refs, admin_csrf):
        h = {'X-CSRF-Token': admin_csrf}
        g = client.post('/api/groups', json={'name': 'Гр-Без-спец'}, headers=h).get_json()
        resp = client.post('/api/curriculum/apply-specialty-plan?group_id=' + str(g['id']),
                           json={'semester': 1}, headers=h)
        assert resp.status_code == 400
        assert 'специальность' in resp.get_json()['error']

    def test_apply_no_template_errors(self, client, seed_refs, spec_and_groups):
        h = spec_and_groups['h']
        gb = spec_and_groups['group_b']['id']
        resp = client.post('/api/curriculum/apply-specialty-plan?group_id=' + str(gb),
                           json={'semester': 1}, headers=h)
        assert resp.status_code == 400
        assert 'плана' in resp.get_json()['error']

    def test_apply_requires_group(self, client, admin_csrf):
        resp = client.post('/api/curriculum/apply-specialty-plan', json={},
                           headers={'X-CSRF-Token': admin_csrf})
        assert resp.status_code == 400
