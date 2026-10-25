class TestDependencyProtection:
    def test_delete_subject_in_use_returns_409(self, client, seed_lessons, admin_csrf):
        resp = client.delete('/api/subjects/1', headers={'X-CSRF-Token': admin_csrf})
        assert resp.status_code == 409
        assert 'уроках' in resp.get_json()['error']

    def test_delete_teacher_in_use_returns_409(self, client, seed_lessons, admin_csrf):
        resp = client.delete('/api/teachers/1', headers={'X-CSRF-Token': admin_csrf})
        assert resp.status_code == 409
        assert 'уроках' in resp.get_json()['error']

    def test_delete_classroom_in_use_returns_409(self, client, seed_lessons, admin_csrf):
        resp = client.delete('/api/classrooms/1', headers={'X-CSRF-Token': admin_csrf})
        assert resp.status_code == 409
        assert 'уроках' in resp.get_json()['error']

    def test_delete_group_in_use_returns_409(self, client, seed_lessons, admin_csrf):
        resp = client.delete('/api/groups/1', headers={'X-CSRF-Token': admin_csrf})
        assert resp.status_code == 409
        assert 'уроках' in resp.get_json()['error']

    def test_delete_subject_not_in_use_succeeds(self, client, seed_refs, admin_csrf):
        resp = client.delete('/api/subjects/1', headers={'X-CSRF-Token': admin_csrf})
        assert resp.status_code == 200


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

    def test_create_with_phone(self, client, seed_refs, admin_csrf):
        resp = client.post(self.ENDPOINT, json={'name': 'Петров П.П.', 'phone': '+7-123-456-78-90'},
                           headers={'X-CSRF-Token': admin_csrf})
        assert resp.status_code == 201
        data = resp.get_json()
        assert data['phone'] == '+7-123-456-78-90'
        item_id = data['id']

        resp = client.put(f'{self.ENDPOINT}/{item_id}', json={'name': 'Петров П.П.', 'phone': '+7-999-888-77-66'},
                          headers={'X-CSRF-Token': admin_csrf})
        assert resp.status_code == 200

        items = client.get(self.ENDPOINT).get_json()
        match = [i for i in items if i['id'] == item_id]
        assert len(match) == 1
        assert match[0]['phone'] == '+7-999-888-77-66'

    def test_duplicate_phone_rejected(self, client, seed_refs, admin_csrf):
        resp = client.post(self.ENDPOINT, json={'name': 'Сидоров С.С.', 'phone': '+7-111-222-33-44'},
                           headers={'X-CSRF-Token': admin_csrf})
        assert resp.status_code == 201

        resp = client.post(self.ENDPOINT, json={'name': 'Петров П.П.', 'phone': '+7-111-222-33-44'},
                           headers={'X-CSRF-Token': admin_csrf})
        assert resp.status_code == 409
        assert resp.get_json()['error'] == 'Этот номер телефона уже используется другим преподавателем'

    def test_duplicate_phone_update_self(self, client, seed_refs, admin_csrf):
        resp = client.post(self.ENDPOINT, json={'name': 'Иванов И.И.', 'phone': '+7-555-666-77-88'},
                           headers={'X-CSRF-Token': admin_csrf})
        assert resp.status_code == 201
        item_id = resp.get_json()['id']

        resp = client.put(f'{self.ENDPOINT}/{item_id}', json={'name': 'Иванов И.И.', 'phone': '+7-555-666-77-88'},
                          headers={'X-CSRF-Token': admin_csrf})
        assert resp.status_code == 200

    def test_multiple_empty_phone_allowed(self, client, seed_refs, admin_csrf):
        resp = client.post(self.ENDPOINT, json={'name': 'Первый'},
                           headers={'X-CSRF-Token': admin_csrf})
        assert resp.status_code == 201

        resp = client.post(self.ENDPOINT, json={'name': 'Второй'},
                           headers={'X-CSRF-Token': admin_csrf})
        assert resp.status_code == 201

    def test_empty_string_phone_not_duplicate(self, client, seed_refs, admin_csrf):
        resp = client.post(self.ENDPOINT, json={'name': 'Антонов А.А.', 'phone': ''},
                           headers={'X-CSRF-Token': admin_csrf})
        assert resp.status_code == 201

        resp = client.post(self.ENDPOINT, json={'name': 'Борисов Б.Б.', 'phone': ''},
                           headers={'X-CSRF-Token': admin_csrf})
        assert resp.status_code == 201

    def test_restore_teacher_returns_name(self, client, seed_refs, admin_csrf):
        client.post(self.ENDPOINT, json={'name': 'Тестов Т.Т.', 'phone': '+7-000-000-00-00'},
                    headers={'X-CSRF-Token': admin_csrf})
        items = client.get(self.ENDPOINT).get_json()
        target = [i for i in items if i['name'] == 'Тестов Т.Т.'][0]
        client.delete(f'{self.ENDPOINT}/{target["id"]}',
                      headers={'X-CSRF-Token': admin_csrf})
        resp = client.post(f'{self.ENDPOINT}/{target["id"]}/restore',
                           headers={'X-CSRF-Token': admin_csrf})
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['item']['type'] == 'teachers'
        assert data['item']['name'] == 'Тестов Т.Т.'


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

    def test_advance_courses_soft_deletes_group_with_lessons(self, client, seed_refs, admin_csrf):
        """Course-4 groups that have lessons must be soft-deleted, not hard-deleted."""
        import db as db_module
        h = {'X-CSRF-Token': admin_csrf}
        resp = client.post(self.ENDPOINT, json={'name': '4к-1', 'course': 4}, headers=h)
        assert resp.status_code in (200, 201)
        gid = resp.get_json()['id']
        # Attach a lesson to the 4th-course group so hard DELETE would violate FK
        resp = client.post('/api/days', json={
            'day_name': 'Понедельник', 'date': '2026-09-07', 'group_name': '4к-1'
        }, headers=h)
        assert resp.status_code == 201
        day_id = resp.get_json()['id']
        resp = client.post(f'/api/days/{day_id}/lessons', json={
            'period': 1, 'subject_id': 1, 'teacher_id': 1, 'group_id': gid,
        }, headers=h)
        assert resp.status_code == 201

        resp = client.post(f'{self.ENDPOINT}/advance-courses', headers=h)
        assert resp.status_code == 200
        assert resp.get_json()['deleted'] == 1
        # The group row stays present, marked soft-deleted
        conn = db_module.get_db()
        row = conn.execute('SELECT id, deleted_at FROM groups_list WHERE id = ?', (gid,)).fetchone()
        conn.close()
        assert row is not None, '4th-course group must remain in DB (soft delete)'
        assert row['deleted_at'] is not None, '4th-course group must be soft-deleted'
        # And it no longer shows up in the active list
        remaining = client.get(self.ENDPOINT).get_json()
        assert all(i['id'] != gid for i in remaining)


