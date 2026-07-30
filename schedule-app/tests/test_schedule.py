class TestScheduleTable:
    def test_group_schedule(self, client, seed_lessons):
        resp = client.get('/api/schedule-table?group=Группа-1&monday=2026-09-07')
        assert resp.status_code == 200
        data = resp.get_json()
        assert len(data['days']) == 6
        assert data['days'][0]['date'] == '2026-09-07'
        assert len(data['periods']) == 8

    def test_group_schedule_no_group(self, client):
        resp = client.get('/api/schedule-table?monday=2026-09-07')
        assert resp.status_code == 200
        assert resp.get_json()['days'] == []

    def test_group_schedule_empty_week(self, client, seed_refs):
        resp = client.get('/api/schedule-table?group=Группа-1&monday=2026-09-21')
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['week_exists'] is False

    def test_teacher_schedule_table(self, client, seed_lessons):
        resp = client.get('/api/teacher-schedule-table?teacher_id=1&monday=2026-09-07')
        assert resp.status_code == 200
        data = resp.get_json()
        assert len(data['days']) == 6

    def test_teacher_schedule_table_no_id(self, client):
        resp = client.get('/api/teacher-schedule-table?monday=2026-09-07')
        assert resp.status_code == 200
        assert resp.get_json()['days'] == []

    def test_classroom_schedule_table(self, client, seed_lessons):
        resp = client.get('/api/classroom-schedule-table?classroom_id=1&monday=2026-09-07')
        assert resp.status_code == 200
        data = resp.get_json()
        assert len(data['days']) == 6

    def test_classroom_schedule_table_no_id(self, client):
        resp = client.get('/api/classroom-schedule-table?monday=2026-09-07')
        assert resp.status_code == 200
        assert resp.get_json()['days'] == []


class TestTeacherSchedule:
    def test_teacher_schedule(self, client, seed_lessons):
        resp = client.get('/api/teacher-schedule?teacher_id=1')
        assert resp.status_code == 200
        data = resp.get_json()
        assert len(data) == 1
        assert data[0]['date'] == '2026-09-07'

    def test_teacher_schedule_no_id(self, client):
        resp = client.get('/api/teacher-schedule')
        assert resp.status_code == 200
        assert resp.get_json() == []


class TestTeachersWithSchedule:
    def test_teachers_with_schedule(self, client, seed_lessons):
        resp = client.get('/api/teachers-with-schedule')
        assert resp.status_code == 200
        data = resp.get_json()
        assert any(t['id'] == 1 for t in data)

    def test_teachers_with_schedule_empty(self, client, seed_refs):
        resp = client.get('/api/teachers-with-schedule')
        assert resp.get_json() == []


class TestClassroomsWithSchedule:
    def test_classrooms_with_schedule(self, client, seed_lessons):
        resp = client.get('/api/classrooms-with-schedule')
        assert resp.status_code == 200
        data = resp.get_json()
        assert any(c['id'] == 1 for c in data)

    def test_classrooms_with_schedule_empty(self, client, seed_refs):
        resp = client.get('/api/classrooms-with-schedule')
        assert resp.get_json() == []


