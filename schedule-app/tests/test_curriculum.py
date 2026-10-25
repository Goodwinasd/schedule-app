"""Tests for curriculum planning and workload balancing."""
import pytest
from schedule_balancer import weekly_pairs, validate_weekly_load
from generator import _is_teacher_on_absence


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

    def test_generator_seeded_shuffle_produces_varied_weeks(self):
        """Two different seed values should produce different day assignments."""
        import random
        pool = [(i % 6 + 1, (i % 3) + 1) for i in range(18)]  # 18 pairs
        rng1 = random.Random("2026_30_1")
        p1 = pool[:]
        rng1.shuffle(p1)
        rng2 = random.Random("2026_31_1")
        p2 = pool[:]
        rng2.shuffle(p2)
        assert p1 != p2, "Seeded shuffle must produce different order for different weeks"

    def test_generator_seeded_shuffle_deterministic(self):
        """Same seed must produce identical order."""
        import random
        pool = [(1, 1), (1, 1), (2, 2), (3, 1)]
        rng1 = random.Random("2026_30_1")
        p1 = pool[:]
        rng1.shuffle(p1)
        rng2 = random.Random("2026_30_1")
        p2 = pool[:]
        rng2.shuffle(p2)
        assert p1 == p2, "Same seed must produce identical order"

    def test_generate_fills_remaining_not_duplicate(self, client, seed_refs, admin_csrf):
        """Generator must only add missing pairs, not duplicate existing ones."""
        h = {'X-CSRF-Token': admin_csrf}
        # Create curriculum: 72 hours / 18 weeks = 2 pairs/week
        resp = client.post('/api/curriculum', json={
            'group_id': 1, 'subject_id': 1, 'teacher_id': 1,
            'semester': 1, 'total_hours': 72,
        }, headers=h)
        assert resp.status_code == 201

        # Manually place 1 existing lesson for subject 1 (Математика) on Mon period 1
        resp = client.post('/api/days', json={
            'day_name': 'Понедельник', 'date': '2026-09-07', 'group_name': 'Группа-1'
        }, headers=h)
        assert resp.status_code == 201
        day_id = resp.get_json()['id']
        resp = client.post(f'/api/days/{day_id}/lessons', json={
            'period': 1, 'subject_id': 1, 'teacher_id': 1, 'group_id': 1,
        }, headers=h)
        assert resp.status_code == 201

        # Generate: should add only 1 more pair (2 - 1 = 1), not 2
        resp = client.post('/api/schedule/generate', json={
            'group_id': 1, 'semester': 1,
            'monday': '2026-09-07', 'week_count': 1,
        }, headers=h)
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['created'] == 1, f"Expected 1 new pair, got {data['created']}"

        # Verify total lessons for subject 1 = exactly 2
        resp = client.get('/api/schedule-table?group=%D0%93%D1%80%D1%83%D0%BF%D0%BF%D0%B0-1&monday=2026-09-07')
        assert resp.status_code == 200
        data = resp.get_json()
        total = sum(
            1 for p in data['periods']
            for d in data['days']
            for l in p['lessons'].get(d['date'], [])
            if l['subject_id'] == 1
        )
        assert total == 2, f"Expected exactly 2 Математика lessons, got {total}"

    def test_generator_substitutes_sick_teacher(self, client, seed_refs, admin_csrf):
        """A sick teacher must be replaced by a qualified substitute."""
        import db as db_module
        conn = db_module.get_db()
        # Teacher 2 (Петров) is qualified for subject 1 (Математика)
        conn.execute("INSERT INTO teacher_subjects (teacher_id, subject_id) VALUES (2, 1)")
        # Teacher 1 (Иванов) on sick leave whole week
        conn.execute("INSERT INTO teacher_absences (teacher_id, start_date, end_date, reason) VALUES (1, '2026-09-07', '2026-09-12', 'illness')")
        conn.commit()
        conn.close()
        h = {'X-CSRF-Token': admin_csrf}
        resp = client.post('/api/curriculum', json={
            'group_id': 1, 'subject_id': 1, 'teacher_id': 1,
            'semester': 1, 'total_hours': 72,
        }, headers=h)
        assert resp.status_code == 201
        resp = client.post('/api/schedule/generate', json={
            'group_id': 1, 'semester': 1, 'monday': '2026-09-07', 'week_count': 1,
        }, headers=h)
        assert resp.status_code == 200
        # Verify: no lesson by teacher 1 (sick), all by teacher 2 with substitution flag
        conn = db_module.get_db()
        lessons = conn.execute('''
            SELECT l.*, sd.date FROM lessons l JOIN schedule_days sd ON l.day_id = sd.id
            WHERE l.group_id = 1 AND l.deleted_at IS NULL AND sd.deleted_at IS NULL
        ''').fetchall()
        conn.close()
        assert len(lessons) > 0
        for l in lessons:
            assert l['teacher_id'] == 2, f"Sick teacher 1 got a lesson (id={l['id']})"
            assert l['is_substitution'] == 1, f"Lesson {l['id']} not flagged as substitution"
            assert l['original_teacher_id'] == 1, f"Lesson {l['id']} missing original_teacher"

    def test_generator_no_substitute_reports_error(self, client, seed_refs, admin_csrf):
        """If no qualified replacement exists for a sick teacher, an understandable error is reported."""
        import db as db_module
        conn = db_module.get_db()
        # Teacher 1 (Иванов) on sick leave whole week, NO substitute qualified for subject 1
        conn.execute("INSERT INTO teacher_absences (teacher_id, start_date, end_date, reason) VALUES (1, '2026-09-07', '2026-09-12', 'illness')")
        conn.commit()
        conn.close()
        h = {'X-CSRF-Token': admin_csrf}
        resp = client.post('/api/curriculum', json={
            'group_id': 1, 'subject_id': 1, 'teacher_id': 1,
            'semester': 1, 'total_hours': 72,
        }, headers=h)
        assert resp.status_code == 201
        resp = client.post('/api/schedule/generate', json={
            'group_id': 1, 'semester': 1, 'monday': '2026-09-07', 'week_count': 1,
        }, headers=h)
        assert resp.status_code == 200
        data = resp.get_json()
        # No lessons can be placed (sick + no substitute)
        assert data['created'] == 0
        assert data['errors'], "Expected a human-readable error about the missing substitute"
        joined = ' '.join(data['errors'])
        assert 'замена' in joined.lower() or 'пропущена' in joined.lower() or 'не найдена' in joined

    def test_restore_week_scopes_strictly_to_group_and_dates(self, client, seed_refs, admin_csrf):
        """Restore must revive ONLY the target group's pairs on the target week."""
        h = {'X-CSRF-Token': admin_csrf}
        # Create 2nd group
        resp = client.post('/api/groups', json={'name': 'Группа-2', 'course': 2}, headers=h)
        assert resp.status_code in (200, 201)
        g2 = resp.get_json()['id']
        # Curriculum: group1 math/teacher1, group2 physics/teacher2 (distinct, avoid collisions)
        resp = client.post('/api/curriculum', json={
            'group_id': 1, 'subject_id': 1, 'teacher_id': 1,
            'semester': 1, 'total_hours': 144,
        }, headers=h)
        assert resp.status_code == 201
        resp = client.post('/api/curriculum', json={
            'group_id': g2, 'subject_id': 2, 'teacher_id': 2,
            'semester': 1, 'total_hours': 144,
        }, headers=h)
        assert resp.status_code == 201
        for gid in (1, g2):
            resp = client.post('/api/schedule/generate', json={
                'group_id': gid, 'semester': 1, 'monday': '2026-09-07', 'weeks_count': 1,
            }, headers=h)
            assert resp.status_code == 200
        # Group 1 also has Week B (2026-09-14) generated
        resp = client.post('/api/schedule/generate', json={
            'group_id': 1, 'semester': 1, 'monday': '2026-09-14', 'weeks_count': 1,
        }, headers=h)
        assert resp.status_code == 200
        # Soft-delete Week A for group 1 only and Week A for group 2, plus week B for group 1
        for gid, start in [(1, '2026-09-07'), (g2, '2026-09-07'), (1, '2026-09-14')]:
            resp = client.delete(f'/api/schedule/clear-week?start_date={start}&group_id={gid}', headers=h)
            assert resp.status_code == 200
        # Now restore ONLY group 1 on Week A
        resp = client.post('/api/schedule/restore-week?start_date=2026-09-07&group_id=1', headers=h)
        assert resp.status_code == 200
        restored = resp.get_json()['restored_count']
        assert restored > 0 and restored <= 24, f"restored={restored} out of range"
        # Week A group 1 pairs revived (active)
        import db as db_module
        conn = db_module.get_db()
        g1a = conn.execute('''
            SELECT COUNT(*) FROM lessons l JOIN schedule_days sd ON l.day_id = sd.id
            WHERE l.group_id = 1 AND sd.date BETWEEN '2026-09-07' AND '2026-09-12' AND l.deleted_at IS NULL AND sd.deleted_at IS NULL
        ''').fetchone()[0]
        # Week B group 1 still deleted
        g1b_deleted = conn.execute('''
            SELECT COUNT(*) FROM lessons l JOIN schedule_days sd ON l.day_id = sd.id
            WHERE l.group_id = 1 AND sd.date BETWEEN '2026-09-14' AND '2026-09-19' AND l.deleted_at IS NOT NULL AND sd.deleted_at IS NOT NULL
        ''').fetchone()[0]
        # Week A group 2 still deleted
        g2a_deleted = conn.execute('''
            SELECT COUNT(*) FROM lessons l JOIN schedule_days sd ON l.day_id = sd.id
            WHERE l.group_id = ? AND sd.date BETWEEN '2026-09-07' AND '2026-09-12' AND l.deleted_at IS NOT NULL AND sd.deleted_at IS NOT NULL
        ''', (g2,)).fetchone()[0]
        conn.close()
        assert g1a == restored, f"expected {restored} restored for grp1 wkA, got {g1a}"
        assert g1b_deleted >= 1, "Week B of group 1 must remain deleted"
        assert g2a_deleted >= 1, "Week A of group 2 must remain deleted"

    def test_delete_week_scopes_strictly_to_group_and_dates(self, client, seed_refs, admin_csrf):
        """Deleting one group's week must not touch other groups or adjacent weeks."""
        h = {'X-CSRF-Token': admin_csrf}
        import db as db_module
        # Two groups, generate Week A for both, Week B for group 1
        resp = client.post('/api/groups', json={'name': 'Группа-2', 'course': 2}, headers=h)
        assert resp.status_code in (200, 201)
        g2 = resp.get_json()['id']
        resp = client.post('/api/curriculum', json={
            'group_id': 1, 'subject_id': 1, 'teacher_id': 1,
            'semester': 1, 'total_hours': 144,
        }, headers=h)
        assert resp.status_code == 201
        resp = client.post('/api/curriculum', json={
            'group_id': g2, 'subject_id': 2, 'teacher_id': 2,
            'semester': 1, 'total_hours': 144,
        }, headers=h)
        assert resp.status_code == 201
        for gid in (1, g2):
            resp = client.post('/api/schedule/generate', json={
                'group_id': gid, 'semester': 1, 'monday': '2026-09-07', 'weeks_count': 1,
            }, headers=h)
            assert resp.status_code == 200
        resp = client.post('/api/schedule/generate', json={
            'group_id': 1, 'semester': 1, 'monday': '2026-09-14', 'weeks_count': 1,
        }, headers=h)
        assert resp.status_code == 200
        # Delete only group 1 Week A
        resp = client.delete('/api/schedule/clear-week?start_date=2026-09-07&group_id=1', headers=h)
        assert resp.status_code == 200
        assert resp.get_json()['deleted_count'] <= 24
        # Verify: group 1 Week A deleted, group 1 Week B intact, group 2 Week A intact
        conn = db_module.get_db()
        g1a_active = conn.execute('''
            SELECT COUNT(*) FROM lessons l JOIN schedule_days sd ON l.day_id = sd.id
            WHERE l.group_id = 1 AND sd.date BETWEEN '2026-09-07' AND '2026-09-12' AND l.deleted_at IS NULL AND sd.deleted_at IS NULL
        ''').fetchone()[0]
        g1b_active = conn.execute('''
            SELECT COUNT(*) FROM lessons l JOIN schedule_days sd ON l.day_id = sd.id
            WHERE l.group_id = 1 AND sd.date BETWEEN '2026-09-14' AND '2026-09-19' AND l.deleted_at IS NULL AND sd.deleted_at IS NULL
        ''').fetchone()[0]
        g2a_active = conn.execute('''
            SELECT COUNT(*) FROM lessons l JOIN schedule_days sd ON l.day_id = sd.id
            WHERE l.group_id = ? AND sd.date BETWEEN '2026-09-07' AND '2026-09-12' AND l.deleted_at IS NULL AND sd.deleted_at IS NULL
        ''', (g2,)).fetchone()[0]
        conn.close()
        assert g1a_active == 0, f"Group1 WeekA should be empty, got {g1a_active}"
        assert g1b_active >= 1, f"Group1 WeekB must be intact, got {g1b_active}"
        assert g2a_active >= 1, f"Group2 WeekA must be intact, got {g2a_active}"

    def test_clear_week_isolates_even_with_many_pairs(self, client, seed_refs, admin_csrf):
        """Clearing a week must isolate to the target group even if it holds many pairs."""
        import db as db_module
        h = {'X-CSRF-Token': admin_csrf}
        conn = db_module.get_db()
        # Ensure the day exists, then add 40 pairs for group 1 on the week
        day = conn.execute("SELECT id FROM schedule_days WHERE group_name='Группа-1' AND date='2026-09-07'").fetchone()
        if not day:
            cur = conn.execute("INSERT INTO schedule_days (day_name, date, group_name) VALUES ('Понедельник','2026-09-07','Группа-1')")
            day_id = cur.lastrowid
        else:
            day_id = day['id']
        for i in range(40):
            conn.execute(
                "INSERT INTO lessons (day_id, period, subject_id, teacher_id, group_id) VALUES (?, ?, 1, 1, 1)",
                (day_id, (i % 8) + 1)
            )
        conn.commit()
        conn.close()
        # Clear must succeed (200) and delete exactly those 40 pairs of group 1 only
        resp = client.delete('/api/schedule/clear-week?start_date=2026-09-07&group_id=1', headers=h)
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.get_json()}"
        assert resp.get_json()['deleted_count'] == 40

    def test_generate_schedule_monthly_batch(self, client, seed_refs, admin_csrf):
        """Batch generation (weeks_count=4) must produce schedule on 4 distinct weeks without collisions."""
        h = {'X-CSRF-Token': admin_csrf}
        resp = client.post('/api/curriculum', json={
            'group_id': 1, 'subject_id': 1, 'teacher_id': 1,
            'semester': 1, 'total_hours': 144,
        }, headers=h)
        assert resp.status_code == 201
        resp = client.post('/api/schedule/generate', json={
            'group_id': 1, 'semester': 1, 'monday': '2026-09-07', 'weeks_count': 4,
        }, headers=h)
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['weeks_processed'] == 4
        assert data['created'] > 0
        # Verify distinct weeks (dates in 4 different ISO weeks, 7 days apart starts)
        import db as db_module
        conn = db_module.get_db()
        rows = conn.execute('''
            SELECT sd.date FROM lessons l JOIN schedule_days sd ON l.day_id = sd.id
            WHERE l.group_id = 1 AND l.deleted_at IS NULL AND sd.deleted_at IS NULL
        ''').fetchall()
        conn.close()
        dates = sorted({r['date'] for r in rows})
        # 1st course: 4 pairs/week on periods 1-4 → 4 distinct days per week; 4 weeks = 16
        assert len(dates) >= 16, f"Expected lessons across 4 weeks (>=16 distinct days), got {len(dates)}"
        # Ensure start dates span > 1 week (multiple calendar weeks present)
        import datetime as _dt
        parsed = [_dt.date.fromisoformat(d) for d in dates]
        weeks_set = set((dd.isocalendar()[0], dd.isocalendar()[1]) for dd in parsed)
        assert len(weeks_set) >= 3, f"Expected >=3 distinct ISO weeks, got {len(weeks_set)}"
        # Ensure no collisions via 3D: no two lessons share (date, period, teacher)
        conn = db_module.get_db()
        dup = conn.execute('''
            SELECT COUNT(*) FROM lessons l1 JOIN lessons l2 ON l1.id < l2.id
            JOIN schedule_days sd1 ON l1.day_id = sd1.id
            JOIN schedule_days sd2 ON l2.day_id = sd2.id
            WHERE sd1.date = sd2.date AND l1.period = l2.period AND l1.teacher_id = l2.teacher_id
              AND l1.deleted_at IS NULL AND l2.deleted_at IS NULL AND sd1.deleted_at IS NULL AND sd2.deleted_at IS NULL
        ''').fetchone()[0]
        dup_room = conn.execute('''
            SELECT COUNT(*) FROM lessons l1 JOIN lessons l2 ON l1.id < l2.id
            JOIN schedule_days sd1 ON l1.day_id = sd1.id
            JOIN schedule_days sd2 ON l2.day_id = sd2.id
            WHERE sd1.date = sd2.date AND l1.period = l2.period
              AND l1.classroom_id = l2.classroom_id AND l1.classroom_id IS NOT NULL
              AND l1.deleted_at IS NULL AND l2.deleted_at IS NULL AND sd1.deleted_at IS NULL AND sd2.deleted_at IS NULL
        ''').fetchone()[0]
        dup_group = conn.execute('''
            SELECT COUNT(*) FROM lessons l1 JOIN lessons l2 ON l1.id < l2.id
            JOIN schedule_days sd1 ON l1.day_id = sd1.id
            JOIN schedule_days sd2 ON l2.day_id = sd2.id
            WHERE sd1.date = sd2.date AND l1.period = l2.period AND l1.group_id = l2.group_id
              AND l1.deleted_at IS NULL AND l2.deleted_at IS NULL AND sd1.deleted_at IS NULL AND sd2.deleted_at IS NULL
        ''').fetchone()[0]
        conn.close()
        assert dup == 0, f"{dup} teacher collisions"
        assert dup_room == 0, f"{dup_room} classroom collisions"
        assert dup_group == 0, f"{dup_group} group collisions"

    def test_clear_week_scopes_to_group(self, client, seed_refs, admin_csrf):
        """Deleting a week must affect ONLY the target group, not others."""
        h = {'X-CSRF-Token': admin_csrf}
        # Create second group
        resp = client.post('/api/groups', json={'name': 'Группа-2', 'course': 2}, headers=h)
        assert resp.status_code in (200, 201)
        g2 = resp.get_json()['id']
        # Create curriculum for both groups
        for gid in (1, g2):
            resp = client.post('/api/curriculum', json={
                'group_id': gid, 'subject_id': 1, 'teacher_id': 1,
                'semester': 1, 'total_hours': 144,
            }, headers=h)
            assert resp.status_code == 201
        # Generate for both groups on same week
        for gid in (1, g2):
            resp = client.post('/api/schedule/generate', json={
                'group_id': gid, 'semester': 1, 'monday': '2026-09-07', 'week_count': 1,
            }, headers=h)
            assert resp.status_code == 200
        # Delete week for group 1 only
        resp = client.delete('/api/schedule/clear-week?start_date=2026-09-07&group_id=1', headers=h)
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['deleted_count'] > 0
        assert data['deleted_count'] < 36, f"deleted too many: {data['deleted_count']} (must be only group 1)"
        # Group 1 week now empty
        g1_table = client.get('/api/schedule-table?group=%D0%93%D1%80%D1%83%D0%BF%D0%BF%D0%B0-1&monday=2026-09-07').get_json()
        assert g1_table['week_exists'] is False
        # Group 2 week intact
        from urllib.parse import quote
        g2_name = next(g['name'] for g in client.get('/api/groups').get_json() if g['id'] == g2)
        g2_table = client.get(f'/api/schedule-table?group={quote(g2_name)}&monday=2026-09-07').get_json()
        assert g2_table['week_exists'] is True

    def test_curriculum_progress_calculation(self, client, seed_refs, admin_csrf):
        """Progress endpoint must compute expected vs actual pace correctly."""
        h = {'X-CSRF-Token': admin_csrf}
        # Plan: 30 pairs total over 15 weeks -> plan_pairs=30
        # total_hours so that weekly*weeks=30: choose weeks=15, weekly=2 -> total_hours=60, weeks=15
        # weekly=2 requires ceil(total_hours/(15*2))=2 -> total_hours between 45 and 60
        resp = client.post('/api/curriculum', json={
            'group_id': 1, 'subject_id': 1, 'teacher_id': 1,
            'semester': 1, 'total_hours': 60, 'weeks_in_semester': 15,
        }, headers=h)
        assert resp.status_code == 201
        # Insert 10 actual pairs (already conducted) across weeks before week 5
        conn = __import__('db', fromlist=['get_db']).get_db()
        day_names = ['Понедельник', 'Вторник', 'Среда', 'Четверг', 'Пятница', 'Суббота']
        # Create 10 schedule days (first 2 weeks * 5 days)
        conn.execute("INSERT INTO schedule_days (day_name, date, group_name) VALUES ('Понедельник','2026-09-07','Группа-1')")
        for i in range(10):
            day_id = conn.execute("SELECT id FROM schedule_days WHERE group_name='Группа-1' ORDER BY id LIMIT 1").fetchone()['id']
            conn.execute("INSERT INTO lessons (day_id, period, subject_id, teacher_id, group_id) VALUES (?, ?, 1, 1, 1)",
                         (day_id, (i % 4) + 1))
        conn.commit()
        conn.close()
        # Query progress at week 5 of 15 (expected = (30/15)*5 = 10)
        resp = client.get('/api/curriculum/progress?group_id=1&semester=1&current_week=5&total_weeks=15')
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['group_id'] == 1
        subjects = data['subjects']
        math_subj = next((s for s in subjects if s['subject_id'] == 1), None)
        assert math_subj is not None
        assert math_subj['plan_pairs'] == 30, f"plan_pairs={math_subj['plan_pairs']}"
        assert math_subj['actual_pairs'] == 10, f"actual={math_subj['actual_pairs']}"
        assert math_subj['expected_pairs'] == 10, f"expected={math_subj['expected_pairs']}"
        assert math_subj['delta_pace'] == 0, f"delta={math_subj['delta_pace']}"
        assert math_subj['status'] == 'success', f"status={math_subj['status']}"

    def test_generator_controlled_shift_drift(self, client, seed_refs, admin_csrf):
        """Старт всегда с 1-й пары (по реальным расписаниям 1 курса), без разрывов.

        Раньше здесь проверялся «дрейф» старта (1 и 2). Реальные расписания
        начинаются с 1-й пары в 81% дней, а сдвиг к 4-5 создавал «дыру» в начале дня.
        """
        import db as db_module
        h = {'X-CSRF-Token': admin_csrf}
        # Create a senior-course group (course=2) so evening shifts are allowed
        resp = client.post('/api/groups', json={'name': '02-Тест', 'course': 2}, headers=h)
        assert resp.status_code in (200, 201)
        gid = resp.get_json()['id']
        conn = db_module.get_db()
        conn.execute("INSERT INTO curriculum (group_id, subject_id, teacher_id, semester, total_hours, weeks_in_semester) VALUES (?, 1, 1, 1, 144, 18)", (gid,))
        conn.commit()
        conn.close()
        # Generate 6 weeks to cover many start-period rolls
        resp = client.post('/api/schedule/generate', json={
            'group_id': gid, 'semester': 1, 'monday': '2026-07-27', 'week_count': 6,
        }, headers=h)
        assert resp.status_code == 200
        assert resp.get_json()['created'] > 0
        # Read all generated lessons grouped by (date) and check no windows inside day
        lessons = db_module.get_db().execute('''
            SELECT l.period, sd.date, sd.group_name FROM lessons l
            JOIN schedule_days sd ON l.day_id = sd.id
            WHERE l.group_id = ? AND l.deleted_at IS NULL AND sd.deleted_at IS NULL
            ORDER BY sd.date, l.period
        ''', (gid,)).fetchall()
        periods_seen = set()
        days = {}
        for l in lessons:
            periods_seen.add(l['period'])
            days.setdefault(l['date'], []).append(l['period'])
        # Каждый учебный день начинается с 1-й пары
        assert 1 in periods_seen, "No period 1 lessons generated"
        for date_str, ps in days.items():
            assert min(ps) == 1, f"День {date_str} начинается не с 1-й пары: {sorted(ps)}"
        # No windows: within each day periods must be contiguous starting from min
        for date_str, ps in days.items():
            ps = sorted(set(ps))
            start = ps[0]
            for i, p in enumerate(ps):
                assert p == start + i, f"Window in schedule on {date_str}: {ps}"

    def test_generator_3d_collision_prevention(self, client, seed_refs, admin_csrf):
        """100% no collisions across group/teacher/classroom in generated schedule."""
        import db as db_module
        h = {'X-CSRF-Token': admin_csrf}
        resp = client.post('/api/groups', json={'name': 'Группа-2', 'course': 1}, headers=h)
        assert resp.status_code in (200, 201)
        g2 = resp.get_json()['id']
        # Two groups, different subjects but same teacher to force collisions
        conn = db_module.get_db()
        conn.execute("INSERT INTO curriculum (group_id, subject_id, teacher_id, semester, total_hours, weeks_in_semester) VALUES (1, 1, 1, 1, 144, 18)")
        conn.execute("INSERT INTO curriculum (group_id, subject_id, teacher_id, semester, total_hours, weeks_in_semester) VALUES (?, 2, 1, 1, 144, 18)", (g2,))
        conn.commit()
        conn.close()
        for gid in (1, g2):
            resp = client.post('/api/schedule/generate', json={
                'group_id': gid, 'semester': 1, 'monday': '2026-09-07', 'week_count': 1,
            }, headers=h)
            assert resp.status_code == 200
        # Check via _validate_slot_3d-style SQL: no two lessons share (date, period, teacher) or (date, period, classroom)
        conn = db_module.get_db()
        dup_teacher = conn.execute('''
            SELECT COUNT(*) FROM lessons l1 JOIN lessons l2 ON l1.id < l2.id
            JOIN schedule_days sd1 ON l1.day_id = sd1.id
            JOIN schedule_days sd2 ON l2.day_id = sd2.id
            WHERE sd1.date = sd2.date AND l1.period = l2.period AND l1.teacher_id = l2.teacher_id
              AND l1.deleted_at IS NULL AND l2.deleted_at IS NULL AND sd1.deleted_at IS NULL AND sd2.deleted_at IS NULL
        ''').fetchone()[0]
        dup_room = conn.execute('''
            SELECT COUNT(*) FROM lessons l1 JOIN lessons l2 ON l1.id < l2.id
            JOIN schedule_days sd1 ON l1.day_id = sd1.id
            JOIN schedule_days sd2 ON l2.day_id = sd2.id
            WHERE sd1.date = sd2.date AND l1.period = l2.period AND l1.classroom_id = l2.classroom_id
              AND l1.classroom_id IS NOT NULL
              AND l1.deleted_at IS NULL AND l2.deleted_at IS NULL AND sd1.deleted_at IS NULL AND sd2.deleted_at IS NULL
        ''').fetchone()[0]
        conn.close()
        assert dup_teacher == 0, f"{dup_teacher} teacher collisions found"
        assert dup_room == 0, f"{dup_room} classroom collisions found"

    def test_generator_first_course_only_first_shift(self, client, seed_refs, admin_csrf):
        """First-course groups must never get period >= 5, even on even weeks."""
        h = {'X-CSRF-Token': admin_csrf}
        # Create a first-course group
        resp = client.get('/api/groups')
        first_course = None
        for g in resp.get_json():
            if g['course'] == 1:
                first_course = g
                break
        if not first_course:
            # Create one ourselves
            resp = client.post('/api/groups', json={'name': '01-Тест', 'course': 1}, headers=h)
            assert resp.status_code in (200, 201)
            first_course = resp.get_json()
        gid = first_course['id']
        gname = first_course['name']
        resp = client.post('/api/curriculum', json={
            'group_id': gid, 'subject_id': 1, 'teacher_id': 1,
            'semester': 1, 'total_hours': 144,
        }, headers=h)
        assert resp.status_code == 201  # 144h / 18w = 4 pairs/week = max load
        # Generate on an even week (2026-09-07 is ISO week 37 -> odd, but 2026-09-14 is week 38 -> even)
        resp = client.post('/api/schedule/generate', json={
            'group_id': gid, 'semester': 1,
            'monday': '2026-09-14', 'week_count': 1,
        }, headers=h)
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['created'] > 0
        # Verify no period >= 5
        resp = client.get(f'/api/days?group={gname}')
        assert resp.status_code == 200
        days = resp.get_json()
        for day in days:
            for l in day.get('lessons', []):
                assert l['period'] <= 4, f"First-course lesson on period {l['period']} (must be 1-4)"

    def test_generator_classroom_no_double_booking(self, client, seed_refs, admin_csrf):
        """Two groups sharing the same teacher must not get the same classroom at the same time."""
        h = {'X-CSRF-Token': admin_csrf}
        # Create 2nd group
        resp = client.post('/api/groups', json={'name': 'Группа-2', 'course': 1}, headers=h)
        assert resp.status_code == 201
        group2_id = resp.get_json()['id']
        # Same subject, same teacher for both groups
        resp = client.post('/api/curriculum', json={
            'group_id': 1, 'subject_id': 1, 'teacher_id': 1,
            'semester': 1, 'total_hours': 72,
        }, headers=h)
        assert resp.status_code == 201
        resp = client.post('/api/curriculum', json={
            'group_id': group2_id, 'subject_id': 1, 'teacher_id': 1,
            'semester': 1, 'total_hours': 72,
        }, headers=h)
        assert resp.status_code == 201
        # Generate for both groups on same week
        resp1 = client.post('/api/schedule/generate', json={
            'group_id': 1, 'semester': 1, 'monday': '2026-09-07', 'week_count': 1,
        }, headers=h)
        assert resp1.status_code == 200
        resp2 = client.post('/api/schedule/generate', json={
            'group_id': group2_id, 'semester': 1, 'monday': '2026-09-07', 'week_count': 1,
        }, headers=h)
        assert resp2.status_code == 200
        # Check: no classroom_id collision between groups on same date+period
        conn = __import__('sqlite3').connect(':memory:')
        import importlib
        import sys
        sys.path.insert(0, '')
        from db import get_db as _gdb
        _gdb_cached = None
        def get_db():
            nonlocal _gdb_cached
            if _gdb_cached is None:
                _gdb_cached = _gdb()
            return _gdb_cached
        # Actually just read from test client's DB
        # Go through API: verify no two lessons share classroom+date+period across groups
        resp = client.get('/api/schedule-table?group=%D0%93%D1%80%D1%83%D0%BF%D0%BF%D0%B0-1&monday=2026-09-07')
        assert resp.status_code == 200
        data1 = resp.get_json()
        resp = client.get('/api/schedule-table?group=%D0%93%D1%80%D1%83%D0%BF%D0%BF%D0%B0-2&monday=2026-09-07')
        assert resp.status_code == 200
        data2 = resp.get_json()
        slots_g1 = set()
        for p in data1['periods']:
            for d in data1['days']:
                for l in p['lessons'].get(d['date'], []):
                    if l['classroom_id']:
                        slots_g1.add((d['date'], p['period'], l['classroom_id']))
        collisions = 0
        for p in data2['periods']:
            for d in data2['days']:
                for l in p['lessons'].get(d['date'], []):
                    if l['classroom_id'] and (d['date'], p['period'], l['classroom_id']) in slots_g1:
                        collisions += 1
        assert collisions == 0, f"Found {collisions} classroom double-booking(s) between groups"

    def test_generator_september_first_only_first_course(self, client, seed_refs, admin_csrf):
        """Sept 1 (линейка) skips pairs ONLY for first-course groups; seniors study normally."""
        h = {'X-CSRF-Token': admin_csrf}
        # Senior group (course=2), 5 pairs/week so a pair lands on 2026-09-01 (Tue, even week)
        resp = client.post('/api/groups', json={'name': '02-Тест', 'course': 2}, headers=h)
        assert resp.status_code in (200, 201)
        senior_id = resp.get_json()['id']
        for gid in (1, senior_id):
            resp = client.post('/api/curriculum', json={
                'group_id': gid, 'subject_id': 1, 'teacher_id': 1,
                'semester': 1, 'total_hours': 180,
            }, headers=h)
            assert resp.status_code == 201
        # Week 2026-08-31 (ISO week 36, even) → day_order reversed [5,4,3,2,1,0];
        # 5 pairs → Sat,Fri,Thu,Wed,Tue, so Tuesday 2026-09-01 gets the 5th pair
        resp = client.post('/api/schedule/generate', json={
            'group_id': 1, 'semester': 1, 'monday': '2026-08-31', 'week_count': 1,
        }, headers=h)
        assert resp.status_code == 200
        assert resp.get_json()['created'] == 4, "first course must skip Sept 1 (5 pairs - 1)"
        resp = client.post('/api/schedule/generate', json={
            'group_id': senior_id, 'semester': 1, 'monday': '2026-08-31', 'week_count': 1,
        }, headers=h)
        assert resp.status_code == 200
        assert resp.get_json()['created'] == 5, "senior course must study on Sept 1 (all 5 pairs)"
        import db as db_module
        conn = db_module.get_db()
        first_course_sept1 = conn.execute('''
            SELECT COUNT(*) FROM lessons l JOIN schedule_days sd ON l.day_id = sd.id
            WHERE l.group_id = 1 AND sd.date = '2026-09-01'
              AND l.deleted_at IS NULL AND sd.deleted_at IS NULL
        ''').fetchone()[0]
        senior_sept1 = conn.execute('''
            SELECT COUNT(*) FROM lessons l JOIN schedule_days sd ON l.day_id = sd.id
            WHERE l.group_id = ? AND sd.date = '2026-09-01'
              AND l.deleted_at IS NULL AND sd.deleted_at IS NULL
        ''', (senior_id,)).fetchone()[0]
        conn.close()
        assert first_course_sept1 == 0, "first-course group must have no pairs on Sept 1"
        assert senior_sept1 == 1, "senior group must have its pair on Sept 1"
