class TestSubjects:
    ENDPOINT = '/api/subjects'

    def test_list_empty(self, client):
        resp = client.get(self.ENDPOINT)
        assert resp.status_code == 200
        assert resp.get_json() == []

    def test_create(self, client, seed_refs, admin_csrf):
        resp = client.post(self.ENDPOINT, json={'name': 'История'},
                           headers={'X-CSRF-Token': admin_csrf})
        assert resp.status_code == 201
        data = resp.get_json()
        assert data['name'] == 'История'
        assert data['id'] > 0

    def test_create_duplicate(self, client, seed_refs, admin_csrf):
        client.post(self.ENDPOINT, json={'name': 'История'},
                    headers={'X-CSRF-Token': admin_csrf})
        resp = client.post(self.ENDPOINT, json={'name': 'История'},
                           headers={'X-CSRF-Token': admin_csrf})
        assert resp.status_code == 409

    def test_create_no_name(self, client, seed_refs, admin_csrf):
        resp = client.post(self.ENDPOINT, json={'name': ''},
                           headers={'X-CSRF-Token': admin_csrf})
        assert resp.status_code == 400

    def test_create_unauthorized(self, client):
        resp = client.post(self.ENDPOINT, json={'name': 'Test'})
        assert resp.status_code == 403

    def test_update(self, client, seed_refs, admin_csrf):
        client.post(self.ENDPOINT, json={'name': 'История'},
                    headers={'X-CSRF-Token': admin_csrf})
        resp = client.put(f'{self.ENDPOINT}/1', json={'name': 'Истор2'},
                          headers={'X-CSRF-Token': admin_csrf})
        assert resp.status_code == 200
        assert resp.get_json()['success'] is True

    def test_delete(self, client, seed_refs, admin_csrf):
        created = client.post(self.ENDPOINT, json={'name': 'История'},
                              headers={'X-CSRF-Token': admin_csrf})
        item_id = created.get_json()['id']
        resp = client.delete(f'{self.ENDPOINT}/{item_id}',
                             headers={'X-CSRF-Token': admin_csrf})
        assert resp.status_code == 200
        items = client.get(self.ENDPOINT).get_json()
        ids = [i['id'] for i in items]
        assert item_id not in ids

    def test_list_after_create(self, client, admin_csrf):
        client.post(self.ENDPOINT, json={'name': 'Химия'},
                    headers={'X-CSRF-Token': admin_csrf})
        client.post(self.ENDPOINT, json={'name': 'Биология'},
                    headers={'X-CSRF-Token': admin_csrf})
        items = client.get(self.ENDPOINT).get_json()
        names = [i['name'] for i in items]
        assert names == ['Биология', 'Химия']

    def test_create_with_default_teacher(self, client, seed_refs, admin_csrf):
        resp = client.post(self.ENDPOINT, json={'name': 'Test', 'default_teacher_id': 1},
                           headers={'X-CSRF-Token': admin_csrf})
        assert resp.status_code == 201
        assert resp.get_json()['default_teacher_id'] == 1


class TestTeachers:
    ENDPOINT = '/api/teachers'

    def test_crud(self, client, seed_refs, admin_csrf):
        resp = client.post(self.ENDPOINT, json={'name': 'Сидоров С.С.'},
                           headers={'X-CSRF-Token': admin_csrf})
        assert resp.status_code == 201
        item_id = resp.get_json()['id']

        items = client.get(self.ENDPOINT).get_json()
        assert any(i['id'] == item_id for i in items)

        resp = client.put(f'{self.ENDPOINT}/{item_id}', json={'name': 'Сидоров2'},
                          headers={'X-CSRF-Token': admin_csrf})
        assert resp.status_code == 200

        resp = client.delete(f'{self.ENDPOINT}/{item_id}',
                             headers={'X-CSRF-Token': admin_csrf})
        assert resp.status_code == 200


class TestClassrooms:
    ENDPOINT = '/api/classrooms'

    def test_crud(self, client, seed_refs, admin_csrf):
        resp = client.post(self.ENDPOINT, json={'name': '301'},
                           headers={'X-CSRF-Token': admin_csrf})
        assert resp.status_code == 201
        item_id = resp.get_json()['id']

        resp = client.delete(f'{self.ENDPOINT}/{item_id}',
                             headers={'X-CSRF-Token': admin_csrf})
        assert resp.status_code == 200


