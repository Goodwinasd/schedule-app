class TestExportIntegration:
    """Экспорт с реальными данными + проверка содержимого."""

    def _seed_schedule(self, client, csrf):
        h = {'X-CSRF-Token': csrf}
        client.post('/api/days/batch', json={'days': [
            {'day_name': 'Понедельник', 'date': '2026-09-07', 'group_name': 'ИС-31'},
            {'day_name': 'Вторник',     'date': '2026-09-08', 'group_name': 'ИС-31'},
        ]}, headers=h)
        days = client.get('/api/days?group=ИС-31').get_json()
        client.post(f'/api/days/{days[0]["id"]}/lessons', json={
            'period': 1, 'subject_id': 1, 'teacher_id': 1, 'classroom_id': 1, 'group_id': 1
        }, headers=h)
        client.post(f'/api/days/{days[0]["id"]}/lessons', json={
            'period': 2, 'subject_id': 2, 'teacher_id': 2, 'classroom_id': 2, 'group_id': 1
        }, headers=h)

    def test_export_xlsx_has_content(self, client, refs):
        self._seed_schedule(client, refs)
        resp = client.get('/api/export?type=group&name=ИС-31&monday=2026-09-07&format=xlsx')
        assert resp.status_code == 200
        assert 'spreadsheetml' in resp.content_type
        assert len(resp.data) > 2000

    def test_export_docx_has_content(self, client, refs):
        self._seed_schedule(client, refs)
        resp = client.get('/api/export?type=group&name=ИС-31&monday=2026-09-07&format=docx')
        assert resp.status_code == 200
        assert resp.mimetype == 'application/vnd.openxmlformats-officedocument.wordprocessingml.document'
        assert len(resp.data) > 2000

    def test_export_pdf_has_content(self, client, refs):
        self._seed_schedule(client, refs)
        resp = client.get('/api/export?type=group&name=ИС-31&monday=2026-09-07&format=pdf')
        assert resp.status_code == 200
        assert resp.mimetype == 'application/pdf'
        assert len(resp.data) > 2000

    def test_export_teacher(self, client, refs):
        self._seed_schedule(client, refs)
        resp = client.get('/api/export?type=teacher&name=Иванов И.И.&monday=2026-09-07&format=xlsx')
        assert resp.status_code == 200
        assert len(resp.data) > 2000

    def test_export_classroom(self, client, refs):
        self._seed_schedule(client, refs)
        resp = client.get('/api/export?type=classroom&name=101&monday=2026-09-07&format=xlsx')
        assert resp.status_code == 200
        assert len(resp.data) > 2000


class TestAvailabilityIntegration:
    """Проверка /api/availability с уроками."""

    def test_availability_with_lessons(self, client, refs):
        csrf = refs
        h = {'X-CSRF-Token': csrf}

        client.post('/api/days/batch', json={'days': [
            {'day_name': 'Понедельник', 'date': '2026-09-07', 'group_name': 'ИС-31'},
            {'day_name': 'Вторник',     'date': '2026-09-08', 'group_name': 'ИС-31'},
        ]}, headers=h)
        days = client.get('/api/days?group=ИС-31').get_json()

        client.post(f'/api/days/{days[0]["id"]}/lessons', json={
            'period': 1, 'subject_id': 1, 'teacher_id': 1, 'classroom_id': 1, 'group_id': 1
        }, headers=h)
        client.post(f'/api/days/{days[0]["id"]}/lessons', json={
            'period': 2, 'subject_id': 2, 'teacher_id': 2, 'classroom_id': 1, 'group_id': 1
        }, headers=h)
        client.post(f'/api/days/{days[1]["id"]}/lessons', json={
            'period': 1, 'subject_id': 3, 'teacher_id': 1, 'classroom_id': 2, 'group_id': 1
        }, headers=h)

        resp = client.get('/api/availability?monday=2026-09-07')
        assert resp.status_code == 200
        data = resp.get_json()

        assert len(data['days']) == 6
        assert len(data['periods']) == 8
        assert len(data['teachers']) == 2
        assert len(data['classrooms']) == 3

        tb = data['teacher_busy']
        assert '1' in tb
        assert '2026-09-07_1' in tb['1']
        assert '2026-09-07_2' not in tb['1']
        assert '2026-09-08_1' in tb['1']
        assert tb['1']['2026-09-07_1']['subject'] == 'Математика'
        assert tb['1']['2026-09-08_1']['subject'] == 'Информатика'

        assert '2' in tb
        assert '2026-09-07_2' in tb['2']

        cb = data['classroom_busy']
        assert '1' in cb
        assert '2026-09-07_1' in cb['1']
        assert '2026-09-07_2' in cb['1']
        assert '2' in cb
        assert '2026-09-08_1' in cb['2']


class TestTrashIntegration:
    """Проверка корзины и очистки."""

    def test_trash_after_operations(self, client, refs):
        csrf = refs
        h = {'X-CSRF-Token': csrf}

        client.post('/api/days/batch', json={'days': [
            {'day_name': 'Понедельник', 'date': '2026-09-07', 'group_name': 'ИС-31'},
            {'day_name': 'Вторник',     'date': '2026-09-08', 'group_name': 'ИС-31'},
        ]}, headers=h)
        days = client.get('/api/days?group=ИС-31').get_json()

        client.post(f'/api/days/{days[0]["id"]}/lessons', json={
            'period': 1, 'subject_id': 1, 'teacher_id': 1, 'classroom_id': 1, 'group_id': 1
        }, headers=h)
        client.post(f'/api/days/{days[1]["id"]}/lessons', json={
            'period': 2, 'subject_id': 2, 'teacher_id': 2, 'classroom_id': 2, 'group_id': 1
        }, headers=h)

        trash = client.get('/api/trash', headers=h).get_json()
        assert len(trash['days']) == 0
        assert len(trash['lessons']) == 0

        client.delete('/api/days/1', headers=h)
        trash = client.get('/api/trash', headers=h).get_json()
        assert len(trash['days']) == 1
        assert trash['days'][0]['id'] == 1
        assert len(trash['lessons']) == 1

        remaining_lesson_id = trash['days'][0]['id'] + 1
        resp = client.delete(f'/api/lessons/{remaining_lesson_id}', headers=h)
        assert resp.status_code == 200
        trash = client.get('/api/trash', headers=h).get_json()
        assert len(trash['days']) == 1
        assert len(trash['lessons']) == 2

        client.post('/api/days/1/restore', headers=h)
        trash = client.get('/api/trash', headers=h).get_json()
        assert len(trash['days']) == 0
        assert len(trash['lessons']) == 1

    def test_trash_requires_auth(self, client):
        resp = client.get('/api/trash')
        assert resp.status_code == 401
