"""Unit-тесты модуля «Специальности» и связи группа <-> специальность."""
import pytest


class TestSeedSpecialties:
    def test_seed_inserts_defaults(self, db, app):
        db.seed_specialties()
        conn = db.get_db()
        rows = conn.execute("SELECT code, name, qualification FROM specialties WHERE deleted_at IS NULL").fetchall()
        conn.close()
        codes = {r['code'] for r in rows}
        assert {'40.02.02', '40.02.04', '38.02.01', '38.02.03'} <= codes
        assert len(rows) == 6

    def test_seed_is_idempotent_when_not_empty(self, db):
        db.seed_specialties()
        db.seed_specialties()
        conn = db.get_db()
        count = conn.execute("SELECT COUNT(*) FROM specialties WHERE deleted_at IS NULL").fetchone()[0]
        conn.close()
        assert count == 6


class TestSpecialtiesCrud:
    ENDPOINT = '/api/specialties'

    def test_list_empty(self, client):
        resp = client.get(self.ENDPOINT)
        assert resp.status_code == 200
        assert resp.get_json() == []

    def test_create(self, client, admin_csrf):
        resp = client.post(self.ENDPOINT, json={'code': '40.02.04', 'name': 'Юриспруденция', 'qualification': 'Юрист'},
                           headers={'X-CSRF-Token': admin_csrf})
        assert resp.status_code == 201
        data = resp.get_json()
        assert data['code'] == '40.02.04'
        assert data['name'] == 'Юриспруденция'
        assert data['qualification'] == 'Юрист'
        assert data['id'] > 0

    def test_create_requires_code(self, client, admin_csrf):
        resp = client.post(self.ENDPOINT, json={'name': 'Без кода'},
                           headers={'X-CSRF-Token': admin_csrf})
        assert resp.status_code == 400

    def test_create_requires_name(self, client, admin_csrf):
        resp = client.post(self.ENDPOINT, json={'code': '38.02.03'},
                           headers={'X-CSRF-Token': admin_csrf})
        assert resp.status_code == 400

    def test_create_duplicate(self, client, admin_csrf):
        payload = {'code': '40.02.02', 'name': 'Правоохранительная деятельность'}
        client.post(self.ENDPOINT, json=payload, headers={'X-CSRF-Token': admin_csrf})
        resp = client.post(self.ENDPOINT, json=payload, headers={'X-CSRF-Token': admin_csrf})
        assert resp.status_code == 409

    def test_create_unauthorized(self, client):
        resp = client.post(self.ENDPOINT, json={'code': '1', 'name': 'Test'})
        assert resp.status_code == 403

    def test_update(self, client, admin_csrf):
        created = client.post(self.ENDPOINT, json={'code': '40.02.04', 'name': 'Юриспруденция'},
                              headers={'X-CSRF-Token': admin_csrf}).get_json()
        resp = client.put(f'{self.ENDPOINT}/{created["id"]}',
                          json={'code': '38.02.01', 'name': 'Экономика', 'qualification': 'Бухгалтер'},
                          headers={'X-CSRF-Token': admin_csrf})
        assert resp.status_code == 200
        assert resp.get_json()['success'] is True
        items = client.get(self.ENDPOINT).get_json()
        updated = next(i for i in items if i['id'] == created['id'])
        assert updated['code'] == '38.02.01'
        assert updated['qualification'] == 'Бухгалтер'

    def test_update_missing_code(self, client, admin_csrf):
        created = client.post(self.ENDPOINT, json={'code': '40.02.04', 'name': 'Юриспруденция'},
                              headers={'X-CSRF-Token': admin_csrf}).get_json()
        resp = client.put(f'{self.ENDPOINT}/{created["id"]}', json={'name': 'X'},
                          headers={'X-CSRF-Token': admin_csrf})
        assert resp.status_code == 400

    def test_delete_soft(self, client, admin_csrf):
        created = client.post(self.ENDPOINT, json={'code': '40.02.04', 'name': 'Юриспруденция'},
                              headers={'X-CSRF-Token': admin_csrf}).get_json()
        resp = client.delete(f'{self.ENDPOINT}/{created["id"]}', headers={'X-CSRF-Token': admin_csrf})
        assert resp.status_code == 200
        items = client.get(self.ENDPOINT).get_json()
        assert all(i['id'] != created['id'] for i in items)

    def test_delete_used_by_group_returns_409(self, client, admin_csrf):
        sp = client.post(self.ENDPOINT, json={'code': '40.02.04', 'name': 'Юриспруденция'},
                         headers={'X-CSRF-Token': admin_csrf}).get_json()
        client.post('/api/groups', json={'name': 'Гр-Юр', 'specialty_id': sp['id']},
                    headers={'X-CSRF-Token': admin_csrf})
        resp = client.delete(f'{self.ENDPOINT}/{sp["id"]}', headers={'X-CSRF-Token': admin_csrf})
        assert resp.status_code == 409

    def test_restore(self, client, admin_csrf):
        created = client.post(self.ENDPOINT, json={'code': '40.02.04', 'name': 'Юриспруденция'},
                              headers={'X-CSRF-Token': admin_csrf}).get_json()
        client.delete(f'{self.ENDPOINT}/{created["id"]}', headers={'X-CSRF-Token': admin_csrf})
        resp = client.post(f'{self.ENDPOINT}/{created["id"]}/restore', headers={'X-CSRF-Token': admin_csrf})
        assert resp.status_code == 200
        items = client.get(self.ENDPOINT).get_json()
        assert any(i['id'] == created['id'] for i in items)

    def test_restore_requires_admin(self, client):
        resp = client.post(f'{self.ENDPOINT}/1/restore')
        assert resp.status_code == 403

    def test_list_not_including_deleted(self, client, admin_csrf):
        a = client.post(self.ENDPOINT, json={'code': '1', 'name': 'А'},
                        headers={'X-CSRF-Token': admin_csrf}).get_json()
        client.post(self.ENDPOINT, json={'code': '2', 'name': 'Б'},
                    headers={'X-CSRF-Token': admin_csrf})
        client.delete(f'{self.ENDPOINT}/{a["id"]}', headers={'X-CSRF-Token': admin_csrf})
        items = client.get(self.ENDPOINT).get_json()
        assert all(i['id'] != a['id'] for i in items)
        assert len(items) == 1


