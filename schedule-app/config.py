# Изменение №1 (бэкенд-рефакторинг): выделен config.py

import os
import os.path
import sys
import secrets
import re
from werkzeug.security import generate_password_hash


def _load_env():
    env_path = os.path.join(os.path.dirname(__file__), '.env')
    if os.path.exists(env_path):
        with open(env_path, encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    k, v = line.split('=', 1)
                    os.environ.setdefault(k.strip(), v.strip())


_load_env()

# ---- Secrets ----

PASSWORD = os.environ.get('SCHEDULE_PASSWORD')
if not PASSWORD:
    print("SCHEDULE_PASSWORD не задан в .env")
    sys.exit(1)

if len(PASSWORD) < 8 or not re.search(r'\d', PASSWORD) or not re.search(r'[!@#$%^&*()_+\-=]', PASSWORD):
    print("Пароль должен быть минимум 8 символов, содержать цифру и спецсимвол (!@#$%^&*()_+-=)")
    sys.exit(1)

SECRET_KEY = os.environ.get('SCHEDULE_SECRET_KEY')
if not SECRET_KEY:
    SECRET_KEY = secrets.token_hex(32)
    env_path = os.path.join(os.path.dirname(__file__), '.env')
    with open(env_path, 'a', encoding='utf-8') as f:
        f.write(f"\nSCHEDULE_SECRET_KEY={SECRET_KEY}\n")

ADMIN_PASSWORD_HASH = generate_password_hash(PASSWORD)

# ---- App settings ----

# Чтение из БД с fallback на хардкод (если миграция не применена или таблица пуста)
def _load_settings_from_db():
    try:
        _db_path = os.path.join(
            os.environ.get('SCHEDULE_DATA_DIR', os.path.dirname(__file__)),
            'schedule.db'
        )
        import sqlite3
        conn = sqlite3.connect(_db_path)
        rows = conn.execute('SELECT key, value FROM settings').fetchall()
        conn.close()
        return {r[0]: r[1] for r in rows}
    except Exception:
        return {}

_settings_db = _load_settings_from_db()

PERMANENT_SESSION_LIFETIME = int(_settings_db.get('session_lifetime', 3600))
LOGIN_RATE_LIMIT = int(_settings_db.get('login_rate_limit', 5))
LOGIN_RATE_WINDOW = int(_settings_db.get('login_rate_window', 300))
BACKUP_RETENTION_DAYS = int(_settings_db.get('backup_retention_days', '30'))
TRASH_RETENTION_DAYS = 30

DEBUG = os.environ.get('FLASK_DEBUG', '').lower() in ('1', 'true', 'yes')
HOST = os.environ.get('FLASK_HOST', '127.0.0.1')
PORT = int(os.environ.get('FLASK_PORT', 5000))

# ---- Database ----

DB_DIR = os.path.dirname(__file__)
DB_NAME = 'schedule.db'
DATA_DIR = os.environ.get('SCHEDULE_DATA_DIR', os.path.join(DB_DIR, 'data'))
DB_PATH = os.path.join(DATA_DIR, DB_NAME)
BACKUPS_DIR = os.environ.get('SCHEDULE_BACKUPS_DIR', os.path.join(DB_DIR, 'backups'))

# ---- Bell schedule ----

BELL_SCHEDULE = [
    {"period": 1, "start": "8:30", "end": "9:55", "shift": 1},
    {"period": 2, "start": "10:00", "end": "11:25", "shift": 1},
    {"period": 3, "start": "12:00", "end": "13:25", "shift": 1},
    {"period": 4, "start": "13:30", "end": "14:55", "shift": 2},
    {"period": 5, "start": "15:00", "end": "16:25", "shift": 2},
    {"period": 6, "start": "16:55", "end": "18:20", "shift": 2},
    {"period": 7, "start": "18:25", "end": "19:50", "shift": 3},
    {"period": 8, "start": "19:55", "end": "21:20", "shift": 3},
]

SHIFT_LABELS = {1: '1 смена', 2: '2 смена', 3: '3 смена'}

# ---- Rate limiting ----

LOGIN_RATE_LIMIT = 5
LOGIN_RATE_WINDOW = 300
LOGIN_CLEANUP_INTERVAL = 300