class TestGroups:
    ENDPOINT = '/api/groups'

    def test_create(self, client, admin_csrf):
        resp = client.post(self.ENDPOINT, json={'name': 'Новая-1', 'course': 1},
                           headers={'X-CSRF-Token': admin_csrf})
        assert resp.status_code == 201
        data = resp.get_json()
        assert data['name'] == 'Новая-1'
        assert data['course'] == 1

    def test_create_distance(self, client, admin_csrf):
        resp = client.post(self.ENDPOINT, json={'name': 'З-11', 'course': 3, 'is_distance': True},
                           headers={'X-CSRF-Token': admin_csrf})
        assert resp.status_code == 201
        assert resp.get_json()['is_distance'] == 1

    def test_create_duplicate_name(self, client, admin_csrf):
        resp = client.post(self.ENDPOINT, json={'name': 'Дубль-1'},
                           headers={'X-CSRF-Token': admin_csrf})
        assert resp.status_code == 201
        resp = client.post(self.ENDPOINT, json={'name': 'Дубль-1'},
                           headers={'X-CSRF-Token': admin_csrf})
        assert resp.status_code == 400

    def test_update_group(self, client, seed_refs, admin_csrf):
        resp = client.post(self.ENDPOINT, json={'name': 'Гр1', 'course': 1},
                           headers={'X-CSRF-Token': admin_csrf})
        item_id = resp.get_json()['id']
        resp = client.put(f'{self.ENDPOINT}/{item_id}', json={'name': 'Гр2', 'course': 2},
                          headers={'X-CSRF-Token': admin_csrf})
        assert resp.status_code == 200

    def test_delete_group(self, client, seed_refs, admin_csrf):
        resp = client.post(self.ENDPOINT, json={'name': 'Гр1'},
                           headers={'X-CSRF-Token': admin_csrf})
        item_id = resp.get_json()['id']
        resp = client.delete(f'{self.ENDPOINT}/{item_id}',
                             headers={'X-CSRF-Token': admin_csrf})
        assert resp.status_code == 200
        remaining = client.get(self.ENDPOINT).get_json()
        assert all(g['id'] != item_id for g in remaining)

    def test_list_with_course_order(self, client, admin_csrf):
        client.post(self.ENDPOINT, json={'name': 'Б-2', 'course': 2},
                    headers={'X-CSRF-Token': admin_csrf})
        client.post(self.ENDPOINT, json={'name': 'А-1', 'course': 1},
                    headers={'X-CSRF-Token': admin_csrf})
        items = client.get(self.ENDPOINT).get_json()
        courses = [i['course'] for i in items]
        assert courses == sorted(courses)

    def test_advance_courses(self, client, admin_csrf):
        client.post(self.ENDPOINT, json={'name': '1к-1', 'course': 1},
                    headers={'X-CSRF-Token': admin_csrf})
        client.post(self.ENDPOINT, json={'name': '4к-1', 'course': 4},
                    headers={'X-CSRF-Token': admin_csrf})
        resp = client.post(f'{self.ENDPOINT}/advance-courses',
                           headers={'X-CSRF-Token': admin_csrf})
        assert resp.status_code == 200
        assert resp.get_json()['deleted'] == 1
        remaining = client.get(self.ENDPOINT).get_json()
        assert len(remaining) == 1
        assert remaining[0]['name'] == '1к-1'
        assert remaining[0]['course'] == 2