class TestDays:
    def test_create_day(self, client, admin_csrf):
        resp = client.post('/api/days', json={
            'day_name': 'Понедельник', 'date': '2026-09-07', 'group_name': 'Группа-1'
        }, headers={'X-CSRF-Token': admin_csrf})
        assert resp.status_code == 201
        assert resp.get_json()['id'] > 0

    def test_create_day_defaults_to_draft(self, client, admin_csrf):
        """Свежесозданный день должен сохраняться как Черновик (is_published = 0)."""
        import db as db_module
        resp = client.post('/api/days', json={
            'day_name': 'Понедельник', 'date': '2026-09-21', 'group_name': 'Группа-1'
        }, headers={'X-CSRF-Token': admin_csrf})
        assert resp.status_code == 201
        day_id = resp.get_json()['id']
        conn = db_module.get_db()
        row = conn.execute('SELECT is_published FROM schedule_days WHERE id = ?', (day_id,)).fetchone()
        conn.close()
        assert row is not None
        assert row['is_published'] == 0, 'Новый день должен быть в Черновике по умолчанию'

    def test_create_batch(self, client, admin_csrf):
        days = [
            {'day_name': 'Понедельник', 'date': '2026-09-07', 'group_name': 'Гр'},
            {'day_name': 'Вторник', 'date': '2026-09-08', 'group_name': 'Гр'},
        ]
        resp = client.post('/api/days/batch', json={'days': days},
                           headers={'X-CSRF-Token': admin_csrf})
        assert resp.status_code == 201
        assert len(resp.get_json()['ids']) == 2

    def test_create_batch_defaults_to_draft(self, client, admin_csrf):
        """Дни, созданные батчом, также сохраняются как Черновик (is_published = 0)."""
        import db as db_module
        days = [
            {'day_name': 'Понедельник', 'date': '2026-09-21', 'group_name': 'Гр'},
            {'day_name': 'Вторник', 'date': '2026-09-22', 'group_name': 'Гр'},
        ]
        resp = client.post('/api/days/batch', json={'days': days},
                           headers={'X-CSRF-Token': admin_csrf})
        assert resp.status_code == 201
        conn = db_module.get_db()
        rows = conn.execute('SELECT is_published FROM schedule_days WHERE group_name = ?', ('Гр',)).fetchall()
        conn.close()
        assert len(rows) == 2
        assert all(r['is_published'] == 0 for r in rows), 'Дни из batch должны быть в Черновике по умолчанию'

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

    def test_move_lesson_to_another_day(self, client, seed_lessons, db, admin_csrf):
        """PUT с новым day_id/period перемещает урок (drag-and-drop)."""
        resp = client.put('/api/lessons/1', json={
            'day_id': 2, 'period': 3, 'subject_id': 1, 'teacher_id': 1,
            'classroom_id': 1, 'group_id': 1
        }, headers={'X-CSRF-Token': admin_csrf})
        assert resp.status_code == 200, resp.get_json()
        row = db.get_db().execute(
            'SELECT day_id, period FROM lessons WHERE id = 1').fetchone()
        assert row['day_id'] == 2
        assert row['period'] == 3

    def test_move_lesson_conflict_rolls_back(self, client, seed_lessons, db, admin_csrf):
        """Перемещение в занятый слот учителя — 409, урок не тронут."""
        conn = db.get_db()
        conn.execute(
            'INSERT INTO lessons (id, day_id, period, subject_id, teacher_id, classroom_id, group_id) '
            'VALUES (9, 2, 1, 1, 1, 1, 1)')
        conn.commit()
        resp = client.put('/api/lessons/1', json={
            'day_id': 2, 'period': 1, 'subject_id': 1, 'teacher_id': 1,
            'classroom_id': 1, 'group_id': 1
        }, headers={'X-CSRF-Token': admin_csrf})
        assert resp.status_code == 409
        row = db.get_db().execute(
            'SELECT day_id, period FROM lessons WHERE id = 1').fetchone()
        assert (row['day_id'], row['period']) == (1, 1)

    def test_move_lesson_invalid_day(self, client, seed_lessons, db, admin_csrf):
        resp = client.put('/api/lessons/1', json={
            'day_id': 999, 'period': 1, 'subject_id': 1
        }, headers={'X-CSRF-Token': admin_csrf})
        assert resp.status_code == 404
        row = db.get_db().execute(
            'SELECT day_id, period FROM lessons WHERE id = 1').fetchone()
        assert (row['day_id'], row['period']) == (1, 1)

    def test_update_lesson_not_found(self, client, admin_csrf):
        resp = client.put('/api/lessons/999', json={'group_id': 1},
                          headers={'X-CSRF-Token': admin_csrf})
        assert resp.status_code == 404

    def test_delete_lesson_soft(self, client, seed_lessons, admin_csrf):
        resp = client.delete('/api/lessons/1', headers={'X-CSRF-Token': admin_csrf})
        assert resp.status_code == 200

    def test_delete_lesson_writes_history(self, client, seed_lessons, admin_csrf):
        client.delete('/api/lessons/1', headers={'X-CSRF-Token': admin_csrf})
        import db as db_module
        conn = db_module.get_db()
        row = conn.execute(
            'SELECT * FROM lesson_history WHERE lesson_id = 1 ORDER BY id DESC LIMIT 1'
        ).fetchone()
        conn.close()
        assert row is not None
        assert row['old_subject_id'] == 1
        assert row['old_teacher_id'] == 1
        assert row['old_classroom_id'] == 1
        assert row['old_group_id'] == 1

    def test_delete_lesson_already_deleted_returns_404(self, client, seed_lessons, admin_csrf):
        client.delete('/api/lessons/1', headers={'X-CSRF-Token': admin_csrf})
        resp = client.delete('/api/lessons/1', headers={'X-CSRF-Token': admin_csrf})
        assert resp.status_code == 404

    def test_restore_lesson(self, client, seed_lessons, admin_csrf):
        client.delete('/api/lessons/1', headers={'X-CSRF-Token': admin_csrf})
        resp = client.post('/api/lessons/1/restore', headers={'X-CSRF-Token': admin_csrf})
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['item']['type'] == 'lesson'
        assert data['item']['subject_name'] == 'Математика'

    def test_restore_lesson_conflict(self, client, seed_lessons, admin_csrf):
        client.delete('/api/lessons/2', headers={'X-CSRF-Token': admin_csrf})
        client.post('/api/days/1/lessons', json={
            'period': 2, 'subject_id': 1, 'teacher_id': 2, 'classroom_id': 1, 'group_id': 1
        }, headers={'X-CSRF-Token': admin_csrf})
        resp = client.post('/api/lessons/2/restore', headers={'X-CSRF-Token': admin_csrf})
        assert resp.status_code == 409

    def test_restore_day_returns_details(self, client, seed_days, admin_csrf):
        client.delete('/api/days/1', headers={'X-CSRF-Token': admin_csrf})
        resp = client.post('/api/days/1/restore', headers={'X-CSRF-Token': admin_csrf})
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['item']['type'] == 'day'
        assert data['item']['day_name'] == 'Понедельник'

    def test_restore_day_conflict(self, client, seed_lessons, admin_csrf):
        client.delete('/api/lessons/2', headers={'X-CSRF-Token': admin_csrf})
        new_day = client.post('/api/days', json={'day_name': 'Понедельник', 'date': '2026-09-07', 'group_name': 'Группа-2'},
                              headers={'X-CSRF-Token': admin_csrf}).get_json()
        new_day_id = new_day['id']
        client.post(f'/api/days/{new_day_id}/lessons', json={
            'period': 2, 'subject_id': 1, 'teacher_id': 2, 'classroom_id': 1, 'group_id': 2
        }, headers={'X-CSRF-Token': admin_csrf})
        client.delete('/api/days/1', headers={'X-CSRF-Token': admin_csrf})
        resp = client.post('/api/days/1/restore', headers={'X-CSRF-Token': admin_csrf})
        assert resp.status_code == 409
        items = client.get('/api/days').get_json()
        assert not any(i['id'] == 1 for i in items)
        items = client.get('/api/days').get_json()
        assert not any(i['id'] == 1 for i in items)


