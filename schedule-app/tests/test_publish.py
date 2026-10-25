"""Тесты режима «Черновик / Опубликовано» для расписания.

Разграничение видимости: публичный пользователь видит только опубликованные
дни (is_published = 1), админ — все дни с флагом is_published в ответе.
Ручки переключения: POST /api/days/<id>/toggle-publish и POST /api/week/publish.
"""

import pytest


@pytest.fixture
def draft_day(client, db):
    """Понедельник (2026-09-07) → черновик, остальные дни недели опубликованы."""
    conn = db.get_db()
    conn.execute("UPDATE schedule_days SET is_published = 0 WHERE id = 1")
    conn.commit()
    conn.close()


class TestPublishVisibility:
    def test_public_sees_only_published_days(self, client, seed_days, draft_day):
        resp = client.get('/api/schedule-table?group=Группа-1&monday=2026-09-07')
        assert resp.status_code == 200
        data = resp.get_json()
        dates = [d['date'] for d in data['days'] if d['day_id'] is not None]
        assert '2026-09-07' not in dates, 'Черновик (Пн) не должен быть виден публике'
        assert '2026-09-08' in dates, 'Опубликованный день (Вт) должен быть виден'
        for d in data['days']:
            if d['day_id'] is not None:
                assert d['is_published'] is True

    def test_public_all_published(self, client, seed_lessons):
        resp = client.get('/api/schedule-table?group=Группа-1&monday=2026-09-07')
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['days'][0]['day_id'] == 1
        assert data['days'][0]['is_published'] is True

    def test_admin_sees_draft_with_flag(self, client, seed_days, draft_day, admin_csrf):
        resp = client.get('/api/schedule-table?group=Группа-1&monday=2026-09-07')
        assert resp.status_code == 200
        data = resp.get_json()
        by_date = {d['date']: d for d in data['days']}
        assert by_date['2026-09-07']['day_id'] == 1
        assert by_date['2026-09-07']['is_published'] is False
        assert by_date['2026-09-08']['is_published'] is True


class TestTogglePublish:
    def test_toggle_day(self, client, seed_days, admin_csrf):
        h = {'X-CSRF-Token': admin_csrf}
        resp = client.post('/api/days/1/toggle-publish', headers=h)
        assert resp.status_code == 200
        assert resp.get_json()['is_published'] == 0
        resp = client.post('/api/days/1/toggle-publish', headers=h)
        assert resp.get_json()['is_published'] == 1

    def test_toggle_day_requires_admin(self, client, seed_days):
        resp = client.post('/api/days/1/toggle-publish')
        assert resp.status_code in (401, 403)

    def test_toggle_day_not_found(self, client, seed_days, admin_csrf):
        resp = client.post('/api/days/9999/toggle-publish', headers={'X-CSRF-Token': admin_csrf})
        assert resp.status_code == 404

    def test_publish_week(self, client, db, seed_days, admin_csrf):
        h = {'X-CSRF-Token': admin_csrf}
        conn = db.get_db()
        conn.execute("UPDATE schedule_days SET is_published = 0")
        conn.commit()
        conn.close()

        resp = client.post('/api/week/publish', json={
            'group_name': 'Группа-1', 'monday': '2026-09-07', 'is_published': True
        }, headers=h)
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['is_published'] == 1
        assert data['message'] == 'Неделя опубликована'

        conn = db.get_db()
        rows = conn.execute(
            "SELECT date, is_published FROM schedule_days ORDER BY date"
        ).fetchall()
        conn.close()
        week_dates = {'2026-09-07', '2026-09-08'}
        for r in rows:
            if r['date'] in week_dates:
                assert r['is_published'] == 1, f'Данная неделя должна быть опубликована: {r["date"]}'
            else:
                assert r['is_published'] == 0, f'Другая неделя не должна затрагиваться: {r["date"]}'

    def test_unpublish_week(self, client, db, seed_days, admin_csrf):
        """Кнопка «В черновик» (is_published=0) должна переводить неделю в черновик."""
        h = {'X-CSRF-Token': admin_csrf}
        resp = client.post('/api/week/publish', json={
            'group_name': 'Группа-1', 'monday': '2026-09-07', 'is_published': False
        }, headers=h)
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['is_published'] == 0
        assert data['message'] == 'Неделя переведена в черновик'

        conn = db.get_db()
        rows = conn.execute(
            "SELECT date, is_published FROM schedule_days WHERE date IN ('2026-09-07', '2026-09-08')"
        ).fetchall()
        conn.close()
        assert all(r['is_published'] == 0 for r in rows), 'Неделя должна быть в черновике после is_published=0'

    def test_publish_week_requires_admin(self, client, seed_days):
        resp = client.post('/api/week/publish', json={
            'group_name': 'Группа-1', 'monday': '2026-09-07', 'is_published': True
        })
        assert resp.status_code in (401, 403)

    def test_publish_week_missing_params(self, client, admin_csrf):
        resp = client.post('/api/week/publish', json={}, headers={'X-CSRF-Token': admin_csrf})
        assert resp.status_code == 400

    def test_toggle_then_public_visibility(self, client, seed_days, admin_csrf):
        """После перевода дня в черновик публике он скрывается."""
        h = {'X-CSRF-Token': admin_csrf}
        client.post('/api/days/1/toggle-publish', headers=h)

        anon = client.application.test_client()
        resp = anon.get('/api/schedule-table?group=Группа-1&monday=2026-09-07')
        data = resp.get_json()
        dates = [d['date'] for d in data['days'] if d['day_id'] is not None]
        assert '2026-09-07' not in dates


