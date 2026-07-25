# Изменение №4 (бэкенд-рефакторинг): выделены маршруты в routes.py

import os
import shutil
from datetime import datetime, timedelta

from flask import Flask
from flask_cors import CORS
from flasgger import Swagger

from config import (
    SECRET_KEY, PERMANENT_SESSION_LIFETIME, BACKUPS_DIR, DB_PATH, DATA_DIR, DEBUG, HOST, PORT
)
from db import get_db, init_db, run_alembic_upgrade
from routes import bp

app = Flask(__name__)
app.secret_key = SECRET_KEY
app.permanent_session_lifetime = PERMANENT_SESSION_LIFETIME
CORS(app)
app.register_blueprint(bp)

Swagger(app)


def _cleanup_old_deleted():
    conn = get_db()
    conn.execute("DELETE FROM lessons WHERE deleted_at IS NOT NULL AND deleted_at < datetime('now', '-30 days')")
    conn.execute("DELETE FROM schedule_days WHERE deleted_at IS NOT NULL AND deleted_at < datetime('now', '-30 days')")
    conn.commit()
    conn.close()


if __name__ == '__main__':
    os.makedirs(DATA_DIR, exist_ok=True)
    os.makedirs(BACKUPS_DIR, exist_ok=True)
    today = datetime.now().strftime('%Y-%m-%d')
    existing = [f for f in os.listdir(BACKUPS_DIR)
                if f.startswith(f'schedule_backup_{today}') and f.endswith('.db')]
    if not existing and os.path.exists(DB_PATH):
        ts = datetime.now().strftime('%Y-%m-%d_%H-%M')
        shutil.copy2(DB_PATH, os.path.join(BACKUPS_DIR, f'schedule_backup_{ts}.db'))
    cutoff = (datetime.now() - timedelta(days=30)).strftime('%Y-%m-%d')
    for f in os.listdir(BACKUPS_DIR):
        if f.startswith('schedule_backup_') and f.endswith('.db'):
            date_part = f.replace('schedule_backup_', '').split('_')[0]
            if date_part < cutoff:
                os.remove(os.path.join(BACKUPS_DIR, f))
    run_alembic_upgrade()
    init_db()
    _cleanup_old_deleted()
    app.run(debug=DEBUG, host=HOST, port=PORT)