class TestGroupSpecialtyLink:
    def test_create_group_with_specialty(self, client, admin_csrf):
        sp = client.post('/api/specialties', json={'code': '40.02.04', 'name': 'Юриспруденция'},
                         headers={'X-CSRF-Token': admin_csrf}).get_json()
        resp = client.post('/api/groups', json={'name': 'ЮР-21', 'specialty_id': sp['id']},
                           headers={'X-CSRF-Token': admin_csrf})
        assert resp.status_code == 201
        assert resp.get_json()['specialty_id'] == sp['id']
        groups = client.get('/api/groups').get_json()
        g = next(x for x in groups if x['name'] == 'ЮР-21')
        assert g['specialty_id'] == sp['id']
        assert g['specialty_code'] == '40.02.04'
        assert g['specialty_name'] == 'Юриспруденция'

    def test_create_group_without_specialty(self, client, admin_csrf):
        resp = client.post('/api/groups', json={'name': 'Гр-1'},
                           headers={'X-CSRF-Token': admin_csrf})
        assert resp.status_code == 201
        assert resp.get_json()['specialty_id'] is None

    def test_create_group_with_invalid_specialty_ignored(self, client, admin_csrf):
        resp = client.post('/api/groups', json={'name': 'Гр-2', 'specialty_id': 9999},
                           headers={'X-CSRF-Token': admin_csrf})
        assert resp.status_code == 201
        assert resp.get_json()['specialty_id'] is None

    def test_update_group_specialty(self, client, admin_csrf):
        sp = client.post('/api/specialties', json={'code': '38.02.01', 'name': 'Экономика'},
                         headers={'X-CSRF-Token': admin_csrf}).get_json()
        created = client.post('/api/groups', json={'name': 'ЭК-11'},
                              headers={'X-CSRF-Token': admin_csrf}).get_json()
        resp = client.put(f"/api/groups/{created['id']}", json={'name': 'ЭК-11', 'specialty_id': sp['id']},
                          headers={'X-CSRF-Token': admin_csrf})
        assert resp.status_code == 200
        groups = client.get('/api/groups').get_json()
        g = next(x for x in groups if x['id'] == created['id'])
        assert g['specialty_id'] == sp['id']
        assert g['specialty_code'] == '38.02.01'

    def test_clear_group_specialty(self, client, admin_csrf):
        sp = client.post('/api/specialties', json={'code': '40.02.04', 'name': 'Юриспруденция'},
                         headers={'X-CSRF-Token': admin_csrf}).get_json()
        created = client.post('/api/groups', json={'name': 'ЮР-31', 'specialty_id': sp['id']},
                              headers={'X-CSRF-Token': admin_csrf}).get_json()
        client.put(f"/api/groups/{created['id']}", json={'name': 'ЮР-31', 'specialty_id': None},
                   headers={'X-CSRF-Token': admin_csrf})
        groups = client.get('/api/groups').get_json()
        g = next(x for x in groups if x['id'] == created['id'])
        assert g['specialty_id'] is None