class TestFreshWeeksDraftByDefault:
    """Свежесозданные недели/дни хранятся как Черновик (is_published = 0) и
    не видны публике, пока админ не выполнит публикацию."""

    def test_fresh_week_invisible_to_public_until_published(self, client, seed_days, admin_csrf):
        h = {'X-CSRF-Token': admin_csrf}
        resp = client.post('/api/days/batch', json={'days': [
            {'day_name': 'Понедельник', 'date': '2026-09-21', 'group_name': 'Группа-1'},
            {'day_name': 'Вторник', 'date': '2026-09-22', 'group_name': 'Группа-1'},
        ]}, headers=h)
        assert resp.status_code == 201

        # Публика не видит свежую неделю: day_id у дней пуст
        anon = client.application.test_client()
        resp = anon.get('/api/schedule-table?group=Группа-1&monday=2026-09-21')
        assert resp.status_code == 200
        data = resp.get_json()
        dates = [d['date'] for d in data['days'] if d['day_id'] is not None]
        assert dates == [], 'Черновая неделя не должна быть видна публике'

        # Админ публикует неделю → она появляется у публики
        resp = client.post('/api/week/publish', json={
            'group_name': 'Группа-1', 'monday': '2026-09-21', 'is_published': True
        }, headers=h)
        assert resp.status_code == 200
        resp = anon.get('/api/schedule-table?group=Группа-1&monday=2026-09-21')
        data = resp.get_json()
        dates = [d['date'] for d in data['days'] if d['day_id'] is not None]
        assert '2026-09-21' in dates, 'Опубликованная неделя должна быть видна публике'

    def test_generate_creates_days_as_draft(self, client, seed_refs, db, admin_csrf):
        """Дни, созданные автогенератором, сохраняются как Черновик (is_published = 0)."""
        h = {'X-CSRF-Token': admin_csrf}
        resp = client.post('/api/curriculum', json={
            'group_id': 1, 'subject_id': 1, 'teacher_id': 1,
            'semester': 1, 'total_hours': 72,
        }, headers=h)
        assert resp.status_code == 201
        resp = client.post('/api/schedule/generate', json={
            'group_id': 1, 'semester': 1, 'monday': '2026-09-07', 'week_count': 1,
        }, headers=h)
        assert resp.status_code == 200

        conn = db.get_db()
        rows = conn.execute(
            "SELECT is_published FROM schedule_days WHERE group_name = 'Группа-1'"
        ).fetchall()
        conn.close()
        assert rows, 'Генератор не создал ни одного дня'
        assert all(r['is_published'] == 0 for r in rows), 'Сгенерированные дни должны быть в Черновике'