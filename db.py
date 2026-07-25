import os
import sqlite3
import re
import time
import logging

import config

logger = logging.getLogger(__name__)
SLOW_THRESHOLD_MS = int(os.environ.get('SLOW_QUERY_THRESHOLD_MS', '100'))
_slow_counter = 0


class _TimedConnection(sqlite3.Connection):
    """Connection subclass that logs slow queries."""

    def execute(self, sql, parameters=None):
        start = time.perf_counter()
        try:
            result = super().execute(sql, parameters or ())
            elapsed = (time.perf_counter() - start) * 1000
            if elapsed > SLOW_THRESHOLD_MS:
                global _slow_counter
                _slow_counter += 1
                params_str = str(parameters) if parameters else ''
                logger.warning(
                    "SLOW QUERY #%d (%.0fms): %s | %s",
                    _slow_counter, elapsed,
                    sql.strip()[:200].replace('\n', ' '),
                    params_str[:200]
                )
            return result
        except Exception:
            elapsed = (time.perf_counter() - start) * 1000
            logger.error("QUERY FAIL (%.0fms): %s", elapsed, sql.strip()[:200])
            raise


def get_db():
    conn = _TimedConnection(config.DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA cache_size=-8000")
    conn.execute("PRAGMA temp_store=MEMORY")
    conn.execute("PRAGMA mmap_size=268435456")
    return conn


def init_db():
    conn = get_db()
    conn.executescript('''
        CREATE TABLE IF NOT EXISTS schedule_days (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            day_name TEXT NOT NULL,
            date TEXT NOT NULL,
            sort_order INTEGER NOT NULL DEFAULT 0,
            group_name TEXT DEFAULT '',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS lessons (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            day_id INTEGER NOT NULL,
            period INTEGER NOT NULL,
            subject_id INTEGER,
            teacher_id INTEGER,
            classroom_id INTEGER,
            group_id INTEGER,
            subgroup INTEGER DEFAULT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (day_id) REFERENCES schedule_days(id) ON DELETE CASCADE,
            FOREIGN KEY (teacher_id) REFERENCES teachers(id),
            FOREIGN KEY (subject_id) REFERENCES subjects(id),
            FOREIGN KEY (classroom_id) REFERENCES classrooms_list(id),
            FOREIGN KEY (group_id) REFERENCES groups_list(id)
        );

        CREATE TABLE IF NOT EXISTS subjects (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE
        );

        CREATE TABLE IF NOT EXISTS teachers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS groups_list (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            course INTEGER DEFAULT 1,
            is_distance INTEGER DEFAULT 0
        );

        CREATE TABLE IF NOT EXISTS classrooms_list (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL
        );
    ''')
    conn.commit()

    # Migration: add course/is_distance to groups_list if missing
    cols = [r[1] for r in conn.execute("PRAGMA table_info(groups_list)").fetchall()]
    if 'course' not in cols:
        conn.execute("ALTER TABLE groups_list ADD COLUMN course INTEGER DEFAULT 1")
    if 'is_distance' not in cols:
        conn.execute("ALTER TABLE groups_list ADD COLUMN is_distance INTEGER DEFAULT 0")
    conn.commit()

    # Migration: text fields -> FK columns in lessons
    lesson_cols = [r[1] for r in conn.execute("PRAGMA table_info(lessons)").fetchall()]
    if 'teacher' in lesson_cols and 'teacher_id' not in lesson_cols:
        conn.execute("ALTER TABLE lessons ADD COLUMN teacher_id INTEGER")
        conn.execute("ALTER TABLE lessons ADD COLUMN subject_id INTEGER")
        conn.execute("ALTER TABLE lessons ADD COLUMN classroom_id INTEGER")

        conn.execute("""UPDATE lessons SET teacher_id = (
            SELECT t.id FROM teachers t WHERE t.name = lessons.teacher
        ) WHERE teacher != ''""")
        conn.execute("""UPDATE lessons SET subject_id = (
            SELECT s.id FROM subjects s WHERE s.name = lessons.subject
        ) WHERE subject != ''""")
        conn.execute("""UPDATE lessons SET classroom_id = (
            SELECT c.id FROM classrooms_list c WHERE c.name = lessons.classroom
        ) WHERE classroom != ''""")

        conn.execute("""INSERT INTO teachers (name) SELECT DISTINCT teacher FROM lessons
            WHERE teacher != '' AND teacher_id IS NULL""")
        conn.execute("""UPDATE lessons SET teacher_id = (
            SELECT t.id FROM teachers t WHERE t.name = lessons.teacher
        ) WHERE teacher != '' AND teacher_id IS NULL""")

        conn.execute("""INSERT INTO subjects (name) SELECT DISTINCT subject FROM lessons
            WHERE subject != '' AND subject_id IS NULL""")
        conn.execute("""UPDATE lessons SET subject_id = (
            SELECT s.id FROM subjects s WHERE s.name = lessons.subject
        ) WHERE subject != '' AND subject_id IS NULL""")

        conn.execute("""INSERT INTO classrooms_list (name) SELECT DISTINCT classroom FROM lessons
            WHERE classroom != '' AND classroom_id IS NULL""")
        conn.execute("""UPDATE lessons SET classroom_id = (
            SELECT c.id FROM classrooms_list c WHERE c.name = lessons.classroom
        ) WHERE classroom != '' AND classroom_id IS NULL""")

        for idx_name in ['idx_lessons_teacher', 'idx_lessons_subject', 'idx_lessons_classroom']:
            conn.execute(f"DROP INDEX IF EXISTS {idx_name}")
        conn.execute("ALTER TABLE lessons DROP COLUMN teacher")
        conn.execute("ALTER TABLE lessons DROP COLUMN subject")
        conn.execute("ALTER TABLE lessons DROP COLUMN classroom")
        conn.commit()

    # Migration: groups TEXT -> group_id + subgroup
    if 'groups' in lesson_cols and 'group_id' not in lesson_cols:
        conn.execute("ALTER TABLE lessons ADD COLUMN group_id INTEGER")
        conn.execute("ALTER TABLE lessons ADD COLUMN subgroup INTEGER DEFAULT NULL")

        all_groups = conn.execute("SELECT id, groups FROM lessons WHERE groups != ''").fetchall()
        for row in all_groups:
            g = row['groups'] or ''
            m = re.search(r'\((\d+)\)\s*$', g)
            subgroup_val = int(m.group(1)) if m else None
            group_name = g[:m.start()].strip() if m else g.strip()
            if not group_name:
                continue
            existing = conn.execute("SELECT id FROM groups_list WHERE name = ?", (group_name,)).fetchone()
            if existing:
                gid = existing['id']
            else:
                gid = conn.execute("INSERT INTO groups_list (name, course, is_distance) VALUES (?, 1, 0)", (group_name,)).lastrowid
            conn.execute("UPDATE lessons SET group_id = ?, subgroup = ? WHERE id = ?", (gid, subgroup_val, row['id']))

        conn.execute("ALTER TABLE lessons DROP COLUMN groups")
        conn.commit()
    conn.execute("CREATE INDEX IF NOT EXISTS idx_days_group_date ON schedule_days(group_name, date)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_lessons_day_period ON lessons(day_id, period)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_lessons_teacher_id ON lessons(teacher_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_lessons_subject_id ON lessons(subject_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_lessons_classroom_id ON lessons(classroom_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_lessons_group_id ON lessons(group_id)")

    # Migration: excluded_dates table
    existing_tables = [r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
    if 'excluded_dates' not in existing_tables:
        conn.execute('''
            CREATE TABLE excluded_dates (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                start_date TEXT NOT NULL,
                end_date TEXT NOT NULL,
                reason TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')

    # Migration: deleted_at columns for soft delete
    lesson_cols = [r[1] for r in conn.execute("PRAGMA table_info(lessons)").fetchall()]
    if 'deleted_at' not in lesson_cols:
        conn.execute("ALTER TABLE lessons ADD COLUMN deleted_at TIMESTAMP NULL")
    day_cols = [r[1] for r in conn.execute("PRAGMA table_info(schedule_days)").fetchall()]
    if 'deleted_at' not in day_cols:
        conn.execute("ALTER TABLE schedule_days ADD COLUMN deleted_at TIMESTAMP NULL")
    conn.commit()
    conn.execute("CREATE INDEX IF NOT EXISTS idx_lessons_deleted_at ON lessons(deleted_at)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_days_deleted_at ON schedule_days(deleted_at)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_days_date_deleted ON schedule_days(date, deleted_at)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_days_group_date_deleted ON schedule_days(group_name, date, deleted_at)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_lessons_day_period_deleted ON lessons(day_id, period, deleted_at)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_lessons_teacher_deleted_subj ON lessons(teacher_id, deleted_at, subject_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_lessons_classroom_deleted_subj ON lessons(classroom_id, deleted_at, subject_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_lessons_day_deleted ON lessons(day_id, deleted_at)")

    # Migration: lesson_history table
    if 'lesson_history' not in existing_tables:
        conn.execute('''
            CREATE TABLE lesson_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                lesson_id INTEGER NOT NULL,
                changed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                old_subject_id INTEGER,
                old_teacher_id INTEGER,
                old_classroom_id INTEGER,
                old_group_id INTEGER,
                old_subgroup INTEGER,
                FOREIGN KEY (lesson_id) REFERENCES lessons(id) ON DELETE CASCADE
            )
        ''')

    # Migration: default_teacher_id on subjects
    subject_cols = [r[1] for r in conn.execute("PRAGMA table_info(subjects)").fetchall()]
    if 'default_teacher_id' not in subject_cols:
        conn.execute("ALTER TABLE subjects ADD COLUMN default_teacher_id INTEGER NULL")

    conn.execute("CREATE INDEX IF NOT EXISTS idx_lesson_history_lesson_id ON lesson_history(lesson_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_lesson_history_changed_at ON lesson_history(changed_at)")

    conn.commit()
    conn.close()


def is_date_excluded(conn, date_str):
    row = conn.execute(
        "SELECT 1 FROM excluded_dates WHERE start_date <= ? AND end_date >= ? LIMIT 1",
        (date_str, date_str)
    ).fetchone()
    return row is not None
