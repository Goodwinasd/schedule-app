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

    @staticmethod
    def _insert_lesson(db, lid, day_id, period, teacher_id=1, classroom_id=1, group_id=1, subject_id=1):
        conn = db.get_db()
        conn.execute(
            'INSERT INTO lessons (id, day_id, period, subject_id, teacher_id, classroom_id, group_id) '
            'VALUES (?, ?, ?, ?, ?, ?, ?)',
            (lid, day_id, period, subject_id, teacher_id, classroom_id, group_id),
        )
        conn.commit()
        conn.close()

    def test_availability_math_accuracy(self, client, db, seed_days, admin_csrf):
        """Математическая точность: total/free/load_pct/busy-ключи при известном сиде
        и отсутствие двойного учёта при дубле урока в один и тот же слот."""
        h = {'X-CSRF-Token': admin_csrf}
        # Teacher 1: Пн 1-я пара (day 1 = 2026-09-07) и Вт 2-я пара (day 2 = 2026-09-08)
        self._insert_lesson(db, 10, 1, 1)
        self._insert_lesson(db, 11, 2, 2, classroom_id=2)

        resp = client.get('/api/availability?monday=2026-09-07', headers=h)
        assert resp.status_code == 200
        data = resp.get_json()

        st = data['teacher_stats']['1']
        assert st['total'] == 2, f'Ожидалось 2 занятых слота, получено {st["total"]}'
        assert st['free'] == 46, f'Ожидалось 46 свободных слотов (48-2), получено {st["free"]}'
        assert st['load_pct'] == round(2 / 48 * 100, 1), \
            f'load_pct не соответствует round(2/48*100, 1): {st["load_pct"]}'

        assert set(data['teacher_busy']['1'].keys()) == {'2026-09-07_1', '2026-09-08_2'}
        assert data['group_lesson_count']['1']['lessons'] == 2
        assert data['all_courses'] == [1]

        # Дубликат урока в тот же слот (Вт 2-я пара) не должен удваивать занятость преподавателя
        self._insert_lesson(db, 12, 2, 2, classroom_id=2)
        resp = client.get('/api/availability?monday=2026-09-07', headers=h)
        assert resp.status_code == 200
        data = resp.get_json()

        st = data['teacher_stats']['1']
        assert st['total'] == 2, f'Дубль слота не должен удваивать total: {st["total"]}'
        assert st['free'] == 46
        assert set(data['teacher_busy']['1'].keys()) == {'2026-09-07_1', '2026-09-08_2'}

    def test_availability_course_null_does_not_crash(self, client, db, seed_days, admin_csrf):
        """Группа с course IS NULL не должна ронять sorted() (баг #1 аудита)."""
        h = {'X-CSRF-Token': admin_csrf}
        conn = db.get_db()
        conn.execute('INSERT INTO groups_list (id, name, course, is_distance) VALUES (99, \'Группа-NULL\', NULL, 0)')
        conn.execute(
            'INSERT INTO lessons (id, day_id, period, subject_id, teacher_id, classroom_id, group_id) '
            'VALUES (20, 1, 3, 1, 2, 2, 99)',
        )
        conn.commit()
        conn.close()

        resp = client.get('/api/availability?monday=2026-09-07', headers=h)
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['all_courses'] == []
        assert 'courses' not in data['teachers'][1]  # у Петрова только курс None — ключ не добавляется

    def test_availability_substitutions_payload(self, client, db, seed_days, admin_csrf):
        """Замена (is_substitution) должна попадать в слот занятости с именем исходного преподавателя."""
        h = {'X-CSRF-Token': admin_csrf}
        # Петров (2) заменяет Иванова (1) на Пн 1-я пара (2026-09-07)
        conn = db.get_db()
        conn.execute(
            'INSERT INTO lessons (id, day_id, period, subject_id, teacher_id, classroom_id, group_id, '
            'is_substitution, original_teacher_id) '
            'VALUES (30, 1, 1, 1, 2, 1, 1, 1, 1)',
        )
        conn.commit()
        conn.close()

        resp = client.get('/api/availability?monday=2026-09-07', headers=h)
        assert resp.status_code == 200
        data = resp.get_json()

        slot = data['teacher_busy']['2']['2026-09-07_1']
        assert slot['is_sub'] is True, 'Слот замены должен содержать is_sub=True'
        assert slot['original_teacher'] == 'Иванов И.И.', \
            f'original_teacher не совпадает: {slot.get("original_teacher")}'

        # Исходный преподаватель свободен в этом слоте (его урок вёл заместитель)
        assert '2026-09-07_1' not in data['teacher_busy'].get('1', {})

        # Урок группы учтён в статистике
        assert data['group_lesson_count']['1']['lessons'] == 1


