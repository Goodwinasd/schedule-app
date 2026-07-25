import os
import sqlite3
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
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            deleted_at TIMESTAMP NULL
        );
        CREATE TABLE IF NOT EXISTS subjects (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE,
            default_teacher_id INTEGER NULL
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
            deleted_at TIMESTAMP NULL,
            FOREIGN KEY (day_id) REFERENCES schedule_days(id) ON DELETE CASCADE,
            FOREIGN KEY (teacher_id) REFERENCES teachers(id),
            FOREIGN KEY (subject_id) REFERENCES subjects(id),
            FOREIGN KEY (classroom_id) REFERENCES classrooms_list(id),
            FOREIGN KEY (group_id) REFERENCES groups_list(id)
        );
        CREATE TABLE IF NOT EXISTS excluded_dates (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            start_date TEXT NOT NULL,
            end_date TEXT NOT NULL,
            reason TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS lesson_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            lesson_id INTEGER NOT NULL,
            changed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            old_subject_id INTEGER,
            old_teacher_id INTEGER,
            old_classroom_id INTEGER,
            old_group_id INTEGER,
            old_subgroup INTEGER,
            FOREIGN KEY (lesson_id) REFERENCES lessons(id) ON DELETE CASCADE
        );
    ''')
    conn.commit()
    _create_indices(conn)
    conn.close()


def _create_indices(conn):
    for idx in [
        'CREATE INDEX IF NOT EXISTS idx_days_group_date ON schedule_days(group_name, date)',
        'CREATE INDEX IF NOT EXISTS idx_days_group_date_deleted ON schedule_days(group_name, date, deleted_at)',
        'CREATE INDEX IF NOT EXISTS idx_lessons_day_period ON lessons(day_id, period)',
        'CREATE INDEX IF NOT EXISTS idx_lessons_day_period_deleted ON lessons(day_id, period, deleted_at)',
        'CREATE INDEX IF NOT EXISTS idx_lessons_teacher_id ON lessons(teacher_id)',
        'CREATE INDEX IF NOT EXISTS idx_lessons_teacher_deleted_subj ON lessons(teacher_id, deleted_at, subject_id)',
        'CREATE INDEX IF NOT EXISTS idx_lessons_subject_id ON lessons(subject_id)',
        'CREATE INDEX IF NOT EXISTS idx_lessons_classroom_id ON lessons(classroom_id)',
        'CREATE INDEX IF NOT EXISTS idx_lessons_classroom_deleted_subj ON lessons(classroom_id, deleted_at, subject_id)',
        'CREATE INDEX IF NOT EXISTS idx_lessons_group_id ON lessons(group_id)',
        'CREATE INDEX IF NOT EXISTS idx_lessons_deleted_at ON lessons(deleted_at)',
        'CREATE INDEX IF NOT EXISTS idx_days_deleted_at ON schedule_days(deleted_at)',
        'CREATE INDEX IF NOT EXISTS idx_days_date_deleted ON schedule_days(date, deleted_at)',
        'CREATE INDEX IF NOT EXISTS idx_lessons_day_deleted ON lessons(day_id, deleted_at)',
        'CREATE INDEX IF NOT EXISTS idx_lesson_history_lesson_id ON lesson_history(lesson_id)',
        'CREATE INDEX IF NOT EXISTS idx_lesson_history_changed_at ON lesson_history(changed_at)',
    ]:
        conn.execute(idx)


def run_alembic_upgrade():
    """Запуск Alembic миграций (только для production/разработки, не для тестов).
    Вызывается из app.py при старте."""
    from alembic.config import Config
    from alembic.command import upgrade
    import os
    base = os.path.dirname(os.path.abspath(__file__))
    if not os.path.exists(os.path.join(base, 'alembic.ini')):
        return
    alembic_cfg = Config(os.path.join(base, 'alembic.ini'))
    alembic_cfg.set_main_option('script_location', os.path.join(base, 'migrations'))
    alembic_cfg.set_main_option('sqlalchemy.url', f"sqlite:///{config.DB_PATH.replace(os.sep, '/')}")
    upgrade(alembic_cfg, 'head')


def is_date_excluded(conn, date_str):
    row = conn.execute(
        "SELECT 1 FROM excluded_dates WHERE start_date <= ? AND end_date >= ? LIMIT 1",
        (date_str, date_str)
    ).fetchone()
    return row is not None
