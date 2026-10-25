"""Регрессии по итогам аудита: частичный PUT, метки удаления, публичные поля, 400 вместо 500.

Каждый тест соответствует конкретному исправлению в routes.py / settings.js.
"""


class TestPartialUpdate:
    """PUT урока не должен затирать поля, которых нет в теле запроса."""

    def test_partial_put_preserves_fields(self, client, seed_lessons, db, admin_csrf):
        resp = client.put('/api/lessons/1', json={'period': 3},
                          headers={'X-CSRF-Token': admin_csrf})
        assert resp.status_code == 200, resp.get_json()
        conn = db.get_db()
        row = conn.execute(
            'SELECT period, subject_id, teacher_id, classroom_id, group_id FROM lessons WHERE id = 1'
        ).fetchone()
        conn.close()
        assert row['period'] == 3
        assert (row['subject_id'], row['teacher_id'], row['classroom_id'], row['group_id']) == (1, 1, 1, 1)


class TestSoftDeleteTimestamps:
    """Повторное удаление дня не должно перезаписывать время удаления уроков."""

    def test_repeated_delete_keeps_original_timestamp(self, client, seed_lessons, db, admin_csrf):
        conn = db.get_db()
        conn.execute("UPDATE lessons SET deleted_at = '2020-01-01 00:00:00' WHERE id = 1")
        conn.commit()
        conn.close()

        resp = client.delete('/api/days/1', headers={'X-CSRF-Token': admin_csrf})
        assert resp.status_code == 200

        conn = db.get_db()
        row = conn.execute('SELECT deleted_at FROM lessons WHERE id = 1').fetchone()
        conn.close()
        assert row['deleted_at'] == '2020-01-01 00:00:00'


class TestDeleteWeekReporting:
    """Счётчики удаления недели считают только реально изменённые сейчас записи."""

    def test_second_delete_reports_zero(self, client, seed_days, admin_csrf):
        url = '/api/week?monday=2026-09-07&target_type=group&target_id=Группа-1'
        first = client.delete(url, headers={'X-CSRF-Token': admin_csrf}).get_json()
        second = client.delete(url, headers={'X-CSRF-Token': admin_csrf}).get_json()
        assert first['days_deleted'] >= 2
        assert second['days_deleted'] == 0

    def test_teacher_delete_warns_about_other_groups(self, client, seed_lessons, admin_csrf):
        resp = client.delete('/api/week?monday=2026-09-07&target_type=teacher&target_id=1',
                             headers={'X-CSRF-Token': admin_csrf})
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['groups_affected'] == 1
        assert 'warning' in data and data['warning']


class TestPublicReferenceFields:
    """Публичные справочники не отдают внутренние колонки; админ получает всё."""

    def test_public_teachers_hide_phone_and_deleted_at(self, client, seed_refs, db):
        conn = db.get_db()
        conn.execute("UPDATE teachers SET phone = '+7-900-000-00-00' WHERE id = 1")
        conn.commit()
        conn.close()

        items = client.get('/api/teachers').get_json()
        assert items, 'список не должен быть пустым'
        for item in items:
            assert 'phone' not in item
            assert 'deleted_at' not in item
        assert all(item.get('name') for item in items)

    def test_admin_teachers_keep_phone(self, client, seed_refs, db, admin_csrf):
        conn = db.get_db()
        conn.execute("UPDATE teachers SET phone = '+7-900-000-00-00' WHERE id = 1")
        conn.commit()
        conn.close()

        items = client.get('/api/teachers').get_json()
        teacher = next(i for i in items if i['id'] == 1)
        assert teacher['phone'] == '+7-900-000-00-00'

    def test_public_groups_keep_public_fields(self, client, seed_refs):
        items = client.get('/api/groups').get_json()
        assert items
        group = next(i for i in items if i['id'] == 1)
        assert group['name'] == 'Группа-1'
        assert 'course' in group
        assert 'deleted_at' not in group


class TestExportPermissions:
    """Массовый экспорт — только админ; одиночный остаётся публичным."""

    def test_bulk_export_requires_admin(self, client, seed_lessons):
        resp = client.get('/api/schedule/export/excel?type=all&start_date=2026-09-07')
        assert resp.status_code == 401

    def test_single_group_export_stays_public(self, client, seed_lessons):
        resp = client.get('/api/export?type=group&name=Группа-1&monday=2026-09-07&format=xlsx')
        assert resp.status_code == 200


class TestBackupRestore:
    """Восстановление БД: раньше падало 500 на refs_cache.invalidate_all()."""

    def test_restore_finishes_without_server_error(self, client, seed_refs, db, admin_csrf):
        import io

        import config

        # В тестах config.DB_PATH указывает на временный файл, поэтому перезапись
        # безопасна. Чекпоинт нужен, чтобы копия содержала всё, что ещё лежит в WAL.
        conn = db.get_db()
        conn.execute('PRAGMA wal_checkpoint(FULL)')
        conn.close()
        with open(config.DB_PATH, 'rb') as f:
            payload = f.read()

        resp = client.post(
            '/api/admin/backup/restore',
            data={'file': (io.BytesIO(payload), 'backup.db')},
            headers={'X-CSRF-Token': admin_csrf},
            content_type='multipart/form-data',
        )
        assert resp.status_code == 200, resp.get_json()
        assert resp.get_json()['success'] is True


class TestBadInputReturns400:
    """Кривые параметры — 400, а не 500 с трассировкой."""

    def test_schedule_table_bad_monday(self, client, seed_refs):
        resp = client.get('/api/schedule-table?group=Группа-1&monday=garbage')
        assert resp.status_code == 400

    def test_export_bad_monday(self, client, seed_refs):
        resp = client.get('/api/export?type=group&name=Группа-1&monday=garbage&format=xlsx')
        assert resp.status_code == 400

    def test_teacher_schedule_bad_id(self, client, seed_refs):
        resp = client.get('/api/teacher-schedule?teacher_id=abc')
        assert resp.status_code == 400

    def test_teacher_schedule_table_bad_monday(self, client, seed_refs):
        resp = client.get('/api/teacher-schedule-table?teacher_id=1&monday=garbage')
        assert resp.status_code == 400

    def test_delete_week_bad_monday(self, client, admin_csrf):
        resp = client.delete('/api/week?monday=garbage&target_type=group&target_id=Группа-1',
                             headers={'X-CSRF-Token': admin_csrf})
        assert resp.status_code == 400

    def test_create_day_without_date(self, client, admin_csrf):
        resp = client.post('/api/days', json={'day_name': 'Понедельник'},
                           headers={'X-CSRF-Token': admin_csrf})
        assert resp.status_code == 400

    def test_update_day_without_payload(self, client, seed_days, admin_csrf):
        resp = client.put('/api/days/1', json={}, headers={'X-CSRF-Token': admin_csrf})
        assert resp.status_code == 400
