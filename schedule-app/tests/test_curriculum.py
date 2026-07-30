"""Tests for curriculum planning and workload balancing."""
import pytest
from schedule_balancer import weekly_pairs, validate_weekly_load


class TestWeeklyPairs:
    def test_72_hours_18_weeks(self):
        assert weekly_pairs(72, 18) == 2  # 72 / (18*2) = 2.0 -> ceil 2

    def test_108_hours_18_weeks(self):
        assert weekly_pairs(108, 18) == 3  # 108 / 36 = 3.0

    def test_144_hours_18_weeks(self):
        assert weekly_pairs(144, 18) == 4  # 144 / 36 = 4.0

    def test_70_hours_18_weeks_ceil(self):
        assert weekly_pairs(70, 18) == 2  # 70/36 = 1.94 -> ceil 2

    def test_36_hours_18_weeks(self):
        assert weekly_pairs(36, 18) == 1


class TestValidateWeeklyLoad:
    def test_ideal_18_pairs(self):
        lessons = {
            '2026-09-07': [1, 2, 3],
            '2026-09-08': [1, 2, 3],
            '2026-09-09': [1, 2, 3],
            '2026-09-10': [1, 2, 3],
            '2026-09-11': [1, 2, 3],
            '2026-09-12': [1, 2, 3],
        }
        result = validate_weekly_load(lessons)
        assert result['total_pairs'] == 18
        assert result['total_hours'] == 36
        assert result['status'] == 'ok'
        assert len(result['violations']) == 0

    def test_overload_20_pairs(self):
        lessons = {f'2026-09-{d:02d}': [1, 2, 3, 4] for d in range(7, 12)}
        result = validate_weekly_load(lessons)
        assert result['total_pairs'] >= 20
        assert result['status'] == 'overload'
        assert any('Превышение' in v for v in result['violations'])

    def test_too_many_in_one_day(self):
        lessons = {
            '2026-09-07': [1, 2, 3, 4, 5],
            '2026-09-08': [1, 2],
            '2026-09-09': [1, 2],
        }
        result = validate_weekly_load(lessons)
        assert result['status'] == 'overload'
        assert any('5 пар' in v for v in result['violations'])

    def test_empty_week(self):
        result = validate_weekly_load({})
        assert result['total_pairs'] == 0
        assert result['status'] == 'ok'

    def test_curriculum_api_create_and_delete(self, client, seed_refs, admin_csrf):
        h = {'X-CSRF-Token': admin_csrf}
        resp = client.post('/api/curriculum', json={
            'group_id': 1, 'subject_id': 1, 'teacher_id': 1,
            'semester': 1, 'total_hours': 72,
        }, headers=h)
        assert resp.status_code == 201
        data = resp.get_json()
        assert data['id'] > 0

        resp = client.get('/api/curriculum?group_id=1', headers=h)
        assert resp.status_code == 200
        items = resp.get_json()
        assert len(items) >= 1

        resp = client.delete(f'/api/curriculum/{items[0]["id"]}', headers=h)
        assert resp.status_code == 200

    def test_curriculum_duplicate_rejected(self, client, seed_refs, admin_csrf):
        h = {'X-CSRF-Token': admin_csrf}
        resp = client.post('/api/curriculum', json={
            'group_id': 1, 'subject_id': 1, 'semester': 1, 'total_hours': 72,
        }, headers=h)
        assert resp.status_code == 201
        resp = client.post('/api/curriculum', json={
            'group_id': 1, 'subject_id': 1, 'semester': 1, 'total_hours': 72,
        }, headers=h)
        assert resp.status_code == 409

    def test_workload_endpoint(self, client, seed_lessons, admin_csrf):
        h = {'X-CSRF-Token': admin_csrf}
        resp = client.get('/api/schedule/workload/1?monday=2026-09-07', headers=h)
        assert resp.status_code == 200
        data = resp.get_json()
        assert 'workload' in data
        assert 'plan' in data
