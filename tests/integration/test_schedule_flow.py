class TestFullScheduleCycle:
    """Создание группы → добавление недели → добавление уроков → получение расписания."""

    def test_create_week_and_lessons_then_read_schedule(self, client, refs):
        csrf = refs
        h = {'X-CSRF-Token': csrf}
        monday = '2026-09-07'

        days = [
            {'day_name': 'Понедельник', 'date': '2026-09-07', 'group_name': 'ИС-31'},
            {'day_name': 'Вторник',     'date': '2026-09-08', 'group_name': 'ИС-31'},
            {'day_name': 'Среда',       'date': '2026-09-09', 'group_name': 'ИС-31'},
            {'day_name': 'Четверг',     'date': '2026-09-10', 'group_name': 'ИС-31'},
            {'day_name': 'Пятница',     'date': '2026-09-11', 'group_name': 'ИС-31'},
            {'day_name': 'Суббота',     'date': '2026-09-12', 'group_name': 'ИС-31'},
        ]
        resp = client.post('/api/days/batch', json={'days': days}, headers=h)
        assert resp.status_code == 201
        day_ids = resp.get_json()['ids']
        assert len(day_ids) == 6

        resp = client.post(f'/api/days/{day_ids[0]}/lessons', json={
            'period': 1, 'subject_id': 1, 'teacher_id': 1, 'classroom_id': 1, 'group_id': 1
        }, headers=h)
        assert resp.status_code == 201
        lesson1_id = resp.get_json()['id']

        resp = client.post(f'/api/days/{day_ids[0]}/lessons', json={
            'period': 2, 'subject_id': 2, 'teacher_id': 2, 'classroom_id': 1, 'group_id': 1
        }, headers=h)
        assert resp.status_code == 201
        lesson2_id = resp.get_json()['id']

        resp = client.post(f'/api/days/{day_ids[1]}/lessons', json={
            'period': 1, 'subject_id': 3, 'teacher_id': 1, 'classroom_id': 2, 'group_id': 1
        }, headers=h)
        assert resp.status_code == 201
        lesson3_id = resp.get_json()['id']

        resp = client.get(f'/api/schedule-table?group=ИС-31&monday={monday}')
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['week_exists'] is True
        assert len(data['days']) == 6
        assert data['days'][0]['date'] == '2026-09-07'
        assert data['days'][0]['day_id'] == day_ids[0]
        assert data['days'][1]['date'] == '2026-09-08'

        periods = data['periods']
        mon_period_1 = periods[0]['lessons'].get('2026-09-07', [])
        assert len(mon_period_1) == 1
        assert mon_period_1[0]['id'] == lesson1_id
        assert mon_period_1[0]['subject'] == 'Математика'
        assert mon_period_1[0]['teacher'] == 'Иванов И.И.'

        mon_period_2 = periods[1]['lessons'].get('2026-09-07', [])
        assert len(mon_period_2) == 1
        assert mon_period_2[0]['id'] == lesson2_id
        assert mon_period_2[0]['subject'] == 'Физика'

        tue_period_1 = periods[0]['lessons'].get('2026-09-08', [])
        assert len(tue_period_1) == 1
        assert tue_period_1[0]['id'] == lesson3_id
        assert tue_period_1[0]['subject'] == 'Информатика'

        empty_dates = ['2026-09-09', '2026-09-10', '2026-09-11', '2026-09-12']
        for dt in empty_dates:
            assert periods[0]['lessons'].get(dt, []) == []

        resp = client.get(f'/api/teacher-schedule-table?teacher_id=1&monday={monday}')
        assert resp.status_code == 200
        data = resp.get_json()
        assert len(data['days']) == 6
        p0 = data['periods']
        assert len(p0[0]['lessons'].get('2026-09-07', [])) == 1
        assert len(p0[0]['lessons'].get('2026-09-08', [])) == 1

        resp = client.get(f'/api/classroom-schedule-table?classroom_id=1&monday={monday}')
        assert resp.status_code == 200
        data = resp.get_json()
        p1 = data['periods']
        assert len(p1[0]['lessons'].get('2026-09-07', [])) == 1
        assert len(p1[1]['lessons'].get('2026-09-07', [])) == 1

    def test_multiple_groups_separate_schedules(self, client, refs):
        csrf = refs
        h = {'X-CSRF-Token': csrf}

        days_a = [
            {'day_name': 'Понедельник', 'date': '2026-09-07', 'group_name': 'ИС-31'},
            {'day_name': 'Вторник',     'date': '2026-09-08', 'group_name': 'ИС-31'},
        ]
        resp = client.post('/api/days/batch', json={'days': days_a}, headers=h)
        a_ids = resp.get_json()['ids']

        days_b = [
            {'day_name': 'Понедельник', 'date': '2026-09-07', 'group_name': 'БО-11'},
            {'day_name': 'Вторник',     'date': '2026-09-08', 'group_name': 'БО-11'},
        ]
        resp = client.post('/api/days/batch', json={'days': days_b}, headers=h)
        b_ids = resp.get_json()['ids']

        client.post(f'/api/days/{a_ids[0]}/lessons', json={
            'period': 1, 'subject_id': 1, 'teacher_id': 1, 'classroom_id': 1, 'group_id': 1
        }, headers=h)
        client.post(f'/api/days/{b_ids[0]}/lessons', json={
            'period': 1, 'subject_id': 2, 'teacher_id': 2, 'classroom_id': 2, 'group_id': 2
        }, headers=h)

        resp_a = client.get('/api/schedule-table?group=ИС-31&monday=2026-09-07')
        resp_b = client.get('/api/schedule-table?group=БО-11&monday=2026-09-07')

        assert resp_a.get_json()['periods'][0]['lessons']['2026-09-07'][0]['subject'] == 'Математика'
        assert resp_b.get_json()['periods'][0]['lessons']['2026-09-07'][0]['subject'] == 'Физика'

    def test_update_lesson_preserves_other_lessons(self, client, refs):
        csrf = refs
        h = {'X-CSRF-Token': csrf}
        monday = '2026-09-07'

        client.post('/api/days/batch', json={'days': [
            {'day_name': 'Понедельник', 'date': '2026-09-07', 'group_name': 'ИС-31'}
        ]}, headers=h)
        day_id = client.get('/api/days?group=ИС-31').get_json()[0]['id']

        r1 = client.post(f'/api/days/{day_id}/lessons', json={
            'period': 1, 'subject_id': 1, 'teacher_id': 1, 'classroom_id': 1, 'group_id': 1
        }, headers=h)
        l1 = r1.get_json()['id']

        r2 = client.post(f'/api/days/{day_id}/lessons', json={
            'period': 2, 'subject_id': 2, 'teacher_id': 2, 'classroom_id': 2, 'group_id': 1
        }, headers=h)
        l2 = r2.get_json()['id']

        client.put(f'/api/lessons/{l1}', json={
            'subject_id': 3, 'teacher_id': 1, 'classroom_id': 3, 'group_id': 1
        }, headers=h)

        data = client.get(f'/api/schedule-table?group=ИС-31&monday={monday}').get_json()
        p0 = data['periods'][0]['lessons']['2026-09-07']
        p1 = data['periods'][1]['lessons']['2026-09-07']
        assert p0[0]['subject'] == 'Информатика'
        assert p0[0]['classroom'] == '303'
        assert p1[0]['id'] == l2
        assert p1[0]['subject'] == 'Физика'