class TestWeekRoutes:
    def test_delete_week_group(self, client, seed_days, admin_csrf):
        resp = client.delete('/api/week?monday=2026-09-07&target_type=group&target_id=Группа-1',
                             headers={'X-CSRF-Token': admin_csrf})
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['days_deleted'] >= 2

    def test_delete_week_no_params(self, client, admin_csrf):
        resp = client.delete('/api/week', headers={'X-CSRF-Token': admin_csrf})
        assert resp.status_code == 400

    def test_restore_week_group(self, client, seed_days, admin_csrf):
        client.delete('/api/week?monday=2026-09-07&target_type=group&target_id=Группа-1',
                      headers={'X-CSRF-Token': admin_csrf})
        resp = client.post('/api/week/restore?monday=2026-09-07&target_type=group&target_id=Группа-1',
                           headers={'X-CSRF-Token': admin_csrf})
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['days_restored'] >= 2

    def test_restore_week_no_params(self, client, admin_csrf):
        resp = client.post('/api/week/restore', headers={'X-CSRF-Token': admin_csrf})
        assert resp.status_code == 400

    def test_delete_week_teacher(self, client, seed_lessons, admin_csrf):
        resp = client.delete('/api/week?monday=2026-09-07&target_type=teacher&target_id=1',
                             headers={'X-CSRF-Token': admin_csrf})
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['days_deleted'] >= 1

    def test_delete_week_classroom(self, client, seed_lessons, admin_csrf):
        resp = client.delete('/api/week?monday=2026-09-07&target_type=classroom&target_id=1',
                             headers={'X-CSRF-Token': admin_csrf})
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['days_deleted'] >= 1