class TestSubstitutionsSuggest:
    def test_suggest_returns_available(self, client, seed_lessons, admin_csrf):
        """Петров (2) свободен на Пн 1-я пара, Иванов (1) занят (lesson 1)."""
        resp = client.get('/api/schedule/substitutions-suggest?date=2026-09-07&period=1', headers={'X-CSRF-Token': admin_csrf})
        assert resp.status_code == 200
        data = resp.get_json()
        ids = [t['id'] for t in data['available']]
        assert 2 in ids, 'Петров должен быть свободен'
        assert 1 not in ids, 'Иванов занят на Пн 1-я пара'

    def test_suggest_via_day_id(self, client, seed_lessons, admin_csrf):
        resp = client.get('/api/schedule/substitutions-suggest?day_id=1&period=1', headers={'X-CSRF-Token': admin_csrf})
        assert resp.status_code == 200
        ids = [t['id'] for t in resp.get_json()['available']]
        assert 2 in ids and 1 not in ids

    def test_suggest_requires_params(self, client, admin_csrf):
        resp = client.get('/api/schedule/substitutions-suggest?period=1', headers={'X-CSRF-Token': admin_csrf})
        assert resp.status_code == 400
        resp = client.get('/api/schedule/substitutions-suggest?date=2026-09-07', headers={'X-CSRF-Token': admin_csrf})
        assert resp.status_code == 400

    def test_suggest_excludes_busy_and_deleted(self, client, db, seed_lessons, admin_csrf):
        h = {'X-CSRF-Token': admin_csrf}
        conn = db.get_db()
        conn.execute('INSERT INTO lessons (id, day_id, period, subject_id, teacher_id, classroom_id, group_id) VALUES (40, 1, 3, 1, 2, 2, 1)')
        conn.commit()
        conn.close()

        resp = client.get('/api/schedule/substitutions-suggest?date=2026-09-07&period=3', headers=h)
        assert resp.status_code == 200
        ids = [t['id'] for t in resp.get_json()['available']]
        assert 2 not in ids, 'Петров занят на Пн 3-я пара (lesson 40)'
        assert 1 in ids

        conn = db.get_db()
        conn.execute('INSERT INTO teachers (id, name, deleted_at) VALUES (99, \'Удалён\', \'2026-09-01\')')
        conn.commit()
        conn.close()
        resp = client.get('/api/schedule/substitutions-suggest?date=2026-09-07&period=1', headers=h)
        assert resp.status_code == 200
        ids = [t['id'] for t in resp.get_json()['available']]
        assert 99 not in ids, 'Удалённые преподаватели не предлагаются'

    def test_suggest_excludes_already_substituting(self, client, db, seed_days, admin_csrf):
        """Преподаватель, уже стоящий заменяющим в другом уроке на эту пару, не предлагается —
        даже если exclude_teacher_id совпадает с ним (нельзя снять его с замены)."""
        h = {'X-CSRF-Token': admin_csrf}
        conn = db.get_db()
        # Иванов (1) на period=4 уже указан как заменяющий в другом уроке
        conn.execute('''INSERT INTO lessons
                        (id, day_id, period, subject_id, teacher_id, classroom_id, group_id, is_substitution)
                        VALUES (50, 1, 4, 1, 1, 1, 1, 1)''')
        conn.commit()
        conn.close()

        resp = client.get('/api/schedule/substitutions-suggest?date=2026-09-07&period=4&exclude_teacher_id=1', headers=h)
        assert resp.status_code == 200
        ids = [t['id'] for t in resp.get_json()['available']]
        assert 1 not in ids, 'Преподаватель уже стоит заменяющим на эту пару — не должен предлагаться'
        assert 2 in ids, 'Петров свободен и должен предлагаться'

    def test_suggest_exclude_teacher_works_for_non_substitute(self, client, db, seed_lessons, admin_csrf):
        """exclude_teacher_id снимает занятость/исключение только обычного преподавателя,
        а не того, кто уже стоит как заменяющий."""
        h = {'X-CSRF-Token': admin_csrf}
        conn = db.get_db()
        # Петров (2) занят на Пн 2-я пара собственным уроком (lesson 2), НЕ как заменяющий
        resp = client.get('/api/schedule/substitutions-suggest?date=2026-09-07&period=2&exclude_teacher_id=2', headers=h)
        assert resp.status_code == 200
        ids = [t['id'] for t in resp.get_json()['available']]
        assert 2 in ids, 'Исключаемый преподаватель снимается из busy при exclude_teacher_id'
        conn.close()

    def test_create_lesson_persists_substitution_fields(self, client, db, seed_days, admin_csrf):
        """POST /api/days/1/lessons должен сохранить флаг замены и исходного преподавателя."""
        h = {'X-CSRF-Token': admin_csrf}
        resp = client.post('/api/days/1/lessons', json={
            'period': 4, 'subject_id': 1, 'teacher_id': 2, 'classroom_id': 1,
            'group_id': 1, 'is_substitution': True, 'original_teacher_id': 1,
            'substitution_reason': 'больничный',
        }, headers=h)
        assert resp.status_code == 201

        resp = client.get('/api/days?group=%D0%93%D1%80%D1%83%D0%BF%D0%BF%D0%B0-1')
        assert resp.status_code == 200
        lessons = resp.get_json()[0]['lessons']
        lesson = next(l for l in lessons if l['period'] == 4)
        assert lesson['is_substitution'] == 1
        assert lesson['original_teacher_id'] == 1
        assert lesson['substitution_reason'] == 'больничный'

    def test_update_lesson_persists_substitution_fields(self, client, db, seed_lessons, admin_csrf):
        """PUT /api/lessons/1 должен обновлять поля замены."""
        h = {'X-CSRF-Token': admin_csrf}
        resp = client.put('/api/lessons/1', json={
            'period': 1, 'subject_id': 1, 'teacher_id': 2, 'classroom_id': 1,
            'group_id': 1, 'is_substitution': True, 'original_teacher_id': 1,
            'substitution_reason': 'отпуск',
        }, headers=h)
        assert resp.status_code == 200, resp.get_json()

        resp = client.get('/api/days?group=%D0%93%D1%80%D1%83%D0%BF%D0%BF%D0%B0-1')
        assert resp.status_code == 200
        lessons = resp.get_json()[0]['lessons']
        lesson = next(l for l in lessons if l['id'] == 1)
        assert lesson['is_substitution'] == 1
        assert lesson['original_teacher_id'] == 1
        assert lesson['substitution_reason'] == 'отпуск'


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


