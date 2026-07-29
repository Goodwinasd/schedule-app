class TestConflictScenarios:
    """Проверка конфликтов: учитель, аудитория, дубликат — и восстановление после удаления."""

    def test_teacher_conflict_rejected_then_resolved(self, client, refs):
        csrf = refs
        h = {'X-CSRF-Token': csrf}

        client.post('/api/days/batch', json={'days': [
            {'day_name': 'Понедельник', 'date': '2026-09-07', 'group_name': 'ИС-31'}
        ]}, headers=h)
        day_id = client.get('/api/days?group=ИС-31').get_json()[0]['id']

        r1 = client.post(f'/api/days/{day_id}/lessons', json={
            'period': 1, 'subject_id': 1, 'teacher_id': 1, 'classroom_id': 1, 'group_id': 1
        }, headers=h)
        assert r1.status_code == 201

        r2 = client.post(f'/api/days/{day_id}/lessons', json={
            'period': 1, 'subject_id': 2, 'teacher_id': 1, 'classroom_id': 2, 'group_id': 1
        }, headers=h)
        assert r2.status_code == 409

        r3 = client.post('/api/validate', json={
            'day_id': day_id, 'period': 1, 'teacher_id': 1
        }, headers=h)
        data = r3.get_json()
        assert data['blocking'] is True
        assert any(w['type'] == 'teacher_conflict' for w in data['warnings'])

        client.delete('/api/lessons/1', headers=h)

        r4 = client.post(f'/api/days/{day_id}/lessons', json={
            'period': 1, 'subject_id': 2, 'teacher_id': 1, 'classroom_id': 2, 'group_id': 1
        }, headers=h)
        assert r4.status_code == 201

    def test_classroom_conflict_rejected_then_resolved(self, client, refs):
        csrf = refs
        h = {'X-CSRF-Token': csrf}

        client.post('/api/days/batch', json={'days': [
            {'day_name': 'Понедельник', 'date': '2026-09-07', 'group_name': 'ИС-31'}
        ]}, headers=h)
        day_id = client.get('/api/days?group=ИС-31').get_json()[0]['id']

        r1 = client.post(f'/api/days/{day_id}/lessons', json={
            'period': 1, 'subject_id': 1, 'teacher_id': 1, 'classroom_id': 1, 'group_id': 1
        }, headers=h)
        assert r1.status_code == 201

        r2 = client.post(f'/api/days/{day_id}/lessons', json={
            'period': 1, 'subject_id': 2, 'teacher_id': 2, 'classroom_id': 1, 'group_id': 1
        }, headers=h)
        assert r2.status_code == 409

        r3 = client.post('/api/validate', json={
            'day_id': day_id, 'period': 1, 'classroom_id': 1
        }, headers=h)
        data = r3.get_json()
        assert data['blocking'] is True
        assert any(w['type'] == 'classroom_conflict' for w in data['warnings'])

        client.delete('/api/lessons/1', headers=h)

        r4 = client.post(f'/api/days/{day_id}/lessons', json={
            'period': 1, 'subject_id': 2, 'teacher_id': 2, 'classroom_id': 1, 'group_id': 1
        }, headers=h)
        assert r4.status_code == 201

    def test_duplicate_lesson_rejected(self, client, refs):
        csrf = refs
        h = {'X-CSRF-Token': csrf}

        client.post('/api/days/batch', json={'days': [
            {'day_name': 'Понедельник', 'date': '2026-09-07', 'group_name': 'ИС-31'}
        ]}, headers=h)
        day_id = client.get('/api/days?group=ИС-31').get_json()[0]['id']

        r1 = client.post(f'/api/days/{day_id}/lessons', json={
            'period': 1, 'subject_id': 1, 'teacher_id': 1, 'classroom_id': 1, 'group_id': 1
        }, headers=h)
        assert r1.status_code == 201

        r2 = client.post(f'/api/days/{day_id}/lessons', json={
            'period': 1, 'subject_id': 1, 'teacher_id': 2, 'classroom_id': 2, 'group_id': 1
        }, headers=h)
        assert r2.status_code == 409

        r3 = client.post('/api/validate', json={
            'day_id': day_id, 'period': 1, 'subject_id': 1, 'group_id': 1
        }, headers=h)
        data = r3.get_json()
        assert data['blocking'] is True

    def test_delete_and_restore_week_cascades_lessons(self, client, refs):
        csrf = refs
        h = {'X-CSRF-Token': csrf}

        client.post('/api/days/batch', json={'days': [
            {'day_name': 'Понедельник', 'date': '2026-09-07', 'group_name': 'ИС-31'}
        ]}, headers=h)
        day_id = client.get('/api/days?group=ИС-31').get_json()[0]['id']

        client.post(f'/api/days/{day_id}/lessons', json={
            'period': 1, 'subject_id': 1, 'teacher_id': 1, 'classroom_id': 1, 'group_id': 1
        }, headers=h)
        client.post(f'/api/days/{day_id}/lessons', json={
            'period': 2, 'subject_id': 2, 'teacher_id': 2, 'classroom_id': 2, 'group_id': 1
        }, headers=h)

        resp = client.delete('/api/week?monday=2026-09-07&target_type=group&target_id=ИС-31', headers=h)
        assert resp.status_code == 200
        assert resp.get_json()['days_deleted'] == 1

        trash = client.get('/api/trash', headers=h).get_json()
        assert len(trash['days']) == 1
        assert len(trash['lessons']) == 2

        schedule = client.get('/api/schedule-table?group=ИС-31&monday=2026-09-07').get_json()
        assert schedule['week_exists'] is False

        resp = client.post('/api/week/restore?monday=2026-09-07&target_type=group&target_id=ИС-31', headers=h)
        assert resp.status_code == 200
        assert resp.get_json()['days_restored'] == 1

        schedule = client.get('/api/schedule-table?group=ИС-31&monday=2026-09-07').get_json()
        assert schedule['week_exists'] is True
        assert len(schedule['periods'][0]['lessons']['2026-09-07']) == 1
        assert len(schedule['periods'][1]['lessons']['2026-09-07']) == 1
