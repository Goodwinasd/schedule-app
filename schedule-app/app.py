# Изменение №4 (бэкенд-рефакторинг): выделены маршруты в routes.py

import os
import logging
from datetime import datetime

from flask import Flask, request
from flask_cors import CORS
from flasgger import Swagger
from apscheduler.schedulers.background import BackgroundScheduler

from config import (
    SECRET_KEY, PERMANENT_SESSION_LIFETIME, BACKUPS_DIR, DB_PATH, DATA_DIR, DEBUG, HOST, PORT,
    TRASH_RETENTION_DAYS,
)
from db import create_backup, get_db, run_alembic_upgrade, ensure_curriculum_table, seed_specialties, cleanup_orphan_schedule_records
from routes import bp

logger = logging.getLogger(__name__)

app = Flask(__name__)
app.secret_key = SECRET_KEY
app.permanent_session_lifetime = PERMANENT_SESSION_LIFETIME
CORS(app)
app.register_blueprint(bp)

# Не кэшировать статику (JS-модули, CSS, иконки): браузер всегда
# запрашивает актуальную версию файлов, чтобы правки в ui.js и др.
# отражались без ручной очистки кэша
app.config['SEND_FILE_MAX_AGE_DEFAULT'] = 0

@app.after_request
def _no_cache_static(resp):
    if request.path.startswith('/static/'):
        resp.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
        resp.headers['Pragma'] = 'no-cache'
        resp.headers['Expires'] = '0'
    return resp

Swagger(app)


def _cleanup_old_deleted():
    conn = get_db()
    retention = f'-{TRASH_RETENTION_DAYS} days'
    conn.execute("DELETE FROM lessons WHERE deleted_at IS NOT NULL AND deleted_at < datetime('now', ?)", (retention,))
    conn.execute("DELETE FROM schedule_days WHERE deleted_at IS NOT NULL AND deleted_at < datetime('now', ?)", (retention,))
    conn.commit()
    conn.close()


def _maybe_create_backup():
    """Один бэкап в сутки. Саму копию делает db.create_backup() (VACUUM INTO + retention),
    чтобы в проекте была ровно одна система бэкапов."""
    if not os.path.exists(DB_PATH):
        return
    today = datetime.now().strftime('%Y-%m-%d')
    existing = [f for f in os.listdir(BACKUPS_DIR)
                if f.startswith(f'schedule_backup_{today}') and f.endswith('.db')]
    if existing:
        return
    create_backup()


def _run_backup_tasks():
    os.makedirs(BACKUPS_DIR, exist_ok=True)
    _maybe_create_backup()


if __name__ == '__main__':
    os.makedirs(DATA_DIR, exist_ok=True)
    os.makedirs(BACKUPS_DIR, exist_ok=True)

    _run_backup_tasks()

    scheduler = BackgroundScheduler(daemon=True)
    scheduler.add_job(_run_backup_tasks, 'interval', hours=6, id='backup_job')
    scheduler.start()

    run_alembic_upgrade()
    ensure_curriculum_table()
    seed_specialties()
    cleanup_orphan_schedule_records()  # audit-only at startup (force_delete=False)
    _cleanup_old_deleted()
    app.run(debug=DEBUG, host=HOST, port=PORT)
