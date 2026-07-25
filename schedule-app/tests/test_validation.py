import pytest

from utils import _validate_lesson_data, _safe_filename, LESSON_SELECT, LESSON_SELECT_WITH_DAY


class TestSafeFilename:
    def test_safe_filename_replaces_special_chars(self):
        assert _safe_filename('foo/bar:baz') == 'foo_bar_baz'

    def test_safe_filename_strips_underscores(self):
        assert _safe_filename('__hello__') == 'hello'

    def test_safe_filename_keeps_normal(self):
        assert _safe_filename('hello_world-123') == 'hello_world-123'

    def test_safe_filename_empty(self):
        assert _safe_filename('') == ''

    def test_safe_filename_empty(self):
        assert _safe_filename('') == ''


class TestLessonSelectConstants:
    def test_lesson_select_contains_keywords(self):
        assert 'LEFT JOIN teachers' in LESSON_SELECT
        assert 'LEFT JOIN subjects' in LESSON_SELECT
        assert 'LEFT JOIN classrooms_list' in LESSON_SELECT
        assert 'LEFT JOIN groups_list' in LESSON_SELECT

    def test_lesson_select_with_day_contains_join(self):
        assert 'JOIN schedule_days' in LESSON_SELECT_WITH_DAY
        assert 'sd.date' in LESSON_SELECT_WITH_DAY
        assert 'sd.group_name' in LESSON_SELECT_WITH_DAY


class TestValidateLessonData:
    def _setup_conflict_data(self, request):
        import db as db_module
        conn = db_module.get_db()
        conn.execute("INSERT INTO teachers (id, name) VALUES (1, 'T1')")
        conn.execute("INSERT INTO subjects (id, name) VALUES (1, 'S1')")
        conn.execute("INSERT INTO classrooms_list (id, name) VALUES (1, 'C1')")
        conn.execute("INSERT INTO groups_list (id, name) VALUES (1, 'G1')")
        conn.execute("INSERT INTO schedule_days (id, day_name, date, sort_order, group_name) VALUES (1, 'Пн', '2026-09-07', 0, 'G1')")
        conn.execute("INSERT INTO lessons (id, day_id, period, subject_id, teacher_id, classroom_id, group_id) VALUES (1, 1, 1, 1, 1, 1, 1)")
        conn.commit()
        conn.close()

        def fin():
            c = db_module.get_db()
            for t in ['lessons', 'schedule_days', 'groups_list', 'classrooms_list', 'subjects', 'teachers']:
                c.execute(f'DELETE FROM {t}')
            c.commit()
            c.close()
        request.addfinalizer(fin)

    @pytest.fixture(autouse=True)
    def setup(self, request, db):
        self._setup_conflict_data(request)

    def test_no_conflict(self):
        import db as db_module
        conn = db_module.get_db()
        warnings, blocking = _validate_lesson_data(
            conn, 1, 2, 1, 1, 1, group_id=1
        )
        assert blocking is False
        assert warnings == []

    def test_teacher_conflict(self):
        import db as db_module
        conn = db_module.get_db()
        warnings, blocking = _validate_lesson_data(
            conn, 1, 1, 1, 2, 2, group_id=1
        )
        assert blocking is True
        assert any('Teacher' in str(w) or 'teacher' in str(w) for w in warnings)

    def test_classroom_conflict(self):
        import db as db_module
        conn = db_module.get_db()
        warnings, blocking = _validate_lesson_data(
            conn, 1, 1, 2, 1, 2, group_id=1
        )
        assert blocking is True
        assert any('Classroom' in str(w) or 'classroom' in str(w) for w in warnings)

    def test_duplicate_lesson(self):
        import db as db_module
        conn = db_module.get_db()
        warnings, blocking = _validate_lesson_data(
            conn, 1, 1, 2, 2, 1, group_id=1
        )
        assert blocking is True
        assert any('Duplicate' in str(w) or 'duplicate' in str(w) for w in warnings)

    def test_exclude_id_avoids_false_conflict(self):
        import db as db_module
        conn = db_module.get_db()
        warnings, blocking = _validate_lesson_data(
            conn, 1, 1, 1, 1, 1, exclude_id=1, group_id=1
        )
        assert blocking is False
        assert warnings == []

    def test_nonexistent_day_returns_empty(self):
        import db as db_module
        conn = db_module.get_db()
        warnings, blocking = _validate_lesson_data(
            conn, 999, 1, 1, 1, 1
        )
        assert blocking is False
        assert warnings == []

    def test_no_teacher_or_classroom_no_conflict(self):
        import db as db_module
        conn = db_module.get_db()
        warnings, blocking = _validate_lesson_data(
            conn, 1, 1, None, None, None
        )
        assert blocking is False
        assert warnings == []