class TestAvailability:
    def test_availability(self, client, seed_lessons, admin_csrf):
        resp = client.get('/api/availability?monday=2026-09-07', headers={'X-CSRF-Token': admin_csrf})
        assert resp.status_code == 200
        data = resp.get_json()
        assert len(data['days']) == 6
        assert len(data['periods']) == 8
        assert len(data['teachers']) == 2
        assert len(data['classrooms']) == 2
        assert '1' in data['teacher_busy']
        assert '1' in data['classroom_busy']

    def test_availability_no_monday(self, client, admin_csrf):
        resp = client.get('/api/availability', headers={'X-CSRF-Token': admin_csrf})
        assert resp.status_code == 400

    def test_availability_empty_week(self, client, seed_refs, admin_csrf):
        resp = client.get('/api/availability?monday=2026-09-21', headers={'X-CSRF-Token': admin_csrf})
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['teacher_busy'] == {}
        assert data['classroom_busy'] == {}

    def test_availability_excludes_deleted_teacher(self, client, seed_lessons, admin_csrf):
        h = {'X-CSRF-Token': admin_csrf}

        resp = client.get('/api/availability?monday=2026-09-07', headers=h)
        data = resp.get_json()
        teacher_ids = [t['id'] for t in data['teachers']]
        assert 1 in teacher_ids, 'Teacher 1 should be visible before deletion'

        # Cannot delete teacher referenced in lessons — must delete lessons first
        resp = client.delete('/api/teachers/1', headers=h)
        assert resp.status_code == 409

        # Delete referencing lessons first
        resp = client.delete('/api/lessons/1', headers=h)
        assert resp.status_code == 200
        resp = client.delete('/api/lessons/2', headers=h)
        assert resp.status_code == 200

        resp = client.delete('/api/teachers/1', headers=h)
        assert resp.status_code == 200

        resp = client.get('/api/availability?monday=2026-09-07', headers=h)
        data = resp.get_json()
        teacher_ids = [t['id'] for t in data['teachers']]
        assert 1 not in teacher_ids, 'Teacher 1 should be excluded after deletion'

    def test_availability_excludes_deleted_classroom(self, client, seed_lessons, admin_csrf):
        h = {'X-CSRF-Token': admin_csrf}

        resp = client.get('/api/availability?monday=2026-09-07', headers=h)
        data = resp.get_json()
        classroom_ids = [c['id'] for c in data['classrooms']]
        assert 1 in classroom_ids, 'Classroom 1 should be visible before deletion'

        # Cannot delete classroom referenced in lessons
        resp = client.delete('/api/classrooms/1', headers=h)
        assert resp.status_code == 409

        # Delete referencing lessons first
        resp = client.delete('/api/lessons/1', headers=h)
        assert resp.status_code == 200
        resp = client.delete('/api/lessons/2', headers=h)
        assert resp.status_code == 200

        resp = client.delete('/api/classrooms/1', headers=h)
        assert resp.status_code == 200

        resp = client.get('/api/availability?monday=2026-09-07', headers=h)
        data = resp.get_json()
        classroom_ids = [c['id'] for c in data['classrooms']]
        assert 1 not in classroom_ids, 'Classroom 1 should be excluded after deletion'


class TestExport:
    def test_export_xlsx(self, client, seed_lessons):
        resp = client.get('/api/export?type=group&name=Группа-1&monday=2026-09-07&format=xlsx')
        assert resp.status_code == 200
        assert 'spreadsheetml' in resp.content_type
        assert len(resp.data) > 100

    def test_export_docx(self, client, seed_lessons):
        resp = client.get('/api/export?type=group&name=Группа-1&monday=2026-09-07&format=docx')
        assert resp.status_code == 200
        assert resp.mimetype == 'application/vnd.openxmlformats-officedocument.wordprocessingml.document'

    def test_export_pdf(self, client, seed_lessons):
        resp = client.get('/api/export?type=group&name=Группа-1&monday=2026-09-07&format=pdf')
        assert resp.status_code == 200
        assert resp.mimetype == 'application/pdf'

    def test_export_missing_params(self, client):
        resp = client.get('/api/export?type=group')
        assert resp.status_code == 400

    def test_export_invalid_format(self, client):
        resp = client.get('/api/export?type=group&name=Гр&monday=2026-09-07&format=csv')
        assert resp.status_code == 400

    def test_export_no_data_returns_404(self, client, seed_refs):
        resp = client.get('/api/export?type=group&name=Группа-1&monday=2026-09-07&format=xlsx')
        assert resp.status_code == 404