class TestDays:
    def test_create_day(self, client, admin_csrf):
        resp = client.post('/api/days', json={
            'day_name': 'Понедельник', 'date': '2026-09-07', 'group_name': 'Группа-1'
        }, headers={'X-CSRF-Token': admin_csrf})
        assert resp.status_code == 201
        assert resp.get_json()['id'] > 0

    def test_create_batch(self, client, admin_csrf):
        days = [
            {'day_name': 'Понедельник', 'date': '2026-09-07', 'group_name': 'Гр'},
            {'day_name': 'Вторник', 'date': '2026-09-08', 'group_name': 'Гр'},
        ]
        resp = client.post('/api/days/batch', json={'days': days},
                           headers={'X-CSRF-Token': admin_csrf})
        assert resp.status_code == 201
        assert len(resp.get_json()['ids']) == 2

    def test_create_batch_duplicate(self, client, admin_csrf):
        days = [
            {'day_name': 'Пн', 'date': '2026-09-07', 'group_name': 'Гр'},
        ]
        client.post('/api/days/batch', json={'days': days},
                    headers={'X-CSRF-Token': admin_csrf})
        resp = client.post('/api/days/batch', json={'days': days},
                           headers={'X-CSRF-Token': admin_csrf})
        assert resp.status_code == 409

    def test_list_days(self, client, seed_days):
        resp = client.get('/api/days?group=Группа-1')
        assert resp.status_code == 200
        data = resp.get_json()
        assert len(data) == 3
        assert data[0]['day_name'] == 'Понедельник'

    def test_list_days_returns_all(self, client, seed_days):
        resp = client.get('/api/days')
        assert resp.status_code == 200
        assert len(resp.get_json()) == 3

    def test_update_day(self, client, seed_days, admin_csrf):
        resp = client.put('/api/days/1', json={'day_name': 'Вторник', 'date': '2026-09-08'},
                          headers={'X-CSRF-Token': admin_csrf})
        assert resp.status_code == 200

    def test_delete_day_soft(self, client, seed_days, admin_csrf):
        resp = client.delete('/api/days/1', headers={'X-CSRF-Token': admin_csrf})
        assert resp.status_code == 200
        items = client.get('/api/days').get_json()
        ids = [i['id'] for i in items]
        assert 1 not in ids

    def test_restore_day(self, client, seed_days, admin_csrf):
        client.delete('/api/days/1', headers={'X-CSRF-Token': admin_csrf})
        resp = client.post('/api/days/1/restore', headers={'X-CSRF-Token': admin_csrf})
        assert resp.status_code == 200
        items = client.get('/api/days').get_json()
        assert any(i['id'] == 1 for i in items)


class TestLessons:
    def test_create_lesson(self, client, seed_days, admin_csrf):
        resp = client.post('/api/days/1/lessons', json={
            'period': 3, 'subject_id': 1, 'teacher_id': 1, 'classroom_id': 1, 'group_id': 1
        }, headers={'X-CSRF-Token': admin_csrf})
        assert resp.status_code == 201
        assert resp.get_json()['id'] > 0

    def test_create_lesson_conflict_teacher(self, client, seed_lessons, admin_csrf):
        resp = client.post('/api/days/1/lessons', json={
            'period': 2, 'subject_id': 2, 'teacher_id': 1, 'classroom_id': 2, 'group_id': 1
        }, headers={'X-CSRF-Token': admin_csrf})
        assert resp.status_code == 409

    def test_create_lesson_invalid_period(self, client, seed_days, admin_csrf):
        resp = client.post('/api/days/1/lessons', json={
            'period': 99, 'subject_id': 1, 'teacher_id': 1
        }, headers={'X-CSRF-Token': admin_csrf})
        assert resp.status_code == 400

    def test_update_lesson(self, client, seed_lessons, admin_csrf):
        resp = client.put('/api/lessons/1', json={
            'subject_id': 2, 'teacher_id': 2, 'classroom_id': 2, 'group_id': 1
        }, headers={'X-CSRF-Token': admin_csrf})
        assert resp.status_code == 200

    def test_update_lesson_not_found(self, client, admin_csrf):
        resp = client.put('/api/lessons/999', json={'group_id': 1},
                          headers={'X-CSRF-Token': admin_csrf})
        assert resp.status_code == 404

    def test_delete_lesson_soft(self, client, seed_lessons, admin_csrf):
        resp = client.delete('/api/lessons/1', headers={'X-CSRF-Token': admin_csrf})
        assert resp.status_code == 200

    def test_restore_lesson(self, client, seed_lessons, admin_csrf):
        client.delete('/api/lessons/1', headers={'X-CSRF-Token': admin_csrf})
        resp = client.post('/api/lessons/1/restore', headers={'X-CSRF-Token': admin_csrf})
        assert resp.status_code == 200


class TestWeekRoutes:
    def test_delete_week(self, client, seed_days, admin_csrf):
        resp = client.delete('/api/week?monday=2026-09-07',
                             headers={'X-CSRF-Token': admin_csrf})
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['days_deleted'] >= 2

    def test_delete_week_no_monday(self, client, admin_csrf):
        resp = client.delete('/api/week', headers={'X-CSRF-Token': admin_csrf})
        assert resp.status_code == 400

    def test_restore_week(self, client, seed_days, admin_csrf):
        client.delete('/api/week?monday=2026-09-07',
                      headers={'X-CSRF-Token': admin_csrf})
        resp = client.post('/api/week/restore?monday=2026-09-07',
                           headers={'X-CSRF-Token': admin_csrf})
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['days_restored'] >= 2

    def test_restore_week_no_monday(self, client, admin_csrf):
        resp = client.post('/api/week/restore', headers={'X-CSRF-Token': admin_csrf})
        assert resp.status_code == 400