class TestWeeksSummary:
    def test_weeks_summary_empty_year(self, client, seed_refs):
        resp = client.get('/api/weeks-summary?year=2030')
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['year'] == 2030
        assert data['active_mondays'] == []

    def test_weeks_summary_year_with_lessons(self, client, seed_lessons):
        resp = client.get('/api/weeks-summary?year=2026')
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['year'] == 2026
        assert data['active_mondays'] == ['2026-09-07']

    def test_weeks_summary_group_filter(self, client, seed_lessons):
        resp = client.get('/api/weeks-summary?year=2026&group=Группа-1')
        assert resp.status_code == 200
        assert resp.get_json()['active_mondays'] == ['2026-09-07']

        resp = client.get('/api/weeks-summary?year=2026&group=Неизвестная')
        assert resp.status_code == 200
        assert resp.get_json()['active_mondays'] == []

    def test_weeks_summary_teacher_filter(self, client, seed_lessons):
        resp = client.get('/api/weeks-summary?year=2026&teacher_id=2')
        assert resp.status_code == 200
        assert resp.get_json()['active_mondays'] == ['2026-09-07']

        resp = client.get('/api/weeks-summary?year=2026&teacher_id=999')
        assert resp.status_code == 200
        assert resp.get_json()['active_mondays'] == []

    def test_weeks_summary_invalid_year(self, client):
        resp = client.get('/api/weeks-summary?year=999')
        assert resp.status_code == 400
