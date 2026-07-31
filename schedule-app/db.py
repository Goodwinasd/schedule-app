import os
import shutil
import sqlite3
import time
import logging
from datetime import datetime

import config

logger = logging.getLogger(__name__)
SLOW_THRESHOLD_MS = int(os.environ.get('SLOW_QUERY_THRESHOLD_MS', '500'))
_slow_counter = 0
BACKUPS_DIR = config.BACKUPS_DIR
MAX_BACKUPS = 10


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
        except sqlite3.OperationalError:
            elapsed = (time.perf_counter() - start) * 1000
            if elapsed > SLOW_THRESHOLD_MS:
                logger.warning("LOCKED (%.0fms): %s", elapsed, sql.strip()[:200])
            raise
        except sqlite3.IntegrityError:
            raise
        except Exception as e:
            elapsed = (time.perf_counter() - start) * 1000
            if 'OperationalError' not in type(e).__name__:
                logger.error("QUERY FAIL (%.0fms): %s | %s", elapsed, sql.strip()[:200], str(e)[:200])
            raise


def get_db():
    conn = _TimedConnection(config.DB_PATH, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA cache_size=-8000")
    conn.execute("PRAGMA temp_store=MEMORY")
    conn.execute("PRAGMA mmap_size=268435456")
    return conn


def ensure_curriculum_table():
    """Create the curriculum table if it doesn't exist."""
    conn = get_db()
    conn.execute('''CREATE TABLE IF NOT EXISTS curriculum (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        group_id INTEGER NOT NULL,
        subject_id INTEGER NOT NULL,
        teacher_id INTEGER,
        semester INTEGER NOT NULL DEFAULT 1,
        total_hours INTEGER NOT NULL DEFAULT 72,
        weeks_in_semester INTEGER NOT NULL DEFAULT 18,
        UNIQUE(group_id, subject_id, semester)
    )''')
    conn.commit()
    conn.close()


def ensure_teacher_tables():
    """Create teacher_absences and teacher_subjects if they don't exist."""
    conn = get_db()
    conn.execute('''CREATE TABLE IF NOT EXISTS teacher_absences (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        teacher_id INTEGER NOT NULL,
        start_date TEXT NOT NULL,
        end_date TEXT NOT NULL,
        reason TEXT
    )''')
    conn.execute('''CREATE TABLE IF NOT EXISTS teacher_subjects (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        teacher_id INTEGER NOT NULL,
        subject_id INTEGER NOT NULL
    )''')
    conn.commit()
    conn.close()


def run_alembic_upgrade():
    """Применить все неприменённые миграции через Alembic.
    Используется в production (app.py) и в тестах (conftest.py)."""
    from alembic.config import Config
    from alembic.command import upgrade
    from sqlalchemy.pool import NullPool
    base = os.path.dirname(os.path.abspath(__file__))
    ini_path = os.path.join(base, 'alembic.ini')
    if not os.path.exists(ini_path):
        return
    alembic_cfg = Config(ini_path)
    alembic_cfg.set_main_option('script_location', os.path.join(base, 'migrations'))
    alembic_cfg.set_main_option('sqlalchemy.url', f"sqlite:///{config.DB_PATH.replace(os.sep, '/')}")
    alembic_cfg.set_main_option('sqlalchemy.poolclass', 'sqlalchemy.pool.NullPool')
    upgrade(alembic_cfg, 'head')
    conn = get_db()
    conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    conn.close()


def prepare_for_restore():
    if not os.path.exists(config.DB_PATH):
        return
    try:
        conn = _TimedConnection(config.DB_PATH, timeout=5)
        conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        conn.close()
    except Exception:
        pass
    for ext in ('-wal', '-shm'):
        p = config.DB_PATH + ext
        if os.path.exists(p):
            try:
                os.remove(p)
                logger.info("Removed %s before restore", ext)
            except OSError:
                logger.warning("Could not remove %s", p)


def verify_db_integrity():
    try:
        conn = _TimedConnection(config.DB_PATH, timeout=5)
        row = conn.execute("PRAGMA integrity_check").fetchone()
        conn.close()
        if row and row[0] == 'ok':
            return True, None
        return False, row[0] if row else 'unknown error'
    except Exception as e:
        return False, str(e)


def create_backup():
    os.makedirs(BACKUPS_DIR, exist_ok=True)
    if not os.path.exists(config.DB_PATH):
        logger.warning("DB file not found at %s, skipping backup", config.DB_PATH)
        return
    ts = datetime.now().strftime('%Y-%m-%d_%H-%M-%S')
    backup_path = os.path.join(BACKUPS_DIR, f'db_backup_{ts}.sqlite')
    shutil.copy2(config.DB_PATH, backup_path)
    logger.info("Backup created: %s", backup_path)
    _rotate_backups()


def _rotate_backups():
    backups = sorted([
        f for f in os.listdir(BACKUPS_DIR)
        if f.startswith('db_backup_') and f.endswith('.sqlite')
    ])
    while len(backups) > MAX_BACKUPS:
        oldest = backups.pop(0)
        os.remove(os.path.join(BACKUPS_DIR, oldest))
        logger.info("Removed old backup: %s", oldest)


def find_orphaned_records():
    conn = get_db()
    orphans = {'lessons': [], 'curriculum': []}
    for ref_table, ref_col in [('teachers', 'teacher_id'), ('groups_list', 'group_id'),
                                ('subjects', 'subject_id'), ('classrooms_list', 'classroom_id')]:
        rows = conn.execute(f'''
            SELECT id, {ref_col} FROM lessons
            WHERE {ref_col} IS NOT NULL AND {ref_col} != ''
            AND {ref_col} NOT IN (SELECT id FROM {ref_table} WHERE deleted_at IS NULL)
            AND deleted_at IS NULL
        ''').fetchall()
        for r in rows:
            orphans['lessons'].append({'id': r['id'], 'ref_col': ref_col, 'ref_val': r[ref_col], 'ref_table': ref_table})
    for ref_table, ref_col in [('teachers', 'teacher_id'), ('groups_list', 'group_id'),
                                ('subjects', 'subject_id')]:
        rows = conn.execute(f'''
            SELECT id, {ref_col} FROM curriculum
            WHERE {ref_col} IS NOT NULL AND {ref_col} != ''
            AND {ref_col} NOT IN (SELECT id FROM {ref_table} WHERE deleted_at IS NULL)
        ''').fetchall()
        for r in rows:
            orphans['curriculum'].append({'id': r['id'], 'ref_col': ref_col, 'ref_val': r[ref_col], 'ref_table': ref_table})
    conn.close()
    return orphans


def cleanup_orphan_schedule_records(force_delete=False):
    orphans = find_orphaned_records()
    total = len(orphans['lessons']) + len(orphans['curriculum'])
    if total == 0:
        logger.info("No orphan records found")
        return {'deleted': 0, 'found': 0, 'lessons': [], 'curriculum': []}
    logger.warning("Found %d orphan records (%d lessons, %d curriculum). Audit only — use force_delete=True to remove.", total, len(orphans['lessons']), len(orphans['curriculum']))
    if not force_delete:
        return {'deleted': 0, 'found': total, 'lessons': orphans['lessons'], 'curriculum': orphans['curriculum']}
    conn = get_db()
    for ref_table, ref_col in [('teachers', 'teacher_id'), ('groups_list', 'group_id'),
                                ('subjects', 'subject_id'), ('classrooms_list', 'classroom_id')]:
        conn.execute(f'''
            UPDATE lessons SET deleted_at = datetime('now', 'localtime')
            WHERE {ref_col} IS NOT NULL AND {ref_col} != ''
            AND {ref_col} NOT IN (SELECT id FROM {ref_table} WHERE deleted_at IS NULL)
            AND deleted_at IS NULL
        ''')
    for ref_table, ref_col in [('teachers', 'teacher_id'), ('groups_list', 'group_id'),
                                ('subjects', 'subject_id')]:
        conn.execute(f'''
            DELETE FROM curriculum
            WHERE {ref_col} IS NOT NULL AND {ref_col} != ''
            AND {ref_col} NOT IN (SELECT id FROM {ref_table} WHERE deleted_at IS NULL)
        ''')
    conn.commit()
    conn.close()
    logger.info("Cleanup completed: soft-deleted %d lessons, hard-deleted %d curriculum rows", len(orphans['lessons']), len(orphans['curriculum']))
    return {'deleted': total, 'found': total, 'lessons': orphans['lessons'], 'curriculum': orphans['curriculum']}


def is_date_excluded(conn, date_str):
    row = conn.execute(
        "SELECT 1 FROM excluded_dates WHERE start_date <= ? AND end_date >= ? LIMIT 1",
        (date_str, date_str)
    ).fetchone()
    return row is not None