class TestSettings:
    ENDPOINT = '/api/settings'

    def test_get_settings(self, client, admin_csrf):
        resp = client.get(self.ENDPOINT, headers={'X-CSRF-Token': admin_csrf})
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['session_lifetime'] == '3600'
        assert data['login_rate_limit'] == '5'
        assert data['login_rate_window'] == '300'
        assert data['backup_retention_days'] == '30'

    def test_get_settings_unauthorized(self, client):
        resp = client.get(self.ENDPOINT)
        assert resp.status_code == 401

    def test_update_setting(self, client, admin_csrf):
        resp = client.put(f'{self.ENDPOINT}/login_rate_limit',
                          json={'value': '10'},
                          headers={'X-CSRF-Token': admin_csrf})
        assert resp.status_code == 200

        resp = client.get(self.ENDPOINT, headers={'X-CSRF-Token': admin_csrf})
        assert resp.get_json()['login_rate_limit'] == '10'

    def test_update_setting_invalid_key(self, client, admin_csrf):
        resp = client.put(f'{self.ENDPOINT}/invalid_key',
                          json={'value': '10'},
                          headers={'X-CSRF-Token': admin_csrf})
        assert resp.status_code == 403

    def test_update_backup_retention(self, client, admin_csrf):
        resp = client.put(f'{self.ENDPOINT}/backup_retention_days',
                          json={'value': '60'},
                          headers={'X-CSRF-Token': admin_csrf})
        assert resp.status_code == 200

        resp = client.get(self.ENDPOINT, headers={'X-CSRF-Token': admin_csrf})
        assert resp.get_json()['backup_retention_days'] == '60'

    def test_update_setting_invalid_value(self, client, admin_csrf):
        resp = client.put(f'{self.ENDPOINT}/login_rate_limit',
                          json={'value': '-1'},
                          headers={'X-CSRF-Token': admin_csrf})
        assert resp.status_code == 400

        resp = client.put(f'{self.ENDPOINT}/login_rate_limit',
                          json={'value': 'abc'},
                          headers={'X-CSRF-Token': admin_csrf})
        assert resp.status_code == 400

    def test_update_session_lifetime_clamped_to_minimum(self, client, admin_csrf):
        resp = client.put(f'{self.ENDPOINT}/session_lifetime',
                          json={'value': '1'},
                          headers={'X-CSRF-Token': admin_csrf})
        assert resp.status_code == 200

        resp = client.get(self.ENDPOINT, headers={'X-CSRF-Token': admin_csrf})
        assert resp.get_json()['session_lifetime'] == '3600'

    def test_update_session_lifetime_valid_minimum(self, client, admin_csrf):
        resp = client.put(f'{self.ENDPOINT}/session_lifetime',
                          json={'value': '120'},
                          headers={'X-CSRF-Token': admin_csrf})
        assert resp.status_code == 200

        resp = client.get(self.ENDPOINT, headers={'X-CSRF-Token': admin_csrf})
        assert resp.get_json()['session_lifetime'] == '120'

    def test_update_setting_syncs_config_store(self, client, admin_csrf):
        """PUT must update the single in-memory config source, not just the DB row."""
        import config
        assert config.SETTINGS['login_rate_limit'] == 5
        resp = client.put(f'{self.ENDPOINT}/login_rate_limit',
                          json={'value': '12'},
                          headers={'X-CSRF-Token': admin_csrf})
        assert resp.status_code == 200
        assert config.SETTINGS['login_rate_limit'] == 12
        # And the DB reflects it too (single source of truth)
        conn = __import__('db', fromlist=['get_db']).get_db()
        row = conn.execute("SELECT value FROM settings WHERE key = 'login_rate_limit'").fetchone()
        conn.close()
        assert row['value'] == '12'


class TestBackupDownload:
    ENDPOINT = '/api/admin/backup/download'

    def test_download_backup(self, client, admin_csrf):
        resp = client.get(self.ENDPOINT, headers={'X-CSRF-Token': admin_csrf})
        assert resp.status_code == 200
        assert 'schedule_backup_' in resp.headers.get('Content-Disposition', '')
        assert len(resp.data) > 0

    def test_download_backup_missing_db(self, client, admin_csrf, monkeypatch):
        monkeypatch.setattr('routes.DB_PATH', 'C:/nonexistent/nope.db')
        resp = client.get(self.ENDPOINT, headers={'X-CSRF-Token': admin_csrf})
        assert resp.status_code == 404
        assert 'не найден' in resp.get_json()['error']