class TestSmartExportExcel:
    def test_export_excel_group(self, client, seed_lessons, admin_csrf):
        resp = client.get('/api/schedule/export/excel?type=group&id=1&start_date=2026-09-07')
        assert resp.status_code == 200
        assert resp.mimetype == 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        assert len(resp.data) > 0

    def test_export_excel_teacher(self, client, seed_lessons, admin_csrf):
        resp = client.get('/api/schedule/export/excel?type=teacher&id=1&start_date=2026-09-07')
        assert resp.status_code == 200
        assert resp.mimetype == 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'

    def test_export_excel_classroom(self, client, seed_lessons, admin_csrf):
        resp = client.get('/api/schedule/export/excel?type=classroom&id=1&start_date=2026-09-07')
        assert resp.status_code == 200
        assert resp.mimetype == 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'

    def test_export_excel_all(self, client, seed_lessons, admin_csrf):
        resp = client.get('/api/schedule/export/excel?type=all&start_date=2026-09-07')
        assert resp.status_code == 200
        assert resp.mimetype == 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'

    def test_export_excel_no_data(self, client, seed_refs, admin_csrf):
        resp = client.get('/api/schedule/export/excel?type=group&id=999')
        assert resp.status_code == 404

    def test_export_excel_empty_week_returns_xlsx(self, client, seed_refs, admin_csrf):
        resp = client.get('/api/schedule/export/excel?type=group&id=1&start_date=2026-09-07')
        assert resp.status_code == 200
        assert resp.mimetype == 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        assert len(resp.data) > 0

    def test_export_excel_missing_id(self, client, admin_csrf):
        resp = client.get('/api/schedule/export/excel?type=group')
        assert resp.status_code == 400

    def test_export_excel_invalid_type(self, client, admin_csrf):
        resp = client.get('/api/schedule/export/excel?type=invalid&id=1')
        assert resp.status_code == 400


class TestCheckDate:
    def test_check_date_not_excluded(self, client, seed_refs):
        resp = client.get('/api/check_date?date=2026-09-07')
        assert resp.status_code == 200
        assert resp.get_json()['excluded'] is False

    def test_check_date_no_param(self, client):
        resp = client.get('/api/check_date')
        assert resp.status_code == 400


class TestTrash:
    def test_trash_empty(self, client, seed_refs, admin_csrf):
        resp = client.get('/api/trash', headers={'X-CSRF-Token': admin_csrf})
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['days'] == []
        assert data['lessons'] == []

    def test_trash_after_delete(self, client, seed_lessons, admin_csrf):
        client.delete('/api/days/1', headers={'X-CSRF-Token': admin_csrf})
        resp = client.get('/api/trash', headers={'X-CSRF-Token': admin_csrf})
        assert resp.status_code == 200
        data = resp.get_json()
        assert len(data['days']) == 1
        assert data['days'][0]['id'] == 1
        assert len(data['lessons']) == 2


class TestValidate:
    def test_validate_no_conflict(self, client, seed_days, admin_csrf):
        resp = client.post('/api/validate', json={
            'day_id': 1, 'period': 1, 'teacher_id': 1, 'classroom_id': 1,
            'subject_id': 1, 'group_id': 1
        }, headers={'X-CSRF-Token': admin_csrf})
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['blocking'] is False

    def test_validate_teacher_conflict(self, client, seed_lessons, admin_csrf):
        resp = client.post('/api/validate', json={
            'day_id': 1, 'period': 1, 'teacher_id': 1
        }, headers={'X-CSRF-Token': admin_csrf})
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['blocking'] is True
        assert any(w['type'] == 'teacher_conflict' for w in data['warnings'])

    def test_validate_exclude_lesson(self, client, seed_lessons, admin_csrf):
        resp = client.post('/api/validate', json={
            'day_id': 1, 'period': 1, 'teacher_id': 1, 'exclude_lesson_id': 1
        }, headers={'X-CSRF-Token': admin_csrf})
        assert resp.status_code == 200
        assert resp.get_json()['blocking'] is False

    def test_validate_week_exists(self, client, seed_days, admin_csrf):
        resp = client.post('/api/validate-week', json={
            'group_name': 'Группа-1', 'dates': ['2026-09-07']
        }, headers={'X-CSRF-Token': admin_csrf})
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['ok'] is False
        assert len(data['warnings']) == 1

    def test_validate_week_ok(self, client, seed_refs, admin_csrf):
        resp = client.post('/api/validate-week', json={
            'group_name': 'Группа-1', 'dates': ['2026-09-21']
        }, headers={'X-CSRF-Token': admin_csrf})
        assert resp.status_code == 200
        assert resp.get_json()['ok'] is True
