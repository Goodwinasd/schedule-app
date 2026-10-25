"""Регрессии по итогам аудита: частичный PUT, метки удаления, публичные поля, 400 вместо 500.

Каждый тест соответствует конкретному исправлению в routes.py / settings.js.
"""

import pytest


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


class TestRestoreLessonIntoDeletedDay:
    """Нельзя восстановить урок в удалённый день: он стал бы «невидимым»."""

    def test_restore_lesson_blocked_when_day_deleted(self, client, seed_lessons, db, admin_csrf):
        conn = db.get_db()
        conn.execute("UPDATE lessons SET deleted_at = datetime('now') WHERE id = 1")
        conn.execute("UPDATE schedule_days SET deleted_at = datetime('now') WHERE id = 1")
        conn.commit()
        conn.close()

        resp = client.post('/api/lessons/1/restore', headers={'X-CSRF-Token': admin_csrf})
        assert resp.status_code == 409, resp.get_json()
        assert 'День' in resp.get_json()['error']

        conn = db.get_db()
        row = conn.execute('SELECT deleted_at FROM lessons WHERE id = 1').fetchone()
        conn.close()
        assert row['deleted_at'] is not None, 'урок не должен восстановиться'

    def test_restore_lesson_ok_when_day_alive(self, client, seed_lessons, db, admin_csrf):
        conn = db.get_db()
        conn.execute("UPDATE lessons SET deleted_at = datetime('now') WHERE id = 1")
        conn.commit()
        conn.close()

        resp = client.post('/api/lessons/1/restore', headers={'X-CSRF-Token': admin_csrf})
        assert resp.status_code == 200, resp.get_json()


class TestConfigValidation:
    """Слабый пароль и дефолтный ключ: внятная ошибка вместо молчаливого sys.exit."""

    def test_missing_password_raises(self):
        import config
        with pytest.raises(RuntimeError):
            config._require_strong_password('')

    def test_weak_passwords_raise(self):
        import config
        for bad in ('short1!', 'NoDigits!', 'NoSpecial1'):
            with pytest.raises(RuntimeError):
                config._require_strong_password(bad)

    def test_strong_password_passes(self):
        import config
        config._require_strong_password('GoodPass123!')

    def test_leaked_and_placeholder_secrets_detected(self):
        import config
        assert config._is_weak_secret('0384e0d154b345d12a37d51db9a846b11647ace477f27991')
        assert config._is_weak_secret('change-me-please')
        assert not config._is_weak_secret('5f2c9a1b7e4d3c8a0b6f1e9d2c7a4b3f')
        assert not config._is_weak_secret('')

    def test_config_error_is_runtime_error(self):
        import config
        assert issubclass(config.ConfigError, RuntimeError)


class TestAvailabilityUsesCustomBellSchedule:
    """availability должна брать схему звонков из настроек, а не хардкод BELL_SCHEDULE."""

    def test_custom_bell_schedule_visible_in_availability(self, client, seed_refs, admin_csrf):
        original = client.get('/api/bell-schedule').get_json()
        custom = [{'period': 1, 'start': '09:15', 'end': '10:30', 'shift': 1}]
        try:
            resp = client.put('/api/admin/bell-schedule', json={'schedule': custom},
                              headers={'X-CSRF-Token': admin_csrf})
            assert resp.status_code == 200, resp.get_json()

            data = client.get('/api/availability?monday=2026-09-07').get_json()
            assert data['periods'] == [{'period': 1, 'start': '09:15', 'end': '10:30'}], data['periods']
        finally:
            client.put('/api/admin/bell-schedule', json={'schedule': original},
                       headers={'X-CSRF-Token': admin_csrf})


class TestGenerateWeekCountLimit:
    """Нельзя генерировать произвольно много недель одним запросом."""

    def test_too_many_weeks_rejected(self, client, seed_refs, admin_csrf):
        resp = client.post('/api/schedule/generate',
                           json={'group_id': 1, 'semester': 1, 'monday': '2026-09-07', 'week_count': 13},
                           headers={'X-CSRF-Token': admin_csrf})
        assert resp.status_code == 400, resp.get_json()
        assert 'недел' in resp.get_json()['error'].lower()

    def test_non_integer_week_count_rejected(self, client, seed_refs, admin_csrf):
        resp = client.post('/api/schedule/generate',
                           json={'group_id': 1, 'semester': 1, 'monday': '2026-09-07', 'week_count': 'много'},
                           headers={'X-CSRF-Token': admin_csrf})
        assert resp.status_code == 400

    def test_alias_weeks_count_still_clamped_to_four(self, client, seed_refs, admin_csrf):
        resp = client.post('/api/schedule/generate',
                           json={'group_id': 1, 'semester': 1, 'monday': '2026-09-07', 'weeks_count': 99},
                           headers={'X-CSRF-Token': admin_csrf})
        assert resp.status_code == 200
        assert resp.get_json()['weeks_processed'] <= 4


class TestPdfExportEscaping:
    """Символы &, <, > из БД не должны ломать XML-парсер reportlab."""

    def test_pdf_export_with_special_chars_in_data(self, client, seed_lessons, db):
        conn = db.get_db()
        conn.execute("UPDATE subjects SET name = ? WHERE id = 1", ('Математика & <Тригонометрия>',))
        conn.execute("UPDATE teachers SET name = ? WHERE id = 1", ('Иванов & <И.И.>',))
        conn.commit()
        conn.close()

        resp = client.get('/api/export', query_string={
            'type': 'group', 'name': 'Группа-1', 'monday': '2026-09-07', 'format': 'pdf',
        })
        assert resp.status_code == 200, resp.data[:300]
        assert resp.mimetype == 'application/pdf'
        assert resp.data.startswith(b'%PDF')

    def test_pdf_font_fallback_warns(self, monkeypatch, caplog):
        import logging

        import routes
        monkeypatch.delenv('PDF_FONT_PATH', raising=False)
        monkeypatch.setattr(routes.os.path, 'exists', lambda p: False)
        with caplog.at_level(logging.WARNING):
            path, bold = routes._resolve_pdf_font()
        assert path is None and bold is None
        assert any('кириллиц' in r.getMessage().lower() or 'шрифт' in r.getMessage().lower()
                   for r in caplog.records), [r.getMessage() for r in caplog.records]

    def test_pdf_safe_escapes_reportlab_markup(self):
        import routes
        assert routes._pdf_safe('Математика & <Тригонометрия>') == \
            'Математика &amp; &lt;Тригонометрия&gt;'
        assert routes._pdf_safe('без спецсимволов') == 'без спецсимволов'
        assert routes._pdf_safe(None) == ''
