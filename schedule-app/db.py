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


def run_alembic_upgrade():
    """Применить все неприменённые миграции через Alembic.
    Используется в production (app.py) и в тестах (conftest.py)."""
    from alembic.config import Config
    from alembic.command import upgrade
    base = os.path.dirname(os.path.abspath(__file__))
    ini_path = os.path.join(base, 'alembic.ini')
    if not os.path.exists(ini_path):
        return
    alembic_cfg = Config(ini_path)
    alembic_cfg.set_main_option('script_location', os.path.join(base, 'migrations'))
    alembic_cfg.set_main_option('sqlalchemy.url', f"sqlite:///{config.DB_PATH.replace(os.sep, '/')}")
    upgrade(alembic_cfg, 'head')


def is_date_excluded(conn, date_str):
    row = conn.execute(
        "SELECT 1 FROM excluded_dates WHERE start_date <= ? AND end_date >= ? LIMIT 1",
        (date_str, date_str)
    ).fetchone()
    return row is not None


def is_date_excluded(conn, date_str):
    row = conn.execute(
        "SELECT 1 FROM excluded_dates WHERE start_date <= ? AND end_date >= ? LIMIT 1",
        (date_str, date_str)
    ).fetchone()
    return row is not None
